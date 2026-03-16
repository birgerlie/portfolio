# Full Market Streaming + Signal Detection — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream all S&P 500 + NASDAQ 100 symbols (~610), observe every trade in SiliconDB, aggregate quotes, and detect high-conviction signals via belief graph properties.

**Architecture:** Expand StreamConfig to accept full ticker list from ontology. Add QuoteAggregator to batch quote observations. New SignalTracker queries SiliconDB entropy/propagation/node_thermo to rank candidate symbols. Signals synced to Supabase.

**Tech Stack:** Python 3.14, alpaca-py StockDataStream, SiliconDB native client, Supabase, Prisma, pytest.

**Spec:** `docs/superpowers/specs/2026-03-16-full-market-streaming-signals-design.md`

---

## File Map

### New Files
| File | Responsibility |
|---|---|
| `src/fund/signal_tracker.py` | Query SiliconDB belief properties, rank signals, track history |
| `src/fund/quote_aggregator.py` | Aggregate quotes per symbol per 1s window |
| `tests/unit/fund/test_signal_tracker.py` | SignalTracker tests |
| `tests/unit/fund/test_quote_aggregator.py` | QuoteAggregator tests |

### Modified Files
| File | Changes |
|---|---|
| `src/fund/broker_types.py` | Add tracked_symbols to StreamConfig |
| `src/fund/stream_service.py` | Subscribe to full ticker list |
| `src/fund/observation_recorder.py` | Integrate QuoteAggregator |
| `src/fund/live_engine.py` | Queue 10k, integrate SignalTracker, log signals |
| `src/fund/run_server.py` | Load tickers from ontology, pass to StreamConfig |
| `src/fund/supabase_sync.py` | Add push_signals() |
| `web/prisma/schema.prisma` | Add Signal model |

---

## Chunk 1: QuoteAggregator

### Task 1: QuoteAggregator — Windowed Quote Batching

**Files:**
- Create: `src/fund/quote_aggregator.py`
- Create: `tests/unit/fund/test_quote_aggregator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_quote_aggregator.py
import time
import pytest
from fund.quote_aggregator import QuoteAggregator


class TestQuoteAggregator:
    def test_record_quote(self):
        agg = QuoteAggregator(window_seconds=1.0)
        agg.record("AAPL", bid=149.90, ask=150.10, timestamp=time.time())
        assert "AAPL" in agg.symbols()

    def test_flush_returns_aggregated_spread(self):
        agg = QuoteAggregator(window_seconds=1.0)
        ts = time.time()
        agg.record("AAPL", bid=149.90, ask=150.10, timestamp=ts)
        agg.record("AAPL", bid=149.80, ask=150.20, timestamp=ts + 0.5)
        result = agg.flush()
        assert "AAPL" in result
        assert result["AAPL"]["latest_bid"] == 149.80
        assert result["AAPL"]["latest_ask"] == 150.20
        # Mean spread: (0.20 + 0.40) / 2 = 0.30
        assert abs(result["AAPL"]["mean_spread"] - 0.30) < 0.01

    def test_flush_clears_window(self):
        agg = QuoteAggregator(window_seconds=1.0)
        agg.record("AAPL", bid=149.90, ask=150.10, timestamp=time.time())
        agg.flush()
        result = agg.flush()
        assert result == {}

    def test_multiple_symbols(self):
        agg = QuoteAggregator(window_seconds=1.0)
        ts = time.time()
        agg.record("AAPL", bid=149.90, ask=150.10, timestamp=ts)
        agg.record("MSFT", bid=299.90, ask=300.10, timestamp=ts)
        result = agg.flush()
        assert "AAPL" in result
        assert "MSFT" in result

    def test_quote_count(self):
        agg = QuoteAggregator(window_seconds=1.0)
        ts = time.time()
        for i in range(10):
            agg.record("AAPL", bid=149.90, ask=150.10, timestamp=ts + i * 0.1)
        result = agg.flush()
        assert result["AAPL"]["quote_count"] == 10

    def test_thread_safety(self):
        import threading
        agg = QuoteAggregator(window_seconds=1.0)
        errors = []

        def writer():
            try:
                for i in range(100):
                    agg.record("AAPL", bid=150.0 + i * 0.01, ask=150.1 + i * 0.01, timestamp=time.time())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_quote_aggregator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement QuoteAggregator**

```python
# src/fund/quote_aggregator.py
"""Aggregates quotes per symbol per time window for batched observation."""

