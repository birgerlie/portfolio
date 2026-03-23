"""V2 Paper Trading Runner — runs alongside V1 for live comparison.

Connects to Alpaca paper trading, feeds live trades/quotes through the
ORM pipeline with real SiliconDB engine, and logs signals for comparison.

Usage:
    SILICONDB_LIBRARY_PATH=lib/silicondb/.build/release \
    PYTHONPATH=src:lib/silicondb/python \
    python3 -m fund_v2.run_paper

    # Or with custom symbols:
    PORTFOLIO_SYMBOLS=AAPL,MSFT,NVDA python3 -m fund_v2.run_paper
"""

from __future__ import annotations

import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ── Load env vars from web/.env.local ────────────────────────────────────────

def _load_env():
    """Load Alpaca credentials from web/.env.local."""
    env_path = Path(__file__).resolve().parents[2] / "web" / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


# ── Signal logger ────────────────────────────────────────────────────────────

class SignalLogger:
    """Logs V2 signals to JSONL for comparison with V1."""

    def __init__(self, log_dir: str = "logs/v2_paper"):
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._path = self._dir / f"signals_{self._date}.jsonl"
        self._count = 0

    def log_signal(self, signal: dict):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "signal",
            **signal,
        }
        with open(self._path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self._count += 1

    def log_event(self, event_type: str, data: dict):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **data,
        }
        with open(self._path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_beliefs(self, beliefs: dict):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "belief_snapshot",
            "beliefs": beliefs,
        }
        with open(self._path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    @property
    def count(self):
        return self._count


# ── Main runner ──────────────────────────────────────────────────────────────

def run():
    """Start V2 paper trading engine."""
    _load_env()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Config from env ──────────────────────────────────────────────
    alpaca_api_key = os.environ.get("ALPACA_API_KEY", "")
    alpaca_secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    alpaca_paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    if not alpaca_api_key or not alpaca_secret_key:
        print("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY required (in web/.env.local)")
        sys.exit(1)

    portfolio_str = os.environ.get("PORTFOLIO_SYMBOLS", "AAPL,MSFT,NVDA,GOOG,AMZN")
    portfolio_symbols = [s.strip() for s in portfolio_str.split(",") if s.strip()]
    reference_symbols = ["SPY", "QQQ", "IWM", "DIA"]
    macro_proxies = ["TLT", "USO", "UUP", "UVXY", "GLD"]

    all_symbols = list(set(portfolio_symbols + reference_symbols + macro_proxies))

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Glass Box Fund — V2 Paper Trading Engine                    ║
║  Built on SiliconDB ORM + Layered Belief Model               ║
╠══════════════════════════════════════════════════════════════╣
║  Portfolio:    {', '.join(portfolio_symbols):<44}║
║  References:   {', '.join(reference_symbols):<44}║
║  Macro:        {', '.join(macro_proxies):<44}║
║  Total:        {len(all_symbols)} symbols{' ' * 38}║
║  Paper:        {str(alpaca_paper):<44}║
╚══════════════════════════════════════════════════════════════╝
""")

    # ── SiliconDB engine ─────────────────────────────────────────────
    import tempfile
    db_dir = os.environ.get("V2_DB_PATH", tempfile.mkdtemp(prefix="fund_v2_paper_"))
    print(f"SiliconDB: {db_dir}")

    try:
        from silicondb.engine.native import SiliconDBNativeEngine
        engine = SiliconDBNativeEngine(db_dir, dimension=384)
        engine_type = "native"
    except Exception as e:
        print(f"WARNING: Native engine unavailable ({e}), using MockEngine")
        from silicondb.engine.mock import MockEngine
        engine = MockEngine()
        engine_type = "mock"

    print(f"Engine: {engine_type}")

    # ── ORM App ──────────────────────────────────────────────────────
    from silicondb.orm import App
    app = App(engine, internal_db_url="sqlite:///:memory:")

    from fund_v2.entities import ALL_ENTITIES
    app.register(*ALL_ENTITIES)

    # Register hooks
    from silicondb.orm.hooks import collect_hooks_from_module
    import fund_v2.hooks as hook_module
    for hook in collect_hooks_from_module(hook_module):
        app._hook_registry.register(
            hook_type=hook["hook_type"],
            entity_type=hook["entity_type"],
            field_name=hook.get("field_name"),
            callback=hook["callback"],
        )

    # Register tools
    from fund_v2.tools import register_tools
    register_tools(app)

    # Execution policy
    from silicondb.orm.execution import ExecutionPolicy
    app._execution_policy = ExecutionPolicy(
        auto_approve=["volatility_alert", "macro_shift", "sector_rotation",
                       "conviction_flip_warning", "macro_flip_predicted",
                       "sector_headwind_predicted", "risk_off_predicted"],
        human_approve=["buy", "sell"],
        confidence_gate={"sell": 0.95},
        cooldown={"buy": 3600, "sell": 1800},
    )

    # Pipeline without dedup (live data has unique timestamps)
    from silicondb.pipeline import Pipeline
    from silicondb.pipeline.validate import ValidateStage
    from silicondb.pipeline.normalise import NormaliseStage
    from silicondb.pipeline.route import RouteStage
    app._pipeline = Pipeline([ValidateStage(), NormaliseStage(), RouteStage()])

    print(f"Entities: {len(ALL_ENTITIES)} registered")

    # ── Ontology ─────────────────────────────────────────────────────
    from fund_v2.backtest_harness import setup_ontology
    setup_ontology(app, portfolio_symbols + reference_symbols, macro_proxies)

    # ── Seed instruments via pipeline ────────────────────────────────
    from fund_v2.entities import Instrument, MacroFactor
    from silicondb.sources.models import SourceRecord
    from silicondb.pipeline.models import PipelineContext

    pipeline = app.get_pipeline()
    for symbol in all_symbols:
        is_macro = symbol in macro_proxies
        entity_cls = MacroFactor if is_macro else Instrument
        record = SourceRecord(
            source_name="init",
            collection="seed",
            identity=symbol,
            data={"symbol": symbol, "price": 0, "trade_count": 0},
            timestamp=datetime.now(timezone.utc),
            idempotency_key=f"seed:{symbol}",
            tenant_id=0,
        )
        ctx = PipelineContext(engine=app.engine, entity_cls=entity_cls, tenant_id=0)
        try:
            pipeline.process(record, ctx)
        except Exception:
            pass

    print(f"Seeded {len(all_symbols)} instruments")

    # ── Alpaca stream ────────────────────────────────────────────────
    from fund.broker_types import AlpacaConfig, StreamConfig
    from fund.price_cache import PriceCache
    from fund.stream_service import AlpacaStreamService
    from fund_v2.sources.alpaca import AlpacaSourceAdapter

    alpaca_cfg = AlpacaConfig(
        api_key=alpaca_api_key,
        secret_key=alpaca_secret_key,
        paper=alpaca_paper,
    )
    stream_cfg = StreamConfig(
        portfolio_symbols=portfolio_symbols,
        reference_symbols=reference_symbols,
        macro_proxies=macro_proxies,
        crypto_symbols=[],
        tracked_symbols=all_symbols,
        data_feed="iex",
    )

    price_cache = PriceCache()
    event_queue = queue.Queue(maxsize=10000)
    stream = AlpacaStreamService(alpaca_cfg, stream_cfg, price_cache, event_queue)
    adapter = AlpacaSourceAdapter(symbols=all_symbols)
    sig_logger = SignalLogger()

    print("Starting Alpaca stream...")
    stream.start()

    # ── Event consumer ───────────────────────────────────────────────
    stop_event = threading.Event()
    observation_count = 0
    last_signal_time = time.time()
    signal_interval = 60  # generate signals every 60 seconds

    def consume_events():
        nonlocal observation_count, last_signal_time

        while not stop_event.is_set():
            try:
                event = event_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            symbol = event.symbol
            is_macro = symbol in macro_proxies
            prefix = "macrofactor" if is_macro else "instrument"
            ext_id = f"{prefix}:{symbol}"

            # Route trade/quote events to beliefs
            if event.kind == "trade":
                price = event.data.get("price", 0)
                size = event.data.get("size", 0)
                prev = price_cache.get(symbol)
                if prev and prev.price > 0:
                    price_up = price > prev.price
                    move_pct = abs(price - prev.price) / prev.price

                    # Map beliefs based on entity type
                    if is_macro:
                        # MacroFactor has: elevated, trending
                        try:
                            app.engine.observe(f"{ext_id}:trending", confirmed=price_up, source="alpaca")
                            app.engine.observe(f"{ext_id}:elevated", confirmed=price_up, source="alpaca")
                        except Exception:
                            pass
                    else:
                        # Instrument has: price_trend_fast, price_trend_slow, spread_tight, etc.
                        # Multiple observations per trade — larger moves get more weight
                        n_obs = max(1, int(move_pct * 5000))  # 0.1% move = 5 obs, 1% = 50
                        n_obs = min(n_obs, 20)  # cap at 20 per trade

                        for _ in range(n_obs):
                            try:
                                app.engine.observe(f"{ext_id}:price_trend_fast", confirmed=price_up, source="alpaca")
                            except Exception:
                                break

                        # Slow trend gets fewer observations (more inertia)
                        for _ in range(max(1, n_obs // 3)):
                            try:
                                app.engine.observe(f"{ext_id}:price_trend_slow", confirmed=price_up, source="alpaca")
                            except Exception:
                                break

                        # Exhaustion: large moves in either direction
                        try:
                            if move_pct > 0.002:  # > 0.2% move
                                app.engine.observe(f"{ext_id}:exhaustion", confirmed=True, source="alpaca")
                            elif move_pct < 0.0005:  # tiny move = cooling
                                app.engine.observe(f"{ext_id}:exhaustion", confirmed=False, source="alpaca")
                        except Exception:
                            pass

                        # Volume/liquidity
                        try:
                            app.engine.observe(f"{ext_id}:spread_tight", confirmed=True, source="alpaca")
                            app.engine.observe(f"{ext_id}:volume_normal", confirmed=(size > 0), source="alpaca")
                        except Exception:
                            pass

                    # Propagate through graph (from ontology node, not entity ID)
                    try:
                        if hasattr(app.engine, "propagate"):
                            app.engine.propagate(
                                external_id=symbol,  # ontology node for graph traversal
                                confidence=0.3 + move_pct * 10,
                                decay=0.4,
                            )
                    except Exception:
                        pass

                    observation_count += 1

            elif event.kind == "quote":
                bid = event.data.get("bid", 0)
                ask = event.data.get("ask", 0)
                if bid > 0 and ask > 0 and not is_macro:
                    spread = (ask - bid) / bid
                    tight = spread < 0.005
                    try:
                        app.engine.observe(f"{ext_id}:spread_tight", confirmed=tight, source="alpaca")
                    except Exception:
                        pass

            # Periodic signal generation
            now = time.time()
            if now - last_signal_time > signal_interval:
                last_signal_time = now
                _generate_and_log_signals(app, portfolio_symbols, macro_proxies, sig_logger, observation_count)

    def _generate_and_log_signals(app, symbols, proxies, logger, obs_count):
        """Generate signals and log them."""
        from fund_v2.backtest_harness import run_daily_signals, collect_daily_state, _derive_layer2_from_graph

        # Derive Layer 2 beliefs from graph
        data_stub = {s: type("SD", (), {"closes": [0], "dates": []})() for s in symbols}
        _derive_layer2_from_graph(app, data_stub, set(proxies))

        # Generate signals
        signals = run_daily_signals(app, symbols, proxies)

        # Log belief snapshot
        beliefs = collect_daily_state(app, symbols, proxies)
        logger.log_beliefs(beliefs)

        # Log each signal
        for sig in signals:
            logger.log_signal(sig)

        # Print summary
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        n_sigs = len(signals)
        top = signals[0] if signals else None
        top_str = f" | top: {top['symbol']} {top['direction']} edge={top['edge']:.3f}" if top else ""
        print(f"[{ts}] obs={obs_count} signals={n_sigs}{top_str} (logged to {logger._path.name})")

        # Print beliefs for portfolio symbols
        for sym in symbols[:5]:
            b = beliefs.get(sym, {})
            fast = b.get("price_trend_fast", 0.5)
            rs = b.get("relative_strength", 0.5)
            exh = b.get("exhaustion", 0.5)
            prs = b.get("pressure", 0.5)
            print(f"  {sym:>6}: fast={fast:.3f} rs={rs:.3f} exh={exh:.3f} prs={prs:.3f}")

    # ── Start consumer thread ────────────────────────────────────────
    consumer = threading.Thread(target=consume_events, daemon=True, name="v2-consumer")
    consumer.start()

    # ── Graceful shutdown ────────────────────────────────────────────
    def shutdown(signum, frame):
        print("\nShutting down V2 paper trading...")
        stop_event.set()
        stream.stop()
        try:
            engine.close()
        except Exception:
            pass
        print(f"Total observations: {observation_count}")
        print(f"Total signals logged: {sig_logger.count}")
        print(f"Log file: {sig_logger._path}")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"\nV2 paper trading running. Signals every {signal_interval}s.")
    print("Press Ctrl+C to stop.\n")

    # Block main thread
    while not stop_event.is_set():
        stop_event.wait(10)


if __name__ == "__main__":
    run()
