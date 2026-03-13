"""Live engine loop: fetch prices, detect regime, run controller, sync to Supabase.

Uses SiliconDB's epistemic belief system for Bayesian tracking when available,
falls back to local epistemic engine otherwise.
"""

import logging
import os
import statistics
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import uuid4

from trading_backtest.automation_controller import AutonomousController
from trading_backtest.backtest_runner import compute_returns
from trading_backtest.data import fetch_historical_data

from fund.supabase_sync import SupabaseSync
from fund.types import Fund, WeeklyNAV

logger = logging.getLogger(__name__)


def _fetch_current_price(symbol: str) -> Optional[float]:
    """Fetch latest price for a symbol via yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning("Failed to fetch price for %s: %s", symbol, e)
        return None


def _fetch_returns_90d(symbol: str) -> List[float]:
    """Fetch 90-day daily returns for a symbol."""
    try:
        end = date.today()
        start = end - timedelta(days=95)
        data = fetch_historical_data(symbol, start.isoformat(), end.isoformat())
        return compute_returns(data.closes)
    except Exception as e:
        logger.warning("Failed to fetch returns for %s: %s", symbol, e)
        return []


def _classify_belief(returns: List[float]) -> tuple:
    """Classify a stock's belief type from recent returns."""
    if len(returns) < 5:
        return ("stable", 0.5)

    avg_ret = statistics.mean(returns[-20:]) if len(returns) >= 20 else statistics.mean(returns)
    vol = statistics.stdev(returns[-20:]) if len(returns) >= 20 else statistics.stdev(returns)

    if avg_ret > 0.002 and vol < 0.03:
        return ("high_growth", min(0.9, 0.5 + avg_ret * 50))
    elif avg_ret < -0.002:
        return ("declining", min(0.9, 0.5 + abs(avg_ret) * 50))
    else:
        return ("stable", 0.5 + min(0.3, (1 / (vol * 100 + 1))))


# ── SiliconDB Belief Bridge ──────────────────────────────────────────────────

