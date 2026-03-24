"""V2 Crypto — Coinbase WebSocket feed (free, 770+ trades/min).

Usage:
    SILICONDB_LIBRARY_PATH=lib/silicondb/.build/release \
    PYTHONPATH=src:lib/silicondb/python \
    python3 -m fund_v2.run_crypto_coinbase

    DURATION_MINUTES=60 python3 -m fund_v2.run_crypto_coinbase
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
from typing import Dict

CRYPTO_PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD"]
SYMBOLS_CLEAN = ["BTCUSD", "ETHUSD", "SOLUSD"]
SIGNAL_INTERVAL = 60


def run():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    duration = int(os.environ.get("DURATION_MINUTES", "30")) * 60

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Glass Box Fund V2 — Coinbase Crypto (FREE, ~770 trades/m)  ║
╠══════════════════════════════════════════════════════════════╣
║  Pairs:     {', '.join(CRYPTO_PAIRS):<47}║
║  Duration:  {duration // 60} minutes{' ' * 43}║
║  Signals:   every {SIGNAL_INTERVAL}s{' ' * 40}║
╚══════════════════════════════════════════════════════════════╝
""")

    # SiliconDB
    db_dir = os.environ.get("V2_CRYPTO_DB_PATH", os.path.expanduser("~/.fund/silicondb_v2_crypto"))
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
    for sym in SYMBOLS_CLEAN:
        r = SourceRecord(source_name="init", collection="seed", identity=sym,
            data={"symbol": sym, "price": 0, "trade_count": 0},
            timestamp=datetime.now(timezone.utc), idempotency_key=f"seed:{sym}", tenant_id=0)
        try:
            app.get_pipeline().process(r, PipelineContext(engine=app.engine, entity_cls=Instrument, tenant_id=0))
        except Exception:
            pass

    # Coinbase WebSocket
    from fund_v2.sources.coinbase_ws import CoinbaseWebSocket
    event_queue = queue.Queue(maxsize=50000)
    ws = CoinbaseWebSocket(symbols=CRYPTO_PAIRS)
    ws.start(event_queue)

    # Log file
    log_dir = Path("logs/v2_crypto_coinbase")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"cb_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.jsonl"
    print(f"Log: {log_path}")

    def log(entry_type, data):
        with open(log_path, "a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "type": entry_type, **data}) + "\n")

    # Decision engine — unified beliefs + thermodynamics
    from fund_v2.decision_engine import generate_decision, format_decision

    # State
    stop = threading.Event()
    obs_count = 0
    trade_count = 0
    signal_count = 0
    last_signal = time.time()
    start = time.time()
    prices: Dict[str, float] = {}
    prev_prices: Dict[str, float] = {}
    signal_log = []

    def consume():
        nonlocal obs_count, trade_count, signal_count, last_signal

        while not stop.is_set():
            try:
                event = event_queue.get(timeout=0.5)
            except queue.Empty:
                now = time.time()
                if now - last_signal > SIGNAL_INTERVAL:
                    last_signal = now
                    do_signals()
                continue

            sym = event.symbol
            ext_id = f"instrument:{sym}"
            price = event.data.get("price", 0)

            prev = prev_prices.get(sym)
            if prev is None or prev <= 0:
                prev_prices[sym] = price
                prices[sym] = price
                trade_count += 1
                continue

            price_up = price > prev
            move = abs(price - prev) / prev if prev > 0 else 0
            prices[sym] = price
            prev_prices[sym] = price

            # Scale observations by move magnitude
            n = min(10, max(1, int(move * 20000)))
            for _ in range(n):
                try:
                    engine.observe(f"{ext_id}:price_trend_fast", confirmed=price_up, source="coinbase")
                    obs_count += 1
                except Exception:
                    break

            # Slow trend — fewer observations
            for _ in range(max(1, n // 4)):
                try:
                    engine.observe(f"{ext_id}:price_trend_slow", confirmed=price_up, source="coinbase")
                    obs_count += 1
                except Exception:
                    break

            # Exhaustion
            try:
                if move > 0.0005:
                    engine.observe(f"{ext_id}:exhaustion", confirmed=True, source="coinbase")
                elif move < 0.0001:
                    engine.observe(f"{ext_id}:exhaustion", confirmed=False, source="coinbase")
                obs_count += 1
            except Exception:
                pass

            trade_count += 1

            # Signals on interval
            now = time.time()
            if now - last_signal > SIGNAL_INTERVAL:
                last_signal = now
                do_signals()

    def do_signals():
        nonlocal signal_count

        # Unified decision: beliefs + thermodynamics in one pass
        decision = generate_decision(
            engine=engine,
            symbols=SYMBOLS_CLEAN,
            cost_per_symbol={s: 5 for s in SYMBOLS_CLEAN},  # 5 bps default for crypto
        )
        elapsed = time.time() - start

        # Evaluate past signals (5-min forward)
        for entry in signal_log:
            if entry.get("eval"):
                continue
            if time.time() - entry["t"] < 300:
                continue
            sym = entry["sym"]
            if sym in prices and entry["px"] > 0:
                fwd = (prices[sym] - entry["px"]) / entry["px"]
                entry["fwd"] = fwd
                entry["ok"] = (entry["dir"] == "long" and fwd > 0) or (entry["dir"] == "short" and fwd < 0)
                entry["eval"] = True

        total_eval = sum(1 for s in signal_log if s.get("eval"))
        total_ok = sum(1 for s in signal_log if s.get("ok"))
        acc = total_ok / total_eval if total_eval > 0 else 0

        # Print system state + signals
        print(f"\n[{elapsed/60:.1f}m] trades={trade_count:,} obs={obs_count:,} signals={signal_count} eval={total_eval} acc={acc:.1%}")
        print(format_decision(decision))

        # Add prices to output
        for sym in SYMBOLS_CLEAN:
            px = prices.get(sym, 0)
            if px > 0:
                ext_id = f"instrument:{sym}"
                try:
                    fast = engine.belief(f"{ext_id}:price_trend_fast")
                    slow = engine.belief(f"{ext_id}:price_trend_slow")
                    print(f"  {sym:>8}: ${px:>10,.2f}  fast={fast:.3f}  slow={slow:.3f}")
                except Exception:
                    print(f"  {sym:>8}: ${px:>10,.2f}")

        # Log signals for accuracy tracking
        for sig in decision.signals:
            if sig.direction == "neutral":
                continue
            px = prices.get(sig.symbol, 0)
            signal_log.append({
                "t": time.time(), "sym": sig.symbol, "dir": sig.direction,
                "edge": sig.edge, "px": px, "size": sig.size,
                "free_energy": sig.free_energy, "velocity": sig.velocity,
                "phase": sig.phase,
            })
            signal_count += 1
            log("signal", {
                "symbol": sig.symbol, "direction": sig.direction,
                "edge": sig.edge, "conviction": sig.conviction,
                "size": sig.size, "price": px,
                "momentum": sig.momentum_component,
                "thermo": sig.thermo_component,
                "free_energy": sig.free_energy, "velocity": sig.velocity,
                "phase": sig.phase,
                "system_temp": decision.system.temperature,
                "system_crit": decision.system.criticality,
            })

        if total_eval > 0:
            print(f"  Accuracy: {total_ok}/{total_eval} ({acc:.1%}) [5-min forward]")

        # Log system state
        log("system", {
            "temperature": decision.system.temperature,
            "entropy": decision.system.entropy,
            "criticality": decision.system.criticality,
            "criticality_tier": decision.system.criticality_tier,
            "temp_scalar": decision.temperature_scalar,
            "crit_discount": decision.criticality_discount,
            "hotspots": decision.focus_count,
            "accuracy": acc, "evaluated": total_eval,
            "trades": trade_count, "obs": obs_count,
        })

    # Start
    consumer = threading.Thread(target=consume, daemon=True, name="cb-consumer")
    consumer.start()

    def shutdown(signum, frame):
        print(f"\n\nShutting down...")
        stop.set()
        ws.stop()

        total_eval = sum(1 for s in signal_log if s.get("eval"))
        total_ok = sum(1 for s in signal_log if s.get("ok"))
        acc = total_ok / total_eval if total_eval > 0 else 0

        print(f"\n{'='*55}")
        print(f"  FINAL RESULTS — Coinbase Feed")
        print(f"{'='*55}")
        print(f"  Duration:      {(time.time() - start)/60:.1f} minutes")
        print(f"  Trades:        {trade_count:,}")
        print(f"  Observations:  {obs_count:,}")
        print(f"  Signals:       {signal_count}")
        print(f"  Evaluated:     {total_eval}")
        print(f"  Accuracy:      {acc:.1%} ({total_ok}/{total_eval})")
        print(f"  Log:           {log_path}")
        for sym in SYMBOLS_CLEAN:
            sym_sigs = [s for s in signal_log if s.get("eval") and s["sym"] == sym]
            if sym_sigs:
                ok = sum(1 for s in sym_sigs if s.get("ok"))
                print(f"    {sym}: {ok}/{len(sym_sigs)} ({ok/len(sym_sigs):.1%})")

        try:
            engine.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"\nRunning for {duration//60} minutes. Ctrl+C to stop.\n")
    stop.wait(duration)
    if not stop.is_set():
        shutdown(None, None)


if __name__ == "__main__":
    run()
