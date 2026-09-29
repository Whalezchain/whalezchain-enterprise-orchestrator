from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, AsyncIterator
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import MarketQuote


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _split_pair(symbol: str) -> tuple[str, str]:
    normalized = symbol.replace("-", "/").replace("_", "/")
    if "/" not in normalized:
        return normalized.upper(), ""
    base, quote_asset = normalized.split("/", 1)
    return base.upper(), quote_asset.upper()


async def _ws_iter(url: str, subscribe: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("python-package-websockets-required") from exc

    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps(subscribe))
        async for message in ws:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


async def stream_binance_quotes(
    *,
    symbols: list[str] | None = None,
    include_global_ticker: bool = True,
) -> AsyncIterator[MarketQuote]:
    """Binance Spot public market stream.

    Global 24h ticker packets cover the broad spot universe. Additional
    symbol streams can be configured separately when full depth/trades are
    needed.
    """
    if include_global_ticker:
        streams = ["!ticker@arr"]
    else:
        wanted = [s.replace("/", "").replace("-", "").lower() for s in (symbols or [])]
        streams = [f"{s}@ticker" for s in wanted]

    url = "wss://stream.binance.com:9443/stream?streams=" + quote("/".join(streams), safe="")
    async for packet in _ws_iter(url, {}):
        data = packet.get("data")
        if not isinstance(data, list):
            data = [data]

        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("s", "")).upper()
            if not symbol:
                continue
            quote_asset = ""
            base_asset = symbol
            for suffix in ("USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB", "EUR", "TRY"):
                if symbol.endswith(suffix) and len(symbol) > len(suffix):
                    base_asset = symbol[: -len(suffix)]
                    quote_asset = suffix
                    break
            yield MarketQuote(
                source_id="binance.spot",
                venue="BINANCE",
                asset_class="crypto",
                symbol=f"{base_asset}/{quote_asset}" if quote_asset else symbol,
                base_asset=base_asset,
                quote_asset=quote_asset,
                bid=_decimal(item.get("b")),
                ask=_decimal(item.get("a")),
                last=_decimal(item.get("c")),
                timestamp=datetime.fromtimestamp(
                    int(item.get("E", 0)) / 1000,
                    tz=timezone.utc,
                ).isoformat() if item.get("E") else _now(),
                received_at=_now(),
                sequence=int(item["u"]) if str(item.get("u", "")).isdigit() else None,
                metadata={
                    "raw_symbol": symbol,
                    "price_change_pct": item.get("P"),
                    "volume": item.get("v"),
                },
            )


async def stream_coinbase_quotes(
    symbols: list[str],
    *,
    channel: str = "ticker",
) -> AsyncIterator[MarketQuote]:
    subscribe = {
        "type": "subscribe",
        "product_ids": symbols,
        "channel": channel,
    }
    async for payload in _ws_iter(
        "wss://advanced-trade-ws.coinbase.com",
        subscribe,
    ):
        events = payload.get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            tickers = event.get("tickers", []) if isinstance(event, dict) else []
            for ticker in tickers:
                if not isinstance(ticker, dict):
                    continue
                symbol = str(ticker.get("product_id", "")).upper()
                base, quote_asset = _split_pair(symbol)
                yield MarketQuote(
                    source_id="coinbase.advanced",
                    venue="COINBASE",
                    asset_class="crypto",
                    symbol=f"{base}/{quote_asset}" if quote_asset else symbol,
                    base_asset=base,
                    quote_asset=quote_asset,
                    bid=_decimal(ticker.get("best_bid")),
                    ask=_decimal(ticker.get("best_ask")),
                    last=_decimal(ticker.get("price")),
                    timestamp=str(ticker.get("time") or _now()),
                    received_at=_now(),
                    sequence=None,
                    metadata={
                        "volume_24_h": ticker.get("volume_24_h"),
                        "low_24_h": ticker.get("low_24_h"),
                        "high_24_h": ticker.get("high_24_h"),
                    },
                )


async def stream_kraken_quotes(
    symbols: list[str],
) -> AsyncIterator[MarketQuote]:
    subscribe = {
        "method": "subscribe",
        "params": {
            "channel": "ticker",
            "symbol": symbols,
            "snapshot": True,
        },
    }
    async for payload in _ws_iter("wss://ws.kraken.com/v2", subscribe):
        if payload.get("channel") != "ticker":
            continue
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).upper()
            base, quote_asset = _split_pair(symbol)
            yield MarketQuote(
                source_id="kraken.spot",
                venue="KRAKEN",
                asset_class="crypto",
                symbol=f"{base}/{quote_asset}" if quote_asset else symbol,
                base_asset=base,
                quote_asset=quote_asset,
                bid=_decimal(item.get("bid")),
                ask=_decimal(item.get("ask")),
                last=_decimal(item.get("last")),
                timestamp=str(item.get("timestamp") or _now()),
                received_at=_now(),
                sequence=int(item["sequence"]) if str(item.get("sequence", "")).isdigit() else None,
                metadata={
                    "bid_qty": item.get("bid_qty"),
                    "ask_qty": item.get("ask_qty"),
                    "volume": item.get("volume"),
                },
            )


