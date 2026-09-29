from dataclasses import replace
from pathlib import Path

import pytest

from whalezchain_orchestrator.mainnet.block_builder import MainnetBlockBuilder
from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.genesis import (
    GenesisValidator,
    build_genesis,
)
from whalezchain_orchestrator.mainnet.genesis_economic_state import (
    initialize_genesis_economic_state,
    economic_state_root,
)
from whalezchain_orchestrator.mainnet.state_transition import state_root
from whalezchain_orchestrator.mainnet.transaction_validator import TransactionValidationError
from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    CHAIN_ID,
    account,
    signed_mainnet_transaction,
)


def _genesis():
    economic_state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000.00000000",
    )

    initial_state = {
        account("alice"): {
            "PTN": "10.00000000",
            "PRN": "0.00000000",
            "WHZ": "0.00000000",
        },
    }

    return build_genesis(
        genesis_timestamp="2026-09-20T05:59:00Z",
        initial_state=initial_state,
        validators=(
            GenesisValidator(
                validator_id="validator-1",
                public_key="00" * 32,
            ),
        ),
        authority_config={"mode": "test"},
        economic_state=economic_state,
    )


def test_finalized_block_survives_store_reopen_and_persisted_tampering_is_rejected(
    tmp_path: Path,
):
    genesis = _genesis()
    sender = account("alice")
    recipient = account("bob")

    tx = signed_mainnet_transaction(
        tx_id="tx-persistence-001",
        sender_label="alice",
        recipient_label="bob",
        asset_symbol="PTN",
        amount="1.00000000",
        nonce=0,
        ordering_key="00000000000000000001",
    )

    next_state = {
        sender: {
            "PTN": "9.00000000",
            "PRN": "0.00000000",
            "WHZ": "0.00000000",
        },
        recipient: {
            "PTN": "1.00000000",
            "PRN": "0.00000000",
            "WHZ": "0.00000000",
        },
    }

    builder = MainnetBlockBuilder()
    block = builder.build(
        chain_id=CHAIN_ID,
        height=0,
        previous_block_hash="",
        timestamp="2026-09-20T06:00:00Z",
        transactions=(tx,),
        resulting_state_root=state_root(next_state),
        economic_state_root=economic_state_root(genesis.economic_state),
        proposer_id="validator-1",
    )

    finalized = replace(
        block,
        consensus_evidence={
            "status": "finalized",
            "finalized": True,
        },
    )

    store = MainnetChainStore(tmp_path)
    store.initialize_genesis(genesis)

    store.append_finalized_block(
        finalized,
        expected_state=genesis.initial_state,
    )

    assert store.committed(tx.tx_hash) is True

    reopened = MainnetChainStore(tmp_path)

    assert reopened.finalized_head()["height"] == 0
    assert reopened.committed(tx.tx_hash) is True
    assert reopened.replay_state() == next_state

    block_path = next((tmp_path / "blocks").glob("00000000000000000000-*.json"))
    data = reopened._read_json(block_path)
    data["transactions"][0]["amount"] = "9.00000000"
    reopened._atomic_write_json(block_path, data)

    with pytest.raises(TransactionValidationError, match="invalid transaction signature"):
        reopened.verify_chain()
