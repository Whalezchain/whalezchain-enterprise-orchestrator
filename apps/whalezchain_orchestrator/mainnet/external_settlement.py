from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .block_builder import MainnetBlockBuilder
from .chain_store import MainnetChainStore, ChainStoreError
from .finalization_authorization import (
    MainnetFinalizationAuthorization,
)
from .transaction import canonical_json, sha256_hex


EXTERNAL_SETTLEMENT_TYPE = "whalezchain.external_settlement_attestation.v1"


class ExternalSettlementError(ValueError):
    pass


@dataclass(frozen=True)
class ExternalSettlement:
    correlation_id: str
    idempotency_key: str
    user_id: str
    jurisdiction: str
    settlement_asset: str
    amount_minor: int
    currency: str
    external_provider: str
    external_reference: str
    provider_transaction_id: str
    provider_event_id: str
    provider_domain: str
    settlement_required_whz: str | None

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "user_id": self.user_id,
            "jurisdiction": self.jurisdiction,
            "settlement_asset": self.settlement_asset,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "external_provider": self.external_provider,
            "external_reference": self.external_reference,
            "provider_transaction_id": self.provider_transaction_id,
            "provider_event_id": self.provider_event_id,
            "provider_domain": self.provider_domain,
            "settlement_required_whz": self.settlement_required_whz,
        }

    @property
    def evidence_hash(self) -> str:
        return sha256_hex(self.canonical_dict())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_path() -> Path:
    configured = os.getenv("WHALEZCHAIN_MAINNET_STORE_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path("data") / "whalezchain-mainnet"


def _decimal_or_none(value: Any) -> str | None:
    if value in (None, "", "0", "0.0", "0.00000000"):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ExternalSettlementError("invalid_settlement_required_whz")
    if not amount.is_finite() or amount < 0:
        raise ExternalSettlementError("invalid_settlement_required_whz")
    if amount == 0:
        return None
    return f"{amount:.8f}"


def _build_request(payload: dict[str, Any]) -> ExternalSettlement:
    required = (
        "correlation_id",
        "idempotency_key",
        "user_id",
        "jurisdiction",
        "settlement_asset",
        "amount_minor",
        "currency",
        "external_provider",
        "external_reference",
        "provider_transaction_id",
        "provider_event_id",
        "provider_domain",
        "approval_id",
    )
    missing = [key for key in required if payload.get(key) in (None, "")]
    if missing:
        raise ExternalSettlementError(
            "missing_external_settlement_fields:" + ",".join(missing)
        )

    try:
        amount_minor = int(payload["amount_minor"])
    except (TypeError, ValueError) as exc:
        raise ExternalSettlementError("invalid_amount_minor") from exc
    if amount_minor <= 0:
        raise ExternalSettlementError("invalid_amount_minor")

    currency = str(payload["currency"]).upper()
    jurisdiction = str(payload["jurisdiction"]).upper()
    provider = str(payload["external_provider"]).lower()

    allowed = {
        item.strip().lower()
        for item in os.getenv(
            "WHALEZCHAIN_EXTERNAL_SETTLEMENT_PROVIDERS",
            "paystack",
        ).split(",")
        if item.strip()
    }

    if provider not in allowed:
        raise ExternalSettlementError("external_provider_not_allowlisted")
    if not jurisdiction:
        raise ExternalSettlementError("invalid_jurisdiction")
    if not currency:
        raise ExternalSettlementError("invalid_currency")

    required_whz = _decimal_or_none(payload.get("settlement_required_whz"))

    # The current canonical chain state transition knows how to lock WHZ
    # through MainnetTransaction, but an external fiat attestation is not
    # itself a native balance transfer. Until a governed native transaction
    # mapping is supplied, refusing the lock path is the safe behavior.
    if required_whz is not None:
        raise ExternalSettlementError(
            "whz_bond_lock_requires_native_transaction_path"
        )

    return ExternalSettlement(
        correlation_id=str(payload["correlation_id"]).strip(),
        idempotency_key=str(payload["idempotency_key"]).strip(),
        user_id=str(payload["user_id"]).strip(),
        jurisdiction=jurisdiction,
        settlement_asset=str(payload["settlement_asset"]).strip(),
        amount_minor=amount_minor,
        currency=currency,
        external_provider=provider,
        external_reference=str(payload["external_reference"]).strip(),
        provider_transaction_id=str(payload["provider_transaction_id"]).strip(),
        provider_event_id=str(payload["provider_event_id"]).strip(),
        provider_domain=str(payload["provider_domain"]).strip(),
        settlement_required_whz=required_whz,
    )


def _index_path(store: MainnetChainStore) -> Path:
    return store.meta_dir / "external_settlement_index.json"


def _receipt_dir(store: MainnetChainStore) -> Path:
    return store.root / "receipts" / "external-settlement"


def _load_index(store: MainnetChainStore) -> dict[str, Any]:
    path = _index_path(store)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _with_lock(store: MainnetChainStore):
    lock_path = store.meta_dir / "external_settlement.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _block_from_dict(data: dict[str, Any]):
    from .block import MainnetBlock
    from .transaction import MainnetTransaction

    txs = []
    for raw in data.get("transactions", []):
        txs.append(
            MainnetTransaction(
                chain_id=raw["chain_id"],
                tx_id=raw["tx_id"],
                sender=raw["sender"],
                recipient=raw["recipient"],
                asset_symbol=raw["asset_symbol"],
                amount=raw["amount"],
                nonce=int(raw["nonce"]),
                transaction_type=raw["transaction_type"],
                authorization=raw["authorization"],
                ordering_key=raw["ordering_key"],
                settlement_required_whz=raw.get("settlement_required_whz"),
            )
        )

    return MainnetBlock(
        chain_id=data["chain_id"],
        height=int(data["height"]),
        previous_block_hash=data["previous_block_hash"],
        timestamp=data["timestamp"],
        transactions=tuple(txs),
        transaction_root=data["transaction_root"],
        resulting_state_root=data["resulting_state_root"],
        economic_state_root=data["economic_state_root"],
        proposer_id=data["proposer_id"],
        consensus_evidence=data["consensus_evidence"],
    )


def _build_candidate(
    store: MainnetChainStore,
    settlement: ExternalSettlement,
    *,
    approval_id: str,
    timestamp: str,
) -> dict[str, Any]:
    head = store.finalized_head()
    block = MainnetBlockBuilder().build(
        chain_id=store.chain_id,
        height=int(head["height"]) + 1,
        previous_block_hash=str(head["block_hash"]),
        timestamp=timestamp,
        transactions=[],
        resulting_state_root=str(head["state_root"]),
        economic_state_root=str(head["economic_state_root"]),
        proposer_id="whalez-ai-external-settlement",
    )

    consensus_evidence = {
        "status": "finalizable",
        "finalized": True,
        "finality_type": "external_settlement_attestation",
        "external_settlement_type": EXTERNAL_SETTLEMENT_TYPE,
        "provider_verified": True,
        "external_settlement": settlement.canonical_dict(),
        "external_settlement_evidence_hash": settlement.evidence_hash,
    }

    from .block import MainnetBlock

    finalized_candidate = MainnetBlock(
        chain_id=block.chain_id,
        height=block.height,
        previous_block_hash=block.previous_block_hash,
        timestamp=block.timestamp,
        transactions=block.transactions,
        transaction_root=block.transaction_root,
        resulting_state_root=block.resulting_state_root,
        economic_state_root=block.economic_state_root,
        proposer_id=block.proposer_id,
        consensus_evidence=consensus_evidence,
    )

    if not approval_id:
        raise ExternalSettlementError("missing_approval_id")

    genesis = store.load_genesis()
    finalization_payload = {
        "authorization_type": "wcz.mainnet.finalization_authorization.v1",
        "approval_id": approval_id,
        "chain_id": store.chain_id,
        "genesis_hash": str(genesis["genesis_hash"]),
        "height": finalized_candidate.height,
        "previous_block_hash": finalized_candidate.previous_block_hash,
        "transaction_root": finalized_candidate.transaction_root,
        "resulting_state_root": finalized_candidate.resulting_state_root,
        "economic_state_root": finalized_candidate.economic_state_root,
        "block_hash": finalized_candidate.block_hash,
        "authority": "WHALEZ_AI",
        "execution_mode": "mainnet_finalization",
    }
    finalization_payload["target_payload_hash"] = sha256_hex(
        finalization_payload
    )

    return {
        "block": finalized_candidate.unsigned_dict() | {
            "block_hash": finalized_candidate.block_hash,
            "transactions": [],
        },
        "finalization_payload": finalization_payload,
        "external_settlement_evidence_hash": settlement.evidence_hash,
    }


def prepare_external_settlement(payload: dict[str, Any]) -> dict[str, Any]:
    if os.getenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "").lower() != "true":
        raise ExternalSettlementError("mainnet_not_live")

    settlement = _build_request(payload)
    store = MainnetChainStore(_store_path())

    with _with_lock(store) as lock:
        try:
            index = _load_index(store)
            existing = index.get(settlement.idempotency_key)
            if existing:
                return {**existing, "replay": True}

            candidate = _build_candidate(
                store,
                settlement,
                approval_id=str(payload.get("approval_id", "")).strip(),
                timestamp=str(payload.get("timestamp") or _now()),
            )
            result = {
                "status": "FINALIZATION_AUTHORIZATION_REQUIRED",
                "finalized": False,
                "correlation_id": settlement.correlation_id,
                "idempotency_key": settlement.idempotency_key,
                "approval_id": str(payload["approval_id"]).strip(),
                "block": candidate["block"],
                "finalization_payload": candidate["finalization_payload"],
                "external_settlement_evidence_hash": settlement.evidence_hash,
            }
            return result
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def finalize_external_settlement(payload: dict[str, Any]) -> dict[str, Any]:
    if os.getenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "").lower() != "true":
        raise ExternalSettlementError("mainnet_not_live")

    settlement = _build_request(payload)
    store = MainnetChainStore(_store_path())

    block_data = payload.get("block")
    finalization_payload = payload.get("finalization_payload")
    execution_authorization = payload.get("execution_authorization")

    if not isinstance(block_data, dict):
        raise ExternalSettlementError("missing_candidate_block")
    if not isinstance(finalization_payload, dict):
        raise ExternalSettlementError("missing_finalization_payload")
    if not isinstance(execution_authorization, dict):
        raise ExternalSettlementError("missing_execution_authorization")

    with _with_lock(store) as lock:
        try:
            index = _load_index(store)
            existing = index.get(settlement.idempotency_key)
            if existing:
                return {**existing, "replay": True}

            approval_id = str(finalization_payload.get("approval_id", "")).strip()
            candidate = _build_candidate(
                store,
                settlement,
                approval_id=approval_id,
                timestamp=str(block_data.get("timestamp") or ""),
            )

            expected_block_hash = str(candidate["block"]["block_hash"])
            if str(block_data.get("block_hash")) != expected_block_hash:
                raise ExternalSettlementError("candidate_block_changed")

            if finalization_payload != candidate["finalization_payload"]:
                raise ExternalSettlementError("finalization_payload_changed")

            required_auth_fields = (
                "approval_id",
                "execution_hash",
                "target_payload_hash",
            )
            for key in required_auth_fields:
                if not str(execution_authorization.get(key, "")).strip():
                    raise ExternalSettlementError(
                        "execution_authorization_missing_" + key
                    )

            if str(execution_authorization["approval_id"]).strip() != approval_id:
                raise ExternalSettlementError("approval_id_mismatch")

            target_without_hash = {
                key: value
                for key, value in finalization_payload.items()
                if key != "target_payload_hash"
            }
            expected_target_hash = sha256_hex(target_without_hash)
            if (
                str(execution_authorization["target_payload_hash"]).strip()
                != str(finalization_payload["target_payload_hash"])
                or str(finalization_payload["target_payload_hash"])
                != expected_target_hash
            ):
                raise ExternalSettlementError(
                    "finalization_target_payload_hash_mismatch"
                )

            authorization = MainnetFinalizationAuthorization(
                authorization_type=str(finalization_payload["authorization_type"]),
                approval_id=str(execution_authorization["approval_id"]),
                execution_hash=str(execution_authorization["execution_hash"]),
                target_payload_hash=str(execution_authorization["target_payload_hash"]),
                chain_id=str(finalization_payload["chain_id"]),
                genesis_hash=str(finalization_payload["genesis_hash"]),
                height=int(finalization_payload["height"]),
                previous_block_hash=str(finalization_payload["previous_block_hash"]),
                transaction_root=str(finalization_payload["transaction_root"]),
                resulting_state_root=str(finalization_payload["resulting_state_root"]),
                economic_state_root=str(finalization_payload["economic_state_root"]),
                block_hash=str(finalization_payload["block_hash"]),
                authority=str(finalization_payload["authority"]),
                execution_mode=str(finalization_payload["execution_mode"]),
            )

            block = _block_from_dict(block_data)
            authorization.matches_block(
                chain_id=store.chain_id,
                genesis_hash=str(store.load_genesis()["genesis_hash"]),
                height=block.height,
                previous_block_hash=block.previous_block_hash,
                transaction_root=block.transaction_root,
                resulting_state_root=block.resulting_state_root,
                economic_state_root=block.economic_state_root,
                block_hash=block.block_hash,
            )

            expected_state = store.replay_state()
            new_head = store.append_finalized_block(
                block,
                expected_state=expected_state,
            )

            receipt_body = {
                "receipt_type": "whalezchain_external_settlement_receipt_v1",
                "status": "FINALIZED",
                "finality": "FINALIZED",
                "canonical": True,
                "external_settlement": settlement.canonical_dict(),
                "external_settlement_evidence_hash": settlement.evidence_hash,
                "finalization_authorization_hash": authorization.authorization_hash,
                "approval_id": authorization.approval_id,
                "execution_hash": authorization.execution_hash,
                "target_payload_hash": authorization.target_payload_hash,
                "block_height": block.height,
                "block_hash": block.block_hash,
                "transaction_root": block.transaction_root,
                "resulting_state_root": block.resulting_state_root,
                "economic_state_root": block.economic_state_root,
                "previous_block_hash": block.previous_block_hash,
                "head": new_head,
                "settlement_required_whz": settlement.settlement_required_whz,
                "settlement_status": "NONE",
                "timestamp": _now(),
            }
            receipt_hash = sha256_hex(receipt_body)
            receipt = {
                **receipt_body,
                "receipt_hash": receipt_hash,
            }

            receipt_path = _receipt_dir(store) / f"{receipt_hash}.json"
            _atomic_write(receipt_path, receipt)

            index[settlement.idempotency_key] = {
                "status": "FINALIZED",
                "finality": "FINALIZED",
                "canonical": True,
                "correlation_id": settlement.correlation_id,
                "idempotency_key": settlement.idempotency_key,
                "receipt_hash": receipt_hash,
                "receipt_path": str(receipt_path),
                "block_height": block.height,
                "block_hash": block.block_hash,
            }
            _atomic_write(_index_path(store), index)

            return {
                "status": "FINALIZED",
                "finality": "FINALIZED",
                "canonical": True,
                "canonical_receipt": receipt,
            }
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
