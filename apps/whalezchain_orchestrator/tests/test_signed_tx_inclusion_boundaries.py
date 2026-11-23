"""Negative tests for independent CometBFT finality and tx inclusion bridge."""
from __future__ import annotations

from pathlib import Path

import pytest

from whalezchain_orchestrator.consensus.signed_tx_inclusion import (
    SignedInclusionError, verify_signed_transaction_inclusion,
)


def request(tmp_path, txhash="12" * 32, height=5):
    return dict(
        network=tmp_path / "nonexistent-network",
        verifier_binary=tmp_path / "nonexistent-verifier",
        signed_header_proof=tmp_path / "no-proof",
        signed_header_height=height,
        signed_tx_sha256=txhash,
    )


def test_production_execution_flag_denied(monkeypatch, tmp_path):
    monkeypatch.setenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "true")
    with pytest.raises(SignedInclusionError, match="forbidden"):
        verify_signed_transaction_inclusion(**request(tmp_path))


def test_invalid_transaction_id_and_header_height_denied(monkeypatch, tmp_path):
    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", raising=False)
    for args in (
        request(tmp_path, txhash="not-a-hash"),
        request(tmp_path, height=0),
        request(tmp_path, height=True),
    ):
        with pytest.raises(SignedInclusionError, match="invalid_signed_inclusion_request"):
            verify_signed_transaction_inclusion(**args)


def test_missing_canonical_network_cannot_authenticate_caller_claim(tmp_path, monkeypatch):
    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", raising=False)
    with pytest.raises(SignedInclusionError, match="unknown_internal_validator_network"):
        verify_signed_transaction_inclusion(**request(tmp_path))