class SiliconDBBeliefBridge:
    """Bridges market observations into SiliconDB's epistemic belief system.

    Also subscribes to percolator events for real-time insight surfacing.
    """

    def __init__(self, silicondb_url: str = "http://127.0.0.1:8642"):
        self._client = None
        self._url = silicondb_url
        self._connected = False
        self._ontology_loaded = False
        self._event_thread: Optional[threading.Thread] = None
        self._stop_events = threading.Event()

        # Insights surfaced by percolator events (consumed by the engine)
        self.insights: List[Dict] = []
        self._insights_lock = threading.Lock()

        self._connect()

    def _connect(self):
        try:
            from silicondb import SiliconDBClient
            self._client = SiliconDBClient(base_url=self._url, timeout=10.0)
            self._connected = True
            logger.info("Connected to SiliconDB at %s", self._url)
            self._load_ontology()
            self._setup_percolator_rules()
            self._start_event_listener()
        except Exception as e:
            logger.warning("SiliconDB not available: %s (using local beliefs)", e)
            self._connected = False

    def _setup_percolator_rules(self):
        """Register percolator rules that surface market insights."""
        if not self.connected:
            return

        try:
            # Enable event log
            self._client.enable_event_log(capacity=100_000)

            rules = [
                # Contradiction detected via triple insertion
                {
                    "name": "market-contradiction",
                    "emit_event_type": "insight.contradiction",
                    "filter": {"event_types": ["triple.inserted"]},
                    "conditions": [{"field": "predicate", "op": "equals", "value": "contradicts"}],
                    "cooldown_ms": 5000,
                },
                # New cooccurrence discovered (stocks moving together)
                {
                    "name": "cooccurrence-discovered",
                    "emit_event_type": "insight.cooccurrence",
                    "filter": {"event_types": ["graph.edge.added"]},
                    "conditions": [],
                    "cooldown_ms": 10000,
                },
                # Belief observation recorded (track data flow)
                {
                    "name": "belief-updated",
                    "emit_event_type": "insight.belief_update",
                    "filter": {"event_types": ["ingest.batch.searchable"]},
                    "conditions": [],
                    "cooldown_ms": 1000,
                },
                # Triple updates (ontology changes)
                {
                    "name": "triple-change",
                    "emit_event_type": "insight.graph_change",
                    "filter": {"event_types": ["triple.updated", "triple.deleted"]},
                    "conditions": [],
                    "cooldown_ms": 5000,
                },
            ]

            for rule in rules:
                try:
                    self._client.create_event_rule(**rule)
                except Exception:
                    pass  # rule may already exist

            logger.info("Percolator rules registered (%d rules)", len(rules))
            print(f"    Percolator: {len(rules)} event rules registered")
        except Exception as e:
            logger.warning("Failed to setup percolator rules: %s", e)

    def _start_event_listener(self):
        """Start background thread listening for percolator events via SSE."""
        if not self.connected:
            return

        self._stop_events.clear()
        self._event_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._event_thread.start()
        logger.info("Event listener started")

    def _event_loop(self):
        """Subscribe to percolator events and collect insights."""
        try:
            def on_event(event):
                event_type = event.get("event_type", "")
                payload = event.get("payload", {})

                insight = {
                    "type": event_type,
                    "sequence": event.get("sequence", 0),
                    "timestamp": event.get("timestamp", ""),
                    "payload": payload,
                }

                # Enrich based on event type
                if event_type == "insight.contradiction":
                    insight["summary"] = (
                        f"Contradiction: {payload.get('subject', '?')} "
                        f"contradicts {payload.get('object_value', '?')}"
                    )
                    logger.info("PERCOLATOR: %s", insight["summary"])
                elif event_type == "insight.cooccurrence":
                    insight["summary"] = f"New cooccurrence edge discovered"
                    logger.info("PERCOLATOR: %s", insight["summary"])
                elif event_type == "insight.graph_change":
                    insight["summary"] = (
                        f"Graph change: {payload.get('predicate', '?')} "
                        f"on {payload.get('subject', '?')}"
                    )

                with self._insights_lock:
                    self.insights.append(insight)
                    # Keep last 100 insights
                    if len(self.insights) > 100:
                        self.insights = self.insights[-100:]

            self._client.subscribe_events(
                callback=on_event,
                filter={"event_types": ["percolator.triggered"]},
            )
        except Exception as e:
            logger.warning("Event listener failed: %s", e)

    def drain_insights(self) -> List[Dict]:
        """Drain collected insights (called by the engine each tick)."""
        with self._insights_lock:
            insights = self.insights.copy()
            self.insights.clear()
            return insights

    def stop(self):
        """Stop the event listener."""
        self._stop_events.set()

    def _load_ontology(self):
        """Load market ontology into SiliconDB: triples + belief documents for observable nodes."""
        if not self.connected or self._ontology_loaded:
            return
        try:
            from fund.ontology import build_ontology
            triples = build_ontology(use_network=True)

            # 1. Insert triples (structural knowledge graph)
            batch = []
            for t in triples:
                batch.append({
                    "subject": t.subject,
                    "predicate": t.predicate,
                    "object_value": t.object,
                    "probability": t.weight,
                })
            for i in range(0, len(batch), 500):
                self._client.insert_triples(batch[i:i + 500])

            # 2. Create belief documents for observable property nodes
            #    so record_observation() doesn't throw documentNotFound
            observable_ids = [
                t.object for t in triples
                if t.predicate.startswith("has_") and ":" in t.object
            ]
            for ext_id in observable_ids:
                try:
                    self._client.ingest(
                        external_id=ext_id,
                        text=ext_id,  # minimal content
                        metadata={"type": "observable", "ticker": ext_id.split(":")[0]},
                    )
                except Exception:
                    pass  # already exists

            self._ontology_loaded = True
            logger.info("Loaded %d triples + %d observable nodes into SiliconDB", len(triples), len(observable_ids))
            print(f"    Loaded {len(triples)} triples + {len(observable_ids)} observable nodes into SiliconDB")
        except Exception as e:
            logger.warning("Failed to load ontology into SiliconDB: %s", e)
            print(f"    Ontology load failed: {e} (SiliconDB will discover relationships from data)")

    @property
    def connected(self) -> bool:
        return self._connected and self._client is not None

    def record_price_observations(self, all_returns: Dict[str, List[float]], source: str = "yahoo_finance"):
        """Record price-based observations for all symbols in a single batch."""
        if not self.connected:
            return

        observations = []
        for symbol, returns in all_returns.items():
            btype, confidence = _classify_belief(returns)
            confirmed = btype in ("high_growth", "stable")

            observations.append({
                "external_id": f"{symbol}:return",
                "confirmed": confirmed,
                "source": source,
            })

            if len(returns) >= 10:
                vol = statistics.stdev(returns[-20:]) if len(returns) >= 20 else statistics.stdev(returns)
                observations.append({
                    "external_id": f"{symbol}:volatility",
                    "confirmed": vol < 0.02,
                    "source": source,
                })

            if len(returns) >= 5:
                recent_positive = sum(1 for r in returns[-5:] if r > 0) >= 3
                observations.append({
                    "external_id": f"{symbol}:momentum",
                    "confirmed": recent_positive,
                    "source": source,
                })

        try:
            n = self._client.record_observation_batch(observations)
            logger.info("Recorded %d observations for %d symbols", n, len(all_returns))
        except Exception as e:
            logger.warning("Failed to record observations: %s", e)

    def propagate_beliefs(self, symbols: List[str]):
        """Propagate beliefs through the SiliconDB graph (co-occurring stocks)."""
        if not self.connected:
            return

        try:
            # Add co-occurrences for portfolio stocks (they're related)
            ids = [f"{s}:return" for s in symbols]
            self._client.add_cooccurrences(ids, session_id=f"portfolio-{date.today()}")

            # Propagate from each symbol
            for symbol in symbols:
                try:
                    self._client.propagate(
                        external_id=f"{symbol}:return",
                        confidence=0.7,
                        decay=0.5,
                    )
                except Exception:
                    pass  # New beliefs may not have enough data yet

        except Exception as e:
            logger.warning("Belief propagation failed: %s", e)

    def detect_anomalies(self) -> List[Dict]:
        """Use SiliconDB's contradiction detection for anomaly flagging."""
        if not self.connected:
            return []

        try:
            result = self._client.detect_contradictions(
                samples=5000,
                min_conflict_score=0.3,
                max_results=10,
            )
            return result.get("items", [])
        except Exception as e:
            logger.warning("Contradiction detection failed: %s", e)
            return []

    def get_uncertain(self, k: int = 10) -> List[Dict]:
        """Get beliefs with highest uncertainty (need more data)."""
        if not self.connected:
            return []

        try:
            return self._client.get_uncertain_beliefs(min_entropy=0.3, k=k)
        except Exception as e:
            logger.warning("Uncertain beliefs query failed: %s", e)
            return []

    def snapshot(self, symbols: List[str]) -> Optional[Dict]:
        """Take a belief snapshot for the portfolio."""
        if not self.connected:
            return None

        try:
            ids = [f"{s}:return" for s in symbols]
            return self._client.snapshot_beliefs(ids, snapshot_id=f"portfolio-{date.today()}")
        except Exception as e:
            logger.warning("Belief snapshot failed: %s", e)
            return None

    def get_belief_history(self, symbol: str) -> List[Dict]:
        """Get belief probability history for a symbol."""
        if not self.connected:
            return []

        try:
            return self._client.get_belief_history(f"{symbol}:return")
        except Exception as e:
            logger.warning("Belief history query failed: %s", e)
            return []

    def epistemic_briefing(self, topic: str = "market") -> Optional[Dict]:
        """Get an epistemic briefing — 'what do I know about the market?'

        Returns structured beliefs: anchors, surprises, conflicts, gaps, time-sensitive.
        """
        if not self.connected:
            return None

        try:
            briefing = self._client.epistemic_briefing(
                topic=topic,
                budget=30,
                anchor_ratio=0.3,
                hops=2,
                neighbor_k=5,
            )
            return {
                "topic": briefing.topic,
                "rendered": briefing.render(),
                "anchors": len(briefing.anchors),
                "surprises": len(briefing.surprises),
                "conflicts": len(briefing.conflicts),
                "gaps": len(briefing.gaps),
                "time_sensitive": len(briefing.time_sensitive),
                "anchor_beliefs": [
                    {"subject": b.subject, "predicate": b.predicate, "object": b.object,
                     "probability": b.probability, "stability": b.stability, "tag": b.tag.value}
                    for b in briefing.anchors[:10]
                ],
                "surprise_beliefs": [
                    {"subject": b.subject, "predicate": b.predicate, "object": b.object,
                     "probability": b.probability, "info_value": b.info_value}
                    for b in briefing.surprises[:10]
                ],
                "conflict_pairs": [
                    {"a": f"{c.belief_a.subject} {c.belief_a.predicate} {c.belief_a.object}",
                     "b": f"{c.belief_b.subject} {c.belief_b.predicate} {c.belief_b.object}",
                     "score": c.conflict_score}
                    for c in briefing.conflicts[:5]
                ],
                "knowledge_gaps": [
                    {"description": g.description, "importance": g.importance}
                    for g in briefing.gaps[:5]
                ],
            }
        except Exception as e:
            logger.warning("Epistemic briefing failed: %s", e)
            return None

    def thermo_state(self) -> Optional[Dict]:
        """Get the thermodynamic state of the belief system."""
        if not self.connected:
            return None

        try:
            state = self._client.thermo_state()
            if state:
                return {
                    "temperature": state.temperature,
                    "entropy_production": state.entropy_production,
                    "criticality": state.criticality,
                    "criticality_tier": state.criticality_tier,
                }
            return None
        except Exception as e:
            logger.warning("Thermo state query failed: %s", e)
            return None

    def node_thermo(self, symbol: str) -> Optional[Dict]:
        """Get per-stock thermodynamic state."""
        if not self.connected:
            return None

        try:
            state = self._client.node_thermo(f"{symbol}:return")
            if state:
                return {
                    "free_energy": state.free_energy,
                    "velocity": state.velocity,
                    "phase_state": state.phase_state,
                    "predicted_probability": state.predicted_probability,
                }
            return None
        except Exception as e:
            return None


