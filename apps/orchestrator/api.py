from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["v1"])


@router.get("/health")
def v1_health() -> dict[str, object]:
    return {
        "service": "whalezchain-enterprise-orchestrator",
        "api": "v1",
        "status": "ok",
        "execution_authority": "internal",
        "mutation": False,
    }


@router.get("/capabilities")
def capabilities() -> dict[str, object]:
    return {
        "capabilities": [
            {"id": "orchestration.dispatch", "version": "1.0", "status": "available"},
            {"id": "whalezchain.settlement", "version": "1.0", "status": "gated", "mutation": True},
            {"id": "provenance.anchor", "version": "1.0", "status": "gated", "mutation": True},
        ],
        "note": "Capability declaration only. Gated capabilities are not enabled merely by this endpoint.",
    }
