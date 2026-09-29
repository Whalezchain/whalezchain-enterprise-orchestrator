from pathlib import Path

import pytest

from apps.whalezchain_orchestrator.mainnet.block_builder import MainnetBlockBuilder
from apps.whalezchain_orchestrator.mainnet.chain_store import (
    ChainStoreError,
    MainnetChainStore,
)
from apps.whalezchain_orchestrator.mainnet.genesis import (
    GenesisValidator,
    build_genesis,
)
from apps.whalezchain_orchestrator.mainnet.genesis_economic_state import (
    initialize_genesis_economic_state,
    economic_state_root,
)
from apps.whalezchain_orchestrator.mainnet.state_transition import state_root


CHAIN_ID = "whalezchain-mainnet-v1"
PUBLIC_KEY = "00" * 32


def _genesis():
    economic_state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000.00000000",
    )

    initial_state = {
        "account-a": {
            "PTN": "10.00000000",
            "PRN": "0.00000000",
            "WHZ": "0.00000000",
        }
    }

    return build_genesis(
        genesis_timestamp="2026-08-30T00:00:00Z",
        initial_state=initial_state,
        validators=(
            GenesisValidator(
                validator_id="validator-1",
                public_key=PUBLIC_KEY,
            ),
        ),
        authority_config={"mode": "test"},
        economic_state=economic_state,
    )


def _empty_finalized_block(genesis):
    return MainnetBlockBuilder().build(
        chain_id=CHAIN_ID,
        height=0,
        previous_block_hash="",
        timestamp="2026-08-30T00:01:00Z",
        transactions=(),
        resulting_state_root=genesis.state_root,
        economic_state_root=genesis.economic_state
        and economic_state_root(genesis.economic_state),
        proposer_id="validator-1",
    )


def test_append_rejects_tampered_economic_state_root(tmp_path: Path):
    genesis = _genesis()
    store = MainnetChainStore(tmp_path)
    store.initialize_genesis(genesis)

    valid = _empty_finalized_block(genesis)

    tampered = type(valid)(
        chain_id=valid.chain_id,
        height=valid.height,
        previous_block_hash=valid.previous_block_hash,
        timestamp=valid.timestamp,
        transactions=valid.transactions,
        transaction_root=valid.transaction_root,
        resulting_state_root=valid.resulting_state_root,
        economic_state_root="f" * 64,
        proposer_id=valid.proposer_id,
        consensus_evidence={"finalized": True},
    )

    with pytest.raises(ChainStoreError, match="economic state root mismatch"):
        store.append_finalized_block(
            tampered,
            expected_state=genesis.initial_state,
        )


def test_verify_chain_rejects_persisted_economic_root_tampering(tmp_path: Path):
    genesis = _genesis()
    store = MainnetChainStore(tmp_path)
    store.initialize_genesis(genesis)

    valid = _empty_finalized_block(genesis)

    finalized = type(valid)(
        chain_id=valid.chain_id,
        height=valid.height,
        previous_block_hash=valid.previous_block_hash,
        timestamp=valid.timestamp,
        transactions=valid.transactions,
        transaction_root=valid.transaction_root,
        resulting_state_root=valid.resulting_state_root,
        economic_state_root=valid.economic_state_root,
        proposer_id=valid.proposer_id,
        consensus_evidence={"finalized": True},
    )

    store.append_finalized_block(
        finalized,
        expected_state=genesis.initial_state,
    )

    block_path = next((tmp_path / "blocks").glob("00000000000000000000-*.json"))

    data = store._read_json(block_path)
    data["economic_state_root"] = "f" * 64
    store._atomic_write_json(block_path, data)

    with pytest.raises(ChainStoreError):
        store.verify_chain()


