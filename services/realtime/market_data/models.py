from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class MarketSource:
    source_id: str
    venue: str
    asset_class: str
    transport: str
    status: str = "UNKNOWN"


@dataclass(frozen=True)
class MarketInstrument:
    symbol: str
    base_asset: str
    quote_asset: str
    asset_class: str
    venue: str
    status: str = "UNKNOWN"
    tradeable: bool | None = None


@dataclass(frozen=True)
class MarketQuote:
    source_id: str
    venue: str
    asset_class: str
    symbol: str
    base_asset: str
    quote_asset: str
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    timestamp: str
    received_at: str
    sequence: int | None = None
    status: str = "LIVE"
    stale_after_ms: int = 5000
    metadata: dict[str, Any] | None = None

    @property
    def mid(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / Decimal("2")
        return self.last

    @property
    def spread(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "venue": self.venue,
            "asset_class": self.asset_class,
            "symbol": self.symbol,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "bid": str(self.bid) if self.bid is not None else None,
            "ask": str(self.ask) if self.ask is not None else None,
            "last": str(self.last) if self.last is not None else None,
            "mid": str(self.mid) if self.mid is not None else None,
            "spread": str(self.spread) if self.spread is not None else None,
            "timestamp": self.timestamp,
            "received_at": self.received_at,
            "sequence": self.sequence,
            "status": self.status,
            "stale_after_ms": self.stale_after_ms,
            "metadata": self.metadata or {},
        }
