"""Fail-closed private provenance and financial-release boundaries."""
from __future__ import annotations

import pytest

from whalezchain_orchestrator.consensus.offline_proof import (
    OfflineProofError,
    verify_and_receipt,
)


def test_financial_mainnet_flag_blocks_offline_devnet_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "true")
    with pytest.raises(OfflineProofError, match="production financial release"):
        verify_and_receipt(
            network=tmp_path / "nonexistent",
            verifier=tmp_path / "none",
            height=4,
            proof=tmp_path / "proof",
            output=tmp_path / "receipt",
        )
    assert not (tmp_path / "receipt").exists()


def test_cannot_certify_a_pre_genesis_block(monkeypatch, tmp_path):
    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", raising=False)
    with pytest.raises(OfflineProofError, match="pre-genesis"):
        verify_and_receipt(
            network=tmp_path / "nonexistent",
            verifier=tmp_path / "none",
            height=1,
            proof=tmp_path / "proof",
            output=tmp_path / "receipt",
        )
    assert not (tmp_path / "receipt").exists()
