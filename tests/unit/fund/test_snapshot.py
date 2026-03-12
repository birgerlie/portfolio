"""Tests for snapshot builder — assembles WeeklyNAV from all components."""
from datetime import date
from decimal import Decimal
import pytest
from fund.snapshot import SnapshotBuilder
from fund.types import Fund, WeeklyNAV
from fund.fees import FeeEngine
from fund.nav import NAVCalculator
from fund.thermo_metrics import ThermoMetrics
from fund.benchmarks import BenchmarkEngine


class TestSnapshotBuilder:
    def _make_builder(self):
        return SnapshotBuilder(
            nav_calculator=NAVCalculator(fee_engine=FeeEngine()),
            fee_engine=FeeEngine(),
            thermo_metrics=ThermoMetrics(),
            benchmark_engine=BenchmarkEngine())

    def test_build_snapshot(self):
        builder = self._make_builder()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        snapshot = builder.build(
            fund=fund, positions={"NVDA": {"quantity": 100, "price": 150.0}},
            cash=Decimal("985000"), beliefs={"NVDA": 0.85}, prev_beliefs={"NVDA": 0.80},
            volatility=0.20, prev_nav=Decimal("990000"), snapshot_date=date(2026, 3, 14),
            benchmark_values={}, stock_returns={})
        assert isinstance(snapshot, WeeklyNAV)
        assert snapshot.date == date(2026, 3, 14)
        assert snapshot.nav > 0
        assert snapshot.clarity_score > 0
        assert snapshot.market_health == "green"

    def test_snapshot_includes_fees(self):
        builder = self._make_builder()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        snapshot = builder.build(
            fund=fund, positions={}, cash=Decimal("1000000"),
            beliefs={}, prev_beliefs={}, volatility=0.20,
            prev_nav=Decimal("1000000"), snapshot_date=date(2026, 3, 14),
            benchmark_values={}, stock_returns={})
        assert snapshot.mgmt_fee_accrued > 0
