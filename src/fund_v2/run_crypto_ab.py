"""A/B test on LIVE crypto — run old decision engine vs E_adapt_all side by side.

Same Coinbase feed, same beliefs, two strategies evaluated simultaneously.

Usage:
    SILICONDB_LIBRARY_PATH=lib/silicondb/.build/release \
    PYTHONPATH=src:lib/silicondb/python \
    python3 -m fund_v2.run_crypto_ab
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
from typing import Dict, List, Tuple

# Crypto pairs
_MAJORS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"]
_HIGH = ["FET-USD", "AVAX-USD", "LINK-USD", "PEPE-USD", "DOGE-USD", "ADA-USD"]
_MED = ["SUI-USD", "DOT-USD", "INJ-USD", "APT-USD"]
CRYPTO_PAIRS = _MAJORS + _HIGH + _MED
SYMBOLS = [c.replace("-", "") for c in CRYPTO_PAIRS]
SIGNAL_INTERVAL = 60


# ── Strategy A: E_adapt_all (the A/B test winner) ───────────────────────────

def strategy_adapt_all(fast, slow, vol, market_trend, win_rate, n_trades):
    """Prediction + graph + adaptive."""
    if win_rate < 0.35 and n_trades >= 10:
        return "neutral", 0.0
    scale = 1.3 if win_rate > 0.55 else (0.2 if win_rate < 0.45 and n_trades >= 10 else 1.0)

    velocity = fast - slow
    predicted = fast + velocity * 3
    if predicted < 0.25 and vol > 0.02:
        return "sell", min(0.15, (0.5 - predicted) * 0.3 + vol) * scale
    if market_trend < 0.40 and (fast - market_trend) > 0.10:
        return "sell", min(0.10, (fast - market_trend) * 0.3) * scale
    if market_trend > 0.60 and (fast - market_trend) < -0.10:
        return "buy", min(0.10, abs(fast - market_trend) * 0.3) * scale
    if vol > 0.02 and fast > slow + 0.05 and slow < 0.45:
        return "buy", min(0.08, (fast - slow) * 0.5) * scale

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


# ── Strategy B: Simple momentum (baseline) ──────────────────────────────────

def strategy_simple(fast, slow, vol, market_trend, win_rate, n_trades):
    """Just momentum, no filters."""
    avg = fast * 0.6 + slow * 0.4
    if avg > 0.55:
        return "buy", min(0.10, (avg - 0.5) * 0.5)
    elif avg < 0.45:
        return "sell", min(0.10, (0.5 - avg) * 0.5)
    return "neutral", 0.0


def run():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    from pathlib import Path
    env_path = Path(__file__).resolve().parents[2] / "web" / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    duration = int(os.environ.get("DURATION_MINUTES", "60")) * 60

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  A/B LIVE TEST — Same feed, two strategies                   ║
║  A: E_adapt_all (prediction + graph + adaptive)              ║
║  B: Simple momentum (baseline)                               ║
╠══════════════════════════════════════════════════════════════╣
║  Pairs:    {len(CRYPTO_PAIRS)} crypto on Coinbase{' ' * 33}║
║  Duration: {duration // 60} minutes{' ' * 44}║
╚══════════════════════════════════════════════════════════════╝
""")

    # SiliconDB
    import tempfile
    db_dir = os.environ.get("V2_CRYPTO_DB_PATH", os.path.expanduser("~/.fund/silicondb_v2_crypto_ab"))
    try:
        from silicondb.engine.native import SiliconDBNativeEngine
        engine = SiliconDBNativeEngine(db_dir, dimension=384, tenant_id=3)
        print(f"Engine: native at {db_dir}")
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

    # Seed
    from silicondb.sources.models import SourceRecord
    from silicondb.pipeline.models import PipelineContext
    for sym in SYMBOLS:
        r = SourceRecord(source_name="init", collection="seed", identity=sym,
            data={"symbol": sym, "price": 0, "trade_count": 0},
            timestamp=datetime.now(timezone.utc), idempotency_key=f"seed:{sym}", tenant_id=0)
        try:
            app.get_pipeline().process(r, PipelineContext(engine=app.engine, entity_cls=Instrument, tenant_id=0))
        except Exception:
            pass

    # Coinbase
    from fund_v2.sources.coinbase_ws import CoinbaseWebSocket
    event_queue = queue.Queue(maxsize=100000)
    ws = CoinbaseWebSocket(symbols=CRYPTO_PAIRS)
    ws.start(event_queue)

    # Log
    log_dir = Path("logs/v2_crypto_ab")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"ab_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.jsonl"
    print(f"Log: {log_path}")

    def log(data):
        with open(log_path, "a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **data}) + "\n")

    # State
    stop = threading.Event()
    obs = 0
    trades = 0
    last_signal = time.time()
    start = time.time()
    prices: Dict[str, float] = {}

    # Per-strategy tracking
    strats = {
        "A_adapt_all": {"fn": strategy_adapt_all, "signals": [], "wins": []},
        "B_simple": {"fn": strategy_simple, "signals": [], "wins": []},
    }

    def consume():
        nonlocal obs, trades, last_signal

        while not stop.is_set():
            try:
                event = event_queue.get(timeout=0.5)
            except queue.Empty:
                if time.time() - last_signal > SIGNAL_INTERVAL:
                    last_signal = time.time()
                    do_signals()
                continue

            if event.kind != "trade":
                continue

            sym = event.symbol
            ext_id = f"instrument:{sym}"
            price = event.data.get("price", 0)
            prev = prices.get(sym)

            if not prev or prev <= 0:
                prices[sym] = price
                trades += 1
                continue

            price_up = price > prev
            move = abs(price - prev) / prev if prev > 0 else 0
            prices[sym] = price

            n = min(10, max(1, int(move * 20000)))
            for _ in range(n):
                try:
                    engine.observe(f"{ext_id}:price_trend_fast", confirmed=price_up, source="cb")
                    obs += 1
                except Exception:
                    break
            for _ in range(max(1, n // 4)):
                try:
                    engine.observe(f"{ext_id}:price_trend_slow", confirmed=price_up, source="cb")
                    obs += 1
                except Exception:
                    break

            trades += 1
            if time.time() - last_signal > SIGNAL_INTERVAL:
                last_signal = time.time()
                do_signals()

    def do_signals():
        elapsed = time.time() - start

        # Get BTC as market proxy
        btc_fast = 0.5
        try:
            btc_fast = engine.belief("instrument:BTCUSD:price_trend_fast")
        except Exception:
            pass

        # Evaluate past signals for both strategies
        for name, s in strats.items():
            for entry in s["signals"]:
                if entry.get("eval"):
                    continue
                if time.time() - entry["t"] < 300:
                    continue
                sym = entry["sym"]
                if sym in prices and entry["px"] > 0:
                    fwd = (prices[sym] - entry["px"]) / entry["px"]
                    entry["ok"] = (entry["dir"] == "buy" and fwd > 0) or (entry["dir"] == "sell" and fwd < 0)
                    entry["eval"] = True
                    s["wins"].append(1.0 if entry["ok"] else 0.0)

        # Run both strategies on each symbol
        print(f"\n[{elapsed/60:.1f}m] trades={trades:,} obs={obs:,} BTC_trend={btc_fast:.3f}")

        for name, s in strats.items():
            total_eval = sum(1 for sig in s["signals"] if sig.get("eval"))
            total_ok = sum(1 for sig in s["signals"] if sig.get("ok"))
            acc = total_ok / total_eval if total_eval > 0 else 0
            win_rate = sum(s["wins"][-20:]) / len(s["wins"][-20:]) if len(s["wins"]) >= 5 else 0.5

            new_signals = 0
            for sym in SYMBOLS:
                ext_id = f"instrument:{sym}"
                try:
                    fast = engine.belief(f"{ext_id}:price_trend_fast")
                    slow = engine.belief(f"{ext_id}:price_trend_slow")
                except Exception:
                    continue

                vol = abs(fast - slow) * 2
                direction, size = s["fn"](fast, slow, vol, btc_fast, win_rate, len(s["wins"]))

                if direction != "neutral" and size > 0:
                    px = prices.get(sym, 0)
                    s["signals"].append({"t": time.time(), "sym": sym, "dir": direction, "px": px})
                    new_signals += 1
                    log({"type": "signal", "strategy": name, "symbol": sym,
                         "direction": direction, "size": round(size, 4), "price": px,
                         "fast": round(fast, 4), "slow": round(slow, 4)})

            print(f"  {name}: acc={acc:.1%} ({total_ok}/{total_eval}) new={new_signals} win_rate={win_rate:.0%}")

    # Start
    consumer = threading.Thread(target=consume, daemon=True)
    consumer.start()

    def shutdown(signum, frame):
        print(f"\n\n{'='*60}")
        print(f"  A/B LIVE RESULTS — {(time.time()-start)/60:.0f} minutes")
        print(f"{'='*60}")
        for name, s in strats.items():
            total_eval = sum(1 for sig in s["signals"] if sig.get("eval"))
            total_ok = sum(1 for sig in s["signals"] if sig.get("ok"))
            acc = total_ok / total_eval if total_eval > 0 else 0
            print(f"  {name}: {acc:.1%} ({total_ok}/{total_eval}) signals={len(s['signals'])}")
        print(f"  Log: {log_path}")
        stop.set()
        ws.stop()
        try:
            engine.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"\nRunning {duration//60} min. Ctrl+C to stop.\n")
    stop.wait(duration)
    if not stop.is_set():
        shutdown(None, None)


if __name__ == "__main__":
    run()
