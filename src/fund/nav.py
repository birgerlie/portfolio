"""NAV calculator — weekly official and real-time indicative."""
from decimal import Decimal
from typing import Dict
from fund.fees import FeeEngine
from fund.types import FeeBreakdown


class NAVCalculator:
    def __init__(self, fee_engine: FeeEngine):
        self.fee_engine = fee_engine

    def gross_nav(self, positions: Dict[str, Dict], cash: Decimal) -> Decimal:
        position_value = sum(
            Decimal(str(pos["quantity"])) * Decimal(str(pos["price"]))
            for pos in positions.values())
        return position_value + cash

    def net_nav(self, gross_nav: Decimal, fees: FeeBreakdown) -> Decimal:
        return gross_nav - fees.total

    def return_pct(self, prev_nav: Decimal, curr_nav: Decimal) -> float:
        if prev_nav == 0:
            return 0.0
        return float((curr_nav - prev_nav) / prev_nav)
