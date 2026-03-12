"""End-to-end tests for data ingestion."""

from trading_backtest.data import (
    fetch_sp500_symbols,
    fetch_historical_data,
)


def test_fetch_sp500_historical_data():
    """Fetch first 10 S&P 500 symbols for 2023, verify data completeness."""
    symbols = fetch_sp500_symbols()
    first_10 = symbols[:10]

    assert len(first_10) == 10

    for symbol in first_10:
        data = fetch_historical_data(symbol, start="2023-01-01", end="2023-12-31")

        # Verify all OHLCV data is present
        assert data.symbol == symbol
        assert len(data.dates) > 0
        assert len(data.dates) == len(data.closes)
        assert len(data.dates) == len(data.opens)
        assert len(data.dates) == len(data.highs)
        assert len(data.dates) == len(data.lows)
        assert len(data.dates) == len(data.volumes)

        # Verify data integrity (basic sanity checks)
        for i, _ in enumerate(data.dates):
            assert data.lows[i] <= data.opens[i] <= data.highs[i]
            assert data.lows[i] <= data.closes[i] <= data.highs[i]
