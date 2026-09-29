from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

from .genesis_economic_state import (
    GenesisEconomicStateError,
    canonical_economic_state,
    economic_state_root,
)


class SettlementStateError(ValueError):
    pass


def _decimal(value: str | Decimal) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise SettlementStateError("invalid settlement decimal") from exc

    if not result.is_finite():
        raise SettlementStateError("settlement decimal must be finite")

    return result


def _positive(value: str | Decimal) -> Decimal:
    result = _decimal(value)
    if result <= 0:
        raise SettlementStateError(
            "settlement amount must be greater than zero"
        )
    return result


def _normalize(value: Decimal) -> str:
    return f"{value:.8f}"


def _account(state: dict[str, Any], account_id: str) -> dict[str, str]:
    if not account_id:
        raise SettlementStateError("account_id is required")

    accounts = state.setdefault("accounts", {})
    if account_id not in accounts:
        raise SettlementStateError(
            f"economic account does not exist: {account_id}"
        )

    return accounts[account_id]


def lock_whz_bond(
    state: dict[str, Any],
    *,
    account_id: str,
    required_whz: str | Decimal,
) -> dict[str, Any]:
    """
    Reserve WHZ economic bond capacity for a settlement.

    This deliberately does not define the policy that calculates
    required_whz. That value must come from the trusted policy /
    eligibility layer.
    """
    required = _positive(required_whz)
    result = deepcopy(state)
    account = _account(result, account_id)

    total_bond = _decimal(account["whz_bond"])
    locked = _decimal(account.get("whz_bond_locked", "0.00000000"))

    available = total_bond - locked

    if available < required:
        raise SettlementStateError(
            "insufficient WHZ bond capacity"
        )

    account["whz_bond_locked"] = _normalize(
        locked + required
    )

    canonical = canonical_economic_state(result)

    return {
        "state": result,
        "required_whz": _normalize(required),
        "available_whz_bond_before": _normalize(available),
        "economic_state_root": economic_state_root(canonical),
        "status": "BOND_LOCKED",
    }


def release_whz_bond(
    state: dict[str, Any],
    *,
    account_id: str,
    required_whz: str | Decimal,
) -> dict[str, Any]:
    required = _positive(required_whz)
    result = deepcopy(state)
    account = _account(result, account_id)

    locked = _decimal(account.get("whz_bond_locked", "0.00000000"))

    if locked < required:
        raise SettlementStateError(
            "locked WHZ bond is insufficient for release"
        )

    account["whz_bond_locked"] = _normalize(
        locked - required
    )

    canonical = canonical_economic_state(result)

    return {
        "state": result,
        "required_whz": _normalize(required),
        "economic_state_root": economic_state_root(canonical),
        "status": "BOND_RELEASED",
    }


def slash_whz_bond(
    state: dict[str, Any],
    *,
    account_id: str,
    required_whz: str | Decimal,
) -> dict[str, Any]:
    required = _positive(required_whz)
    result = deepcopy(state)
    account = _account(result, account_id)

    total_bond = _decimal(account["whz_bond"])
    locked = _decimal(account.get("whz_bond_locked", "0.00000000"))

    if locked < required:
        raise SettlementStateError(
            "locked WHZ bond is insufficient for slash"
        )

    account["whz_bond_locked"] = _normalize(
        locked - required
    )
    account["whz_bond"] = _normalize(
        total_bond - required
    )

    canonical = canonical_economic_state(result)

    return {
        "state": result,
        "required_whz": _normalize(required),
        "economic_state_root": economic_state_root(canonical),
        "status": "BOND_SLASHED",
    }
