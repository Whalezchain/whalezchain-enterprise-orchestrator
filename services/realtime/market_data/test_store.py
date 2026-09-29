from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from services.realtime.market_data.models import MarketQuote
from services.realtime.market_data.store import MarketDataStore


def test_store_round_trip_and_latest_filter(tmp_path: Path):
    store = MarketDataStore(tmp_path / "market.db")
    quote = MarketQuote(
        source_id="test.source",
        venue="TEST",
        asset_class="crypto",
        symbol="BTC/USD",
        base_asset="BTC",
        quote_asset="USD",
        bid=Decimal("100.00"),
        ask=Decimal("101.00"),
        last=Decimal("100.50"),
        timestamp=datetime.now(timezone.utc).isoformat(),
        received_at=datetime.now(timezone.utc).isoformat(),
    )
    store.put_quote(quote)

    rows = store.latest("BTC/USD")
    assert len(rows) == 1
    assert rows[0]["mid"] == "100.50"
    assert rows[0]["spread"] == "1.00"

    assert store.latest("ETH/USD") == []


def test_store_tracks_source_health(tmp_path: Path):
    store = MarketDataStore(tmp_path / "market.db")
    store.set_source_status(
        "oanda.v20",
        venue="OANDA",
        asset_class="fx",
        transport="websocket_or_http_stream",
        status="LIVE",
        last_event_at="2026-09-29T00:00:00+00:00",
    )

    sources = store.sources()
    assert sources[0]["source_id"] == "oanda.v20"
    assert sources[0]["status"] == "LIVE"
