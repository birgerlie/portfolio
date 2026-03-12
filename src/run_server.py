#!/usr/bin/env python3
"""Launch the fund engine with mock broker, sync to Supabase, and start gRPC server.

Usage:
    python run_server.py                          # uses .env or env vars
    SUPABASE_URL=... SUPABASE_KEY=... python run_server.py
"""

import os
import sys
import signal
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Ensure src/ is on path
sys.path.insert(0, str(Path(__file__).parent))

from fund.types import Fund, Instrument, WeeklyNAV
from fund.mock_broker import MockBroker
from fund.belief_synthesizer import BeliefSynthesizer
from fund.universe import InvestmentUniverse
from fund.journal import EventJournal
from fund.thermo_metrics import ThermoMetrics
from fund.benchmarks import BenchmarkEngine
from fund.heartbeat import HealthMonitor
from fund.supabase_sync import SupabaseSync, SupabaseConfig
from fund.grpc_runner import run_server
from fund.grpc_server import FundServiceServicer


# ── Seed data ────────────────────────────────────────────────────────────────

SEED_POSITIONS = {
    "AAPL":  {"qty": Decimal("50"),  "avg": Decimal("178.50"), "current": Decimal("195.20")},
    "MSFT":  {"qty": Decimal("30"),  "avg": Decimal("380.00"), "current": Decimal("415.60")},
    "NVDA":  {"qty": Decimal("25"),  "avg": Decimal("450.00"), "current": Decimal("520.30")},
    "GOOG":  {"qty": Decimal("15"),  "avg": Decimal("140.00"), "current": Decimal("155.80")},
    "AMZN":  {"qty": Decimal("20"),  "avg": Decimal("175.00"), "current": Decimal("188.40")},
}

SEED_INSTRUMENTS = [
    Instrument("AAPL", "Apple Inc.", "equity", "Consumer tech dominance + services growth", "birger", date(2025, 1, 1), 5),
    Instrument("MSFT", "Microsoft Corp.", "equity", "Cloud + AI platform play", "birger", date(2025, 1, 1), 5),
    Instrument("NVDA", "NVIDIA Corp.", "equity", "GPU compute monopoly for AI training", "birger", date(2025, 1, 1), 4),
    Instrument("GOOG", "Alphabet Inc.", "equity", "Search moat + Waymo optionality", "birger", date(2025, 1, 1), 3),
    Instrument("AMZN", "Amazon.com", "equity", "AWS + retail logistics flywheel", "birger", date(2025, 1, 1), 4),
    Instrument("TSM", "Taiwan Semiconductor", "equity", "Foundry monopoly for advanced nodes", "birger", date(2025, 2, 1), 3),
    Instrument("META", "Meta Platforms", "equity", "Social graph + Reels monetisation", "birger", date(2025, 2, 1), 2),
]


def build_weekly_nav_history(fund_nav: Decimal, weeks: int = 12) -> list:
    """Generate plausible weekly NAV history."""
    history = []
    nav = float(fund_nav) * 0.92  # start ~8% lower
    hwm = nav
    today = date.today()
    start = today - timedelta(weeks=weeks)

    for i in range(weeks):
        week_date = start + timedelta(weeks=i)
        # Simulate gentle upward drift with noise
        import random
        random.seed(42 + i)
        weekly_return = random.gauss(0.008, 0.02)  # ~0.8% mean, 2% vol
        nav *= (1 + weekly_return)
        hwm = max(hwm, nav)
        units = float(fund_nav) / 100  # ~stable units

        benchmarks = {
            "SPY": round(random.gauss(0.005, 0.015) * (i + 1), 4),
            "QQQ": round(random.gauss(0.007, 0.02) * (i + 1), 4),
        }

        history.append(WeeklyNAV(
            date=week_date,
            nav=Decimal(str(round(nav, 2))),
            nav_per_unit=Decimal(str(round(nav / units, 4))),
            gross_return_pct=round(weekly_return * 100, 2),
            net_return_pct=round(weekly_return * 100 - 0.04, 2),  # ~2% annual mgmt
            mgmt_fee_accrued=Decimal(str(round(nav * 0.02 / 52, 2))),
            perf_fee_accrued=Decimal("0"),
            high_water_mark=Decimal(str(round(hwm, 2))),
            clarity_score=round(55 + i * 1.5 + random.gauss(0, 5), 1),
            opportunity_score=round(45 + i * 1.2 + random.gauss(0, 8), 1),
            capture_rate=round(0.6 + random.gauss(0, 0.1), 2),
            market_health="green" if i > 4 else "yellow",
            momentum="rising" if weekly_return > 0.005 else "steady",
            benchmarks=benchmarks,
            narrative_summary=f"Week {i+1}: Fund returned {weekly_return*100:.1f}%. "
                              f"Clarity improving as conviction builds across positions.",
        ))

    return history


