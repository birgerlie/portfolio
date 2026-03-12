"""Trade execution logic."""

from datetime import datetime, timedelta
from typing import List

from trading_backtest.backtest import Backtester
from trading_backtest.backtest_runner import get_price_for_month
from trading_backtest.decision import StockAction, ActionType


def execute_trades(
    recommended: List[StockAction],
    backtester: Backtester,
    month_date: datetime,
    top_k: int,
) -> None:
    """Execute recommended trades via backtester.

    Args:
        recommended: List of recommended actions
        backtester: Backtester instance
        month_date: Current month for trade date
        top_k: Number of positions to allocate
    """
    trade_date = month_date.date()

    for action in recommended:
        if action.action_type != ActionType.BUY:
            continue

        success, price = get_price_for_month(action.symbol, month_date)

        if not success or price <= 0:
            continue

        position_value = backtester.portfolio_value / top_k
        quantity = position_value / price

        if backtester.cash >= position_value:
            backtester.buy(action.symbol, quantity, price, trade_date)


def update_portfolio_prices(
    backtester: Backtester, month_date: datetime
) -> None:
    """Update current prices for all positions.

    Args:
        backtester: Backtester instance
        month_date: Current month
    """
    for symbol in list(backtester.positions.keys()):
        success, current_price = get_price_for_month(
            symbol, month_date
        )

        if success and current_price > 0:
            backtester.update_price(symbol, current_price)