import threading
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class _QuoteWindow:
    latest_bid: float = 0.0
    latest_ask: float = 0.0
    spreads: List[float] = field(default_factory=list)
    quote_count: int = 0


class QuoteAggregator:
    """Collects quotes and aggregates per symbol per window."""

    def __init__(self, window_seconds: float = 1.0):
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._windows: Dict[str, _QuoteWindow] = {}

    def record(self, symbol: str, bid: float, ask: float, timestamp: float) -> None:
        with self._lock:
            w = self._windows.get(symbol)
            if w is None:
                w = _QuoteWindow()
                self._windows[symbol] = w
            w.latest_bid = bid
            w.latest_ask = ask
            spread = ask - bid
            w.spreads.append(spread)
            w.quote_count += 1

    def symbols(self) -> list:
        with self._lock:
            return list(self._windows.keys())

    def flush(self) -> Dict[str, dict]:
        with self._lock:
            result = {}
            for symbol, w in self._windows.items():
                if w.quote_count == 0:
                    continue
                mean_spread = sum(w.spreads) / len(w.spreads) if w.spreads else 0.0
                result[symbol] = {
                    "latest_bid": w.latest_bid,
                    "latest_ask": w.latest_ask,
                    "mean_spread": mean_spread,
                    "min_spread": min(w.spreads) if w.spreads else 0.0,
                    "max_spread": max(w.spreads) if w.spreads else 0.0,
                    "quote_count": w.quote_count,
                }
            self._windows.clear()
            return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_quote_aggregator.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/quote_aggregator.py tests/unit/fund/test_quote_aggregator.py
git commit -m "feat: add QuoteAggregator for windowed quote batching"
```

---

## Chunk 2: SignalTracker

### Task 2: SignalTracker — Belief Graph Signal Detection

**Files:**
- Create: `src/fund/signal_tracker.py`
- Create: `tests/unit/fund/test_signal_tracker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_signal_tracker.py
import time
from unittest.mock import MagicMock
import pytest
from fund.signal_tracker import SignalTracker, Signal


