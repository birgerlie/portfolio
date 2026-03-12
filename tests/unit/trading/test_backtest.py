"""Unit tests for backtesting framework."""

import pytest
from datetime import date, timedelta
from trading_backtest.backtest import Position, Backtester


class TestPosition:
    """Tests for Position class."""

    def test_position_creation(self):
        """Create a position with symbol, quantity, entry price, date."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=100.0,
            entry_date=date(2023, 1, 1),
        )
        assert pos.symbol == "AAPL"
        assert pos.quantity == 100
        assert pos.entry_price == 100.0
        assert pos.entry_date == date(2023, 1, 1)

    def test_position_market_value_at_entry(self):
        """Market value equals cost basis when at entry price."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=100.0,
            entry_date=date(2023, 1, 1),
        )
        pos.current_price = 100.0
        assert pos.market_value == 10000.0

    def test_position_market_value_at_higher_price(self):
        """Market value increases with price."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=100.0,
            entry_date=date(2023, 1, 1),
        )
        pos.current_price = 110.0
        assert pos.market_value == 11000.0

    def test_position_gain_positive(self):
        """Gain is positive when price increases."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=100.0,
            entry_date=date(2023, 1, 1),
        )
        pos.current_price = 110.0
        assert pos.gain == 1000.0

    def test_position_gain_negative(self):
        """Gain is negative when price decreases."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=100.0,
            entry_date=date(2023, 1, 1),
        )
        pos.current_price = 90.0
        assert pos.gain == -1000.0

    def test_position_return_pct_positive(self):
        """Return percentage is positive when price increases."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=100.0,
            entry_date=date(2023, 1, 1),
        )
        pos.current_price = 110.0
        assert abs(pos.return_pct - 0.10) < 0.0001

    def test_position_return_pct_negative(self):
        """Return percentage is negative when price decreases."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=100.0,
            entry_date=date(2023, 1, 1),
        )
        pos.current_price = 95.0
        assert abs(pos.return_pct - (-0.05)) < 0.0001


class TestBacktesterBasics:
    """Tests for basic Backtester functionality."""

    def test_backtester_creation(self):
        """Create backtester with initial capital."""
        bt = Backtester(initial_capital=100000.0)
        assert bt.initial_capital == 100000.0
        assert bt.cash == 100000.0
        assert len(bt.positions) == 0
        assert len(bt.trades) == 0

    def test_portfolio_value_cash_only(self):
        """Portfolio value equals cash when no positions."""
        bt = Backtester(initial_capital=100000.0)
        assert bt.portfolio_value == 100000.0

    def test_buy_single_stock(self):
        """Buy 100 shares reduces cash and creates position."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))

        assert len(bt.positions) == 1
        assert "AAPL" in bt.positions
        assert bt.positions["AAPL"].quantity == 100
        assert bt.cash == 90000.0
        assert len(bt.trades) == 1

    def test_buy_adds_to_existing_position(self):
        """Buying same stock adds to existing position."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.buy(symbol="AAPL", quantity=50, price=105.0, date=date(2023, 1, 2))

        assert bt.positions["AAPL"].quantity == 150
        assert bt.cash == 84750.0

    def test_buy_multiple_stocks(self):
        """Buy different stocks creates separate positions."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.buy(symbol="MSFT", quantity=50, price=200.0, date=date(2023, 1, 1))

        assert len(bt.positions) == 2
        assert "AAPL" in bt.positions
        assert "MSFT" in bt.positions

    def test_sell_reduces_position(self):
        """Sell reduces position quantity."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.sell(symbol="AAPL", quantity=50, price=110.0, date=date(2023, 1, 2))

        assert bt.positions["AAPL"].quantity == 50
        assert bt.cash == 95500.0

    def test_sell_closes_position(self):
        """Sell all shares removes position from dict."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.sell(symbol="AAPL", quantity=100, price=110.0, date=date(2023, 1, 2))

        assert "AAPL" not in bt.positions
        assert bt.cash == 101000.0


class TestBacktesterValuation:
    """Tests for portfolio valuation."""

    def test_portfolio_value_with_positions(self):
        """Portfolio value = cash + sum of position values."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.update_price(symbol="AAPL", price=110.0)

        # Cash: 90,000, Position: 100 * 110 = 11,000
        assert bt.portfolio_value == 101000.0

    def test_update_price_single_stock(self):
        """Update price changes position market value."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.update_price(symbol="AAPL", price=105.0)

        assert bt.positions["AAPL"].current_price == 105.0
        assert bt.portfolio_value == 100500.0

    def test_update_price_multiple_positions(self):
        """Update price on multiple positions."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.buy(symbol="MSFT", quantity=50, price=200.0, date=date(2023, 1, 1))

        bt.update_price(symbol="AAPL", price=110.0)
        bt.update_price(symbol="MSFT", price=210.0)

        # Cash: 90,000 - 10,000 = 80,000
        # AAPL: 100 * 110 = 11,000
        # MSFT: 50 * 210 = 10,500
        # Total: 101,500
        assert bt.portfolio_value == 101500.0

    def test_total_gain_no_positions(self):
        """Total gain is zero when no positions."""
        bt = Backtester(initial_capital=100000.0)
        assert bt.total_gain == 0.0

    def test_total_gain_with_gains(self):
        """Total gain sums all position gains."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.buy(symbol="MSFT", quantity=50, price=200.0, date=date(2023, 1, 1))
        bt.update_price(symbol="AAPL", price=110.0)
        bt.update_price(symbol="MSFT", price=210.0)

        # AAPL gain: 1000, MSFT gain: 500
        assert bt.total_gain == 1500.0


