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


def policy_from_authority_config(config: dict) -> PRNIssuancePolicy | None:
    """Use only the policy committed in genesis; missing policy disables minting.

    This parses approved configuration; it does not select issuers or a cap.
    """
    if "prn_issuance_policy" not in config:
        return None
    data = config["prn_issuance_policy"]
    if not isinstance(data, dict) or set(data) != {"authorized_issuers", "max_supply"}:
        raise PRNIssuancePolicyError("invalid genesis PRN issuance policy")
    issuers = data["authorized_issuers"]
    if (not isinstance(issuers, list) or
            any(not isinstance(issuer, str) or not issuer for issuer in issuers) or
            len(issuers) != len(set(issuers))):
        raise PRNIssuancePolicyError("invalid genesis PRN issuers")
    cap = data["max_supply"]
    if not isinstance(cap, str):
        raise PRNIssuancePolicyError("genesis PRN max_supply must be a decimal string")
    try:
        supply = Decimal(cap)
    except InvalidOperation as exc:
        raise PRNIssuancePolicyError("invalid genesis PRN max_supply") from exc
    try:
        valid = (supply.is_finite() and supply > 0 and
                 supply == supply.quantize(Decimal("0.00000001")))
    except InvalidOperation:
        valid = False
    if not valid:
        raise PRNIssuancePolicyError("invalid genesis PRN max_supply")
    return PRNIssuancePolicy(frozenset(issuers), supply)
