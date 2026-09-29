from __future__ import annotations

import hashlib
from dataclasses import replace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from whalezchain_orchestrator.mainnet import MainnetTransaction
from whalezchain_orchestrator.mainnet.authentication import (
    AUTHORIZATION_SCHEME,
    derive_account_id,
    sign_transaction,
)

CHAIN_ID = "whalezchain-mainnet-v1"


def private_key(label: str) -> Ed25519PrivateKey:
    seed = hashlib.sha256(
        f"whalezchain-test-key:{label}".encode("utf-8")
    ).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def account(label: str) -> str:
    return derive_account_id(
        private_key(label).public_key().public_bytes_raw()
    )


def signed_mainnet_transaction(
    *,
    tx_id: str,
    sender_label: str,
    recipient_label: str,
    asset_symbol: str,
    amount: str,
    nonce: int,
    transaction_type: str = "transfer",
    ordering_key: str,
) -> MainnetTransaction:
    key = private_key(sender_label)
    public_key = key.public_key().public_bytes_raw()

    tx = MainnetTransaction(
        chain_id=CHAIN_ID,
        tx_id=tx_id,
        sender=account(sender_label),
        recipient=account(recipient_label),
        asset_symbol=asset_symbol,
        amount=amount,
        nonce=nonce,
        transaction_type=transaction_type,
        authorization={
            "scheme": AUTHORIZATION_SCHEME,
            "public_key": public_key.hex(),
            "signature": "",
        },
        ordering_key=ordering_key,
    )

    return replace(tx, authorization=sign_transaction(tx, key))


def label_for_account(account_id: str) -> str:
    for label in ("alice", "bob", "carol", "receiver"):
        if account(label) == account_id:
            return label
    raise ValueError(f"unknown test account: {account_id}")
