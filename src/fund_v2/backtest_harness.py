"""Full SiliconDB-backed backtest harness.

Feeds historical data day-by-day through the real ORM pipeline with
native SiliconDB engine. Beliefs propagate through the graph, hooks fire,
predictions run, signals are generated — exactly as they would live.

Usage:
    SILICONDB_LIBRARY_PATH=lib/silicondb/.build/release \
    PYTHONPATH=src:lib/silicondb/python \
    python3 -m fund_v2.backtest_harness --period svb

    # Run all periods:
    python3 -m fund_v2.backtest_harness --all

    # Compare with v1 baseline:
    python3 -m fund_v2.backtest_harness --period svb --compare-v1
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from trading_backtest.data import fetch_historical_data, StockData

logger = logging.getLogger(__name__)


# ── Test periods (reused from backtest_comparison.py) ────────────────────────

PERIODS = {
    "svb": {
        "name": "SVB Crisis",
        "start": "2023-02-15",
        "end": "2023-04-15",
        "key_event": "2023-03-09",
        "description": "SVB collapse → regional bank contagion → flight to safety",
        "symbols": ["JPM", "BAC", "GS", "MS", "WFC", "C",
                     "AAPL", "MSFT", "NVDA", "GOOG", "META",
                     "XLF", "KRE", "SPY", "QQQ"],
        "macro_proxies": ["TLT", "UVXY", "GLD", "IWM"],
    },
    "rate_hike": {
        "name": "Rate Hike Cycle",
        "start": "2022-01-01",
        "end": "2022-07-01",
        "key_event": "2022-01-05",
        "description": "Fed hawkish pivot → tech selloff → energy outperformance",
        "symbols": ["AAPL", "MSFT", "NVDA", "GOOG", "META", "AMZN",
                     "XOM", "CVX", "COP", "SPY", "QQQ"],
        "macro_proxies": ["TLT", "USO", "UUP", "UVXY", "GLD", "IWM"],
    },
    "rotation": {
        "name": "Great Rotation",
        "start": "2024-07-01",
        "end": "2024-08-15",
        "key_event": "2024-07-11",
        "description": "Mega-cap → small-cap rotation after soft CPI",
        "symbols": ["AAPL", "MSFT", "NVDA", "GOOG", "META", "AMZN",
                     "SPY", "QQQ"],
        "macro_proxies": ["TLT", "IWM", "UVXY", "UUP"],
    },
    "covid": {
        "name": "COVID Crash",
        "start": "2020-02-15",
        "end": "2020-04-15",
        "key_event": "2020-03-16",
        "description": "Market crash → V-shaped recovery",
        "symbols": ["AAPL", "MSFT", "AMZN", "GOOG",
                     "JPM", "BAC", "XOM", "CVX",
                     "SPY", "QQQ"],
        "macro_proxies": ["TLT", "USO", "UVXY", "GLD", "IWM"],
    },
    "pivot": {
        "name": "Fed Pivot Rally",
        "start": "2023-10-15",
        "end": "2023-12-31",
        "key_event": "2023-10-27",
        "description": "Treasury yield peaks → risk-on rally",
        "symbols": ["AAPL", "MSFT", "NVDA", "GOOG", "META", "AMZN",
                     "SPY", "QQQ"],
        "macro_proxies": ["TLT", "UVXY", "GLD", "IWM", "UUP"],
    },
}


# ── Sector mapping for ontology ──────────────────────────────────────────────

SYMBOL_SECTORS = {
    "AAPL": "technology", "MSFT": "technology", "NVDA": "technology",
    "GOOG": "technology", "META": "technology", "AMZN": "technology",
    "JPM": "financials", "BAC": "financials", "GS": "financials",
    "MS": "financials", "WFC": "financials", "C": "financials",
    "XLF": "financials", "KRE": "financials",
    "XOM": "energy", "CVX": "energy", "COP": "energy",
}

MACRO_PROXY_MAPPINGS = {
    "TLT": ("interest_rates", "pressures", "technology"),
    "USO": ("oil_prices", "drives", "energy"),
    "UVXY": ("market_fear", "pressures", "technology"),
    "GLD": ("gold_prices", None, None),
    "IWM": ("small_cap_strength", None, None),
    "UUP": ("usd_strength", "pressures", "materials"),
}

COMPETITORS = [
    ("GOOG", "META"), ("AMZN", "MSFT"), ("NVDA", "AMD"),
    ("JPM", "BAC"), ("JPM", "GS"), ("XOM", "CVX"),
]


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class DayResult:
    date: date
    signals: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    beliefs: Dict[str, Dict[str, float]] = field(default_factory=dict)
    thermo: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestResult:
    period_name: str
    days: List[DayResult] = field(default_factory=list)
    signal_accuracy: float = 0.0
    detection_lead_days: int = 0
    total_signals: int = 0
    total_events: int = 0
    total_actions: int = 0


# ── Engine setup ─────────────────────────────────────────────────────────────

def create_backtest_engine(db_dir: str, dimension: int = 384):
    """Create a SiliconDB native engine for backtesting.

    Falls back to MockEngine if native library isn't available.
    """
    try:
        from silicondb.engine.native import SiliconDBNativeEngine
        engine = SiliconDBNativeEngine(db_dir, dimension=dimension)
        logger.info("Using native SiliconDB engine at %s", db_dir)
        return engine, "native"
    except Exception as e:
        logger.warning("Native engine unavailable (%s), falling back to MockEngine", e)
        from silicondb.engine.mock import MockEngine
        return MockEngine(), "mock"


def setup_ontology(app, symbols: List[str], macro_proxies: List[str]):
    """Seed the knowledge graph with sector, competition, and macro relationships."""
    triples = []

    # Sector membership
    sectors_seen = set()
    for symbol in symbols:
        sector = SYMBOL_SECTORS.get(symbol)
        if sector:
            triples.append({"subject": symbol, "predicate": "in_sector", "object": sector, "weight": 1.0})
            triples.append({"subject": sector, "predicate": "contains_instrument", "object": symbol, "weight": 1.0})
            triples.append({"subject": symbol, "predicate": "is_a", "object": "instrument", "weight": 1.0})
            sectors_seen.add(sector)

    # Sector entities
    for sector in sectors_seen:
        triples.append({"subject": sector, "predicate": "is_a", "object": "sector", "weight": 1.0})

    # Competition
    for a, b in COMPETITORS:
        if a in symbols and b in symbols:
            triples.append({"subject": a, "predicate": "competes_with", "object": b, "weight": 0.7})
            triples.append({"subject": b, "predicate": "competes_with", "object": a, "weight": 0.7})

    # Macro factors
    for proxy, (factor, predicate, sector) in MACRO_PROXY_MAPPINGS.items():
        if proxy in macro_proxies:
            triples.append({"subject": proxy, "predicate": "proxy_for", "object": factor, "weight": 0.9})
            triples.append({"subject": proxy, "predicate": "is_a", "object": "instrument", "weight": 1.0})
            if predicate and sector and sector in sectors_seen:
                triples.append({"subject": factor, "predicate": predicate, "object": sector, "weight": 0.6})

    # Ingest triples
    if hasattr(app.engine, "insert_triples"):
        app.engine.insert_triples(triples)
    else:
        for t in triples:
            try:
                app.engine.add_triple(t["subject"], t["predicate"], t["object"], weight=t.get("weight", 1.0))
            except Exception:
                pass

    logger.info("Ontology seeded: %d triples, %d sectors, %d symbols", len(triples), len(sectors_seen), len(symbols))


# ── Daily replay ─────────────────────────────────────────────────────────────

def _ensure_belief_nodes(app, symbols: List[str]):
    """Ingest belief node documents so observe() has something to update.

    SiliconDB requires a document to exist before beliefs can be tracked.
    Each belief is a separate node: "{symbol}:{belief_name}".
    """
    belief_names = ["price_trend_fast", "price_trend_slow", "relative_strength",
                    "exhaustion", "pressure", "spread_tight", "volume_normal",
                    "retail_sentiment", "crowded", "return"]
    for symbol in symbols:
        # Ingest the instrument document
        try:
            app.engine.ingest(symbol, f"Instrument {symbol}", metadata={"node_type": "instrument", "symbol": symbol})
        except Exception:
            pass
        # Ingest each belief node
        for belief in belief_names:
            node_id = f"{symbol}:{belief}"
            try:
                app.engine.ingest(node_id, f"{belief} for {symbol}", metadata={"node_type": belief, "symbol": symbol})
            except Exception:
                pass
        # Connect belief nodes to instrument via triples
        for belief in belief_names:
            try:
                app.engine.add_triple(symbol, f"has_{belief}", f"{symbol}:{belief}", weight=1.0)
            except Exception:
                pass


def feed_daily_observations(app, data: Dict[str, StockData], day_idx: int, prev_day_idx: int):
    """Feed one day's worth of observations into SiliconDB.

    For each symbol: observe price movement → belief updates.
    Multiple observations per day to build conviction (Bayesian updates accumulate).
    """
    for symbol, sd in data.items():
        if day_idx >= len(sd.closes) or prev_day_idx >= len(sd.closes):
            continue

        close = sd.closes[day_idx]
        prev_close = sd.closes[prev_day_idx]
        volume = sd.volumes[day_idx] if day_idx < len(sd.volumes) else 0

        if prev_close <= 0:
            continue

        daily_return = (close - prev_close) / prev_close
        price_up = daily_return > 0

        # Observe price direction — both confirmed AND disconfirmed
        # so beliefs converge toward the actual trend rather than saturating
        strength = min(5, max(1, int(abs(daily_return) * 500)))

        for _ in range(strength):
            try:
                # Price up → confirm trend_fast, disconfirm if down
                app.engine.observe(f"{symbol}:price_trend_fast", confirmed=price_up, source="backtest")
            except Exception:
                pass

        for _ in range(max(1, strength // 2)):
            try:
                app.engine.observe(f"{symbol}:price_trend_slow", confirmed=price_up, source="backtest")
            except Exception:
                pass

        # Exhaustion: observe when trend is extreme in EITHER direction
        if abs(daily_return) > 0.02:
            try:
                app.engine.observe(f"{symbol}:exhaustion", confirmed=True, source="backtest")
            except Exception:
                pass
        else:
            try:
                app.engine.observe(f"{symbol}:exhaustion", confirmed=False, source="backtest")
            except Exception:
                pass

        # Volume normality
        try:
            app.engine.observe(f"{symbol}:volume_normal", confirmed=(volume > 0), source="backtest")
            app.engine.observe(f"{symbol}:spread_tight", confirmed=True, source="backtest")
        except Exception:
            pass

        # Propagate through graph
        try:
            if hasattr(app.engine, "propagate"):
                app.engine.propagate(external_id=f"{symbol}:return", confidence=0.5 + abs(daily_return) * 5, decay=0.3)
        except Exception:
            pass

    # Compute relative_strength directly (hooks can't query peers from native engine)
    slow_beliefs = {}
    for symbol in data:
        try:
            slow_beliefs[symbol] = app.engine.belief(f"{symbol}:price_trend_slow")
        except Exception:
            slow_beliefs[symbol] = 0.5

    if slow_beliefs:
        avg_slow = sum(slow_beliefs.values()) / len(slow_beliefs)
        for symbol, slow_val in slow_beliefs.items():
            rs_up = slow_val > avg_slow
            try:
                app.engine.observe(f"{symbol}:relative_strength", confirmed=rs_up, source="derived")
            except Exception:
                pass

    # Compute pressure from macro proxies
    for symbol in data:
        if symbol in ("TLT", "UVXY", "GLD"):
            try:
                proxy_trend = app.engine.belief(f"{symbol}:price_trend_fast")
                # TLT falling = rates rising = pressure on tech
                # UVXY rising = fear = pressure on everything
                is_pressure = (symbol == "TLT" and proxy_trend < 0.5) or \
                              (symbol == "UVXY" and proxy_trend > 0.5) or \
                              (symbol == "GLD" and proxy_trend > 0.6)
                if is_pressure:
                    for target in data:
                        if target not in ("TLT", "UVXY", "GLD", "USO", "UUP", "IWM"):
                            try:
                                app.engine.observe(f"{target}:pressure", confirmed=True, source=f"macro:{symbol}")
                            except Exception:
                                pass
            except Exception:
                pass


def collect_daily_state(app, symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """Read current belief state for all symbols."""
    beliefs = {}
    belief_names = ["price_trend_fast", "price_trend_slow", "relative_strength",
                    "exhaustion", "pressure", "spread_tight", "volume_normal"]

    for symbol in symbols:
        b = {}
        for name in belief_names:
            try:
                b[name] = app.engine.belief(f"{symbol}:{name}")
            except Exception:
                b[name] = 0.5
        beliefs[symbol] = b

    return beliefs


def run_daily_signals(app, symbols: List[str], macro_proxies: List[str]) -> List[Dict[str, Any]]:
    """Run signal generation for today's state using belief values from engine."""
    try:
        from fund_v2.signals import generate_signals_impl

        # Build regime from macro proxy beliefs
        regime = type("Regime", (), {
            "trend_following": 0.5,
            "mean_reverting_regime": 0.5,
            "risk_on": 0.5,
        })()

        # Read beliefs directly for each instrument
        instruments = []
        for symbol in symbols:
            if symbol in macro_proxies:
                continue
            inst = type("Inst", (), {"external_id": symbol, "symbol": symbol})()
            for attr in ["relative_strength", "exhaustion", "pressure",
                         "retail_sentiment", "crowded", "price_trend_fast", "price_trend_slow"]:
                try:
                    val = app.engine.belief(f"{symbol}:{attr}")
                except Exception:
                    val = 0.5
                setattr(inst, attr, val)
            instruments.append(inst)

        if instruments:
            result = generate_signals_impl(app.engine, regime=regime, instruments=instruments)
            return result.get("signals", [])
    except Exception as e:
        logger.debug("Signal generation failed: %s", e)

    return []


