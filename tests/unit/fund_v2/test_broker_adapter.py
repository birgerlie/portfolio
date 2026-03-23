"""Broker adapter — executes approved actions via Alpaca."""
from unittest.mock import MagicMock
from fund_v2.broker_adapter import BrokerAdapter


def test_execute_buy_action():
    broker = MagicMock()
    broker.submit_market_order.return_value = MagicMock(id="ord-1", status="filled")
    adapter = BrokerAdapter(broker)
    result = adapter.execute_action({
        "action_type": "buy",
        "entity_id": "AAPL",
        "description": "test buy",
        "confidence": 0.8,
    }, portfolio_value=100000, target_allocation=0.10, price=150.0)
    broker.submit_market_order.assert_called_once()
    assert result["status"] == "executed"


def test_execute_sell_action():
    broker = MagicMock()
    broker.submit_market_order.return_value = MagicMock(id="ord-2", status="filled")
    adapter = BrokerAdapter(broker)
    result = adapter.execute_action({
        "action_type": "sell",
        "entity_id": "NVDA",
    }, qty=10, price=500.0)
    broker.submit_market_order.assert_called_once()
    assert result["status"] == "executed"


def test_skip_non_trade_action():
    broker = MagicMock()
    adapter = BrokerAdapter(broker)
    result = adapter.execute_action({"action_type": "volatility_alert", "entity_id": "AAPL"})
    broker.submit_market_order.assert_not_called()
    assert result["status"] == "skipped"
