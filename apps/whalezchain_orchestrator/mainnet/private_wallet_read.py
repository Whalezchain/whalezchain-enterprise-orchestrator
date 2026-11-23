"""Owner-signed internal wallet balance query against canonical WhalezChain.

This is a *private synthetic test-genesis* read boundary; it is not a
production wallet, financial signer, or ledger mutation API. Only a genuine
Ed25519 signature from the requested account can read its balances. The
canonical state is replay-verified under ChainStore's reader lock.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .authentication import derive_account_id
from .chain_store import MainnetChainStore
from .cometbft_state_machine import _app_hash
from .transaction import canonical_json, sha256_hex


SCHEMA = "whalezchain.internal.wallet_query.v1"
SIGNING_DOMAIN = b"WHALEZCHAIN/WALLET/OWNER-QUERY/V1\x00"
PERMIT_FIELDS = frozenset({
    "schema", "account_id", "chain_id", "owner_public_key_hex",
    "issued_at", "expires_at", "nonce_hex",
})
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX128 = re.compile(r"[0-9a-f]{128}\Z")


class PrivateWalletReadError(ValueError):
    pass


@dataclass(frozen=True)
class TrustedFinalityCheckpoint:
    """Paths provisioned by the private operator, never from the request."""

    comet_genesis: Path
    signed_header_proof: Path
    verifier_binary: Path
    signed_header_height: int


def _trusted_regular_file(path: Path, *, max_bytes: int, private: bool) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise PrivateWalletReadError("untrusted_wallet_finality_proof_path")
    try:
        info = path.stat()
    except OSError as exc:
        raise PrivateWalletReadError("missing_wallet_finality_trust_anchor") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_size <= 0
        or info.st_size > max_bytes
        or (private and stat.S_IMODE(info.st_mode) & 0o077)
        or (not private and stat.S_IMODE(info.st_mode) & 0o022)
    ):
        raise PrivateWalletReadError("untrusted_wallet_finality_trust_anchor")
    return path.read_bytes()


def _verify_finality_checkpoint(
    store: MainnetChainStore,
    canonical_genesis: dict,
    checkpoint: TrustedFinalityCheckpoint,
) -> tuple[dict, dict]:
    if (
        not isinstance(checkpoint, TrustedFinalityCheckpoint)
        or type(checkpoint.signed_header_height) is not int
        or checkpoint.signed_header_height < 2
    ):
        raise PrivateWalletReadError("invalid_signed_finality_checkpoint")
    comet_bytes = _trusted_regular_file(
        checkpoint.comet_genesis, max_bytes=200000, private=True
    )
    proof_bytes = _trusted_regular_file(
        checkpoint.signed_header_proof, max_bytes=1048576, private=True
    )
    verifier = checkpoint.verifier_binary
    if not verifier.is_absolute() or verifier.is_symlink():
        raise PrivateWalletReadError("invalid_wallet_verifier_binary")
    try:
        verifier_info = verifier.stat()
    except OSError as exc:
        raise PrivateWalletReadError("wallet_verifier_binary_unavailable") from exc
    if (
        not stat.S_ISREG(verifier_info.st_mode)
        or verifier_info.st_uid != os.getuid()
        or verifier_info.st_size < 1000
        or verifier_info.st_size > 100000000
        or stat.S_IMODE(verifier_info.st_mode) & 0o022
        or not stat.S_IMODE(verifier_info.st_mode) & 0o100
    ):
        raise PrivateWalletReadError("untrusted_wallet_verifier_binary")
    try:
        trusted = json.loads(comet_bytes)
    except (ValueError, TypeError) as exc:
        raise PrivateWalletReadError("invalid_trusted_comet_genesis") from exc
    network = trusted.get("chain_id") if type(trusted) is dict else None
    if (
        type(network) is not str
        or not network.startswith("whalezchain-internal-devnet-")
        or type(trusted.get("app_state")) is not dict
        or trusted["app_state"].get("whalez_genesis_hash") !=
            canonical_genesis["genesis_hash"]
    ):
        raise PrivateWalletReadError("comet_and_whalez_genesis_not_pinned_together")

    height = checkpoint.signed_header_height - 2
    snapshot = store.verified_snapshot_at(height)
    expected_app_hash = _app_hash(
        height + 1, snapshot["block_hash"],
        snapshot["state_root"], snapshot["economic_state_root"],
    )
    cmd = [
        str(checkpoint.verifier_binary),
        "--proof-in", str(checkpoint.signed_header_proof),
        "--genesis", str(checkpoint.comet_genesis),
        "--height", str(checkpoint.signed_header_height),
        "--expected-apphash", expected_app_hash,
    ]
    try:
        process = subprocess.run(
            cmd, capture_output=True, text=True, timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PrivateWalletReadError("wallet_finality_verifier_unavailable") from exc
    if process.returncode != 0:
        raise PrivateWalletReadError("wallet_consensus_signature_or_state_invalid")
    try:
        report = json.loads(process.stdout)
    except ValueError as exc:
        raise PrivateWalletReadError("invalid_consensus_verifier_result") from exc
    if not (
        type(report) is dict
        and report.get("verified") is True
        and report.get("verification_mode") == "offline_signature_cryptographic"
        and report.get("network_chain_id") == network
        and report.get("certified_whalez_block_height") == height
        and report.get("signed_header_prior_app_hash") == expected_app_hash
        and type(report.get("signed_votes_for_block")) is int
        and report["signed_votes_for_block"] >= 3
        and report.get("validator_count") == 4
    ):
        raise PrivateWalletReadError("consensus_and_state_proof_contract_failed")
    return snapshot, {
        "independent_consensus_finality_verified": True,
        "finality_verification_source": "cometbft_signed_header_offline",
        "signed_header_height": checkpoint.signed_header_height,
        "certified_whalez_height": height,
        "latest_canonical_height": snapshot["latest_canonical_height"],
        "consensus_signatures": report["signed_votes_for_block"],
        "signed_proof_sha256": hashlib.sha256(proof_bytes).hexdigest(),
    }


def _validated_permit(signed_query: Any, chain_id: str, now: int) -> str:
    if type(signed_query) is not dict or set(signed_query) != PERMIT_FIELDS | {"signature_hex"}:
        raise PrivateWalletReadError("invalid_wallet_query_schema")
    if (
        signed_query["schema"] != SCHEMA
        or signed_query["chain_id"] != chain_id
        or type(now) is not int
    ):
        raise PrivateWalletReadError("wrong_wallet_query_network_or_schema")
    for name in ("nonce_hex", "owner_public_key_hex"):
        if (
            type(signed_query[name]) is not str
            or not HEX64.fullmatch(signed_query[name])
        ):
            raise PrivateWalletReadError("invalid_wallet_owner_proof")
    if (
        type(signed_query["signature_hex"]) is not str
        or not HEX128.fullmatch(signed_query["signature_hex"])
    ):
        raise PrivateWalletReadError("invalid_wallet_owner_signature")
    issued, expires = signed_query["issued_at"], signed_query["expires_at"]
    if (
        type(issued) is not int or type(expires) is not int
        or not issued < expires <= issued + 60
        or not issued - 30 <= now < expires
    ):
        raise PrivateWalletReadError("expired_wallet_owner_query")
    public_key = bytes.fromhex(signed_query["owner_public_key_hex"])
    if (
        type(signed_query["account_id"]) is not str
        or signed_query["account_id"] != derive_account_id(public_key)
    ):
        raise PrivateWalletReadError("wallet_owner_and_requested_account_differ")
    unsigned = {
        key: signed_query[key] for key in PERMIT_FIELDS
    }
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(signed_query["signature_hex"]),
            SIGNING_DOMAIN + canonical_json(unsigned),
        )
    except (InvalidSignature, ValueError) as exc:
        raise PrivateWalletReadError("wallet_owner_signature_invalid") from exc
    return signed_query["account_id"]


def query_verified_wallet(
    store: MainnetChainStore, signed_query: Mapping[str, Any],
    *, now: int | None = None,
    trusted_finality: TrustedFinalityCheckpoint | None = None,
) -> dict[str, Any]:
    """Read an owner-signed balance at the exact verified chain height.

    Without an independent trusted signed header, the latest balance is
    replay-verified only and explicitly marked uncertified. With one, balances
    are derived from the exact earlier checkpoint authenticated by the proof.
    """
    if os.getenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "").lower() == "true":
        raise PrivateWalletReadError("live_financial_mainnet_forbidden")
    genesis = store.load_genesis()
    if genesis.get("authority_config", {}).get("mode") != "test":
        raise PrivateWalletReadError("private_wallet_reader_requires_synthetic_test_genesis")
    if not isinstance(signed_query, dict):
        raise PrivateWalletReadError("invalid_wallet_query_schema")
    address = _validated_permit(
        signed_query, store.chain_id,
        int(time.time()) if now is None else now,
    )
    if trusted_finality is None:
        snapshot = store.verified_snapshot()
        finality = {
            "independent_consensus_finality_verified": False,
            "finality_verification_source": "none",
            "latest_canonical_height": snapshot["height"],
        }
    else:
        snapshot, finality = _verify_finality_checkpoint(
            store, genesis, trusted_finality
        )
    state = snapshot["state"]
    registry = genesis["asset_registry"]
    if type(registry) is not dict:
        raise PrivateWalletReadError("untrusted_asset_registry")
    values = state.get(address, {})
    balances = {
        asset: values.get(asset, "0.00000000")
        for asset in sorted(registry)
    }
    return {
        "ok": True,
        "schema": "whalezchain.private.wallet_query_response.v1",
        "account_id": address,
        "chain_id": store.chain_id,
        "balances": balances,
        "canonical_height": snapshot["height"],
        "canonical_block_hash": snapshot["block_hash"],
        "state_root": snapshot["state_root"],
        "economic_state_root": snapshot["economic_state_root"],
        "genesis_hash": genesis["genesis_hash"],
        "owner_signature_verified": True,
        "canonical_state_replay_verified": True,
        **finality,
        "execution_mode": "internal_devnet_read_only",
        "real_financial_operations": False,
        "side_effects_performed": False,
        "query_commitment_sha256": sha256_hex(signed_query),
    }
