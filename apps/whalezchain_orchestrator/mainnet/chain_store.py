from __future__ import annotations

import json
import os
import re
import tempfile
import fcntl
from functools import wraps
from pathlib import Path
from typing import Any, Mapping

from .block import MainnetBlock
from .state_transition import MainnetStateTransition, state_root
from .genesis_economic_state import economic_state_root
from .settlement import lock_whz_bond, release_whz_bond, slash_whz_bond
from .transaction import MainnetTransaction, canonical_json, sha256_hex
from .issuance_policy import policy_from_authority_config
from .genesis import MainnetGenesis, GenesisValidator, verify_genesis


MAINNET_CHAIN_ID = "whalezchain-mainnet-v1"


class ChainStoreError(ValueError):
    pass


def _serialized_write(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        # Independent descriptors make this an inter-process AND thread lock.
        with (self.root / ".write.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                return method(self, *args, **kwargs)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return locked


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

    @_serialized_write
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
        data = self._read_json(self.genesis_path)
        genesis = MainnetGenesis(
            chain_id=data["chain_id"], network_class=data["network_class"],
            genesis_timestamp=data["genesis_timestamp"],
            asset_registry=data["asset_registry"], initial_state=data["initial_state"],
            economic_state=data["economic_state"], authority_config=data["authority_config"],
            validator_config=tuple(GenesisValidator(v["validator_id"], v["public_key"])
                                   for v in data["validator_config"]),
            state_root=data["state_root"], genesis_hash=data["genesis_hash"],
        )
        verify_genesis(genesis)
        if genesis.chain_id != self.chain_id or genesis.to_dict() != data:
            raise ChainStoreError("canonical genesis identity or encoding mismatch")
        return data

    def _sender_nonce_state(self, through_height: int | None = None) -> dict[str, int]:
        """Return next nonces after verifying finalized per-account nonce history."""
        head = self.finalized_head()
        final_height = int(head["height"]) if through_height is None else through_height
        next_nonces: dict[str, int] = {}
        for height in range(0, final_height + 1):
            block = self._load_block(height)
            for item in block.get("transactions", []):
                sender = str(item["sender"])
                try:
                    nonce = int(item["nonce"])
                except (TypeError, ValueError) as exc:
                    raise ChainStoreError("canonical transaction nonce is invalid") from exc
                expected_nonce = next_nonces.get(sender, 0)
                if nonce != expected_nonce:
                    raise ChainStoreError("canonical sender nonce sequence is not contiguous")
                next_nonces[sender] = expected_nonce + 1
        return next_nonces

    def finalized_head(self) -> dict[str, Any]:
        if not self.head_path.exists():
            raise ChainStoreError("finalized head is not initialized")
        return self._read_json(self.head_path)

    def committed(self, tx_hash: str) -> bool:
        return tx_hash in self._read_json(self.tx_index_path)

    @_serialized_write
    def append_finalized_block(
        self,
        block: MainnetBlock,
        *,
        expected_state: Mapping[str, Mapping[str, str]],
    ) -> dict[str, Any]:
        canonical_state, canonical_head, canonical_index = self._scan_canonical()
        head = self.finalized_head()
        tx_index = self._read_json(self.tx_index_path)
        if head != canonical_head or tx_index != canonical_index:
            raise ChainStoreError("derived metadata mismatch; reconcile before append")
        if state_root(dict(expected_state)) != canonical_head["state_root"]:
            raise ChainStoreError("starting state does not match canonical finalized state")

        if block.chain_id != self.chain_id:
            raise ChainStoreError("block chain id mismatch")

        expected_height = int(head["height"]) + 1
        if block.height != expected_height:
            raise ChainStoreError("block height does not extend finalized head")

        if block.previous_block_hash != head["block_hash"]:
            raise ChainStoreError("previous block hash does not match finalized head")

        txs = tuple(block.transactions)
        issuance_policy = policy_from_authority_config(self.load_genesis()["authority_config"])

        seen: set[str] = set()
        for tx in txs:
            if tx.chain_id != self.chain_id:
                raise ChainStoreError("transaction chain id mismatch")

            if tx.tx_hash in seen:
                raise ChainStoreError("duplicate transaction inside block")

            if tx.tx_hash in tx_index:
                raise ChainStoreError("transaction replay detected")

            seen.add(tx.tx_hash)

        starting_nonces = self._sender_nonce_state()
        expected_economic_state = self._replay_economic_state()

        expected_economic_state = self._economic_state_after_transactions(
            expected_economic_state,
            txs,
        )

        expected_economic_root = economic_state_root(expected_economic_state)

        if block.economic_state_root != expected_economic_root:
            raise ChainStoreError("block economic state root mismatch")

        transition = MainnetStateTransition().apply(
            canonical_state,
            list(txs),
            chain_id=self.chain_id,
            known_tx_hashes=tuple(tx_index.keys()),
            issuance_policy=issuance_policy,
            expected_nonces=starting_nonces,
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
        state, head, index = self._scan_canonical()
        self._verify_metadata(head, index)
        return state

    @_serialized_write
    def reconcile(self, *, expected_head: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Rebuild derived metadata only after validating ALL canonical files.

        Historical state-root incompatibility is an error, never permission to
        rewrite genesis or finalized blocks. Run recovery on a copy first.
        """
        _, head, index = self._scan_canonical()
        if expected_head is not None and dict(expected_head) != head:
            raise ChainStoreError("recovery checkpoint mismatch")
        if self.head_path.exists():
            prior = self.finalized_head()
            if int(prior["height"]) > head["height"]:
                raise ChainStoreError("canonical blocks missing below recorded finalized head")
        self._atomic_write_json(self.tx_index_path, index)
        self._atomic_write_json(self.head_path, head)
        return {"reconciled": True, **head, "transactions_indexed": len(index)}

    def verify_chain(self) -> dict[str, Any]:
        _, head, index = self._scan_canonical()
        self._verify_metadata(head, index)
        return {"verified": True, **head, "blocks_checked": head["height"] + 1}

    def _verify_metadata(self, head: dict[str, Any], index: dict[str, Any]) -> None:
        if self.finalized_head() != head:
            raise ChainStoreError("finalized head mismatch with canonical replay")
        if self._read_json(self.tx_index_path) != index:
            raise ChainStoreError("transaction index mismatch with canonical replay")

    def _scan_canonical(self):
        """Read-only validation independent of head/index availability."""
        genesis = self.load_genesis()
        state = {account: dict(balances)
                 for account, balances in genesis["initial_state"].items()}
        economics = genesis["economic_state"]
        issuance_policy = policy_from_authority_config(genesis["authority_config"])
        index: dict[str, Any] = {}
        previous_hash = ""
        nonces: dict[str, int] = {}
        files = sorted(self.blocks_dir.glob("*.json"))
        for height, path in enumerate(files):
            if not re.fullmatch(r"[0-9]{20}-[0-9a-f]{64}\.json", path.name):
                raise ChainStoreError("invalid canonical block filename")
            block = self._read_json(path)
            if type(block["height"]) is not int or block["height"] != height:
                raise ChainStoreError(f"canonical block gap or duplicate at height {height}")
            if path.name != f"{height:020d}-{block['block_hash']}.json":
                raise ChainStoreError(f"canonical block filename mismatch at height {height}")
            if block["chain_id"] != self.chain_id:
                raise ChainStoreError(f"block chain id mismatch at height {height}")
            if block["previous_block_hash"] != previous_hash:
                raise ChainStoreError(f"previous hash mismatch at height {height}")
            txs = tuple(self._transaction_from_dict(item) for item in block["transactions"])
            # The transition authenticates every transaction, rejects duplicate
            # hashes and replays its financial effects from canonical genesis.
            transition = MainnetStateTransition().apply(
                state, txs, chain_id=self.chain_id, known_tx_hashes=tuple(index),
                issuance_policy=issuance_policy, expected_nonces=nonces)
            if self._transaction_root(txs) != block["transaction_root"]:
                raise ChainStoreError(f"transaction root mismatch at height {height}")
            state = transition["state"]
            if transition["state_root"] != block["resulting_state_root"]:
                raise ChainStoreError(f"state replay mismatch at height {height}")
            economics = self._economic_state_after_transactions(economics, txs)
            if economic_state_root(economics) != block["economic_state_root"]:
                raise ChainStoreError(f"economic state root mismatch at height {height}")
            unsigned = {key: block[key] for key in (
                "chain_id", "height", "previous_block_hash", "timestamp",
                "transaction_root", "resulting_state_root", "economic_state_root",
                "proposer_id", "consensus_evidence")}
            unsigned["transactions"] = [tx.unsigned_dict() for tx in txs]
            if sha256_hex(unsigned) != block["block_hash"]:
                raise ChainStoreError(f"block hash mismatch at height {height}")
            if dict(block["consensus_evidence"] or {}).get("finalized") is not True:
                raise ChainStoreError(f"block lacks finalization evidence at height {height}")
            for tx in txs:
                nonces[tx.sender] = nonces.get(tx.sender, 0) + 1
                index[tx.tx_hash] = {"height": height, "block_hash": block["block_hash"]}
            previous_hash = block["block_hash"]
        head = {"height": len(files) - 1, "block_hash": previous_hash,
                "state_root": state_root(state),
                "economic_state_root": economic_state_root(economics)}
        return state, head, index

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

            if tx.transaction_type == "settlement_release":
                result = release_whz_bond(
                    state,
                    account_id=tx.sender,
                    required_whz=required,
                )
            elif tx.transaction_type == "settlement_slash":
                result = slash_whz_bond(
                    state,
                    account_id=tx.sender,
                    required_whz=required,
                )
            else:
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
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=path.name + ".", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
