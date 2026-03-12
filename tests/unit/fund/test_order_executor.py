"""Tests for the order executor."""

from decimal import Decimal
from unittest.mock import MagicMock

from fund.order_executor import OrderExecutor, ExecutedOrder


class TestOrderExecutor:
    def _make_broker(self):
        broker = MagicMock()
        broker.get_account.return_value = MagicMock(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        mock_order = MagicMock()
        mock_order.id = "order-1"
        mock_order.symbol = "NVDA"
        mock_order.side = "buy"
        mock_order.qty = Decimal("10")
        mock_order.order_type = "market"
        mock_order.status = "new"
        mock_order.filled_qty = Decimal("0")
        mock_order.filled_avg_price = None
        broker.submit_market_order.return_value = mock_order
        return broker

    def test_execute_buy_order(self):
        broker = self._make_broker()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        result = executor.execute_buy(
            symbol="NVDA",
            target_allocation=0.30,
            current_price=Decimal("850"),
            portfolio_value=Decimal("100000"),
        )

        assert result.symbol == "NVDA"
        assert result.side == "buy"
        assert result.qty > 0
        broker.submit_market_order.assert_called_once()
        journal.log.assert_called_once()

    def test_execute_sell_order(self):
        broker = self._make_broker()
        broker.submit_market_order.return_value.side = "sell"
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        result = executor.execute_sell(
            symbol="NVDA",
            qty=Decimal("10"),
            current_price=Decimal("850"),
        )

        assert result.side == "sell"
        broker.submit_market_order.assert_called_once()
        journal.log.assert_called_once()

    def test_execute_buy_calculates_shares_from_allocation(self):
        broker = self._make_broker()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        executor.execute_buy(
            symbol="NVDA",
            target_allocation=0.30,
            current_price=Decimal("850"),
            portfolio_value=Decimal("100000"),
        )

        # 30% of 100k = 30k / 850 = 35 shares (truncated to whole shares)
        call_args = broker.submit_market_order.call_args
        assert call_args.kwargs["qty"] == Decimal("35")

    def test_execute_buy_zero_allocation_skips(self):
        broker = self._make_broker()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        result = executor.execute_buy(
            symbol="NVDA",
            target_allocation=0.0,
            current_price=Decimal("850"),
            portfolio_value=Decimal("100000"),
        )

        assert result is None
        broker.submit_market_order.assert_not_called()

    def test_journal_entry_on_trade(self):
        broker = self._make_broker()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        executor.execute_buy(
            symbol="NVDA",
            target_allocation=0.30,
            current_price=Decimal("850"),
            portfolio_value=Decimal("100000"),
        )

        journal.log.assert_called_once()
        call_args = journal.log.call_args[0]
        assert call_args[0] == "trade_executed"


class TestExecutePlan:
    def test_execute_plan_sells_first_then_buys(self):
        """Sells should execute before buys to free up cash."""
        broker = MagicMock()
        order_counter = {"n": 0}

        def mock_submit(symbol=None, qty=None, side=None):
            order_counter["n"] += 1
            m = MagicMock()
            m.id = f"order-{order_counter['n']}"
            m.symbol = symbol
            m.side = side
            m.qty = str(qty)
            m.order_type = "market"
            m.status = "new"
            m.filled_qty = "0"
            m.filled_avg_price = None
            return m

        broker.submit_market_order.side_effect = mock_submit
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        current_positions = {"AAPL": Decimal("50"), "NVDA": Decimal("0")}
        current_prices = {"AAPL": Decimal("180"), "NVDA": Decimal("850")}

        # Sell AAPL (reduce), Buy NVDA (new position)
        trades = [
            {"symbol": "AAPL", "side": "SELL", "qty": Decimal("20")},
            {"symbol": "NVDA", "side": "BUY", "allocation": 0.25},
        ]

        results = executor.execute_plan(
            trades=trades,
            current_prices=current_prices,
            portfolio_value=Decimal("100000"),
        )

        assert len(results) == 2
        # Verify sells happened first (submit_market_order called with kwargs)
        calls = broker.submit_market_order.call_args_list
        assert calls[0].kwargs["side"] == "sell"
        assert calls[1].kwargs["side"] == "buy"

    def test_execute_plan_skips_zero_qty(self):
        broker = MagicMock()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        trades = [
            {"symbol": "NVDA", "side": "BUY", "allocation": 0.0},
        ]

        results = executor.execute_plan(
            trades=trades,
            current_prices={"NVDA": Decimal("850")},
            portfolio_value=Decimal("100000"),
        )

        assert len(results) == 0
        broker.submit_market_order.assert_not_called()