class TestSignalTracker:
    def _make_tracker(self, silicondb=None, portfolio=None):
        client = silicondb or MagicMock()
        return SignalTracker(
            silicondb_client=client,
            portfolio_symbols=portfolio or ["AAPL", "MSFT"],
        ), client

    def test_init(self):
        tracker, _ = self._make_tracker()
        assert tracker.get_signals() == []

    def test_update_detects_low_entropy_signal(self):
        tracker, client = self._make_tracker()
        # Mock: AMD has low entropy (high conviction)
        client.get_uncertain_beliefs.return_value = [
            {"external_id": "AAPL:return", "entropy": 0.8},  # portfolio symbol, skip
        ]
        client.node_thermo.return_value = {"temperature": 0.6}

        signals = tracker.update(["AAPL", "MSFT", "AMD", "NVDA"])
        # AMD and NVDA are not in portfolio and not in uncertain list = low entropy
        signal_symbols = [s.symbol for s in tracker.get_signals()]
        assert "AMD" in signal_symbols or "NVDA" in signal_symbols

    def test_portfolio_symbols_excluded(self):
        tracker, client = self._make_tracker(portfolio=["AAPL", "MSFT"])
        client.get_uncertain_beliefs.return_value = []
        client.node_thermo.return_value = {"temperature": 0.5}
        tracker.update(["AAPL", "MSFT", "AMD"])
        signal_symbols = [s.symbol for s in tracker.get_signals()]
        assert "AAPL" not in signal_symbols
        assert "MSFT" not in signal_symbols

    def test_signal_strength_ranking(self):
        tracker, client = self._make_tracker()
        client.get_uncertain_beliefs.return_value = []
        # AMD hotter than INTC
        def mock_node_thermo(ext_id):
            if "AMD" in ext_id:
                return {"temperature": 0.9}
            return {"temperature": 0.2}
        client.node_thermo.side_effect = mock_node_thermo
        tracker.update(["AAPL", "MSFT", "AMD", "INTC"])
        signals = tracker.get_signals()
        if len(signals) >= 2:
            assert signals[0].signal_strength >= signals[1].signal_strength

    def test_signal_decay(self):
        tracker, client = self._make_tracker()
        # Cycle 1: AMD has signal
        client.get_uncertain_beliefs.return_value = []
        client.node_thermo.return_value = {"temperature": 0.7}
        tracker.update(["AAPL", "MSFT", "AMD"])
        assert any(s.symbol == "AMD" for s in tracker.get_signals())

        # Cycle 2: AMD now uncertain (high entropy)
        client.get_uncertain_beliefs.return_value = [
            {"external_id": "AMD:return", "entropy": 0.9},
        ]
        tracker.update(["AAPL", "MSFT", "AMD"])
        decayed = tracker.get_decayed()
        assert "AMD" in decayed

    def test_signal_history(self):
        tracker, client = self._make_tracker()
        client.get_uncertain_beliefs.return_value = []
        client.node_thermo.return_value = {"temperature": 0.5}
        tracker.update(["AAPL", "MSFT", "AMD"])
        tracker.update(["AAPL", "MSFT", "AMD"])
        history = tracker.get_signal_history("AMD")
        assert len(history) >= 1

    def test_silicondb_error_handled(self):
        tracker, client = self._make_tracker()
        client.get_uncertain_beliefs.side_effect = Exception("connection failed")
        # Should not raise
        tracker.update(["AAPL", "MSFT", "AMD"])

    def test_signal_dataclass(self):
        s = Signal(symbol="AMD", signal_strength=0.82, entropy=0.15,
                   node_temperature=0.7, belief_type="high_growth",
                   conviction=0.85, first_seen=time.time(), last_seen=time.time(),
                   status="active")
        assert s.symbol == "AMD"
        assert s.status == "active"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_signal_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SignalTracker**

