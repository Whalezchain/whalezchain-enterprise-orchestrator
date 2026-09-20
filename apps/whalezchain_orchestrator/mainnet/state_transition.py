from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable

from ..asset_authority import ASSET_REGISTRY
from .transaction import MainnetTransaction, sha256_hex
from .transaction_validator import (
    MainnetTransactionValidator,
    TransactionValidationError,
)


class StateTransitionError(ValueError):
    pass


BalanceState = Dict[str, Dict[str, str]]


def _decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise StateTransitionError(
            "invalid balance state"
        ) from exc

    if not result.is_finite():
        raise StateTransitionError(
            "balance must be finite"
        )

    return result


def _normalize_balance(value: Decimal) -> str:
    return f"{value:.8f}"


def canonical_state(
    accounts: BalanceState,
) -> Dict[str, Any]:
    normalized: Dict[str, Dict[str, str]] = {}

    for account_id in sorted(accounts):
        normalized[account_id] = {}

        for asset_symbol in sorted(ASSET_REGISTRY):
            value = accounts[account_id].get(
                asset_symbol,
                "0.00000000",
            )

            normalized[account_id][asset_symbol] = (
                _normalize_balance(_decimal(value))
            )

    return {
        "accounts": normalized,
        "assets": deepcopy(ASSET_REGISTRY),
    }


def state_root(accounts: BalanceState) -> str:
    return sha256_hex(
        canonical_state(accounts)
    )


class MainnetStateTransition:

    def __init__(
        self,
        *,
        validator: MainnetTransactionValidator | None = None,
    ):
        self.validator = (
            validator
            if validator is not None
            else MainnetTransactionValidator()
        )

    def apply(
        self,
        initial_state: BalanceState,
        transactions: Iterable[MainnetTransaction],
        *,
        chain_id: str,
        known_tx_hashes: Iterable[str] = (),
    ) -> Dict[str, Any]:

        working_state = deepcopy(initial_state)

        committed_hashes = set(known_tx_hashes)
        block_hashes: set[str] = set()

        transitions = []

        for tx in transactions:
            tx_hash = tx.tx_hash

            if tx_hash in block_hashes:
                raise StateTransitionError(
                    f"duplicate transaction in block: {tx_hash}"
                )

            try:
                amount = Decimal(tx.amount)
            except (InvalidOperation, ValueError) as exc:
                raise StateTransitionError(
                    "amount must be a valid decimal"
                ) from exc

            if not amount.is_finite() or amount <= 0:
                raise StateTransitionError(
                    "amount must be greater than zero"
                )

            sender = working_state.setdefault(
                tx.sender,
                {
                    symbol: "0.00000000"
                    for symbol in ASSET_REGISTRY
                },
            )

            recipient = working_state.setdefault(
                tx.recipient,
                {
                    symbol: "0.00000000"
                    for symbol in ASSET_REGISTRY
                },
            )

            sender_balance = _decimal(
                sender.get(
                    tx.asset_symbol,
                    "0.00000000",
                )
            )

            # Validate against the state as it exists immediately
            # before this transaction.
            self.validator.validate(
                tx,
                expected_chain_id=chain_id,
                known_tx_hashes=committed_hashes,
                sender_balance=sender_balance,
            )

            before_root = state_root(
                working_state
            )

            recipient_balance = _decimal(
                recipient.get(
                    tx.asset_symbol,
                    "0.00000000",
                )
            )

            sender[
                tx.asset_symbol
            ] = _normalize_balance(
                sender_balance - amount
            )

            recipient[
                tx.asset_symbol
            ] = _normalize_balance(
                recipient_balance + amount
            )

            after_root = state_root(
                working_state
            )

            transitions.append({
                "tx_hash": tx_hash,
                "tx_id": tx.tx_id,
                "sender": tx.sender,
                "recipient": tx.recipient,
                "asset_symbol": tx.asset_symbol,
                "amount": _normalize_balance(amount),
                "before_state_root": before_root,
                "after_state_root": after_root,
                "status": "APPLIED",
            })

            block_hashes.add(tx_hash)

        return {
            "state": deepcopy(working_state),
            "state_root": state_root(
                working_state
            ),
            "transaction_count": len(
                transitions
            ),
            "transitions": transitions,
        }