def _oanda_quote(payload: dict[str, Any]) -> MarketQuote | None:
    if payload.get("type") != "PRICE":
        return None
    symbol = str(payload.get("instrument", "")).upper().replace("_", "/")
    base, quote_asset = _split_pair(symbol)
    bids = payload.get("bids") or []
    asks = payload.get("asks") or []
    bid = _decimal(bids[0].get("price")) if bids and isinstance(bids[0], dict) else None
    ask = _decimal(asks[0].get("price")) if asks and isinstance(asks[0], dict) else None
    return MarketQuote(
        source_id="oanda.v20",
        venue="OANDA",
        asset_class="fx",
        symbol=f"{base}/{quote_asset}" if quote_asset else symbol,
        base_asset=base,
        quote_asset=quote_asset,
        bid=bid,
        ask=ask,
        last=None,
        timestamp=str(payload.get("time") or _now()),
        received_at=_now(),
        metadata={
            "tradeable": payload.get("tradeable"),
            "bid_liquidity": bids[0].get("liquidity") if bids and isinstance(bids[0], dict) else None,
            "ask_liquidity": asks[0].get("liquidity") if asks and isinstance(asks[0], dict) else None,
        },
    )


async def stream_oanda_quotes(
    symbols: list[str],
) -> AsyncIterator[MarketQuote]:
    account_id = os.getenv("OANDA_ACCOUNT_ID", "").strip()
    token = os.getenv("OANDA_ACCESS_TOKEN", "").strip()
    base_url = os.getenv(
        "OANDA_STREAM_URL",
        "https://stream-fxtrade.oanda.com/v3/accounts",
    ).rstrip("/")

    if not account_id or not token:
        raise RuntimeError("oanda_stream_not_configured")

    instrument_list = ",".join(s.replace("/", "_").upper() for s in symbols)
    url = (
        f"{base_url}/{account_id}/pricing/stream"
        f"?instruments={quote(instrument_list, safe=",")}"
    )

    def blocking_stream() -> list[dict[str, Any]]:
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept-Datetime-Format": "RFC3339",
            },
        )
        events: list[dict[str, Any]] = []
        with urlopen(req, timeout=30) as response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    events.append(item)
                if len(events) >= 32:
                    break
        return events

    while True:
        events = await asyncio.to_thread(blocking_stream)
        for event in events:
            quote_event = _oanda_quote(event)
            if quote_event is not None:
                yield quote_event


async def stream_twelvedata_quotes(
    symbols: list[str],
) -> AsyncIterator[MarketQuote]:
    """Rate-only fallback.

    Twelve Data exposes a unified REST/WebSocket market-data API, but the
    public WebSocket quote payload does not provide bid/ask. This adapter is
    therefore deliberately marked as a rate source, not execution pricing.
    """
    api_key = os.getenv("TWELVE_DATA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("twelvedata_not_configured")

    interval_seconds = float(os.getenv("TWELVE_DATA_POLL_SECONDS", "5"))
    while True:
        for symbol in symbols:
            url = (
                "https://api.twelvedata.com/exchange_rate"
                f"?symbol={quote(symbol, safe='/')}&apikey={quote(api_key)}"
            )
            req = Request(url, headers={"Accept": "application/json"})
            try:
                raw = await asyncio.to_thread(
                    lambda: urlopen(req, timeout=10).read().decode("utf-8")
                )
                payload = json.loads(raw)
            except Exception:
                continue

            rate = _decimal(payload.get("rate"))
            if rate is None:
                continue
            base, quote_asset = _split_pair(symbol)
            yield MarketQuote(
                source_id="twelvedata.exchange_rate",
                venue="TWELVE_DATA",
                asset_class="fx" if len(base) == 3 and len(quote_asset) == 3 else "crypto",
                symbol=f"{base}/{quote_asset}",
                base_asset=base,
                quote_asset=quote_asset,
                bid=None,
                ask=None,
                last=rate,
                timestamp=_now(),
                received_at=_now(),
                status="LIVE_RATE_ONLY",
                metadata={"execution_grade": False},
            )
        await asyncio.sleep(interval_seconds)
