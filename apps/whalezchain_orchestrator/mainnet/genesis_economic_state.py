from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict

from .economic_policy import (
    EconomicPolicyError,
    get_account_level,
    validate_founder_external_unlock,
)
from .transaction import sha256_hex


class GenesisEconomicStateError(ValueError):
    pass


SYSTEM_POOL_WALLET = "SYSTEM_POOL_WALLET"
FOUNDER_ALLOCATION_WALLET = "FOUNDER_ALLOCATION_WALLET"
FOUNDER_EXTERNAL_WALLET = "FOUNDER_EXTERNAL_WALLET"


def _decimal(value: str | Decimal) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise GenesisEconomicStateError(
            "invalid economic-state decimal"
        ) from exc

    if not result.is_finite():
        raise GenesisEconomicStateError(
            "economic-state decimal must be finite"
        )

    return result


def _amount(value: str | Decimal, *, positive: bool = True) -> Decimal:
    result = _decimal(value)

    if positive and result <= 0:
        raise GenesisEconomicStateError(
            "amount must be greater than zero"
        )

    if not positive and result < 0:
        raise GenesisEconomicStateError(
            "amount cannot be negative"
        )

    return result


def _normalize(value: Decimal) -> str:
    return f"{value:.8f}"


EconomicAccountState = Dict[str, Dict[str, str]]


def empty_economic_state() -> Dict[str, Any]:
    return {
        "version": "genesis-v1.1",
        "system_pool": {
            "ptn": "0.00000000",
        },
        "founder": {
            "allocation_ptn": "0.00000000",
            "external_ptn": "0.00000000",
        },
        "accounts": {},
    }


