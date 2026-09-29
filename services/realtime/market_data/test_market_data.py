from decimal import Decimal
from pathlib import Path

from .models import MarketQuote
from .store import MarketDataStore


def test_quote_mid_and_spread():
    quote = MarketQuote(
        source_id="test.source",
        venue="TEST",
        asset_class="fx",
        symbol="EUR/USD",
        base_asset="EUR",
        quote_asset="USD",
        bid=Decimal("1.1000"),
        ask=Decimal("1.1002"),
        last=Decimal("1.1001"),
        timestamp="2026-09-29T00:00:00+00:00",
        received_at="2026-09-29T00:00:00+00:00",
    )
    assert quote.mid == Decimal("1.1001")
    assert quote.spread == Decimal("0.0002")


def test_store_round_trip(tmp_path: Path):
    store = MarketDataStore(tmp_path / "market.sqlite3")
    quote = MarketQuote(
        source_id="test.source",
        venue="TEST",
        asset_class="crypto",
        symbol="BTC/USD",
        base_asset="BTC",
        quote_asset="USD",
        bid=Decimal("100.00"),
        ask=Decimal("100.10"),
        last=Decimal("100.05"),
        timestamp="2026-09-29T00:00:00+00:00",
        received_at="2026-09-29T00:00:00+00:00",
    )
    store.put_quote(quote)
    rows = store.latest("BTC/USD")
    assert len(rows) == 1
    assert rows[0]["mid"] == "100.05"
