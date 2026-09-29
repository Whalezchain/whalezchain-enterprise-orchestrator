# Live Market Data Corridor

Status: IMPLEMENTATION BRANCH / NOT LIVE

This service is the realtime market-data edge for Whalez-AI. It is deliberately separate from:

- trading order routing,
- external execution,
- custody,
- settlement,
- WhalezChain canonical state.

## Coverage

### Crypto

The worker supports live public market feeds from:

- Binance Spot global ticker plus optional per-symbol streams.
- Coinbase Advanced Trade ticker channels.
- Kraken Spot WebSocket v2 ticker channels.

The Binance global ticker path provides broad spot-universe top-of-market/rolling statistics. This is broad venue coverage, not a claim that every cryptocurrency or every venue globally is covered. Full depth/trade streams remain separately configurable per venue and symbol.

### FX

The worker supports:

- OANDA v20 pricing stream for live bid/ask/liquidity on account-eligible instruments.
- Twelve Data exchange-rate polling as a rate-only fallback.

OANDA is the execution-grade FX market-data adapter in this implementation. When `MARKET_DATA_FX_ALL=true`, the service queries the configured OANDA account for its full tradeable `CURRENCY` instrument set and subscribes to those pairs; that set is account/jurisdiction dependent. Twelve Data fallback values are explicitly marked LIVE_RATE_ONLY and must not be used as execution prices.

## Canonical quote fields

Every quote carries source, venue, asset class, symbol, bid, ask, last/mid, timestamp, receive timestamp, optional sequence, status and stale-data threshold.

A stale quote is never silently promoted to live. Consumers receive a stale flag from the read API.

## Configuration

Use server-side environment variables only.

- MARKET_DATA_STORE_PATH
- MARKET_DATA_HOST
- MARKET_DATA_PORT
- MARKET_DATA_CRYPTO_SYMBOLS
- MARKET_DATA_COINBASE_SYMBOLS
- MARKET_DATA_KRAKEN_SYMBOLS
- MARKET_DATA_FX_SYMBOLS
- OANDA_ACCOUNT_ID
- OANDA_ACCESS_TOKEN
- OANDA_STREAM_URL
- TWELVE_DATA_API_KEY
- TWELVE_DATA_POLL_SECONDS

Provider credentials must never enter the browser or repository.

## Free/open alternatives

Free/public feeds are useful for development and validation, but production market-data rights and coverage are provider/license dependent. Binance, Coinbase and Kraken provide public crypto market-data websocket surfaces. OANDA requires a v20 trading account/token for its pricing stream. Twelve Data exposes both REST and WebSocket APIs with plan-dependent coverage and limits.

This service therefore uses explicit source adapters and keeps provider choice replaceable rather than baking a commercial feed into WhalezChain or DeltaAlpha.

## Operational rule

Market data is observation. It does not authorize execution and does not mutate WhalezChain economic state.

## Run

python -m services.realtime.market_data.run