```python
# src/fund/signal_tracker.py
"""Detects high-conviction signals from SiliconDB belief graph properties."""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    symbol: str
    signal_strength: float
    entropy: float
    node_temperature: float
    belief_type: str = "unknown"
    conviction: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0
    status: str = "active"  # active / decayed


class SignalTracker:
    """Queries SiliconDB belief properties to detect and rank signals."""

    def __init__(self, silicondb_client, portfolio_symbols: List[str]):
        self._silicondb = silicondb_client
        self._portfolio = set(portfolio_symbols)
        self._signals: Dict[str, Signal] = {}
        self._decayed: List[str] = []
        self._history: Dict[str, List[dict]] = {}

    def update(self, all_symbols: List[str]) -> List[Signal]:
        """Query SiliconDB and update signal states. Returns new signals."""
        self._decayed.clear()
        new_signals = []

        try:
            # Get uncertain beliefs (high entropy)
            uncertain = set()
            try:
                uncertain_beliefs = self._silicondb.get_uncertain_beliefs(min_entropy=0.5, k=200)
                if uncertain_beliefs:
                    for b in uncertain_beliefs:
                        ext_id = b.get("external_id", "") if isinstance(b, dict) else str(b)
                        symbol = ext_id.split(":")[0] if ":" in ext_id else ext_id
                        uncertain.add(symbol)
            except Exception:
                pass

            # Evaluate each non-portfolio symbol
            now = time.time()
            for symbol in all_symbols:
                if symbol in self._portfolio:
                    continue
                if "/" in symbol:  # skip crypto for now
                    continue

                # Entropy: low = signal, high = noise
                is_uncertain = symbol in uncertain
                entropy = 0.8 if is_uncertain else 0.2

                # Node thermo
                node_temp = 0.0
                try:
                    thermo = self._silicondb.node_thermo(f"{symbol}:return")
                    if thermo:
                        node_temp = thermo.get("temperature", 0.0) if isinstance(thermo, dict) else getattr(thermo, "temperature", 0.0)
                except Exception:
                    pass

                # Signal strength
                strength = (1.0 - entropy) * max(node_temp, 0.01)

                if is_uncertain:
                    # Symbol is uncertain — if it was a signal, it decayed
                    if symbol in self._signals:
                        self._signals[symbol].status = "decayed"
                        self._decayed.append(symbol)
                        del self._signals[symbol]
                    continue

                if strength > 0.1:  # minimum threshold to avoid noise
                    if symbol in self._signals:
                        sig = self._signals[symbol]
                        sig.signal_strength = strength
                        sig.entropy = entropy
                        sig.node_temperature = node_temp
                        sig.last_seen = now
                    else:
                        sig = Signal(
                            symbol=symbol,
                            signal_strength=strength,
                            entropy=entropy,
                            node_temperature=node_temp,
                            first_seen=now,
                            last_seen=now,
                        )
                        self._signals[symbol] = sig
                        new_signals.append(sig)

                    # Track history
                    self._history.setdefault(symbol, []).append({
                        "time": now,
                        "strength": strength,
                        "entropy": entropy,
                        "temperature": node_temp,
                    })

        except Exception as e:
            logger.error("SignalTracker update failed: %s", e)

        return new_signals

    def get_signals(self) -> List[Signal]:
        """Ranked list of active signals by strength."""
        active = [s for s in self._signals.values() if s.status == "active"]
        return sorted(active, key=lambda s: s.signal_strength, reverse=True)

    def get_decayed(self) -> List[str]:
        """Symbols that decayed since last update."""
        return list(self._decayed)

    def get_signal_history(self, symbol: str) -> List[dict]:
        """Conviction trajectory for a symbol."""
        return self._history.get(symbol, [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_signal_tracker.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/signal_tracker.py tests/unit/fund/test_signal_tracker.py
git commit -m "feat: add SignalTracker with belief graph signal detection and ranking"
```

---

## Chunk 3: Expand StreamConfig + Streaming

### Task 3: Update StreamConfig for Full Ticker List

**Files:**
- Modify: `src/fund/broker_types.py`

- [ ] **Step 1: Add tracked_symbols to StreamConfig**

Add a new field and property:

```python
    tracked_symbols: List[str] = field(default_factory=list)  # full S&P/NASDAQ list

    @property
    def all_stream_symbols(self) -> list:
        """All symbols to subscribe to (portfolio + reference + macro + tracked)."""
        return sorted(set(
            self.portfolio_symbols + self.reference_symbols +
            self.macro_proxies + self.tracked_symbols
        ))
```

Update `all_symbols` to remain as-is (portfolio + reference + macro only) for backward compatibility. `all_stream_symbols` is the new property used for subscription.

- [ ] **Step 2: Commit**

```bash
git add src/fund/broker_types.py
git commit -m "feat: add tracked_symbols and all_stream_symbols to StreamConfig"
```

### Task 4: Update StreamService for Full Ticker Subscription

**Files:**
- Modify: `src/fund/stream_service.py`

- [ ] **Step 1: Update _stream_main to use all_stream_symbols**

Change the symbols variable in `_stream_main()` from `self.all_stream_symbols` to `self._stream_config.all_stream_symbols`. Also update `all_stream_symbols` property to include tracked.

- [ ] **Step 2: Commit**

```bash
git add src/fund/stream_service.py
git commit -m "feat: subscribe to full tracked ticker list in StreamService"
```

### Task 5: Update run_server.py to Load Full Ticker List

**Files:**
- Modify: `src/fund/run_server.py`

- [ ] **Step 1: Load tickers from ontology and pass to StreamConfig**

After the ontology is loaded, extract the ticker list and pass to StreamConfig:

```python
    # After ontology loading...
    from fund.ontology import fetch_index_compositions
    sp500, nasdaq100 = fetch_index_compositions()
    all_tracked = sorted(set(sp500 + nasdaq100))
    print(f"  Tracked:         {len(all_tracked)} symbols (S&P 500 + NASDAQ 100)")
```

