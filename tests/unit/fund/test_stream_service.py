"""Tests for AlpacaStreamService."""

import asyncio
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fund.broker_types import AlpacaConfig, StreamConfig
from fund.price_cache import PriceCache
from fund.stream_service import AlpacaStreamService, StreamEvent


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_service(maxsize: int = 100) -> tuple[AlpacaStreamService, PriceCache, queue.Queue]:
    alpaca_config = AlpacaConfig(api_key="key", secret_key="secret", paper=True)
    stream_config = StreamConfig(
        portfolio_symbols=["AAPL", "MSFT"],
        reference_symbols=["SPY"],
        macro_proxies=["TLT"],
    )
    price_cache = PriceCache()
    event_queue: queue.Queue = queue.Queue(maxsize=maxsize)
    service = AlpacaStreamService(alpaca_config, stream_config, price_cache, event_queue)
    return service, price_cache, event_queue


def make_trade(symbol: str = "AAPL", price: float = 150.0, size: float = 10.0):
    trade = MagicMock()
    trade.symbol = symbol
    trade.price = price
    trade.size = size
    trade.timestamp = datetime(2026, 3, 16, 14, 30, 0, tzinfo=timezone.utc)
    return trade


def make_quote(symbol: str = "AAPL", bid: float = 149.9, ask: float = 150.1):
    quote = MagicMock()
    quote.symbol = symbol
    quote.bid_price = bid
    quote.ask_price = ask
    quote.timestamp = datetime(2026, 3, 16, 14, 30, 1, tzinfo=timezone.utc)
    return quote


# ---------------------------------------------------------------------------
# StreamEvent dataclass
# ---------------------------------------------------------------------------

class TestStreamEvent:
    def test_defaults(self):
        before = time.time()
        ev = StreamEvent(kind="trade", symbol="AAPL", data={"price": 100.0})
        after = time.time()
        assert ev.kind == "trade"
        assert ev.symbol == "AAPL"
        assert ev.data == {"price": 100.0}
        assert before <= ev.timestamp <= after

    def test_explicit_timestamp(self):
        ev = StreamEvent(kind="fill", symbol="TSLA", data={}, timestamp=1234567890.0)
        assert ev.timestamp == 1234567890.0


# ---------------------------------------------------------------------------
# Trade handler
# ---------------------------------------------------------------------------

class TestHandleTrade:
    def test_updates_price_cache(self):
        service, price_cache, _ = make_service()
        trade = make_trade("AAPL", 150.0, 10.0)
        service._handle_trade_sync(trade)
        entry = price_cache.get("AAPL")
        assert entry is not None
        assert entry.price == Decimal("150.0")
        assert entry.total_volume == Decimal("10.0")

    def test_posts_event_to_queue(self):
        service, _, event_queue = make_service()
        trade = make_trade("MSFT", 300.0, 5.0)
        service._handle_trade_sync(trade)
        assert not event_queue.empty()
        event = event_queue.get_nowait()
        assert event.kind == "trade"
        assert event.symbol == "MSFT"
        assert event.data["price"] == pytest.approx(300.0)
        assert event.data["size"] == pytest.approx(5.0)

    def test_multiple_trades_accumulate(self):
        service, price_cache, event_queue = make_service()
        service._handle_trade_sync(make_trade("AAPL", 100.0, 10.0))
        service._handle_trade_sync(make_trade("AAPL", 110.0, 5.0))
        entry = price_cache.get("AAPL")
        assert entry.trade_count == 2
        assert entry.total_volume == Decimal("15.0")
        assert event_queue.qsize() == 2


# ---------------------------------------------------------------------------
# Quote handler
# ---------------------------------------------------------------------------

class TestHandleQuote:
    def test_updates_price_cache(self):
        service, price_cache, _ = make_service()
        quote = make_quote("SPY", 440.0, 440.1)
        service._handle_quote_sync(quote)
        entry = price_cache.get("SPY")
        assert entry is not None
        assert entry.bid == Decimal("440.0")
        assert entry.ask == Decimal("440.1")
        assert entry.spread == Decimal("0.1")

    def test_posts_event_to_queue(self):
        service, _, event_queue = make_service()
        quote = make_quote("SPY", 440.0, 440.2)
        service._handle_quote_sync(quote)
        event = event_queue.get_nowait()
        assert event.kind == "quote"
        assert event.symbol == "SPY"
        assert event.data["bid"] == pytest.approx(440.0)
        assert event.data["ask"] == pytest.approx(440.2)


