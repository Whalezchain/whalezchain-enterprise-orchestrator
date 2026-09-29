from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .bootstrap import initialize_runtime
from .models import (
    TestnetTransferRequest,
    TestnetTransferResponse,
)
from .services.execution_service import execute
from .asset_authority import asset_authority
from .asset_authority.assets import list_assets
from .mainnet.external_settlement import (
    ExternalSettlementError,
    prepare_external_settlement,
    finalize_external_settlement,
)


# Load canonical execution registrations before serving requests.
initialize_runtime()

app = FastAPI(
    title="Whalezchain Orchestrator"
)


@app.exception_handler(ValueError)
async def validation_error_handler(
    request: Request,
    exc: ValueError,
):
    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "error": "validation_error",
            "detail": str(exc),
        },
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "whalezchain-orchestrator",
    }


@app.get("/assets")
def assets():
    return {
        "status": "ok",
        "assets": list_assets(),
    }


@app.post(
    "/testnet/transfer",
    response_model=TestnetTransferResponse,
)
def testnet_transfer(
    request: TestnetTransferRequest,
):
    result = execute(
        from_account=request.from_account,
        to_account=request.to_account,
        asset_symbol=request.asset_symbol,
        amount=request.amount,
    )

    return TestnetTransferResponse(
        proposal_id=result["proposal_id"],
        execution=result["execution"],
        ledger_receipt=result["ledger_receipt"],
    )


@app.get("/debug/state")
def debug_state():
    from .whalezchain_testnet_engine.runtime import engine
    return engine.state()


@app.post("/mainnet/settlement/prepare")
def mainnet_settlement_prepare(payload: dict[str, Any]):
    try:
        return prepare_external_settlement(payload)
    except ExternalSettlementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/mainnet/settlement/finalize")
def mainnet_settlement_finalize(payload: dict[str, Any]):
    try:
        return finalize_external_settlement(payload)
    except ExternalSettlementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
