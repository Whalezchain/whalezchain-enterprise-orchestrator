This service provides a bus for real‑time market data, telemetry, and anomaly events.
In development, it may simulate events using mock publishers and subscribers.

## Live market data

The realtime subsystem now includes the provider-neutral live market-data corridor under `services/realtime/market_data`.

It is responsible for observation only. It does not authorize orders, perform custody, or mutate WhalezChain settlement state.

See `services/realtime/market_data/README.md` for provider coverage and production configuration.
