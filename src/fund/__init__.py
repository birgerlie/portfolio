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
from fund.grpc_server import FundServiceServicer
from fund.belief_synthesizer import BeliefSynthesizer
from fund.grpc_runner import create_server, run_server
from fund.supabase_sync import SupabaseSync, SupabaseConfig
from fund.notifications import NotificationManager
from fund.email_reports import EmailReporter
from fund.price_cache import PriceCache, PriceEntry
from fund.stream_service import AlpacaStreamService, StreamEvent
from fund.observation_recorder import ObservationRecorder
from fund.tempo import Tempo, ThermoTier
from fund.reactor import Reactor, ReactorConfig

__all__ = [
    "Fund", "Member", "Transaction", "TransactionType", "TransactionStatus",
    "FeeBreakdown", "Instrument", "EngineHealth", "WeeklyNAV", "MarketHealth", "Momentum",
    "NAVCalculator", "FeeEngine", "UnitLedger", "InvestmentUniverse",
    "BenchmarkEngine", "ThermoMetrics", "HealthMonitor", "SnapshotBuilder",
    "JournalEntry", "DailyJournal", "EventJournal",
    "AlpacaBroker", "AlpacaConfig", "BrokerAccount", "BrokerPosition", "BrokerOrder",
    "OrderExecutor", "ExecutedOrder",
    "PositionSync", "SyncResult",
    "FundServiceServicer", "create_server", "run_server",
    "BeliefSynthesizer",
    "SupabaseSync", "SupabaseConfig",
    "NotificationManager",
    "EmailReporter",
    "PriceCache", "PriceEntry",
    "AlpacaStreamService", "StreamEvent",
    "ObservationRecorder",
    "Tempo", "ThermoTier",
    "Reactor", "ReactorConfig",
]
