"""Live engine — thin wiring layer that connects streaming, observation, and reaction components."""

import logging
import queue
import statistics
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# ANSI colors for console event log
_C = {
    "trade": "\033[36m",     # cyan
    "quote": "\033[34m",     # blue
    "fill": "\033[32m",      # green
    "anomaly": "\033[33m",   # yellow
    "thermo": "\033[35m",    # magenta
    "regime": "\033[91m",    # bright red
    "belief": "\033[93m",    # bright yellow
    "briefing": "\033[95m",  # bright magenta
    "signal": "\033[92m",    # bright green
    "decay": "\033[90m",     # gray
    "reset": "\033[0m",
}

# Pretty names for internal identifiers
_PRETTY = {
    # Strategies
    "kelly_monthly_rebalance": "Kelly Criterion (Monthly Rebalance)",
    "kelly_inverse_hedge": "Kelly Criterion (Inverse Hedge)",
    "equal_weight_inverse_hedge": "Equal Weight (Inverse Hedge)",
    "kelly_dynamic_hedge": "Kelly Criterion (Dynamic Hedge)",
    "belief_weighted": "Belief-Weighted Allocation",
    "stop_loss_20pct": "Stop-Loss 20%",
    # Regimes
    "BULL": "Bull Market",
    "BEAR": "Bear Market",
    "CONSOLIDATION": "Consolidation",
    "TRANSITION": "Regime Transition",
    "bull": "Bull Market",
    "bear": "Bear Market",
    "consolidation": "Consolidation",
    "transition": "Regime Transition",
    # Belief types
    "high_growth": "High Growth",
    "stable": "Stable",
    "declining": "Declining",
}


def _pretty(name: str) -> str:
    return _PRETTY.get(name, name.replace("_", " ").title())


# System prompt for all financial narratives
_FINANCE_SYSTEM = (
    "You are a senior portfolio strategist at a quantitative investment fund. "
    "Write in precise financial language using terms like alpha, beta, conviction, "
    "risk-adjusted return, drawdown, correlation, mean reversion, momentum, "
    "factor exposure, regime shift, volatility clustering, and sector rotation. "
    "Be concise (1-3 sentences). Never use marketing language. "
    "Speak as you would in a morning research briefing to the investment committee."
)


