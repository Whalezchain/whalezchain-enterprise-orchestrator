"""Owner-signed, canonical private wallet read and denial regressions."""
from __future__ import annotations

from dataclasses import replace
import http.client
import json
import os
from pathlib import Path
import socket
import threading
import tempfile

import pytest

from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.private_wallet_read import (
    PrivateWalletReadError,
    SCHEMA,
    SIGNING_DOMAIN,
    query_verified_wallet,
)
from whalezchain_orchestrator.mainnet.private_wallet_server import (
    PrivateWalletUnixServer,
)
from whalezchain_orchestrator.mainnet.transaction import canonical_json
from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    account, private_key,
)
from whalezchain_orchestrator.tests.test_mainnet_chain_store_persistence import (
    _genesis,
)


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", raising=False)
    store = MainnetChainStore(tmp_path / "synthetic-node")
    store.initialize_genesis(_genesis())
    return store


def signed_owner_query(label="alice", *, now=1780000000, target=None):
    key = private_key(label)
    body = {
        "schema": SCHEMA,
        "account_id": target or account(label),
        "chain_id": "whalezchain-mainnet-v1",
        "owner_public_key_hex": key.public_key().public_bytes_raw().hex(),
        "issued_at": now,
        "expires_at": now + 45,
        "nonce_hex": "1f" * 32,
    }
    return {
        **body,
        "signature_hex": key.sign(
            SIGNING_DOMAIN + canonical_json(body)
        ).hex(),
    }


def test_owner_signed_canonical_balance_and_no_mutation(store):
    before = store.verified_snapshot()
    query = signed_owner_query()
    result = query_verified_wallet(store, query, now=query["issued_at"] + 1)
    assert result["ok"]
    assert result["owner_signature_verified"] is True
    assert result["canonical_state_replay_verified"] is True
    assert result["independent_consensus_finality_verified"] is False
    assert result["balances"]["PTN"] == "10.00000000"
    assert result["account_id"] == account("alice")
    assert result["side_effects_performed"] is False
    assert store.verified_snapshot() == before


def test_cannot_query_other_account_or_tamper_balance(store):
    owner = signed_owner_query("alice", target=account("bob"))
    with pytest.raises(PrivateWalletReadError, match="wallet_owner"):
        query_verified_wallet(store, owner, now=owner["issued_at"] + 1)

    approved = signed_owner_query()
    approved["account_id"] = account("bob")
    with pytest.raises(PrivateWalletReadError):
        query_verified_wallet(store, approved, now=approved["issued_at"] + 1)

    approved = signed_owner_query()
    approved["nonce_hex"] = "2e" * 32
    with pytest.raises(PrivateWalletReadError, match="signature"):
        query_verified_wallet(store, approved, now=approved["issued_at"] + 1)


def test_expiration_schema_and_financial_guards(store, monkeypatch):
    signed = signed_owner_query()
    with pytest.raises(PrivateWalletReadError, match="expired"):
        query_verified_wallet(store, signed, now=signed["expires_at"])
    signed["mint"] = True
    with pytest.raises(PrivateWalletReadError, match="schema"):
        query_verified_wallet(store, signed, now=signed["issued_at"] + 1)
    monkeypatch.setenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "true")
    with pytest.raises(PrivateWalletReadError, match="forbidden"):
        query_verified_wallet(store, signed, now=signed["issued_at"] + 1)


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: Path):
        super().__init__("localhost", timeout=3)
        self.path = str(path)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(3)
        self.sock.connect(self.path)


def test_real_unix_socket_cryptographic_owner_query(store, tmp_path, monkeypatch):
    # Stable wall clock for the duration of this server integration.
    monkeypatch.setattr(
        "whalezchain_orchestrator.mainnet.private_wallet_read.time.time",
        lambda: 1780000001,
    )
    socket_dir = Path(tempfile.mkdtemp(prefix=".wcz-wallet-", dir=Path.home()))
    os.chmod(socket_dir, 0o700)
    path = socket_dir / "wallet.sock"
    server = PrivateWalletUnixServer(path, store)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        assert path.stat().st_mode & 0o777 == 0o600
        authorized = signed_owner_query()
        with UnixConnection(path) as client:
            client.request(
                "POST", "/v1/private/wallet/query",
                body=json.dumps(authorized), headers={
                    "Content-Type": "application/json",
                },
            )
            reply = client.getresponse()
            result = json.loads(reply.read())
        assert reply.status == 200
        assert result["account_id"] == account("alice")
        assert result["balances"]["PTN"] == "10.00000000"

        unauthorized = signed_owner_query(target=account("bob"))
        with UnixConnection(path) as client:
            client.request(
                "POST", "/v1/private/wallet/query",
                body=json.dumps(unauthorized),
            )
            denied = client.getresponse()
            assert denied.status == 403
            assert json.loads(denied.read())["ok"] is False
    finally:
        server.shutdown()
        server.server_close()
        path.unlink(missing_ok=True)
        socket_dir.rmdir()
        worker.join(timeout=3)



def test_finality_configured_must_verify_or_deny(store, tmp_path):
    from whalezchain_orchestrator.mainnet.private_wallet_read import (
        TrustedFinalityCheckpoint,
    )

    query = signed_owner_query()
    finality = TrustedFinalityCheckpoint(
        comet_genesis=tmp_path / "unknown-genesis.json",
        signed_header_proof=tmp_path / "unknown-proof.json",
        verifier_binary=tmp_path / "unknown-verifier",
        signed_header_height=4,
    )
    with pytest.raises(PrivateWalletReadError, match="missing_wallet_finality"):
        query_verified_wallet(
            store, query, now=query["issued_at"] + 1,
            trusted_finality=finality,
        )
