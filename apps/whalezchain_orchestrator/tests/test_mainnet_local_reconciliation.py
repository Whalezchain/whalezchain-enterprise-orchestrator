"""Test-only reconciliation of balance conservation and persisted nonce checks."""
from dataclasses import replace
from decimal import Decimal

import pytest

from whalezchain_orchestrator.mainnet.block_builder import MainnetBlockBuilder
from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.genesis import GenesisValidator, build_genesis
from whalezchain_orchestrator.mainnet.genesis_economic_state import (
    economic_state_root,
    initialize_genesis_economic_state,
)
from whalezchain_orchestrator.mainnet.state_transition import MainnetStateTransition, state_root
from whalezchain_orchestrator.mainnet.transaction_validator import TransactionValidationError
from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    CHAIN_ID,
    account,
    signed_mainnet_transaction,
)


def _state():
    return {account("alice"): {"WHZ": "10.00000000", "PTN": "0.00000000", "PRN": "0.00000000"}}


def _tx(name, recipient, nonce):
    return signed_mainnet_transaction(
        tx_id=name, sender_label="alice", recipient_label=recipient,
        asset_symbol="WHZ", amount="1.00000000", nonce=nonce,
        ordering_key=f"{nonce:020d}",
    )


def test_self_transfer_consumes_nonce_before_following_transfer():
    original = _state()
    nonces = {account("alice"): 7}
    result = MainnetStateTransition().apply(
        original, [_tx("self-seven", "alice", 7), _tx("next-eight", "bob", 8)],
        chain_id=CHAIN_ID, expected_nonces=nonces,
    )
    assert result["state"][account("alice")]["WHZ"] == "9.00000000"
    assert result["state"][account("bob")]["WHZ"] == "1.00000000"
    assert result["transitions"][0]["before_state_root"] == result["transitions"][0]["after_state_root"]
    assert result["transaction_count"] == 2
    assert nonces == {account("alice"): 7}
    assert original == _state()


def test_repeated_nonce_after_self_transfer_is_rejected_atomically():
    original = _state()
    with pytest.raises(TransactionValidationError, match="nonce does not match"):
        MainnetStateTransition().apply(
            original, [_tx("self-zero", "alice", 0), _tx("repeat-zero", "bob", 0)],
            chain_id=CHAIN_ID, expected_nonces={},
        )
    assert original == _state()


def test_self_transfer_and_next_nonce_survive_reopen_and_replay(tmp_path):
    genesis = build_genesis(
        genesis_timestamp="2026-10-27T00:00:00Z", initial_state=_state(),
        validators=(GenesisValidator(validator_id="test-validator", public_key="00" * 32),),
        authority_config={"mode": "test"},
        economic_state=initialize_genesis_economic_state(ptn_genesis_supply="1000.00000000"),
    )
    store = MainnetChainStore(tmp_path)
    store.initialize_genesis(genesis)
    self_tx = _tx("persist-self", "alice", 0)
    block = MainnetBlockBuilder().build(
        chain_id=CHAIN_ID, height=0, previous_block_hash="",
        timestamp="2026-10-27T00:01:00Z", transactions=(self_tx,),
        resulting_state_root=state_root(_state()),
        economic_state_root=economic_state_root(genesis.economic_state), proposer_id="test-validator",
    )
    # Synthetic finality evidence is a unit-test fixture, never production consensus.
    finalized = replace(block, consensus_evidence={"status": "finalized", "finalized": True})
    store.append_finalized_block(finalized, expected_state=_state())
    reopened = MainnetChainStore(tmp_path)
    assert reopened.replay_state() == _state()
    following = _tx("persist-next", "bob", 1)
    expected = _state()
    expected[account("alice")]["WHZ"] = "9.00000000"
    expected[account("bob")] = {"WHZ": "1.00000000", "PTN": "0.00000000", "PRN": "0.00000000"}
    second = MainnetBlockBuilder().build(
        chain_id=CHAIN_ID, height=1, previous_block_hash=finalized.block_hash,
        timestamp="2026-10-27T00:02:00Z", transactions=(following,),
        resulting_state_root=state_root(expected),
        economic_state_root=economic_state_root(genesis.economic_state), proposer_id="test-validator",
    )
    reopened.append_finalized_block(
        replace(second, consensus_evidence={"status": "finalized", "finalized": True}),
        expected_state=_state(),
    )
    fresh = MainnetChainStore(tmp_path)
    fresh.verify_chain()
    assert fresh.replay_state() == expected
    assert fresh.committed(self_tx.tx_hash)
    assert fresh.committed(following.tx_hash)
    assert sum(Decimal(a["WHZ"]) for a in expected.values()) == Decimal("10")