# ---------------------------------------------------------------------------
# Fill handler
# ---------------------------------------------------------------------------

class TestHandleFill:
    def test_posts_fill_event_from_dict(self):
        service, _, event_queue = make_service()
        fill_data = {"symbol": "TSLA", "qty": 3, "side": "buy"}
        service._handle_fill_sync(fill_data)
        event = event_queue.get_nowait()
        assert event.kind == "fill"
        assert event.symbol == "TSLA"
        assert event.data == fill_data

    def test_posts_fill_event_from_object(self):
        service, _, event_queue = make_service()
        fill_obj = MagicMock()
        fill_obj.symbol = "NVDA"
        fill_obj.__dict__ = {"symbol": "NVDA", "qty": 1}
        service._handle_fill_sync(fill_obj)
        event = event_queue.get_nowait()
        assert event.kind == "fill"
        assert event.symbol == "NVDA"


# ---------------------------------------------------------------------------
# Queue full / dropped_events
# ---------------------------------------------------------------------------

class TestDroppedEvents:
    def test_drops_when_queue_full(self):
        service, _, event_queue = make_service(maxsize=2)
        assert service.dropped_events == 0

        # Fill queue
        service._handle_trade_sync(make_trade("AAPL", 100.0, 1.0))
        service._handle_trade_sync(make_trade("AAPL", 101.0, 1.0))
        assert service.dropped_events == 0
        assert event_queue.full()

        # This one should be dropped
        service._handle_trade_sync(make_trade("AAPL", 102.0, 1.0))
        assert service.dropped_events == 1
        assert event_queue.qsize() == 2  # still only 2 items

    def test_multiple_drops_accumulate(self):
        # maxsize=1 so the first event fits, the rest are dropped
        service, _, _ = make_service(maxsize=1)
        for _ in range(6):
            service._handle_quote_sync(make_quote())
        assert service.dropped_events == 5


# ---------------------------------------------------------------------------
# subscribe_symbol / all_stream_symbols
# ---------------------------------------------------------------------------

class TestSubscribeSymbol:
    def test_all_stream_symbols_includes_config(self):
        service, _, _ = make_service()
        symbols = service.all_stream_symbols
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert "SPY" in symbols
        assert "TLT" in symbols

    def test_subscribe_adds_symbol(self):
        service, _, _ = make_service()
        service.subscribe_symbol("GOOG")
        assert "GOOG" in service.all_stream_symbols

    def test_subscribe_no_duplicates(self):
        service, _, _ = make_service()
        service.subscribe_symbol("AAPL")
        service.subscribe_symbol("AAPL")
        assert service.all_stream_symbols.count("AAPL") == 1

    def test_subscribe_new_symbol(self):
        service, _, _ = make_service()
        before = set(service.all_stream_symbols)
        service.subscribe_symbol("AMZN")
        after = set(service.all_stream_symbols)
        assert "AMZN" in after
        assert after - before == {"AMZN"}

    def test_all_stream_symbols_sorted(self):
        service, _, _ = make_service()
        symbols = service.all_stream_symbols
        assert symbols == sorted(symbols)


# ---------------------------------------------------------------------------
# is_running property
# ---------------------------------------------------------------------------

class TestIsRunning:
    def _make_running_service(self):
        """Return a service with _stream_main patched to sleep forever."""
        service, _, _ = make_service()

        async def fake_main():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                pass

        service._stream_main = fake_main
        return service

    def test_not_running_initially(self):
        service, _, _ = make_service()
        assert not service.is_running

    def test_running_after_start(self):
        service = self._make_running_service()
        service.start()
        time.sleep(0.05)
        assert service.is_running
        service.stop()

    def test_not_running_after_stop(self):
        service = self._make_running_service()
        service.start()
        time.sleep(0.05)
        service.stop()
        assert not service.is_running

    def test_start_idempotent(self):
        service = self._make_running_service()
        service.start()
        time.sleep(0.05)
        service.start()  # second call should be a no-op
        assert service.is_running
        service.stop()


# ---------------------------------------------------------------------------
# Thread safety for subscribe_symbol
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_subscribe(self):
        service, _, _ = make_service()
        symbols = [f"SYM{i}" for i in range(50)]

        def subscribe_all():
            for sym in symbols:
                service.subscribe_symbol(sym)

        threads = [threading.Thread(target=subscribe_all) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for sym in symbols:
            assert sym in service.all_stream_symbols
