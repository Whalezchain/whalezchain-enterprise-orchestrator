from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .transaction import canonical_json, sha256_hex
from .transaction import MainnetTransaction


def merkle_root(hashes: Iterable[str]) -> str:
    items = list(hashes)

    if not items:
        return sha256_hex({"empty": True})

    while len(items) > 1:
        if len(items) % 2:
            items.append(items[-1])

        items = [
            sha256_hex({
                "left": items[i],
                "right": items[i + 1],
            })
            for i in range(0, len(items), 2)
        ]

    return items[0]


@dataclass(frozen=True)
class MainnetBlock:
    chain_id: str
    height: int
    previous_block_hash: str
    timestamp: str
    transactions: tuple[MainnetTransaction, ...]
    transaction_root: str
    resulting_state_root: str
    economic_state_root: str
    proposer_id: str
    consensus_evidence: dict[str, Any]

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "height": self.height,
            "previous_block_hash": self.previous_block_hash,
            "timestamp": self.timestamp,
            "transactions": [
                tx.unsigned_dict()
                for tx in self.transactions
            ],
            "transaction_root": self.transaction_root,
            "resulting_state_root": self.resulting_state_root,
            "economic_state_root": self.economic_state_root,
            "proposer_id": self.proposer_id,
            "consensus_evidence": self.consensus_evidence,
        }

    @property
    def block_hash(self) -> str:
        return sha256_hex(self.unsigned_dict())

    def canonical_bytes(self) -> bytes:
        return canonical_json(self.unsigned_dict())
