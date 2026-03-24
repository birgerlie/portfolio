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

    # Signal generation
    from fund_v2.signals import generate_signals_impl

    def gen_signals():
        regime = type("R", (), {"trend_following": 0.5, "mean_reverting_regime": 0.5, "risk_on": 0.5})()
        instruments = []
        for sym in SYMBOLS_CLEAN:
            ext_id = f"instrument:{sym}"
            inst = type("I", (), {"external_id": ext_id, "symbol": sym})()
            for attr in ["relative_strength", "exhaustion", "pressure",
                         "retail_sentiment", "crowded", "price_trend_fast", "price_trend_slow"]:
                try:
                    setattr(inst, attr, engine.belief(f"{ext_id}:{attr}"))
                except Exception:
                    setattr(inst, attr, 0.5)
            instruments.append(inst)
        try:
            return generate_signals_impl(engine, regime=regime, instruments=instruments).get("signals", [])
        except Exception:
            return []

    # (#4) Relative strength between coins
    _rs_baseline: Dict[str, float] = {}

    def _update_relative_strength(eng, current_prices, syms):
        nonlocal _rs_baseline
        # Initialize baselines on first call
        if not _rs_baseline:
            _rs_baseline.update(current_prices)
            return
        # Compute returns since baseline for each symbol
        returns = {}
        for s in syms:
            if s in current_prices and s in _rs_baseline and _rs_baseline[s] > 0:
                returns[s] = (current_prices[s] - _rs_baseline[s]) / _rs_baseline[s]
        if len(returns) < 2:
            return
        avg_ret = sum(returns.values()) / len(returns)
        for s, ret in returns.items():
            try:
                eng.observe(f"instrument:{s}:relative_strength",
                            confirmed=(ret > avg_ret), source="relative")
            except Exception:
                pass
        # Reset baseline every 500 calls (~every 5 min at 100-trade intervals)
        if sum(1 for _ in returns) > 0:
            _rs_baseline.update(current_prices)

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
            trade_size = event.data.get("size", 0)
            prices[sym] = price
            prev_prices[sym] = price

            # (#2) Faster belief response: 3x more observations per trade
            # Volume-weighted (#7): large trades get proportionally more observations
            size_mult = min(5.0, max(1.0, trade_size * 100)) if trade_size > 0 else 1.0
            n_fast = min(30, max(3, int(move * 60000 * size_mult)))
            n_slow = max(1, n_fast // 3)

            for _ in range(n_fast):
                try:
                    engine.observe(f"{ext_id}:price_trend_fast", confirmed=price_up, source="coinbase")
                    obs_count += 1
                except Exception:
                    break

            for _ in range(n_slow):
                try:
                    engine.observe(f"{ext_id}:price_trend_slow", confirmed=price_up, source="coinbase")
                    obs_count += 1
                except Exception:
                    break

            # Exhaustion — large moves in either direction
            try:
                if move > 0.0003:
                    engine.observe(f"{ext_id}:exhaustion", confirmed=True, source="coinbase")
                elif move < 0.00005:
                    engine.observe(f"{ext_id}:exhaustion", confirmed=False, source="coinbase")
                obs_count += 1
            except Exception:
                pass

            # (#3) Graph propagation — signal flows to related coins
            try:
                if hasattr(engine, "propagate") and move > 0.0002:
                    engine.propagate(external_id=ext_id, confidence=0.3 + move * 50, decay=0.4)
            except Exception:
                pass

            # (#4) Relative strength — compare coins to each other
            if trade_count % 100 == 0 and len(prices) >= 2:
                _update_relative_strength(engine, prices, SYMBOLS_CLEAN)

            trade_count += 1

            # Signals on interval
            now = time.time()
            if now - last_signal > SIGNAL_INTERVAL:
                last_signal = now
                do_signals()

    def do_signals():
        nonlocal signal_count
        signals = gen_signals()
        elapsed = time.time() - start

        # Evaluate past signals (5-min forward)
        correct = 0
        evaluated = 0
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
                evaluated += 1
                if entry["ok"]:
                    correct += 1

        total_eval = sum(1 for s in signal_log if s.get("eval"))
        total_ok = sum(1 for s in signal_log if s.get("ok"))
        acc = total_ok / total_eval if total_eval > 0 else 0

        # Print
        print(f"\n[{elapsed/60:.1f}m] trades={trade_count:,} obs={obs_count:,} signals={signal_count} eval={total_eval} acc={acc:.1%}")
        for sym in SYMBOLS_CLEAN:
            ext_id = f"instrument:{sym}"
            try:
                fast = engine.belief(f"{ext_id}:price_trend_fast")
                slow = engine.belief(f"{ext_id}:price_trend_slow")
                exh = engine.belief(f"{ext_id}:exhaustion")
                px = prices.get(sym, 0)
                print(f"  {sym:>8}: ${px:>10,.2f}  fast={fast:.3f}  slow={slow:.3f}  exh={exh:.3f}")
            except Exception:
                pass

        for sig in signals:
            sym = sig.get("symbol", "")
            d = sig.get("direction", "")
            e = sig.get("edge", 0)
            c = sig.get("confidence", 0)
            px = prices.get(sym, 0)
            arrow = "▲" if d == "long" else "▼" if d == "short" else "—"
            print(f"  {arrow} {sym} {d} edge={e:.3f} conf={c:.3f}")

            signal_log.append({"t": time.time(), "sym": sym, "dir": d, "edge": e, "px": px})
            signal_count += 1
            log("signal", {"symbol": sym, "direction": d, "edge": e, "confidence": c, "price": px})

        if total_eval > 0:
            print(f"  Accuracy: {total_ok}/{total_eval} ({acc:.1%}) [5-min forward]")

        # Log beliefs
        beliefs = {}
        for sym in SYMBOLS_CLEAN:
            ext_id = f"instrument:{sym}"
            b = {}
            for attr in ["price_trend_fast", "price_trend_slow", "exhaustion"]:
                try:
                    b[attr] = round(engine.belief(f"{ext_id}:{attr}"), 4)
                except Exception:
                    b[attr] = 0.5
            b["price"] = prices.get(sym, 0)
            beliefs[sym] = b
        log("beliefs", {"beliefs": beliefs, "accuracy": acc, "evaluated": total_eval, "trades": trade_count, "obs": obs_count})

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
