"""Tests for NAV calculator."""
from decimal import Decimal
import pytest
from fund.nav import NAVCalculator
from fund.types import FeeBreakdown
from fund.fees import FeeEngine


class TestWeeklyNAV:
    def test_calculate_nav_from_positions(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        positions = {"NVDA": {"quantity": 100, "price": 150.0}, "AAPL": {"quantity": 200, "price": 200.0}}
        cash = Decimal("50000")
        gross_nav = calc.gross_nav(positions=positions, cash=cash)
        assert gross_nav == Decimal("105000")

    def test_net_nav_deducts_fees(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        fees = FeeBreakdown(management_fee=Decimal("384.62"), performance_fee=Decimal("0"))
        net = calc.net_nav(gross_nav=Decimal("1000000"), fees=fees)
        assert net == Decimal("999615.38")

    def test_weekly_return_pct(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        assert calc.return_pct(Decimal("1000000"), Decimal("1020000")) == pytest.approx(0.02, abs=0.0001)

    def test_weekly_return_pct_zero_prev(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        assert calc.return_pct(Decimal("0"), Decimal("100")) == 0.0

class TestIndicativeNAV:
    def test_indicative_nav_uses_live_prices(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        positions = {"NVDA": {"quantity": 100, "price": 160.0}}
        cash = Decimal("50000")
        nav = calc.gross_nav(positions=positions, cash=cash)
        assert nav == Decimal("66000")