Then in StreamConfig construction, add `tracked_symbols=all_tracked`.

- [ ] **Step 2: Increase queue size to 10,000**

Change `queue.Queue(maxsize=1000)` to `queue.Queue(maxsize=10000)`.

- [ ] **Step 3: Commit**

```bash
git add src/fund/run_server.py
git commit -m "feat: stream all S&P 500 + NASDAQ 100 symbols, increase queue to 10k"
```

---

## Chunk 4: Wire QuoteAggregator into ObservationRecorder

### Task 6: Integrate QuoteAggregator

**Files:**
- Modify: `src/fund/observation_recorder.py`
- Modify: `src/fund/live_engine.py`

- [ ] **Step 1: Add QuoteAggregator to ObservationRecorder**

Add a `QuoteAggregator` instance to `ObservationRecorder`. On `flush()`, also flush the aggregator and emit `SYMBOL:spread` observations with mean_spread as value.

```python
from fund.quote_aggregator import QuoteAggregator

class ObservationRecorder:
    def __init__(self, price_cache, silicondb_client, batch_interval=1.0):
        ...
        self._quote_agg = QuoteAggregator(window_seconds=batch_interval)

    def record_quote(self, symbol: str, bid: float, ask: float, timestamp: float):
        self._quote_agg.record(symbol, bid, ask, timestamp)

    def flush(self):
        # ... existing trade observation flush ...
        # Then flush aggregated quotes
        quote_data = self._quote_agg.flush()
        if quote_data:
            quote_obs = []
            for symbol, data in quote_data.items():
                quote_obs.append({
                    "external_id": f"{symbol}:spread",
                    "confirmed": True,
                    "source": "alpaca_stream",
                    "metadata": {"value": data["mean_spread"], "symbol": symbol},
                })
            if quote_obs:
                try:
                    self._silicondb.record_observation_batch(quote_obs)
                except Exception as exc:
                    logger.warning("SiliconDB quote batch error: %s", exc)
```

- [ ] **Step 2: Update live_engine.py to route quotes to recorder**

In `_consume_events`, change the quote handler to call `self._recorder.record_quote()`:

```python
            elif event.kind == "quote":
                self._recorder.record_quote(
                    event.symbol,
                    event.data.get("bid", 0),
                    event.data.get("ask", 0),
                    event.timestamp,
                )
```

Remove the old throttled quote logging — the aggregator handles batching now.

- [ ] **Step 3: Commit**

```bash
git add src/fund/observation_recorder.py src/fund/live_engine.py
git commit -m "feat: integrate QuoteAggregator for batched spread observations"
```

---

## Chunk 5: Wire SignalTracker + Supabase + Schema

### Task 7: Add Signal Model to Prisma Schema

**Files:**
- Modify: `web/prisma/schema.prisma`

- [ ] **Step 1: Add Signal model**

```prisma
model Signal {
  id                String   @id @default(cuid())
  symbol            String
  signalStrength    Float    @map("signal_strength")
  entropy           Float
  nodeTemperature   Float    @map("node_temperature")
  beliefType        String   @map("belief_type") @default("unknown")
  conviction        Float    @default(0)
  firstSeen         DateTime @map("first_seen") @default(now())
  lastSeen          DateTime @map("last_seen") @default(now())
  status            String   @default("active")

  @@unique([symbol, status])
  @@map("signals")
}
```

- [ ] **Step 2: Commit**

```bash
git add web/prisma/schema.prisma
git commit -m "feat: add Signal model to Prisma schema"
```

### Task 8: Add push_signals to SupabaseSync

**Files:**
- Modify: `src/fund/supabase_sync.py`

- [ ] **Step 1: Add push_signals method**

