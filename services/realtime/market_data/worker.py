from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from typing import Awaitable, Callable

from .adapters import (
    stream_binance_quotes,
    stream_coinbase_quotes,
    stream_kraken_quotes,
    stream_oanda_quotes,
    stream_twelvedata_quotes,
)
from .models import MarketQuote
from .store import MarketDataStore


def _csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


async def _consume(
    store: MarketDataStore,
    source_id: str,
    venue: str,
    asset_class: str,
    stream_factory: Callable[[], Awaitable],
) -> None:
    while True:
        try:
            store.set_source_status(
                source_id,
                venue=venue,
                asset_class=asset_class,
                transport="websocket_or_http_stream",
                status="CONNECTING",
            )
            stream = stream_factory()
            async for quote in stream:
                if not isinstance(quote, MarketQuote):
                    continue
                store.put_quote(quote)
                store.set_source_status(
                    source_id,
                    venue=venue,
                    asset_class=asset_class,
                    transport="websocket_or_http_stream",
                    status="LIVE",
                    last_event_at=quote.received_at,
                    error=None,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            store.set_source_status(
                source_id,
                venue=venue,
                asset_class=asset_class,
                transport="websocket_or_http_stream",
                status="DEGRADED",
                error=str(exc),
            )
            await asyncio.sleep(3)


async def run_workers(store: MarketDataStore) -> None:
    crypto_symbols = _csv(
        "MARKET_DATA_CRYPTO_SYMBOLS",
        "BTC/USD,ETH/USD",
    )
    coinbase_symbols = _csv(
        "MARKET_DATA_COINBASE_SYMBOLS",
        "BTC-USD,ETH-USD",
    )
    kraken_symbols = _csv(
        "MARKET_DATA_KRAKEN_SYMBOLS",
        "BTC/USD,ETH/USD",
    )
    fx_symbols = _csv(
        "MARKET_DATA_FX_SYMBOLS",
        "EUR/USD,GBP/USD,USD/JPY,USD/CHF,AUD/USD,USD/CAD,NZD/USD,USD/NGN",
    )

    tasks: list[asyncio.Task] = [
        asyncio.create_task(
            _consume(
                store,
                "binance.spot",
                "BINANCE",
                "crypto",
                lambda: stream_binance_quotes(
                    symbols=crypto_symbols,
                    include_global_ticker=True,
                ),
            )
        )
    ]

    if coinbase_symbols:
        tasks.append(
            asyncio.create_task(
                _consume(
                    store,
                    "coinbase.advanced",
                    "COINBASE",
                    "crypto",
                    lambda: stream_coinbase_quotes(coinbase_symbols),
                )
            )
        )

    if kraken_symbols:
        tasks.append(
            asyncio.create_task(
                _consume(
                    store,
                    "kraken.spot",
                    "KRAKEN",
                    "crypto",
                    lambda: stream_kraken_quotes(kraken_symbols),
                )
            )
        )

    if os.getenv("OANDA_ACCESS_TOKEN") and os.getenv("OANDA_ACCOUNT_ID"):
        tasks.append(
            asyncio.create_task(
                _consume(
                    store,
                    "oanda.v20",
                    "OANDA",
                    "fx",
                    lambda: stream_oanda_quotes(fx_symbols),
                )
            )
        )

    if os.getenv("TWELVE_DATA_API_KEY"):
        tasks.append(
            asyncio.create_task(
                _consume(
                    store,
                    "twelvedata.exchange_rate",
                    "TWELVE_DATA",
                    "fx",
                    lambda: stream_twelvedata_quotes(fx_symbols),
                )
            )
        )

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
