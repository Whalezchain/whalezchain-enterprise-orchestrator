from whalezchain_orchestrator.mainnet import (
    MainnetBlockBuilder,
    MainnetTransaction,
    BlockConstructionError,
)


CHAIN_ID = "whalezchain-mainnet-v1"


def make_tx(tx_id: str, ordering_key: str):
    return MainnetTransaction(
        chain_id=CHAIN_ID,
        tx_id=tx_id,
        sender=f"whalezchain://account/{tx_id}",
        recipient="whalezchain://account/receiver",
        asset_symbol="WHZ",
        amount="1.00000000",
        nonce=0,
        transaction_type="transfer",
        authorization={
            "scheme": "placeholder-test-auth",
            "proof": tx_id,
        },
        ordering_key=ordering_key,
    )


def make_block(txs):
    return MainnetBlockBuilder().build(
        chain_id=CHAIN_ID,
        height=1,
        previous_block_hash="0" * 64,
        timestamp="2026-08-30T00:00:00Z",
        transactions=txs,
        resulting_state_root="1" * 64,
        proposer_id="whalezchain://validator/test-validator",
    )


def test_transaction_root_is_deterministic():
    txs = (
        make_tx("tx-001", "00000000000000000001"),
        make_tx("tx-002", "00000000000000000002"),
    )

    a = make_block(txs)
    b = make_block(txs)

    assert a.transaction_root == b.transaction_root


def test_block_hash_is_deterministic():
    txs = (
        make_tx("tx-001", "00000000000000000001"),
        make_tx("tx-002", "00000000000000000002"),
    )

    a = make_block(txs)
    b = make_block(txs)

    assert a.block_hash == b.block_hash
    assert len(a.block_hash) == 64


def test_transaction_order_changes_block_commitment():
    tx1 = make_tx("tx-001", "00000000000000000001")
    tx2 = make_tx("tx-002", "00000000000000000002")

    ordered = make_block((tx1, tx2))
    reversed_block = make_block((tx2, tx1))

    assert ordered.transaction_root != reversed_block.transaction_root
    assert ordered.block_hash != reversed_block.block_hash


def test_wrong_transaction_chain_is_rejected():
    foreign = MainnetTransaction(
        chain_id="foreign-chain",
        tx_id="tx-foreign",
        sender="whalezchain://account/alice",
        recipient="whalezchain://account/bob",
        asset_symbol="WHZ",
        amount="1.00000000",
        nonce=0,
        transaction_type="transfer",
        authorization={
            "scheme": "placeholder-test-auth",
            "proof": "test",
        },
        ordering_key="00000000000000000001",
    )

    try:
        make_block((foreign,))
    except BlockConstructionError as exc:
        assert str(exc) == "transaction chain id mismatch"
    else:
        raise AssertionError(
            "foreign-chain transaction was accepted"
        )


def test_missing_previous_hash_rejected_for_non_genesis_block():
    try:
        MainnetBlockBuilder().build(
            chain_id=CHAIN_ID,
            height=1,
            previous_block_hash="",
            timestamp="2026-08-30T00:00:00Z",
            transactions=(),
            resulting_state_root="1" * 64,
            proposer_id="validator-1",
        )
    except BlockConstructionError as exc:
        assert str(exc) == "missing previous block hash"
    else:
        raise AssertionError(
            "missing previous block hash was accepted"
        )


def test_genesis_height_can_have_empty_previous_hash():
    block = MainnetBlockBuilder().build(
        chain_id=CHAIN_ID,
        height=0,
        previous_block_hash="",
        timestamp="2026-08-30T00:00:00Z",
        transactions=(),
        resulting_state_root="1" * 64,
        proposer_id="validator-1",
    )

    assert block.height == 0
    assert block.previous_block_hash == ""
    assert len(block.block_hash) == 64


def test_block_hash_excludes_self_hash():
    block = make_block((
        make_tx("tx-001", "00000000000000000001"),
    ))

    assert "block_hash" not in block.unsigned_dict()
    assert block.block_hash == block.block_hash


def test_missing_proposer_is_rejected():
    try:
        MainnetBlockBuilder().build(
            chain_id=CHAIN_ID,
            height=0,
            previous_block_hash="",
            timestamp="2026-08-30T00:00:00Z",
            transactions=(),
            resulting_state_root="1" * 64,
            proposer_id="",
        )
    except BlockConstructionError as exc:
        assert str(exc) == "missing proposer identity"
    else:
        raise AssertionError(
            "missing proposer identity was accepted"
        )
