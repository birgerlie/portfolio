"""Tests for unit ledger — subscriptions, redemptions, lock-up."""

from datetime import date, datetime
from decimal import Decimal
import pytest
from fund.ledger import UnitLedger
from fund.types import Fund, Member, TransactionType, TransactionStatus


class TestSubscription:
    def test_subscribe_issues_units(self):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        member = Member(id="m1", name="Alice", email="a@b.com",
                        units=Decimal("0"), cost_basis=Decimal("0"), join_date=date(2026, 1, 1))
        tx = ledger.subscribe(fund=fund, member=member, amount=Decimal("100000"),
                              process_date=date(2026, 2, 1))
        assert tx.units == Decimal("100")
        assert tx.nav_per_unit == Decimal("1000")
        assert member.units == Decimal("100")
        assert member.cost_basis == Decimal("100000")
        assert fund.units_outstanding == Decimal("1100")
        assert fund.nav == Decimal("1100000")

    def test_subscribe_at_higher_nav(self):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1050000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1050"), inception_date=date(2026, 1, 1))
        member = Member(id="m2", name="Bob", email="b@b.com",
                        units=Decimal("0"), cost_basis=Decimal("0"), join_date=date(2026, 3, 1))
        tx = ledger.subscribe(fund=fund, member=member, amount=Decimal("105000"),
                              process_date=date(2026, 4, 1))
        assert tx.units == Decimal("100")
        assert tx.nav_per_unit == Decimal("1050")


class TestRedemption:
    def test_redeem_cancels_units(self):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1100000"), units_outstanding=Decimal("1100"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        member = Member(id="m1", name="Alice", email="a@b.com",
                        units=Decimal("100"), cost_basis=Decimal("100000"), join_date=date(2026, 1, 1))
        tx = ledger.redeem(fund=fund, member=member, units=Decimal("50"),
                           process_date=date(2026, 6, 1))
        assert tx.amount == Decimal("50000")
        assert member.units == Decimal("50")
        assert fund.units_outstanding == Decimal("1050")
        assert fund.nav == Decimal("1050000")

    def test_redeem_rejected_during_lockup(self):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        member = Member(id="m1", name="Alice", email="a@b.com",
                        units=Decimal("100"), cost_basis=Decimal("100000"),
                        join_date=date(2026, 3, 1))
        tx = ledger.redeem(fund=fund, member=member, units=Decimal("50"),
                           process_date=date(2026, 4, 1))
        assert tx.status == TransactionStatus.REJECTED
        assert member.units == Decimal("100")

    def test_redeem_insufficient_units(self):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        member = Member(id="m1", name="Alice", email="a@b.com",
                        units=Decimal("50"), cost_basis=Decimal("50000"), join_date=date(2026, 1, 1))
        tx = ledger.redeem(fund=fund, member=member, units=Decimal("100"),
                           process_date=date(2026, 6, 1))
        assert tx.status == TransactionStatus.REJECTED


class TestCashReserve:
    def test_redeem_within_cash(self):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        member = Member(id="m1", name="Alice", email="a@b.com",
                        units=Decimal("30"), cost_basis=Decimal("30000"), join_date=date(2026, 1, 1))
        tx = ledger.redeem(fund=fund, member=member, units=Decimal("30"),
                           process_date=date(2026, 6, 1), available_cash=Decimal("50000"))
        assert tx.status == TransactionStatus.PROCESSED
        assert tx.requires_liquidation is False

    def test_redeem_exceeds_cash(self):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        member = Member(id="m1", name="Alice", email="a@b.com",
                        units=Decimal("100"), cost_basis=Decimal("100000"), join_date=date(2026, 1, 1))
        tx = ledger.redeem(fund=fund, member=member, units=Decimal("100"),
                           process_date=date(2026, 6, 1), available_cash=Decimal("50000"))
        assert tx.status == TransactionStatus.PROCESSED
        assert tx.requires_liquidation is True
        assert tx.liquidation_amount == Decimal("50000")


class TestLedgerHistory:
    def test_transaction_history(self):
        ledger = UnitLedger()
        fund = Fund(nav=Decimal("1000000"), units_outstanding=Decimal("1000"),
                     high_water_mark=Decimal("1000"), inception_date=date(2026, 1, 1))
        member = Member(id="m1", name="Alice", email="a@b.com",
                        units=Decimal("0"), cost_basis=Decimal("0"), join_date=date(2026, 1, 1))
        ledger.subscribe(fund, member, Decimal("100000"), date(2026, 2, 1))
        ledger.subscribe(fund, member, Decimal("50000"), date(2026, 3, 1))
        history = ledger.get_history("m1")
        assert len(history) == 2
        assert history[0].type == TransactionType.SUBSCRIBE
