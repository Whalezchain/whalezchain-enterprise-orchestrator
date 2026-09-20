from decimal import Decimal

import pytest

from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    account,
    label_for_account,
    signed_mainnet_transaction,
)

from whalezchain_orchestrator.mainnet import (
    MainnetStateTransition,
    MainnetTransaction,
    StateTransitionError,
    state_root,
)


CHAIN_ID = "whalezchain-mainnet-v1"
ALICE = account("alice")
BOB = account("bob")
CAROL = account("carol")


def make_tx(
    tx_id: str,
    sender: str,
    recipient: str,
    amount: str,
    nonce: int = 0,
    ordering_key: str = "00000000000000000001",
    asset_symbol: str = "WHZ",
):
    return signed_mainnet_transaction(
        tx_id=tx_id,
        sender_label=label_for_account(sender),
        recipient_label=label_for_account(recipient),
        asset_symbol=asset_symbol,
        amount=amount,
        nonce=nonce,
        ordering_key=ordering_key,
    )


def initial_state():
    return {
        ALICE: {
            "WHZ": "100.00000000",
            "PTN": "0.00000000",
            "PRN": "0.00000000",
        },
        BOB: {
            "WHZ": "0.00000000",
            "PTN": "0.00000000",
            "PRN": "0.00000000",
        },
    }


def test_single_transfer_changes_balances():
    tx = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "25.00000000",
    )

    result = MainnetStateTransition().apply(
        initial_state(),
        [tx],
        chain_id=CHAIN_ID,
    )

    assert (
        result["state"]
        [ALICE]
        ["WHZ"]
        == "75.00000000"
    )

    assert (
        result["state"]
        [BOB]
        ["WHZ"]
        == "25.00000000"
    )


def test_state_root_is_deterministic():
    tx = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "25.00000000",
    )

    a = MainnetStateTransition().apply(
        initial_state(),
        [tx],
        chain_id=CHAIN_ID,
    )

    b = MainnetStateTransition().apply(
        initial_state(),
        [tx],
        chain_id=CHAIN_ID,
    )

    assert a["state_root"] == b["state_root"]


def test_state_root_changes_after_transition():
    before = state_root(initial_state())

    tx = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "25.00000000",
    )

    result = MainnetStateTransition().apply(
        initial_state(),
        [tx],
        chain_id=CHAIN_ID,
    )

    assert result["state_root"] != before


def test_transactions_execute_sequentially():
    tx1 = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "25.00000000",
        ordering_key="00000000000000000001",
    )

    tx2 = make_tx(
        "tx-002",
        BOB,
        CAROL,
        "10.00000000",
        ordering_key="00000000000000000002",
    )

    result = MainnetStateTransition().apply(
        initial_state(),
        [tx1, tx2],
        chain_id=CHAIN_ID,
    )

    assert (
        result["state"]
        [ALICE]
        ["WHZ"]
        == "75.00000000"
    )

    assert (
        result["state"]
        [BOB]
        ["WHZ"]
        == "15.00000000"
    )

    assert (
        result["state"]
        [CAROL]
        ["WHZ"]
        == "10.00000000"
    )


def test_insufficient_balance_rejects_transition():
    tx = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "101.00000000",
    )

    with pytest.raises(
        (ValueError, StateTransitionError),
        match="insufficient sender balance",
    ):
        MainnetStateTransition().apply(
            initial_state(),
            [tx],
            chain_id=CHAIN_ID,
        )


def test_failed_block_does_not_mutate_original_state():
    original = initial_state()

    tx1 = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "50.00000000",
    )

    tx2 = make_tx(
        "tx-002",
        ALICE,
        BOB,
        "100.00000000",
        ordering_key="00000000000000000002",
    )

    before = state_root(original)

    with pytest.raises(
        (ValueError, StateTransitionError),
        match="insufficient sender balance",
    ):
        MainnetStateTransition().apply(
            original,
            [tx1, tx2],
            chain_id=CHAIN_ID,
        )

    assert state_root(original) == before

    assert (
        original
        [ALICE]
        ["WHZ"]
        == "100.00000000"
    )


def test_duplicate_transaction_is_rejected():
    tx = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "10.00000000",
    )

    with pytest.raises(
        StateTransitionError,
        match="duplicate transaction",
    ):
        MainnetStateTransition().apply(
            initial_state(),
            [tx, tx],
            chain_id=CHAIN_ID,
        )


def test_committed_transaction_is_rejected():
    tx = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "10.00000000",
    )

    with pytest.raises(
        ValueError,
        match="already been committed",
    ):
        MainnetStateTransition().apply(
            initial_state(),
            [tx],
            chain_id=CHAIN_ID,
            known_tx_hashes=[tx.tx_hash],
        )


def test_transition_contains_per_transaction_evidence():
    tx = make_tx(
        "tx-001",
        ALICE,
        BOB,
        "10.00000000",
    )

    result = MainnetStateTransition().apply(
        initial_state(),
        [tx],
        chain_id=CHAIN_ID,
    )

    evidence = result["transitions"][0]

    assert evidence["tx_hash"] == tx.tx_hash
    assert evidence["status"] == "APPLIED"
    assert len(evidence["before_state_root"]) == 64
    assert len(evidence["after_state_root"]) == 64
    assert evidence["before_state_root"] != evidence["after_state_root"]


