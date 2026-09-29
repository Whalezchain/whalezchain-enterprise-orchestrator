from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import MarketQuote


class MarketDataStore:
    """Durable latest-value store; never a trading or settlement ledger."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_quotes (
                    source_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    PRIMARY KEY (source_id, symbol)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_sources (
                    source_id TEXT PRIMARY KEY,
                    venue TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_event_at TEXT,
                    error TEXT
                )
                """
            )
            conn.commit()

    def put_quote(self, quote: MarketQuote) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_quotes
                    (source_id, venue, asset_class, symbol, payload, received_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, symbol) DO UPDATE SET
                    payload=excluded.payload,
                    received_at=excluded.received_at,
                    venue=excluded.venue,
                    asset_class=excluded.asset_class
                """,
                (
                    quote.source_id,
                    quote.venue,
                    quote.asset_class,
                    quote.symbol,
                    json.dumps(quote.to_dict(), sort_keys=True),
                    quote.received_at,
                ),
            )
            conn.commit()

    def set_source_status(
        self,
        source_id: str,
        *,
        venue: str,
        asset_class: str,
        transport: str,
        status: str,
        last_event_at: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_sources
                    (source_id, venue, asset_class, transport, status, last_event_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    venue=excluded.venue,
                    asset_class=excluded.asset_class,
                    transport=excluded.transport,
                    status=excluded.status,
                    last_event_at=excluded.last_event_at,
                    error=excluded.error
                """,
                (
                    source_id,
                    venue,
                    asset_class,
                    transport,
                    status,
                    last_event_at,
                    error,
                ),
            )
            conn.commit()

    def latest(
        self,
        symbol: str,
        *,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT payload FROM market_quotes WHERE symbol = ?"
        params: list[Any] = [symbol]
        if source_id:
            sql += " AND source_id = ?"
            params.append(source_id)
        sql += " ORDER BY source_id"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [json.loads(row["payload"]) for row in rows]

    def sources(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM market_sources ORDER BY source_id"
            ).fetchall()
        return [dict(row) for row in rows]
