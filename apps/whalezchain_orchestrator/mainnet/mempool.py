from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .transaction import MainnetTransaction
from .transaction_validator import MainnetTransactionValidator


class MempoolError(ValueError):
    pass


@dataclass
class MainnetMempool:
    chain_id: str
    validator: MainnetTransactionValidator = field(
        default_factory=MainnetTransactionValidator
    )
    _transactions: Dict[str, MainnetTransaction] = field(
        default_factory=dict
    )

    def add(
        self,
        tx: MainnetTransaction,
        *,
        expected_nonce: int | None = None,
        sender_balance=None,
    ) -> str:

        self.validator.validate(
            tx,
            expected_chain_id=self.chain_id,
            known_tx_hashes=self._transactions.keys(),
            expected_nonce=expected_nonce,
            sender_balance=sender_balance,
        )

        tx_hash = tx.tx_hash

        if tx_hash in self._transactions:
            raise MempoolError(
                "transaction already in mempool"
            )

        self._transactions[tx_hash] = tx

        return tx_hash

    def contains(self, tx_hash: str) -> bool:
        return tx_hash in self._transactions

    def get(self, tx_hash: str) -> MainnetTransaction:
        try:
            return self._transactions[tx_hash]
        except KeyError:
            raise MempoolError(
                "transaction not found in mempool"
            )

    def ordered(self) -> List[MainnetTransaction]:
        return sorted(
            self._transactions.values(),
            key=lambda tx: (
                tx.ordering_key,
                tx.tx_hash,
            ),
        )

    def remove(self, tx_hash: str) -> None:
        self._transactions.pop(
            tx_hash,
            None,
        )

    def remove_committed(
        self,
        tx_hashes: List[str],
    ) -> None:
        for tx_hash in tx_hashes:
            self.remove(tx_hash)

    def __len__(self) -> int:
        return len(self._transactions)

    def hashes(self) -> List[str]:
        return [
            tx.tx_hash
            for tx in self.ordered()
        ]