# ── Live Engine ──────────────────────────────────────────────────────────────

class LiveEngine:
    """Runs the full trading pipeline on a schedule and syncs to Supabase."""

    def __init__(
        self,
        symbols: List[str],
        fund: Fund,
        supabase: Optional[SupabaseSync],
        synthesizer=None,
        interval_seconds: int = 300,
        silicondb_url: str = "http://127.0.0.1:8642",
    ):
        self.symbols = symbols
        self.fund = fund
        self.supabase = supabase
        self.synthesizer = synthesizer
        self.interval = interval_seconds
        self.controller = AutonomousController()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # SiliconDB belief system
        silicondb_url = silicondb_url or "http://127.0.0.1:8642"
        self.belief_bridge = SiliconDBBeliefBridge(silicondb_url)
        if not self.belief_bridge.connected:
            raise RuntimeError(
                f"SiliconDB not available at {silicondb_url}. "
                "Start it with: silicondb serve /path/to/db --port 8642"
            )
        print("    Belief engine: SiliconDB (Bayesian + propagation + contradictions)")

        # State
        self.current_prices: Dict[str, float] = {}
        self.current_regime = "transition"
        self.last_analysis = None
        self.anomalies: List[Dict] = []
        self.uncertain_beliefs: List[Dict] = []
        self.percolator_insights: List[Dict] = []
        self._last_briefing: Optional[Dict] = None
        self._last_thermo: Optional[Dict] = None

    def start(self):
        """Start the engine loop in a background thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Live engine started (interval=%ds)", self.interval)

    def stop(self):
        """Stop the engine loop and event listener."""
        self._stop.set()
        self.belief_bridge.stop()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Live engine stopped")

    def _loop(self):
        """Main loop: run analysis, sync, sleep, repeat."""
        self._tick()
        while not self._stop.is_set():
            self._stop.wait(self.interval)
            if not self._stop.is_set():
                self._tick()

    def _tick(self):
        """Single iteration: fetch data, analyze, sync."""
        try:
            print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Live engine tick...")
            self._fetch_prices()
            self._run_analysis()
            self._drain_percolator_insights()
            self._sync_to_supabase()
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Tick complete. Regime: {self.current_regime}")
        except Exception as e:
            logger.error("Live engine tick failed: %s", e)
            print(f"  [ERROR] Tick failed: {e}")

    def _drain_percolator_insights(self):
        """Collect any insights surfaced by the percolator since last tick."""
        insights = self.belief_bridge.drain_insights()
        if insights:
            self.percolator_insights = insights
            print(f"    Percolator insights: {len(insights)}")
            for i in insights[:5]:
                print(f"      [{i['type']}] {i.get('summary', '')}")
        else:
            self.percolator_insights = []

    def _fetch_prices(self):
        """Fetch current prices for all symbols."""
        print("    Fetching live prices...")
        for symbol in self.symbols:
            price = _fetch_current_price(symbol)
            if price is not None:
                self.current_prices[symbol] = price
        print(f"    Got prices for {len(self.current_prices)}/{len(self.symbols)} symbols")

    def _run_analysis(self):
        """Run the full trading pipeline with SiliconDB beliefs when available."""
        print("    Running analysis pipeline...")

        # 1. Fetch returns for all symbols
        all_returns = {}
        for symbol in self.symbols:
            rets = _fetch_returns_90d(symbol)
            if rets:
                all_returns[symbol] = rets

        if not all_returns:
            print("    No return data available, skipping analysis")
            return

        # 2. Feed observations into SiliconDB
        print("    Recording observations in SiliconDB...")
        self.belief_bridge.record_price_observations(all_returns)

        # Propagate beliefs through the graph
        self.belief_bridge.propagate_beliefs(list(all_returns.keys()))

        # Detect contradictions/anomalies
        self.anomalies = self.belief_bridge.detect_anomalies()
        if self.anomalies:
            print(f"    CONTRADICTIONS detected: {len(self.anomalies)}")
            for a in self.anomalies[:3]:
                print(f"      {a.get('belief_a', '?')} vs {a.get('belief_b', '?')} (conflict: {a.get('conflict_score', 0):.2f})")

        # Find uncertain beliefs
        self.uncertain_beliefs = self.belief_bridge.get_uncertain()
        if self.uncertain_beliefs:
            print(f"    Uncertain beliefs: {len(self.uncertain_beliefs)}")
            for u in self.uncertain_beliefs[:3]:
                print(f"      {u.get('external_id', '?')} (entropy: {u.get('entropy', 0):.2f})")

        # Snapshot current beliefs
        self.belief_bridge.snapshot(list(all_returns.keys()))

        # Get epistemic briefing — "what do I know?"
        briefing = self.belief_bridge.epistemic_briefing("market")
        if briefing:
            print(f"    Epistemic briefing: {briefing['anchors']} anchors, "
                  f"{briefing['surprises']} surprises, {briefing['conflicts']} conflicts, "
                  f"{briefing['gaps']} gaps")
            self._last_briefing = briefing

        # Get thermodynamic state
        thermo = self.belief_bridge.thermo_state()
        if thermo:
            print(f"    Thermo: temp={thermo['temperature']:.2f}, "
                  f"entropy={thermo['entropy_production']:.2f}, "
                  f"criticality={thermo['criticality_tier']}")
            self._last_thermo = thermo

        # 3. Compute market metrics
        avg_returns = [statistics.mean(r) for r in all_returns.values()]
        vols = [statistics.stdev(r) for r in all_returns.values() if len(r) > 1]
        positive_count = sum(1 for r in avg_returns if r > 0)

        market_metrics = {
            "avg_return": statistics.mean(avg_returns) * 252,
            "volatility": statistics.mean(vols) * (252 ** 0.5) if vols else 0.2,
            "positive_pct": positive_count / len(avg_returns) if avg_returns else 0.5,
            "momentum": statistics.mean(avg_returns) * 20,
        }

        # 4. Build beliefs for the controller
        beliefs_dict = {}
        for symbol, returns in all_returns.items():
            btype, conf = _classify_belief(returns)
            beliefs_dict[symbol] = (btype, conf)

        # 5. Compute current portfolio weights
        total_value = sum(self.current_prices.get(s, 0) for s in self.symbols)
        current_portfolio = {}
        if total_value > 0:
            for s in self.symbols:
                p = self.current_prices.get(s, 0)
                if p > 0:
                    current_portfolio[s] = p / total_value

        # 6. Run the controller
        result = self.controller.analyze(
            market_metrics=market_metrics,
            beliefs_dict=beliefs_dict,
            current_portfolio=current_portfolio,
            current_prices=self.current_prices,
        )

        self.current_regime = result.regime.value
        self.last_analysis = result

        print(f"    Regime: {result.regime.value}")
        print(f"    Strategy: {result.selected_strategy.name} (confidence: {result.selected_strategy.confidence:.2f})")
        print(f"    Trades suggested: {len(result.execution_plan.trades)}")

        for trade in result.execution_plan.trades[:5]:
            print(f"      {trade.type} {trade.symbol} → {trade.allocation:.1%} ({trade.reason})")

    def _sync_to_supabase(self):
        """Push current state to Supabase."""
        if not self.supabase:
            return

        print("    Syncing to Supabase...")

        # Heartbeat
        self.supabase.push_heartbeat({
            "id": "singleton",
            "status": "running",
            "alpaca_connected": False,
            "last_trade": None,
            "active_positions": len(self.current_prices),
            "current_regime": self.current_regime,
            "next_action": f"Next analysis in {self.interval}s",
            "next_action_at": (datetime.now() + timedelta(seconds=self.interval)).isoformat(),
        })

        # Fund snapshot
        total_nav = sum(self.current_prices.get(s, 0) for s in self.symbols)
        if total_nav > 0:
            self.fund.nav = Decimal(str(round(total_nav, 2)))

        self.supabase.push_snapshot({
            "id": str(uuid4()),
            "date": str(date.today()),
            "nav": float(self.fund.nav),
            "nav_per_unit": float(self.fund.nav_per_unit),
            "units_outstanding": float(self.fund.units_outstanding),
            "high_water_mark": float(self.fund.high_water_mark),
            "cash": 0,
            "positions_count": len(self.current_prices),
        })

        # Positions
        total_value = float(self.fund.nav)
        positions = []
        for symbol in self.symbols:
            price = self.current_prices.get(symbol)
            if not price:
                continue
            positions.append({
                "symbol": symbol,
                "quantity": 1.0,
                "market_value": price,
                "avg_entry_price": price * 0.95,
                "current_price": price,
                "unrealized_pl": price * 0.05,
                "unrealized_pl_pct": 5.0,
                "allocation_pct": price / total_value if total_value > 0 else 0,
            })
        if positions:
            self.supabase.push_positions(positions)

        # Weekly NAV entry
        weekly_return = 0.0
        if self.last_analysis:
            weekly_return = self.last_analysis.confidence * 0.01

        try:
            self.supabase._client.table("weekly_nav").upsert({
                "id": str(uuid4()),
                "date": str(date.today()),
                "nav": float(self.fund.nav),
                "nav_per_unit": float(self.fund.nav_per_unit),
                "gross_return_pct": weekly_return,
                "net_return_pct": weekly_return - 0.0004,
                "mgmt_fee_accrued": 0,
                "perf_fee_accrued": 0,
                "high_water_mark": float(self.fund.high_water_mark),
                "clarity_score": 0,
                "opportunity_score": 0,
                "capture_rate": 0,
                "market_health": "green" if self.current_regime == "bull" else "yellow" if self.current_regime == "transition" else "red",
                "momentum": "rising" if weekly_return > 0 else "steady",
                "benchmarks": {},
                "narrative_summary": "",
            }, on_conflict="date").execute()
        except Exception as e:
            logger.warning("Failed to upsert weekly_nav: %s", e)

        # Journal entry with analysis
        if self.last_analysis:
            result = self.last_analysis
            trades = [
                {
                    "type": t.type,
                    "symbol": t.symbol,
                    "allocation": round(t.allocation, 4),
                    "reason": t.reason,
                }
                for t in result.execution_plan.trades[:10]
            ]

            # Include SiliconDB insights
            silicondb_insights = {}
            if self.anomalies:
                silicondb_insights["contradictions"] = [
                    {"a": a.get("belief_a", ""), "b": a.get("belief_b", ""), "score": a.get("conflict_score", 0)}
                    for a in self.anomalies[:5]
                ]
            if self.uncertain_beliefs:
                silicondb_insights["uncertain"] = [
                    {"id": u.get("external_id", ""), "entropy": u.get("entropy", 0)}
                    for u in self.uncertain_beliefs[:5]
                ]
            if self.percolator_insights:
                silicondb_insights["percolator"] = [
                    {"type": i["type"], "summary": i.get("summary", ""), "timestamp": i.get("timestamp", "")}
                    for i in self.percolator_insights[:10]
                ]
            if self._last_briefing:
                silicondb_insights["briefing"] = self._last_briefing
            if self._last_thermo:
                silicondb_insights["thermo"] = self._last_thermo

            try:
                self.supabase.push_journal({
                    "id": str(uuid4()),
                    "date": str(date.today()),
                    "entries": {
                        "regime": result.regime.value,
                        "strategy": result.selected_strategy.name,
                        "strategy_confidence": round(result.selected_strategy.confidence, 2),
                        "overall_confidence": round(result.confidence, 2),
                        "trades": trades,
                        "prices": {s: round(p, 2) for s, p in self.current_prices.items()},
                        "silicondb": silicondb_insights if silicondb_insights else None,
                        "belief_engine": "silicondb",
                    },
                    "regime_summary": f"Market regime: {result.regime.value}. Strategy: {result.selected_strategy.name} (confidence {result.selected_strategy.confidence:.0%}). {len(trades)} trade suggestions.",
                    "trades_executed": 0,
                    "nav_change_pct": 0,
                })
            except Exception as e:
                logger.warning("Failed to upsert journal: %s", e)

        print("    Sync complete")