def sync_to_supabase(supabase: SupabaseSync, fund: Fund, broker: MockBroker,
                     universe: InvestmentUniverse, nav_history: list,
                     health: HealthMonitor, thermo: ThermoMetrics):
    """Push all fund state to Supabase for the web dashboard."""
    print("  Syncing fund snapshot...")
    account = broker.get_account()
    positions = broker.get_positions()
    supabase.push_snapshot({
        "date": str(date.today()),
        "nav": float(fund.nav),
        "nav_per_unit": float(fund.nav_per_unit),
        "units_outstanding": float(fund.units_outstanding),
        "high_water_mark": float(fund.high_water_mark),
        "cash": float(account.cash),
        "positions_count": len(positions),
    })

    print("  Syncing positions...")
    total_value = float(account.equity)
    pos_data = []
    for p in positions:
        mv = float(p.market_value)
        pos_data.append({
            "symbol": p.symbol,
            "quantity": float(p.quantity),
            "market_value": mv,
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_pl_pct": p.unrealized_pl_pct,
            "allocation_pct": mv / total_value if total_value > 0 else 0,
        })
    supabase.push_positions(pos_data)

    print("  Syncing engine heartbeat...")
    heartbeat = health.create_heartbeat(
        alpaca_connected=True,
        last_trade=datetime.now() - timedelta(hours=2),
        active_positions=len(positions),
        current_regime="accumulation",
        next_action="Weekly rebalance check",
        next_action_at=datetime.now() + timedelta(hours=4),
    )
    supabase.push_heartbeat({
        "id": "singleton",
        "status": heartbeat.status,
        "alpaca_connected": heartbeat.alpaca_connected,
        "last_trade": heartbeat.last_trade.isoformat() if heartbeat.last_trade else None,
        "active_positions": heartbeat.active_positions,
        "current_regime": heartbeat.current_regime,
        "next_action": heartbeat.next_action,
        "next_action_at": heartbeat.next_action_at.isoformat() if heartbeat.next_action_at else None,
    })

    print("  Syncing weekly NAV history...")
    for nav in nav_history:
        try:
            supabase._client.table("weekly_nav").upsert({
                "id": str(uuid4()),
                "date": str(nav.date),
                "nav": float(nav.nav),
                "nav_per_unit": float(nav.nav_per_unit),
                "gross_return_pct": nav.gross_return_pct,
                "net_return_pct": nav.net_return_pct,
                "mgmt_fee_accrued": float(nav.mgmt_fee_accrued),
                "perf_fee_accrued": float(nav.perf_fee_accrued),
                "high_water_mark": float(nav.high_water_mark),
                "clarity_score": nav.clarity_score,
                "opportunity_score": nav.opportunity_score,
                "capture_rate": nav.capture_rate,
                "market_health": nav.market_health,
                "momentum": nav.momentum,
                "benchmarks": nav.benchmarks,
                "narrative_summary": nav.narrative_summary,
            }, on_conflict="date").execute()
        except Exception as e:
            print(f"    Warning: failed to upsert weekly_nav {nav.date}: {e}")

    print("  Syncing instruments...")
    for inst in universe.instruments:
        try:
            supabase._client.table("instruments").upsert({
                "id": str(uuid4()),
                "symbol": inst.symbol,
                "name": inst.name,
                "asset_class": inst.asset_class,
                "thesis": inst.thesis,
                "proposed_by": inst.proposed_by,
                "added_date": str(inst.added_date),
                "votes_for": inst.votes_for,
            }, on_conflict="symbol").execute()
        except Exception as e:
            print(f"    Warning: failed to upsert instrument {inst.symbol}: {e}")


