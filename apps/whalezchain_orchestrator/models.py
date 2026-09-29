from pydantic import BaseModel
from typing import Dict, Any


class TestnetTransferRequest(BaseModel):
    from_account: str
    to_account: str
    asset_symbol: str
    amount: str
    intent_id: str | None = None


class ExecutionReceipt(BaseModel):
    execution_id: str
    status: str
    state_root: str
    receipt_hash: str
    transaction: Dict[str, Any]


class TestnetTransferResponse(BaseModel):
    proposal_id: str
    execution: ExecutionReceipt
    ledger_receipt: Dict[str, Any]
