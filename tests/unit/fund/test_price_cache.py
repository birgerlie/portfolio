"""Tests for PriceCache — thread-safe price store."""

import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from fund.price_cache import PriceCache, PriceEntry


# ---------------------------------------------------------------------------
# PriceEntry tests
# ---------------------------------------------------------------------------

class TestPriceEntry:
    def _make_entry(self, **kwargs):
        defaults = dict(
            symbol="AAPL",
            price=Decimal("150.00"),
            bid=Decimal("149.95"),
            ask=Decimal("150.05"),
            spread=Decimal("0.10"),
            vwap=Decimal("150.00"),
            trade_count=1,
            total_volume=Decimal("100"),
            last_trade_ts=datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc),
            last_quote_ts=datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc),
            prev_price=None,
        )
        defaults.update(kwargs)
        return PriceEntry(**defaults)

    def test_is_stale_when_old(self):
        old_ts = datetime(2026, 3, 16, 9, 0, 0, tzinfo=timezone.utc)
        entry = self._make_entry(last_trade_ts=old_ts, last_quote_ts=old_ts)
        # 3600 seconds old, max_age 60 → stale
        assert entry.is_stale(max_age_seconds=60, now=datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc))

    def test_is_not_stale_when_fresh(self):
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        entry = self._make_entry(last_trade_ts=ts, last_quote_ts=ts)
        now = datetime(2026, 3, 16, 10, 0, 30, tzinfo=timezone.utc)
        assert not entry.is_stale(max_age_seconds=60, now=now)

    def test_is_stale_uses_most_recent_timestamp(self):
        trade_ts = datetime(2026, 3, 16, 10, 0, 50, tzinfo=timezone.utc)
        quote_ts = datetime(2026, 3, 16, 9, 0, 0, tzinfo=timezone.utc)
        entry = self._make_entry(last_trade_ts=trade_ts, last_quote_ts=quote_ts)
        now = datetime(2026, 3, 16, 10, 1, 0, tzinfo=timezone.utc)
        # Most recent is trade_ts (10 seconds ago) → not stale
        assert not entry.is_stale(max_age_seconds=60, now=now)

    def test_price_return_none_when_no_prev(self):
        entry = self._make_entry(prev_price=None)
        assert entry.price_return is None

    def test_price_return_computed_correctly(self):
        entry = self._make_entry(price=Decimal("110"), prev_price=Decimal("100"))
        assert entry.price_return == pytest.approx(0.10)

    def test_price_return_negative(self):
        entry = self._make_entry(price=Decimal("90"), prev_price=Decimal("100"))
        assert entry.price_return == pytest.approx(-0.10)


# ---------------------------------------------------------------------------
# PriceCache basic operations
# ---------------------------------------------------------------------------

