from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class EconomicPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class AccountLevelPolicy:
    level: str
    whz_bond_ratio: Decimal
    trading_capital_ratio: Decimal

    def split_deposit(self, deposit: Decimal) -> tuple[Decimal, Decimal]:
        if not deposit.is_finite() or deposit <= 0:
            raise EconomicPolicyError(
                "deposit must be finite and greater than zero"
            )

        whz_bond = deposit * self.whz_bond_ratio
        trading_capital = deposit * self.trading_capital_ratio

        if whz_bond + trading_capital != deposit:
            raise EconomicPolicyError(
                "deposit split invariant violated"
            )

        return trading_capital, whz_bond


ACCOUNT_LEVELS = {
    "L0": AccountLevelPolicy(
        level="L0",
        whz_bond_ratio=Decimal("0.10"),
        trading_capital_ratio=Decimal("0.90"),
    ),
    "L1": AccountLevelPolicy(
        level="L1",
        whz_bond_ratio=Decimal("0.20"),
        trading_capital_ratio=Decimal("0.80"),
    ),
    "L2": AccountLevelPolicy(
        level="L2",
        whz_bond_ratio=Decimal("0.30"),
        trading_capital_ratio=Decimal("0.70"),
    ),
    "L3": AccountLevelPolicy(
        level="L3",
        whz_bond_ratio=Decimal("0.40"),
        trading_capital_ratio=Decimal("0.60"),
    ),
}


def get_account_level(level: str) -> AccountLevelPolicy:
    try:
        return ACCOUNT_LEVELS[level]
    except KeyError as exc:
        raise EconomicPolicyError(
            f"unknown account level: {level}"
        ) from exc


def split_deposit(
    deposit: str | Decimal,
    *,
    account_level: str,
) -> dict[str, Decimal]:
    try:
        amount = (
            deposit
            if isinstance(deposit, Decimal)
            else Decimal(deposit)
        )
    except (InvalidOperation, ValueError) as exc:
        raise EconomicPolicyError(
            "deposit must be a valid decimal"
        ) from exc

    policy = get_account_level(account_level)
    trading_capital, whz_bond = policy.split_deposit(amount)

    return {
        "deposit": amount,
        "trading_capital": trading_capital,
        "whz_bond": whz_bond,
    }


def validate_founder_external_unlock(
    *,
    allocation_balance: Decimal,
    external_balance: Decimal,
    founder_access_ratio: Decimal,
) -> None:
    if allocation_balance < 0 or external_balance < 0:
        raise EconomicPolicyError(
            "founder balances cannot be negative"
        )

    if not founder_access_ratio.is_finite() or founder_access_ratio < 0:
        raise EconomicPolicyError(
            "founder access ratio must be finite and non-negative"
        )

    if external_balance > founder_access_ratio * allocation_balance:
        raise EconomicPolicyError(
            "founder external balance exceeds allocation limit"
        )