```python
    def push_signals(self, signals: list) -> None:
        """Upsert active signals to Supabase."""
        try:
            for sig in signals:
                self._client.table("signals").upsert({
                    "symbol": sig["symbol"],
                    "signal_strength": sig["signal_strength"],
                    "entropy": sig["entropy"],
                    "node_temperature": sig["node_temperature"],
                    "belief_type": sig.get("belief_type", "unknown"),
                    "conviction": sig.get("conviction", 0),
                    "first_seen": sig.get("first_seen"),
                    "last_seen": sig.get("last_seen"),
                    "status": sig.get("status", "active"),
                }, on_conflict="symbol,status").execute()
        except Exception as e:
            logger.error("Failed to push signals: %s", e)
```

- [ ] **Step 2: Commit**

```bash
git add src/fund/supabase_sync.py
git commit -m "feat: add push_signals to SupabaseSync"
```

### Task 9: Wire SignalTracker into LiveEngine

**Files:**
- Modify: `src/fund/live_engine.py`
- Modify: `src/fund/run_server.py`

- [ ] **Step 1: Add SignalTracker to LiveEngine**

Add `signal_tracker` parameter to `__init__`. In `_run_analysis_cycle()`, after the AutonomousController runs, call signal tracker:

```python
    # After controller analysis...
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
```

Add new color codes:
```python
    "signal": "\033[92m",    # bright green
    "decay": "\033[90m",     # gray
```

- [ ] **Step 2: Wire SignalTracker in run_server.py**

```python
    from fund.signal_tracker import SignalTracker
    signal_tracker = SignalTracker(
        silicondb_client=silicondb_client,
        portfolio_symbols=portfolio_syms,
    )
    print(f"  Signals:         SignalTracker (watching {len(all_tracked)} symbols)")
```

Pass to LiveEngine constructor.

- [ ] **Step 3: Commit**

```bash
git add src/fund/live_engine.py src/fund/run_server.py
git commit -m "feat: wire SignalTracker into engine, log signals and decay, sync to Supabase"
```

---

## Chunk 6: Integration Test

### Task 10: Integration Test — Signal Detection Pipeline

**Files:**
- Create: `tests/integration/fund/test_signal_pipeline.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/fund/test_signal_pipeline.py
"""Integration: observations → SiliconDB beliefs → signal detection."""

import time
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from fund.price_cache import PriceCache
from fund.observation_recorder import ObservationRecorder
from fund.signal_tracker import SignalTracker


class TestSignalPipeline:
    def test_observation_to_signal_flow(self):
        """Observations build beliefs, SignalTracker detects signals."""
        silicondb = MagicMock()
        silicondb.get_uncertain_beliefs.return_value = []
        silicondb.node_thermo.return_value = {"temperature": 0.7}

        price_cache = PriceCache()
        recorder = ObservationRecorder(price_cache, silicondb)
        tracker = SignalTracker(silicondb, portfolio_symbols=["AAPL"])

        # Simulate trades
        ts = time.time()
        price_cache.update_trade("AMD", Decimal("150"), Decimal("1000"), ts)
        recorder.record_symbol("AMD")
        recorder.flush()
        assert silicondb.record_observation_batch.called

        # Run signal detection
        new_signals = tracker.update(["AAPL", "AMD"])
        assert any(s.symbol == "AMD" for s in new_signals)

    def test_quote_aggregation_flow(self):
        """Quotes aggregate and flush as single spread observation."""
        silicondb = MagicMock()
        price_cache = PriceCache()
        recorder = ObservationRecorder(price_cache, silicondb)

        ts = time.time()
        for i in range(10):
            recorder.record_quote("AAPL", 149.9 + i * 0.01, 150.1 + i * 0.01, ts + i * 0.1)
        recorder.flush()
        # Should have called record_observation_batch for quote spread
        calls = silicondb.record_observation_batch.call_args_list
        all_obs = []
        for call in calls:
            all_obs.extend(call[0][0])
        spread_obs = [o for o in all_obs if "spread" in o["external_id"]]
        assert len(spread_obs) > 0
```

- [ ] **Step 2: Run integration test**

Run: `PYTHONPATH=src python3 -m pytest tests/integration/fund/test_signal_pipeline.py -v`
Expected: All 2 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/fund/test_signal_pipeline.py
git commit -m "test: add signal detection pipeline integration test"
```
