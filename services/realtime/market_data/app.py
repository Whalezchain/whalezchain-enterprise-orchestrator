from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query

from .store import MarketDataStore


def _store() -> MarketDataStore:
    path = os.getenv("MARKET_DATA_STORE_PATH", str(Path("data") / "market_data.sqlite3"))
    return MarketDataStore(path)


def _is_stale(payload: dict[str, Any]) -> bool:
    try:
        received = datetime.fromisoformat(str(payload["received_at"]).replace("Z", "+00:00"))
    except Exception:
        return True

    age_ms = (
        datetime.now(timezone.utc) - received.astimezone(timezone.utc)
    ).total_seconds() * 1000

    return age_ms > int(payload.get("stale_after_ms", 5000))



def _require_token(token: str | None) -> None:
    expected = os.getenv("MARKET_DATA_RUNTIME_TOKEN", "").strip()
    if not expected or not token or not hmac.compare_digest(expected, token):
        raise HTTPException(status_code=401, detail="unauthorized")


app = FastAPI(title="Whalez-AI Live Market Data")


@app.get("/health")
def health() -> dict[str, Any]:
    sources = _store().sources()
    live = sum(1 for item in sources if item["status"] == "LIVE")
    degraded = sum(1 for item in sources if item["status"] == "DEGRADED")
    if degraded:
        status = "degraded"
    elif live > 0:
        status = "ok"
    else:
        status = "not_configured"

    return {
        "status": status,
        "service": "realtime-market-data",
        "live_sources": live,
        "degraded_sources": degraded,
    }


@app.get("/v1/market/sources")
def sources(x_whalez_market_data_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_whalez_market_data_token)
    return {"status": "ok", "sources": _store().sources()}


@app.get("/v1/market/quote")
def quote(
    symbol: str = Query(min_length=2),
    source_id: str | None = Query(default=None),
    x_whalez_market_data_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_whalez_market_data_token)
    rows = _store().latest(symbol.upper(), source_id=source_id)
    if not rows:
        raise HTTPException(status_code=404, detail="quote_not_available")

    return {
        "status": "ok",
        "symbol": symbol.upper(),
        "quotes": [{**row, "stale": _is_stale(row)} for row in rows],
    }
