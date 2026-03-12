"""Tests for fee engine — management fee, performance fee, HWM."""

from decimal import Decimal
import pytest
from fund.fees import FeeEngine
from fund.types import FeeBreakdown


class TestManagementFee:
    def test_weekly_management_fee(self):
        engine = FeeEngine(mgmt_fee_annual=Decimal("0.02"))
        fee = engine.weekly_management_fee(nav=Decimal("1000000"))
        assert fee == pytest.approx(Decimal("384.62"), abs=Decimal("0.01"))

    def test_zero_nav(self):
        engine = FeeEngine()
        fee = engine.weekly_management_fee(nav=Decimal("0"))
        assert fee == Decimal("0")


class TestPerformanceFee:
    def test_performance_fee_above_hwm(self):
        engine = FeeEngine(perf_fee_rate=Decimal("0.20"))
        fee, new_hwm = engine.performance_fee(
            nav_per_unit=Decimal("1100"), high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"))
        assert fee == Decimal("20000")
        assert new_hwm == Decimal("1100")

    def test_no_performance_fee_below_hwm(self):
        engine = FeeEngine()
        fee, new_hwm = engine.performance_fee(
            nav_per_unit=Decimal("950"), high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"))
        assert fee == Decimal("0")
        assert new_hwm == Decimal("1000")

    def test_no_performance_fee_at_hwm(self):
        engine = FeeEngine()
        fee, new_hwm = engine.performance_fee(
            nav_per_unit=Decimal("1000"), high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"))
        assert fee == Decimal("0")
        assert new_hwm == Decimal("1000")

    def test_hwm_never_decreases(self):
        engine = FeeEngine()
        _, hwm1 = engine.performance_fee(Decimal("1200"), Decimal("1000"), Decimal("1000"))
        _, hwm2 = engine.performance_fee(Decimal("1100"), hwm1, Decimal("1000"))
        assert hwm2 == Decimal("1200")

    def test_recovery_no_double_charge(self):
        engine = FeeEngine(perf_fee_rate=Decimal("0.20"))
        fee1, hwm = engine.performance_fee(Decimal("1200"), Decimal("1000"), Decimal("100"))
        assert fee1 == Decimal("4000")
        fee2, hwm = engine.performance_fee(Decimal("1100"), hwm, Decimal("100"))
        assert fee2 == Decimal("0")
        fee3, hwm = engine.performance_fee(Decimal("1200"), hwm, Decimal("100"))
        assert fee3 == Decimal("0")
        fee4, hwm = engine.performance_fee(Decimal("1300"), hwm, Decimal("100"))
        assert fee4 == Decimal("2000")


class TestAccrueFees:
    def test_accrue_weekly(self):
        engine = FeeEngine()
        breakdown = engine.accrue_weekly(
            nav=Decimal("1000000"), nav_per_unit=Decimal("1050"),
            high_water_mark=Decimal("1000"), units_outstanding=Decimal("1000"))
        assert breakdown.management_fee > 0
        assert breakdown.performance_fee == Decimal("0")


class TestMonthlyCrystallization:
    def test_crystallize_above_hwm(self):
        engine = FeeEngine(perf_fee_rate=Decimal("0.20"))
        fees, new_hwm = engine.crystallize_monthly(
            nav_per_unit=Decimal("1100"), high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"))
        assert fees.performance_fee == Decimal("20000")
        assert new_hwm == Decimal("1100")

    def test_crystallize_below_hwm(self):
        engine = FeeEngine()
        fees, new_hwm = engine.crystallize_monthly(
            nav_per_unit=Decimal("950"), high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"))
        assert fees.performance_fee == Decimal("0")
        assert new_hwm == Decimal("1000")
