from decimal import Decimal

import pytest

from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    account,
    signed_mainnet_transaction,
)

from whalezchain_orchestrator.mainnet import (
    MainnetTransaction,
    MainnetTransactionValidator,
    TransactionValidationError,
)


def make_tx(
    nonce=0,
    authorization=None,
):
    if authorization is not None:
        return MainnetTransaction(
            chain_id="whalezchain-mainnet-v1",
            tx_id="tx-0001",
            sender=account("alice"),
            recipient=account("bob"),
            asset_symbol="WHZ",
            amount="10.00000000",
            nonce=nonce,
            transaction_type="transfer",
            authorization=authorization,
            ordering_key="00000000000000000001",
        )

    return signed_mainnet_transaction(
        tx_id="tx-0001",
        sender_label="alice",
        recipient_label="bob",
        asset_symbol="WHZ",
        amount="10.00000000",
        nonce=nonce,
        ordering_key="00000000000000000001",
    )


def test_transaction_hash_is_deterministic():
    assert make_tx().tx_hash == make_tx().tx_hash


def test_validator_accepts_valid_transaction():
    MainnetTransactionValidator().validate(
        make_tx(),
        expected_chain_id="whalezchain-mainnet-v1",
        expected_nonce=0,
        sender_balance=Decimal("20.00000000"),
    )


def test_validator_rejects_replay():
    with pytest.raises(
        TransactionValidationError,
        match="already been committed",
    ):
        MainnetTransactionValidator().validate(
            make_tx(),
            expected_chain_id="whalezchain-mainnet-v1",
            known_tx_hashes=[
                make_tx().tx_hash
            ],
        )


def test_validator_rejects_missing_authorization():
    with pytest.raises(
        TransactionValidationError,
        match="authorization",
    ):
        MainnetTransactionValidator().validate(
            make_tx(authorization={}),
            expected_chain_id="whalezchain-mainnet-v1",
        )


def test_validator_rejects_wrong_nonce():
    with pytest.raises(
        TransactionValidationError,
        match="nonce does not match expected nonce",
    ):
        MainnetTransactionValidator().validate(
            make_tx(nonce=7),
            expected_chain_id="whalezchain-mainnet-v1",
            expected_nonce=0,
        )


def test_validator_rejects_insufficient_balance():
    with pytest.raises(
        TransactionValidationError,
        match="insufficient sender balance",
    ):
        MainnetTransactionValidator().validate(
            make_tx(),
            expected_chain_id="whalezchain-mainnet-v1",
            sender_balance=Decimal("5.00000000"),
        )