def _log_event(kind: str, symbol: str, detail: str = "") -> None:
    """Print a colored event line to console."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    color = _C.get(kind, "")
    reset = _C["reset"]
    tag = kind.upper().ljust(7)
    sym = symbol.ljust(6) if symbol else "      "
    print(f"{color}[{ts}] {tag} {sym} {detail}{reset}")


class LiveEngine:
    """Consumes events from AlpacaStreamService and coordinates observation recording,
    anomaly reaction, and Supabase heartbeat sync."""

    def __init__(
        self,
        symbols: list,
        fund,
        supabase,
        synthesizer,
        stream_service,          # AlpacaStreamService
        observation_recorder,    # ObservationRecorder
        reactor,                 # Reactor
        tempo,                   # Tempo
        silicondb_client,
        controller=None,         # AutonomousController
        broker=None,             # AlpacaBroker
        interval_seconds: int = 300,
        verbose: bool = True,
        signal_tracker=None,
    ):
        self._symbols = symbols
        self._fund = fund
        self._supabase = supabase
        self._synthesizer = synthesizer
        self._stream = stream_service
        self._recorder = observation_recorder
        self._reactor = reactor
        self._tempo = tempo
        self._silicondb = silicondb_client
        self._controller = controller
        self._broker = broker
        self._interval = interval_seconds
        self._verbose = verbose
        self._signal_tracker = signal_tracker
        self._stop_event = threading.Event()
        self._event_queue = stream_service._event_queue
        self._event_count = 0
        self._current_regime = None
        self._last_analysis = None

    def start(self):
        # Register percolator rules if native SiliconDB client
        self._setup_percolator()

        self._stream.start()
        self._consumer_thread = threading.Thread(
            target=self._consume_events, daemon=True, name="event-consumer",
        )
        self._consumer_thread.start()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="heartbeat",
        )
        self._heartbeat_thread.start()
        self._percolator_thread = threading.Thread(
            target=self._percolator_loop, daemon=True, name="percolator",
        )
        self._percolator_thread.start()
        logger.info("LiveEngine started: streaming + consumer + percolator + heartbeat")

    def stop(self):
        self._stop_event.set()
        self._stream.stop()
        logger.info("LiveEngine stopped")

    # ── queue consumer ────────────────────────────────────────────────────────

    def _consume_events(self):
        while not self._stop_event.is_set():
            try:
                event = self._event_queue.get(timeout=1.0)
            except queue.Empty:
                self._recorder.flush()
                continue

            self._event_count += 1

            if event.kind == "trade":
                self._recorder.record_symbol(event.symbol)
                if self._verbose:
                    price = event.data.get("price", "")
                    size = event.data.get("size", "")
                    _log_event("trade", event.symbol, f"${price} x{size}")
            elif event.kind == "quote":
                self._recorder.record_quote(
                    event.symbol,
                    event.data.get("bid", 0),
                    event.data.get("ask", 0),
                    event.timestamp,
                )
                if self._verbose and self._event_count % 500 == 0:
                    bid = event.data.get("bid", "")
                    ask = event.data.get("ask", "")
                    _log_event("quote", event.symbol, f"bid=${bid} ask=${ask}")
            elif event.kind == "fill":
                self._handle_fill(event)
                if self._verbose:
                    side = event.data.get("side", "")
                    qty = event.data.get("filled_qty", "")
                    price = event.data.get("filled_avg_price", "")
                    _log_event("fill", event.data.get("symbol", ""), f"{side} {qty} @ ${price}")

            self._recorder.flush()

            for symbol in self._recorder.get_anomalies():
                self._reactor.on_volume_anomaly({"symbol": symbol})
                if self._verbose:
                    _log_event("anomaly", symbol, "volume 2x+ baseline")

    def _handle_fill(self, event):
        try:
            self._supabase.push_heartbeat(self._build_heartbeat())
        except Exception as e:
            logger.error("Fill sync failed: %s", e)

    # ── percolator ──────────────────────────────────────────────────────────

    def _setup_percolator(self):
        """Register percolator rules and enable event log on native SiliconDB."""
        if not hasattr(self._silicondb, 'enable_event_log'):
            logger.info("SiliconDB client does not support percolator — skipping")
            return

        try:
            self._silicondb.enable_event_log(capacity=5000)

            # Clean up any stale rules from previous runs
            try:
                for rule in self._silicondb.list_event_rules():
                    self._silicondb.delete_event_rule(rule.get("name", rule) if isinstance(rule, dict) else str(rule))
            except Exception:
                pass

            # Nervous tier: fires on any observation
            self._silicondb.create_event_rule(
                name="belief-updated",
                emit_event_type="belief-updated",
                filter={"event_type": "observation_recorded"},
                conditions=[],
                cooldown_ms=0,
            )

            # Standard tier: fires on contradiction
            self._silicondb.create_event_rule(
                name="contradiction-detected",
                emit_event_type="contradiction-detected",
                filter={"event_type": "contradiction_found"},
                conditions=[],
                cooldown_ms=10_000,
            )

            rules = self._silicondb.list_event_rules()
            _log_event("belief", "", f"Percolator: {len(rules)} rules registered, event log capacity=5000")
        except Exception as e:
            logger.error("Failed to setup percolator: %s", e)

    def _percolator_loop(self):
        """Poll SiliconDB for thermo state and run analysis on a tempo-adaptive interval."""
        import time

        while not self._stop_event.is_set():
            # Adaptive sleep based on tempo
            cooldown = self._tempo.get_cooldown_ms()
            sleep_secs = (cooldown / 1000.0) if cooldown else 30.0
            if self._stop_event.wait(sleep_secs):
                break

            try:
                should_analyze = False

                # Check thermo state
                if hasattr(self._silicondb, 'thermo_state'):
                    thermo = self._silicondb.thermo_state()
                    if thermo:
                        temp = thermo.get("temperature", 0.0) if isinstance(thermo, dict) else getattr(thermo, "temperature", 0.0)
                        entropy = thermo.get("entropy_production", 0.0) if isinstance(thermo, dict) else getattr(thermo, "entropy_production", 0.0)
                        criticality = thermo.get("criticality", 0.0) if isinstance(thermo, dict) else getattr(thermo, "criticality", 0.0)

                        old_tier = self._tempo.current_tier
                        changed = self._tempo.update_temperature(temp)
                        if changed or self._verbose:
                            _log_event("thermo", "", f"temp={temp:.3f} entropy={entropy:.3f} crit={criticality:.3f} tier={self._tempo.current_tier.value}")

                        if changed:
                            self._reactor.on_thermo_shift({"temperature": temp})
                            should_analyze = True

                            # Synthesize thermo narrative
                            if self._synthesizer and hasattr(self._synthesizer, '_complete'):
                                try:
                                    narrative = self._synthesizer._complete(
                                        _FINANCE_SYSTEM,
                                        f"Market conviction temperature shifted from {_pretty(old_tier.value)} to {_pretty(self._tempo.current_tier.value)}.\n"
                                        f"Temperature: {temp:.3f} (belief volatility), Entropy: {entropy:.3f} (uncertainty rate), Criticality: {criticality:.3f} (phase transition proximity)\n"
                                        f"Holdings: {', '.join(self._symbols)}\n"
                                        f"Current regime: {_pretty(self._current_regime or 'unknown')}\n"
                                        f"Assess implications for position sizing, hedging, and factor exposure.",
                                        fallback="",
                                    )
                                    if narrative:
                                        _log_event("briefing", "", narrative)
                                except Exception:
                                    pass

                # Check for contradictions
                contradiction_details = []
                if hasattr(self._silicondb, 'detect_contradictions'):
                    contradictions = self._silicondb.detect_contradictions(samples=20, min_conflict_score=0.3, max_results=5)
                    if contradictions:
                        n = len(contradictions) if isinstance(contradictions, list) else 0
                        if n > 0:
                            if isinstance(contradictions, list):
                                contradiction_details = contradictions
                            if self._verbose:
                                _log_event("belief", "", f"{n} contradictions detected")
                            if self._tempo.should_analyze():
                                self._reactor.on_significant_shift({"contradictions": n})
                                should_analyze = True

                                # Synthesize contradiction narrative
                                if self._synthesizer and hasattr(self._synthesizer, '_complete') and contradiction_details:
                                    try:
                                        contra_str = "\n".join(
                                            f"  - {c.get('belief_a', c.get('a', '?'))} vs {c.get('belief_b', c.get('b', '?'))} "
                                            f"(conflict={c.get('conflict_score', c.get('score', '?'))})"
                                            for c in contradiction_details[:5]
                                            if isinstance(c, dict)
                                        )
                                        if contra_str:
                                            narrative = self._synthesizer._complete(
                                                _FINANCE_SYSTEM,
                                                f"Cross-factor belief divergence detected:\n{contra_str}\n"
                                                f"Holdings: {', '.join(self._symbols)}\n"
                                                f"Regime: {_pretty(self._current_regime or 'unknown')}\n"
                                                f"Assess correlation breakdown, mean reversion opportunity, and hedging implications.",
                                                fallback="",
                                            )
                                            if narrative:
                                                _log_event("briefing", "", narrative)
                                    except Exception:
                                        pass

                # Request epistemic briefing if something triggered analysis
                briefing = None
                if should_analyze and hasattr(self._silicondb, 'epistemic_briefing'):
                    briefing = self._silicondb.epistemic_briefing(
                        topic="market", budget=20, anchor_ratio=0.3, hops=2, neighbor_k=5,
                    )
                    if briefing and self._verbose:
                        if isinstance(briefing, dict):
                            anchors = briefing.get("anchors", [])
                            surprises = briefing.get("surprises", [])
                            conflicts = briefing.get("conflicts", [])
                            gaps = briefing.get("gaps", [])
                        else:
                            anchors = getattr(briefing, "anchors", [])
                            surprises = getattr(briefing, "surprises", [])
                            conflicts = getattr(briefing, "conflicts", [])
                            gaps = getattr(briefing, "gaps", [])
                        _log_event("briefing", "", f"anchors={len(anchors)} surprises={len(surprises)} conflicts={len(conflicts)} gaps={len(gaps)}")

                        # Synthesize briefing narrative
                        if self._synthesizer and hasattr(self._synthesizer, '_complete'):
                            try:
                                anchor_str = ", ".join(str(a) for a in anchors[:3]) if anchors else "none"
                                surprise_str = ", ".join(str(s) for s in surprises[:3]) if surprises else "none"
                                narrative = self._synthesizer._complete(
                                    _FINANCE_SYSTEM,
                                    f"High-conviction anchors (core alpha drivers): {anchor_str}\n"
                                    f"Surprise signals (information edge): {surprise_str}\n"
                                    f"Active conflicts: {len(conflicts)}, Knowledge gaps: {len(gaps)}\n"
                                    f"Holdings: {', '.join(self._symbols)}\n"
                                    f"Regime: {_pretty(self._current_regime or 'unknown')}\n"
                                    f"Synthesize risk-adjusted positioning and factor tilts.",
                                    fallback="",
                                )
                                if narrative:
                                    _log_event("briefing", "", narrative)
                            except Exception:
                                pass

                # Drain percolator events
                if hasattr(self._silicondb, 'event_sequence'):
                    try:
                        events = self._silicondb.replay_events(since_sequence=0, limit=50)
                        if events and len(events) > 0:
                            if self._verbose:
                                for evt in events[-5:]:
                                    evt_type = evt.get("event_type", "?") if isinstance(evt, dict) else str(evt)
                                    _log_event("belief", "", f"percolator: {evt_type}")
                            should_analyze = True  # Percolator fired → re-evaluate
                    except Exception:
                        pass

                # ── Only run analysis when percolator events triggered it ──
                if should_analyze:
                    self._run_analysis_cycle()

            except Exception as e:
                logger.error("Percolator loop error: %s", e)

    def _run_analysis_cycle(self):
        """Run regime detection → portfolio composition → trade execution."""
        if not self._controller or not self._broker:
            return

        try:
            # Build market metrics from PriceCache
            prices = {}
            returns = []
            for sym in self._symbols:
                entry = self._stream._price_cache.get(sym) if hasattr(self._stream, '_price_cache') else None
                if entry and entry.price > 0:
                    prices[sym] = float(entry.price)
                    if entry.price_return is not None:
                        returns.append(entry.price_return)

            if not prices or len(prices) < 2:
                return  # Not enough data yet

            avg_ret = statistics.mean(returns) if returns else 0.0
            vol = statistics.stdev(returns) if len(returns) > 1 else 0.0
            pos_pct = len([r for r in returns if r > 0]) / max(len(returns), 1)

            market_metrics = {
                "avg_return": avg_ret,
                "volatility": vol,
                "positive_pct": pos_pct,
                "momentum": avg_ret,  # simplified
            }

            # Build beliefs from price data
            beliefs_dict = {}
            for sym in self._symbols:
                entry = self._stream._price_cache.get(sym) if hasattr(self._stream, '_price_cache') else None
                if entry and entry.price_return is not None:
                    ret = entry.price_return
                    if ret > 0.002:
                        beliefs_dict[sym] = ("high_growth", min(0.9, 0.5 + ret * 50))
                    elif ret < -0.002:
                        beliefs_dict[sym] = ("declining", min(0.9, 0.5 + abs(ret) * 50))
                    else:
                        beliefs_dict[sym] = ("stable", 0.6)

            if not beliefs_dict:
                return

            # Get current portfolio weights (from broker positions)
            current_portfolio = {}
            try:
                positions = self._broker.get_positions()
                account = self._broker.get_account()
                total_value = float(account.equity) if account.equity > 0 else float(account.cash)
                for pos in positions:
                    current_portfolio[pos.symbol] = float(pos.market_value) / total_value if total_value > 0 else 0
            except Exception:
                pass

            # Run the controller
            state = self._controller.analyze(
                market_metrics=market_metrics,
                beliefs_dict=beliefs_dict,
                current_portfolio=current_portfolio,
                current_prices=prices,
            )

            regime_name = state.regime.name if hasattr(state.regime, 'name') else str(state.regime)
            strategy_name = state.selected_strategy.name if hasattr(state.selected_strategy, 'name') else str(state.selected_strategy)

            if self._verbose:
                _log_event("regime", "", f"{_pretty(regime_name)} | {_pretty(strategy_name)} | confidence {state.confidence:.0%}")

            # Check for regime change
            if self._current_regime and regime_name != self._current_regime:
                _log_event("regime", "", f"REGIME SHIFT: {_pretty(self._current_regime)} → {_pretty(regime_name)}")

                # Execute trades from the execution plan
                if state.execution_plan and state.execution_plan.trades:
                    for trade in state.execution_plan.trades:
                        try:
                            symbol = trade.symbol
                            side = "buy" if trade.type == "BUY" else "sell"
                            # Calculate qty from allocation and portfolio value
                            price = prices.get(symbol, 0)
                            if price > 0 and total_value > 0:
                                target_value = total_value * abs(trade.allocation)
                                qty = Decimal(str(int(target_value / price)))
                                if qty > 0:
                                    order = self._broker.submit_market_order(symbol=symbol, qty=qty, side=side)
                                    _log_event("fill", symbol, f"{side.upper()} {qty} shares @ ${price:,.2f} ({_pretty(trade.reason)})")

                                    # Generate narrative for this trade
                                    if self._synthesizer and hasattr(self._synthesizer, '_complete'):
                                        try:
                                            narrative = self._synthesizer._complete(
                                                _FINANCE_SYSTEM,
                                                f"Trade executed: {side.upper()} {qty} shares of {symbol} at ${price:,.2f}\n"
                                                f"Strategy: {_pretty(strategy_name)}\n"
                                                f"Regime: {_pretty(regime_name)}\n"
                                                f"Conviction: {state.confidence:.0%}\n"
                                                f"Reason: {trade.reason}\n"
                                                f"Explain the risk-reward rationale for this execution.",
                                                fallback="",
                                            )
                                            _log_event("briefing", symbol, narrative)
                                        except Exception:
                                            pass
                        except Exception as exc:
                            logger.error("Trade execution failed for %s: %s", trade.symbol, exc)

                    # Sync to Supabase after trades
                    try:
                        self._supabase.push_heartbeat(self._build_heartbeat())
                    except Exception:
                        pass

            self._current_regime = regime_name
            self._last_analysis = state

            # Signal detection
            if self._signal_tracker:
                all_tracked = list(self._stream._price_cache.all_symbols()) if hasattr(self._stream, '_price_cache') else self._symbols
                new_signals = self._signal_tracker.update(all_tracked)
                for sig in new_signals:
                    _log_event("signal", sig.symbol,
                        f"strength={sig.signal_strength:.2f} entropy={sig.entropy:.2f} "
                        f"thermo={sig.node_temperature:.2f}")

                decayed = self._signal_tracker.get_decayed()
                for sym in decayed:
                    _log_event("decay", sym, "signal decayed")

                # Sync top signals to Supabase
                top_signals = self._signal_tracker.get_signals()[:20]
                if top_signals:
                    try:
                        self._supabase.push_signals([{
                            "symbol": s.symbol,
                            "signal_strength": s.signal_strength,
                            "entropy": s.entropy,
                            "node_temperature": s.node_temperature,
                            "belief_type": s.belief_type,
                            "conviction": s.conviction,
                            "status": s.status,
                        } for s in top_signals])
                    except Exception:
                        pass

        except Exception as e:
            logger.error("Analysis cycle error: %s", e)

    # ── heartbeat ─────────────────────────────────────────────────────────────

    def _heartbeat_loop(self):
        while not self._stop_event.wait(self._interval):
            try:
                self._supabase.push_heartbeat(self._build_heartbeat())
            except Exception as e:
                logger.error("Heartbeat failed: %s", e)

    def _build_heartbeat(self):
        return {
            "status": "running",
            "alpaca_connected": self._stream.is_running,
            "active_positions": len(self._symbols),
            "current_regime": self._current_regime or "unknown",
            "next_action": "streaming",
            "dropped_events": self._stream.dropped_events,
        }
