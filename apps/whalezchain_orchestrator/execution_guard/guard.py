from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..asset_authority import asset_authority


class ExecutionGuard:

    def validate(
        self,
        from_account: str,
        to_account: str,
        asset_symbol: str,
        amount: str,
    ):

        if not from_account:
            raise ValueError(
                "missing source account"
            )

        if not to_account:
            raise ValueError(
                "missing destination account"
            )

        asset_authority.validate(asset_symbol)

        try:
            value = Decimal(amount)
        except (InvalidOperation, ValueError):
            raise ValueError(
                "amount must be a valid decimal"
            )

        if not value.is_finite():
            raise ValueError(
                "amount must be a finite decimal"
            )

        if value <= 0:
            raise ValueError(
                "amount must be greater than zero"
            )

        return {
            "validated": True,
            "asset": asset_symbol,
            "amount": str(value),
            "boundary": "internal_testnet_only",
        }


execution_guard = ExecutionGuard()
