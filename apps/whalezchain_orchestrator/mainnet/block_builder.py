from __future__ import annotations

from typing import Iterable

from .block import MainnetBlock, merkle_root
from .transaction import MainnetTransaction


class BlockConstructionError(ValueError):
    pass


class MainnetBlockBuilder:

    def build(
        self,
        *,
        chain_id: str,
        height: int,
        previous_block_hash: str,
        timestamp: str,
        transactions: Iterable[MainnetTransaction],
        resulting_state_root: str,
        proposer_id: str,
    ) -> MainnetBlock:

        if not chain_id:
            raise BlockConstructionError(
                "missing chain id"
            )

        if height < 0:
            raise BlockConstructionError(
                "block height must be non-negative"
            )

        if height > 0 and not previous_block_hash:
            raise BlockConstructionError(
                "missing previous block hash"
            )

        if not timestamp:
            raise BlockConstructionError(
                "missing block timestamp"
            )

        if not resulting_state_root:
            raise BlockConstructionError(
                "missing resulting state root"
            )

        if not proposer_id:
            raise BlockConstructionError(
                "missing proposer identity"
            )

        txs = tuple(transactions)

        for tx in txs:
            if tx.chain_id != chain_id:
                raise BlockConstructionError(
                    "transaction chain id mismatch"
                )

        tx_hashes = [
            tx.tx_hash
            for tx in txs
        ]

        transaction_root = merkle_root(tx_hashes)

        return MainnetBlock(
            chain_id=chain_id,
            height=height,
            previous_block_hash=previous_block_hash,
            timestamp=timestamp,
            transactions=txs,
            transaction_root=transaction_root,
            resulting_state_root=resulting_state_root,
            proposer_id=proposer_id,
            consensus_evidence={
                "status": "pending",
                "finalized": False,
            },
        )
