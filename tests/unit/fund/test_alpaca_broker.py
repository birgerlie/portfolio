"""Tests for the Alpaca broker adapter."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from fund.alpaca_broker import AlpacaBroker, AlpacaConfig, BrokerAccount, BrokerPosition, BrokerOrder


class TestAlpacaConfig:
    def test_paper_config(self):
        config = AlpacaConfig(api_key="test", secret_key="secret", paper=True)
        assert config.paper is True

    def test_live_config(self):
        config = AlpacaConfig(api_key="test", secret_key="secret", paper=False)
        assert config.paper is False


class TestAlpacaBrokerAccount:
    def test_get_account(self):
        mock_client = MagicMock()
        mock_account = MagicMock()
        mock_account.cash = "50000.00"
        mock_account.equity = "100000.00"
        mock_account.buying_power = "50000.00"
        mock_account.status = "ACTIVE"
        mock_client.get_account.return_value = mock_account

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        account = broker.get_account()
        assert account.cash == Decimal("50000.00")
        assert account.equity == Decimal("100000.00")
        assert account.status == "ACTIVE"

    def test_is_connected_true(self):
        mock_client = MagicMock()
        mock_client.get_account.return_value = MagicMock(status="ACTIVE")
        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client
        assert broker.is_connected() is True

    def test_is_connected_false_on_error(self):
        mock_client = MagicMock()
        mock_client.get_account.side_effect = Exception("API error")
        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client
        assert broker.is_connected() is False


class TestAlpacaBrokerPositions:
    def test_get_positions(self):
        mock_client = MagicMock()
        mock_pos = MagicMock()
        mock_pos.symbol = "NVDA"
        mock_pos.qty = "100"
        mock_pos.market_value = "85000.00"
        mock_pos.avg_entry_price = "800.00"
        mock_pos.current_price = "850.00"
        mock_pos.unrealized_pl = "5000.00"
        mock_pos.unrealized_plpc = "0.0625"
        mock_client.get_all_positions.return_value = [mock_pos]

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "NVDA"
        assert positions[0].quantity == Decimal("100")
        assert positions[0].market_value == Decimal("85000.00")

    def test_get_positions_empty(self):
        mock_client = MagicMock()
        mock_client.get_all_positions.return_value = []
        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client
        assert broker.get_positions() == []


class TestAlpacaBrokerOrders:
    def test_submit_market_buy(self):
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.symbol = "NVDA"
        mock_order.side = "buy"
        mock_order.qty = "100"
        mock_order.order_type = "market"
        mock_order.limit_price = None
        mock_order.status = "new"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_client.submit_order.return_value = mock_order

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        order = broker.submit_market_order("NVDA", Decimal("100"), "buy")
        assert order.id == "order-123"
        assert order.symbol == "NVDA"
        assert order.side == "buy"
        assert order.status == "new"
        mock_client.submit_order.assert_called_once()

    def test_submit_limit_buy(self):
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order-456"
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.qty = "50"
        mock_order.order_type = "limit"
        mock_order.limit_price = "150.00"
        mock_order.status = "new"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_client.submit_order.return_value = mock_order

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        order = broker.submit_limit_order("AAPL", Decimal("50"), "buy", Decimal("150.00"))
        assert order.id == "order-456"
        assert order.order_type == "limit"
        mock_client.submit_order.assert_called_once()

    def test_get_order_status(self):
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.symbol = "NVDA"
        mock_order.side = "buy"
        mock_order.qty = "100"
        mock_order.order_type = "market"
        mock_order.limit_price = None
        mock_order.status = "filled"
        mock_order.filled_qty = "100"
        mock_order.filled_avg_price = "851.25"
        mock_client.get_order_by_id.return_value = mock_order

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        order = broker.get_order("order-123")
        assert order.status == "filled"
        assert order.filled_qty == Decimal("100")
        assert order.filled_avg_price == Decimal("851.25")

    def test_cancel_order(self):
        mock_client = MagicMock()
        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        broker.cancel_order("order-123")
        mock_client.cancel_order_by_id.assert_called_once_with("order-123")
