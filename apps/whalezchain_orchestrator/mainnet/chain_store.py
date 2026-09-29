from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .block import MainnetBlock
from .state_transition import MainnetStateTransition, state_root
from .genesis_economic_state import economic_state_root
from .settlement import lock_whz_bond
from .transaction import MainnetTransaction, canonical_json, sha256_hex
from .transaction_validator import MainnetTransactionValidator
from .genesis import MainnetGenesis, verify_genesis


MAINNET_CHAIN_ID = "whalezchain-mainnet-v1"


class ChainStoreError(ValueError):
    pass


class MainnetChainStore:
    """
    Canonical persistent mainnet chain spine.

    Canonical authority:
      genesis + finalized block files

    Derived/index data:
      finalized head + transaction index

    Candidate blocks, mempool entries and unfinalized proposals are
    deliberately outside this store.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        chain_id: str = MAINNET_CHAIN_ID,
    ) -> None:
        self.root = Path(root)
        self.blocks_dir = self.root / "blocks"
        self.meta_dir = self.root / "meta"
        self.genesis_path = self.root / "genesis.json"
        self.head_path = self.meta_dir / "finalized_head.json"
        self.tx_index_path = self.meta_dir / "tx_index.json"
        self.chain_id = chain_id

        self.blocks_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def initialize_genesis(self, genesis: MainnetGenesis) -> None:
        verify_genesis(genesis)

        if genesis.chain_id != self.chain_id:
            raise ChainStoreError("genesis chain id mismatch")

        if self.genesis_path.exists():
            existing = self._read_json(self.genesis_path)
            if existing != genesis.to_dict():
                raise ChainStoreError("canonical genesis already exists and differs")
            return

        self._atomic_write_json(self.genesis_path, genesis.to_dict())

        if not self.head_path.exists():
            self._atomic_write_json(
                self.head_path,
                {
                    "height": -1,
                    "block_hash": "",
                    "state_root": genesis.state_root,
                    "economic_state_root": economic_state_root(genesis.economic_state),
                },
            )

        if not self.tx_index_path.exists():
            self._atomic_write_json(self.tx_index_path, {})

    def load_genesis(self) -> dict[str, Any]:
        if not self.genesis_path.exists():
            raise ChainStoreError("canonical genesis is not initialized")
        return self._read_json(self.genesis_path)

    def finalized_head(self) -> dict[str, Any]:
        if not self.head_path.exists():
            raise ChainStoreError("finalized head is not initialized")
        return self._read_json(self.head_path)

    def committed(self, tx_hash: str) -> bool:
        return tx_hash in self._read_json(self.tx_index_path)

    def append_finalized_block(
        self,
        block: MainnetBlock,
        *,
        expected_state: Mapping[str, Mapping[str, str]],
    ) -> dict[str, Any]:
        genesis = self.load_genesis()
        head = self.finalized_head()
        tx_index = self._read_json(self.tx_index_path)

        if block.chain_id != self.chain_id:
            raise ChainStoreError("block chain id mismatch")

        expected_height = int(head["height"]) + 1
        if block.height != expected_height:
            raise ChainStoreError("block height does not extend finalized head")

        if block.previous_block_hash != head["block_hash"]:
            raise ChainStoreError("previous block hash does not match finalized head")

        txs = tuple(block.transactions)
        validator = MainnetTransactionValidator()

        seen: set[str] = set()
        for tx in txs:
            if tx.chain_id != self.chain_id:
                raise ChainStoreError("transaction chain id mismatch")

            if tx.tx_hash in seen:
                raise ChainStoreError("duplicate transaction inside block")

            if tx.tx_hash in tx_index:
                raise ChainStoreError("transaction replay detected")

            validator.validate(
                tx,
                expected_chain_id=self.chain_id,
                known_tx_hashes=tx_index.keys(),
            )
            seen.add(tx.tx_hash)

        expected_economic_state = self._replay_economic_state()

        expected_economic_state = self._economic_state_after_transactions(
            expected_economic_state,
            txs,
        )

        expected_economic_root = economic_state_root(expected_economic_state)

        if block.economic_state_root != expected_economic_root:
            raise ChainStoreError("block economic state root mismatch")

        transition = MainnetStateTransition().apply(
            dict(expected_state),
            list(txs),
            chain_id=self.chain_id,
            known_tx_hashes=tuple(tx_index.keys()),
        )

        if transition["state_root"] != block.resulting_state_root:
            raise ChainStoreError("block resulting state root mismatch")

        tx_root = self._transaction_root(txs)
        if tx_root != block.transaction_root:
            raise ChainStoreError("block transaction root mismatch")

        expected_block_hash = sha256_hex(block.unsigned_dict())
        if expected_block_hash != block.block_hash:
            raise ChainStoreError("block hash mismatch")

        finalized_evidence = dict(block.consensus_evidence or {})
        if finalized_evidence.get("finalized") is not True:
            raise ChainStoreError("block lacks finalization evidence")

        block_data = block.unsigned_dict()
        block_data["transactions"] = [
            tx.signed_dict() for tx in block.transactions
        ]
        block_data["block_hash"] = block.block_hash

        block_path = self.blocks_dir / f"{block.height:020d}-{block.block_hash}.json"
        if block_path.exists():
            raise ChainStoreError("canonical block already exists")

        new_index = dict(tx_index)
        for tx in txs:
            new_index[tx.tx_hash] = {
                "height": block.height,
                "block_hash": block.block_hash,
            }

        new_head = {
            "height": block.height,
            "block_hash": block.block_hash,
            "state_root": block.resulting_state_root,
            "economic_state_root": block.economic_state_root,
        }

        # Files are written atomically. Head/index are only advanced after
        # the canonical block itself exists.
        self._atomic_write_json(block_path, block_data)
        self._atomic_write_json(self.tx_index_path, new_index)
        self._atomic_write_json(self.head_path, new_head)

        return new_head

    def replay_state(self) -> dict[str, dict[str, str]]:
        genesis = self.load_genesis()
        state = {
            account: dict(balances)
            for account, balances in genesis["initial_state"].items()
        }
        economic_state = {
            **genesis["economic_state"],
            "accounts": {
                account_id: dict(account)
                for account_id, account in genesis["economic_state"]["accounts"].items()
            },
        }

        head = self.finalized_head()
        height = int(head["height"])
        known_tx_hashes: set[str] = set()

        for block_height in range(0, height + 1):
            block = self._load_block(block_height)
            txs = tuple(
                self._transaction_from_dict(item)
                for item in block["transactions"]
            )

            transition = MainnetStateTransition().apply(
                state,
                list(txs),
                chain_id=self.chain_id,
                known_tx_hashes=tuple(known_tx_hashes),
            )
            state = transition["state"]

            economic_state = self._economic_state_after_transactions(
                economic_state,
                txs,
            )

            expected_economic_root = economic_state_root(economic_state)
            if block["economic_state_root"] != expected_economic_root:
                raise ChainStoreError(
                    f"economic state root mismatch at height {block_height}"
                )

            known_tx_hashes.update(tx.tx_hash for tx in txs)

            if transition["state_root"] != block["resulting_state_root"]:
                raise ChainStoreError(
                    f"state replay mismatch at height {block_height}"
                )

        if state_root(state) != head["state_root"]:
            raise ChainStoreError("finalized head state root mismatch")

        if economic_state_root(economic_state) != head["economic_state_root"]:
            raise ChainStoreError("finalized head economic state root mismatch")

        return state

    def reconcile(self) -> dict[str, Any]:
        """Validate canonical blocks and rebuild derived metadata.

        Block files are canonical. finalized_head.json and tx_index.json
        are derived metadata and may be recreated after an interrupted write.
        """
        genesis = self.load_genesis()

        head = self.finalized_head()

        state = {
            account: dict(balances)
            for account, balances in genesis["initial_state"].items()
        }
        economic_state = {
            **genesis["economic_state"],
            "accounts": {
                account_id: dict(account)
                for account_id, account in genesis["economic_state"]["accounts"].items()
            },
        }

        tx_index: dict[str, dict[str, Any]] = {}
        known_tx_hashes: set[str] = set()
        previous_hash = ""
        height = 0

        while True:
            matches = sorted(self.blocks_dir.glob(f"{height:020d}-*.json"))
            if not matches:
                break
            if len(matches) != 1:
                raise ChainStoreError(
                    f"expected exactly one canonical block at height {height}"
                )

            block = self._read_json(matches[0])

            if block["chain_id"] != self.chain_id:
                raise ChainStoreError(f"block chain id mismatch at height {height}")
            if int(block["height"]) != height:
                raise ChainStoreError(f"block height mismatch at height {height}")
            if block["previous_block_hash"] != previous_hash:
                raise ChainStoreError(
                    f"previous hash mismatch at height {height}"
                )

            txs = tuple(
                self._transaction_from_dict(item)
                for item in block["transactions"]
            )

            if self._transaction_root(txs) != block["transaction_root"]:
                raise ChainStoreError(
                    f"transaction root mismatch at height {height}"
                )

            for tx in txs:
                if tx.tx_hash in known_tx_hashes:
                    raise ChainStoreError(
                        f"duplicate transaction at height {height}: {tx.tx_hash}"
                    )

            transition = MainnetStateTransition().apply(
                state,
                list(txs),
                chain_id=self.chain_id,
                known_tx_hashes=tuple(known_tx_hashes),
            )
            state = transition["state"]

            economic_state = self._economic_state_after_transactions(
                economic_state,
                txs,
            )

            expected_economic_root = economic_state_root(economic_state)

            if transition["state_root"] != block["resulting_state_root"]:
                raise ChainStoreError(
                    f"state replay mismatch at height {height}"
                )

            if block.get("economic_state_root") != expected_economic_root:
                raise ChainStoreError(
                    f"economic state root mismatch at height {height}"
                )

            unsigned_block = {
                "chain_id": block["chain_id"],
                "height": block["height"],
                "previous_block_hash": block["previous_block_hash"],
                "timestamp": block["timestamp"],
                "transactions": [tx.unsigned_dict() for tx in txs],
                "transaction_root": block["transaction_root"],
                "resulting_state_root": block["resulting_state_root"],
                "economic_state_root": block["economic_state_root"],
                "proposer_id": block["proposer_id"],
                "consensus_evidence": block["consensus_evidence"],
            }

            if sha256_hex(unsigned_block) != block["block_hash"]:
                raise ChainStoreError(
                    f"block hash mismatch at height {height}"
                )

            if dict(block["consensus_evidence"] or {}).get("finalized") is not True:
                raise ChainStoreError(
                    f"block lacks finalization evidence at height {height}"
                )

            for tx in txs:
                tx_index[tx.tx_hash] = {
                    "height": height,
                    "block_hash": block["block_hash"],
                }
                known_tx_hashes.add(tx.tx_hash)

            previous_hash = block["block_hash"]
            height += 1

        final_height = height - 1
        final_state_root = state_root(state)

        new_head = {
            "height": final_height,
            "block_hash": previous_hash,
            "state_root": final_state_root,
            "economic_state_root": economic_state_root(economic_state),
        }

        self._atomic_write_json(self.tx_index_path, tx_index)
        self._atomic_write_json(self.head_path, new_head)

        return {
            "reconciled": True,
            "height": final_height,
            "block_hash": previous_hash,
            "state_root": final_state_root,
            "transactions_indexed": len(tx_index),
        }

    def verify_chain(self) -> dict[str, Any]:
        self.replay_state()

        head = self.finalized_head()
        checked = 0

        previous_hash = ""
        for height in range(0, int(head["height"]) + 1):
            block = self._load_block(height)

            if block["previous_block_hash"] != previous_hash:
                raise ChainStoreError(
                    f"previous hash mismatch at height {height}"
                )

            txs = tuple(
                self._transaction_from_dict(item)
                for item in block["transactions"]
            )

            unsigned_block = {
                "chain_id": block["chain_id"],
                "height": block["height"],
                "previous_block_hash": block["previous_block_hash"],
                "timestamp": block["timestamp"],
                "transactions": [
                    tx.unsigned_dict() for tx in txs
                ],
                "transaction_root": block["transaction_root"],
                "resulting_state_root": block["resulting_state_root"],
                "economic_state_root": block["economic_state_root"],
                "proposer_id": block["proposer_id"],
                "consensus_evidence": block["consensus_evidence"],
            }

            if sha256_hex(unsigned_block) != block["block_hash"]:
                raise ChainStoreError(
                    f"block hash mismatch at height {height}"
                )

            previous_hash = block["block_hash"]
            checked += 1

        if previous_hash != head["block_hash"]:
            raise ChainStoreError("finalized head hash mismatch")

        return {
            "verified": True,
            "height": int(head["height"]),
            "block_hash": head["block_hash"],
            "state_root": head["state_root"],
            "blocks_checked": checked,
        }

    def _load_block(self, height: int) -> dict[str, Any]:
        matches = sorted(self.blocks_dir.glob(f"{height:020d}-*.json"))
        if len(matches) != 1:
            raise ChainStoreError(
                f"expected exactly one canonical block at height {height}"
            )
        return self._read_json(matches[0])

    def _replay_economic_state(self) -> dict[str, Any]:
        """Reconstruct the canonical economic state through the finalized chain."""

        genesis = self.load_genesis()

        economic_state = {
            **genesis["economic_state"],
            "accounts": {
                account_id: dict(account)
                for account_id, account in genesis["economic_state"]["accounts"].items()
            },
        }

        head = self.finalized_head()
        height = int(head["height"])

        for block_height in range(0, height + 1):
            block = self._load_block(block_height)
            txs = tuple(
                self._transaction_from_dict(item)
                for item in block["transactions"]
            )

            economic_state = self._economic_state_after_transactions(
                economic_state,
                txs,
            )

            expected_root = economic_state_root(economic_state)
            if block["economic_state_root"] != expected_root:
                raise ChainStoreError(
                    f"economic state root mismatch at height {block_height}"
                )

        return economic_state

    @staticmethod
    def _economic_state_after_transactions(
        economic_state: Mapping[str, Any],
        transactions: tuple[MainnetTransaction, ...],
    ) -> dict[str, Any]:
        state = {
            **economic_state,
            "accounts": {
                account_id: dict(account)
                for account_id, account in economic_state["accounts"].items()
            },
        }

        for tx in transactions:
            required = tx.settlement_required_whz
            if required is None:
                continue

            result = lock_whz_bond(
                state,
                account_id=tx.sender,
                required_whz=required,
            )
            state = result["state"]

        return state

    @staticmethod
    def _transaction_root(
        transactions: tuple[MainnetTransaction, ...],
    ) -> str:
        hashes = [tx.tx_hash for tx in transactions]

        if not hashes:
            return sha256_hex({"empty": True})

        while len(hashes) > 1:
            next_level = []
            for index in range(0, len(hashes), 2):
                left = hashes[index]
                right = hashes[index + 1] if index + 1 < len(hashes) else left
                next_level.append(sha256_hex({"left": left, "right": right}))
            hashes = next_level

        return hashes[0]

    @staticmethod
    def _transaction_from_dict(data: Mapping[str, Any]) -> MainnetTransaction:
        return MainnetTransaction(
            chain_id=data["chain_id"],
            tx_id=data["tx_id"],
            sender=data["sender"],
            recipient=data["recipient"],
            asset_symbol=data["asset_symbol"],
            amount=data["amount"],
            nonce=data["nonce"],
            transaction_type=data["transaction_type"],
            authorization=data["authorization"],
            ordering_key=data["ordering_key"],
            settlement_required_whz=data.get("settlement_required_whz"),
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _atomic_write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")

        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(
                value,
                handle,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
