from dataclasses import replace
from decimal import Decimal

import pytest

from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.block_builder import MainnetBlockBuilder
from whalezchain_orchestrator.mainnet.genesis import build_genesis
from whalezchain_orchestrator.mainnet.genesis_economic_state import economic_state_root
from whalezchain_orchestrator.mainnet.issuance_policy import policy_from_authority_config, PRNIssuancePolicyError
from whalezchain_orchestrator.mainnet.state_transition import MainnetStateTransition
from whalezchain_orchestrator.mainnet.transaction_validator import TransactionValidationError
from whalezchain_orchestrator.mainnet.authentication import sign_transaction
from whalezchain_orchestrator.tests.test_mainnet_chain_store_persistence import _genesis
from apps.whalezchain_orchestrator.tests.test_mainnet_balance_conservation import ALICE, ALICE_KEY, signed


def test_genesis_committed_issuance_policy_survives_reopen_replay_and_reconcile(tmp_path):
    old = _genesis()
    config = {'mode': 'test', 'prn_issuance_policy': {
        'authorized_issuers': [ALICE], 'max_supply': '5.00000000'}}
    genesis = build_genesis(genesis_timestamp=old.genesis_timestamp,
        initial_state=old.initial_state, validators=old.validator_config,
        economic_state=old.economic_state, authority_config=config)
    policy = policy_from_authority_config(config)
    store = MainnetChainStore(tmp_path)
    store.initialize_genesis(genesis)
    tx = MainnetChainStore._transaction_from_dict(
        signed(asset='PRN', kind='mint_prn', amount='5.00000000').signed_dict())
    result = MainnetStateTransition().apply(genesis.initial_state, [tx],
        chain_id=genesis.chain_id, issuance_policy=policy)
    block = MainnetBlockBuilder().build(chain_id=genesis.chain_id, height=0,
        previous_block_hash='', timestamp='2026-11-11T00:00:00Z', transactions=(tx,),
        resulting_state_root=result['state_root'],
        economic_state_root=economic_state_root(genesis.economic_state), proposer_id='validator-1')
    block = replace(block, consensus_evidence={'finalized': True})
    store.append_finalized_block(block, expected_state=genesis.initial_state)
    fresh = MainnetChainStore(tmp_path)
    assert fresh.verify_chain()['verified'] is True
    assert fresh.replay_state() == result['state']
    fresh.head_path.unlink()
    fresh.tx_index_path.unlink()
    fresh.reconcile()
    assert fresh.replay_state() == result['state']
    second = replace(tx, tx_id='second-mint', nonce=1)
    second = replace(second, authorization=sign_transaction(second, ALICE_KEY))
    # Even a candidate claiming the old root cannot bypass the persisted cap.
    bad = replace(block, height=1, previous_block_hash=block.block_hash, transactions=(second,))
    with pytest.raises(TransactionValidationError, match='maximum supply'):
        fresh.append_finalized_block(bad, expected_state=result['state'])
    assert fresh.finalized_head()['height'] == 0


@pytest.mark.parametrize('data', [None, {}, {'authorized_issuers': 'all', 'max_supply': '5'},
    {'authorized_issuers': [ALICE, ALICE], 'max_supply': '5'},
    {'authorized_issuers': [], 'max_supply': 'NaN'},
    {'authorized_issuers': [ALICE], 'max_supply': '-1'},
    {'authorized_issuers': [ALICE], 'max_supply': '0.000000001'}])
def test_invalid_persisted_policy_rejected(data):
    with pytest.raises(PRNIssuancePolicyError):
        policy_from_authority_config({'prn_issuance_policy': data})


def test_absent_policy_keeps_issuance_disabled():
    assert policy_from_authority_config({}) is None
