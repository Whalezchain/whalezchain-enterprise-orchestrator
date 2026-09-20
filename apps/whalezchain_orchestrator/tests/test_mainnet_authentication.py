from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from apps.whalezchain_orchestrator.mainnet.authentication import (
    AUTHORIZATION_SCHEME,
    TransactionAuthenticationError,
    derive_account_id,
    generate_keypair,
    sign_transaction,
    verify_transaction_signature,
)
from apps.whalezchain_orchestrator.mainnet.transaction import MainnetTransaction
from apps.whalezchain_orchestrator.mainnet.transaction_validator import (
    MainnetTransactionValidator,
    TransactionValidationError,
)


CHAIN_ID = "whalezchain-mainnet-v1"
RECIPIENT = "whalezchain://account/recipient"


def make_signed_transaction(
    *,
    private_key=None,
    tx_id: str = "tx-auth-test-001",
    sender: str | None = None,
    recipient: str = RECIPIENT,
    amount: str = "1",
    nonce: int = 0,
    scheme: str = AUTHORIZATION_SCHEME,
):
    if private_key is None:
        private_key, public_key = generate_keypair()
    else:
        public_key = private_key.public_key()

    raw_public_key = public_key.public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )

    derived_sender = derive_account_id(raw_public_key)

    unsigned_tx = MainnetTransaction(
        chain_id=CHAIN_ID,
        tx_id=tx_id,
        sender=sender or derived_sender,
        recipient=recipient,
        asset_symbol="WHZ",
        amount=amount,
        nonce=nonce,
        transaction_type="transfer",
        authorization={
            "scheme": scheme,
            "public_key": raw_public_key.hex(),
        },
        ordering_key=f"{nonce:010d}",
    )

    authorization = sign_transaction(unsigned_tx, private_key)

    signed_tx = MainnetTransaction(
        **{
            **unsigned_tx.__dict__,
            "authorization": authorization,
        }
    )

    return signed_tx, private_key


def validate(tx: MainnetTransaction, **kwargs):
    return MainnetTransactionValidator().validate(
        tx,
        expected_chain_id=CHAIN_ID,
        sender_balance="100",
        **kwargs,
    )


def test_valid_signature_is_accepted():
    tx, _ = make_signed_transaction()

    verify_transaction_signature(tx)
    validate(tx, expected_nonce=0)


def test_amount_tampering_is_rejected():
    tx, _ = make_signed_transaction()

    tampered = MainnetTransaction(
        **{
            **tx.__dict__,
            "amount": "2",
        }
    )

    with pytest.raises(TransactionAuthenticationError):
        verify_transaction_signature(tampered)

    with pytest.raises(TransactionValidationError, match="authentication failed"):
        validate(tampered, expected_nonce=0)


def test_recipient_tampering_is_rejected():
    tx, _ = make_signed_transaction()

    tampered = MainnetTransaction(
        **{
            **tx.__dict__,
            "recipient": "whalezchain://account/attacker",
        }
    )

    with pytest.raises(TransactionAuthenticationError):
        verify_transaction_signature(tampered)


def test_sender_tampering_is_rejected():
    tx, _ = make_signed_transaction()

    tampered = MainnetTransaction(
        **{
            **tx.__dict__,
            "sender": "whalezchain://account/attacker",
        }
    )

    with pytest.raises(TransactionAuthenticationError):
        verify_transaction_signature(tampered)


def test_wrong_public_key_is_rejected():
    tx, _ = make_signed_transaction()
    _, other_public_key = generate_keypair()

    other_public_key = other_public_key.public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )

    tampered_authorization = {
        **tx.authorization,
        "public_key": other_public_key.hex(),
    }

    tampered = MainnetTransaction(
        **{
            **tx.__dict__,
            "authorization": tampered_authorization,
        }
    )

    with pytest.raises(TransactionAuthenticationError):
        verify_transaction_signature(tampered)


def test_wrong_signature_is_rejected():
    tx, _ = make_signed_transaction()

    tampered_authorization = {
        **tx.authorization,
        "signature": "00" * 64,
    }

    tampered = MainnetTransaction(
        **{
            **tx.__dict__,
            "authorization": tampered_authorization,
        }
    )

    with pytest.raises(TransactionAuthenticationError):
        verify_transaction_signature(tampered)


def test_unsupported_authorization_scheme_is_rejected():
    tx, _ = make_signed_transaction()

    tampered_authorization = {
        **tx.authorization,
        "scheme": "unsupported-v99",
    }

    tampered = MainnetTransaction(
        **{
            **tx.__dict__,
            "authorization": tampered_authorization,
        }
    )

    with pytest.raises(TransactionAuthenticationError, match="unsupported"):
        verify_transaction_signature(tampered)


def test_replayed_transaction_hash_is_rejected():
    tx, _ = make_signed_transaction()

    with pytest.raises(TransactionValidationError, match="already been committed"):
        validate(
            tx,
            known_tx_hashes=(tx.tx_hash,),
            expected_nonce=0,
        )


def test_wrong_nonce_is_rejected():
    tx, _ = make_signed_transaction(nonce=0)

    with pytest.raises(TransactionValidationError, match="nonce"):
        validate(tx, expected_nonce=1)


def test_transaction_hash_commits_to_signed_transaction():
    tx, _ = make_signed_transaction()

    changed_signature = {
        **tx.authorization,
        "signature": "11" * 64,
    }

    altered = MainnetTransaction(
        **{
            **tx.__dict__,
            "authorization": changed_signature,
        }
    )

    assert altered.tx_hash != tx.tx_hash


def test_authentication_payload_excludes_signature():
    tx, _ = make_signed_transaction()

    original_payload = tx.canonical_signing_bytes()

    changed_signature = {
        **tx.authorization,
        "signature": "22" * 64,
    }

    altered = MainnetTransaction(
        **{
            **tx.__dict__,
            "authorization": changed_signature,
        }
    )

    assert altered.canonical_signing_bytes() == original_payload
