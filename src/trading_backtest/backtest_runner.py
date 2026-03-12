"""Core backtest execution logic."""

from datetime import datetime, timedelta
from typing import List, Tuple
import statistics

from trading_backtest.data import fetch_historical_data


def compute_returns(closes: List[float]) -> List[float]:
    """Compute returns from closing prices.

    Args:
        closes: List of closing prices

    Returns:
        List of daily returns as decimals
    """
    if len(closes) < 2:
        return []

    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            ret = (closes[i] - closes[i - 1]) / closes[i - 1]
            returns.append(ret)

    return returns


def get_price_for_month(
    symbol: str, month_date: datetime
) -> Tuple[bool, float]:
    """Fetch price for a symbol at month end.

    Args:
        symbol: Stock symbol
        month_date: Target month

    Returns:
        Tuple of (success, price)
    """
    try:
        stock_data = fetch_historical_data(
            symbol,
            start=(month_date - timedelta(days=1)).strftime("%Y-%m-%d"),
            end=month_date.strftime("%Y-%m-%d"),
        )

        if stock_data.closes:
            return True, stock_data.closes[-1]
        return False, 0.0
    except Exception:
        return False, 0.0


def get_historical_returns(
    symbol: str, month_date: datetime
) -> Tuple[bool, float, float]:
    """Get expected return and volatility for symbol.

    Args:
        symbol: Stock symbol
        month_date: Current month

    Returns:
        Tuple of (success, expected_return, volatility)
    """
    try:
        stock_data = fetch_historical_data(
            symbol,
            start=(month_date - timedelta(days=90)).strftime("%Y-%m-%d"),
            end=month_date.strftime("%Y-%m-%d"),
        )

        returns = compute_returns(stock_data.closes)
        if not returns or len(returns) < 2:
            return False, 0.0, 0.0

        exp_return = statistics.mean(returns)
        volatility = statistics.stdev(returns)
        return True, exp_return, volatility
    except Exception:
        return False, 0.0, 0.0


def next_month(current_date: datetime) -> datetime:
    """Get next month date.

    Args:
        current_date: Current month

    Returns:
        First day of next month
    """
    if current_date.month == 12:
        return datetime(current_date.year + 1, 1, 1)
    return datetime(current_date.year, current_date.month + 1, 1)
