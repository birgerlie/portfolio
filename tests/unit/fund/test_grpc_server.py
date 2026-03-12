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


class TestGetMemberPosition:
    def test_returns_member_data(self):
        fund = MagicMock()
        fund.nav_per_unit = Decimal("105")

        member = MagicMock()
        member.id = "m1"
        member.name = "Alice"
        member.units = Decimal("100")
        member.cost_basis = Decimal("10000")
        member.lock_up_until = date(2026, 6, 1)
        member.value_at_nav.return_value = Decimal("10500")
        member.return_pct.return_value = 0.05

        servicer = make_servicer(fund=fund, members={"m1": member})
        req = fund_service_pb2.MemberId(id="m1")
        response = servicer.GetMemberPosition(req, MockContext())

        assert response.name == "Alice"
        assert response.units == 100.0
        assert response.return_pct == 0.05

    def test_unknown_member_returns_error(self):
        servicer = make_servicer()
        ctx = MockContext()
        req = fund_service_pb2.MemberId(id="unknown")
        servicer.GetMemberPosition(req, ctx)
        assert ctx.code == grpc.StatusCode.NOT_FOUND


class TestGetThermoMetrics:
    def test_returns_thermo_snapshot(self):
        thermo = MagicMock()
        thermo.clarity_score.return_value = 0.78
        thermo.opportunity_score.return_value = 0.65
        thermo.market_health.return_value = "green"
        thermo.momentum.return_value = "rising"
        thermo.interpret.return_value = "Strong clarity, good opportunity"

        servicer = make_servicer(thermo=thermo)
        response = servicer.GetThermoMetrics(Empty(), MockContext())

        assert response.clarity_score == 0.78
        assert response.market_health == "green"


class TestGetDailyJournal:
    def test_returns_journal_for_date(self):
        journal = MagicMock()
        journal.load_date.return_value = MagicMock(
            date=date(2026, 3, 12),
            entries=[
                MagicMock(timestamp=datetime(2026, 3, 12, 10, 0), entry_type="trade_executed",
                          summary="Bought NVDA", data={"symbol": "NVDA"}),
            ],
            regime_summary="Bull all day",
            trades_executed=1,
            nav_change_pct=0.02,
            belief_snapshot={"NVDA": 0.85},
            thermo_snapshot={"clarity": 0.78},
        )

        servicer = make_servicer(journal=journal)
        req = fund_service_pb2.JournalDate(date="2026-03-12")
        response = servicer.GetDailyJournal(req, MockContext())

        assert response.date == "2026-03-12"
        assert response.trades_executed == 1
        assert response.regime_summary == "Bull all day"
        assert len(response.entries) == 1
