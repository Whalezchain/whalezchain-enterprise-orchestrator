"""Synthetic recovery tests; never open a live chain store."""
from dataclasses import replace
import json

import pytest

from whalezchain_orchestrator.mainnet.block_builder import MainnetBlockBuilder
from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore, ChainStoreError
from whalezchain_orchestrator.mainnet.genesis_economic_state import economic_state_root
from whalezchain_orchestrator.mainnet.state_transition import state_root
from whalezchain_orchestrator.tests.test_mainnet_chain_store_persistence import _genesis


def chain(tmp_path, count=2):
    genesis = _genesis()
    store = MainnetChainStore(tmp_path)
    store.initialize_genesis(genesis)
    previous = ''
    for height in range(count):
        block = MainnetBlockBuilder().build(
            chain_id=genesis.chain_id, height=height, previous_block_hash=previous,
            timestamp='2026-11-11T00:00:00Z', transactions=(),
            resulting_state_root=genesis.state_root,
            economic_state_root=economic_state_root(genesis.economic_state),
            proposer_id='validator-1')
        block = replace(block, consensus_evidence={'finalized': True})
        store.append_finalized_block(block, expected_state=genesis.initial_state)
        previous = block.block_hash
    return store, genesis


def snapshot(store):
    return {p.name: p.read_bytes() for p in store.meta_dir.glob('*.json')}


@pytest.mark.parametrize('missing', ['head', 'index', 'both'])
def test_rebuild_missing_derived_metadata(tmp_path, missing):
    store, genesis = chain(tmp_path)
    expected = store.finalized_head()
    if missing in ('head', 'both'):
        store.head_path.unlink()
    if missing in ('index', 'both'):
        store.tx_index_path.unlink()
    result = store.reconcile()
    assert result['height'] == 1
    assert store.finalized_head() == expected
    assert store.replay_state() == genesis.initial_state
    assert store.verify_chain()['verified'] is True


def test_gap_never_silently_truncates_recovery(tmp_path):
    store, _ = chain(tmp_path, 3)
    next(store.blocks_dir.glob('00000000000000000001-*.json')).unlink()
    before = snapshot(store)
    with pytest.raises(ChainStoreError):
        store.reconcile()
    assert snapshot(store) == before


def test_append_rejects_invented_starting_balances(tmp_path):
    store, genesis = chain(tmp_path, 0)
    invented = {**genesis.initial_state, 'invented': {'PTN': '1000000.00000000'}}
    block = MainnetBlockBuilder().build(
        chain_id=genesis.chain_id, height=0, previous_block_hash='',
        timestamp='2026-11-11T00:00:00Z', transactions=(),
        resulting_state_root=state_root(invented),
        economic_state_root=economic_state_root(genesis.economic_state),
        proposer_id='validator-1')
    block = replace(block, consensus_evidence={'finalized': True})
    with pytest.raises(ChainStoreError, match='starting state'):
        store.append_finalized_block(block, expected_state=invented)
    assert not list(store.blocks_dir.glob('*.json'))


def test_replay_checks_block_hash_and_finality(tmp_path):
    store, _ = chain(tmp_path)
    path = next(store.blocks_dir.glob('00000000000000000000-*.json'))
    data = json.loads(path.read_text())
    data['consensus_evidence'] = {'finalized': False}
    path.write_text(json.dumps(data))
    with pytest.raises(ChainStoreError):
        store.replay_state()


def test_genesis_tampering_prevents_recovery_writes(tmp_path):
    store, _ = chain(tmp_path, 0)
    data = json.loads(store.genesis_path.read_text())
    data['authority_config'] = {'mode': 'tampered'}
    store.genesis_path.write_text(json.dumps(data))
    before = snapshot(store)
    with pytest.raises(ValueError):
        store.reconcile()
    assert snapshot(store) == before


def test_misnamed_canonical_block_rejected(tmp_path):
    store, _ = chain(tmp_path, 1)
    path = next(store.blocks_dir.glob('*.json'))
    path.rename(path.with_name('00000000000000000000-' + 'f' * 64 + '.json'))
    with pytest.raises(ChainStoreError):
        store.verify_chain()


def test_missing_tail_cannot_roll_back_recorded_head(tmp_path):
    store, _ = chain(tmp_path, 2)
    next(store.blocks_dir.glob('00000000000000000001-*.json')).unlink()
    before = snapshot(store)
    with pytest.raises(ChainStoreError, match='missing'):
        store.reconcile()
    assert snapshot(store) == before


def test_recovery_checks_independent_checkpoint_before_writing(tmp_path):
    store, _ = chain(tmp_path)
    before = snapshot(store)
    wrong = {**store.finalized_head(), 'state_root': 'f' * 64}
    with pytest.raises(ChainStoreError, match='checkpoint'):
        store.reconcile(expected_head=wrong)
    assert snapshot(store) == before
    store.reconcile(expected_head=store.finalized_head())


def test_interrupted_head_write_recovers_from_canonical_block(tmp_path, monkeypatch):
    store, genesis = chain(tmp_path, 0)
    write = store._atomic_write_json
    def fail_head(path, value):
        if path == store.head_path:
            raise OSError('simulated interrupted head write')
        write(path, value)
    monkeypatch.setattr(store, '_atomic_write_json', fail_head)
    block = MainnetBlockBuilder().build(chain_id=genesis.chain_id, height=0,
        previous_block_hash='', timestamp='2026-11-11T00:00:00Z', transactions=(),
        resulting_state_root=genesis.state_root,
        economic_state_root=economic_state_root(genesis.economic_state), proposer_id='validator-1')
    with pytest.raises(OSError):
        store.append_finalized_block(replace(block, consensus_evidence={'finalized': True}),
                                     expected_state=genesis.initial_state)
    assert store.finalized_head()['height'] == -1
    fresh = MainnetChainStore(tmp_path)
    assert fresh.reconcile()['height'] == 0
    assert fresh.verify_chain()['verified'] is True


def test_competing_writers_cannot_commit_two_blocks_at_same_height(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store, genesis = chain(tmp_path, 0)
    base = MainnetBlockBuilder().build(chain_id=genesis.chain_id, height=0,
        previous_block_hash='', timestamp='2026-11-11T00:00:00Z', transactions=(),
        resulting_state_root=genesis.state_root,
        economic_state_root=economic_state_root(genesis.economic_state), proposer_id='validator-1')
    def append(proposer):
        block = replace(base, proposer_id=proposer, consensus_evidence={'finalized': True})
        try:
            MainnetChainStore(tmp_path).append_finalized_block(block, expected_state=genesis.initial_state)
            return True
        except ChainStoreError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append, ['a', 'b']))
    assert sorted(results) == [False, True]
    assert len(list(store.blocks_dir.glob('*.json'))) == 1
    assert store.verify_chain()['verified'] is True


def test_historical_balance_root_mismatch_is_preserved_for_review(tmp_path):
    store, _ = chain(tmp_path)
    path = next(store.blocks_dir.glob('00000000000000000000-*.json'))
    data = json.loads(path.read_text())
    data['resulting_state_root'] = 'f' * 64
    path.write_text(json.dumps(data))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*.json')}
    with pytest.raises(ChainStoreError, match='state replay mismatch'):
        store.reconcile()
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*.json')} == before
