"""E2E tests for backtesting framework."""

import pytest
from datetime import date, timedelta
from trading_backtest.backtest import Backtester


class TestBacktestFullCycle:
    """E2E tests for complete backtest scenarios."""

    def test_backtest_full_cycle_12_months(self):
        """12-month simulation with 2 stocks."""
        bt = Backtester(initial_capital=100000.0)
        portfolio_values = self._simulate_12_months(bt)

        # Verify portfolio state
        assert "AAPL" in bt.positions
        assert "MSFT" in bt.positions
        assert len(bt.trades) == 24

        # Verify metrics can be calculated
        monthly_returns = bt.calculate_monthly_returns(portfolio_values)
        assert len(monthly_returns) == 12

        sharpe = bt.calculate_sharpe_ratio(monthly_returns)
        assert sharpe >= 0

        max_dd = bt.calculate_max_drawdown(portfolio_values)
        assert max_dd >= 0

        # Portfolio should have grown
        assert bt.portfolio_value > 100000.0

    def _simulate_12_months(self, bt: Backtester) -> list:
        """Helper to simulate 12 months of trading."""
        portfolio_values = [100000.0]
        start_date = date(2023, 1, 1)

        for month in range(12):
            current_date = start_date + timedelta(days=30 * month)

            aapl_price = 100.0 + (month * 2.0)
            bt.buy(symbol="AAPL", quantity=100, price=aapl_price, date=current_date)

            msft_price = 200.0 + (month * 3.0)
            bt.buy(symbol="MSFT", quantity=50, price=msft_price, date=current_date)

            aapl_current = aapl_price * 1.05
            msft_current = msft_price * 1.04
            bt.update_price(symbol="AAPL", price=aapl_current)
            bt.update_price(symbol="MSFT", price=msft_current)

            portfolio_values.append(bt.portfolio_value)

        return portfolio_values

    def test_backtest_buy_and_sell_scenario(self):
        """Test complete buy/hold/sell lifecycle."""
        bt = Backtester(initial_capital=100000.0)

        # Buy phase: 6 months
        for month in range(6):
            date_obj = date(2023, 1, 1) + timedelta(days=30 * month)
            price = 100.0 + (month * 2.0)
            bt.buy(symbol="AAPL", quantity=50, price=price, date=date_obj)

        # Update prices: positions worth more
        bt.update_price(symbol="AAPL", price=115.0)
        assert bt.portfolio_value > 100000.0

        # Sell phase: sell half
        bt.sell(symbol="AAPL", quantity=150, price=120.0, date=date(2023, 7, 1))

        # Should have sold at profit
        # Cost basis: 5000+5100+5200+5300+5400+5500 = 31500
        # Cash after buys: 68500, after sell: 86500
        assert bt.cash == 86500.0

        # Remaining position
        assert bt.positions["AAPL"].quantity == 150

    def test_backtest_portfolio_diversity(self):
        """Test portfolio with 5 different stocks."""
        bt = Backtester(initial_capital=100000.0)
        symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"]

        # Equal allocation to each stock
        allocation = 100000.0 / len(symbols)

        for symbol in symbols:
            price = 100.0
            quantity = int(allocation / price)
            bt.buy(symbol=symbol, quantity=quantity, price=price, date=date(2023, 1, 1))

        # All positions exist
        assert len(bt.positions) == 5

        # Simulate price movements
        price_changes = {"AAPL": 1.10, "MSFT": 1.08, "GOOG": 0.95, "AMZN": 1.05, "TSLA": 0.85}
        for symbol, change in price_changes.items():
            new_price = 100.0 * change
            bt.update_price(symbol=symbol, price=new_price)

        # Portfolio value reflects mixed performance
        portfolio = bt.portfolio_value
        assert portfolio > 0  # Should still have value

    def test_backtest_metrics_convergence(self):
        """Test that metrics are consistent with data."""
        bt = Backtester(initial_capital=100000.0)

        # Create a linear growth scenario
        values = [100000.0 + (i * 1000.0) for i in range(13)]

        monthly_returns = bt.calculate_monthly_returns(values)
        assert len(monthly_returns) == 12

        # Returns should be ~1% per month (10K / 100K)
        for ret in monthly_returns:
            assert 0.009 < ret < 0.011

        # Max drawdown should be zero
        max_dd = bt.calculate_max_drawdown(values)
        assert max_dd == 0.0

        # Sharpe ratio should be very high (consistent growth)
        sharpe = bt.calculate_sharpe_ratio(monthly_returns)
        assert sharpe > 10  # Very consistent returns

    def test_backtest_rebalancing_scenario(self):
        """Test portfolio rebalancing across months."""
        bt = Backtester(initial_capital=100000.0)

        # Month 1: 60/40 portfolio
        bt.buy(symbol="AAPL", quantity=600, price=100.0, date=date(2023, 1, 1))
        bt.buy(symbol="MSFT", quantity=200, price=200.0, date=date(2023, 1, 1))
        bt.update_price(symbol="AAPL", price=100.0)
        bt.update_price(symbol="MSFT", price=200.0)

        # Month 2: Price movement
        bt.update_price(symbol="AAPL", price=110.0)
        bt.update_price(symbol="MSFT", price=190.0)
        month2_value = bt.portfolio_value

        # Rebalance: reduce winner, add to loser
        bt.sell(symbol="AAPL", quantity=100, price=110.0, date=date(2023, 2, 1))
        bt.buy(symbol="MSFT", quantity=30, price=190.0, date=date(2023, 2, 1))

        # Portfolio continues to evolve
        bt.update_price(symbol="AAPL", price=115.0)
        bt.update_price(symbol="MSFT", price=195.0)

        # Rebalanced portfolio should track properly
        assert "AAPL" in bt.positions
        assert "MSFT" in bt.positions
        assert bt.portfolio_value > 0


