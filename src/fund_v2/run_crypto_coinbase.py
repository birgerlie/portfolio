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

# Majors (500+ trades/min)
_MAJORS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"]
# High volume (50+ trades/min)
_HIGH = ["FET-USD", "AVAX-USD", "LINK-USD", "PEPE-USD", "DOGE-USD", "ADA-USD"]
# Medium (10-50 trades/min)
_MED = ["SUI-USD", "DOT-USD", "INJ-USD", "APT-USD", "CRV-USD"]
# Lower (4-10 trades/min)
_LOW = ["BONK-USD", "ARB-USD", "SHIB-USD", "AAVE-USD", "NEAR-USD",
        "OP-USD", "UNI-USD", "ATOM-USD", "SEI-USD", "FIL-USD",
        "TIA-USD", "LDO-USD", "GRT-USD"]

CRYPTO_PAIRS = _MAJORS + _HIGH + _MED + _LOW
SYMBOLS_CLEAN = [c.replace("-", "") for c in CRYPTO_PAIRS]
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

    # Seed instruments — track doc_ids for per-node thermo
    from silicondb.sources.models import SourceRecord
    from silicondb.pipeline.models import PipelineContext
    _doc_ids: Dict[str, int] = {}
    for i, sym in enumerate(SYMBOLS_CLEAN):
        r = SourceRecord(source_name="init", collection="seed", identity=sym,
            data={"symbol": sym, "price": 0, "trade_count": 0},
            timestamp=datetime.now(timezone.utc), idempotency_key=f"seed:{sym}", tenant_id=0)
        try:
            app.get_pipeline().process(r, PipelineContext(engine=app.engine, entity_cls=Instrument, tenant_id=0))
            _doc_ids[sym] = i  # doc_ids are sequential from 0
        except Exception:
            pass

    # Crypto ontology — 28 symbols, 10 sectors, competition + BTC dominance
    _CRYPTO_ONTOLOGY = [
        # ── Sectors ──
        # Layer 1 (store of value / base layer)
        ("BTCUSD", "in_sector", "layer1", 1.0),
        ("ETHUSD", "in_sector", "layer1", 1.0),
        # Layer 1 alt (smart contract competitors)
        ("SOLUSD", "in_sector", "l1_alt", 1.0),
        ("AVAXUSD", "in_sector", "l1_alt", 1.0),
        ("ADAUSD", "in_sector", "l1_alt", 1.0),
        ("DOTUSD", "in_sector", "l1_alt", 1.0),
        ("NEARUSD", "in_sector", "l1_alt", 1.0),
        ("SUIUSD", "in_sector", "l1_alt", 1.0),
        ("APTUSD", "in_sector", "l1_alt", 1.0),
        ("SEIUSD", "in_sector", "l1_alt", 1.0),
        ("INJUSD", "in_sector", "l1_alt", 1.0),
        ("TIAUSD", "in_sector", "l1_alt", 1.0),
        # Layer 2 (scaling solutions)
        ("ARBUSD", "in_sector", "layer2", 1.0),
        ("OPUSD", "in_sector", "layer2", 1.0),
        ("MATICUSD", "in_sector", "layer2", 1.0),
        # DeFi
        ("AAVEUSD", "in_sector", "defi", 1.0),
        ("UNIUSD", "in_sector", "defi", 1.0),
        ("CRVUSD", "in_sector", "defi", 1.0),
        ("MKRUSD", "in_sector", "defi", 1.0),
        ("LDOUSD", "in_sector", "defi", 1.0),
        # Oracle / infra
        ("LINKUSD", "in_sector", "infra", 1.0),
        ("GRTUSD", "in_sector", "infra", 1.0),
        ("FILUSD", "in_sector", "infra", 1.0),
        # AI / compute
        ("FETUSD", "in_sector", "ai_compute", 1.0),
        ("RNDRUSD", "in_sector", "ai_compute", 1.0),
        # Meme
        ("DOGEUSD", "in_sector", "meme", 1.0),
        ("SHIBUSD", "in_sector", "meme", 1.0),
        ("PEPEUSD", "in_sector", "meme", 1.0),
        ("BONKUSD", "in_sector", "meme", 1.0),
        # Payments
        ("XRPUSD", "in_sector", "payments", 1.0),
        # Interop
        ("ATOMUSD", "in_sector", "interop", 1.0),

        # ── Competition ──
        # L1 alt competition (all compete for the same TVL)
        ("SOLUSD", "competes_with", "ETHUSD", 0.8),
        ("AVAXUSD", "competes_with", "SOLUSD", 0.7),
        ("SUIUSD", "competes_with", "SOLUSD", 0.6),
        ("APTUSD", "competes_with", "SUIUSD", 0.8),  # Move ecosystem
        ("SEIUSD", "competes_with", "SUIUSD", 0.5),
        ("NEARUSD", "competes_with", "SOLUSD", 0.5),
        ("ADAUSD", "competes_with", "ETHUSD", 0.4),
        ("INJUSD", "competes_with", "SOLUSD", 0.4),
        # L2 competition
        ("ARBUSD", "competes_with", "OPUSD", 0.9),
        ("MATICUSD", "competes_with", "ARBUSD", 0.7),
        # DeFi competition
        ("UNIUSD", "competes_with", "CRVUSD", 0.6),
        ("AAVEUSD", "competes_with", "MKRUSD", 0.4),
        # Meme competition (correlated, not competitive)
        ("DOGEUSD", "competes_with", "SHIBUSD", 0.8),
        ("PEPEUSD", "competes_with", "BONKUSD", 0.7),
        # AI competition
        ("FETUSD", "competes_with", "RNDRUSD", 0.7),

        # ── BTC dominance — everything follows BTC ──
        ("BTCUSD", "leads", "ETHUSD", 0.8),
        ("BTCUSD", "leads", "SOLUSD", 0.6),
        ("BTCUSD", "leads", "XRPUSD", 0.5),
        ("BTCUSD", "leads", "l1_alt", 0.5),
        ("BTCUSD", "leads", "defi", 0.4),
        ("BTCUSD", "leads", "meme", 0.6),
        ("BTCUSD", "leads", "ai_compute", 0.4),
        # ETH leads DeFi
        ("ETHUSD", "leads", "defi", 0.7),
        ("ETHUSD", "leads", "layer2", 0.8),
        # SOL leads its ecosystem
        ("SOLUSD", "leads", "BONKUSD", 0.5),
        ("SOLUSD", "leads", "JUPUSD", 0.6),

        # ── Sector types ──
        ("layer1", "is_a", "sector", 1.0),
        ("l1_alt", "is_a", "sector", 1.0),
        ("layer2", "is_a", "sector", 1.0),
        ("defi", "is_a", "sector", 1.0),
        ("infra", "is_a", "sector", 1.0),
        ("ai_compute", "is_a", "sector", 1.0),
        ("meme", "is_a", "sector", 1.0),
        ("payments", "is_a", "sector", 1.0),
        ("interop", "is_a", "sector", 1.0),
    ]
    # Add bidirectional competition
    extra = []
    for s, p, o, w in _CRYPTO_ONTOLOGY:
        if p == "competes_with":
            extra.append((o, "competes_with", s, w))
    _CRYPTO_ONTOLOGY.extend(extra)

    for s, p, o, w in _CRYPTO_ONTOLOGY:
        try:
            engine.add_triple(f"instrument:{s}" if s in SYMBOLS_CLEAN else s,
                              p,
                              f"instrument:{o}" if o in SYMBOLS_CLEAN else o,
                              weight=w)
        except Exception:
            pass
    print(f"Ontology: {len(_CRYPTO_ONTOLOGY)} triples (sectors + competition + BTC dominance)")

    # Initialize thermodynamic compute
    from fund_v2.decision_engine import _get_native
    native = _get_native(engine)
    if native and hasattr(native, 'init_thermo'):
        try:
            native.init_thermo(max_nodes=10000)
            print("Thermo: initialized (max_nodes=10000)")
        except Exception as e:
            print(f"Thermo: init failed ({e})")
    else:
        print("Thermo: not available on this engine")

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
    cost_per_symbol: Dict[str, float] = {s: 10.0 for s in SYMBOLS_CLEAN}  # default 10 bps for crypto
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

            # (#1) Faster reversal response: when direction flips from recent trend,
            # send extra observations to push belief back faster
            prev_up = prev_prices.get(sym + "_dir")
            direction_flipped = prev_up is not None and price_up != prev_up
            prev_prices[sym] = price
            prev_prices[sym + "_dir"] = price_up

            # Scale observations: more on direction flip, normal otherwise
            base_n = min(10, max(1, int(move * 20000)))
            n = base_n * 3 if direction_flipped else base_n
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

            # Handle quote events (best bid/ask from ticker channel)
            if event.kind == "quote":
                spread_pct = event.data.get("spread_pct", 0)
                tight = spread_pct < 0.001  # < 0.1% spread = tight
                try:
                    engine.observe(f"{ext_id}:spread_tight", confirmed=tight, source="coinbase")
                    obs_count += 1
                except Exception:
                    pass
                # Update cost estimate from live spread
                cost_per_sym = cost_per_symbol.get(sym, 5)
                live_cost = spread_pct * 10000  # convert to bps
                cost_per_symbol[sym] = cost_per_sym * 0.9 + live_cost * 0.1  # EMA
                continue

            # Signals on interval
            now = time.time()
            if now - last_signal > SIGNAL_INTERVAL:
                last_signal = now
                do_signals()

    def do_signals():
        nonlocal signal_count

        # Decision = ranked energy gaps (biggest goal gaps first)
        decision = generate_decision(
            engine=engine,
            symbols=SYMBOLS_CLEAN,
            doc_ids=_doc_ids,
            cost_per_symbol=cost_per_symbol,
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
                entry["ok"] = (
                    (entry["dir"] in ("buy", "add") and fwd > 0) or
                    (entry["dir"] in ("sell", "reduce", "exit") and fwd < 0)
                )
                entry["eval"] = True

        total_eval = sum(1 for s in signal_log if s.get("eval"))
        total_ok = sum(1 for s in signal_log if s.get("ok"))
        acc = total_ok / total_eval if total_eval > 0 else 0

        # Print
        print(f"\n[{elapsed/60:.1f}m] trades={trade_count:,} obs={obs_count:,} gaps={len(decision.gaps)} eval={total_eval} acc={acc:.1%}")
        print(format_decision(decision))

        # Prices
        for sym in SYMBOLS_CLEAN[:6]:  # top 6 by volume
            px = prices.get(sym, 0)
            if px > 0:
                ext_id = f"instrument:{sym}"
                try:
                    fast = engine.belief(f"{ext_id}:price_trend_fast")
                    slow = engine.belief(f"{ext_id}:price_trend_slow")
                    print(f"  {sym:>8}: ${px:>10,.2f}  fast={fast:.3f}  slow={slow:.3f}")
                except Exception:
                    pass

        # (#2) Log only deduped gaps (one per symbol, highest FE) for accuracy
        seen_symbols = set()
        for gap in decision.gaps:
            if gap.symbol in seen_symbols or gap.size <= 0:
                continue
            seen_symbols.add(gap.symbol)
            px = prices.get(gap.symbol, 0)
            signal_log.append({
                "t": time.time(), "sym": gap.symbol, "dir": gap.action,
                "fe": gap.free_energy, "px": px, "size": gap.size,
                "belief": gap.belief_name, "current": gap.current, "goal": gap.goal,
                "velocity": gap.velocity, "phase": gap.phase,
                "hedged_by": gap.hedged_by,
            })
            signal_count += 1
            log("gap", {
                "symbol": gap.symbol, "action": gap.action, "size": gap.size,
                "belief": gap.belief_name, "current": gap.current, "goal": gap.goal,
                "free_energy": gap.free_energy, "velocity": gap.velocity,
                "phase": gap.phase, "price": px,
                "hedged_by": gap.hedged_by,
                "dir_crowding": decision.directional_crowding,
                "crowd_scalar": decision.crowd_scalar,
                "system_temp": decision.system.temperature,
                "system_crit": decision.system.criticality,
            })

        if total_eval > 0:
            print(f"  Accuracy: {total_ok}/{total_eval} ({acc:.1%}) [5-min forward]")

        log("system", {
            "temperature": decision.system.temperature,
            "entropy": decision.system.entropy,
            "criticality": decision.system.criticality,
            "warmup": decision.warmup,
            "gaps": len(decision.gaps),
            "sized": len([g for g in decision.gaps if g.size > 0]),
            "dir_crowding": decision.directional_crowding,
            "crowd_scalar": decision.crowd_scalar,
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
