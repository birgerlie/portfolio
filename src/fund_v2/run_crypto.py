"""V2 Crypto Paper Trading — runs continuously on 24/7 crypto markets.

Streams BTC, ETH, SOL from Alpaca, feeds through SiliconDB belief engine,
generates signals every 60s, logs everything to JSONL for analysis.

Usage:
    SILICONDB_LIBRARY_PATH=lib/silicondb/.build/release \
    PYTHONPATH=src:lib/silicondb/python \
    python3 -m fund_v2.run_crypto

    # Custom duration:
    DURATION_MINUTES=60 python3 -m fund_v2.run_crypto
"""

from __future__ import annotations

import json
import logging
import os
import queue
import signal
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

CRYPTO_PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD"]
SIGNAL_INTERVAL = 60  # seconds between signal generation


def _load_env():
    env_path = Path(__file__).resolve().parents[2] / "web" / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def run():
    _load_env()
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    alpaca_key = os.environ.get("ALPACA_API_KEY", "")
    alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not alpaca_key or not alpaca_secret:
        print("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY required")
        sys.exit(1)

    duration = int(os.environ.get("DURATION_MINUTES", "30")) * 60
    symbols_clean = [c.replace("/", "") for c in CRYPTO_PAIRS]

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Glass Box Fund V2 — Crypto Live Test                        ║
╠══════════════════════════════════════════════════════════════╣
║  Pairs:     {', '.join(CRYPTO_PAIRS):<47}║
║  Duration:  {duration // 60} minutes{' ' * 43}║
║  Signals:   every {SIGNAL_INTERVAL}s{' ' * 40}║
╚══════════════════════════════════════════════════════════════╝
""")

    # ── SiliconDB ────────────────────────────────────────────────────
    default_db = os.path.expanduser("~/.fund/silicondb_v2_crypto")
    db_dir = os.environ.get("V2_CRYPTO_DB_PATH", default_db)
    try:
        from silicondb.engine.native import SiliconDBNativeEngine
        engine = SiliconDBNativeEngine(db_dir, dimension=384, tenant_id=3)
        print(f"Engine: native (Metal GPU) at {db_dir}")
    except Exception:
        from silicondb.engine.mock import MockEngine
        engine = MockEngine()
        print("Engine: mock (native unavailable)")

    from silicondb.orm import App
    app = App(engine, internal_db_url="sqlite:///:memory:", tenant_id=3)

    from fund_v2.entities import ALL_ENTITIES, Instrument
    app.register(*ALL_ENTITIES)

    from silicondb.pipeline import Pipeline
    from silicondb.pipeline.validate import ValidateStage
    from silicondb.pipeline.normalise import NormaliseStage
    from silicondb.pipeline.route import RouteStage
    app._pipeline = Pipeline([ValidateStage(), NormaliseStage(), RouteStage()])

    # Seed instruments
    from silicondb.sources.models import SourceRecord
    from silicondb.pipeline.models import PipelineContext
    for sym in symbols_clean:
        r = SourceRecord(
            source_name="init", collection="seed", identity=sym,
            data={"symbol": sym, "price": 0, "trade_count": 0},
            timestamp=datetime.now(timezone.utc),
            idempotency_key=f"seed:{sym}", tenant_id=0,
        )
        try:
            app.get_pipeline().process(r, PipelineContext(engine=app.engine, entity_cls=Instrument, tenant_id=0))
        except Exception:
            pass

    # ── Alpaca stream ────────────────────────────────────────────────
    from fund.broker_types import AlpacaConfig, StreamConfig
    from fund.price_cache import PriceCache
    from fund.stream_service import AlpacaStreamService

    price_cache = PriceCache()
    event_queue = queue.Queue(maxsize=10000)
    stream = AlpacaStreamService(
        AlpacaConfig(api_key=alpaca_key, secret_key=alpaca_secret, paper=True),
        StreamConfig(
            portfolio_symbols=[], reference_symbols=[], macro_proxies=[],
            crypto_symbols=CRYPTO_PAIRS, tracked_symbols=symbols_clean,
            data_feed="iex",
        ),
        price_cache, event_queue,
    )
    stream.start()

    # ── Log file ─────────────────────────────────────────────────────
    log_dir = Path("logs/v2_crypto")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"crypto_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.jsonl"
    print(f"Logging to: {log_path}")

    def log_entry(entry_type: str, data: dict):
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "type": entry_type, **data}
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # ── Signal generation ────────────────────────────────────────────
    from fund_v2.signals import generate_signals_impl

    def generate_signals():
        regime = type("R", (), {"trend_following": 0.5, "mean_reverting_regime": 0.5, "risk_on": 0.5})()
        instruments = []
        for sym in symbols_clean:
            ext_id = f"instrument:{sym}"
            inst = type("I", (), {"external_id": ext_id, "symbol": sym})()
            for attr in ["relative_strength", "exhaustion", "pressure",
                         "retail_sentiment", "crowded", "price_trend_fast", "price_trend_slow"]:
                try:
                    val = engine.belief(f"{ext_id}:{attr}")
                except Exception:
                    val = 0.5
                setattr(inst, attr, val)
            instruments.append(inst)

        try:
            result = generate_signals_impl(engine, regime=regime, instruments=instruments)
            return result.get("signals", [])
        except Exception:
            return []

    # ── Consumer loop ────────────────────────────────────────────────
    stop_event = threading.Event()
    obs_count = 0
    trade_count = 0
    signal_count = 0
    last_signal_time = time.time()
    start_time = time.time()
    last_prices: Dict[str, float] = {}

    # Track signal accuracy
    signal_log: list = []  # (timestamp, symbol, direction, price_at_signal)

    def consume():
        nonlocal obs_count, trade_count, signal_count, last_signal_time

        while not stop_event.is_set():
            try:
                event = event_queue.get(timeout=1.0)
            except queue.Empty:
                # Check if it's time for signals
                now = time.time()
                if now - last_signal_time > SIGNAL_INTERVAL:
                    last_signal_time = now
                    _do_signals()
                continue

            if event.kind != "trade":
                continue

            sym = event.symbol.replace("/", "")
            ext_id = f"instrument:{sym}"
            price = float(event.data.get("price", 0))

            prev = price_cache.get(event.symbol) or price_cache.get(sym)
            if not prev or float(prev.price) <= 0:
                trade_count += 1
                last_prices[sym] = price
                continue

            prev_price = float(prev.price)
            price_up = price > prev_price
            move = abs(price - prev_price) / prev_price if prev_price > 0 else 0

            # Observe with strength proportional to move
            n = min(20, max(1, int(move * 10000)))
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

            # Exhaustion
            try:
                if move > 0.001:
                    engine.observe(f"{ext_id}:exhaustion", confirmed=True, source="alpaca")
                else:
                    engine.observe(f"{ext_id}:exhaustion", confirmed=False, source="alpaca")
                obs_count += 1
            except Exception:
                pass

            trade_count += 1
            last_prices[sym] = price

            # Signals on interval
            now = time.time()
            if now - last_signal_time > SIGNAL_INTERVAL:
                last_signal_time = now
                _do_signals()

    def _do_signals():
        nonlocal signal_count
        signals = generate_signals()
        elapsed = time.time() - start_time

        # Evaluate past signals (5-minute forward)
        now_prices = dict(last_prices)
        new_evaluated = 0
        correct = 0
        for entry in signal_log:
            if entry.get("evaluated"):
                continue
            age = time.time() - entry["time"]
            if age < 300:  # wait 5 minutes
                continue
            sym = entry["symbol"]
            if sym in now_prices and entry["price"] > 0:
                fwd_return = (now_prices[sym] - entry["price"]) / entry["price"]
                entry["fwd_return"] = fwd_return
                entry["correct"] = (
                    (entry["direction"] == "long" and fwd_return > 0) or
                    (entry["direction"] == "short" and fwd_return < 0)
                )
                entry["evaluated"] = True
                new_evaluated += 1
                if entry["correct"]:
                    correct += 1

        evaluated = [s for s in signal_log if s.get("evaluated")]
        total_eval = len(evaluated)
        total_correct = sum(1 for s in evaluated if s.get("correct"))
        accuracy = total_correct / total_eval if total_eval > 0 else 0

        # Print status
        print(f"\n[{elapsed/60:.1f}m] trades={trade_count} obs={obs_count} signals={signal_count} eval={total_eval} accuracy={accuracy:.1%}")
        for sym in symbols_clean:
            ext_id = f"instrument:{sym}"
            try:
                fast = engine.belief(f"{ext_id}:price_trend_fast")
                slow = engine.belief(f"{ext_id}:price_trend_slow")
                exh = engine.belief(f"{ext_id}:exhaustion")
                px = last_prices.get(sym, 0)
                px_str = f"${px:,.2f}" if px > 0 else "—"
                print(f"  {sym:>8}: {px_str:>12}  fast={fast:.3f}  slow={slow:.3f}  exh={exh:.3f}")
            except Exception:
                pass

        # Print signals
        for sig in signals:
            sym = sig.get("symbol", "")
            direction = sig.get("direction", "")
            edge = sig.get("edge", 0)
            conf = sig.get("confidence", 0)
            px = last_prices.get(sym, 0)
            emoji = "▲" if direction == "long" else "▼" if direction == "short" else "—"
            print(f"  {emoji} {sym} {direction} edge={edge:.3f} conf={conf:.3f}")

            # Log signal for accuracy tracking
            signal_log.append({
                "time": time.time(),
                "symbol": sym,
                "direction": direction,
                "edge": edge,
                "confidence": conf,
                "price": px,
                "evaluated": False,
            })
            signal_count += 1

            log_entry("signal", {
                "symbol": sym, "direction": direction,
                "edge": edge, "confidence": conf, "price": px,
            })

        if total_eval > 0:
            print(f"  Accuracy: {total_correct}/{total_eval} ({accuracy:.1%}) [5-min forward]")

        # Log beliefs
        beliefs = {}
        for sym in symbols_clean:
            ext_id = f"instrument:{sym}"
            b = {}
            for attr in ["price_trend_fast", "price_trend_slow", "exhaustion"]:
                try:
                    b[attr] = round(engine.belief(f"{ext_id}:{attr}"), 4)
                except Exception:
                    b[attr] = 0.5
            b["price"] = last_prices.get(sym, 0)
            beliefs[sym] = b
        log_entry("beliefs", {"beliefs": beliefs, "accuracy": accuracy, "evaluated": total_eval})

    # ── Start ────────────────────────────────────────────────────────
    consumer = threading.Thread(target=consume, daemon=True, name="crypto-consumer")
    consumer.start()

    def shutdown(signum, frame):
        print(f"\n\nShutting down...")
        stop_event.set()
        stream.stop()

        evaluated = [s for s in signal_log if s.get("evaluated")]
        total_eval = len(evaluated)
        total_correct = sum(1 for s in evaluated if s.get("correct"))
        accuracy = total_correct / total_eval if total_eval > 0 else 0

        print(f"\n{'='*50}")
        print(f"  FINAL RESULTS")
        print(f"{'='*50}")
        print(f"  Duration:    {(time.time() - start_time)/60:.1f} minutes")
        print(f"  Trades:      {trade_count}")
        print(f"  Observations:{obs_count}")
        print(f"  Signals:     {signal_count}")
        print(f"  Evaluated:   {total_eval}")
        print(f"  Accuracy:    {accuracy:.1%} ({total_correct}/{total_eval})")
        print(f"  Log:         {log_path}")

        # Per-symbol breakdown
        for sym in symbols_clean:
            sym_signals = [s for s in evaluated if s["symbol"] == sym]
            if sym_signals:
                sym_correct = sum(1 for s in sym_signals if s.get("correct"))
                sym_acc = sym_correct / len(sym_signals) if sym_signals else 0
                print(f"    {sym}: {sym_acc:.1%} ({sym_correct}/{len(sym_signals)})")

        try:
            engine.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"\nRunning for {duration // 60} minutes. Ctrl+C to stop early.\n")

    # Wait for duration or interrupt
    stop_event.wait(duration)
    if not stop_event.is_set():
        shutdown(None, None)


if __name__ == "__main__":
    run()