def canonical_economic_state(
    state: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_accounts: Dict[str, Any] = {}

    accounts = state.get("accounts", {})

    for account_id in sorted(accounts):
        account = accounts[account_id]

        normalized_accounts[account_id] = {
            "level": account["level"],
            "trading_capital": _normalize(
                _decimal(account["trading_capital"])
            ),
            "whz_bond": _normalize(
                _decimal(account["whz_bond"])
            ),
            "whz_bond_locked": _normalize(
                _decimal(account.get("whz_bond_locked", "0.00000000"))
            ),
        }

    return {
        "version": state["version"],
        "system_pool": {
            "ptn": _normalize(
                _decimal(state["system_pool"]["ptn"])
            ),
        },
        "founder": {
            "allocation_ptn": _normalize(
                _decimal(state["founder"]["allocation_ptn"])
            ),
            "external_ptn": _normalize(
                _decimal(state["founder"]["external_ptn"])
            ),
        },
        "accounts": normalized_accounts,
    }


def economic_state_root(state: Dict[str, Any]) -> str:
    return sha256_hex(
        canonical_economic_state(state)
    )


def initialize_genesis_economic_state(
    *,
    ptn_genesis_supply: str | Decimal,
) -> Dict[str, Any]:
    supply = _amount(ptn_genesis_supply)

    state = empty_economic_state()

    state["system_pool"]["ptn"] = _normalize(supply)

    return state


def register_founder_wallets(
    state: Dict[str, Any],
) -> Dict[str, Any]:
    result = deepcopy(state)

    # Registration itself establishes identities only.
    # Balances remain unchanged.
    result.setdefault("founder", {
        "allocation_ptn": "0.00000000",
        "external_ptn": "0.00000000",
    })

    return result


def system_to_founder_allocation(
    state: Dict[str, Any],
    *,
    amount: str | Decimal,
) -> Dict[str, Any]:
    value = _amount(amount)
    result = deepcopy(state)

    system_balance = _decimal(
        result["system_pool"]["ptn"]
    )

    if system_balance < value:
        raise GenesisEconomicStateError(
            "system pool PTN balance is insufficient"
        )

    result["system_pool"]["ptn"] = _normalize(
        system_balance - value
    )

    allocation = _decimal(
        result["founder"]["allocation_ptn"]
    )

    result["founder"]["allocation_ptn"] = _normalize(
        allocation + value
    )

    return result


def founder_external_unlock(
    state: Dict[str, Any],
    *,
    amount: str | Decimal,
    founder_access_ratio: str | Decimal,
) -> Dict[str, Any]:
    value = _amount(amount)
    alpha = _decimal(founder_access_ratio)

    allocation = _decimal(
        state["founder"]["allocation_ptn"]
    )
    external = _decimal(
        state["founder"]["external_ptn"]
    )

    if allocation < value:
        raise GenesisEconomicStateError(
            "founder allocation balance is insufficient"
        )

    next_external = external + value

    try:
        validate_founder_external_unlock(
            allocation_balance=allocation,
            external_balance=next_external,
            founder_access_ratio=alpha,
        )
    except EconomicPolicyError as exc:
        raise GenesisEconomicStateError(
            str(exc)
        ) from exc

    result = deepcopy(state)

    result["founder"]["allocation_ptn"] = _normalize(
        allocation - value
    )
    result["founder"]["external_ptn"] = _normalize(
        next_external
    )

    return result


def apply_user_deposit(
    state: Dict[str, Any],
    *,
    account_id: str,
    account_level: str,
    deposit: str | Decimal,
) -> Dict[str, Any]:
    if not account_id:
        raise GenesisEconomicStateError(
            "account_id is required"
        )

    value = _amount(deposit)

    policy = get_account_level(account_level)

    trading_capital, whz_bond = policy.split_deposit(value)

    result = deepcopy(state)

    system_balance = _decimal(
        result["system_pool"]["ptn"]
    )

    # External deposit first enters SYSTEM_POOL.
    result["system_pool"]["ptn"] = _normalize(
        system_balance + value
    )

    existing = result["accounts"].get(
        account_id,
        {
            "level": account_level,
            "trading_capital": "0.00000000",
            "whz_bond": "0.00000000",
            "whz_bond_locked": "0.00000000",
        },
    )

    if existing["level"] != account_level:
        raise GenesisEconomicStateError(
            "account level change requires explicit governance"
        )

    current_capital = _decimal(
        existing["trading_capital"]
    )
    current_bond = _decimal(
        existing["whz_bond"]
    )

    result["accounts"][account_id] = {
        "level": account_level,
        "trading_capital": _normalize(
            current_capital + trading_capital
        ),
        "whz_bond": _normalize(
            current_bond + whz_bond
        ),
        "whz_bond_locked": _normalize(
            _decimal(existing.get("whz_bond_locked", "0.00000000"))
        ),
    }

    return result


def validate_genesis_economic_state(
    state: Dict[str, Any],
) -> None:
    if state.get("version") != "genesis-v1.1":
        raise GenesisEconomicStateError(
            "invalid Genesis economic-state version"
        )

    system_ptn = _decimal(
        state["system_pool"]["ptn"]
    )
    allocation = _decimal(
        state["founder"]["allocation_ptn"]
    )
    external = _decimal(
        state["founder"]["external_ptn"]
    )

    for account_id, account in state.get("accounts", {}).items():
        if not account_id:
            raise GenesisEconomicStateError(
                "empty account id"
            )

        get_account_level(account["level"])

        capital = _decimal(
            account["trading_capital"]
        )
        bond = _decimal(
            account["whz_bond"]
        )

        locked = _decimal(
            account.get("whz_bond_locked", "0.00000000")
        )

        if capital < 0 or bond < 0 or locked < 0:
            raise GenesisEconomicStateError(
                "user economic balances cannot be negative"
            )

        if locked > bond:
            raise GenesisEconomicStateError(
                "locked WHZ bond cannot exceed total WHZ bond"
            )

    if system_ptn < 0:
        raise GenesisEconomicStateError(
            "system pool PTN cannot be negative"
        )

    if allocation < 0 or external < 0:
        raise GenesisEconomicStateError(
            "founder balances cannot be negative"
        )
