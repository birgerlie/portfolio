"""Core data types for the fund engine."""

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional


class TransactionType(Enum):
    SUBSCRIBE = "subscribe"
    REDEEM = "redeem"


class TransactionStatus(Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    REJECTED = "rejected"


class MarketHealth(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class Momentum(Enum):
    RISING = "rising"
    STEADY = "steady"
    FALLING = "falling"


@dataclass
class FeeBreakdown:
    management_fee: Decimal = Decimal("0")
    performance_fee: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return self.management_fee + self.performance_fee


@dataclass
class Fund:
    nav: Decimal
    units_outstanding: Decimal
    high_water_mark: Decimal
    inception_date: date

    @property
    def nav_per_unit(self) -> Decimal:
        if self.units_outstanding == 0:
            return Decimal("0")
        return self.nav / self.units_outstanding


@dataclass
class Member:
    id: str
    name: str
    email: str
    units: Decimal
    cost_basis: Decimal
    join_date: date

    @property
    def lock_up_until(self) -> date:
        month = self.join_date.month + 3
        year = self.join_date.year
        if month > 12:
            month -= 12
            year += 1
        max_day = calendar.monthrange(year, month)[1]
        day = min(self.join_date.day, max_day)
        return date(year, month, day)

    def value_at_nav(self, nav_per_unit: Decimal) -> Decimal:
        return self.units * nav_per_unit

    def return_pct(self, nav_per_unit: Decimal) -> float:
        if self.cost_basis == 0:
            return 0.0
        current_value = self.value_at_nav(nav_per_unit)
        return float((current_value - self.cost_basis) / self.cost_basis)


@dataclass
class Transaction:
    member_id: str
    type: TransactionType
    units: Decimal
    nav_per_unit: Decimal
    amount: Decimal
    fee_breakdown: FeeBreakdown
    timestamp: datetime
    status: TransactionStatus = TransactionStatus.PENDING
    requires_liquidation: bool = False
    liquidation_amount: Decimal = Decimal("0")


@dataclass
class Instrument:
    symbol: str
    name: str
    asset_class: str
    thesis: str
    proposed_by: str
    added_date: date
    votes_for: int = 0


@dataclass
class EngineHealth:
    status: str
    alpaca_connected: bool
    last_trade: Optional[datetime]
    active_positions: int
    current_regime: str
    next_action: str
    next_action_at: Optional[datetime]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WeeklyNAV:
    date: date
    nav: Decimal
    nav_per_unit: Decimal
    gross_return_pct: float
    mgmt_fee_accrued: Decimal
    perf_fee_accrued: Decimal
    net_return_pct: float
    high_water_mark: Decimal
    clarity_score: float = 0.0
    opportunity_score: float = 0.0
    capture_rate: float = 0.0
    market_health: str = "green"
    momentum: str = "steady"
    benchmarks: Dict[str, float] = field(default_factory=dict)
    universe_equal_weight: float = 0.0
    universe_no_thermo: float = 0.0
    universe_best_possible: float = 0.0
    universe_random_avg: float = 0.0
    narrative_summary: str = ""
    position_narratives: Dict[str, str] = field(default_factory=dict)
