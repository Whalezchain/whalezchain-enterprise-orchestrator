"""Fail-closed release gate: a bare finalized flag is not BFT consensus."""
from types import SimpleNamespace

import pytest

from apps.whalezchain_orchestrator.mainnet.chain_store import (
    ChainStoreError,
    MainnetChainStore,
)


@pytest.mark.parametrize("live_flag", ["true", "TRUE"])
def test_live_mainnet_rejects_unverified_finalized_boolean(
    monkeypatch, tmp_path, live_flag
):
    monkeypatch.setenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", live_flag)
    store = MainnetChainStore(tmp_path / "isolated-mainnet")
    forged = SimpleNamespace(
        consensus_evidence={"status": "finalized", "finalized": True}
    )
    with pytest.raises(
        ChainStoreError, match="network_validator_quorum_finality_unavailable"
    ):
        store.append_finalized_block(forged, expected_state={})
    assert not store.genesis_path.exists()
    assert not any(store.blocks_dir.iterdir())


def test_disabled_mainnet_flag_cannot_bootstrap_canonical_without_genesis(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", raising=False)
    store = MainnetChainStore(tmp_path / "isolated-mainnet")
    with pytest.raises(ChainStoreError):
        store.append_finalized_block(
            SimpleNamespace(consensus_evidence={"finalized": True}),
            expected_state={},
        )
    assert not store.genesis_path.exists()
