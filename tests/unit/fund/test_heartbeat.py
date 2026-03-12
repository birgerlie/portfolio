"""Tests for engine heartbeat."""
from datetime import datetime, timedelta
import pytest
from fund.heartbeat import HealthMonitor
from fund.types import EngineHealth


class TestHealthMonitor:
    def test_create_heartbeat(self):
        monitor = HealthMonitor()
        hb = monitor.create_heartbeat(
            alpaca_connected=True, last_trade=datetime(2026, 3, 12, 10, 0),
            active_positions=5, current_regime="bull",
            next_action="rebalance", next_action_at=datetime(2026, 3, 14, 9, 30))
        assert hb.status == "running"
        assert hb.alpaca_connected is True

    def test_degraded_when_alpaca_down(self):
        monitor = HealthMonitor()
        hb = monitor.create_heartbeat(
            alpaca_connected=False, last_trade=None, active_positions=0,
            current_regime="unknown", next_action="reconnect", next_action_at=None)
        assert hb.status == "degraded"

    def test_status_from_last_heartbeat_green(self):
        monitor = HealthMonitor()
        last = datetime.now() - timedelta(seconds=30)
        assert monitor.display_status(last) == "green"

    def test_status_from_last_heartbeat_yellow(self):
        monitor = HealthMonitor()
        last = datetime.now() - timedelta(minutes=3)
        assert monitor.display_status(last) == "yellow"

    def test_status_from_last_heartbeat_red(self):
        monitor = HealthMonitor()
        last = datetime.now() - timedelta(minutes=10)
        assert monitor.display_status(last) == "red"

    def test_should_notify_manager(self):
        monitor = HealthMonitor()
        last = datetime.now() - timedelta(minutes=6)
        assert monitor.should_notify_manager(last) is True

    def test_should_notify_members(self):
        monitor = HealthMonitor()
        last = datetime.now() - timedelta(minutes=16)
        assert monitor.should_notify_members(last) is True