# ── Main backtest loop ───────────────────────────────────────────────────────

def run_backtest(period_name: str, compare_v1: bool = False) -> BacktestResult:
    """Run full SiliconDB-backed backtest for a period."""
    period = PERIODS[period_name]

    print(f"\n{'='*70}")
    print(f"  {period['name']}: {period['description']}")
    print(f"  {period['start']} → {period['end']}")
    print(f"  Key event: {period['key_event']}")
    print(f"{'='*70}\n")

    # Load historical data
    print("Loading historical data...")
    all_symbols = list(set(period["symbols"] + period["macro_proxies"]))
    data: Dict[str, StockData] = {}
    for symbol in sorted(all_symbols):
        try:
            sd = fetch_historical_data(symbol, period["start"], period["end"])
            if sd and sd.dates:
                data[symbol] = sd
        except Exception as e:
            logger.warning("Failed to load %s: %s", symbol, e)
    print(f"Loaded {len(data)} symbols\n")

    # Create temporary SiliconDB instance
    db_dir = tempfile.mkdtemp(prefix="fund_v2_backtest_")
    print(f"SiliconDB temp dir: {db_dir}")

    try:
        from silicondb.orm import App
        engine, engine_type = create_backtest_engine(db_dir)
        app = App(engine, internal_db_url="sqlite:///:memory:")

        # Register entities
        from fund_v2.entities import ALL_ENTITIES
        app.register(*ALL_ENTITIES)

        # Register hooks (filter out extra metadata keys that HookRegistry.register doesn't accept)
        from silicondb.orm.hooks import collect_hooks_from_module
        import fund_v2.hooks as hook_module
        for hook in collect_hooks_from_module(hook_module):
            app._hook_registry.register(
                hook_type=hook["hook_type"],
                entity_type=hook["entity_type"],
                field_name=hook.get("field_name"),
                callback=hook["callback"],
            )

        print(f"Engine: {engine_type}")
        print(f"Entities registered: {len(ALL_ENTITIES)}")

        # Seed ontology
        setup_ontology(app, period["symbols"], period["macro_proxies"])

        # Create belief node documents so observations have targets
        _ensure_belief_nodes(app, list(data.keys()))

        # Get reference symbol for dates
        ref_symbol = "SPY" if "SPY" in data else list(data.keys())[0]
        n_days = len(data[ref_symbol].dates)
        lookback = 20

        print(f"Trading days: {n_days}")
        print(f"Starting replay from day {lookback}...\n")

        result = BacktestResult(period_name=period_name)

        for day_idx in range(lookback, n_days):
            today = data[ref_symbol].dates[day_idx]

            # Feed observations
            feed_daily_observations(app, data, day_idx, day_idx - 1)

            # Collect state
            beliefs = collect_daily_state(app, period["symbols"])

            # Run signals
            signals = run_daily_signals(app, period["symbols"], period["macro_proxies"])

            # Collect actions
            actions = []
            try:
                actions = app.get_actions(limit=50)
            except Exception:
                pass

            # Run predictions (if native engine)
            predictions = []
            if engine_type == "native" and hasattr(app.engine, "predicted_flips"):
                try:
                    flips = app.engine.predicted_flips(horizon_days=7, min_confidence=0.3, k=10)
                    if flips:
                        predictions = [{"node_id": f.node_id, "predicted": f.predicted_probability} for f in flips]
                except Exception:
                    pass

            # Get thermo state
            thermo = {}
            if hasattr(app.engine, "thermo_state"):
                try:
                    thermo = app.engine.thermo_state() or {}
                except Exception:
                    pass

            day_result = DayResult(
                date=today,
                signals=signals,
                events=[{"type": "predictions", "data": predictions}] if predictions else [],
                actions=[{"action_type": a.get("action_type", ""), "entity_id": a.get("entity_id", "")} for a in actions],
                beliefs=beliefs,
                thermo=thermo,
            )
            result.days.append(day_result)
            result.total_signals += len(signals)
            result.total_actions += len(actions)

            # Progress — show a few belief values to debug
            if day_idx % 10 == 0 or day_idx == n_days - 1:
                sample_sym = period["symbols"][0]
                fast = beliefs.get(sample_sym, {}).get("price_trend_fast", "?")
                slow = beliefs.get(sample_sym, {}).get("price_trend_slow", "?")
                rs = beliefs.get(sample_sym, {}).get("relative_strength", "?")
                exh = beliefs.get(sample_sym, {}).get("exhaustion", "?")
                print(f"  Day {day_idx}/{n_days} ({today}): {len(signals)} signals | {sample_sym}: fast={fast:.3f} slow={slow:.3f} rs={rs:.3f} exh={exh:.3f}")

        # Evaluate signal accuracy
        # Debug: show first signal structure
        if result.days and result.days[0].signals:
            print(f"\n  Debug — first signal keys: {list(result.days[0].signals[0].keys())}")
            print(f"  Debug — first signal: {result.days[0].signals[0]}")

        correct = 0
        total = 0
        for day_result in result.days:
            for sig in day_result.signals:
                symbol = sig.get("symbol", "")
                if symbol not in data:
                    continue
                sd = data[symbol]
                # Find day index by comparing date objects (handle datetime vs date)
                target_date = day_result.date if isinstance(day_result.date, date) else day_result.date.date() if hasattr(day_result.date, 'date') else day_result.date
                day_idx = None
                for i, d in enumerate(sd.dates):
                    d_date = d if isinstance(d, date) else d.date() if hasattr(d, 'date') else d
                    if d_date == target_date:
                        day_idx = i
                        break
                if day_idx is None:
                    continue
                fwd_idx = min(day_idx + 5, len(sd.closes) - 1)
                if fwd_idx <= day_idx:
                    continue
                fwd_return = (sd.closes[fwd_idx] - sd.closes[day_idx]) / sd.closes[day_idx]
                total += 1
                direction = sig.get("direction", "")
                if (direction == "long" and fwd_return > 0) or (direction == "short" and fwd_return < 0):
                    correct += 1

        result.signal_accuracy = correct / total if total > 0 else 0.0

        # Detection timing
        key_date = date.fromisoformat(period["key_event"])
        first_action_date = None
        for day_result in result.days:
            if day_result.actions and (first_action_date is None or day_result.date < first_action_date):
                first_action_date = day_result.date
        result.detection_lead_days = (key_date - first_action_date).days if first_action_date else 0

        # Print results
        print(f"\n{'─'*50}")
        print(f"  RESULTS: {period['name']}")
        print(f"{'─'*50}")
        print(f"  Engine:              {engine_type}")
        print(f"  Total signals:       {result.total_signals}")
        print(f"  Total actions:       {result.total_actions}")
        print(f"  Signal accuracy:     {result.signal_accuracy:.1%} ({correct}/{total})")
        print(f"  Detection lead:      {result.detection_lead_days} days before key event")

        # Belief trajectory for key symbols
        print(f"\n  Belief trajectories (selected days):")
        key_symbols = period["symbols"][:5]
        sample_days = [result.days[i] for i in range(0, len(result.days), max(1, len(result.days) // 5))]
        print(f"  {'Date':<12} ", end="")
        for sym in key_symbols:
            print(f"  {sym:>8}", end="")
        print()
        for day in sample_days:
            print(f"  {day.date!s:<12} ", end="")
            for sym in key_symbols:
                rs = day.beliefs.get(sym, {}).get("relative_strength", 0.5)
                print(f"  {rs:>7.2f}", end="")
            print()

        # V1 comparison
        if compare_v1:
            print(f"\n  V1 comparison:")
            from fund_v2.backtest_comparison import run_v1_signals, evaluate_signal_accuracy
            period_obj = type("P", (), {
                "symbols": period["symbols"],
                "macro_proxies": period["macro_proxies"],
            })()
            v1_signals, v1_events = run_v1_signals(data, period_obj)
            from fund_v2.backtest_comparison import SignalAccuracy
            v1_acc = evaluate_signal_accuracy(v1_signals, data, forward_days=5)
            print(f"  V1 accuracy: {v1_acc.accuracy:.1%} ({v1_acc.correct}/{v1_acc.total})")
            print(f"  V2 accuracy: {result.signal_accuracy:.1%} ({correct}/{total})")
            delta = result.signal_accuracy - v1_acc.accuracy
            print(f"  Delta:       {delta:+.1%}")

        return result

    finally:
        # Cleanup
        try:
            if hasattr(app, "close"):
                app.close()
        except Exception:
            pass
        shutil.rmtree(db_dir, ignore_errors=True)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Full SiliconDB-backed V2 backtest")
    parser.add_argument("--period", choices=list(PERIODS.keys()), default="svb")
    parser.add_argument("--all", action="store_true", help="Run all periods")
    parser.add_argument("--compare-v1", action="store_true", help="Compare with V1 baseline")
    args = parser.parse_args()

    if args.all:
        results = []
        for name in PERIODS:
            results.append(run_backtest(name, compare_v1=args.compare_v1))

        print(f"\n{'='*70}")
        print("  SUMMARY — Full SiliconDB Backtest")
        print(f"{'='*70}")
        print(f"  {'Period':<15} {'Signals':>8} {'Actions':>8} {'Accuracy':>9} {'Lead':>6}")
        print(f"  {'-'*50}")
        for r in results:
            print(f"  {r.period_name:<15} {r.total_signals:>8} {r.total_actions:>8} {r.signal_accuracy:>8.1%} {r.detection_lead_days:>5}d")
    else:
        run_backtest(args.period, compare_v1=args.compare_v1)


if __name__ == "__main__":
    main()
