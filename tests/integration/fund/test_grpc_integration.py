"""Integration tests for gRPC server — real server, real channel, real RPCs."""

import threading
import time
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import grpc
import pytest
from google.protobuf.empty_pb2 import Empty

from fund.grpc_runner import create_server
from fund.grpc_server import FundServiceServicer
from fund.proto import fund_service_pb2, fund_service_pb2_grpc

TEST_PORT = 50099


def _make_servicer():
    """Build a FundServiceServicer with realistic mock dependencies."""
    fund = MagicMock()
    fund.nav = Decimal("120000")
    fund.nav_per_unit = Decimal("110")
    fund.units_outstanding = Decimal("1090.91")
    fund.high_water_mark = Decimal("110")
    fund.inception_date = date(2026, 1, 1)

    broker = MagicMock()
    broker.get_account.return_value = MagicMock(cash=Decimal("20000"))
    broker.get_positions.return_value = [
        MagicMock(
            symbol="NVDA",
            quantity=Decimal("100"),
            market_value=Decimal("85000"),
            avg_entry_price=Decimal("800"),
            current_price=Decimal("850"),
            unrealized_pl=Decimal("5000"),
            unrealized_pl_pct=0.0625,
        ),
        MagicMock(
            symbol="AAPL",
            quantity=Decimal("50"),
            market_value=Decimal("15000"),
            avg_entry_price=Decimal("290"),
            current_price=Decimal("300"),
            unrealized_pl=Decimal("500"),
            unrealized_pl_pct=0.034,
        ),
    ]

    health = MagicMock()
    health.create_heartbeat.return_value = MagicMock(
        status="running",
        alpaca_connected=True,
        last_trade=None,
        active_positions=2,
        current_regime="BULL",
        next_action="rebalance",
        next_action_at=None,
        timestamp=datetime.now(),
    )

    thermo = MagicMock()
    thermo.clarity_score.return_value = 0.78
    thermo.opportunity_score.return_value = 0.65
    thermo.market_health.return_value = "green"
    thermo.momentum.return_value = "rising"
    thermo.interpret.return_value = "Strong clarity, good opportunity"

    return FundServiceServicer(
        fund=fund,
        members={},
        broker=broker,
        universe=MagicMock(),
        journal=MagicMock(),
        thermo=thermo,
        benchmarks=MagicMock(),
        health=health,
    )


@pytest.fixture(scope="module")
def grpc_server():
    """Start a real gRPC server on TEST_PORT; yield the servicer; stop after tests."""
    servicer = _make_servicer()
    server = create_server(servicer, port=TEST_PORT)
    server.start()
    # Give the server a moment to bind
    time.sleep(0.2)
    yield servicer
    server.stop(grace=1)


@pytest.fixture(scope="module")
def stub():
    """Return a gRPC stub connected to the test server."""
    channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
    return fund_service_pb2_grpc.FundServiceStub(channel)


# ---------------------------------------------------------------------------
# Test 1: GetCurrentState
# ---------------------------------------------------------------------------
class TestGetCurrentState:
    def test_nav_and_nav_per_unit(self, grpc_server, stub):
        response = stub.GetCurrentState(Empty())
        assert response.nav == pytest.approx(120000.0)
        assert response.nav_per_unit == pytest.approx(110.0)

    def test_engine_status(self, grpc_server, stub):
        response = stub.GetCurrentState(Empty())
        status = response.engine_status
        assert status.status == "running"
        assert status.alpaca_connected is True
        assert status.current_regime == "BULL"


# ---------------------------------------------------------------------------
# Test 2: GetPositions
# ---------------------------------------------------------------------------
class TestGetPositions:
    def test_positions_list(self, grpc_server, stub):
        response = stub.GetPositions(Empty())
        symbols = [p.symbol for p in response.positions]
        assert "NVDA" in symbols
        assert "AAPL" in symbols
        assert len(response.positions) == 2

    def test_total_value(self, grpc_server, stub):
        response = stub.GetPositions(Empty())
        # 85000 + 15000 + 20000 cash = 120000
        assert response.total_value == pytest.approx(120000.0)
        assert response.cash == pytest.approx(20000.0)


# ---------------------------------------------------------------------------
# Test 3: GetThermoMetrics
# ---------------------------------------------------------------------------
class TestGetThermoMetrics:
    def test_clarity_score(self, grpc_server, stub):
        response = stub.GetThermoMetrics(Empty())
        assert response.clarity_score == pytest.approx(0.78)

    def test_market_health(self, grpc_server, stub):
        response = stub.GetThermoMetrics(Empty())
        assert response.market_health == "green"


# ---------------------------------------------------------------------------
# Test 4: GetEngineStatus
# ---------------------------------------------------------------------------
class TestGetEngineStatus:
    def test_status_field(self, grpc_server, stub):
        response = stub.GetEngineStatus(Empty())
        assert response.status == "running"

    def test_current_regime(self, grpc_server, stub):
        response = stub.GetEngineStatus(Empty())
        assert response.current_regime == "BULL"


# ---------------------------------------------------------------------------
# Test 5: StreamEvents
# ---------------------------------------------------------------------------
class TestStreamEvents:
    def test_push_event_then_read_from_stream(self, grpc_server, stub):
        """Push an event via the servicer, then confirm it arrives in the stream."""
        received = []
        error = []

        def collect_stream():
            try:
                # Read with a short deadline so the test doesn't hang
                for event in stub.StreamEvents(Empty(), timeout=3):
                    received.append(event)
                    # Stop after receiving one event
                    break
            except grpc.RpcError as e:
                # DEADLINE_EXCEEDED is expected when no more events arrive
                if e.code() not in (grpc.StatusCode.DEADLINE_EXCEEDED,
                                    grpc.StatusCode.CANCELLED):
                    error.append(e)

        # Start the stream consumer in a background thread
        t = threading.Thread(target=collect_stream, daemon=True)
        t.start()

        # Give the thread a moment to connect and start blocking
        time.sleep(0.3)

        # Push an event into the servicer
        grpc_server.push_event("trade_executed", "Bought NVDA", "info", {"symbol": "NVDA"})

        # Wait for the consumer thread to finish
        t.join(timeout=5)

        assert not error, f"Stream raised unexpected error: {error}"
        assert len(received) == 1
        assert received[0].event_type == "trade_executed"
        assert received[0].title == "Bought NVDA"
