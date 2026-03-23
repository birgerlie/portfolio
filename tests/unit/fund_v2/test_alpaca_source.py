"""Alpaca source connector — converts WebSocket events to SourceRecords."""
import time
from unittest.mock import MagicMock

import pytest

from fund_v2.sources.alpaca import AlpacaSourceAdapter


def test_trade_to_source_record():
    adapter = AlpacaSourceAdapter(symbols=["AAPL", "NVDA"])
    trade = MagicMock(symbol="AAPL", price=150.0, size=100, timestamp=1711200000.0)
    record = adapter.trade_to_record(trade)
    assert record.source_name == "alpaca"
    assert record.collection == "trades"
    assert record.identity == "AAPL"
    assert record.data["price"] == 150.0
    assert record.data["size"] == 100


def test_quote_to_source_record():
    adapter = AlpacaSourceAdapter(symbols=["AAPL"])
    quote = MagicMock(symbol="AAPL", bid_price=149.9, ask_price=150.1, timestamp=1711200000.0)
    record = adapter.quote_to_record(quote)
    assert record.collection == "quotes"
    assert record.data["bid"] == 149.9
    assert record.data["ask"] == 150.1
    assert record.data["spread"] == pytest.approx(0.2, abs=0.01)


def test_fill_to_source_record():
    adapter = AlpacaSourceAdapter(symbols=["AAPL"])
    fill = MagicMock()
    fill.order = {"symbol": "AAPL", "side": "buy", "filled_qty": "10", "filled_avg_price": "150.0", "id": "ord-123"}
    fill.event = "fill"
    record = adapter.fill_to_record(fill)
    assert record.collection == "fills"
    assert record.data["side"] == "buy"
    assert record.data["filled_qty"] == 10.0


def test_idempotency_key_unique():
    adapter = AlpacaSourceAdapter(symbols=["AAPL"])
    trade1 = MagicMock(symbol="AAPL", price=150.0, size=100, timestamp=1711200000.0)
    trade2 = MagicMock(symbol="AAPL", price=150.0, size=100, timestamp=1711200001.0)
    r1 = adapter.trade_to_record(trade1)
    r2 = adapter.trade_to_record(trade2)
    assert r1.idempotency_key != r2.idempotency_key


def test_stale_trade_skipped():
    adapter = AlpacaSourceAdapter(symbols=["AAPL"], max_age_seconds=30)
    old_trade = MagicMock(symbol="AAPL", price=150.0, size=100, timestamp=time.time() - 60)
    record = adapter.trade_to_record(old_trade)
    assert record is None
