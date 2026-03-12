"""Tests for position synchronization between Alpaca and fund engine."""

from decimal import Decimal
from unittest.mock import MagicMock

from fund.position_sync import PositionSync, SyncResult


class TestPositionSync:
    def test_sync_returns_total_value(self):
        broker = MagicMock()
        broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"), market_value=Decimal("85000"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000")),
            MagicMock(symbol="AAPL", quantity=Decimal("50"), market_value=Decimal("9000"),
                      current_price=Decimal("180"), unrealized_pl=Decimal("500")),
        ]
        broker.get_account.return_value = MagicMock(cash=Decimal("6000"))

        sync = PositionSync(broker=broker)
        result = sync.sync()

        assert result.positions_value == Decimal("94000")
        assert result.cash == Decimal("6000")
        assert result.total_value == Decimal("100000")
        assert len(result.positions) == 2

    def test_sync_empty_portfolio(self):
        broker = MagicMock()
        broker.get_positions.return_value = []
        broker.get_account.return_value = MagicMock(cash=Decimal("100000"))

        sync = PositionSync(broker=broker)
        result = sync.sync()

        assert result.positions_value == Decimal("0")
        assert result.cash == Decimal("100000")
        assert result.total_value == Decimal("100000")

    def test_sync_detects_discrepancy(self):
        broker = MagicMock()
        broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"), market_value=Decimal("85000"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000")),
        ]
        broker.get_account.return_value = MagicMock(cash=Decimal("15000"))

        sync = PositionSync(broker=broker)
        result = sync.sync()

        # Check that we can compare with expected fund NAV
        expected_nav = Decimal("99000")
        discrepancy = result.total_value - expected_nav
        assert discrepancy == Decimal("1000")

    def test_positions_as_dict(self):
        broker = MagicMock()
        broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"), market_value=Decimal("85000"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000")),
        ]
        broker.get_account.return_value = MagicMock(cash=Decimal("15000"))

        sync = PositionSync(broker=broker)
        result = sync.sync()

        positions_dict = result.positions_by_symbol()
        assert "NVDA" in positions_dict
        assert positions_dict["NVDA"].quantity == Decimal("100")

    def test_sync_journals_event(self):
        broker = MagicMock()
        broker.get_positions.return_value = []
        broker.get_account.return_value = MagicMock(cash=Decimal("100000"))
        journal = MagicMock()

        sync = PositionSync(broker=broker, journal=journal)
        sync.sync()

        journal.log.assert_called_once()
        call_args = journal.log.call_args
        assert call_args[0][0] == "position_sync"
