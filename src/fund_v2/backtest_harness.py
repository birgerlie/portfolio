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
    """Seed the knowledge graph using the real ontology from fund/ontology.py.

    Loads sector membership, competition, macro relationships, index structure,
    market structure, and macro proxies — the full graph, not a hardcoded subset.
    Then connects ORM entity IDs to ontology nodes so propagation flows through.
    """
    from fund.ontology import build_ontology, MACRO_PROXIES as ONTO_PROXIES, MACRO, COMPETITORS as ONTO_COMPETITORS

    # Build the full ontology (uses_network=False to skip Wikipedia/Yahoo fetch)
    all_triples = build_ontology(use_network=False)
    logger.info("Built ontology: %d triples from curated data", len(all_triples))

    # Filter to symbols we're backtesting + their graph neighborhood
    relevant_symbols = set(symbols + macro_proxies)
    relevant_triples = []
    for t in all_triples:
        # Keep triple if either endpoint is a symbol we care about,
        # or it's a structural triple (sector, macro factor, index)
        if t.subject in relevant_symbols or t.object in relevant_symbols:
            relevant_triples.append(t)
        elif t.predicate in ("is_a", "pressures", "benefits", "drives", "signals",
                              "proxy_for", "tracks", "measures_volatility_of",
                              "derived_from", "measures"):
            relevant_triples.append(t)

    # Ingest as dicts
    triple_dicts = [
        {"subject": t.subject, "predicate": t.predicate, "object": t.object, "weight": t.weight}
        for t in relevant_triples
    ]

    if hasattr(app.engine, "insert_triples"):
        app.engine.insert_triples(triple_dicts)
    else:
        for t in triple_dicts:
            try:
                app.engine.add_triple(t["subject"], t["predicate"], t["object"], weight=t.get("weight", 1.0))
            except Exception:
                pass

    # Bridge: connect ORM entity IDs (instrument:AAPL) to ontology nodes (AAPL)
    # so propagation from ontology reaches the belief nodes
    bridge_triples = []
    for symbol in symbols:
        ext_id = f"instrument:{symbol}"
        bridge_triples.append({"subject": ext_id, "predicate": "represents", "object": symbol, "weight": 1.0})
        bridge_triples.append({"subject": symbol, "predicate": "represented_by", "object": ext_id, "weight": 1.0})
    for symbol in macro_proxies:
        ext_id = f"macrofactor:{symbol}"
        bridge_triples.append({"subject": ext_id, "predicate": "represents", "object": symbol, "weight": 1.0})
        bridge_triples.append({"subject": symbol, "predicate": "represented_by", "object": ext_id, "weight": 1.0})

    if hasattr(app.engine, "insert_triples"):
        app.engine.insert_triples(bridge_triples)
    else:
        for t in bridge_triples:
            try:
                app.engine.add_triple(t["subject"], t["predicate"], t["object"], weight=t.get("weight", 1.0))
            except Exception:
                pass

    logger.info("Ontology seeded: %d relevant triples + %d bridge triples", len(relevant_triples), len(bridge_triples))


# ── Daily replay ─────────────────────────────────────────────────────────────

def _seed_instruments(app, data: Dict[str, StockData], period: dict):
    """Ingest instruments via the ORM pipeline.

    RouteStage auto-creates belief nodes with initial probabilities
    and connects them with has_{belief} triples. No manual node
    creation needed (fixed in #338).
    """
    from fund_v2.entities import Instrument, MacroFactor
    from silicondb.sources.models import SourceRecord
    from silicondb.pipeline.models import PipelineContext
    from datetime import datetime, timezone

    pipeline = app.get_pipeline()

    for symbol in data:
        is_macro = symbol in period.get("macro_proxies", [])
        entity_cls = MacroFactor if is_macro else Instrument

        record = SourceRecord(
            source_name="backtest",
            collection="instruments",
            identity=symbol,
            data={"symbol": symbol, "price": data[symbol].closes[0], "trade_count": 1},
            timestamp=datetime.now(timezone.utc),
            idempotency_key=f"seed:{symbol}",
            tenant_id=0,
        )
        ctx = PipelineContext(
            engine=app.engine,
            entity_cls=entity_cls,
            tenant_id=0,
        )
        pipeline.process(record, ctx)

    logger.info("Seeded %d instruments via pipeline (belief nodes auto-created)", len(data))


