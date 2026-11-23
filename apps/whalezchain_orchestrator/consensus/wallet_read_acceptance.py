"""Hosted acceptance of signed-owner wallet reads with real offline finality.

Uses only existing synthetic devnet identities and persisted CometBFT state.
No production credentials, financial writes, external RPC, or public socket.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.private_wallet_read import (
    SCHEMA, SIGNING_DOMAIN, TrustedFinalityCheckpoint,
)
from whalezchain_orchestrator.mainnet.private_wallet_server import (
    PrivateWalletUnixServer,
)
from whalezchain_orchestrator.mainnet.transaction import canonical_json
from whalezchain_orchestrator.tests.mainnet_test_helpers import account, private_key


class PrivateUnixHTTP(http.client.HTTPConnection):
    def __init__(self, endpoint: Path):
        super().__init__("localhost", timeout=12)
        self.endpoint = str(endpoint)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(12)
        self.sock.connect(self.endpoint)


def signed_owner_query(label: str, *, account_override: str | None = None) -> dict:
    key = private_key(label)
    now = int(time.time())
    body = {
        "schema": SCHEMA,
        "account_id": account_override or account(label),
        "chain_id": "whalezchain-mainnet-v1",
        "owner_public_key_hex": key.public_key().public_bytes_raw().hex(),
        "issued_at": now,
        "expires_at": now + 40,
        "nonce_hex": os.urandom(32).hex(),
    }
    return {
        **body, "signature_hex": key.sign(
            SIGNING_DOMAIN + canonical_json(body)
        ).hex(),
    }


def _query(sock: Path, request: dict) -> tuple[int, dict]:
    conn = PrivateUnixHTTP(sock)
    try:
        conn.request(
            "POST", "/v1/private/wallet/query",
            body=json.dumps(request, sort_keys=True),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        raw = response.read(32769)
        if len(raw) > 32768:
            raise RuntimeError("private wallet exceeded response limit")
        return response.status, json.loads(raw)
    finally:
        conn.close()


def run(network: Path, verifier: Path, proof: Path, height: int, out: Path) -> dict:
    if os.getenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "").lower() == "true":
        raise RuntimeError("live financial mainnet not permitted")
    if out.exists() or out.is_symlink():
        raise RuntimeError("refusing overwrite of private wallet receipt")
    store = MainnetChainStore(network / "node0" / "whalez-state")
    before = store.verified_snapshot()
    finality = TrustedFinalityCheckpoint(
        comet_genesis=network / "node0" / "config" / "genesis.json",
        signed_header_proof=proof,
        verifier_binary=verifier,
        signed_header_height=height,
    )
    base = Path(tempfile.mkdtemp(prefix=".wcz-signedwallet-", dir=Path.home()))
    os.chmod(base, 0o700)
    endpoint = base / "wallet.sock"
    server = PrivateWalletUnixServer(endpoint, store, finality)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    balances = {}
    try:
        for label, expected in (("alice", "9.00000000"), ("bob", "1.00000000")):
            status, response = _query(endpoint, signed_owner_query(label))
            if not (
                status == 200
                and response["ok"] is True
                and response["balances"]["PTN"] == expected
                and response["account_id"] == account(label)
                and response["independent_consensus_finality_verified"] is True
                and response["canonical_state_replay_verified"] is True
                and response["certified_whalez_height"] == height - 2
                and response["signed_header_height"] == height
                and response["consensus_signatures"] >= 3
                and response["side_effects_performed"] is False
            ):
                raise RuntimeError("owner query was not independently certified")
            balances[label] = expected
        denied, _ = _query(
            endpoint, signed_owner_query("alice", account_override=account("bob"))
        )
        if denied != 403:
            raise RuntimeError("cross-owner query was not rejected")
        if store.verified_snapshot() != before:
            raise RuntimeError("owner-only wallet read mutated canonical ledger")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=4)
        endpoint.unlink(missing_ok=True)
        base.rmdir()

    receipt = {
        "schema": "whalezchain.internal.certified_wallet_acceptance.v1",
        "result": "PASS_SYNTHETIC_OWNER_SIGNED_WALLET_FINALITY",
        "verified_at_comet_header_height": height,
        "certified_whalez_block_height": height - 2,
        "latest_whalez_block_height": before["height"],
        "synthetic_balances_ptn": balances,
        "forged_account_query_rejected": True,
        "canonical_state_unchanged": True,
        "independent_signed_quorum_verified": True,
        "synthetic_only": True,
        "real_financial_operations": False,
        "external_networks_used": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write((json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
        file.flush()
        os.fsync(file.fileno())
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", required=True, type=Path)
    parser.add_argument("--verifier", required=True, type=Path)
    parser.add_argument("--proof", required=True, type=Path)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run(
        args.network, args.verifier, args.proof, args.height, args.output
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