class TestBacktestEdgeCases:
    """E2E tests for edge cases and boundary conditions."""

    def test_backtest_zero_gain_scenario(self):
        """Portfolio that returns to starting value."""
        bt = Backtester(initial_capital=100000.0)

        values = [100000.0, 110000.0, 99000.0]
        returns = bt.calculate_monthly_returns(values)

        # First month: +10%, Second month: ~-10%
        assert len(returns) == 2
        assert returns[0] > 0
        assert returns[1] < 0

        sharpe = bt.calculate_sharpe_ratio(returns)
        # Should be low due to volatility
        assert sharpe < 2

    def test_backtest_high_volatility(self):
        """Portfolio with extreme swings."""
        bt = Backtester(initial_capital=100000.0)

        values = [100000.0, 150000.0, 75000.0, 180000.0, 90000.0]
        returns = bt.calculate_monthly_returns(values)

        max_dd = bt.calculate_max_drawdown(values)
        # Should have significant drawdown
        assert max_dd > 0.3

        sharpe = bt.calculate_sharpe_ratio(returns)
        # High volatility, likely low sharpe
        assert sharpe < 1

    def test_backtest_single_day_scenario(self):
        """Backtest with single day of trading."""
        bt = Backtester(initial_capital=100000.0)
        bt.buy(symbol="AAPL", quantity=100, price=100.0, date=date(2023, 1, 1))
        bt.update_price(symbol="AAPL", price=105.0)

        values = [100000.0, 105000.0]
        returns = bt.calculate_monthly_returns(values)

        assert len(returns) == 1
        assert abs(returns[0] - 0.05) < 0.0001

    def test_backtest_fractional_shares(self):
        """Handle fractional share scenarios."""
        bt = Backtester(initial_capital=100000.0)

        # Buy with fractional quantities
        bt.buy(symbol="AAPL", quantity=333.333, price=100.0, date=date(2023, 1, 1))
        bt.update_price(symbol="AAPL", price=110.0)

        # Portfolio value: cash (66666.7) + position (36666.63) = 103333.33
        assert abs(bt.portfolio_value - 103333.33) < 1.0

    def test_backtest_large_portfolio(self):
        """Test scalability with many positions."""
        bt = Backtester(initial_capital=1000000.0)

        # Create 50 positions
        for i in range(50):
            symbol = f"SYM{i}"
            price = 100.0 + i
            bt.buy(symbol=symbol, quantity=100, price=price, date=date(2023, 1, 1))

        assert len(bt.positions) == 50

        # Update all prices
        for i in range(50):
            symbol = f"SYM{i}"
            new_price = (100.0 + i) * 1.05
            bt.update_price(symbol=symbol, price=new_price)

        # Portfolio should reflect all positions
        assert bt.portfolio_value > 1000000.0
        assert bt.total_gain > 0

    def test_backtest_negative_cash_protection(self):
        """Ensure we track cash properly on large sells."""
        bt = Backtester(initial_capital=10000.0)
        bt.buy(symbol="AAPL", quantity=50, price=100.0, date=date(2023, 1, 1))

        # Sell at profit
        bt.sell(symbol="AAPL", quantity=50, price=150.0, date=date(2023, 1, 2))

        # Cash: 10000 - 5000 (buy) + 7500 (sell) = 12500
        assert bt.cash == 12500.0
        assert len(bt.positions) == 0 or "AAPL" not in bt.positions
