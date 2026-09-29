from __future__ import annotations

import asyncio
import os
from pathlib import Path

import uvicorn

from .app import app
from .store import MarketDataStore
from .worker import run_workers


def store_path() -> str:
    return os.getenv(
        "MARKET_DATA_STORE_PATH",
        str(Path("data") / "market_data.sqlite3"),
    )


async def main() -> None:
    store = MarketDataStore(store_path())
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=os.getenv("MARKET_DATA_HOST", "127.0.0.1"),
            port=int(os.getenv("MARKET_DATA_PORT", "8870")),
            log_level="info",
        )
    )
    worker = asyncio.create_task(run_workers(store))
    try:
        await asyncio.gather(server.serve(), worker)
    finally:
        worker.cancel()


if __name__ == "__main__":
    asyncio.run(main())
