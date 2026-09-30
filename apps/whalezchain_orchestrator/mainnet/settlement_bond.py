from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .genesis_economic_state import economic_state_root
from .transaction import sha256_hex


class SettlementBondStateError(ValueError):
    """Raised when canonical WHZ settlement-bond state cannot be verified."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _decimal(value: Any, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SettlementBondStateError(
            f"invalid_settlement_bond_{field}"
        ) from exc

    if not amount.is_finite() or amount < 0:
        raise SettlementBondStateError(
            f"invalid_settlement_bond_{field}"
        )

    return amount


def _normalize(value: Decimal) -> str:
    return f"{value:.8f}"


def _required_whz(value: Any) -> Decimal:
    amount = _decimal(value, "required_whz")
    if amount <= 0:
        raise SettlementBondStateError(
            "settlement_required_whz_must_be_greater_than_zero"
        )
    return amount


def get_settlement_bond_state(
    economic_state: Mapping[str, Any],
    *,
    account_id: str,
    correlation_id: str,
    required_whz: str | Decimal,
    chain_id: str,
    finalized_head: Mapping[str, Any],
    observed_at: str | None = None,
) -> dict[str, Any]:
    """
    Return a read-only verification snapshot for the canonical WHZ settlement bond.

    Current canonical economic state has one settlement reservation counter:
    'whz_bond_locked'. The v1 read contract exposes that same value as
    'reserved_whz'; it does not create a second reservation ledger.
    """
    if not account_id:
        raise SettlementBondStateError("account_id_is_required")
    if not correlation_id:
        raise SettlementBondStateError("correlation_id_is_required")

    accounts = economic_state.get("accounts", {})
    if not isinstance(accounts, Mapping) or account_id not in accounts:
        raise SettlementBondStateError(
            "economic_account_not_found",
            status_code=404,
        )

    account = accounts[account_id]
    if not isinstance(account, Mapping):
        raise SettlementBondStateError("invalid_economic_account")

    total = _decimal(account.get("whz_bond", "0.00000000"), "total")
    locked = _decimal(
        account.get("whz_bond_locked", "0.00000000"),
        "locked",
    )

    if locked > total:
        raise SettlementBondStateError("settlement_bond_state_inconsistent")

    available = total - locked
    required = _required_whz(required_whz)

    if required > available:
        raise SettlementBondStateError(
            "settlement_whz_bond_insufficient",
            status_code=409,
        )

    economic_root = economic_state_root(dict(economic_state))
    height = int(finalized_head.get("height", -1))
    block_hash = str(finalized_head.get("block_hash", ""))

    state_material = {
        "contract": "whalezchain.settlement_bond_state.v1",
        "chain_id": chain_id,
        "correlation_id": correlation_id,
        "account_id": account_id,
        "economic_state_root": economic_root,
        "finalized_height": height,
        "finalized_block_hash": block_hash,
        "total_whz": _normalize(total),
        "locked_whz": _normalize(locked),
        "available_whz": _normalize(available),
        "required_whz": _normalize(required),
    }

    return {
        "status": "VERIFIED",
        "contract": "whalezchain.settlement_bond_state.v1",
        "chain_id": chain_id,
        "account_id": account_id,
        "bond_state_id": sha256_hex(state_material),
        "total_whz": _normalize(total),
        "available_whz": _normalize(available),
        "locked_whz": _normalize(locked),
        "reserved_whz": _normalize(locked),
        "required_whz": _normalize(required),
        "policy_version": str(
            economic_state.get("version", "unknown")
        ),
        "economic_state_root": economic_root,
        "finalized_height": height,
        "finalized_block_hash": block_hash,
        "correlation_id": correlation_id,
        "observed_at": observed_at
        or datetime.now(timezone.utc).isoformat(),
        "reservation_semantics": "reserved_whz_aliases_whz_bond_locked",
    }
}
