"""Tests for QuoteAggregator — windowed quote batching."""
import threading
import time
from datetime import datetime, timezone

import pytest

from fund.quote_aggregator import QuoteAggregator


def ts(offset: float = 0.0) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestRecordAndFlushSingleSymbol:
    def test_flush_returns_symbol_data(self):
        agg = QuoteAggregator()
        agg.record("AAPL", bid=150.00, ask=150.10, timestamp=ts())
        result = agg.flush()
        assert "AAPL" in result

    def test_latest_bid_ask(self):
        agg = QuoteAggregator()
        agg.record("AAPL", bid=150.00, ask=150.10, timestamp=ts())
        agg.record("AAPL", bid=150.05, ask=150.15, timestamp=ts())
        result = agg.flush()
        assert result["AAPL"]["latest_bid"] == pytest.approx(150.05)
        assert result["AAPL"]["latest_ask"] == pytest.approx(150.15)

    def test_quote_count_single(self):
        agg = QuoteAggregator()
        agg.record("AAPL", bid=100.0, ask=100.1, timestamp=ts())
        result = agg.flush()
        assert result["AAPL"]["quote_count"] == 1


class TestSpreadCalculation:
    def test_mean_spread_two_quotes(self):
        """Two quotes with spreads 0.20 and 0.40 → mean 0.30."""
        agg = QuoteAggregator()
        agg.record("MSFT", bid=300.00, ask=300.20, timestamp=ts())
        agg.record("MSFT", bid=300.00, ask=300.40, timestamp=ts())
        result = agg.flush()
        assert result["MSFT"]["mean_spread"] == pytest.approx(0.30)

    def test_min_spread(self):
        agg = QuoteAggregator()
        agg.record("MSFT", bid=300.00, ask=300.20, timestamp=ts())
        agg.record("MSFT", bid=300.00, ask=300.40, timestamp=ts())
        result = agg.flush()
        assert result["MSFT"]["min_spread"] == pytest.approx(0.20)

    def test_max_spread(self):
        agg = QuoteAggregator()
        agg.record("MSFT", bid=300.00, ask=300.20, timestamp=ts())
        agg.record("MSFT", bid=300.00, ask=300.40, timestamp=ts())
        result = agg.flush()
        assert result["MSFT"]["max_spread"] == pytest.approx(0.40)

    def test_single_quote_spread_stats_equal(self):
        agg = QuoteAggregator()
        agg.record("TSLA", bid=200.00, ask=200.50, timestamp=ts())
        result = agg.flush()
        assert result["TSLA"]["mean_spread"] == pytest.approx(0.50)
        assert result["TSLA"]["min_spread"] == pytest.approx(0.50)
        assert result["TSLA"]["max_spread"] == pytest.approx(0.50)


class TestFlushClears:
    def test_second_flush_empty(self):
        agg = QuoteAggregator()
        agg.record("AAPL", bid=150.0, ask=150.1, timestamp=ts())
        agg.flush()
        result = agg.flush()
        assert result == {}

    def test_symbols_empty_after_flush(self):
        agg = QuoteAggregator()
        agg.record("AAPL", bid=150.0, ask=150.1, timestamp=ts())
        agg.flush()
        assert agg.symbols() == []


class TestMultipleSymbols:
    def test_multiple_symbols_returned(self):
        agg = QuoteAggregator()
        agg.record("AAPL", bid=150.0, ask=150.1, timestamp=ts())
        agg.record("GOOG", bid=2800.0, ask=2800.5, timestamp=ts())
        agg.record("MSFT", bid=300.0, ask=300.2, timestamp=ts())
        result = agg.flush()
        assert set(result.keys()) == {"AAPL", "GOOG", "MSFT"}

    def test_symbols_method_lists_pending(self):
        agg = QuoteAggregator()
        agg.record("AAPL", bid=150.0, ask=150.1, timestamp=ts())
        agg.record("GOOG", bid=2800.0, ask=2800.5, timestamp=ts())
        assert set(agg.symbols()) == {"AAPL", "GOOG"}

    def test_independent_stats_per_symbol(self):
        agg = QuoteAggregator()
        agg.record("AAPL", bid=100.0, ask=100.1, timestamp=ts())
        agg.record("GOOG", bid=200.0, ask=200.4, timestamp=ts())
        result = agg.flush()
        assert result["AAPL"]["mean_spread"] == pytest.approx(0.10)
        assert result["GOOG"]["mean_spread"] == pytest.approx(0.40)


class TestQuoteCount:
    def test_quote_count_multiple(self):
        agg = QuoteAggregator()
        for i in range(5):
            agg.record("NVDA", bid=400.0 + i, ask=400.1 + i, timestamp=ts())
        result = agg.flush()
        assert result["NVDA"]["quote_count"] == 5


class TestThreadSafety:
    def test_three_writer_threads_no_exceptions(self):
        agg = QuoteAggregator()
        errors = []

        def writer(symbol: str, n: int):
            try:
                for i in range(n):
                    agg.record(symbol, bid=100.0 + i * 0.01, ask=100.1 + i * 0.01, timestamp=ts())
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("AAPL", 100)),
            threading.Thread(target=writer, args=("MSFT", 100)),
            threading.Thread(target=writer, args=("GOOG", 100)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        result = agg.flush()
        assert result["AAPL"]["quote_count"] == 100
        assert result["MSFT"]["quote_count"] == 100
        assert result["GOOG"]["quote_count"] == 100
