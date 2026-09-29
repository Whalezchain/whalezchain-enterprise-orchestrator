from __future__ import annotations

import hashlib
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


AUTHORIZATION_SCHEME = "ed25519-v1"
ACCOUNT_PREFIX = "whalezchain://account/"


class TransactionAuthenticationError(ValueError):
    """Raised when transaction authentication is invalid."""


def canonical_signing_payload(tx: Any) -> bytes:
    """
    Return the canonical transaction payload that is signed.

    The signature itself is deliberately excluded so authentication
    cannot create a circular dependency.
    """
    return tx.canonical_signing_bytes()


def derive_account_id(public_key: bytes) -> str:
    """
    Derive the canonical WhalezChain v1 account identifier.

    account_id =
        whalezchain://account/<sha256(raw_ed25519_public_key)>
    """
    if not isinstance(public_key, bytes):
        raise TransactionAuthenticationError(
            "public key must be raw bytes"
        )

    if len(public_key) != 32:
        raise TransactionAuthenticationError(
            "Ed25519 public key must be 32 bytes"
        )

    digest = hashlib.sha256(public_key).hexdigest()
    return f"{ACCOUNT_PREFIX}{digest}"


def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    return (
        private_key := Ed25519PrivateKey.generate(),
        private_key.public_key(),
    )


def sign_transaction(
    tx: Any,
    private_key: Ed25519PrivateKey,
) -> dict[str, str]:
    public_key = private_key.public_key().public_bytes_raw()
    signature = private_key.sign(
        canonical_signing_payload(tx)
    )

    return {
        "scheme": AUTHORIZATION_SCHEME,
        "public_key": public_key.hex(),
        "signature": signature.hex(),
    }


def verify_transaction_signature(tx: Any) -> None:
    authorization = tx.authorization

    if not isinstance(authorization, dict):
        raise TransactionAuthenticationError(
            "transaction authorization must be an object"
        )

    if authorization.get("scheme") != AUTHORIZATION_SCHEME:
        raise TransactionAuthenticationError(
            "unsupported transaction authorization scheme"
        )

    public_key_hex = authorization.get("public_key")
    signature_hex = authorization.get("signature")

    if not isinstance(public_key_hex, str):
        raise TransactionAuthenticationError(
            "missing public key"
        )

    if not isinstance(signature_hex, str):
        raise TransactionAuthenticationError(
            "missing transaction signature"
        )

    try:
        public_key = bytes.fromhex(public_key_hex)
        signature = bytes.fromhex(signature_hex)
    except ValueError as exc:
        raise TransactionAuthenticationError(
            "public key and signature must be hexadecimal"
        ) from exc

    if len(public_key) != 32:
        raise TransactionAuthenticationError(
            "Ed25519 public key must be 32 bytes"
        )

    if len(signature) != 64:
        raise TransactionAuthenticationError(
            "Ed25519 signature must be 64 bytes"
        )

    expected_sender = derive_account_id(public_key)

    if tx.sender != expected_sender:
        raise TransactionAuthenticationError(
            "transaction sender does not match signing identity"
        )

    try:
        Ed25519PublicKey.from_public_bytes(
            public_key
        ).verify(
            signature,
            canonical_signing_payload(tx),
        )
    except InvalidSignature as exc:
        raise TransactionAuthenticationError(
            "invalid transaction signature"
        ) from exc
