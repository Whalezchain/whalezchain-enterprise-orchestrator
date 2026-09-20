from __future__ import annotations

import uuid

from ..execution_registry import execution_registry
from ..execution_guard import execution_guard
from ..whalezchain_testnet_engine.runtime import engine, engine_lock


def transfer_handler(
    from_account: str,
    to_account: str,
    asset_symbol: str,
    amount: str,
):
    # Lock ownership belongs to the canonical execution boundary.
    # Do not reacquire engine_lock here; execute() already owns it.
    return engine.transfer(
        from_account,
        to_account,
        asset_symbol,
        amount,
    )


execution_registry.register(
    "transfer",
    transfer_handler,
)


def execute(
    from_account: str,
    to_account: str,
    asset_symbol: str,
    amount: str,
):
    proposal_id = (
        "whalezchain-testnet-transfer-"
        + str(uuid.uuid4())
    )

    execution_id = (
        "execution-"
        + str(uuid.uuid4())
    )

    execution_guard.validate(
        from_account,
        to_account,
        asset_symbol,
        amount,
    )

    with engine_lock:
        engine.reload()

        transaction = execution_registry.resolve(
            "transfer"
        )(
            from_account,
            to_account,
            asset_symbol,
            amount,
        )

        receipt = engine.receipt()

    execution = {
        "execution_id": execution_id,
        "status": "EXECUTED",
        "state_root": receipt["state_root"],
        "receipt_hash": receipt["receipt_hash"],
        "transaction": transaction,
    }

    ledger_receipt = {
        "proposal_id": proposal_id,
        "network_class": receipt["network_class"],
        "state_root": receipt["state_root"],
        "receipt_hash": receipt["receipt_hash"],
        "journal_count": receipt["journal_count"],
        "boundaries": receipt["boundaries"],
    }

    return {
        "proposal_id": proposal_id,
        "execution": execution,
        "ledger_receipt": ledger_receipt,
    }
