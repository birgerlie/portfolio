# Fund Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the fund engine — NAV calculation, unit accounting, fee math (2/20 with HWM), investment universe, benchmark comparison, thermodynamic metrics, engine heartbeat, and Supabase integration.

**Architecture:** A Python library (`src/fund/`) alongside the existing `src/trading_backtest/`. The fund engine consumes data from the trading engine (positions, beliefs, regime) and produces fund-level state (NAV, units, fees, metrics). It pushes snapshots to Supabase and sends heartbeats.

**Tech Stack:** Python 3.14, dataclasses, Decimal for money, supabase-py, pytest

**Spec:** `docs/superpowers/specs/2026-03-12-fund-platform-design.md`

---

## File Structure

```
src/fund/
├── __init__.py              # Public API exports
├── types.py                 # Core data types (Fund, Member, Transaction, WeeklyNAV, etc.)
├── nav.py                   # NAV calculator (weekly valuation, indicative NAV)
├── fees.py                  # Fee engine (management fee, performance fee, HWM)
├── ledger.py                # Unit ledger (subscriptions, redemptions, lock-up)
├── universe.py              # Investment universe (max 20, voting)
├── benchmarks.py            # Benchmark tracking + alternative universes
├── thermo_metrics.py        # Plain-language thermodynamic metrics
├── heartbeat.py             # Engine health monitor + Supabase push
└── snapshot.py              # Snapshot builder (assembles WeeklyNAV from all components)

tests/unit/fund/
├── __init__.py
├── test_types.py
├── test_nav.py
├── test_fees.py
├── test_ledger.py
├── test_universe.py
├── test_benchmarks.py
├── test_thermo_metrics.py
├── test_heartbeat.py
└── test_snapshot.py
```

---

## Chunk 1: Core Types and Fee Engine

### Task 1: Core Data Types

**Files:**
- Create: `src/fund/__init__.py`
- Create: `src/fund/types.py`
- Create: `tests/unit/fund/__init__.py`
- Create: `tests/unit/fund/test_types.py`

- [ ] **Step 1: Write failing tests for Fund, Member, Transaction types**

```python
# tests/unit/fund/test_types.py
"""Tests for fund core data types."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from fund.types import (
    Fund,
    Member,
    Transaction,
    TransactionType,
    TransactionStatus,
    FeeBreakdown,
)


class TestFund:
    def test_create_fund(self):
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        assert fund.nav_per_unit == Decimal("1000")

    def test_nav_per_unit_calculation(self):
        fund = Fund(
            nav=Decimal("1050000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        assert fund.nav_per_unit == Decimal("1050")

    def test_nav_per_unit_zero_units(self):
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("0"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        assert fund.nav_per_unit == Decimal("0")


class TestMember:
    def test_create_member(self):
        member = Member(
            id="m1",
            name="Alice",
            email="alice@example.com",
            units=Decimal("100"),
            cost_basis=Decimal("100000"),
            join_date=date(2026, 1, 1),
        )
        assert member.lock_up_until == date(2026, 4, 1)

    def test_member_value_at_nav(self):
        member = Member(
            id="m1",
            name="Alice",
            email="alice@example.com",
            units=Decimal("100"),
            cost_basis=Decimal("100000"),
            join_date=date(2026, 1, 1),
        )
        assert member.value_at_nav(Decimal("1050")) == Decimal("105000")

    def test_member_return_pct(self):
        member = Member(
            id="m1",
            name="Alice",
            email="alice@example.com",
            units=Decimal("100"),
            cost_basis=Decimal("100000"),
            join_date=date(2026, 1, 1),
        )
        # NAV went from 1000 to 1050 = 5% return
        assert member.return_pct(Decimal("1050")) == pytest.approx(0.05, abs=0.001)


class TestTransaction:
    def test_create_subscription(self):
        tx = Transaction(
            member_id="m1",
            type=TransactionType.SUBSCRIBE,
            units=Decimal("100"),
            nav_per_unit=Decimal("1000"),
            amount=Decimal("100000"),
            fee_breakdown=FeeBreakdown(),
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
        )
        assert tx.status == TransactionStatus.PENDING

    def test_fee_breakdown_total(self):
        fb = FeeBreakdown(
            management_fee=Decimal("167"),
            performance_fee=Decimal("1000"),
        )
        assert fb.total == Decimal("1167")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_types.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement types**

```python
# src/fund/__init__.py
"""Fund engine for NAV-based investment club."""

