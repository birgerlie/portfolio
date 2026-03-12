"""Property-based tests for fund invariants."""
from datetime import date
from decimal import Decimal
from hypothesis import given, strategies as st, settings
from fund.types import Fund, Member
from fund.fees import FeeEngine
from fund.ledger import UnitLedger

money = st.decimals(min_value=1, max_value=10_000_000, places=2, allow_nan=False, allow_infinity=False)


class TestFeeInvariants:
    @given(nav=money)
    def test_management_fee_never_negative(self, nav):
        engine = FeeEngine()
        fee = engine.weekly_management_fee(nav)
        assert fee >= 0

    @given(
        nav_per_unit=st.decimals(min_value=0, max_value=10000, places=2, allow_nan=False, allow_infinity=False),
        hwm=st.decimals(min_value=0, max_value=10000, places=2, allow_nan=False, allow_infinity=False),
        units=st.decimals(min_value=1, max_value=100000, places=0, allow_nan=False, allow_infinity=False),
    )
    def test_performance_fee_never_negative(self, nav_per_unit, hwm, units):
        engine = FeeEngine()
        fee, new_hwm = engine.performance_fee(nav_per_unit, hwm, units)
        assert fee >= 0

    @given(
        nav1=st.decimals(min_value=500, max_value=2000, places=2, allow_nan=False, allow_infinity=False),
        nav2=st.decimals(min_value=500, max_value=2000, places=2, allow_nan=False, allow_infinity=False),
    )
    def test_hwm_never_decreases(self, nav1, nav2):
        engine = FeeEngine()
        _, hwm1 = engine.performance_fee(nav1, Decimal("1000"), Decimal("100"))
        _, hwm2 = engine.performance_fee(nav2, hwm1, Decimal("100"))
        assert hwm2 >= hwm1


class TestLedgerInvariants:
    @given(amount=st.decimals(min_value=100, max_value=1_000_000, places=2, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_subscribe_units_balance(self, amount):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        member = Member(id="m1", name="Test", email="t@t.com",
                        units=Decimal("0"), cost_basis=Decimal("0"), join_date=date(2026, 1, 1))
        ledger.subscribe(fund, member, amount, date(2026, 2, 1))
        expected = fund.units_outstanding * fund.nav_per_unit
        assert abs(fund.nav - expected) < Decimal("1")
