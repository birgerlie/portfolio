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
    Fund, Member, Transaction, TransactionType, TransactionStatus,
    FeeBreakdown, Instrument, EngineHealth, WeeklyNAV, MarketHealth, Momentum,
)
from fund.nav import NAVCalculator
from fund.fees import FeeEngine
from fund.ledger import UnitLedger
from fund.universe import InvestmentUniverse
from fund.benchmarks import BenchmarkEngine
from fund.thermo_metrics import ThermoMetrics
from fund.heartbeat import HealthMonitor
from fund.snapshot import SnapshotBuilder
from fund.journal import JournalEntry, DailyJournal, EventJournal
from fund.alpaca_broker import AlpacaBroker, AlpacaConfig, BrokerAccount, BrokerPosition, BrokerOrder
from fund.order_executor import OrderExecutor, ExecutedOrder
from fund.position_sync import PositionSync, SyncResult

__all__ = [
    "Fund", "Member", "Transaction", "TransactionType", "TransactionStatus",
    "FeeBreakdown", "Instrument", "EngineHealth", "WeeklyNAV", "MarketHealth", "Momentum",
    "NAVCalculator", "FeeEngine", "UnitLedger", "InvestmentUniverse",
    "BenchmarkEngine", "ThermoMetrics", "HealthMonitor", "SnapshotBuilder",
    "JournalEntry", "DailyJournal", "EventJournal",
    "AlpacaBroker", "AlpacaConfig", "BrokerAccount", "BrokerPosition", "BrokerOrder",
    "OrderExecutor", "ExecutedOrder",
    "PositionSync", "SyncResult",
]
