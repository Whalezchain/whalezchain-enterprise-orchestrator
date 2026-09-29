from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


@dataclass(frozen=True)
class MainnetTransaction:
    chain_id: str
    tx_id: str
    sender: str
    recipient: str
    asset_symbol: str
    amount: str
    nonce: int
    transaction_type: str
    authorization: dict[str, Any]
    ordering_key: str
    settlement_required_whz: str | None = None

    def signing_authorization(self) -> dict[str, Any]:
        """
        Return only the authorization fields covered by the signature.

        The signature itself is deliberately excluded to prevent
        circular signing.
        """
        if not isinstance(self.authorization, dict):
            raise ValueError("transaction authorization must be an object")

        return {
            "scheme": self.authorization.get("scheme"),
            "public_key": self.authorization.get("public_key"),
        }

    def canonical_signing_dict(self) -> dict[str, Any]:
        """
        Canonical transaction representation covered by the signature.
        """
        return {
            "chain_id": self.chain_id,
            "tx_id": self.tx_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "asset_symbol": self.asset_symbol,
            "amount": self.amount,
            "nonce": self.nonce,
            "transaction_type": self.transaction_type,
            "authorization": self.signing_authorization(),
            "ordering_key": self.ordering_key,
            "settlement_required_whz": self.settlement_required_whz,
        }

    def canonical_signing_bytes(self) -> bytes:
        return canonical_json(self.canonical_signing_dict())

    def signed_dict(self) -> dict[str, Any]:
        """
        Complete canonical transaction representation.

        Unlike the signing payload, this includes the signature and is
        therefore suitable for transaction identity/hash commitment.
        """
        return {
            "chain_id": self.chain_id,
            "tx_id": self.tx_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "asset_symbol": self.asset_symbol,
            "amount": self.amount,
            "nonce": self.nonce,
            "transaction_type": self.transaction_type,
            "authorization": self.authorization,
            "ordering_key": self.ordering_key,
            "settlement_required_whz": self.settlement_required_whz,
        }

    def unsigned_dict(self) -> dict[str, Any]:
        """
        Backward-compatible alias.

        Historically this method included authorization metadata.
        It now returns the canonical signing representation.
        """
        return self.canonical_signing_dict()

    @property
    def tx_hash(self) -> str:
        """
        Hash of the complete signed transaction.
        """
        return sha256_hex(self.signed_dict())
