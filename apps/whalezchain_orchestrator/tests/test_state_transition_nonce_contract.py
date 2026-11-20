"""Safety regression of existing deterministic Chain transfer/nonce code.

Only generic synthetic accounts and test keys; no real wallet, public claims,
ledger persistence, private role metadata or external settlement.
"""
from dataclasses import replace
import pytest
from whalezchain_orchestrator.mainnet.state_transition import MainnetStateTransition
from whalezchain_orchestrator.mainnet.transaction_validator import TransactionValidationError
from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    CHAIN_ID, account, signed_mainnet_transaction,
)


def _tx(tx_id, nonce, amount="1.00000000", recipient="bob"):
    return signed_mainnet_transaction(
        tx_id=tx_id, sender_label="alice", recipient_label=recipient,
        asset_symbol="PTN", amount=amount, nonce=nonce,
        ordering_key=tx_id,
    )


def _funded():
    return {account("alice"): {"PTN": "5.00000000"}}


def test_valid_sequential_nonces_and_balance_conservation():
    result = MainnetStateTransition().apply(
        _funded(), (_tx("tx1", 0), _tx("tx2", 1)),
        chain_id=CHAIN_ID, expected_nonces={},
    )
    assert result["state"][account("alice")]["PTN"] == "3.00000000"
    assert result["state"][account("bob")]["PTN"] == "2.00000000"
    assert result["transaction_count"] == 2


def test_previous_nonce_rejected():
    tx = _tx("replay", 0)
    with pytest.raises(TransactionValidationError, match="nonce"):
        MainnetStateTransition().apply(
            _funded(), (tx,), chain_id=CHAIN_ID,
            expected_nonces={account("alice"): 1},
        )


def test_nonce_gap_rejected_within_ordered_batch():
    with pytest.raises(TransactionValidationError, match="nonce"):
        MainnetStateTransition().apply(
            _funded(), (_tx("one", 0), _tx("gap", 2)),
            chain_id=CHAIN_ID, expected_nonces={},
        )


def test_nonexistent_sender_cannot_spend():
    with pytest.raises(TransactionValidationError, match="insufficient"):
        MainnetStateTransition().apply(
            {}, (_tx("missing-sender", 0),),
            chain_id=CHAIN_ID, expected_nonces={},
        )


def test_self_transfer_does_not_change_balance():
    original = _funded()
    result = MainnetStateTransition().apply(
        original, (_tx("self-transfer", 0, recipient="alice"),),
        chain_id=CHAIN_ID, expected_nonces={},
    )
    assert result["state"][account("alice")]["PTN"] == "5.00000000"
    assert original == _funded()


def test_signature_tampering_is_rejected():
    tx = _tx("signed", 0)
    with pytest.raises(TransactionValidationError, match="authentication"):
        MainnetStateTransition().apply(
            _funded(), (replace(tx, amount="4.00000000"),),
            chain_id=CHAIN_ID, expected_nonces={},
        )