def test_asset_balances_remain_separated():
    tx = make_tx(
        "tx-asset-001",
        ALICE,
        BOB,
        "10.00000000",
        asset_symbol="PTN",
    )

    state = initial_state()
    state[ALICE]["PTN"] = "50.00000000"

    result = MainnetStateTransition().apply(
        state,
        [tx],
        chain_id=CHAIN_ID,
    )

    assert result["state"][ALICE]["PTN"] == "40.00000000"
    assert result["state"][BOB]["PTN"] == "10.00000000"
    assert result["state"][ALICE]["WHZ"] == "100.00000000"


def test_prn_issuance_requires_explicit_policy():
    from whalezchain_orchestrator.mainnet.state_transition import (
        MainnetStateTransition,
        StateTransitionError,
    )
    from whalezchain_orchestrator.tests.mainnet_test_helpers import (
        signed_mainnet_transaction,
    )

    tx = signed_mainnet_transaction(
        tx_id="PRN-ISSUE-001",
        sender_label="alice",
        recipient_label="receiver",
        asset_symbol="PRN",
        amount="2",
        nonce=0,
        transaction_type="mint_prn",
        ordering_key="000001",
    )

    try:
        MainnetStateTransition().apply(
            {
                tx.sender: {"PTN": "0", "PRN": "0", "WHZ": "0"},
                tx.recipient: {"PTN": "0", "PRN": "0", "WHZ": "0"},
            },
            [tx],
            chain_id="whalezchain-mainnet-v1",
        )
    except Exception as exc:
        assert "issuance policy is not configured" in str(exc)
    else:
        raise AssertionError("PRN issuance was accepted without policy")


def test_prn_issuance_credits_recipient_without_debiting_issuer():
    from decimal import Decimal

    from whalezchain_orchestrator.mainnet.issuance_policy import (
        PRNIssuancePolicy,
    )
    from whalezchain_orchestrator.mainnet.state_transition import (
        MainnetStateTransition,
    )
    from whalezchain_orchestrator.tests.mainnet_test_helpers import (
        account,
        signed_mainnet_transaction,
    )

    tx = signed_mainnet_transaction(
        tx_id="PRN-ISSUE-002",
        sender_label="alice",
        recipient_label="receiver",
        asset_symbol="PRN",
        amount="2",
        nonce=0,
        transaction_type="mint_prn",
        ordering_key="000002",
    )

    policy = PRNIssuancePolicy(
        authorized_issuers=frozenset({account("alice")}),
        max_supply=Decimal("10"),
    )

    result = MainnetStateTransition().apply(
        {
            tx.sender: {"PTN": "5", "PRN": "0", "WHZ": "0"},
            tx.recipient: {"PTN": "0", "PRN": "1", "WHZ": "0"},
        },
        [tx],
        chain_id="whalezchain-mainnet-v1",
        issuance_policy=policy,
    )

    state = result["state"]

    assert state[tx.sender]["PTN"] == "5"
    assert state[tx.sender]["PRN"] == "0"
    assert state[tx.recipient]["PRN"] == "3.00000000"
    assert result["transitions"][0]["status"] == "APPLIED"


def test_prn_issuance_rejects_unauthorized_issuer():
    from decimal import Decimal

    from whalezchain_orchestrator.mainnet.issuance_policy import (
        PRNIssuancePolicy,
    )
    from whalezchain_orchestrator.mainnet.state_transition import (
        MainnetStateTransition,
    )
    from whalezchain_orchestrator.tests.mainnet_test_helpers import (
        account,
        signed_mainnet_transaction,
    )

    tx = signed_mainnet_transaction(
        tx_id="PRN-ISSUE-003",
        sender_label="alice",
        recipient_label="receiver",
        asset_symbol="PRN",
        amount="1",
        nonce=0,
        transaction_type="mint_prn",
        ordering_key="000003",
    )

    policy = PRNIssuancePolicy(
        authorized_issuers=frozenset({account("bob")}),
        max_supply=Decimal("10"),
    )

    try:
        MainnetStateTransition().apply(
            {
                tx.sender: {"PTN": "5", "PRN": "0", "WHZ": "0"},
                tx.recipient: {"PTN": "0", "PRN": "0", "WHZ": "0"},
            },
            [tx],
            chain_id="whalezchain-mainnet-v1",
            issuance_policy=policy,
        )
    except Exception as exc:
        assert "issuer is not authorized" in str(exc)
    else:
        raise AssertionError("unauthorized PRN issuance was accepted")


def test_prn_issuance_respects_max_supply():
    from decimal import Decimal

    from whalezchain_orchestrator.mainnet.issuance_policy import (
        PRNIssuancePolicy,
    )
    from whalezchain_orchestrator.mainnet.state_transition import (
        MainnetStateTransition,
    )
    from whalezchain_orchestrator.tests.mainnet_test_helpers import (
        account,
        signed_mainnet_transaction,
    )

    tx = signed_mainnet_transaction(
        tx_id="PRN-ISSUE-004",
        sender_label="alice",
        recipient_label="receiver",
        asset_symbol="PRN",
        amount="2",
        nonce=0,
        transaction_type="mint_prn",
        ordering_key="000004",
    )

    policy = PRNIssuancePolicy(
        authorized_issuers=frozenset({account("alice")}),
        max_supply=Decimal("10"),
    )

    try:
        MainnetStateTransition().apply(
            {
                tx.sender: {"PTN": "0", "PRN": "9", "WHZ": "0"},
                tx.recipient: {"PTN": "0", "PRN": "0", "WHZ": "0"},
            },
            [tx],
            chain_id="whalezchain-mainnet-v1",
            issuance_policy=policy,
        )
    except Exception as exc:
        assert "exceed maximum supply" in str(exc)
    else:
        raise AssertionError("PRN issuance exceeded maximum supply")