# src/fund/types.py
"""Core data types for the fund engine."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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
    """Breakdown of fees for a transaction or period."""

    management_fee: Decimal = Decimal("0")
    performance_fee: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return self.management_fee + self.performance_fee


@dataclass
class Fund:
    """Core fund state."""

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
    """Fund member."""

    id: str
    name: str
    email: str
    units: Decimal
    cost_basis: Decimal
    join_date: date

    @property
    def lock_up_until(self) -> date:
        """3-month lock-up from join date."""
        import calendar
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
    """Immutable ledger entry."""

    member_id: str
    type: TransactionType
    units: Decimal
    nav_per_unit: Decimal
    amount: Decimal
    fee_breakdown: FeeBreakdown
    timestamp: datetime
    status: TransactionStatus = TransactionStatus.PENDING


@dataclass
class Instrument:
    """An instrument in the investment universe."""

    symbol: str
    name: str
    asset_class: str  # "equity" or "etf"
    thesis: str
    proposed_by: str
    added_date: date
    votes_for: int = 0


@dataclass
class EngineHealth:
    """Health status of the trading engine on Mac."""

    status: str  # "running", "degraded", "stopped"
    alpaca_connected: bool
    last_trade: Optional[datetime]
    active_positions: int
    current_regime: str
    next_action: str
    next_action_at: Optional[datetime]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WeeklyNAV:
    """Weekly NAV snapshot with all metrics."""

    date: date
    nav: Decimal
    nav_per_unit: Decimal
    gross_return_pct: float
    mgmt_fee_accrued: Decimal
    perf_fee_accrued: Decimal
    net_return_pct: float
    high_water_mark: Decimal

    # Thermodynamic metrics
    clarity_score: float = 0.0
    opportunity_score: float = 0.0
    capture_rate: float = 0.0
    market_health: str = "green"
    momentum: str = "steady"

    # Benchmarks
    benchmarks: Dict[str, float] = field(default_factory=dict)

    # Alternative universes
    universe_equal_weight: float = 0.0
    universe_no_thermo: float = 0.0
    universe_best_possible: float = 0.0
    universe_random_avg: float = 0.0

    # Narratives
    narrative_summary: str = ""
    position_narratives: Dict[str, str] = field(default_factory=dict)
```

- [ ] **Step 4: Create tests/__init__.py**

```python
# tests/unit/fund/__init__.py
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_types.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/__init__.py src/fund/types.py tests/unit/fund/__init__.py tests/unit/fund/test_types.py
git commit -m "feat(fund): core data types — Fund, Member, Transaction, WeeklyNAV"
```

---

### Task 2: Fee Engine

**Files:**
- Create: `src/fund/fees.py`
- Create: `tests/unit/fund/test_fees.py`

- [ ] **Step 1: Write failing tests for fee calculations**

```python
# tests/unit/fund/test_fees.py
"""Tests for fee engine — management fee, performance fee, HWM."""

from decimal import Decimal

import pytest

from fund.fees import FeeEngine
from fund.types import FeeBreakdown


class TestManagementFee:
    def test_weekly_management_fee(self):
        engine = FeeEngine(mgmt_fee_annual=Decimal("0.02"))
        fee = engine.weekly_management_fee(nav=Decimal("1000000"))
        # 1,000,000 * 0.02 / 52 = 384.615...
        assert fee == pytest.approx(Decimal("384.62"), abs=Decimal("0.01"))

    def test_zero_nav(self):
        engine = FeeEngine()
        fee = engine.weekly_management_fee(nav=Decimal("0"))
        assert fee == Decimal("0")


class TestPerformanceFee:
    def test_performance_fee_above_hwm(self):
        engine = FeeEngine(perf_fee_rate=Decimal("0.20"))
        fee, new_hwm = engine.performance_fee(
            nav_per_unit=Decimal("1100"),
            high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"),
        )
        # Gain = 100 per unit * 1000 units = 100,000 * 20% = 20,000
        assert fee == Decimal("20000")
        assert new_hwm == Decimal("1100")

    def test_no_performance_fee_below_hwm(self):
        engine = FeeEngine()
        fee, new_hwm = engine.performance_fee(
            nav_per_unit=Decimal("950"),
            high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"),
        )
        assert fee == Decimal("0")
        assert new_hwm == Decimal("1000")  # HWM unchanged

    def test_no_performance_fee_at_hwm(self):
        engine = FeeEngine()
        fee, new_hwm = engine.performance_fee(
            nav_per_unit=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"),
        )
        assert fee == Decimal("0")
        assert new_hwm == Decimal("1000")

    def test_hwm_never_decreases(self):
        engine = FeeEngine()
        # First: gain above HWM
        _, hwm1 = engine.performance_fee(
            nav_per_unit=Decimal("1200"),
            high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"),
        )
        assert hwm1 == Decimal("1200")

        # Second: drop below HWM
        _, hwm2 = engine.performance_fee(
            nav_per_unit=Decimal("1100"),
            high_water_mark=hwm1,
            units_outstanding=Decimal("1000"),
        )
        assert hwm2 == Decimal("1200")  # Still 1200

    def test_recovery_no_double_charge(self):
        engine = FeeEngine(perf_fee_rate=Decimal("0.20"))
        # Rise to 1200, HWM = 1200
        fee1, hwm = engine.performance_fee(
            nav_per_unit=Decimal("1200"),
            high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("100"),
        )
        assert fee1 == Decimal("4000")  # 200 * 100 * 0.20

        # Drop to 1100, no fee
        fee2, hwm = engine.performance_fee(
            nav_per_unit=Decimal("1100"),
            high_water_mark=hwm,
            units_outstanding=Decimal("100"),
        )
        assert fee2 == Decimal("0")

        # Recover to 1200, no fee (just back to HWM)
        fee3, hwm = engine.performance_fee(
            nav_per_unit=Decimal("1200"),
            high_water_mark=hwm,
            units_outstanding=Decimal("100"),
        )
        assert fee3 == Decimal("0")

        # New high 1300, fee only on 1200→1300
        fee4, hwm = engine.performance_fee(
            nav_per_unit=Decimal("1300"),
            high_water_mark=hwm,
            units_outstanding=Decimal("100"),
        )
        assert fee4 == Decimal("2000")  # 100 * 100 * 0.20


class TestAccrueFees:
    def test_accrue_weekly(self):
        engine = FeeEngine()
        breakdown = engine.accrue_weekly(
            nav=Decimal("1000000"),
            nav_per_unit=Decimal("1050"),
            high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"),
        )
        assert breakdown.management_fee > 0
        # No perf fee accrual in weekly — only crystallized monthly
        assert breakdown.performance_fee == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_fees.py -v`
Expected: FAIL

- [ ] **Step 3: Implement fee engine**

```python
# src/fund/fees.py
"""Fee engine — management fee (2%), performance fee (20%), high-water mark."""

from decimal import Decimal, ROUND_HALF_UP


class FeeEngine:
    """Calculates fund fees."""

    def __init__(
        self,
        mgmt_fee_annual: Decimal = Decimal("0.02"),
        perf_fee_rate: Decimal = Decimal("0.20"),
    ):
        self.mgmt_fee_annual = mgmt_fee_annual
        self.perf_fee_rate = perf_fee_rate

    def weekly_management_fee(self, nav: Decimal) -> Decimal:
        """Calculate weekly management fee: NAV * annual_rate / 52."""
        if nav <= 0:
            return Decimal("0")
        fee = nav * self.mgmt_fee_annual / Decimal("52")
        return fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def performance_fee(
        self,
        nav_per_unit: Decimal,
        high_water_mark: Decimal,
        units_outstanding: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Calculate performance fee and updated HWM.

        Returns: (fee_amount, new_high_water_mark)
        """
        if nav_per_unit <= high_water_mark:
            return Decimal("0"), high_water_mark

        gain_per_unit = nav_per_unit - high_water_mark
        fee = (gain_per_unit * units_outstanding * self.perf_fee_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        new_hwm = nav_per_unit

        return fee, new_hwm

    def accrue_weekly(
        self,
        nav: Decimal,
        nav_per_unit: Decimal,
        high_water_mark: Decimal,
        units_outstanding: Decimal,
    ) -> "FeeBreakdown":
        """Accrue weekly fees. Performance fee only crystallized monthly."""
        from fund.types import FeeBreakdown

        mgmt = self.weekly_management_fee(nav)
        return FeeBreakdown(management_fee=mgmt, performance_fee=Decimal("0"))

    def crystallize_monthly(
        self,
        nav_per_unit: Decimal,
        high_water_mark: Decimal,
        units_outstanding: Decimal,
    ) -> tuple["FeeBreakdown", Decimal]:
        """Crystallize performance fee at month end. Returns (fees, new_hwm)."""
        from fund.types import FeeBreakdown

        perf_fee, new_hwm = self.performance_fee(
            nav_per_unit, high_water_mark, units_outstanding
        )
        return FeeBreakdown(management_fee=Decimal("0"), performance_fee=perf_fee), new_hwm
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_fees.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/fees.py tests/unit/fund/test_fees.py
git commit -m "feat(fund): fee engine — 2% management, 20% performance, HWM"
```

---

### Task 3: Unit Ledger (Subscriptions & Redemptions)

**Files:**
- Create: `src/fund/ledger.py`
- Create: `tests/unit/fund/test_ledger.py`

- [ ] **Step 1: Write failing tests for ledger operations**

```python
# tests/unit/fund/test_ledger.py
"""Tests for unit ledger — subscriptions, redemptions, lock-up."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from fund.ledger import UnitLedger
from fund.types import Fund, Member, TransactionType, TransactionStatus


class TestSubscription:
    def test_subscribe_issues_units(self):
        ledger = UnitLedger()
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m1", name="Alice", email="a@b.com",
            units=Decimal("0"), cost_basis=Decimal("0"),
            join_date=date(2026, 1, 1),
        )

        tx = ledger.subscribe(
            fund=fund,
            member=member,
            amount=Decimal("100000"),
            process_date=date(2026, 2, 1),
        )

        assert tx.units == Decimal("100")
        assert tx.nav_per_unit == Decimal("1000")
        assert member.units == Decimal("100")
        assert member.cost_basis == Decimal("100000")
        assert fund.units_outstanding == Decimal("1100")
        assert fund.nav == Decimal("1100000")

    def test_subscribe_at_higher_nav(self):
        ledger = UnitLedger()
        fund = Fund(
            nav=Decimal("1050000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1050"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m2", name="Bob", email="b@b.com",
            units=Decimal("0"), cost_basis=Decimal("0"),
            join_date=date(2026, 3, 1),
        )

        tx = ledger.subscribe(
            fund=fund,
            member=member,
            amount=Decimal("105000"),
            process_date=date(2026, 4, 1),
        )

        assert tx.units == Decimal("100")
        assert tx.nav_per_unit == Decimal("1050")


class TestRedemption:
    def test_redeem_cancels_units(self):
        ledger = UnitLedger()
        fund = Fund(
            nav=Decimal("1100000"),
            units_outstanding=Decimal("1100"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m1", name="Alice", email="a@b.com",
            units=Decimal("100"), cost_basis=Decimal("100000"),
            join_date=date(2026, 1, 1),
        )

        tx = ledger.redeem(
            fund=fund,
            member=member,
            units=Decimal("50"),
            process_date=date(2026, 6, 1),
        )

        assert tx.amount == Decimal("50000")
        assert member.units == Decimal("50")
        assert fund.units_outstanding == Decimal("1050")

    def test_redeem_rejected_during_lockup(self):
        ledger = UnitLedger()
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m1", name="Alice", email="a@b.com",
            units=Decimal("100"), cost_basis=Decimal("100000"),
            join_date=date(2026, 3, 1),  # Joined March, lock-up until June
        )

        tx = ledger.redeem(
            fund=fund,
            member=member,
            units=Decimal("50"),
            process_date=date(2026, 4, 1),  # April — still locked
        )

        assert tx.status == TransactionStatus.REJECTED
        assert member.units == Decimal("100")  # unchanged

    def test_redeem_insufficient_units(self):
        ledger = UnitLedger()
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m1", name="Alice", email="a@b.com",
            units=Decimal("50"), cost_basis=Decimal("50000"),
            join_date=date(2026, 1, 1),
        )

        tx = ledger.redeem(
            fund=fund,
            member=member,
            units=Decimal("100"),
            process_date=date(2026, 6, 1),
        )

        assert tx.status == TransactionStatus.REJECTED


class TestLedgerHistory:
    def test_transaction_history(self):
        ledger = UnitLedger()
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m1", name="Alice", email="a@b.com",
            units=Decimal("0"), cost_basis=Decimal("0"),
            join_date=date(2026, 1, 1),
        )

        ledger.subscribe(fund, member, Decimal("100000"), date(2026, 2, 1))
        ledger.subscribe(fund, member, Decimal("50000"), date(2026, 3, 1))

        history = ledger.get_history("m1")
        assert len(history) == 2
        assert history[0].type == TransactionType.SUBSCRIBE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_ledger.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ledger**

```python
# src/fund/ledger.py
"""Unit ledger — subscriptions, redemptions, lock-up enforcement."""

from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
from typing import List

from fund.types import (
    Fund,
    Member,
    Transaction,
    TransactionType,
    TransactionStatus,
    FeeBreakdown,
)


class UnitLedger:
    """Manages unit issuance and redemption."""

    def __init__(self):
        self._transactions: List[Transaction] = []

    def subscribe(
        self,
        fund: Fund,
        member: Member,
        amount: Decimal,
        process_date: date,
    ) -> Transaction:
        """Issue units to a member at current NAV."""
        nav_per_unit = fund.nav_per_unit
        units = (amount / nav_per_unit).quantize(Decimal("1"), rounding=ROUND_DOWN)

        # Update member
        member.units += units
        member.cost_basis += amount

        # Update fund
        fund.units_outstanding += units
        fund.nav += amount

        tx = Transaction(
            member_id=member.id,
            type=TransactionType.SUBSCRIBE,
            units=units,
            nav_per_unit=nav_per_unit,
            amount=amount,
            fee_breakdown=FeeBreakdown(),
            timestamp=datetime.combine(process_date, datetime.min.time()),
            status=TransactionStatus.PROCESSED,
        )
        self._transactions.append(tx)
        return tx

    def redeem(
        self,
        fund: Fund,
        member: Member,
        units: Decimal,
        process_date: date,
    ) -> Transaction:
        """Redeem units from a member at current NAV."""
        nav_per_unit = fund.nav_per_unit
        amount = units * nav_per_unit

        # Check lock-up
        if process_date < member.lock_up_until:
            tx = Transaction(
                member_id=member.id,
                type=TransactionType.REDEEM,
                units=units,
                nav_per_unit=nav_per_unit,
                amount=amount,
                fee_breakdown=FeeBreakdown(),
                timestamp=datetime.combine(process_date, datetime.min.time()),
                status=TransactionStatus.REJECTED,
            )
            self._transactions.append(tx)
            return tx

        # Check sufficient units
        if units > member.units:
            tx = Transaction(
                member_id=member.id,
                type=TransactionType.REDEEM,
                units=units,
                nav_per_unit=nav_per_unit,
                amount=amount,
                fee_breakdown=FeeBreakdown(),
                timestamp=datetime.combine(process_date, datetime.min.time()),
                status=TransactionStatus.REJECTED,
            )
            self._transactions.append(tx)
            return tx

        # Process redemption
        payout = units * nav_per_unit
        member.units -= units
        fund.units_outstanding -= units
        fund.nav -= payout

        tx = Transaction(
            member_id=member.id,
            type=TransactionType.REDEEM,
            units=units,
            nav_per_unit=nav_per_unit,
            amount=payout,
            fee_breakdown=FeeBreakdown(),
            timestamp=datetime.combine(process_date, datetime.min.time()),
            status=TransactionStatus.PROCESSED,
        )
        self._transactions.append(tx)
        return tx

    def get_history(self, member_id: str) -> List[Transaction]:
        """Get transaction history for a member."""
        return [tx for tx in self._transactions if tx.member_id == member_id]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_ledger.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/ledger.py tests/unit/fund/test_ledger.py
git commit -m "feat(fund): unit ledger — subscriptions, redemptions, lock-up"
```

---

## Chunk 2: NAV Calculator and Investment Universe

### Task 4: NAV Calculator

**Files:**
- Create: `src/fund/nav.py`
- Create: `tests/unit/fund/test_nav.py`

- [ ] **Step 1: Write failing tests for NAV calculation**

```python
# tests/unit/fund/test_nav.py
"""Tests for NAV calculator."""

from datetime import date
from decimal import Decimal

import pytest

from fund.nav import NAVCalculator
from fund.types import Fund, FeeBreakdown
from fund.fees import FeeEngine


class TestWeeklyNAV:
    def test_calculate_nav_from_positions(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        positions = {
            "NVDA": {"quantity": 100, "price": 150.0},
            "AAPL": {"quantity": 200, "price": 200.0},
        }
        cash = Decimal("50000")

        gross_nav = calc.gross_nav(positions=positions, cash=cash)
        # 100*150 + 200*200 + 50000 = 15000 + 40000 + 50000 = 105000
        assert gross_nav == Decimal("105000")

    def test_net_nav_deducts_fees(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        gross = Decimal("1000000")
        fees = FeeBreakdown(
            management_fee=Decimal("384.62"),
            performance_fee=Decimal("0"),
        )

        net = calc.net_nav(gross_nav=gross, fees=fees)
        assert net == Decimal("999615.38")

    def test_weekly_return_pct(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        prev_nav = Decimal("1000000")
        curr_nav = Decimal("1020000")

        pct = calc.return_pct(prev_nav, curr_nav)
        assert pct == pytest.approx(0.02, abs=0.0001)

    def test_weekly_return_pct_zero_prev(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        assert calc.return_pct(Decimal("0"), Decimal("100")) == 0.0


class TestIndicativeNAV:
    def test_indicative_nav_uses_live_prices(self):
        calc = NAVCalculator(fee_engine=FeeEngine())
        positions = {
            "NVDA": {"quantity": 100, "price": 160.0},  # price changed
        }
        cash = Decimal("50000")

        nav = calc.gross_nav(positions=positions, cash=cash)
        assert nav == Decimal("66000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_nav.py -v`
Expected: FAIL

- [ ] **Step 3: Implement NAV calculator**

```python
# src/fund/nav.py
"""NAV calculator — weekly official and real-time indicative."""

from decimal import Decimal
from typing import Dict

from fund.fees import FeeEngine
from fund.types import FeeBreakdown


class NAVCalculator:
    """Calculates fund NAV from positions and cash."""

    def __init__(self, fee_engine: FeeEngine):
        self.fee_engine = fee_engine

    def gross_nav(
        self,
        positions: Dict[str, Dict],
        cash: Decimal,
    ) -> Decimal:
        """Calculate gross NAV from positions and cash.

        positions: {symbol: {quantity: float, price: float}}
        """
        position_value = sum(
            Decimal(str(pos["quantity"])) * Decimal(str(pos["price"]))
            for pos in positions.values()
        )
        return position_value + cash

    def net_nav(self, gross_nav: Decimal, fees: FeeBreakdown) -> Decimal:
        """Calculate net NAV after fee deductions."""
        return gross_nav - fees.total

    def return_pct(self, prev_nav: Decimal, curr_nav: Decimal) -> float:
        """Calculate return percentage between two NAV values."""
        if prev_nav == 0:
            return 0.0
        return float((curr_nav - prev_nav) / prev_nav)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_nav.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/nav.py tests/unit/fund/test_nav.py
git commit -m "feat(fund): NAV calculator — gross, net, return pct"
```

---

### Task 5: Investment Universe

**Files:**
- Create: `src/fund/universe.py`
- Create: `tests/unit/fund/test_universe.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_universe.py
"""Tests for investment universe — max 20, voting."""

from datetime import date

import pytest

from fund.universe import InvestmentUniverse
from fund.types import Instrument


class TestUniverse:
    def test_add_instrument(self):
        universe = InvestmentUniverse()
        inst = Instrument(
            symbol="NVDA", name="Nvidia", asset_class="equity",
            thesis="AI compute leader", proposed_by="Alice",
            added_date=date(2026, 1, 1),
        )
        universe.add(inst)
        assert len(universe.instruments) == 1
        assert universe.get("NVDA") == inst

    def test_max_20_instruments(self):
        universe = InvestmentUniverse(max_size=20)
        for i in range(20):
            universe.add(Instrument(
                symbol=f"SYM{i}", name=f"Stock {i}", asset_class="equity",
                thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1),
            ))
        assert len(universe.instruments) == 20

        with pytest.raises(ValueError, match="full"):
            universe.add(Instrument(
                symbol="SYM20", name="Stock 20", asset_class="equity",
                thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1),
            ))

    def test_remove_instrument(self):
        universe = InvestmentUniverse()
        universe.add(Instrument(
            symbol="NVDA", name="Nvidia", asset_class="equity",
            thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1),
        ))
        universe.remove("NVDA")
        assert len(universe.instruments) == 0

    def test_vote_for_instrument(self):
        universe = InvestmentUniverse()
        universe.add(Instrument(
            symbol="NVDA", name="Nvidia", asset_class="equity",
            thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1),
        ))
        universe.vote("NVDA", votes=3)
        assert universe.get("NVDA").votes_for == 3

    def test_drop_lowest_voted(self):
        universe = InvestmentUniverse(max_size=3)
        for i, sym in enumerate(["A", "B", "C"]):
            universe.add(Instrument(
                symbol=sym, name=sym, asset_class="equity",
                thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1),
                votes_for=i,  # A=0, B=1, C=2
            ))

        dropped = universe.drop_lowest()
        assert dropped.symbol == "A"
        assert len(universe.instruments) == 2

    def test_symbols_list(self):
        universe = InvestmentUniverse()
        universe.add(Instrument(
            symbol="NVDA", name="Nvidia", asset_class="equity",
            thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1),
        ))
        universe.add(Instrument(
            symbol="AAPL", name="Apple", asset_class="equity",
            thesis="test", proposed_by="Bob", added_date=date(2026, 1, 1),
        ))
        assert set(universe.symbols) == {"NVDA", "AAPL"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_universe.py -v`
Expected: FAIL

- [ ] **Step 3: Implement investment universe**

```python
# src/fund/universe.py
"""Investment universe — curated list of max 20 instruments."""

from typing import Dict, List, Optional

from fund.types import Instrument


class InvestmentUniverse:
    """Manages the fund's tradeable instrument list."""

    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        self._instruments: Dict[str, Instrument] = {}

    @property
    def instruments(self) -> List[Instrument]:
        return list(self._instruments.values())

    @property
    def symbols(self) -> List[str]:
        return list(self._instruments.keys())

    def get(self, symbol: str) -> Optional[Instrument]:
        return self._instruments.get(symbol)

    def add(self, instrument: Instrument) -> None:
        if len(self._instruments) >= self.max_size:
            raise ValueError(
                f"Universe is full ({self.max_size}). "
                "Remove an instrument or drop lowest-voted first."
            )
        self._instruments[instrument.symbol] = instrument

    def remove(self, symbol: str) -> None:
        self._instruments.pop(symbol, None)

    def vote(self, symbol: str, votes: int) -> None:
        if symbol in self._instruments:
            self._instruments[symbol].votes_for = votes

    def drop_lowest(self) -> Instrument:
        """Drop and return the instrument with fewest votes."""
        if not self._instruments:
            raise ValueError("Universe is empty")
        lowest = min(self._instruments.values(), key=lambda i: i.votes_for)
        del self._instruments[lowest.symbol]
        return lowest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_universe.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/universe.py tests/unit/fund/test_universe.py
git commit -m "feat(fund): investment universe — max 20, voting, drop lowest"
```

---

## Chunk 3: Benchmarks and Thermodynamic Metrics

### Task 6: Benchmark Engine

**Files:**
- Create: `src/fund/benchmarks.py`
- Create: `tests/unit/fund/test_benchmarks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_benchmarks.py
"""Tests for benchmark engine — standard benchmarks + alternative universes."""

import pytest

from fund.benchmarks import BenchmarkEngine


class TestBenchmarkComparison:
    def test_cumulative_return(self):
        engine = BenchmarkEngine()
        values = [100.0, 105.0, 110.0, 108.0, 115.0]
        assert engine.cumulative_return(values) == pytest.approx(0.15, abs=0.001)

    def test_cumulative_return_empty(self):
        engine = BenchmarkEngine()
        assert engine.cumulative_return([]) == 0.0

    def test_alpha_vs_benchmark(self):
        engine = BenchmarkEngine()
        fund_return = 0.15
        benchmark_return = 0.10
        assert engine.alpha(fund_return, benchmark_return) == pytest.approx(0.05)

    def test_compare_all_benchmarks(self):
        engine = BenchmarkEngine()
        fund_values = [100.0, 110.0, 120.0]
        benchmark_values = {
            "SPY": [100.0, 105.0, 108.0],
            "QQQ": [100.0, 108.0, 115.0],
        }
        result = engine.compare(fund_values, benchmark_values)
        assert "SPY" in result
        assert "QQQ" in result
        assert result["SPY"]["alpha"] > 0


class TestAlternativeUniverses:
    def test_equal_weight_return(self):
        engine = BenchmarkEngine()
        # 3 stocks, each with daily returns
        stock_returns = {
            "A": [0.01, 0.02, -0.01],
            "B": [-0.01, 0.03, 0.02],
            "C": [0.02, -0.01, 0.01],
        }
        eq_return = engine.equal_weight_return(stock_returns)
        # Day 1: avg(0.01, -0.01, 0.02) = 0.00667
        # Cumulative should be positive
        assert eq_return > 0

    def test_best_possible_return(self):
        engine = BenchmarkEngine()
        stock_returns = {
            "A": [0.05, -0.02, 0.01],
            "B": [-0.01, 0.08, -0.03],
            "C": [0.02, 0.01, 0.10],
        }
        best = engine.best_daily_pick_return(stock_returns)
        # Best each day: A(0.05), B(0.08), C(0.10)
        # Compound: 1.05 * 1.08 * 1.10 - 1 = 0.2474
        assert best == pytest.approx(0.2474, abs=0.001)

    def test_random_portfolio_return(self):
        engine = BenchmarkEngine()
        stock_returns = {
            "A": [0.01, 0.02],
            "B": [-0.01, 0.03],
        }
        median = engine.random_portfolio_median(stock_returns, n_simulations=100)
        # Should be a float, roughly between the returns
        assert isinstance(median, float)


class TestCaptureRate:
    def test_capture_rate(self):
        engine = BenchmarkEngine()
        actual = 0.15
        best_possible = 0.25
        assert engine.capture_rate(actual, best_possible) == pytest.approx(60.0)

    def test_capture_rate_zero_best(self):
        engine = BenchmarkEngine()
        assert engine.capture_rate(0.10, 0.0) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_benchmarks.py -v`
Expected: FAIL

- [ ] **Step 3: Implement benchmark engine**

```python
# src/fund/benchmarks.py
"""Benchmark engine — standard benchmarks and alternative universe comparison."""

import random
from typing import Dict, List


class BenchmarkEngine:
    """Compares fund performance against benchmarks and alternative universes."""

    def cumulative_return(self, values: List[float]) -> float:
        """Calculate cumulative return from a series of values."""
        if len(values) < 2:
            return 0.0
        return (values[-1] - values[0]) / values[0]

    def alpha(self, fund_return: float, benchmark_return: float) -> float:
        """Calculate alpha (excess return over benchmark)."""
        return fund_return - benchmark_return

    def compare(
        self,
        fund_values: List[float],
        benchmark_values: Dict[str, List[float]],
    ) -> Dict[str, Dict[str, float]]:
        """Compare fund against multiple benchmarks."""
        fund_return = self.cumulative_return(fund_values)
        result = {}
        for name, values in benchmark_values.items():
            bench_return = self.cumulative_return(values)
            result[name] = {
                "return": bench_return,
                "alpha": self.alpha(fund_return, bench_return),
            }
        return result

    def equal_weight_return(self, stock_returns: Dict[str, List[float]]) -> float:
        """Calculate return of equal-weight portfolio across all stocks."""
        if not stock_returns:
            return 0.0
        symbols = list(stock_returns.keys())
        n_days = len(next(iter(stock_returns.values())))
        cumulative = 1.0
        for day in range(n_days):
            daily_avg = sum(stock_returns[s][day] for s in symbols) / len(symbols)
            cumulative *= (1 + daily_avg)
        return cumulative - 1

    def best_daily_pick_return(self, stock_returns: Dict[str, List[float]]) -> float:
        """Calculate return if you picked the best stock each day."""
        if not stock_returns:
            return 0.0
        symbols = list(stock_returns.keys())
        n_days = len(next(iter(stock_returns.values())))
        cumulative = 1.0
        for day in range(n_days):
            best = max(stock_returns[s][day] for s in symbols)
            cumulative *= (1 + best)
        return cumulative - 1

    def random_portfolio_median(
        self,
        stock_returns: Dict[str, List[float]],
        n_simulations: int = 1000,
    ) -> float:
        """Monte Carlo: median return of random portfolios."""
        if not stock_returns:
            return 0.0
        symbols = list(stock_returns.keys())
        n_days = len(next(iter(stock_returns.values())))
        results = []
        for _ in range(n_simulations):
            # Random weights that sum to 1
            weights = [random.random() for _ in symbols]
            total = sum(weights)
            weights = [w / total for w in weights]

            cumulative = 1.0
            for day in range(n_days):
                daily = sum(
                    weights[i] * stock_returns[s][day]
                    for i, s in enumerate(symbols)
                )
                cumulative *= (1 + daily)
            results.append(cumulative - 1)

        results.sort()
        return results[len(results) // 2]

    def capture_rate(self, actual: float, best_possible: float) -> float:
        """What % of the best possible return did we capture?"""
        if best_possible <= 0:
            return 0.0
        return (actual / best_possible) * 100
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_benchmarks.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/benchmarks.py tests/unit/fund/test_benchmarks.py
git commit -m "feat(fund): benchmark engine — comparison + alternative universes"
```

---

### Task 7: Thermodynamic Metrics (Plain Language)

**Files:**
- Create: `src/fund/thermo_metrics.py`
- Create: `tests/unit/fund/test_thermo_metrics.py`
- Reference: `docs/MAXWELL-RELATIONS-IN-PORTFOLIO-SYSTEM.md`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_thermo_metrics.py
"""Tests for plain-language thermodynamic metrics."""

import math

import pytest

from fund.thermo_metrics import ThermoMetrics


class TestClarity:
    def test_full_clarity(self):
        """Conviction at 1.0 means entropy = 0, clarity = 100%."""
        metrics = ThermoMetrics()
        # Single position with p=0.99 (near certain)
        beliefs = {"NVDA": 0.99}
        clarity = metrics.clarity_score(beliefs)
        assert clarity > 90

    def test_zero_clarity(self):
        """Conviction at 0.5 means max entropy, clarity near 0."""
        metrics = ThermoMetrics()
        beliefs = {"NVDA": 0.5}
        clarity = metrics.clarity_score(beliefs)
        assert clarity < 10

    def test_mixed_clarity(self):
        metrics = ThermoMetrics()
        beliefs = {"NVDA": 0.88, "AAPL": 0.52, "MSFT": 0.75}
        clarity = metrics.clarity_score(beliefs)
        assert 30 < clarity < 80


class TestOpportunity:
    def test_high_opportunity(self):
        metrics = ThermoMetrics()
        # High conviction + low volatility = high Φ
        score = metrics.opportunity_score(
            beliefs={"NVDA": 0.88},
            volatility=0.18,
        )
        assert score > 60

    def test_low_opportunity(self):
        metrics = ThermoMetrics()
        # Low conviction + high volatility = low Φ
        score = metrics.opportunity_score(
            beliefs={"NVDA": 0.52},
            volatility=0.45,
        )
        assert score < 30


class TestMarketHealth:
    def test_green(self):
        metrics = ThermoMetrics()
        assert metrics.market_health(volatility=0.15) == "green"

    def test_yellow(self):
        metrics = ThermoMetrics()
        assert metrics.market_health(volatility=0.35) == "yellow"

    def test_red(self):
        metrics = ThermoMetrics()
        assert metrics.market_health(volatility=0.48) == "red"


class TestMomentum:
    def test_rising(self):
        metrics = ThermoMetrics()
        # Beliefs increasing over time
        prev = {"NVDA": 0.70, "AAPL": 0.60}
        curr = {"NVDA": 0.80, "AAPL": 0.65}
        assert metrics.momentum(prev, curr) == "rising"

    def test_falling(self):
        metrics = ThermoMetrics()
        prev = {"NVDA": 0.80, "AAPL": 0.65}
        curr = {"NVDA": 0.60, "AAPL": 0.55}
        assert metrics.momentum(prev, curr) == "falling"

    def test_steady(self):
        metrics = ThermoMetrics()
        prev = {"NVDA": 0.75, "AAPL": 0.60}
        curr = {"NVDA": 0.76, "AAPL": 0.59}
        assert metrics.momentum(prev, curr) == "steady"


class TestInterpretation:
    def test_generates_text(self):
        metrics = ThermoMetrics()
        text = metrics.interpret(
            clarity=82.0, opportunity=71.0, health="green", momentum="rising",
        )
        assert isinstance(text, str)
        assert len(text) > 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_thermo_metrics.py -v`
Expected: FAIL

- [ ] **Step 3: Implement thermo metrics**

```python
# src/fund/thermo_metrics.py
"""Plain-language thermodynamic metrics for the dashboard.

Translates Shannon entropy, portfolio potential, and volatility
into Clarity, Opportunity, Market Health, and Momentum.
"""

import math
from typing import Dict


class ThermoMetrics:
    """Computes plain-language metrics from thermodynamic state."""

    # Volatility thresholds for market health
    SIGMA_GREEN = 0.25
    SIGMA_YELLOW = 0.40
    SIGMA_CRIT = 0.50

    # Momentum threshold (average dp)
    MOMENTUM_THRESHOLD = 0.03

    def _shannon_entropy(self, p: float) -> float:
        """S(p) = -p*ln(p) - (1-p)*ln(1-p)."""
        if p <= 0 or p >= 1:
            return 0.0
        return -p * math.log(p) - (1 - p) * math.log(1 - p)

    def clarity_score(self, beliefs: Dict[str, float]) -> float:
        """Portfolio clarity: 0-100%. High = system is confident.

        Derived from: 1 - average_entropy, normalized to 0-100.
        Max entropy (p=0.5) = ln(2) ≈ 0.693.
        """
        if not beliefs:
            return 0.0
        max_entropy = math.log(2)
        avg_entropy = sum(self._shannon_entropy(p) for p in beliefs.values()) / len(beliefs)
        clarity = (1 - avg_entropy / max_entropy) * 100
        return max(0.0, min(100.0, clarity))

    def opportunity_score(
        self, beliefs: Dict[str, float], volatility: float
    ) -> float:
        """Opportunity score: 0-100. High = lots of upside available.

        Derived from portfolio potential: Φ = E[R] - σ*S
        Normalized to 0-100 scale.
        """
        if not beliefs:
            return 0.0

        # Simplified: average excess conviction * (1 - vol_penalty)
        avg_conviction = sum(abs(p - 0.5) for p in beliefs.values()) / len(beliefs)
        avg_entropy = sum(self._shannon_entropy(p) for p in beliefs.values()) / len(beliefs)

        # Φ approximation: conviction strength minus volatility-entropy drag
        phi = avg_conviction - volatility * avg_entropy
        # Normalize: phi ranges roughly from -0.3 to +0.5
        score = (phi + 0.3) / 0.8 * 100
        return max(0.0, min(100.0, score))

    def market_health(self, volatility: float) -> str:
        """Market health gauge based on volatility distance from critical point."""
        if volatility < self.SIGMA_GREEN:
            return "green"
        elif volatility < self.SIGMA_YELLOW:
            return "yellow"
        else:
            return "red"

    def momentum(
        self, prev_beliefs: Dict[str, float], curr_beliefs: Dict[str, float]
    ) -> str:
        """Is overall conviction rising, steady, or falling?"""
        common = set(prev_beliefs) & set(curr_beliefs)
        if not common:
            return "steady"
        avg_dp = sum(curr_beliefs[s] - prev_beliefs[s] for s in common) / len(common)
        if avg_dp > self.MOMENTUM_THRESHOLD:
            return "rising"
        elif avg_dp < -self.MOMENTUM_THRESHOLD:
            return "falling"
        return "steady"

    def interpret(
        self,
        clarity: float,
        opportunity: float,
        health: str,
        momentum: str,
    ) -> str:
        """Generate plain-language interpretation of current state."""
        if clarity > 70 and opportunity > 60 and health == "green":
            return (
                "High conviction, good opportunity, calm market. "
                "System is running at full capacity."
            )
        elif clarity > 50 and health in ("green", "yellow"):
            return (
                "Moderate conviction with some uncertainty. "
                "System is selectively positioned."
            )
        elif health == "red":
            return (
                "Dangerous market conditions. "
                "System has moved to minimum exposure."
            )
        elif clarity < 30:
            return (
                "Mixed signals, limited opportunity. "
                "System is sizing positions conservatively."
            )
        else:
            return (
                f"Clarity at {clarity:.0f}%, opportunity at {opportunity:.0f}. "
                f"Market health: {health}. Momentum: {momentum}."
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_thermo_metrics.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/thermo_metrics.py tests/unit/fund/test_thermo_metrics.py
git commit -m "feat(fund): thermodynamic metrics — clarity, opportunity, health, momentum"
```

---

## Chunk 4: Heartbeat, Snapshot, and Integration

### Task 8: Engine Heartbeat

**Files:**
- Create: `src/fund/heartbeat.py`
- Create: `tests/unit/fund/test_heartbeat.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_heartbeat.py
"""Tests for engine heartbeat."""

from datetime import datetime, timedelta

import pytest

from fund.heartbeat import HealthMonitor
from fund.types import EngineHealth


class TestHealthMonitor:
    def test_create_heartbeat(self):
        monitor = HealthMonitor()
        hb = monitor.create_heartbeat(
            alpaca_connected=True,
            last_trade=datetime(2026, 3, 12, 10, 0),
            active_positions=5,
            current_regime="bull",
            next_action="rebalance",
            next_action_at=datetime(2026, 3, 14, 9, 30),
        )
        assert hb.status == "running"
        assert hb.alpaca_connected is True

    def test_degraded_when_alpaca_down(self):
        monitor = HealthMonitor()
        hb = monitor.create_heartbeat(
            alpaca_connected=False,
            last_trade=None,
            active_positions=0,
            current_regime="unknown",
            next_action="reconnect",
            next_action_at=None,
        )
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_heartbeat.py -v`
Expected: FAIL

- [ ] **Step 3: Implement heartbeat**

```python
# src/fund/heartbeat.py
"""Engine health monitor — heartbeat creation and status evaluation."""

from datetime import datetime, timedelta
from typing import Optional

from fund.types import EngineHealth


class HealthMonitor:
    """Creates heartbeats and evaluates engine status."""

    HEARTBEAT_GREEN = timedelta(minutes=2)
    HEARTBEAT_YELLOW = timedelta(minutes=5)
    NOTIFY_MANAGER = timedelta(minutes=5)
    NOTIFY_MEMBERS = timedelta(minutes=15)

    def create_heartbeat(
        self,
        alpaca_connected: bool,
        last_trade: Optional[datetime],
        active_positions: int,
        current_regime: str,
        next_action: str,
        next_action_at: Optional[datetime],
    ) -> EngineHealth:
        """Create a heartbeat snapshot."""
        status = "running" if alpaca_connected else "degraded"

        return EngineHealth(
            status=status,
            alpaca_connected=alpaca_connected,
            last_trade=last_trade,
            active_positions=active_positions,
            current_regime=current_regime,
            next_action=next_action,
            next_action_at=next_action_at,
        )

    def display_status(self, last_heartbeat: datetime) -> str:
        """Determine dashboard status color from last heartbeat time."""
        age = datetime.now() - last_heartbeat
        if age < self.HEARTBEAT_GREEN:
            return "green"
        elif age < self.HEARTBEAT_YELLOW:
            return "yellow"
        return "red"

    def should_notify_manager(self, last_heartbeat: datetime) -> bool:
        """Should we alert the fund manager?"""
        return (datetime.now() - last_heartbeat) > self.NOTIFY_MANAGER

    def should_notify_members(self, last_heartbeat: datetime) -> bool:
        """Should we alert all members?"""
        return (datetime.now() - last_heartbeat) > self.NOTIFY_MEMBERS
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_heartbeat.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/heartbeat.py tests/unit/fund/test_heartbeat.py
git commit -m "feat(fund): engine heartbeat — health monitor and status"
```

---

### Task 9: Snapshot Builder

**Files:**
- Create: `src/fund/snapshot.py`
- Create: `tests/unit/fund/test_snapshot.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_snapshot.py
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
            benchmark_engine=BenchmarkEngine(),
        )

    def test_build_snapshot(self):
        builder = self._make_builder()
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        positions = {
            "NVDA": {"quantity": 100, "price": 150.0},
        }
        beliefs = {"NVDA": 0.85}
        prev_beliefs = {"NVDA": 0.80}

        snapshot = builder.build(
            fund=fund,
            positions=positions,
            cash=Decimal("985000"),
            beliefs=beliefs,
            prev_beliefs=prev_beliefs,
            volatility=0.20,
            prev_nav=Decimal("990000"),
            snapshot_date=date(2026, 3, 14),
            benchmark_values={},
            stock_returns={},
        )

        assert isinstance(snapshot, WeeklyNAV)
        assert snapshot.date == date(2026, 3, 14)
        assert snapshot.nav > 0
        assert snapshot.clarity_score > 0
        assert snapshot.market_health == "green"

    def test_snapshot_includes_fees(self):
        builder = self._make_builder()
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )

        snapshot = builder.build(
            fund=fund,
            positions={},
            cash=Decimal("1000000"),
            beliefs={},
            prev_beliefs={},
            volatility=0.20,
            prev_nav=Decimal("1000000"),
            snapshot_date=date(2026, 3, 14),
            benchmark_values={},
            stock_returns={},
        )

        assert snapshot.mgmt_fee_accrued > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_snapshot.py -v`
Expected: FAIL

- [ ] **Step 3: Implement snapshot builder**

```python
# src/fund/snapshot.py
"""Snapshot builder — assembles WeeklyNAV from all fund components."""

from datetime import date
from decimal import Decimal
from typing import Dict

from fund.types import Fund, WeeklyNAV
from fund.fees import FeeEngine
from fund.nav import NAVCalculator
from fund.thermo_metrics import ThermoMetrics
from fund.benchmarks import BenchmarkEngine


class SnapshotBuilder:
    """Assembles a complete WeeklyNAV snapshot."""

    def __init__(
        self,
        nav_calculator: NAVCalculator,
        fee_engine: FeeEngine,
        thermo_metrics: ThermoMetrics,
        benchmark_engine: BenchmarkEngine,
    ):
        self.nav_calc = nav_calculator
        self.fee_engine = fee_engine
        self.thermo = thermo_metrics
        self.benchmarks = benchmark_engine

    def build(
        self,
        fund: Fund,
        positions: Dict[str, Dict],
        cash: Decimal,
        beliefs: Dict[str, float],
        prev_beliefs: Dict[str, float],
        volatility: float,
        prev_nav: Decimal,
        snapshot_date: date,
        benchmark_values: Dict[str, list],
        stock_returns: Dict[str, list],
    ) -> WeeklyNAV:
        """Build a complete weekly snapshot."""
        # NAV
        gross = self.nav_calc.gross_nav(positions, cash)
        fees = self.fee_engine.accrue_weekly(
            nav=gross,
            nav_per_unit=fund.nav_per_unit,
            high_water_mark=fund.high_water_mark,
            units_outstanding=fund.units_outstanding,
        )
        net = self.nav_calc.net_nav(gross, fees)
        nav_per_unit = (
            net / fund.units_outstanding
            if fund.units_outstanding > 0
            else Decimal("0")
        )
        gross_return = self.nav_calc.return_pct(prev_nav, gross)
        net_return = self.nav_calc.return_pct(prev_nav, net)

        # Thermodynamic metrics
        clarity = self.thermo.clarity_score(beliefs)
        opportunity = self.thermo.opportunity_score(beliefs, volatility)
        health = self.thermo.market_health(volatility)
        momentum = self.thermo.momentum(prev_beliefs, beliefs)
        interpretation = self.thermo.interpret(clarity, opportunity, health, momentum)

        # Benchmarks
        bench_results = {}
        if benchmark_values:
            fund_values = [float(prev_nav), float(net)]
            bench_results = {
                name: self.benchmarks.cumulative_return(vals)
                for name, vals in benchmark_values.items()
            }

        # Alternative universes
        eq_weight = self.benchmarks.equal_weight_return(stock_returns) if stock_returns else 0.0
        best = self.benchmarks.best_daily_pick_return(stock_returns) if stock_returns else 0.0
        rand = self.benchmarks.random_portfolio_median(stock_returns) if stock_returns else 0.0
        capture = self.benchmarks.capture_rate(net_return, best) if best > 0 else 0.0

        return WeeklyNAV(
            date=snapshot_date,
            nav=net,
            nav_per_unit=nav_per_unit,
            gross_return_pct=gross_return,
            mgmt_fee_accrued=fees.management_fee,
            perf_fee_accrued=fees.performance_fee,
            net_return_pct=net_return,
            high_water_mark=fund.high_water_mark,
            clarity_score=clarity,
            opportunity_score=opportunity,
            capture_rate=capture,
            market_health=health,
            momentum=momentum,
            benchmarks=bench_results,
            universe_equal_weight=eq_weight,
            universe_no_thermo=0.0,  # Requires backtest infrastructure
            universe_best_possible=best,
            universe_random_avg=rand,
            narrative_summary=interpretation,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_snapshot.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/snapshot.py tests/unit/fund/test_snapshot.py
git commit -m "feat(fund): snapshot builder — assembles WeeklyNAV from all components"
```

---

### Task 10: Public API and Exports

**Files:**
- Modify: `src/fund/__init__.py`

- [ ] **Step 1: Update __init__.py with public exports**

```python
# src/fund/__init__.py
"""Fund engine for NAV-based investment club.

Core components:
- NAVCalculator: weekly and indicative NAV
- FeeEngine: 2% management + 20% performance with HWM
- UnitLedger: subscriptions, redemptions, lock-up
- InvestmentUniverse: max 20 instruments, monthly voting
- BenchmarkEngine: standard + alternative universe comparison
- ThermoMetrics: plain-language thermodynamic gauges
- HealthMonitor: engine heartbeat and status
- SnapshotBuilder: assembles complete WeeklyNAV
"""

from fund.types import (
    Fund,
    Member,
    Transaction,
    TransactionType,
    TransactionStatus,
    FeeBreakdown,
    Instrument,
    EngineHealth,
    WeeklyNAV,
    MarketHealth,
    Momentum,
)
from fund.nav import NAVCalculator
from fund.fees import FeeEngine
from fund.ledger import UnitLedger
from fund.universe import InvestmentUniverse
from fund.benchmarks import BenchmarkEngine
from fund.thermo_metrics import ThermoMetrics
from fund.heartbeat import HealthMonitor
from fund.snapshot import SnapshotBuilder

__all__ = [
    "Fund",
    "Member",
    "Transaction",
    "TransactionType",
    "TransactionStatus",
    "FeeBreakdown",
    "Instrument",
    "EngineHealth",
    "WeeklyNAV",
    "MarketHealth",
    "Momentum",
    "NAVCalculator",
    "FeeEngine",
    "UnitLedger",
    "InvestmentUniverse",
    "BenchmarkEngine",
    "ThermoMetrics",
    "HealthMonitor",
    "SnapshotBuilder",
]
```

- [ ] **Step 2: Run all fund tests**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/__init__.py
git commit -m "feat(fund): public API exports"
```

---

## Chunk 5: Cash Reserve, Monthly Crystallization, and Property Tests

### Task 11: Cash Reserve Management

**Files:**
- Modify: `src/fund/ledger.py`
- Modify: `tests/unit/fund/test_ledger.py`

- [ ] **Step 1: Add cash reserve tests**

```python
# Add to tests/unit/fund/test_ledger.py

class TestCashReserve:
    def test_redeem_within_cash_reserve(self):
        """Redemption succeeds when within cash reserve."""
        ledger = UnitLedger(cash_reserve_pct=Decimal("0.05"))
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m1", name="Alice", email="a@b.com",
            units=Decimal("30"), cost_basis=Decimal("30000"),
            join_date=date(2026, 1, 1),
        )

        tx = ledger.redeem(
            fund=fund, member=member,
            units=Decimal("30"),
            process_date=date(2026, 6, 1),
            available_cash=Decimal("50000"),  # 5% of 1M
        )
        assert tx.status == TransactionStatus.PROCESSED
        assert tx.requires_liquidation is False

    def test_redeem_exceeds_cash_reserve(self):
        """Redemption requires position liquidation when exceeding cash."""
        ledger = UnitLedger(cash_reserve_pct=Decimal("0.05"))
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m1", name="Alice", email="a@b.com",
            units=Decimal("100"), cost_basis=Decimal("100000"),
            join_date=date(2026, 1, 1),
        )

        tx = ledger.redeem(
            fund=fund, member=member,
            units=Decimal("100"),
            process_date=date(2026, 6, 1),
            available_cash=Decimal("50000"),
        )
        assert tx.status == TransactionStatus.PROCESSED
        assert tx.requires_liquidation is True
        assert tx.liquidation_amount == Decimal("50000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_ledger.py::TestCashReserve -v`
Expected: FAIL

- [ ] **Step 3: Update ledger with cash reserve logic**

Add `cash_reserve_pct` parameter to `UnitLedger.__init__()`. Update `redeem()` to accept `available_cash` parameter. Add `requires_liquidation` and `liquidation_amount` fields to `Transaction`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_ledger.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/birger/code/portfolio
git add src/fund/ledger.py src/fund/types.py tests/unit/fund/test_ledger.py
git commit -m "feat(fund): cash reserve management for redemptions"
```

---

### Task 12: Monthly Crystallization Flow

**Files:**
- Modify: `tests/unit/fund/test_fees.py`

- [ ] **Step 1: Add crystallization tests**

```python
# Add to tests/unit/fund/test_fees.py

class TestMonthlyCrystallization:
    def test_crystallize_above_hwm(self):
        engine = FeeEngine(perf_fee_rate=Decimal("0.20"))
        fees, new_hwm = engine.crystallize_monthly(
            nav_per_unit=Decimal("1100"),
            high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"),
        )
        assert fees.performance_fee == Decimal("20000")
        assert new_hwm == Decimal("1100")

    def test_crystallize_below_hwm(self):
        engine = FeeEngine()
        fees, new_hwm = engine.crystallize_monthly(
            nav_per_unit=Decimal("950"),
            high_water_mark=Decimal("1000"),
            units_outstanding=Decimal("1000"),
        )
        assert fees.performance_fee == Decimal("0")
        assert new_hwm == Decimal("1000")
```

- [ ] **Step 2: Run tests to verify they pass** (implementation already added in Task 2 fix)

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_fees.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/birger/code/portfolio
git add tests/unit/fund/test_fees.py
git commit -m "test(fund): monthly performance fee crystallization"
```

---

### Task 13: Property-Based Tests

**Files:**
- Create: `tests/unit/fund/test_properties.py`

- [ ] **Step 1: Write property-based tests**

```python
# tests/unit/fund/test_properties.py
"""Property-based tests for fund invariants."""

from datetime import date, datetime
from decimal import Decimal
from hypothesis import given, strategies as st

from fund.types import Fund, Member
from fund.fees import FeeEngine
from fund.ledger import UnitLedger


# Strategy: positive decimals for money
money = st.decimals(min_value=1, max_value=10_000_000, places=2)
units_st = st.decimals(min_value=1, max_value=100_000, places=0)


class TestFeeInvariants:
    @given(nav=money)
    def test_management_fee_never_negative(self, nav):
        engine = FeeEngine()
        fee = engine.weekly_management_fee(nav)
        assert fee >= 0

    @given(
        nav_per_unit=st.decimals(min_value=0, max_value=10000, places=2),
        hwm=st.decimals(min_value=0, max_value=10000, places=2),
        units=st.decimals(min_value=1, max_value=100000, places=0),
    )
    def test_performance_fee_never_negative(self, nav_per_unit, hwm, units):
        engine = FeeEngine()
        fee, new_hwm = engine.performance_fee(nav_per_unit, hwm, units)
        assert fee >= 0

    @given(
        nav1=st.decimals(min_value=500, max_value=2000, places=2),
        nav2=st.decimals(min_value=500, max_value=2000, places=2),
    )
    def test_hwm_never_decreases(self, nav1, nav2):
        engine = FeeEngine()
        _, hwm1 = engine.performance_fee(nav1, Decimal("1000"), Decimal("100"))
        _, hwm2 = engine.performance_fee(nav2, hwm1, Decimal("100"))
        assert hwm2 >= hwm1


class TestLedgerInvariants:
    @given(amount=st.decimals(min_value=100, max_value=1_000_000, places=2))
    def test_subscribe_units_balance(self, amount):
        """Total units * nav_per_unit should equal total NAV."""
        ledger = UnitLedger()
        fund = Fund(
            nav=Decimal("1000000"),
            units_outstanding=Decimal("1000"),
            high_water_mark=Decimal("1000"),
            inception_date=date(2026, 1, 1),
        )
        member = Member(
            id="m1", name="Test", email="t@t.com",
            units=Decimal("0"), cost_basis=Decimal("0"),
            join_date=date(2026, 1, 1),
        )
        ledger.subscribe(fund, member, amount, date(2026, 2, 1))
        # NAV should equal units * nav_per_unit (approximately, due to rounding)
        expected = fund.units_outstanding * fund.nav_per_unit
        assert abs(fund.nav - expected) < Decimal("1")
```

- [ ] **Step 2: Install hypothesis if needed**

Run: `pip install hypothesis`

- [ ] **Step 3: Run property tests**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund/test_properties.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/birger/code/portfolio
git add tests/unit/fund/test_properties.py
git commit -m "test(fund): property-based tests for fee and ledger invariants"
```

---

## Summary

| Task | Component | What it does |
|------|-----------|-------------|
| 1 | Types | Fund, Member, Transaction, WeeklyNAV, EngineHealth |
| 2 | Fee Engine | 2% management, 20% performance, HWM |
| 3 | Unit Ledger | Subscribe, redeem, lock-up enforcement |
| 4 | NAV Calculator | Gross/net NAV, return calculation |
| 5 | Investment Universe | Max 20 instruments, voting |
| 6 | Benchmark Engine | Standard benchmarks + alternative universes |
| 7 | Thermo Metrics | Clarity, Opportunity, Health, Momentum |
| 8 | Heartbeat | Engine health monitor |
| 9 | Snapshot Builder | Assembles WeeklyNAV from all components |
| 10 | Public API | Exports and integration |
| 11 | Cash Reserve | 5% reserve, liquidation flag on redemptions |
| 12 | Monthly Crystallization | Performance fee crystallization tests |
| 13 | Property Tests | Hypothesis-based invariant tests |

**Notes:**
- SQLite persistence deferred to Sub-project 3 (gRPC Service) which needs it for caching
- Supabase push deferred to Sub-project 3 (gRPC Service)
- "No conviction" alternative universe requires the backtest engine — tracked but not computed in this sub-project