def main():
    print("=" * 60)
    print("  FUND ENGINE - Development Server")
    print("=" * 60)

    # ── Load env ──────────────────────────────────────────────
    env_file = Path(__file__).parent.parent / "web" / ".env.local"
    if env_file.exists():
        print(f"\n  Loading env from {env_file}")
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip('"')
                os.environ.setdefault(key.strip(), value)

    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    # ── Build fund engine ─────────────────────────────────────
    print("\n  Building fund engine...")

    broker = MockBroker(cash=Decimal("25000"))
    for symbol, data in SEED_POSITIONS.items():
        broker.seed_position(symbol, data["qty"], data["avg"])
        broker.seed_price(symbol, data["current"])

    fund = Fund(
        nav=broker.get_account().equity,
        units_outstanding=Decimal("1000"),
        high_water_mark=broker.get_account().equity,
        inception_date=date(2025, 1, 6),
    )

    universe = InvestmentUniverse(max_size=20)
    for inst in SEED_INSTRUMENTS:
        universe.add(inst)

    journal = EventJournal(journal_dir="/tmp/fund-journals")
    thermo = ThermoMetrics()
    benchmarks = BenchmarkEngine()
    health = HealthMonitor()
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        synthesizer = BeliefSynthesizer(api_key=openai_key, model="gpt-4o-mini")
        print("  Synthesizer:     OpenAI gpt-4o-mini (cached)")
    else:
        from fund.mock_synthesizer import MockSynthesizer
        synthesizer = MockSynthesizer()
        print("  Synthesizer:     Mock (no OPENAI_API_KEY set)")

    nav_history = build_weekly_nav_history(fund.nav)

    account = broker.get_account()
    print(f"  Fund NAV:        ${float(fund.nav):,.2f}")
    print(f"  Cash:            ${float(account.cash):,.2f}")
    print(f"  Positions:       {len(broker.get_positions())}")
    print(f"  NAV/unit:        ${float(fund.nav_per_unit):,.4f}")
    print(f"  Universe:        {len(universe.instruments)} instruments")

    # ── Sync to Supabase ──────────────────────────────────────
    if supabase_url and supabase_key and supabase_key != "your-service-role-key":
        print(f"\n  Syncing to Supabase ({supabase_url})...")
        try:
            supabase = SupabaseSync(SupabaseConfig(url=supabase_url, key=supabase_key))
            sync_to_supabase(supabase, fund, broker, universe, nav_history, health, thermo)
            print("  Supabase sync complete!")
        except Exception as e:
            print(f"  Warning: Supabase sync failed: {e}")
            print("  (Server will still start — web dashboard may show stale data)")
    else:
        print("\n  Supabase sync skipped (no SUPABASE_SERVICE_ROLE_KEY set)")
        print("  Set it in web/.env.local to enable dashboard data sync")

    # ── Build gRPC servicer ───────────────────────────────────
    # Wrap HealthMonitor so the gRPC server can call create_heartbeat() without args
    class _HealthAdapter:
        def __init__(self, monitor, broker):
            self._monitor = monitor
            self._broker = broker

        def create_heartbeat(self):
            positions = self._broker.get_positions()
            return self._monitor.create_heartbeat(
                alpaca_connected=True,
                last_trade=datetime.now() - timedelta(hours=2),
                active_positions=len(positions),
                current_regime="accumulation",
                next_action="Weekly rebalance check",
                next_action_at=datetime.now() + timedelta(hours=4),
            )

    # Wrap ThermoMetrics so gRPC can call without args
    class _ThermoAdapter:
        def __init__(self, thermo):
            self._thermo = thermo
            self._beliefs = {"AAPL": 0.72, "MSFT": 0.68, "NVDA": 0.75, "GOOG": 0.55, "AMZN": 0.63}

        def clarity_score(self):
            return self._thermo.clarity_score(self._beliefs)

        def opportunity_score(self):
            return self._thermo.opportunity_score(self._beliefs, 0.18)

        def market_health(self):
            return self._thermo.market_health(0.18)

        def momentum(self):
            prev = {s: p - 0.02 for s, p in self._beliefs.items()}
            return self._thermo.momentum(prev, self._beliefs)

        def interpret(self):
            c = self.clarity_score()
            o = self.opportunity_score()
            h = self.market_health()
            m = self.momentum()
            return self._thermo.interpret(c, o, h, m)

    # Wrap BenchmarkEngine so gRPC can call without args
    class _BenchmarkAdapter:
        def compare(self):
            return {"SPY": 0.052, "QQQ": 0.071}

        def equal_weight_return(self):
            return 0.065

        def best_daily_pick_return(self):
            return 0.12

        def random_portfolio_median(self):
            return 0.04

        def capture_rate(self):
            return 0.76

    servicer = FundServiceServicer(
        fund=fund,
        members={},
        broker=broker,
        universe=universe,
        journal=journal,
        thermo=_ThermoAdapter(thermo),
        benchmarks=_BenchmarkAdapter(),
        health=_HealthAdapter(health, broker),
        belief_synthesizer=synthesizer,
    )
    servicer._nav_history = nav_history

    # ── Start gRPC server ─────────────────────────────────────
    port = int(os.environ.get("GRPC_PORT", "50051"))
    print(f"\n  Starting gRPC server on port {port}...")
    print(f"  Dashboard: http://localhost:3000")
    print(f"  Press Ctrl+C to stop\n")
    print("=" * 60)

    journal.log("engine_start", "Fund engine started in development mode")

    try:
        run_server(servicer, port=port)
    except KeyboardInterrupt:
        print("\n  Shutting down...")


if __name__ == "__main__":
    main()
