from decimal import Decimal

import pytest

from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    signed_mainnet_transaction,
)

from whalezchain_orchestrator.mainnet import (
    MainnetTransaction,
    MainnetTransactionValidator,
    TransactionValidationError,
)
from whalezchain_orchestrator.mainnet.mempool import (
    MainnetMempool,
    MempoolError,
)


CHAIN_ID = "whalezchain-mainnet-v1"


def make_tx(
    tx_id: str,
    ordering_key: str,
    nonce: int = 0,
):
    return signed_mainnet_transaction(
        tx_id=tx_id,
        sender_label=tx_id,
        recipient_label="receiver",
        asset_symbol="WHZ",
        amount="10.00000000",
        nonce=nonce,
        ordering_key=ordering_key,
    )


def test_mempool_accepts_valid_transaction():
    mempool = MainnetMempool(CHAIN_ID)

    tx = make_tx(
        "tx-a",
        "00000000000000000002",
    )

    tx_hash = mempool.add(
        tx,
        sender_balance=Decimal("20.00000000"),
    )

    assert tx_hash == tx.tx_hash
    assert len(mempool) == 1
    assert mempool.contains(tx_hash)


def test_mempool_orders_by_ordering_key():
    mempool = MainnetMempool(CHAIN_ID)

    tx_b = make_tx(
        "tx-b",
        "00000000000000000002",
    )

    tx_a = make_tx(
        "tx-a",
        "00000000000000000001",
    )

    mempool.add(
        tx_b,
        sender_balance=Decimal("20"),
    )

    mempool.add(
        tx_a,
        sender_balance=Decimal("20"),
    )

    ordered = mempool.ordered()

    assert [tx.tx_id for tx in ordered] == [
        "tx-a",
        "tx-b",
    ]


def test_ordering_is_deterministic_for_equal_keys():
    mempool = MainnetMempool(CHAIN_ID)

    tx_a = make_tx(
        "tx-a",
        "00000000000000000001",
    )

    tx_b = make_tx(
        "tx-b",
        "00000000000000000001",
    )

    mempool.add(
        tx_b,
        sender_balance=Decimal("20"),
    )

    mempool.add(
        tx_a,
        sender_balance=Decimal("20"),
    )

    first = mempool.hashes()
    second = mempool.hashes()

    assert first == second


def test_duplicate_transaction_is_rejected():
    mempool = MainnetMempool(CHAIN_ID)

    tx = make_tx(
        "tx-a",
        "00000000000000000001",
    )

    mempool.add(
        tx,
        sender_balance=Decimal("20"),
    )

    with pytest.raises(
        TransactionValidationError,
        match="already been committed",
    ):
        mempool.add(
            tx,
            sender_balance=Decimal("20"),
        )


def test_committed_transactions_can_be_removed():
    mempool = MainnetMempool(CHAIN_ID)

    tx = make_tx(
        "tx-a",
        "00000000000000000001",
    )

    mempool.add(
        tx,
        sender_balance=Decimal("20"),
    )

    mempool.remove_committed(
        [tx.tx_hash]
    )

    assert len(mempool) == 0
    assert not mempool.contains(tx.tx_hash)
