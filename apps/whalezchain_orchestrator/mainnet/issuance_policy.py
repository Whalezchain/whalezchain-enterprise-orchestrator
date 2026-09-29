from __future__ import annotations

from decimal import Decimal, InvalidOperation
from dataclasses import dataclass


class PRNIssuancePolicyError(ValueError):
    """Raised when PRN issuance policy is missing or violated."""


@dataclass(frozen=True)
class PRNIssuancePolicy:
    """
    Explicit PRN issuance policy.

    An empty issuer set disables issuance.
    max_supply is mandatory so issuance cannot create
    uncontrolled PRN supply.
    """

    authorized_issuers: frozenset[str]
    max_supply: Decimal

    def __post_init__(self) -> None:
        if not self.authorized_issuers:
            return

        try:
            supply = Decimal(self.max_supply)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PRNIssuancePolicyError(
                "PRN max_supply must be a valid decimal"
            ) from exc

        if not supply.is_finite() or supply <= 0:
            raise PRNIssuancePolicyError(
                "PRN max_supply must be finite and greater than zero"
            )

    def validate_issuer(self, issuer: str) -> None:
        if issuer not in self.authorized_issuers:
            raise PRNIssuancePolicyError(
                "PRN issuer is not authorized"
            )

    def validate_supply(self, current_supply: Decimal, amount: Decimal) -> None:
        if current_supply + amount > self.max_supply:
            raise PRNIssuancePolicyError(
                "PRN issuance would exceed maximum supply"
            )


DISABLED_PRN_ISSUANCE_POLICY = PRNIssuancePolicy(
    authorized_issuers=frozenset(),
    max_supply=Decimal("1"),
)
