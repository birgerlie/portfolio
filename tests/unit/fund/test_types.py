"""Tests for fund core data types."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from fund.types import (
    Fund, Member, Transaction, TransactionType, TransactionStatus, FeeBreakdown,
)


class TestFund:
    def test_create_fund(self):
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        assert fund.nav_per_unit == Decimal("1000")

    def test_nav_per_unit_calculation(self):
        fund = Fund(nav=Decimal("1050000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        assert fund.nav_per_unit == Decimal("1050")

    def test_nav_per_unit_zero_units(self):
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("0"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        assert fund.nav_per_unit == Decimal("0")


class TestMember:
    def test_create_member(self):
        member = Member(id="m1", name="Alice", email="alice@example.com",
                        units=Decimal("100"), cost_basis=Decimal("100000"),
                        join_date=date(2026, 1, 1))
        assert member.lock_up_until == date(2026, 4, 1)

    def test_member_value_at_nav(self):
        member = Member(id="m1", name="Alice", email="alice@example.com",
                        units=Decimal("100"), cost_basis=Decimal("100000"),
                        join_date=date(2026, 1, 1))
        assert member.value_at_nav(Decimal("1050")) == Decimal("105000")

    def test_member_return_pct(self):
        member = Member(id="m1", name="Alice", email="alice@example.com",
                        units=Decimal("100"), cost_basis=Decimal("100000"),
                        join_date=date(2026, 1, 1))
        assert member.return_pct(Decimal("1050")) == pytest.approx(0.05, abs=0.001)


class TestTransaction:
    def test_create_subscription(self):
        tx = Transaction(member_id="m1", type=TransactionType.SUBSCRIBE,
                         units=Decimal("100"), nav_per_unit=Decimal("1000"),
                         amount=Decimal("100000"), fee_breakdown=FeeBreakdown(),
                         timestamp=datetime(2026, 1, 1, 12, 0, 0))
        assert tx.status == TransactionStatus.PENDING

    def test_fee_breakdown_total(self):
        fb = FeeBreakdown(management_fee=Decimal("167"), performance_fee=Decimal("1000"))
        assert fb.total == Decimal("1167")