class TestPriceCacheBasic:
    def test_get_unknown_symbol_returns_none(self):
        cache = PriceCache()
        assert cache.get("AAPL") is None

    def test_update_trade_creates_entry(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", price=Decimal("150"), size=Decimal("10"), timestamp=ts)
        entry = cache.get("AAPL")
        assert entry is not None
        assert entry.symbol == "AAPL"
        assert entry.price == Decimal("150")
        assert entry.trade_count == 1

    def test_update_trade_multiple_updates_increments_count(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        cache.update_trade("AAPL", Decimal("152"), Decimal("20"), ts)
        entry = cache.get("AAPL")
        assert entry.trade_count == 2

    def test_update_trade_tracks_prev_price(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        cache.update_trade("AAPL", Decimal("155"), Decimal("5"), ts)
        entry = cache.get("AAPL")
        assert entry.prev_price == Decimal("150")
        assert entry.price == Decimal("155")

    def test_vwap_single_trade(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        entry = cache.get("AAPL")
        assert entry.vwap == Decimal("150")

    def test_vwap_multiple_trades(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("100"), Decimal("10"), ts)
        cache.update_trade("AAPL", Decimal("200"), Decimal("10"), ts)
        entry = cache.get("AAPL")
        assert entry.vwap == Decimal("150")

    def test_vwap_weighted_correctly(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("100"), Decimal("30"), ts)
        cache.update_trade("AAPL", Decimal("200"), Decimal("10"), ts)
        # vwap = (100*30 + 200*10) / 40 = (3000 + 2000) / 40 = 125
        entry = cache.get("AAPL")
        assert entry.vwap == Decimal("125")

    def test_total_volume_accumulates(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        cache.update_trade("AAPL", Decimal("151"), Decimal("20"), ts)
        entry = cache.get("AAPL")
        assert entry.total_volume == Decimal("30")

    def test_update_quote_creates_entry(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_quote("MSFT", bid=Decimal("299"), ask=Decimal("301"), timestamp=ts)
        entry = cache.get("MSFT")
        assert entry is not None
        assert entry.bid == Decimal("299")
        assert entry.ask == Decimal("301")
        assert entry.spread == Decimal("2")

    def test_update_quote_spread_computed(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_quote("TSLA", bid=Decimal("199.50"), ask=Decimal("200.50"), timestamp=ts)
        entry = cache.get("TSLA")
        assert entry.spread == Decimal("1.00")

    def test_get_returns_copy(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        entry1 = cache.get("AAPL")
        entry2 = cache.get("AAPL")
        assert entry1 is not entry2


# ---------------------------------------------------------------------------
# PriceCache collection methods
# ---------------------------------------------------------------------------

class TestPriceCacheCollection:
    def test_all_symbols_empty(self):
        cache = PriceCache()
        assert cache.all_symbols() == []

    def test_all_symbols_after_updates(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        cache.update_quote("MSFT", Decimal("299"), Decimal("301"), ts)
        symbols = cache.all_symbols()
        assert set(symbols) == {"AAPL", "MSFT"}

    def test_snapshot_returns_all_copies(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        cache.update_trade("GOOG", Decimal("2800"), Decimal("5"), ts)
        snap = cache.snapshot()
        assert set(snap.keys()) == {"AAPL", "GOOG"}
        assert snap["AAPL"].symbol == "AAPL"
        assert snap["GOOG"].symbol == "GOOG"

    def test_snapshot_entries_are_copies(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        snap = cache.snapshot()
        assert snap["AAPL"] is not cache.get("AAPL")


# ---------------------------------------------------------------------------
# relative_return
# ---------------------------------------------------------------------------

class TestRelativeReturn:
    def test_relative_return_none_when_symbol_missing(self):
        cache = PriceCache()
        assert cache.relative_return("AAPL", "SPY") is None

    def test_relative_return_none_when_benchmark_missing(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("110"), Decimal("10"), ts)
        cache.update_trade("AAPL", Decimal("110"), Decimal("10"), ts)  # need prev_price
        assert cache.relative_return("AAPL", "SPY") is None

    def test_relative_return_computed(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        # AAPL: prev=100, curr=110 → return = 0.10
        cache.update_trade("AAPL", Decimal("100"), Decimal("10"), ts)
        cache.update_trade("AAPL", Decimal("110"), Decimal("10"), ts)
        # SPY: prev=400, curr=404 → return = 0.01
        cache.update_trade("SPY", Decimal("400"), Decimal("10"), ts)
        cache.update_trade("SPY", Decimal("404"), Decimal("10"), ts)
        rel = cache.relative_return("AAPL", "SPY")
        assert rel == pytest.approx(0.09)  # 0.10 - 0.01

    def test_relative_return_none_when_no_prev_price(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        cache.update_trade("AAPL", Decimal("150"), Decimal("10"), ts)
        cache.update_trade("SPY", Decimal("400"), Decimal("10"), ts)
        # Both have only one trade → no prev_price → price_return is None
        assert cache.relative_return("AAPL", "SPY") is None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestPriceCacheThreadSafety:
    def test_concurrent_updates_dont_raise(self):
        cache = PriceCache()
        errors = []

        def writer(symbol, price_start):
            ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
            for i in range(100):
                try:
                    cache.update_trade(symbol, Decimal(str(price_start + i)), Decimal("1"), ts)
                except Exception as e:
                    errors.append(e)

        def reader(symbol):
            for _ in range(100):
                try:
                    cache.get(symbol)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("AAPL", 100)),
            threading.Thread(target=writer, args=("MSFT", 200)),
            threading.Thread(target=reader, args=("AAPL",)),
            threading.Thread(target=reader, args=("MSFT",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_concurrent_snapshot_is_consistent(self):
        cache = PriceCache()
        ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
        for sym in ["AAPL", "MSFT", "GOOG"]:
            cache.update_trade(sym, Decimal("100"), Decimal("10"), ts)

        snapshots = []
        errors = []

        def take_snapshot():
            try:
                snapshots.append(cache.snapshot())
            except Exception as e:
                errors.append(e)

        def do_updates():
            for i in range(50):
                try:
                    cache.update_trade("AAPL", Decimal(str(150 + i)), Decimal("1"), ts)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=take_snapshot) for _ in range(10)]
        threads += [threading.Thread(target=do_updates)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(snapshots) == 10
        for snap in snapshots:
            assert set(snap.keys()) == {"AAPL", "MSFT", "GOOG"}