class TestBacktesterReturns:
    """Tests for return calculations."""

    def test_monthly_return_calculation(self):
        """Monthly return = (end - start) / start."""
        bt = Backtester(initial_capital=100000.0)
        returns = bt.calculate_monthly_returns([100000.0, 101000.0, 99990.0])

        # Month 1: (101000 - 100000) / 100000 = 0.01
        # Month 2: (99990 - 101000) / 101000 ≈ -0.00990
        assert len(returns) == 2
        assert abs(returns[0] - 0.01) < 0.0001
        assert abs(returns[1] - (-0.00990)) < 0.0001

    def test_monthly_return_single_month(self):
        """Single month return with two values."""
        bt = Backtester(initial_capital=100000.0)
        returns = bt.calculate_monthly_returns([100000.0, 110000.0])

        assert len(returns) == 1
        assert abs(returns[0] - 0.10) < 0.0001

    def test_monthly_return_empty_list(self):
        """Empty list returns empty list."""
        bt = Backtester(initial_capital=100000.0)
        returns = bt.calculate_monthly_returns([])

        assert returns == []

    def test_monthly_return_single_value(self):
        """Single value returns empty list."""
        bt = Backtester(initial_capital=100000.0)
        returns = bt.calculate_monthly_returns([100000.0])

        assert returns == []


class TestBacktesterMetrics:
    """Tests for performance metrics."""

    def test_sharpe_ratio_calculation(self):
        """Sharpe ratio = mean(returns) / std(returns)."""
        bt = Backtester(initial_capital=100000.0)
        returns = [0.01, 0.02, 0.015, 0.005, 0.01]

        sharpe = bt.calculate_sharpe_ratio(returns)

        # Mean: 0.012
        # Std: ~0.00570
        # Sharpe: ~2.105
        assert sharpe > 0
        assert abs(sharpe - 2.105) < 0.1

    def test_sharpe_ratio_empty_returns(self):
        """Empty returns list returns 0."""
        bt = Backtester(initial_capital=100000.0)
        sharpe = bt.calculate_sharpe_ratio([])

        assert sharpe == 0.0

    def test_sharpe_ratio_single_return(self):
        """Single return has zero std, undefined sharpe."""
        bt = Backtester(initial_capital=100000.0)
        sharpe = bt.calculate_sharpe_ratio([0.01])

        # std = 0, so sharpe = 0
        assert sharpe == 0.0

    def test_max_drawdown_no_drawdown(self):
        """Monotonic increasing values have zero drawdown."""
        bt = Backtester(initial_capital=100000.0)
        values = [100000.0, 101000.0, 102000.0, 103000.0]

        dd = bt.calculate_max_drawdown(values)

        assert dd == 0.0

    def test_max_drawdown_with_drawdown(self):
        """Drawdown is peak-to-trough decline."""
        bt = Backtester(initial_capital=100000.0)
        values = [100000.0, 110000.0, 99000.0, 105000.0]

        dd = bt.calculate_max_drawdown(values)

        # Peak: 110000, Trough: 99000
        # Drawdown: (110000 - 99000) / 110000 ≈ 0.1
        assert abs(dd - 0.1) < 0.0001

    def test_max_drawdown_multiple_peaks(self):
        """Find largest drawdown across multiple peaks."""
        bt = Backtester(initial_capital=100000.0)
        values = [100000.0, 120000.0, 100000.0, 115000.0, 95000.0]

        dd = bt.calculate_max_drawdown(values)

        # Peak: 120000, Trough: 95000 = 20.83%
        assert dd > 0.15
        assert dd < 0.25

    def test_max_drawdown_empty_values(self):
        """Empty values list returns 0."""
        bt = Backtester(initial_capital=100000.0)
        dd = bt.calculate_max_drawdown([])

        assert dd == 0.0

    def test_max_drawdown_single_value(self):
        """Single value has zero drawdown."""
        bt = Backtester(initial_capital=100000.0)
        dd = bt.calculate_max_drawdown([100000.0])

        assert dd == 0.0


class TestBacktesterPortfolioTracking:
    """Tests for portfolio tracking integration."""

    def test_portfolio_tracking_scenario(self):
        """Buy 100 AAPL @ $100, price → $110, verify $101K portfolio value."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.update_price(symbol="AAPL", price=110.0)

        assert bt.portfolio_value == 101000.0
        assert bt.positions["AAPL"].return_pct == 0.10
        assert bt.total_gain == 1000.0

    def test_portfolio_return_calculation(self):
        """$100K → $110K = 10% return."""
        bt = Backtester(initial_capital=100000.0)
        returns = bt.calculate_monthly_returns([100000.0, 110000.0])

        assert abs(returns[0] - 0.10) < 0.0001

    def test_multiple_positions_tracking(self):
        """Track multiple stocks with different gains."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.buy(symbol="MSFT", quantity=50, price=200.0, date=date(2023, 1, 1))
        bt.update_price(symbol="AAPL", price=110.0)
        bt.update_price(symbol="MSFT", price=220.0)

        assert bt.positions["AAPL"].gain == 1000.0
        assert bt.positions["MSFT"].gain == 1000.0
        assert bt.total_gain == 2000.0
        assert bt.portfolio_value == 102000.0
