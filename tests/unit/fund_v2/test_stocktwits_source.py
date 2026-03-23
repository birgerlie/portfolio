"""StockTwits sentiment source — bull/bear ratio as observations."""
from unittest.mock import MagicMock, patch

import pytest

from fund_v2.sentiment.stocktwits import StockTwitsSentiment


def test_parse_sentiment_response():
    adapter = StockTwitsSentiment()
    response = {
        "symbol": {"symbol": "AAPL"},
        "sentiment": {"bullish": 120, "bearish": 30},
    }
    record = adapter.parse_sentiment(response)
    assert record.identity == "AAPL"
    assert record.data["bull_ratio"] == pytest.approx(0.8, abs=0.01)
    assert record.data["total_messages"] == 150


def test_parse_sentiment_handles_zero_messages():
    adapter = StockTwitsSentiment()
    response = {
        "symbol": {"symbol": "AAPL"},
        "sentiment": {"bullish": 0, "bearish": 0},
    }
    record = adapter.parse_sentiment(response)
    assert record.data["bull_ratio"] == 0.5


def test_bull_ratio_extremes():
    adapter = StockTwitsSentiment()
    response = {"symbol": {"symbol": "GME"}, "sentiment": {"bullish": 1000, "bearish": 10}}
    record = adapter.parse_sentiment(response)
    assert record.data["bull_ratio"] > 0.95

    response = {"symbol": {"symbol": "GME"}, "sentiment": {"bullish": 5, "bearish": 500}}
    record = adapter.parse_sentiment(response)
    assert record.data["bull_ratio"] < 0.05
