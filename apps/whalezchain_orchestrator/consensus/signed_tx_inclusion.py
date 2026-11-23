"""Read-only independently signed CometBFT transaction inclusion proof.

The actual WhalezChain ledger remains canonical. A caller-provided
"finalized": true, RPC success, or success-shaped JSON is NOT sufficient.
The official Go verifier checks real Ed25519 voting power against trusted
genesis and the exact WhalezChain application state commitment.

This is scoped to synthetic internal devnet, not production mainnet, real
wallet custody or external financial settlement. Never expose this as a
public payment-certification API.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from .devnet_bootstrap import NETWORK
from .offline_proof import _run_verifier
from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.cometbft_state_machine import _app_hash
from whalezchain_orchestrator.mainnet.transaction import canonical_json


HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class SignedInclusionError(ValueError):
    pass


def verify_signed_transaction_inclusion(
    *, network: Path, verifier_binary: Path, signed_header_proof: Path,
    signed_header_height: int, signed_tx_sha256: str,
) -> dict:
    """Return a bound inclusion receipt or raise. No ledger mutation."""
    if os.getenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "").lower() == "true":
        raise SignedInclusionError("production_mainnet_financial_release_forbidden")
    if (
        type(signed_header_height) is not int
        or signed_header_height < 2
        or type(signed_tx_sha256) is not str
        or HEX64.fullmatch(signed_tx_sha256) is None
    ):
        raise SignedInclusionError("invalid_signed_inclusion_request")
    if any(not isinstance(p, Path) or p.is_symlink() for p in (
        network, verifier_binary, signed_header_proof,
    )):
        raise SignedInclusionError("untrusted_signed_inclusion_source")
    manifest_path = network / "devnet_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        raise SignedInclusionError("unknown_internal_validator_network") from exc
    if manifest.get("network_chain_id") != NETWORK or manifest.get("nodes") != 4:
        raise SignedInclusionError("unqualified_internal_validator_network")
    store = MainnetChainStore(network / "node0" / "whalez-state")
    genesis = store.load_genesis()
    if genesis["authority_config"].get("mode") != "test":
        raise SignedInclusionError("synthetic_test_genesis_required")
    if manifest["whalez_genesis_hash"] != genesis["genesis_hash"]:
        raise SignedInclusionError("manifest_and_canonical_genesis_mismatch")
    comet_path = network / "node0" / "config" / "genesis.json"
    try:
        comet_genesis = json.loads(comet_path.read_text())
    except (OSError, ValueError) as exc:
        raise SignedInclusionError("trusted_comet_genesis_unavailable") from exc
    if not (
        comet_genesis.get("chain_id") == NETWORK
        and comet_genesis.get("app_state", {}).get("whalez_genesis_hash")
            == genesis["genesis_hash"]
    ):
        raise SignedInclusionError("comet_and_canonical_genesis_identity_mismatch")
    certified_height = signed_header_height - 2
    snapshot = store.verified_snapshot_at(certified_height)
    expected = _app_hash(
        certified_height + 1,
        snapshot["block_hash"], snapshot["state_root"],
        snapshot["economic_state_root"],
    )
    try:
        cryptographic = _run_verifier(
            verifier_binary, comet_path, signed_header_height,
            expected, signed_header_proof,
        )
    except (OSError, ValueError, TimeoutError) as exc:
        raise SignedInclusionError("independent_signature_verifier_unavailable") from exc
    if cryptographic.returncode != 0:
        raise SignedInclusionError("signed_consensus_proof_rejected")
    try:
        proof = json.loads(cryptographic.stdout)
    except ValueError as exc:
        raise SignedInclusionError("signed_consensus_verifier_invalid_output") from exc
    if not (
        type(proof) is dict
        and proof.get("verified") is True
        and proof.get("verification_mode") == "offline_signature_cryptographic"
        and proof.get("network_chain_id") == NETWORK
        and proof.get("signed_header_prior_app_hash") == expected
        and proof.get("certified_whalez_block_height") == certified_height
        and type(proof.get("signed_votes_for_block")) is int
        and proof["signed_votes_for_block"] >= 3
        and proof.get("validator_count") == 4
    ):
        raise SignedInclusionError("signed_consensus_output_contract_rejected")
    inclusion = []
    for height in range(certified_height + 1):
        block = store._load_block(height)
        for record in block["transactions"]:
            try:
                tx = store._transaction_from_dict(record)
            except (TypeError, ValueError, KeyError) as exc:
                raise SignedInclusionError("corrupt_canonical_transaction") from exc
            if tx.tx_hash == signed_tx_sha256:
                inclusion.append((height, block["block_hash"], tx.tx_hash))
    if len(inclusion) != 1:
        raise SignedInclusionError("transaction_not_uniquely_included_in_certified_state")
    tx_height, block_hash, authenticated_tx_hash = inclusion[0]
    if authenticated_tx_hash != signed_tx_sha256:
        raise SignedInclusionError("canonical_signed_transaction_digest_mismatch")

    receipt = {
        "schema": "whalezchain.internal.signed_tx_inclusion.v1",
        "status": "VERIFIED_SYNTHETIC_CHAIN_INCLUSION",
        "synthetic_test_only": True,
        "network_chain_id": NETWORK,
        "canonical_genesis_hash": genesis["genesis_hash"],
        "signed_tx_sha256": signed_tx_sha256,
        "whalez_inclusion_height": tx_height,
        "whalez_inclusion_block_hash": block_hash,
        "certified_whalez_height": certified_height,
        "comet_signed_header_height": signed_header_height,
        "signed_validator_votes": proof["signed_votes_for_block"],
        "signed_header_proof_sha256": hashlib.sha256(
            signed_header_proof.read_bytes()
        ).hexdigest(),
        "certified_state_root": snapshot["state_root"],
        "certified_economic_state_root": snapshot["economic_state_root"],
        "no_real_financial_operations": True,
        "production_mainnet_certified": False,
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json(receipt)).hexdigest()
    return receipt
