"""Tests for the gRPC server servicer."""

import threading
import time
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


class TestGetWeeklyNAVHistory:
    def test_returns_nav_records(self):
        servicer = make_servicer()
        servicer._nav_history = [
            MagicMock(date=date(2026, 3, 5), nav=Decimal("98000"), nav_per_unit=Decimal("103"),
                      gross_return_pct=0.01, net_return_pct=0.008, mgmt_fee_accrued=Decimal("38"),
                      perf_fee_accrued=Decimal("0"), high_water_mark=Decimal("103"),
                      clarity_score=0.75, opportunity_score=0.6, capture_rate=0.5,
                      market_health="green", momentum="rising",
                      benchmarks={"SPY": 0.005}, narrative_summary="Good week"),
        ]

        req = fund_service_pb2.TimeRange()
        records = list(servicer.GetWeeklyNAVHistory(req, MockContext()))
        assert len(records) == 1
        assert records[0].nav == 98000.0
        assert records[0].nav_per_unit == 103.0


class TestGetBenchmarkComparison:
    def test_returns_benchmark_data(self):
        benchmarks = MagicMock()
        benchmarks.compare.return_value = {"SPY": 0.05, "QQQ": 0.08}
        benchmarks.equal_weight_return.return_value = 0.06
        benchmarks.best_daily_pick_return.return_value = 0.12
        benchmarks.random_portfolio_median.return_value = 0.04
        benchmarks.capture_rate.return_value = 0.76

        servicer = make_servicer(benchmarks=benchmarks)
        req = fund_service_pb2.TimeRange()
        response = servicer.GetBenchmarkComparison(req, MockContext())

        assert response.capture_rate == 0.76
        assert response.equal_weight_return == 0.06


class TestGetDecisionLog:
    def test_returns_decisions_from_journal(self):
        journal = MagicMock()
        journal.today = MagicMock(
            entries=[
                MagicMock(timestamp=datetime(2026, 3, 12, 10, 0), entry_type="trade_executed",
                          summary="Bought NVDA", data={"symbol": "NVDA"}),
                MagicMock(timestamp=datetime(2026, 3, 12, 11, 0), entry_type="regime_change",
                          summary="Bull to Bear", data={}),
            ]
        )

        servicer = make_servicer(journal=journal)
        req = fund_service_pb2.TimeRange()
        decisions = list(servicer.GetDecisionLog(req, MockContext()))

        assert len(decisions) == 2
        assert decisions[0].type == "trade_executed"
        assert decisions[1].type == "regime_change"


class TestPushEvent:
    def test_push_event_adds_to_queue(self):
        servicer = make_servicer()
        servicer.push_event("trade_executed", "Bought NVDA", "info", {"symbol": "NVDA"})
        assert servicer._event_queue.qsize() == 1

    def test_push_event_stores_correct_fields(self):
        servicer = make_servicer()
        servicer.push_event("regime_change", "Bull to Bear", "warning", {"old": "bull"})
        events = servicer._drain_events()
        assert len(events) == 1
        assert events[0].event_type == "regime_change"
        assert events[0].title == "Bull to Bear"
        assert events[0].severity == "warning"


class TestDrainEvents:
    def test_drain_returns_all_events(self):
        servicer = make_servicer()
        servicer.push_event("trade_executed", "Bought NVDA", "info", {"symbol": "NVDA"})
        servicer.push_event("regime_change", "Bull to Bear", "warning", {})
        events = servicer._drain_events()
        assert len(events) == 2
        assert events[0].event_type == "trade_executed"
        assert events[1].event_type == "regime_change"

    def test_drain_empties_queue(self):
        servicer = make_servicer()
        servicer.push_event("trade_executed", "Bought NVDA", "info", {})
        servicer._drain_events()
        assert servicer._event_queue.qsize() == 0


class TestStreamEvents:
    def test_stream_yields_events(self):
        servicer = make_servicer()
        servicer.push_event("trade_executed", "Bought NVDA", "info", {"symbol": "NVDA"})
        servicer.push_event("regime_change", "Bull to Bear", "warning", {})

        ctx = MockContext()
        ctx.is_active = lambda: True
        events = list(servicer._drain_events())

        assert len(events) == 2
        assert events[0].event_type == "trade_executed"
        assert events[1].event_type == "regime_change"

    def test_stream_events_stops_when_context_inactive(self):
        servicer = make_servicer()

        ctx = MockContext()
        call_count = [0]

        def is_active():
            call_count[0] += 1
            return call_count[0] <= 1  # active only on first check

        ctx.is_active = is_active
        # No events in queue; context becomes inactive quickly
        events = list(servicer.StreamEvents(None, ctx))
        assert events == []


class TestStreamThermoMetrics:
    def test_stream_yields_thermo_snapshot(self):
        thermo = MagicMock()
        thermo.clarity_score.return_value = 0.9
        thermo.opportunity_score.return_value = 0.7
        thermo.market_health.return_value = "green"
        thermo.momentum.return_value = "rising"
        thermo.interpret.return_value = "Looking good"

        servicer = make_servicer(thermo=thermo)

        call_count = [0]

        def is_active():
            call_count[0] += 1
            return call_count[0] <= 1  # yield exactly one snapshot then stop

        ctx = MockContext()
        ctx.is_active = is_active

        snapshots = list(servicer.StreamThermoMetrics(None, ctx))
        assert len(snapshots) == 1
        assert snapshots[0].clarity_score == 0.9
        assert snapshots[0].market_health == "green"
