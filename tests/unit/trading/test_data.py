"""Unit tests for data ingestion layer."""

import pytest
from trading_backtest.data import (
    fetch_sp500_symbols,
    fetch_historical_data,
)
from trading_backtest.types import StockData


def test_fetch_sp500_constituents():
    """Verify S&P 500 list has 500+ symbols, including AAPL and MSFT."""
    symbols = fetch_sp500_symbols()
    assert len(symbols) >= 500
    assert "AAPL" in symbols
    assert "MSFT" in symbols


def test_fetch_historical_data_valid_symbol():
    """Fetch AAPL 2023 data, verify > 200 trading days."""
    data = fetch_historical_data("AAPL", start="2023-01-01", end="2023-12-31")

    assert isinstance(data, StockData)
    assert data.symbol == "AAPL"
    assert len(data.dates) > 200
    assert len(data.closes) == len(data.dates)
    assert len(data.volumes) == len(data.dates)
    assert len(data.opens) == len(data.dates)
    assert len(data.highs) == len(data.dates)
    assert len(data.lows) == len(data.dates)

    # Verify basic data validity
    for close in data.closes:
        assert close > 0


def test_fetch_historical_data_invalid_symbol():
    """Handle ValueError gracefully for invalid symbols."""
    with pytest.raises(ValueError):
        fetch_historical_data("INVALID_TICKER_XYZ", start="2023-01-01", end="2023-12-31")
