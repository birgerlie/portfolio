"""V2 Live Equities — E_adapt_all strategy on Alpaca paper trading.

Runs during US market hours (9:30 AM - 4:00 PM ET).
Uses the winning strategy: prediction + graph + adaptive.

Usage:
    SILICONDB_LIBRARY_PATH=lib/silicondb/.build/release \
    PYTHONPATH=src:lib/silicondb/python \
    python3 -m fund_v2.run_equities
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
from typing import Dict, List

PORTFOLIO = ["AAPL", "MSFT", "NVDA", "GOOG", "AMZN"]
REFERENCES = ["SPY", "QQQ", "IWM", "DIA"]
MACRO = ["TLT", "USO", "UUP", "UVXY", "GLD"]
ALL_SYMBOLS = list(set(PORTFOLIO + REFERENCES + MACRO))
SIGNAL_INTERVAL = 60


def _load_env():
    env_path = Path(__file__).resolve().parents[2] / "web" / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _strategy(fast, slow, vol, market_trend, win_rate, n_trades):
    """E_adapt_all: prediction + graph + adaptive."""
    # Self-awareness
    if win_rate < 0.35 and n_trades >= 10:
        return "neutral", 0.0
    scale = 1.3 if win_rate > 0.55 else (0.2 if win_rate < 0.45 and n_trades >= 10 else 1.0)

    # Prediction crash detector
    velocity = fast - slow
    predicted = fast + velocity * 3
    if predicted < 0.25 and vol > 0.02:
        return "sell", min(0.15, (0.5 - predicted) * 0.3 + vol) * scale

    # Graph early warning
    divergence = fast - market_trend
    if market_trend < 0.40 and divergence > 0.10:
        return "sell", min(0.10, divergence * 0.3) * scale
    if market_trend > 0.60 and divergence < -0.10:
        return "buy", min(0.10, abs(divergence) * 0.3) * scale

    # Recovery
    if vol > 0.02 and fast > slow + 0.05 and slow < 0.45:
        return "buy", min(0.08, (fast - slow) * 0.5) * scale

    # Trending
    agreement = 1 - abs((fast - 0.5) - (slow - 0.5)) * 2
    conviction = abs(fast - 0.5) + abs(slow - 0.5)
    if agreement < 0.6 or conviction < 0.15:
        return "neutral", 0.0

    avg = fast * 0.6 + slow * 0.4
    if avg > 0.55:
        return "buy", min(0.10, (avg - 0.5) * 0.5 * scale)
    elif avg < 0.45:
        return "sell", min(0.10, (0.5 - avg) * 0.5 * scale)
    return "neutral", 0.0


def run():
    _load_env()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    alpaca_key = os.environ.get("ALPACA_API_KEY", "")
    alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not alpaca_key or not alpaca_secret:
        print("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY required")
        sys.exit(1)

    duration = int(os.environ.get("DURATION_MINUTES", "390")) * 60  # full trading day

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Rock & Grolla Trading Club — V2 Live Equities               ║
║  Strategy: E_adapt_all (prediction + graph + adaptive)       ║
╠══════════════════════════════════════════════════════════════╣
║  Portfolio:  {', '.join(PORTFOLIO):<46}║
║  References: {', '.join(REFERENCES):<46}║
║  Macro:      {', '.join(MACRO):<46}║
║  Duration:   {duration // 60} minutes{' ' * 40}║
╚══════════════════════════════════════════════════════════════╝
""")

    # SiliconDB
    db_dir = os.path.expanduser("~/.fund/silicondb_v2_equities")
    try:
        from silicondb.engine.native import SiliconDBNativeEngine
        engine = SiliconDBNativeEngine(db_dir, dimension=384, tenant_id=3)
        print(f"Engine: native (Metal GPU) at {db_dir}")
    except Exception:
        from silicondb.engine.mock import MockEngine
        engine = MockEngine()
        print("Engine: mock")

    from silicondb.orm import App
    app = App(engine, internal_db_url="sqlite:///:memory:", tenant_id=3)
    from fund_v2.entities import ALL_ENTITIES, Instrument, MacroFactor
    app.register(*ALL_ENTITIES)

    from silicondb.pipeline import Pipeline
    from silicondb.pipeline.validate import ValidateStage
    from silicondb.pipeline.normalise import NormaliseStage
    from silicondb.pipeline.route import RouteStage
    app._pipeline = Pipeline([ValidateStage(), NormaliseStage(), RouteStage()])

    # Thermo
    from fund_v2.decision_engine import _get_native
    native = _get_native(engine)
    if native and hasattr(native, 'init_thermo'):
        native.init_thermo(max_nodes=10000)
        print("Thermo: initialized")

    # Seed instruments
    from silicondb.sources.models import SourceRecord
    from silicondb.pipeline.models import PipelineContext
    for sym in ALL_SYMBOLS:
        is_macro = sym in MACRO
        cls = MacroFactor if is_macro else Instrument
        r = SourceRecord(source_name="init", collection="seed", identity=sym,
            data={"symbol": sym, "price": 0, "trade_count": 0},
            timestamp=datetime.now(timezone.utc), idempotency_key=f"seed:{sym}", tenant_id=0)
        try:
            app.get_pipeline().process(r, PipelineContext(engine=app.engine, entity_cls=cls, tenant_id=0))
        except Exception:
            pass

    # Ontology
    from fund_v2.backtest_harness import setup_ontology
    setup_ontology(app, PORTFOLIO + REFERENCES, MACRO)
    print(f"Seeded {len(ALL_SYMBOLS)} instruments with ontology")

    # Alpaca stream
    from fund.broker_types import AlpacaConfig, StreamConfig
    from fund.price_cache import PriceCache
    from fund.stream_service import AlpacaStreamService

    price_cache = PriceCache()
    event_queue = queue.Queue(maxsize=50000)
    stream = AlpacaStreamService(
        AlpacaConfig(api_key=alpaca_key, secret_key=alpaca_secret, paper=True),
        StreamConfig(portfolio_symbols=PORTFOLIO, reference_symbols=REFERENCES,
                     macro_proxies=MACRO, crypto_symbols=[], tracked_symbols=ALL_SYMBOLS,
                     data_feed="iex"),
        price_cache, event_queue)
    stream.start()

    # Log
    log_dir = Path("logs/v2_equities")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"eq_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.jsonl"
    print(f"Log: {log_path}")

    def log(entry_type, data):
        with open(log_path, "a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "type": entry_type, **data}) + "\n")

    # State
    stop = threading.Event()
    obs_count = 0
    trade_count = 0
    signal_count = 0
    last_signal = time.time()
    start = time.time()
    prices: Dict[str, float] = {}
    prev_prices: Dict[str, float] = {}
    signal_log: list = []

    def consume():
        nonlocal obs_count, trade_count, signal_count, last_signal

        while not stop.is_set():
            try:
                event = event_queue.get(timeout=1.0)
            except queue.Empty:
                now = time.time()
                if now - last_signal > SIGNAL_INTERVAL:
                    last_signal = now
                    do_signals()
                continue

            if event.kind != "trade":
                continue

            sym = event.symbol
            is_macro = sym in MACRO
            prefix = "macrofactor" if is_macro else "instrument"
            ext_id = f"{prefix}:{sym}"
            price = float(event.data.get("price", 0))

            prev = price_cache.get(sym)
            if not prev or float(prev.price) <= 0:
                prices[sym] = price
                trade_count += 1
                continue

            prev_price = float(prev.price)
            price_up = price > prev_price
            move = abs(price - prev_price) / prev_price if prev_price > 0 else 0
            prices[sym] = price

            # Direction flip detection
            prev_up = prev_prices.get(sym + "_dir")
            flipped = prev_up is not None and price_up != prev_up
            prev_prices[sym + "_dir"] = price_up

            n = min(10, max(1, int(move * 20000)))
            if flipped:
                n = min(30, n * 3)

            if is_macro:
                try:
                    engine.observe(f"{ext_id}:trending", confirmed=price_up, source="alpaca")
                    engine.observe(f"{ext_id}:elevated", confirmed=price_up, source="alpaca")
                    obs_count += 2
                except Exception:
                    pass
            else:
                for _ in range(n):
                    try:
                        engine.observe(f"{ext_id}:price_trend_fast", confirmed=price_up, source="alpaca")
                        obs_count += 1
                    except Exception:
                        break
                for _ in range(max(1, n // 3)):
                    try:
                        engine.observe(f"{ext_id}:price_trend_slow", confirmed=price_up, source="alpaca")
                        obs_count += 1
                    except Exception:
                        break
                if move > 0.002:
                    try:
                        engine.observe(f"{ext_id}:exhaustion", confirmed=True, source="alpaca")
                    except Exception:
                        pass

            trade_count += 1

            now = time.time()
            if now - last_signal > SIGNAL_INTERVAL:
                last_signal = now
                do_signals()

    def do_signals():
        nonlocal signal_count
        elapsed = time.time() - start

        # Run thermo pass
        if native and hasattr(native, 'run_thermo_pass'):
            try:
                native.run_thermo_pass()
            except Exception:
                pass

        # Get SPY trend as market signal
        spy_fast = 0.5
        try:
            spy_fast = engine.belief("instrument:SPY:price_trend_fast")
        except Exception:
            pass

        # Evaluate past signals
        for entry in signal_log:
            if entry.get("eval"):
                continue
            if time.time() - entry["t"] < 300:
                continue
            sym = entry["sym"]
            if sym in prices and entry["px"] > 0:
                fwd = (prices[sym] - entry["px"]) / entry["px"]
                entry["fwd"] = fwd
                entry["ok"] = (
                    (entry["dir"] in ("buy",) and fwd > 0) or
                    (entry["dir"] in ("sell",) and fwd < 0)
                )
                entry["eval"] = True

        total_eval = sum(1 for s in signal_log if s.get("eval"))
        total_ok = sum(1 for s in signal_log if s.get("ok"))
        acc = total_ok / total_eval if total_eval > 0 else 0
        recent_wins = [1.0 if s.get("ok") else 0.0 for s in signal_log if s.get("eval")][-20:]
        win_rate = sum(recent_wins) / len(recent_wins) if len(recent_wins) >= 5 else 0.5

        print(f"\n[{elapsed/60:.1f}m] trades={trade_count:,} obs={obs_count:,} signals={signal_count} eval={total_eval} acc={acc:.1%} win_rate={win_rate:.0%}")

        # Run strategy on each portfolio symbol
        seen = set()
        for sym in PORTFOLIO:
            ext_id = f"instrument:{sym}"
            try:
                fast = engine.belief(f"{ext_id}:price_trend_fast")
                slow = engine.belief(f"{ext_id}:price_trend_slow")
            except Exception:
                fast = slow = 0.5

            # Rough volatility from belief distance
            vol = abs(fast - slow) * 2

            direction, size = _strategy(fast, slow, vol, spy_fast, win_rate, len(recent_wins))

            px = prices.get(sym, 0)
            arrow = "▲" if direction == "buy" else "▼" if direction == "sell" else "—"
            print(f"  {arrow} {sym:>6} {direction:>7} size={size:.1%} fast={fast:.3f} slow={slow:.3f} vol={vol:.3f} px=${px:,.2f}")

            if direction != "neutral" and size > 0 and sym not in seen:
                seen.add(sym)
                signal_log.append({"t": time.time(), "sym": sym, "dir": direction, "px": px})
                signal_count += 1
                log("signal", {"symbol": sym, "direction": direction, "size": size, "price": px,
                               "fast": fast, "slow": slow, "spy": spy_fast, "win_rate": win_rate})

        print(f"  SPY trend: {spy_fast:.3f} | Win rate: {win_rate:.0%} ({len(recent_wins)} recent)")
        if total_eval > 0:
            print(f"  Accuracy: {total_ok}/{total_eval} ({acc:.1%})")

        log("system", {"accuracy": acc, "evaluated": total_eval, "win_rate": win_rate,
                        "spy_trend": spy_fast, "trades": trade_count, "obs": obs_count})

    # Start
    consumer = threading.Thread(target=consume, daemon=True, name="eq-consumer")
    consumer.start()

    def shutdown(signum, frame):
        print(f"\n\nShutting down...")
        stop.set()
        stream.stop()

        total_eval = sum(1 for s in signal_log if s.get("eval"))
        total_ok = sum(1 for s in signal_log if s.get("ok"))
        acc = total_ok / total_eval if total_eval > 0 else 0

        print(f"\n{'='*55}")
        print(f"  FINAL — Rock & Grolla V2 Equities")
        print(f"{'='*55}")
        print(f"  Duration:    {(time.time() - start)/60:.1f} min")
        print(f"  Trades:      {trade_count:,}")
        print(f"  Signals:     {signal_count}")
        print(f"  Evaluated:   {total_eval}")
        print(f"  Accuracy:    {acc:.1%} ({total_ok}/{total_eval})")
        print(f"  Log:         {log_path}")

        try:
            engine.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"\nRunning for {duration//60} min. Ctrl+C to stop.\n")
    stop.wait(duration)
    if not stop.is_set():
        shutdown(None, None)


if __name__ == "__main__":
    run()
