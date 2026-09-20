from __future__ import annotations

import uuid

from ..execution_guard import execution_guard
from ..whalezchain_testnet_engine.runtime import engine, engine_lock
from ..models import (
    TestnetTransferRequest,
    TestnetTransferResponse,
    ExecutionReceipt,
)


def execute_transfer(
    request: TestnetTransferRequest,
) -> TestnetTransferResponse:

    proposal_id = (
        "whalezchain-testnet-transfer-"
        + str(uuid.uuid4())
    )

    execution_guard.validate(
        request.from_account,
        request.to_account,
        request.asset_symbol,
        request.amount,
    )

    with engine_lock:
        engine.reload()

        transaction = engine.transfer(
            from_account=request.from_account,
            to_account=request.to_account,
            asset_symbol=request.asset_symbol,
            amount=request.amount,
        )

    receipt = engine.receipt()

    execution = ExecutionReceipt(
        execution_id=proposal_id,
        status="executed",
        state_root=receipt["state_root"],
        receipt_hash=receipt["receipt_hash"],
        transaction=transaction,
    )

    ledger_receipt = {
        "proposal_id": proposal_id,
        "network_class": receipt["network_class"],
        "state_root": receipt["state_root"],
        "receipt_hash": receipt["receipt_hash"],
        "journal_count": receipt["journal_count"],
        "boundaries": receipt["boundaries"],
    }

    return TestnetTransferResponse(
        proposal_id=proposal_id,
        execution=execution,
        ledger_receipt=ledger_receipt,
    )