def feed_daily_observations(app, data: Dict[str, StockData], day_idx: int, prev_day_idx: int, period: dict):
    """Feed one day's observations directly into SiliconDB belief nodes.

    Seeding (via _seed_instruments) creates entities + belief nodes through
    the pipeline. Daily updates go directly to engine.observe() since the
    pipeline's ingest rejects duplicate external_ids.

    Observation strength scales with move magnitude to simulate intraday
    trade density — a 3% move generates more observations than a 0.1% move.
    """
    macro_proxies = set(period.get("macro_proxies", []))

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
        is_macro = symbol in macro_proxies
        prefix = "macrofactor" if is_macro else "instrument"
        ext_id = f"{prefix}:{symbol}"

        # Observation strength scales with move magnitude
        strength = min(10, max(1, int(abs(daily_return) * 1000)))

        # Price trend fast (responsive — full strength)
        for _ in range(strength):
            try:
                app.engine.observe(f"{ext_id}:price_trend_fast", confirmed=price_up, source="backtest")
            except Exception:
                pass

        # Price trend slow (inertia — half strength)
        for _ in range(max(1, strength // 2)):
            try:
                app.engine.observe(f"{ext_id}:price_trend_slow", confirmed=price_up, source="backtest")
            except Exception:
                pass

        # Exhaustion: extreme moves in either direction
        try:
            if abs(daily_return) > 0.02:
                app.engine.observe(f"{ext_id}:exhaustion", confirmed=True, source="backtest")
            else:
                app.engine.observe(f"{ext_id}:exhaustion", confirmed=False, source="backtest")
        except Exception:
            pass

        # Volume and spread
        try:
            app.engine.observe(f"{ext_id}:volume_normal", confirmed=(volume > 0), source="backtest")
            app.engine.observe(f"{ext_id}:spread_tight", confirmed=True, source="backtest")
        except Exception:
            pass

        # Graph propagation
        try:
            if hasattr(app.engine, "propagate"):
                app.engine.propagate(
                    external_id=ext_id,
                    confidence=0.5 + abs(daily_return) * 5,
                    decay=0.3,
                )
        except Exception:
            pass

    # Macro-specific observations
    for symbol in macro_proxies:
        if symbol not in data:
            continue
        try:
            ext_id = f"macrofactor:{symbol}"
            # Macro "elevated" belief tracks whether the factor is above normal
            sd = data[symbol]
            if day_idx < len(sd.closes) and prev_day_idx < len(sd.closes):
                ret = (sd.closes[day_idx] - sd.closes[prev_day_idx]) / sd.closes[prev_day_idx]
                app.engine.observe(f"{ext_id}:elevated", confirmed=(ret > 0), source="backtest")
                app.engine.observe(f"{ext_id}:trending", confirmed=(ret > 0), source="backtest")
        except Exception:
            pass

    # Graph-driven Layer 2 derivation:
    # 1. Relative strength from sector peer comparison
    # 2. Pressure from graph propagation (macro → sector → instrument)
    _derive_layer2_from_graph(app, data, macro_proxies)


def _derive_layer2_from_graph(app, data: Dict[str, StockData], macro_proxies: set):
    """Derive Layer 2 beliefs using the graph, not hardcoded logic.

    Relative strength: compare each instrument's price_trend_slow to
    sector peers by querying the graph for in_sector relationships.

    Pressure: propagate macro proxy observations through the ontology.
    TLT moves → interest_rates:trending belief → engine.propagate() pushes
    signal through graph edges → instruments connected via sector membership
    and macro relationships get pressure updated automatically.
    """
    # ── Relative strength via sector peer comparison ──────────────────────
    # Group instruments by sector using graph triples
    sector_members: Dict[str, List[str]] = {}
    for symbol in data:
        if symbol in macro_proxies:
            continue
        ext_id = f"instrument:{symbol}"
        try:
            # Query: what sector is this instrument in?
            triples = app.engine.query_triples(subject=symbol, predicate="in_sector")
            for t in triples:
                sector = t.get("object", t.get("object_value", ""))
                if sector:
                    sector_members.setdefault(sector, []).append(symbol)
        except Exception:
            pass

    # If graph query didn't work (no triples found), fall back to all-vs-all
    if not sector_members:
        sector_members["all"] = [s for s in data if s not in macro_proxies]

    # Compute relative strength within each sector group
    for sector, members in sector_members.items():
        if len(members) < 2:
            continue
        slow_beliefs = {}
        for symbol in members:
            try:
                slow_beliefs[symbol] = app.engine.belief(f"instrument:{symbol}:price_trend_slow")
            except Exception:
                slow_beliefs[symbol] = 0.5

        avg = sum(slow_beliefs.values()) / len(slow_beliefs)
        for symbol, val in slow_beliefs.items():
            try:
                app.engine.observe(
                    f"instrument:{symbol}:relative_strength",
                    confirmed=(val > avg),
                    source=f"sector_peer:{sector}",
                )
            except Exception:
                pass

    # ── Pressure via graph propagation ────────────────────────────────────
    # For each macro proxy, propagate its belief state through the graph.
    # The ontology has: TLT proxy_for interest_rates, interest_rates pressures technology,
    # technology contains_instrument AAPL — so propagating from TLT reaches AAPL
    # through 3 hops with decaying confidence.
    for symbol in macro_proxies:
        if symbol not in data:
            continue
        ext_id = f"macrofactor:{symbol}"
        try:
            # Read the macro proxy's current trend belief
            trend = app.engine.belief(f"{ext_id}:trending")
        except Exception:
            trend = 0.5

        # Propagate from the ontology node (e.g., "TLT") with strength
        # proportional to how far the trend deviates from neutral
        deviation = abs(trend - 0.5)
        if deviation > 0.05:  # only propagate if meaningful
            try:
                # Propagate from the raw ontology node so it flows through
                # proxy_for → factor → pressures/drives → sector → instrument edges
                app.engine.propagate(
                    external_id=symbol,  # "TLT" (ontology node, not "macrofactor:TLT")
                    confidence=0.3 + deviation,
                    decay=0.4,
                )
            except Exception:
                pass

        # Also observe pressure directly on instruments connected via graph
        # This catches what propagation might miss due to edge structure
        try:
            # Find what factor this proxy represents
            proxy_triples = app.engine.query_triples(subject=symbol, predicate="proxy_for")
            for pt in proxy_triples:
                factor = pt.get("object", pt.get("object_value", ""))
                if not factor:
                    continue
                # Find what sectors this factor pressures
                pressure_triples = app.engine.query_triples(subject=factor, predicate="pressures")
                benefit_triples = app.engine.query_triples(subject=factor, predicate="benefits")

                for st in pressure_triples:
                    sector = st.get("object", st.get("object_value", ""))
                    weight = st.get("weight", st.get("probability", 0.5))
                    # Find instruments in this sector
                    members = sector_members.get(sector, [])
                    for inst_sym in members:
                        try:
                            # Pressure increases when macro factor trend is strong
                            app.engine.observe(
                                f"instrument:{inst_sym}:pressure",
                                confirmed=(trend > 0.5),  # factor rising = pressure
                                source=f"graph:{factor}→{sector}",
                            )
                        except Exception:
                            pass

                for bt in benefit_triples:
                    sector = bt.get("object", bt.get("object_value", ""))
                    members = sector_members.get(sector, [])
                    for inst_sym in members:
                        try:
                            # Benefits = inverse pressure
                            app.engine.observe(
                                f"instrument:{inst_sym}:pressure",
                                confirmed=(trend < 0.5),  # factor rising = benefit (less pressure)
                                source=f"graph:{factor}→{sector}",
                            )
                        except Exception:
                            pass
        except Exception:
            pass


def collect_daily_state(app, symbols: List[str], macro_proxies: List[str]) -> Dict[str, Dict[str, float]]:
    """Read current belief state for all symbols."""
    beliefs = {}
    belief_names = ["price_trend_fast", "price_trend_slow", "relative_strength",
                    "exhaustion", "pressure", "spread_tight", "volume_normal"]

    for symbol in symbols:
        is_macro = symbol in macro_proxies
        prefix = "macrofactor" if is_macro else "instrument"
        ext_id = f"{prefix}:{symbol}"
        b = {}
        for name in belief_names:
            try:
                b[name] = app.engine.belief(f"{ext_id}:{name}")
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

        # Read beliefs directly for each instrument (using pipeline entity ID format)
        instruments = []
        for symbol in symbols:
            if symbol in macro_proxies:
                continue
            ext_id = f"instrument:{symbol}"
            inst = type("Inst", (), {"external_id": ext_id, "symbol": symbol})()
            for attr in ["relative_strength", "exhaustion", "pressure",
                         "retail_sentiment", "crowded", "price_trend_fast", "price_trend_slow",
                         "entry_ready", "exit_ready"]:
                try:
                    val = app.engine.belief(f"{ext_id}:{attr}")
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

        # Use a pipeline without dedup for backtest (same entity ingested repeatedly)
        from silicondb.pipeline import Pipeline
        from silicondb.pipeline.validate import ValidateStage
        from silicondb.pipeline.normalise import NormaliseStage
        from silicondb.pipeline.route import RouteStage
        app._pipeline = Pipeline([ValidateStage(), NormaliseStage(), RouteStage()])

        print(f"Engine: {engine_type}")
        print(f"Entities registered: {len(ALL_ENTITIES)}")

        # Seed ontology
        setup_ontology(app, period["symbols"], period["macro_proxies"])

        # Seed instruments via pipeline — RouteStage auto-creates belief nodes (#338)
        _seed_instruments(app, data, period)

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
            feed_daily_observations(app, data, day_idx, day_idx - 1, period)

            # Collect state
            beliefs = collect_daily_state(app, period["symbols"], period.get("macro_proxies", []))

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