def test_append_finalized_blocks_preserves_cumulative_whz_lock(tmp_path: Path):
    from dataclasses import replace

    from apps.whalezchain_orchestrator.mainnet.authentication import (
        AUTHORIZATION_SCHEME,
        generate_keypair,
        sign_transaction,
    )
    from apps.whalezchain_orchestrator.mainnet.transaction import MainnetTransaction
    from apps.whalezchain_orchestrator.services.mainnet_candidate_service import (
        MainnetCandidateService,
    )

    private_key, public_key = generate_keypair()
    public_key_hex = public_key.public_bytes_raw().hex()

    sender = (
        "whalezchain://account/"
        + __import__("hashlib").sha256(
            public_key.public_bytes_raw()
        ).hexdigest()
    )

    economic_state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000.00000000",
    )
    economic_state["accounts"][sender] = {
        "level": "L0",
        "trading_capital": "900.00000000",
        "whz_bond": "100.00000000",
        "whz_bond_locked": "0.00000000",
    }

    initial_state = {
        sender: {
            "WHZ": "0.00000000",
            "PTN": "10.00000000",
            "PRN": "0.00000000",
        }
    }

    genesis = build_genesis(
        genesis_timestamp="2026-09-20T05:59:00Z",
        initial_state=initial_state,
        validators=(
            GenesisValidator(
                validator_id="validator-1",
                public_key=PUBLIC_KEY,
            ),
        ),
        authority_config={"mode": "test"},
        economic_state=economic_state,
    )

    def signed_transfer(
        tx_id: str,
        nonce: int,
        required_whz: str,
    ):
        tx = MainnetTransaction(
            chain_id=CHAIN_ID,
            tx_id=tx_id,
            sender=sender,
            recipient=f"whalezchain://account/{tx_id}",
            asset_symbol="PTN",
            amount="1.00000000",
            nonce=nonce,
            transaction_type="transfer",
            authorization={
                "scheme": AUTHORIZATION_SCHEME,
                "public_key": public_key_hex,
                "signature": "",
            },
            ordering_key=f"{nonce + 1:020d}",
            settlement_required_whz=required_whz,
        )

        return replace(
            tx,
            authorization=sign_transaction(tx, private_key),
        )

    service = MainnetCandidateService()

    tx1 = signed_transfer(
        "tx-economic-continuity-001",
        0,
        "25.00000000",
    )

    candidate1 = service.execute_transfer_candidate(
        transaction=tx1,
        initial_state=initial_state,
        economic_state=genesis.economic_state,
        height=0,
        previous_block_hash="",
        timestamp="2026-09-20T06:00:00+00:00",
    )

    assert (
        candidate1["economic_state"]["accounts"][sender]["whz_bond_locked"]
        == "25.00000000"
    )

    finalized1 = replace(
        candidate1["block"],
        consensus_evidence={
            "status": "finalized",
            "finalized": True,
        },
    )

    store = MainnetChainStore(tmp_path)
    store.initialize_genesis(genesis)

    store.append_finalized_block(
        finalized1,
        expected_state=initial_state,
    )

    tx2 = signed_transfer(
        "tx-economic-continuity-002",
        1,
        "10.00000000",
    )

    candidate2 = service.execute_transfer_candidate(
        transaction=tx2,
        initial_state=candidate1["transition"]["state"],
        economic_state=candidate1["economic_state"],
        height=1,
        previous_block_hash=finalized1.block_hash,
        timestamp="2026-09-20T06:01:00+00:00",
        known_tx_hashes=(tx1.tx_hash,),
    )

    assert (
        candidate2["economic_state"]["accounts"][sender]["whz_bond_locked"]
        == "35.00000000"
    )

    finalized2 = replace(
        candidate2["block"],
        consensus_evidence={
            "status": "finalized",
            "finalized": True,
        },
    )

    store.append_finalized_block(
        finalized2,
        expected_state=candidate1["transition"]["state"],
    )

    verification = store.verify_chain()
    assert verification["verified"] is True
    assert verification["height"] == 1
    assert verification["blocks_checked"] == 2
