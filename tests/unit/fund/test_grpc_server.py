"""Tests for the gRPC server servicer."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import grpc
from google.protobuf.empty_pb2 import Empty

from fund.grpc_server import FundServiceServicer
from fund.proto import fund_service_pb2


class MockContext:
    """Minimal gRPC context for testing."""
    def set_code(self, code): self.code = code
    def set_details(self, details): self.details = details


def make_servicer(fund=None, members=None, broker=None, universe=None,
                  journal=None, thermo=None, benchmarks=None, health=None):
    """Create a servicer with mocked dependencies."""
    return FundServiceServicer(
        fund=fund or MagicMock(),
        members=members or {},
        broker=broker or MagicMock(),
        universe=universe or MagicMock(),
        journal=journal or MagicMock(),
        thermo=thermo or MagicMock(),
        benchmarks=benchmarks or MagicMock(),
        health=health or MagicMock(),
    )


class TestGetCurrentState:
    def test_returns_fund_state(self):
        fund = MagicMock()
        fund.nav = Decimal("100000")
        fund.nav_per_unit = Decimal("105")
        fund.units_outstanding = Decimal("952.38")
        fund.high_water_mark = Decimal("105")
        fund.inception_date = date(2026, 1, 1)

        broker = MagicMock()
        broker.get_account.return_value = MagicMock(cash=Decimal("15000"))

        health = MagicMock()
        health.create_heartbeat.return_value = MagicMock(
            status="running", alpaca_connected=True, last_trade=None,
            active_positions=3, current_regime="BULL",
            next_action="rebalance", next_action_at=None,
            timestamp=datetime.now(),
        )

        servicer = make_servicer(fund=fund, broker=broker, health=health)
        response = servicer.GetCurrentState(Empty(), MockContext())

        assert response.nav == 100000.0
        assert response.nav_per_unit == 105.0
        assert response.engine_status.status == "running"


class TestGetPositions:
    def test_returns_positions(self):
        broker = MagicMock()
        broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"),
                      market_value=Decimal("85000"), avg_entry_price=Decimal("800"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000"),
                      unrealized_pl_pct=0.0625),
        ]
        broker.get_account.return_value = MagicMock(cash=Decimal("15000"))

        servicer = make_servicer(broker=broker)
        response = servicer.GetPositions(Empty(), MockContext())

        assert len(response.positions) == 1
        assert response.positions[0].symbol == "NVDA"
        assert response.total_value == 100000.0
        assert response.cash == 15000.0


class TestGetUniverse:
    def test_returns_universe(self):
        universe = MagicMock()
        universe.max_size = 20
        universe._instruments = {
            "NVDA": MagicMock(symbol="NVDA", name="NVIDIA", asset_class="equity",
                              thesis="AI leader", proposed_by="alice",
                              added_date=date(2026, 1, 15), votes_for=5),
        }

        servicer = make_servicer(universe=universe)
        response = servicer.GetUniverse(Empty(), MockContext())

        assert response.max_size == 20
        assert len(response.instruments) == 1
        assert response.instruments[0].symbol == "NVDA"
