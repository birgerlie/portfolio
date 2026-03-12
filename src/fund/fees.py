"""Fee engine — management fee (2%), performance fee (20%), high-water mark."""

from decimal import Decimal, ROUND_HALF_UP
from fund.types import FeeBreakdown


class FeeEngine:
    def __init__(self, mgmt_fee_annual: Decimal = Decimal("0.02"),
                 perf_fee_rate: Decimal = Decimal("0.20")):
        self.mgmt_fee_annual = mgmt_fee_annual
        self.perf_fee_rate = perf_fee_rate

    def weekly_management_fee(self, nav: Decimal) -> Decimal:
        if nav <= 0:
            return Decimal("0")
        fee = nav * self.mgmt_fee_annual / Decimal("52")
        return fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def performance_fee(self, nav_per_unit: Decimal, high_water_mark: Decimal,
                        units_outstanding: Decimal) -> tuple[Decimal, Decimal]:
        if nav_per_unit <= high_water_mark:
            return Decimal("0"), high_water_mark
        gain_per_unit = nav_per_unit - high_water_mark
        fee = (gain_per_unit * units_outstanding * self.perf_fee_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        return fee, nav_per_unit

    def accrue_weekly(self, nav: Decimal, nav_per_unit: Decimal,
                      high_water_mark: Decimal, units_outstanding: Decimal) -> FeeBreakdown:
        mgmt = self.weekly_management_fee(nav)
        return FeeBreakdown(management_fee=mgmt, performance_fee=Decimal("0"))

    def crystallize_monthly(self, nav_per_unit: Decimal, high_water_mark: Decimal,
                            units_outstanding: Decimal) -> tuple[FeeBreakdown, Decimal]:
        perf_fee, new_hwm = self.performance_fee(nav_per_unit, high_water_mark, units_outstanding)
        return FeeBreakdown(management_fee=Decimal("0"), performance_fee=perf_fee), new_hwm
