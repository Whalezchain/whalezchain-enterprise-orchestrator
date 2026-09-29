from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Iterable

from .authentication import (
    TransactionAuthenticationError,
    verify_transaction_signature,
)
from .transaction import MainnetTransaction
from apps.whalezchain_orchestrator.asset_authority.authority import asset_authority
from .issuance_policy import PRNIssuancePolicy, PRNIssuancePolicyError


class TransactionValidationError(ValueError):
    """Raised when a Mainnet transaction is invalid."""


class MainnetTransactionValidator:
    def validate(
        self,
        tx: MainnetTransaction,
        *,
        expected_chain_id: str,
        known_tx_hashes: Iterable[str] = (),
        expected_nonce: int | None = None,
        sender_balance: str | Decimal | None = None,
        issuance_policy: PRNIssuancePolicy | None = None,
        current_prn_supply: str | Decimal | None = None,
    ) -> None:
        if not isinstance(tx, MainnetTransaction):
            raise TransactionValidationError(
                "transaction must be a MainnetTransaction"
            )

        if tx.chain_id != expected_chain_id:
            raise TransactionValidationError(
                "transaction chain_id does not match expected chain"
            )

        if not tx.tx_id:
            raise TransactionValidationError(
                "transaction tx_id is required"
            )

        if not tx.sender:
            raise TransactionValidationError(
                "transaction sender is required"
            )

        if not tx.recipient:
            raise TransactionValidationError(
                "transaction recipient is required"
            )

        if tx.transaction_type not in {"transfer", "mint_prn", "settlement_attestation"}:
            raise TransactionValidationError(
                "unsupported transaction type"
            )

        if tx.transaction_type == "settlement_attestation":
            if tx.asset_symbol != "WHZ":
                raise TransactionValidationError(
                    "settlement_attestation transactions must use WHZ"
                )
            if tx.settlement_required_whz is None:
                raise TransactionValidationError(
                    "settlement_attestation requires settlement_required_whz"
                )
            try:
                required_whz = Decimal(tx.settlement_required_whz)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise TransactionValidationError(
                    "settlement_required_whz must be a valid decimal"
                ) from exc
            if not required_whz.is_finite() or required_whz <= 0:
                raise TransactionValidationError(
                    "settlement_required_whz must be greater than zero"
                )

        if tx.transaction_type == "mint_prn":
            if tx.asset_symbol != "PRN":
                raise TransactionValidationError(
                    "mint_prn transactions must use PRN"
                )
            if issuance_policy is None:
                raise TransactionValidationError(
                    "PRN issuance policy is not configured"
                )
            try:
                issuance_policy.validate_issuer(tx.sender)
            except PRNIssuancePolicyError as exc:
                raise TransactionValidationError(str(exc)) from exc

        try:
            asset_authority.validate(tx.asset_symbol)
        except Exception as exc:
            raise TransactionValidationError(
                f"invalid asset: {tx.asset_symbol}"
            ) from exc

        try:
            amount = Decimal(tx.amount)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise TransactionValidationError(
                "transaction amount must be a valid decimal"
            ) from exc

        if not amount.is_finite() or amount <= 0:
            raise TransactionValidationError(
                "transaction amount must be greater than zero"
            )

        if tx.transaction_type == "mint_prn":
            if current_prn_supply is None:
                raise TransactionValidationError(
                    "current PRN supply is required for issuance"
                )
            try:
                current_supply = Decimal(current_prn_supply)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise TransactionValidationError(
                    "current PRN supply must be a valid decimal"
                ) from exc
            if not current_supply.is_finite() or current_supply < 0:
                raise TransactionValidationError(
                    "current PRN supply must be finite and non-negative"
                )
            try:
                issuance_policy.validate_supply(current_supply, amount)
            except PRNIssuancePolicyError as exc:
                raise TransactionValidationError(str(exc)) from exc

        if tx.nonce < 0:
            raise TransactionValidationError(
                "transaction nonce must be non-negative"
            )

        if expected_nonce is not None and tx.nonce != expected_nonce:
            raise TransactionValidationError(
                "transaction nonce does not match expected nonce"
            )

        if tx.tx_hash in set(known_tx_hashes):
            raise TransactionValidationError(
                "transaction has already been committed"
            )

        try:
            verify_transaction_signature(tx)
        except TransactionAuthenticationError as exc:
            raise TransactionValidationError(
                f"transaction authentication failed: {exc}"
            ) from exc

        if tx.transaction_type == "transfer" and sender_balance is not None:
            try:
                balance = Decimal(sender_balance)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise TransactionValidationError(
                    "sender balance must be a valid decimal"
                ) from exc

            if not balance.is_finite():
                raise TransactionValidationError(
                    "sender balance must be finite"
                )

            if amount > balance:
                raise TransactionValidationError(
                    "insufficient sender balance"
                )
