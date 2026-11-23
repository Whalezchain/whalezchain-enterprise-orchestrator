"""ABCI++ deterministic application adapter for the existing WhalezChain state machine.

Internal devnet implementation. The production network finality/release gate is
not bypassed. CometBFT owns consensus; WhalezChain owns state transitions.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .block import MainnetBlock
from .block_builder import MainnetBlockBuilder
from .chain_store import MAINNET_CHAIN_ID, MainnetChainStore
from .genesis_economic_state import economic_state_root
from .issuance_policy import policy_from_authority_config
from .state_transition import MainnetStateTransition
from .transaction import MainnetTransaction, canonical_json, sha256_hex


class CometABCIError(ValueError):
    """Untrusted or inconsistent ABCI request. Fail closed."""


DEVNET_PREFIX = "whalezchain-internal-devnet-"
MAX_TRANSACTION_BYTES = 65536
MAX_BLOCK_TRANSACTIONS = 500


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise CometABCIError("duplicate transaction JSON key")
        output[key] = value
    return output


def _decode_transaction(raw: bytes, chain_id: str) -> MainnetTransaction:
    if not raw or len(raw) > MAX_TRANSACTION_BYTES:
        raise CometABCIError("transaction size outside admission limits")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise CometABCIError("invalid canonical transaction encoding") from exc
    if not isinstance(data, dict) or raw != canonical_json(data):
        raise CometABCIError("transaction must use canonical JSON encoding")
    if set(data) != {
        "chain_id", "tx_id", "sender", "recipient", "asset_symbol",
        "amount", "nonce", "transaction_type", "authorization",
        "ordering_key", "settlement_required_whz",
    }:
        raise CometABCIError("unsupported signed transaction schema")
    if (
        data["chain_id"] != chain_id
        or data["transaction_type"] != "transfer"
        or data["settlement_required_whz"] is not None
    ):
        raise CometABCIError("devnet admits native transfers only")
    if not isinstance(data["nonce"], int) or isinstance(data["nonce"], bool):
        raise CometABCIError("nonce must be an integer")
    try:
        return MainnetTransaction(**data)
    except (TypeError, ValueError) as exc:
        raise CometABCIError("invalid signed transaction") from exc


def _app_hash(height: int, block_hash: str, state: str, economic: str) -> str:
    return sha256_hex({
        "schema": "whalezchain.cometbft.abci_app_hash.v1",
        "comet_height": height,
        "whalez_block_hash": block_hash,
        "state_root": state,
        "economic_state_root": economic,
    })


@dataclass(frozen=True)
class StagedBlock:
    comet_height: int
    block: MainnetBlock
    initial_state: dict[str, dict[str, str]]
    app_hash: str


class WhalezCometApplication:
    """CometBFT ABCI++ lifecycle over canonical WhalezChain persistence.

    A single instance belongs to one validator application process/store.
    In production, the independent validator proof gate must be implemented
    before this protocol can be enabled; no test-only flag enables mainnet.
    """

    def __init__(self, store_path: str | Path, network_chain_id: str):
        if not network_chain_id.startswith(DEVNET_PREFIX):
            raise CometABCIError("unapproved network: internal devnet only")
        self.network_chain_id = network_chain_id
        self.store = MainnetChainStore(store_path)
        self._staged: StagedBlock | None = None
        self._assert_devnet()
        self.store.verify_chain()
        genesis = self.store.load_genesis()
        # Devnet naming is insufficient: never attach this laboratory
        # adapter to an approved or otherwise non-test genesis.
        if genesis.get("authority_config", {}).get("mode") != "test":
            raise CometABCIError("internal devnet requires a synthetic test genesis")

    @staticmethod
    def _assert_devnet() -> None:
        if os.getenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "").lower() == "true":
            raise CometABCIError("production financial execution forbidden in devnet adapter")

    def _current_head(self) -> dict[str, Any]:
        self._assert_devnet()
        self.store.verify_chain()
        return self.store.finalized_head()

    def info(self) -> dict[str, Any]:
        head = self._current_head()
        return {
            "height": int(head["height"]) + 1,
            "app_hash": _app_hash(
                int(head["height"]) + 1, head["block_hash"],
                head["state_root"], head["economic_state_root"]
            ),
            "network_chain_id": self.network_chain_id,
        }

    def init_chain(self, chain_id: str, app_genesis_hash: str) -> dict[str, Any]:
        if chain_id != self.network_chain_id:
            raise CometABCIError("CometBFT network chain ID mismatch")
        if app_genesis_hash != self.store.load_genesis()["genesis_hash"]:
            raise CometABCIError("CometBFT and WhalezChain genesis differ")
        if int(self._current_head()["height"]) != -1:
            raise CometABCIError("InitChain cannot reinitialize committed state")
        return self.info()

    def _simulate(self, raws: Sequence[bytes]) -> tuple[
        tuple[MainnetTransaction, ...],
        dict[str, dict[str, str]],
        str,
        str,
    ]:
        self._assert_devnet()
        if len(raws) > MAX_BLOCK_TRANSACTIONS:
            raise CometABCIError("block transaction count exceeds limit")
        head = self._current_head()
        start = self.store.replay_state()
        txs = tuple(_decode_transaction(raw, self.store.chain_id) for raw in raws)
        index = self.store._read_json(self.store.tx_index_path)
        policy = policy_from_authority_config(self.store.load_genesis()["authority_config"])
        result = MainnetStateTransition().apply(
            start, txs,
            chain_id=self.store.chain_id,
            known_tx_hashes=tuple(index.keys()),
            issuance_policy=policy,
            expected_nonces=self.store._sender_nonce_state(),
        )
        return (
            txs, start, result["state_root"],
            economic_state_root(self.store._replay_economic_state()),
        )

    def check_tx(self, raw: bytes) -> bool:
        try:
            self._simulate((raw,))
            return True
        except (ValueError, KeyError, TypeError):
            return False

    def prepare_proposal(self, raws: Sequence[bytes], max_bytes: int) -> list[bytes]:
        if max_bytes <= 0:
            return []
        accepted: list[bytes] = []
        total = 0
        for raw in raws[:MAX_BLOCK_TRANSACTIONS]:
            if total + len(raw) > max_bytes:
                break
            try:
                self._simulate((*accepted, raw))
            except (ValueError, KeyError, TypeError):
                continue
            accepted.append(raw)
            total += len(raw)
        return accepted

    def process_proposal(self, raws: Sequence[bytes]) -> bool:
        try:
            self._simulate(raws)
            return True
        except (ValueError, KeyError, TypeError):
            return False

    def finalize_block(
        self, *, height: int, block_hash: str, timestamp: str,
        proposer_address: str, raws: Sequence[bytes],
    ) -> dict[str, Any]:
        head = self._current_head()
        if self._staged is not None:
            raise CometABCIError("a block is already staged awaiting Commit")
        if height != int(head["height"]) + 2 or height < 1:
            raise CometABCIError("CometBFT block height does not extend canonical head")
        if len(block_hash) != 64:
            raise CometABCIError("invalid CometBFT block hash")
        try:
            bytes.fromhex(block_hash)
            bytes.fromhex(proposer_address)
        except ValueError as exc:
            raise CometABCIError("invalid CometBFT identity/hash") from exc
        if not proposer_address or not timestamp.endswith("Z"):
            raise CometABCIError("invalid deterministic block metadata")
        txs, start, state_root, economic_root = self._simulate(raws)
        candidate = MainnetBlockBuilder().build(
            chain_id=MAINNET_CHAIN_ID,
            height=height - 1,
            previous_block_hash=str(head["block_hash"]),
            timestamp=timestamp,
            transactions=txs,
            resulting_state_root=state_root,
            economic_state_root=economic_root,
            proposer_id="cometbft:" + proposer_address.lower(),
        )
        # Identical committed application evidence on all replicas, derived
        # from decided block data. NOT an independently certified quorum proof.
        block = replace(candidate, consensus_evidence={
            "status": "COMET_ABCI_DECIDED_DEVNET",
            "finalized": True,
            "finality_type": "cometbft_engine_decision_devnet_not_independently_verified",
            "network_chain_id": self.network_chain_id,
            "comet_height": height,
            "comet_block_hash": block_hash.lower(),
        })
        digest = _app_hash(height, block.block_hash, state_root, economic_root)
        self._staged = StagedBlock(height, block, start, digest)
        return {"app_hash": digest, "tx_count": len(txs), "whalez_block_hash": block.block_hash}

    def commit(self) -> dict[str, Any]:
        self._assert_devnet()
        staged = self._staged
        if staged is None:
            raise CometABCIError("Commit without FinalizeBlock")
        head = self.store.append_finalized_block(
            staged.block, expected_state=staged.initial_state
        )
        self._staged = None
        if int(head["height"]) + 1 != staged.comet_height:
            raise CometABCIError("post-commit height mismatch")
        if self.info()["app_hash"] != staged.app_hash:
            raise CometABCIError("post-commit app hash mismatch")
        return {"height": staged.comet_height, "app_hash": staged.app_hash}
