"""Regressions for canonical readers against concurrent ChainStore commits."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import fcntl
import threading
import time

from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.tests.mainnet_test_helpers import account
from whalezchain_orchestrator.tests.test_mainnet_chain_store_persistence import _genesis


def test_consistent_snapshot_matches_canonical_genesis(tmp_path):
    store = MainnetChainStore(tmp_path / "isolated")
    genesis = _genesis()
    store.initialize_genesis(genesis)

    snapshot = store.verified_snapshot()
    assert snapshot["verified"] is True
    assert snapshot["height"] == -1
    assert snapshot["block_hash"] == ""
    assert snapshot["blocks_checked"] == 0
    assert snapshot["transactions_indexed"] == 0
    assert snapshot["state"] == genesis.initial_state

    # Mutable result objects are detached from the canonical persisted state.
    snapshot["state"][account("alice")]["PTN"] = "100.00000000"
    assert store.verified_snapshot()["state"] == genesis.initial_state


def test_snapshot_cannot_read_under_active_exclusive_commit_lock(tmp_path):
    store = MainnetChainStore(tmp_path / "isolated")
    store.initialize_genesis(_genesis())
    acquired = threading.Event()

    def read_from_another_thread():
        acquired.set()
        return store.verified_snapshot()

    with (store.root / ".write.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(read_from_another_thread)
                assert acquired.wait(timeout=2)
                time.sleep(0.1)
                assert not future.done(), "snapshot bypassed the writer lock"
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                assert future.result(timeout=4)["height"] == -1
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)



def test_historical_snapshot_requires_an_existing_signed_block(tmp_path):
    import pytest
    from whalezchain_orchestrator.mainnet.chain_store import ChainStoreError

    store = MainnetChainStore(tmp_path / "isolated-historical")
    store.initialize_genesis(_genesis())
    latest = store.verified_snapshot()
    old = store.verified_snapshot_at(-1)
    assert old["state"] == latest["state"]
    assert old["height"] == -1
    assert old["latest_canonical_height"] == -1
    assert old["blocks_checked"] == 0
    with pytest.raises(ChainStoreError, match="exceeds"):
        store.verified_snapshot_at(0)
    with pytest.raises(ChainStoreError, match="invalid"):
        store.verified_snapshot_at(True)
    with pytest.raises(ChainStoreError, match="invalid"):
        store.verified_snapshot_at(-2)
