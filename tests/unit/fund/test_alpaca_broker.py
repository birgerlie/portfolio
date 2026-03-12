"""Tests for the Alpaca broker adapter."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from fund.alpaca_broker import AlpacaBroker, AlpacaConfig, BrokerAccount, BrokerPosition


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
