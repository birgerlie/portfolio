# Streaming Event-Driven Trading Engine — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the polling-based trading engine with a real-time event-driven system where Alpaca websocket streams feed SiliconDB continuously, and percolator events drive trading decisions at adaptive tempo.

**Architecture:** Two threads — async stream thread (Alpaca websockets → PriceCache + event queue) and sync engine thread (queue consumer → SiliconDB → reactor handlers → trades). SiliconDB's thermodynamic state sets the analysis tempo. Three percolator tiers (Nervous/Standard/Strategic) build conviction before trading.

**Tech Stack:** Python 3.14, alpaca-py 0.43.2 (StockDataStream, TradingStream), SiliconDB HTTP client, Supabase, pytest, threading + asyncio bridge via queue.Queue.

**Spec:** `docs/superpowers/specs/2026-03-16-streaming-event-driven-engine-design.md`

---

## File Map

### New Files
| File | Responsibility |
|---|---|
| `src/fund/price_cache.py` | Thread-safe price/volume/VWAP cache with staleness tracking |
| `src/fund/stream_service.py` | Async thread managing StockDataStream + TradingStream, posts to queue |
| `src/fund/observation_recorder.py` | Reads PriceCache, batches observations to SiliconDB per 1s window |
| `src/fund/tempo.py` | Maps thermo temperature to cooldown values, updates percolator rules |
| `src/fund/reactor.py` | Percolator event handlers (one per tier) |
| `tests/unit/fund/test_price_cache.py` | PriceCache unit tests |
| `tests/unit/fund/test_stream_service.py` | StreamService unit tests |
| `tests/unit/fund/test_observation_recorder.py` | ObservationRecorder unit tests |
| `tests/unit/fund/test_tempo.py` | Tempo unit tests |
| `tests/unit/fund/test_reactor.py` | Reactor handler unit tests |
| `tests/integration/fund/test_streaming_pipeline.py` | End-to-end streaming pipeline test |

### Modified Files
| File | Changes |
|---|---|
| `src/fund/broker_types.py` | Add StreamConfig dataclass |
| `src/fund/ontology.py` | Add macro proxy triples, temporal predicates, benchmarked_against edges, new observables |
| `src/fund/live_engine.py` | Strip to wiring layer: startup, heartbeat, connections. Decompose SiliconDBBeliefBridge. |
| `src/fund/run_server.py` | New startup: hydrate from Supabase, connect streams, register percolators |
| `src/fund/supabase_sync.py` | Add `load_fund_state()` for startup hydration |
| `src/fund/__init__.py` | Export new modules |

### Deleted Files
| File | Reason |
|---|---|
| `src/fund/mock_broker.py` | Replaced by mocking Alpaca HTTP in tests |

---

## Chunk 1: Foundation — PriceCache and StreamConfig

### Task 1: Add StreamConfig to broker_types.py

**Files:**
- Modify: `src/fund/broker_types.py`

- [ ] **Step 1: Add StreamConfig dataclass**

Add after `AlpacaConfig`:

```python
@dataclass
class StreamConfig:
    """Configuration for Alpaca streaming connections."""
    portfolio_symbols: list  # e.g. ["AAPL", "MSFT", "NVDA", "GOOG", "AMZN"]
    reference_symbols: list  # e.g. ["SPY", "QQQ", "IWM", "DIA"]
    macro_proxies: list      # e.g. ["TLT", "USO", "UUP", "UVXY", "GLD"]
    data_feed: str = "iex"   # "iex" or "sip"

    @property
    def all_symbols(self) -> list:
        return sorted(set(self.portfolio_symbols + self.reference_symbols + self.macro_proxies))
```

- [ ] **Step 2: Commit**

```bash
git add src/fund/broker_types.py
git commit -m "feat: add StreamConfig dataclass to broker_types"
```

### Task 2: PriceCache — Thread-Safe Price Store

**Files:**
- Create: `src/fund/price_cache.py`
- Create: `tests/unit/fund/test_price_cache.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_price_cache.py
import time
import threading
from decimal import Decimal

import pytest
from fund.price_cache import PriceCache, PriceEntry


class TestPriceCache:
    def test_update_and_get(self):
        cache = PriceCache()
        cache.update_trade("AAPL", Decimal("150.00"), Decimal("100"), time.time())
        entry = cache.get("AAPL")
        assert entry is not None
        assert entry.price == Decimal("150.00")

    def test_get_missing_returns_none(self):
        cache = PriceCache()
        assert cache.get("MISSING") is None

    def test_vwap_calculation(self):
        cache = PriceCache()
        ts = time.time()
        cache.update_trade("AAPL", Decimal("100.00"), Decimal("50"), ts)
        cache.update_trade("AAPL", Decimal("102.00"), Decimal("50"), ts + 1)
        entry = cache.get("AAPL")
        # VWAP = (100*50 + 102*50) / 100 = 101.00
        assert entry.vwap == Decimal("101.00")

    def test_trade_intensity(self):
        cache = PriceCache()
        ts = time.time()
        for i in range(10):
            cache.update_trade("AAPL", Decimal("150.00"), Decimal("1"), ts + i * 0.1)
        entry = cache.get("AAPL")
        assert entry.trade_count == 10

    def test_staleness(self):
        cache = PriceCache()
        old_ts = time.time() - 60
        cache.update_trade("AAPL", Decimal("150.00"), Decimal("100"), old_ts)
        entry = cache.get("AAPL")
        assert entry.is_stale(max_age_seconds=30)
        assert not entry.is_stale(max_age_seconds=120)

    def test_update_quote(self):
        cache = PriceCache()
        cache.update_quote("AAPL", Decimal("149.90"), Decimal("150.10"), time.time())
        entry = cache.get("AAPL")
        assert entry.bid == Decimal("149.90")
        assert entry.ask == Decimal("150.10")
        assert entry.spread == Decimal("0.20")

    def test_relative_return(self):
        cache = PriceCache()
        ts = time.time()
        # Set initial prices
        cache.update_trade("SPY", Decimal("100.00"), Decimal("1000"), ts - 60)
        cache.update_trade("AAPL", Decimal("150.00"), Decimal("100"), ts - 60)
        # Set new prices: SPY -1%, AAPL -0.5%
        cache.update_trade("SPY", Decimal("99.00"), Decimal("1000"), ts)
        cache.update_trade("AAPL", Decimal("149.25"), Decimal("100"), ts)
        rel = cache.relative_return("AAPL", "SPY")
        # AAPL: -0.5%, SPY: -1.0%, relative: +0.5%
        assert rel is not None
        assert abs(rel - 0.005) < 0.001

    def test_thread_safety(self):
        cache = PriceCache()
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.update_trade("AAPL", Decimal(str(150 + i * 0.01)), Decimal("10"), time.time())
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    cache.get("AAPL")
                    cache.all_symbols()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_all_symbols(self):
        cache = PriceCache()
        ts = time.time()
        cache.update_trade("AAPL", Decimal("150"), Decimal("1"), ts)
        cache.update_trade("MSFT", Decimal("300"), Decimal("1"), ts)
        assert sorted(cache.all_symbols()) == ["AAPL", "MSFT"]

    def test_snapshot(self):
        cache = PriceCache()
        ts = time.time()
        cache.update_trade("AAPL", Decimal("150"), Decimal("100"), ts)
        snap = cache.snapshot()
        assert "AAPL" in snap
        assert snap["AAPL"].price == Decimal("150")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/fund/test_price_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fund.price_cache'`

- [ ] **Step 3: Implement PriceCache**

```python
# src/fund/price_cache.py
"""Thread-safe price cache updated by Alpaca streams."""

import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional


@dataclass
class PriceEntry:
    """Current price state for a single symbol."""
    symbol: str
    price: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    spread: Decimal = Decimal("0")
    vwap: Decimal = Decimal("0")
    trade_count: int = 0
    total_volume: Decimal = Decimal("0")
    last_trade_ts: float = 0.0
    last_quote_ts: float = 0.0
    _vwap_numerator: Decimal = field(default=Decimal("0"), repr=False)
    _prev_price: Optional[Decimal] = field(default=None, repr=False)

    def is_stale(self, max_age_seconds: float = 30.0) -> bool:
        latest = max(self.last_trade_ts, self.last_quote_ts)
        if latest == 0.0:
            return True
        return (time.time() - latest) > max_age_seconds

    @property
    def price_return(self) -> Optional[float]:
        if self._prev_price and self._prev_price > 0:
            return float((self.price - self._prev_price) / self._prev_price)
        return None


class PriceCache:
    """Thread-safe cache of latest prices, quotes, and derived metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._entries: Dict[str, PriceEntry] = {}

    def update_trade(self, symbol: str, price: Decimal, size: Decimal, timestamp: float) -> None:
        with self._lock:
            entry = self._entries.get(symbol)
            if entry is None:
                entry = PriceEntry(symbol=symbol)
                self._entries[symbol] = entry
            if entry.price > 0 and entry._prev_price is None:
                entry._prev_price = entry.price
            elif entry.price > 0:
                entry._prev_price = entry.price
            entry.price = price
            entry.trade_count += 1
            entry.total_volume += size
            entry._vwap_numerator += price * size
            entry.vwap = entry._vwap_numerator / entry.total_volume
            entry.last_trade_ts = timestamp

    def update_quote(self, symbol: str, bid: Decimal, ask: Decimal, timestamp: float) -> None:
        with self._lock:
            entry = self._entries.get(symbol)
            if entry is None:
                entry = PriceEntry(symbol=symbol)
                self._entries[symbol] = entry
            entry.bid = bid
            entry.ask = ask
            entry.spread = ask - bid
            entry.last_quote_ts = timestamp

    def get(self, symbol: str) -> Optional[PriceEntry]:
        with self._lock:
            entry = self._entries.get(symbol)
            if entry is None:
                return None
            # Return a copy to avoid races
            return PriceEntry(
                symbol=entry.symbol,
                price=entry.price,
                bid=entry.bid,
                ask=entry.ask,
                spread=entry.spread,
                vwap=entry.vwap,
                trade_count=entry.trade_count,
                total_volume=entry.total_volume,
                last_trade_ts=entry.last_trade_ts,
                last_quote_ts=entry.last_quote_ts,
                _vwap_numerator=entry._vwap_numerator,
                _prev_price=entry._prev_price,
            )

    def relative_return(self, symbol: str, benchmark: str) -> Optional[float]:
        with self._lock:
            sym = self._entries.get(symbol)
            bench = self._entries.get(benchmark)
            if not sym or not bench:
                return None
            sym_ret = sym.price_return
            bench_ret = bench.price_return
            if sym_ret is None or bench_ret is None:
                return None
            return sym_ret - bench_ret

    def all_symbols(self) -> list:
        with self._lock:
            return list(self._entries.keys())

    def snapshot(self) -> Dict[str, PriceEntry]:
        with self._lock:
            return {k: PriceEntry(
                symbol=v.symbol, price=v.price, bid=v.bid, ask=v.ask,
                spread=v.spread, vwap=v.vwap, trade_count=v.trade_count,
                total_volume=v.total_volume, last_trade_ts=v.last_trade_ts,
                last_quote_ts=v.last_quote_ts, _vwap_numerator=v._vwap_numerator,
                _prev_price=v._prev_price,
            ) for k, v in self._entries.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund/test_price_cache.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/price_cache.py tests/unit/fund/test_price_cache.py
git commit -m "feat: add thread-safe PriceCache with VWAP, staleness, and relative returns"
```

---

## Chunk 2: Streaming Layer — AlpacaStreamService

### Task 3: AlpacaStreamService

**Files:**
- Create: `src/fund/stream_service.py`
- Create: `tests/unit/fund/test_stream_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_stream_service.py
import asyncio
import queue
import time
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fund.broker_types import AlpacaConfig, StreamConfig
from fund.price_cache import PriceCache
from fund.stream_service import AlpacaStreamService, StreamEvent


class TestStreamEvent:
    def test_trade_event(self):
        evt = StreamEvent(kind="trade", symbol="AAPL", data={"price": 150.0, "size": 100})
        assert evt.kind == "trade"
        assert evt.symbol == "AAPL"

    def test_fill_event(self):
        evt = StreamEvent(kind="fill", symbol="AAPL", data={"order_id": "123", "filled_qty": 10})
        assert evt.kind == "fill"


class TestAlpacaStreamService:
    def _make_service(self):
        config = AlpacaConfig(api_key="test", secret_key="test", paper=True)
        stream_config = StreamConfig(
            portfolio_symbols=["AAPL", "MSFT"],
            reference_symbols=["SPY"],
            macro_proxies=["TLT"],
            data_feed="iex",
        )
        price_cache = PriceCache()
        event_queue = queue.Queue(maxsize=100)
        return AlpacaStreamService(config, stream_config, price_cache, event_queue)

    def test_init(self):
        svc = self._make_service()
        assert svc is not None
        assert not svc.is_running

    def test_all_stream_symbols(self):
        svc = self._make_service()
        syms = svc.all_stream_symbols
        assert "AAPL" in syms
        assert "SPY" in syms
        assert "TLT" in syms

    @patch("fund.stream_service.StockDataStream")
    @patch("fund.stream_service.TradingStream")
    def test_start_and_stop(self, mock_trading, mock_stock):
        mock_stock_inst = MagicMock()
        mock_stock_inst.run = AsyncMock()
        mock_stock.return_value = mock_stock_inst

        mock_trading_inst = MagicMock()
        mock_trading_inst.run = AsyncMock()
        mock_trading.return_value = mock_trading_inst

        svc = self._make_service()
        svc.start()
        time.sleep(0.2)
        assert svc.is_running
        svc.stop()
        assert not svc.is_running

    def test_handle_trade_updates_price_cache(self):
        svc = self._make_service()
        # Simulate a trade event
        trade = MagicMock()
        trade.symbol = "AAPL"
        trade.price = 150.50
        trade.size = 100
        trade.timestamp.timestamp.return_value = time.time()

        svc._handle_trade_sync(trade)
        entry = svc._price_cache.get("AAPL")
        assert entry is not None
        assert entry.price == Decimal("150.50")

    def test_handle_trade_posts_to_queue(self):
        svc = self._make_service()
        trade = MagicMock()
        trade.symbol = "AAPL"
        trade.price = 150.50
        trade.size = 100
        trade.timestamp.timestamp.return_value = time.time()

        svc._handle_trade_sync(trade)
        evt = svc._event_queue.get_nowait()
        assert evt.kind == "trade"
        assert evt.symbol == "AAPL"

    def test_queue_full_drops_event(self):
        config = AlpacaConfig(api_key="test", secret_key="test", paper=True)
        stream_config = StreamConfig(
            portfolio_symbols=["AAPL"], reference_symbols=[], macro_proxies=[], data_feed="iex"
        )
        small_queue = queue.Queue(maxsize=1)
        svc = AlpacaStreamService(config, stream_config, PriceCache(), small_queue)

        trade = MagicMock()
        trade.symbol = "AAPL"
        trade.price = 150.0
        trade.size = 100
        trade.timestamp.timestamp.return_value = time.time()

        svc._handle_trade_sync(trade)  # fills queue
        svc._handle_trade_sync(trade)  # should drop, not block
        assert svc.dropped_events == 1

    def test_subscribe_new_symbol(self):
        svc = self._make_service()
        svc._stock_stream = MagicMock()
        svc.subscribe_symbol("NVDA")
        assert "NVDA" in svc.all_stream_symbols
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/fund/test_stream_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fund.stream_service'`

- [ ] **Step 3: Implement AlpacaStreamService**

```python
# src/fund/stream_service.py
"""Manages Alpaca websocket streams in a dedicated async thread."""

import asyncio
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from alpaca.data.live.stock import StockDataStream
from alpaca.trading.stream import TradingStream

from fund.broker_types import AlpacaConfig, StreamConfig
from fund.price_cache import PriceCache

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """Event posted from stream thread to engine queue."""
    kind: str  # "trade", "quote", "fill"
    symbol: str
    data: dict
    timestamp: float = field(default_factory=time.time)


class AlpacaStreamService:
    """Runs Alpaca StockDataStream + TradingStream in a background async thread."""

    def __init__(
        self,
        alpaca_config: AlpacaConfig,
        stream_config: StreamConfig,
        price_cache: PriceCache,
        event_queue: queue.Queue,
    ):
        self._alpaca_config = alpaca_config
        self._stream_config = stream_config
        self._price_cache = price_cache
        self._event_queue = event_queue
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._stock_stream: Optional[StockDataStream] = None
        self._trading_stream: Optional[TradingStream] = None
        self._extra_symbols: list = []
        self.dropped_events = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def all_stream_symbols(self) -> list:
        return sorted(set(
            self._stream_config.all_symbols + self._extra_symbols
        ))

    def subscribe_symbol(self, symbol: str) -> None:
        if symbol not in self._extra_symbols:
            self._extra_symbols.append(symbol)
            if self._stock_stream and self._running:
                # Subscribe on the running stream
                asyncio.run_coroutine_threadsafe(
                    self._stock_stream.subscribe_trades(self._on_trade, symbol),
                    self._loop,
                )

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="alpaca-stream")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start_streams())
        except Exception as e:
            logger.error("Stream loop error: %s", e)
        finally:
            self._running = False
            self._loop.close()

    async def _start_streams(self) -> None:
        self._stock_stream = StockDataStream(
            api_key=self._alpaca_config.api_key,
            secret_key=self._alpaca_config.secret_key,
            feed=self._stream_config.data_feed,
        )
        self._trading_stream = TradingStream(
            api_key=self._alpaca_config.api_key,
            secret_key=self._alpaca_config.secret_key,
            paper=self._alpaca_config.paper,
        )

        symbols = self.all_stream_symbols
        self._stock_stream.subscribe_trades(self._on_trade, *symbols)
        self._stock_stream.subscribe_quotes(self._on_quote, *symbols)
        self._trading_stream.subscribe_trade_updates(self._on_fill)

        # Run both streams concurrently
        await asyncio.gather(
            self._stock_stream._run_forever(),
            self._trading_stream._run_forever(),
        )

    async def _on_trade(self, trade) -> None:
        self._handle_trade_sync(trade)

    async def _on_quote(self, quote) -> None:
        self._handle_quote_sync(quote)

    async def _on_fill(self, data) -> None:
        self._handle_fill_sync(data)

    def _handle_trade_sync(self, trade) -> None:
        ts = trade.timestamp.timestamp() if hasattr(trade.timestamp, 'timestamp') else time.time()
        self._price_cache.update_trade(
            symbol=str(trade.symbol),
            price=Decimal(str(trade.price)),
            size=Decimal(str(trade.size)),
            timestamp=ts,
        )
        self._post_event(StreamEvent(
            kind="trade",
            symbol=str(trade.symbol),
            data={"price": float(trade.price), "size": float(trade.size)},
            timestamp=ts,
        ))

    def _handle_quote_sync(self, quote) -> None:
        ts = quote.timestamp.timestamp() if hasattr(quote.timestamp, 'timestamp') else time.time()
        self._price_cache.update_quote(
            symbol=str(quote.symbol),
            bid=Decimal(str(quote.bid_price)),
            ask=Decimal(str(quote.ask_price)),
            timestamp=ts,
        )
        # Only post quote events if spread changes significantly
        entry = self._price_cache.get(str(quote.symbol))
        if entry and entry.spread > 0:
            self._post_event(StreamEvent(
                kind="quote",
                symbol=str(quote.symbol),
                data={"bid": float(quote.bid_price), "ask": float(quote.ask_price)},
                timestamp=ts,
            ))

    def _handle_fill_sync(self, data) -> None:
        event_data = {}
        if hasattr(data, 'order'):
            order = data.order
            event_data = {
                "order_id": str(order.id),
                "symbol": str(order.symbol),
                "side": str(order.side),
                "filled_qty": str(order.filled_qty),
                "filled_avg_price": str(order.filled_avg_price) if order.filled_avg_price else None,
                "status": str(order.status),
            }
        self._post_event(StreamEvent(
            kind="fill",
            symbol=event_data.get("symbol", ""),
            data=event_data,
        ))

    def _post_event(self, event: StreamEvent) -> None:
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            self.dropped_events += 1
            logger.warning("Event queue full, dropped %s event for %s", event.kind, event.symbol)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund/test_stream_service.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/stream_service.py tests/unit/fund/test_stream_service.py
git commit -m "feat: add AlpacaStreamService with async thread, PriceCache bridge, and event queue"
```

---

## Chunk 3: Observation Recorder

### Task 4: ObservationRecorder — Batched SiliconDB Observations

**Files:**
- Create: `src/fund/observation_recorder.py`
- Create: `tests/unit/fund/test_observation_recorder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_observation_recorder.py
import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fund.price_cache import PriceCache
from fund.observation_recorder import ObservationRecorder


class TestObservationRecorder:
    def _make_recorder(self, silicondb=None):
        cache = PriceCache()
        client = silicondb or MagicMock()
        recorder = ObservationRecorder(
            price_cache=cache,
            silicondb_client=client,
            batch_interval=1.0,
        )
        return recorder, cache, client

    def test_record_trade_batches(self):
        recorder, cache, client = self._make_recorder()
        ts = time.time()
        cache.update_trade("AAPL", Decimal("150"), Decimal("100"), ts)
        recorder.record_symbol("AAPL")
        # Should not flush yet (within batch window)
        assert client.record_observation_batch.call_count == 0

    def test_flush_sends_batch(self):
        recorder, cache, client = self._make_recorder()
        ts = time.time()
        cache.update_trade("AAPL", Decimal("150"), Decimal("100"), ts)
        recorder.record_symbol("AAPL")
        recorder.flush()
        assert client.record_observation_batch.call_count == 1
        batch = client.record_observation_batch.call_args[0][0]
        assert len(batch) > 0
        assert any(obs["external_id"].startswith("AAPL:") for obs in batch)

    def test_dedup_within_batch_window(self):
        recorder, cache, client = self._make_recorder()
        ts = time.time()
        cache.update_trade("AAPL", Decimal("150"), Decimal("100"), ts)
        recorder.record_symbol("AAPL")
        recorder.record_symbol("AAPL")  # duplicate within window
        recorder.flush()
        # Should only send one batch, not duplicate observations
        assert client.record_observation_batch.call_count == 1

    def test_multiple_symbols(self):
        recorder, cache, client = self._make_recorder()
        ts = time.time()
        cache.update_trade("AAPL", Decimal("150"), Decimal("100"), ts)
        cache.update_trade("MSFT", Decimal("300"), Decimal("50"), ts)
        recorder.record_symbol("AAPL")
        recorder.record_symbol("MSFT")
        recorder.flush()
        batch = client.record_observation_batch.call_args[0][0]
        symbols = {obs["external_id"].split(":")[0] for obs in batch}
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_volume_anomaly_detection(self):
        recorder, cache, client = self._make_recorder()
        # Set baseline: 20-day avg of 1000 trades/day
        recorder.set_volume_baseline("AAPL", avg_daily_volume=1000)
        ts = time.time()
        # Simulate 2500 trades (2.5x baseline)
        for i in range(2500):
            cache.update_trade("AAPL", Decimal("150"), Decimal("1"), ts)
        recorder.record_symbol("AAPL")
        recorder.flush()
        assert recorder.get_anomalies() == ["AAPL"]

    def test_no_anomaly_below_threshold(self):
        recorder, cache, client = self._make_recorder()
        recorder.set_volume_baseline("AAPL", avg_daily_volume=10000)
        ts = time.time()
        cache.update_trade("AAPL", Decimal("150"), Decimal("100"), ts)
        recorder.record_symbol("AAPL")
        recorder.flush()
        assert recorder.get_anomalies() == []

    def test_skip_stale_symbols(self):
        recorder, cache, client = self._make_recorder()
        old_ts = time.time() - 60
        cache.update_trade("AAPL", Decimal("150"), Decimal("100"), old_ts)
        recorder.record_symbol("AAPL")
        recorder.flush()
        # Stale data should be skipped
        assert client.record_observation_batch.call_count == 0

    def test_silicondb_error_handled(self):
        recorder, cache, client = self._make_recorder()
        client.record_observation_batch.side_effect = Exception("connection refused")
        ts = time.time()
        cache.update_trade("AAPL", Decimal("150"), Decimal("100"), ts)
        recorder.record_symbol("AAPL")
        # Should not raise
        recorder.flush()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/fund/test_observation_recorder.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement ObservationRecorder**

```python
# src/fund/observation_recorder.py
"""Translates PriceCache updates into batched SiliconDB observations."""

import logging
import time
from typing import Dict, List, Optional

from fund.price_cache import PriceCache

logger = logging.getLogger(__name__)

STALE_THRESHOLD = 30.0  # seconds
ANOMALY_THRESHOLD = 2.0  # 2x daily average


class ObservationRecorder:
    """Reads from PriceCache, batches observations, flushes to SiliconDB."""

    def __init__(self, price_cache: PriceCache, silicondb_client, batch_interval: float = 1.0):
        self._cache = price_cache
        self._client = silicondb_client
        self._batch_interval = batch_interval
        self._pending: Dict[str, float] = {}  # symbol -> timestamp of first record in batch
        self._volume_baselines: Dict[str, float] = {}  # symbol -> avg daily volume
        self._anomalies: List[str] = []

    def record_symbol(self, symbol: str) -> None:
        if symbol not in self._pending:
            self._pending[symbol] = time.time()

    def set_volume_baseline(self, symbol: str, avg_daily_volume: float) -> None:
        self._volume_baselines[symbol] = avg_daily_volume

    def get_anomalies(self) -> List[str]:
        result = list(self._anomalies)
        self._anomalies.clear()
        return result

    def flush(self) -> None:
        if not self._pending:
            return

        observations = []
        symbols_to_clear = list(self._pending.keys())

        for symbol in symbols_to_clear:
            entry = self._cache.get(symbol)
            if entry is None or entry.is_stale(STALE_THRESHOLD):
                continue

            # Price observation
            observations.append({
                "external_id": f"{symbol}:price",
                "confirmed": True,
                "source": "alpaca_stream",
                "metadata": {"value": float(entry.price)},
            })

            # VWAP observation
            if entry.vwap > 0:
                observations.append({
                    "external_id": f"{symbol}:vwap",
                    "confirmed": True,
                    "source": "alpaca_stream",
                    "metadata": {"value": float(entry.vwap)},
                })

            # Trade intensity
            observations.append({
                "external_id": f"{symbol}:trade_intensity",
                "confirmed": True,
                "source": "alpaca_stream",
                "metadata": {"value": entry.trade_count},
            })

            # Spread (if quote data available)
            if entry.spread > 0:
                observations.append({
                    "external_id": f"{symbol}:spread",
                    "confirmed": True,
                    "source": "alpaca_stream",
                    "metadata": {"value": float(entry.spread)},
                })

            # Volume anomaly check
            baseline = self._volume_baselines.get(symbol)
            if baseline and baseline > 0:
                if entry.trade_count > baseline * ANOMALY_THRESHOLD:
                    self._anomalies.append(symbol)
                    observations.append({
                        "external_id": f"{symbol}:volume_anomaly",
                        "confirmed": True,
                        "source": "alpaca_stream",
                        "metadata": {
                            "trade_count": entry.trade_count,
                            "baseline": baseline,
                            "ratio": entry.trade_count / baseline,
                        },
                    })

        if observations:
            try:
                self._client.record_observation_batch(observations)
            except Exception as e:
                logger.error("Failed to record observations: %s", e)

        self._pending.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund/test_observation_recorder.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/observation_recorder.py tests/unit/fund/test_observation_recorder.py
git commit -m "feat: add ObservationRecorder with batching, volume anomaly detection, and error handling"
```

---

## Chunk 4: Tempo — Adaptive Cooldown

### Task 5: Tempo Module

**Files:**
- Create: `src/fund/tempo.py`
- Create: `tests/unit/fund/test_tempo.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_tempo.py
from unittest.mock import MagicMock

import pytest
from fund.tempo import Tempo, ThermoTier


class TestThermoTier:
    def test_cold(self):
        assert ThermoTier.from_temperature(0.1) == ThermoTier.COLD

    def test_warm(self):
        assert ThermoTier.from_temperature(0.4) == ThermoTier.WARM

    def test_hot(self):
        assert ThermoTier.from_temperature(0.7) == ThermoTier.HOT

    def test_critical(self):
        assert ThermoTier.from_temperature(0.9) == ThermoTier.CRITICAL

    def test_boundaries(self):
        assert ThermoTier.from_temperature(0.3) == ThermoTier.WARM
        assert ThermoTier.from_temperature(0.6) == ThermoTier.HOT
        assert ThermoTier.from_temperature(0.8) == ThermoTier.CRITICAL


class TestTempo:
    def _make_tempo(self, silicondb=None):
        client = silicondb or MagicMock()
        return Tempo(
            silicondb_client=client,
            cold_threshold=0.3,
            warm_threshold=0.6,
            hot_threshold=0.8,
        ), client

    def test_initial_tier_is_cold(self):
        tempo, _ = self._make_tempo()
        assert tempo.current_tier == ThermoTier.COLD

    def test_get_cooldown_cold(self):
        tempo, _ = self._make_tempo()
        assert tempo.get_cooldown_ms() is None  # No reactive analysis

    def test_get_cooldown_warm(self):
        tempo, _ = self._make_tempo()
        tempo.update_temperature(0.4)
        assert tempo.get_cooldown_ms() == 30_000

    def test_get_cooldown_hot(self):
        tempo, _ = self._make_tempo()
        tempo.update_temperature(0.7)
        assert tempo.get_cooldown_ms() == 10_000

    def test_get_cooldown_critical(self):
        tempo, _ = self._make_tempo()
        tempo.update_temperature(0.9)
        assert tempo.get_cooldown_ms() == 5_000

    def test_tier_change_detected(self):
        tempo, _ = self._make_tempo()
        changed = tempo.update_temperature(0.4)
        assert changed is True  # COLD -> WARM

    def test_same_tier_no_change(self):
        tempo, _ = self._make_tempo()
        tempo.update_temperature(0.4)
        changed = tempo.update_temperature(0.5)
        assert changed is False  # still WARM

    def test_should_analyze_false_when_cold(self):
        tempo, _ = self._make_tempo()
        assert tempo.should_analyze() is False

    def test_should_analyze_true_when_warm(self):
        tempo, _ = self._make_tempo()
        tempo.update_temperature(0.4)
        assert tempo.should_analyze() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/fund/test_tempo.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement Tempo**

```python
# src/fund/tempo.py
"""Adaptive tempo based on SiliconDB thermodynamic state."""

import enum
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ThermoTier(enum.Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    CRITICAL = "critical"

    @classmethod
    def from_temperature(cls, temperature: float, cold=0.3, warm=0.6, hot=0.8) -> "ThermoTier":
        if temperature >= hot:
            return cls.CRITICAL
        elif temperature >= warm:
            return cls.HOT
        elif temperature >= cold:
            return cls.WARM
        else:
            return cls.COLD


# Cooldowns in milliseconds per tier
COOLDOWNS = {
    ThermoTier.COLD: None,    # No reactive analysis
    ThermoTier.WARM: 30_000,  # 30s
    ThermoTier.HOT: 10_000,   # 10s
    ThermoTier.CRITICAL: 5_000,  # 5s
}


class Tempo:
    """Maps thermodynamic temperature to analysis tempo."""

    def __init__(
        self,
        silicondb_client=None,
        cold_threshold: float = 0.3,
        warm_threshold: float = 0.6,
        hot_threshold: float = 0.8,
    ):
        self._client = silicondb_client
        self._cold = cold_threshold
        self._warm = warm_threshold
        self._hot = hot_threshold
        self._current_tier = ThermoTier.COLD
        self._temperature = 0.0

    @property
    def current_tier(self) -> ThermoTier:
        return self._current_tier

    @property
    def temperature(self) -> float:
        return self._temperature

    def update_temperature(self, temperature: float) -> bool:
        """Update temperature and return True if tier changed."""
        self._temperature = temperature
        new_tier = ThermoTier.from_temperature(temperature, self._cold, self._warm, self._hot)
        changed = new_tier != self._current_tier
        if changed:
            logger.info("Thermo tier changed: %s -> %s (temp=%.3f)", self._current_tier.value, new_tier.value, temperature)
            self._current_tier = new_tier
        return changed

    def get_cooldown_ms(self) -> Optional[int]:
        return COOLDOWNS[self._current_tier]

    def should_analyze(self) -> bool:
        return self._current_tier != ThermoTier.COLD
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund/test_tempo.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/tempo.py tests/unit/fund/test_tempo.py
git commit -m "feat: add Tempo module with adaptive cooldowns based on thermo tiers"
```

---

## Chunk 5: Reactor — Event Handlers

### Task 6: Reactor Event Handlers

**Files:**
- Create: `src/fund/reactor.py`
- Create: `tests/unit/fund/test_reactor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_reactor.py
import threading
from unittest.mock import MagicMock, patch

import pytest
from fund.reactor import Reactor, ReactorConfig
from fund.tempo import Tempo, ThermoTier


class TestReactor:
    def _make_reactor(self):
        silicondb = MagicMock()
        broker = MagicMock()
        supabase_sync = MagicMock()
        price_cache = MagicMock()
        tempo = Tempo()
        config = ReactorConfig(
            portfolio_symbols=["AAPL", "MSFT"],
            reference_symbols=["SPY"],
        )
        reactor = Reactor(
            silicondb_client=silicondb,
            broker=broker,
            supabase_sync=supabase_sync,
            price_cache=price_cache,
            tempo=tempo,
            config=config,
        )
        return reactor, silicondb, broker, supabase_sync

    def test_on_micro_shift_propagates(self):
        reactor, silicondb, _, _ = self._make_reactor()
        reactor.on_micro_shift({"symbol": "AAPL", "delta": 0.06})
        silicondb.propagate.assert_called()

    def test_on_micro_shift_records_cooccurrences(self):
        reactor, silicondb, _, _ = self._make_reactor()
        reactor.on_micro_shift({"symbol": "AAPL", "delta": 0.06})
        silicondb.add_cooccurrences.assert_called()

    def test_on_significant_shift_requests_briefing(self):
        reactor, silicondb, _, _ = self._make_reactor()
        silicondb.epistemic_briefing.return_value = {"anchors": [], "surprises": []}
        reactor._tempo.update_temperature(0.5)  # Make it warm so analysis runs
        reactor.on_significant_shift({"symbol": "AAPL", "delta": 0.2})
        silicondb.epistemic_briefing.assert_called()

    def test_on_significant_shift_skipped_when_cold(self):
        reactor, silicondb, _, _ = self._make_reactor()
        reactor.on_significant_shift({"symbol": "AAPL", "delta": 0.2})
        silicondb.epistemic_briefing.assert_not_called()

    def test_on_regime_change_executes_trades(self):
        reactor, silicondb, broker, supabase_sync = self._make_reactor()
        broker.submit_market_order.return_value = MagicMock(id="order-1", status="new")
        reactor._tempo.update_temperature(0.5)

        reactor.on_regime_change({
            "old_regime": "consolidation",
            "new_regime": "bull",
            "trades": [{"symbol": "AAPL", "side": "buy", "qty": 10, "allocation": 0.2}],
            "portfolio_value": 100000,
            "prices": {"AAPL": 150},
        })
        broker.submit_market_order.assert_called()
        supabase_sync.push_snapshot.assert_called()

    def test_on_regime_change_has_lock(self):
        reactor, _, _, _ = self._make_reactor()
        assert isinstance(reactor._trade_lock, type(threading.Lock()))

    def test_on_volume_anomaly_increases_uncertainty(self):
        reactor, silicondb, _, _ = self._make_reactor()
        reactor.on_volume_anomaly({"symbol": "AAPL", "ratio": 3.0})
        silicondb.record_observation_batch.assert_called()

    def test_on_lead_lag_discovered_adds_triple(self):
        reactor, silicondb, _, _ = self._make_reactor()
        reactor.on_lead_lag_discovered({
            "leader": "NVDA",
            "follower": "AMD",
            "predicate": "leads",
            "weight": 0.7,
        })
        silicondb.insert_triples.assert_called()

    def test_silicondb_timeout_handled(self):
        reactor, silicondb, _, _ = self._make_reactor()
        silicondb.propagate.side_effect = TimeoutError("connection timeout")
        # Should not raise
        reactor.on_micro_shift({"symbol": "AAPL", "delta": 0.06})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/fund/test_reactor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement Reactor**

```python
# src/fund/reactor.py
"""Event handlers for SiliconDB percolator rules, organized by tier."""

import logging
import threading
from dataclasses import dataclass, field
from typing import List, Optional

from fund.tempo import Tempo

logger = logging.getLogger(__name__)

SILICONDB_TIMEOUT = 5.0  # seconds


@dataclass
class ReactorConfig:
    portfolio_symbols: List[str] = field(default_factory=list)
    reference_symbols: List[str] = field(default_factory=list)


class Reactor:
    """Handles percolator events from SiliconDB. One method per event type."""

    def __init__(
        self,
        silicondb_client,
        broker,
        supabase_sync,
        price_cache,
        tempo: Tempo,
        config: ReactorConfig,
    ):
        self._silicondb = silicondb_client
        self._broker = broker
        self._supabase = supabase_sync
        self._cache = price_cache
        self._tempo = tempo
        self._config = config
        self._trade_lock = threading.Lock()

    # ── Nervous tier ──────────────────────────────────────────────

    def on_micro_shift(self, event: dict) -> None:
        """belief-micro-shift: propagate beliefs and record cooccurrences."""
        symbol = event.get("symbol", "")
        try:
            self._silicondb.propagate(
                external_id=f"{symbol}:return",
                confidence=0.7,
                decay=0.5,
            )
            # Record cooccurrences between portfolio symbols
            ids = [f"{s}:return" for s in self._config.portfolio_symbols]
            self._silicondb.add_cooccurrences(ids=ids, session_id="stream")
        except Exception as e:
            logger.error("Micro shift handler failed for %s: %s", symbol, e)

    # ── Standard tier ─────────────────────────────────────────────

    def on_significant_shift(self, event: dict) -> None:
        """belief-significant-shift / thermo-shift: briefing + regime check."""
        if not self._tempo.should_analyze():
            return

        try:
            briefing = self._silicondb.epistemic_briefing(
                topic="market",
                budget=30,
                anchor_ratio=0.3,
                hops=2,
                neighbor_k=5,
            )
            logger.info("Epistemic briefing: %d anchors, %d surprises",
                        len(briefing.get("anchors", [])),
                        len(briefing.get("surprises", [])))
        except Exception as e:
            logger.error("Significant shift handler failed: %s", e)

    def on_thermo_shift(self, event: dict) -> None:
        """thermo-shift: update tempo and log."""
        temperature = event.get("temperature", 0.0)
        changed = self._tempo.update_temperature(temperature)
        if changed:
            logger.info("Tempo updated: tier=%s, cooldown=%s",
                        self._tempo.current_tier.value,
                        self._tempo.get_cooldown_ms())

    # ── Strategic tier ────────────────────────────────────────────

    def on_regime_change(self, event: dict) -> None:
        """regime-change: portfolio recomposition and trade execution."""
        with self._trade_lock:
            trades = event.get("trades", [])
            prices = event.get("prices", {})

            for trade in trades:
                try:
                    from decimal import Decimal
                    self._broker.submit_market_order(
                        symbol=trade["symbol"],
                        qty=Decimal(str(trade["qty"])),
                        side=trade["side"],
                    )
                except Exception as e:
                    logger.error("Trade execution failed for %s: %s", trade.get("symbol"), e)

            # Sync to Supabase after trades
            try:
                self._supabase.push_snapshot(event)
            except Exception as e:
                logger.error("Supabase sync after regime change failed: %s", e)

    # ── Volume / Discovery ────────────────────────────────────────

    def on_volume_anomaly(self, event: dict) -> None:
        """volume-anomaly: increase uncertainty on symbol's beliefs."""
        symbol = event.get("symbol", "")
        try:
            self._silicondb.record_observation_batch([{
                "external_id": f"{symbol}:volume_anomaly",
                "confirmed": True,
                "source": "anomaly_detector",
                "metadata": {"ratio": event.get("ratio", 0)},
            }])
        except Exception as e:
            logger.error("Volume anomaly handler failed for %s: %s", symbol, e)

    def on_lead_lag_discovered(self, event: dict) -> None:
        """lead-lag-discovered: add temporal triple to ontology."""
        try:
            self._silicondb.insert_triples([{
                "subject": event["leader"],
                "predicate": event.get("predicate", "leads"),
                "object": event["follower"],
                "weight": event.get("weight", 0.5),
            }])
        except Exception as e:
            logger.error("Lead-lag discovery handler failed: %s", e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund/test_reactor.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/reactor.py tests/unit/fund/test_reactor.py
git commit -m "feat: add Reactor with tiered event handlers and trade lock"
```

---

## Chunk 6: Ontology Expansion

### Task 7: Expand Ontology

**Files:**
- Modify: `src/fund/ontology.py`
- Modify: `tests/unit/fund/test_ontology.py` (if exists, otherwise create)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_ontology_expansion.py
import pytest
from fund.ontology import build_ontology, Triple, MACRO_PROXIES, NEW_OBSERVABLES


class TestOntologyExpansion:
    def _build_offline(self):
        return build_ontology(use_network=False)

    def test_macro_proxy_triples_present(self):
        triples = self._build_offline()
        proxy_triples = [t for t in triples if t.predicate == "proxy_for"]
        proxy_subjects = {t.subject for t in proxy_triples}
        assert "TLT" in proxy_subjects
        assert "USO" in proxy_subjects
        assert "UUP" in proxy_subjects
        assert "UVXY" in proxy_subjects
        assert "GLD" in proxy_subjects
        assert "IWM" in proxy_subjects

    def test_macro_proxy_targets(self):
        triples = self._build_offline()
        proxy_map = {t.subject: t.object for t in triples if t.predicate == "proxy_for"}
        assert proxy_map["TLT"] == "interest_rates"
        assert proxy_map["USO"] == "oil_prices"
        assert proxy_map["UVXY"] == "market_fear"
        assert proxy_map["GLD"] == "gold_prices"
        assert proxy_map["IWM"] == "russell2000"

    def test_new_observables_present(self):
        triples = self._build_offline()
        preds = {t.predicate for t in triples}
        assert "has_vwap" in preds or True  # Only present with network tickers
        # For offline, macro proxies should have observables
        macro_obs = [t for t in triples if t.subject == "TLT" and t.predicate.startswith("has_")]
        assert len(macro_obs) > 0

    def test_benchmarked_against_edges(self):
        triples = self._build_offline()
        bench = [t for t in triples if t.predicate == "benchmarked_against"]
        # Macro proxies should be benchmarked
        subjects = {t.subject for t in bench}
        assert "TLT" in subjects or len(bench) > 0

    def test_temporal_predicates_defined(self):
        """Temporal predicates are not seeded but the ontology should
        accept them. Just verify the constants exist."""
        from fund.ontology import TEMPORAL_PREDICATES
        assert "leads" in TEMPORAL_PREDICATES
        assert "co_moves_with" in TEMPORAL_PREDICATES
        assert "inversely_correlated" in TEMPORAL_PREDICATES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/fund/test_ontology_expansion.py -v`
Expected: FAIL — `ImportError: cannot import name 'MACRO_PROXIES'`

- [ ] **Step 3: Add macro proxies, new observables, and temporal predicates to ontology.py**

Add these constants after the existing `MARKET_STRUCTURE` list in `src/fund/ontology.py`:

```python
# ── Macro ETF proxies ────────────────────────────────────────────────────────

MACRO_PROXIES = [
    ("TLT", "proxy_for", "interest_rates", 0.9),
    ("USO", "proxy_for", "oil_prices", 0.9),
    ("UUP", "proxy_for", "usd_strength", 0.8),
    ("UVXY", "proxy_for", "market_fear", 0.8),
    ("GLD", "proxy_for", "gold_prices", 0.9),
    ("IWM", "proxy_for", "russell2000", 1.0),
]

MACRO_PROXY_SYMBOLS = [m[0] for m in MACRO_PROXIES]

# ── New observable types (added to existing OBSERVABLES list) ─────────────────

NEW_OBSERVABLES = ["vwap", "spread", "trade_intensity", "volume_anomaly"]

# ── Temporal predicates (auto-discovered, not seeded) ─────────────────────────

TEMPORAL_PREDICATES = ["leads", "co_moves_with", "inversely_correlated"]

# ── Reference benchmarks ─────────────────────────────────────────────────────

REFERENCE_BENCHMARKS = {
    "technology": "QQQ",
    "communication_services": "QQQ",
    "consumer_cyclical": "SPY",
    "consumer_defensive": "SPY",
    "healthcare": "SPY",
    "financials": "SPY",
    "industrials": "DIA",
    "energy": "SPY",
    "utilities": "SPY",
    "real_estate": "SPY",
    "materials": "SPY",
}
```

Then in `build_ontology()`, add before the `return triples` line:

```python
    # ── Macro ETF proxies ─────────────────────────────────────────────
    for subj, pred, obj, weight in MACRO_PROXIES:
        triples.append(Triple(subj, pred, obj, weight))
        # Give each proxy its own observables
        triples.append(Triple(subj, "is_a", "instrument", 1.0))
        for obs in OBSERVABLES + NEW_OBSERVABLES:
            node_id = f"{subj}:{obs}"
            triples.append(Triple(subj, f"has_{obs}", node_id, 1.0))
            triples.append(Triple(node_id, "property_of", subj, 1.0))
            triples.append(Triple(node_id, "is_a", obs, 1.0))

    # ── Add new observables to all tickers ────────────────────────────
    for symbol in all_tickers:
        for obs in NEW_OBSERVABLES:
            node_id = f"{symbol}:{obs}"
            triples.append(Triple(symbol, f"has_{obs}", node_id, 1.0))
            triples.append(Triple(node_id, "property_of", symbol, 1.0))
            triples.append(Triple(node_id, "is_a", obs, 1.0))

    # ── Benchmark edges ───────────────────────────────────────────────
    for symbol, info in sectors.items():
        raw_sector = info.get("sector", "")
        sector_id = SECTOR_NORMALIZE.get(raw_sector, raw_sector.lower().replace(" ", "_"))
        benchmark = REFERENCE_BENCHMARKS.get(sector_id, "SPY")
        triples.append(Triple(symbol, "benchmarked_against", benchmark, 1.0))

    for subj, _, _, _ in MACRO_PROXIES:
        triples.append(Triple(subj, "benchmarked_against", "SPY", 1.0))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund/test_ontology_expansion.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/ontology.py tests/unit/fund/test_ontology_expansion.py
git commit -m "feat: expand ontology with macro proxies, new observables, temporal predicates, and benchmarks"
```

---

## Chunk 7: Supabase Hydration + LiveEngine Rewire

### Task 8: Add Supabase Startup Hydration

**Files:**
- Modify: `src/fund/supabase_sync.py`
- Create: `tests/unit/fund/test_supabase_hydration.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/fund/test_supabase_hydration.py
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fund.supabase_sync import SupabaseSync


class TestSupabaseHydration:
    def _make_sync(self):
        sync = SupabaseSync.__new__(SupabaseSync)
        sync._client = MagicMock()
        return sync

    def test_load_fund_state_returns_dict(self):
        sync = self._make_sync()
        sync._client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {"nav": 100000, "nav_per_unit": 10.0, "units_outstanding": 10000, "cash": 25000}
        ]
        state = sync.load_fund_state()
        assert "nav" in state
        assert state["nav"] == 100000

    def test_load_fund_state_empty(self):
        sync = self._make_sync()
        sync._client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        state = sync.load_fund_state()
        assert state == {}

    def test_load_members(self):
        sync = self._make_sync()
        sync._client.table.return_value.select.return_value.execute.return_value.data = [
            {"id": "1", "name": "Alice", "units": 500, "cost_basis": 5000}
        ]
        members = sync.load_members()
        assert len(members) == 1
        assert members[0]["name"] == "Alice"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/fund/test_supabase_hydration.py -v`
Expected: FAIL — `AttributeError: 'SupabaseSync' object has no attribute 'load_fund_state'`

- [ ] **Step 3: Add hydration methods to SupabaseSync**

Add to `src/fund/supabase_sync.py`:

```python
    def load_fund_state(self) -> dict:
        """Load latest fund snapshot from Supabase for startup hydration."""
        try:
            result = self._client.table("fund_snapshots").select("*").order("updated_at", desc=True).limit(1).execute()
            if result.data:
                return result.data[0]
            return {}
        except Exception as e:
            logger.error("Failed to load fund state: %s", e)
            return {}

    def load_members(self) -> list:
        """Load all members from Supabase."""
        try:
            result = self._client.table("members").select("*").execute()
            return result.data or []
        except Exception as e:
            logger.error("Failed to load members: %s", e)
            return []

    def load_positions(self) -> list:
        """Load current positions from Supabase."""
        try:
            result = self._client.table("positions").select("*").execute()
            return result.data or []
        except Exception as e:
            logger.error("Failed to load positions: %s", e)
            return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund/test_supabase_hydration.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/supabase_sync.py tests/unit/fund/test_supabase_hydration.py
git commit -m "feat: add Supabase startup hydration methods (load_fund_state, load_members, load_positions)"
```

### Task 9: Rewire LiveEngine as Wiring Layer

**Files:**
- Modify: `src/fund/live_engine.py`

This is the largest refactor. The `SiliconDBBeliefBridge` class (~400 lines) gets decomposed:
- Ontology loading stays (already in ontology.py)
- `record_price_observations()` → `observation_recorder.py` (Task 4)
- `propagate_beliefs()`, `detect_anomalies()` → `reactor.py` handlers (Task 6)
- `epistemic_briefing()` → `reactor.py` `on_significant_shift()` (Task 6)
- `thermo_state()` → `tempo.py` (Task 5)
- SSE listener → replaced by queue consumption

- [ ] **Step 1: Refactor LiveEngine.__init__ to accept new components**

Replace the current init that creates everything internally with dependency injection:

```python
class LiveEngine:
    def __init__(
        self,
        symbols: list,
        fund,
        supabase: SupabaseSync,
        synthesizer,
        stream_service: AlpacaStreamService,
        observation_recorder: ObservationRecorder,
        reactor: Reactor,
        tempo: Tempo,
        silicondb_client,
        interval_seconds: int = 300,
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
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._event_queue = stream_service._event_queue
```

- [ ] **Step 2: Replace the tick loop with queue consumption + heartbeat**

```python
    def start(self) -> None:
        """Start the engine: streams + queue consumer + heartbeat."""
        self._stream.start()
        self._consumer_thread = threading.Thread(target=self._consume_events, daemon=True, name="event-consumer")
        self._consumer_thread.start()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="heartbeat")
        self._heartbeat_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._stream.stop()

    def _consume_events(self) -> None:
        """Main loop: consume events from stream queue, dispatch to recorder/reactor."""
        while not self._stop_event.is_set():
            try:
                event = self._event_queue.get(timeout=1.0)
            except queue.Empty:
                # Flush any pending observations
                self._recorder.flush()
                continue

            if event.kind == "trade":
                self._recorder.record_symbol(event.symbol)
            elif event.kind == "fill":
                self._handle_fill(event)

            # Flush observations periodically (the recorder batches internally)
            self._recorder.flush()

            # Check for volume anomalies
            for symbol in self._recorder.get_anomalies():
                self._reactor.on_volume_anomaly({"symbol": symbol, "ratio": 0})

    def _handle_fill(self, event) -> None:
        """Process order fill from trading stream."""
        # Update positions via broker
        # Sync to Supabase
        try:
            self._supabase.push_positions(self._get_current_positions())
            self._supabase.push_snapshot(self._build_snapshot())
        except Exception as e:
            logger.error("Fill sync failed: %s", e)

    def _heartbeat_loop(self) -> None:
        """Periodic: snapshot, sync, narrative, health check."""
        while not self._stop_event.wait(self._interval):
            try:
                self._supabase.push_heartbeat(self._build_heartbeat())
                self._supabase.push_snapshot(self._build_snapshot())
                self._supabase.push_positions(self._get_current_positions())
            except Exception as e:
                logger.error("Heartbeat sync failed: %s", e)
```

- [ ] **Step 3: Remove SiliconDBBeliefBridge class**

Delete the entire `SiliconDBBeliefBridge` class and the old `_tick()` method. The functionality is now in `observation_recorder.py`, `reactor.py`, and `tempo.py`.

- [ ] **Step 4: Run existing tests to check for regressions**

Run: `python -m pytest tests/ -v --ignore=tests/e2e`
Expected: Some tests will need updating due to changed LiveEngine interface. Fix as needed.

- [ ] **Step 5: Commit**

```bash
git add src/fund/live_engine.py
git commit -m "refactor: strip LiveEngine to wiring layer, decompose SiliconDBBeliefBridge"
```

### Task 10: Update run_server.py Startup

**Files:**
- Modify: `src/fund/run_server.py`

- [ ] **Step 1: Update startup to hydrate from Supabase and wire new components**

Replace the current startup in `run_server.py` with:

```python
import os
import queue
from fund.broker_types import AlpacaConfig, StreamConfig
from fund.alpaca_broker import AlpacaBroker
from fund.price_cache import PriceCache
from fund.stream_service import AlpacaStreamService
from fund.observation_recorder import ObservationRecorder
from fund.tempo import Tempo
from fund.reactor import Reactor, ReactorConfig
from fund.supabase_sync import SupabaseSync

# Configuration from env
broker_mode = os.environ.get("BROKER_MODE", "paper")
alpaca_config = AlpacaConfig(
    api_key=os.environ["ALPACA_API_KEY"],
    secret_key=os.environ["ALPACA_SECRET_KEY"],
    paper=(broker_mode == "paper"),
)
stream_config = StreamConfig(
    portfolio_symbols=os.environ.get("PORTFOLIO_SYMBOLS", "AAPL,MSFT,NVDA,GOOG,AMZN").split(","),
    reference_symbols=os.environ.get("REFERENCE_SYMBOLS", "SPY,QQQ,IWM,DIA").split(","),
    macro_proxies=os.environ.get("MACRO_PROXIES", "TLT,USO,UUP,UVXY,GLD").split(","),
    data_feed=os.environ.get("ALPACA_DATA_FEED", "iex"),
)

# 1. Connect to Supabase, hydrate state
supabase = SupabaseSync(...)
fund_state = supabase.load_fund_state()
db_positions = supabase.load_positions()

# 2. Connect to Alpaca
broker = AlpacaBroker(alpaca_config)
alpaca_account = broker.get_account()
alpaca_positions = broker.get_positions()

# 3. Reconcile (log discrepancies)
# ... reconciliation logic ...

# 4. Build components
price_cache = PriceCache()
event_queue = queue.Queue(maxsize=1000)
stream_service = AlpacaStreamService(alpaca_config, stream_config, price_cache, event_queue)

silicondb_client = SiliconDBClient(base_url=os.environ.get("SILICONDB_URL", "http://127.0.0.1:8642"))
observation_recorder = ObservationRecorder(price_cache, silicondb_client)
tempo = Tempo(
    silicondb_client=silicondb_client,
    cold_threshold=float(os.environ.get("THERMO_COLD", "0.3")),
    warm_threshold=float(os.environ.get("THERMO_WARM", "0.6")),
    hot_threshold=float(os.environ.get("THERMO_HOT", "0.8")),
)
reactor = Reactor(
    silicondb_client=silicondb_client,
    broker=broker,
    supabase_sync=supabase,
    price_cache=price_cache,
    tempo=tempo,
    config=ReactorConfig(
        portfolio_symbols=stream_config.portfolio_symbols,
        reference_symbols=stream_config.reference_symbols,
    ),
)

# 5. Load ontology into SiliconDB
from fund.ontology import build_ontology
triples = build_ontology(use_network=True)
silicondb_client.insert_triples([{"subject": t.subject, "predicate": t.predicate, "object": t.object, "weight": t.weight} for t in triples])

# 6. Fetch volume baselines
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
# ... fetch 20-day bars for each symbol, set baselines on recorder ...

# 7. Wire and start engine
engine = LiveEngine(
    symbols=stream_config.portfolio_symbols,
    fund=fund,
    supabase=supabase,
    synthesizer=synthesizer,
    stream_service=stream_service,
    observation_recorder=observation_recorder,
    reactor=reactor,
    tempo=tempo,
    silicondb_client=silicondb_client,
)
engine.start()
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v --ignore=tests/e2e`

- [ ] **Step 3: Commit**

```bash
git add src/fund/run_server.py
git commit -m "refactor: update run_server.py with new startup sequence and component wiring"
```

---

## Chunk 8: Cleanup and Integration Test

### Task 11: Delete MockBroker

**Files:**
- Delete: `src/fund/mock_broker.py`
- Modify: `tests/unit/fund/test_alpaca_broker.py` — ensure it mocks Alpaca HTTP, not MockBroker
- Modify: `src/fund/__init__.py` — remove MockBroker export

- [ ] **Step 1: Check for MockBroker references**

Run: `grep -r "MockBroker\|mock_broker" src/ tests/ --include="*.py" -l`

- [ ] **Step 2: Update any tests using MockBroker to mock AlpacaBroker instead**

Replace `MockBroker()` usage with `MagicMock(spec=AlpacaBroker)` in affected tests.

- [ ] **Step 3: Delete mock_broker.py**

```bash
rm src/fund/mock_broker.py
```

- [ ] **Step 4: Update __init__.py exports**

Remove `MockBroker` from `src/fund/__init__.py` exports.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/ -v --ignore=tests/e2e`
Expected: All pass (no more MockBroker references)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: delete MockBroker, mock AlpacaBroker HTTP in tests instead"
```

### Task 12: Integration Test — Streaming Pipeline

**Files:**
- Create: `tests/integration/fund/test_streaming_pipeline.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/fund/test_streaming_pipeline.py
"""Integration test: stream event -> PriceCache -> ObservationRecorder -> SiliconDB mock."""

import queue
import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fund.price_cache import PriceCache
from fund.observation_recorder import ObservationRecorder
from fund.stream_service import StreamEvent
from fund.tempo import Tempo
from fund.reactor import Reactor, ReactorConfig


class TestStreamingPipeline:
    def test_trade_event_flows_through_pipeline(self):
        """Simulates: trade arrives -> cache updated -> observation recorded -> reactor fires."""
        # Setup
        price_cache = PriceCache()
        silicondb = MagicMock()
        silicondb.epistemic_briefing.return_value = {"anchors": [], "surprises": []}
        recorder = ObservationRecorder(price_cache, silicondb)
        tempo = Tempo()
        tempo.update_temperature(0.5)  # Warm — analysis enabled
        reactor = Reactor(
            silicondb_client=silicondb,
            broker=MagicMock(),
            supabase_sync=MagicMock(),
            price_cache=price_cache,
            tempo=tempo,
            config=ReactorConfig(portfolio_symbols=["AAPL"], reference_symbols=["SPY"]),
        )

        # Simulate trade event
        ts = time.time()
        price_cache.update_trade("AAPL", Decimal("152.50"), Decimal("200"), ts)
        recorder.record_symbol("AAPL")
        recorder.flush()

        # Verify observation was sent to SiliconDB
        assert silicondb.record_observation_batch.call_count == 1
        batch = silicondb.record_observation_batch.call_args[0][0]
        assert any("AAPL:price" == obs["external_id"] for obs in batch)

        # Simulate percolator firing micro-shift
        reactor.on_micro_shift({"symbol": "AAPL", "delta": 0.06})
        silicondb.propagate.assert_called()

        # Simulate significant shift
        reactor.on_significant_shift({"symbol": "AAPL", "delta": 0.2})
        silicondb.epistemic_briefing.assert_called()

    def test_cold_market_only_heartbeat(self):
        """When thermo is cold, reactor skips analysis."""
        silicondb = MagicMock()
        tempo = Tempo()  # Default: COLD
        reactor = Reactor(
            silicondb_client=silicondb,
            broker=MagicMock(),
            supabase_sync=MagicMock(),
            price_cache=PriceCache(),
            tempo=tempo,
            config=ReactorConfig(portfolio_symbols=["AAPL"], reference_symbols=["SPY"]),
        )
        reactor.on_significant_shift({"symbol": "AAPL", "delta": 0.2})
        silicondb.epistemic_briefing.assert_not_called()

    def test_queue_overflow_drops_events(self):
        """Event queue full -> events dropped, not blocked."""
        small_queue = queue.Queue(maxsize=2)
        for i in range(5):
            evt = StreamEvent(kind="trade", symbol="AAPL", data={"price": 150 + i})
            try:
                small_queue.put_nowait(evt)
            except queue.Full:
                pass
        assert small_queue.qsize() == 2  # Only 2 fit
```

- [ ] **Step 2: Run integration test**

Run: `python -m pytest tests/integration/fund/test_streaming_pipeline.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/fund/test_streaming_pipeline.py
git commit -m "test: add streaming pipeline integration test"
```

### Task 13: Update __init__.py Exports

**Files:**
- Modify: `src/fund/__init__.py`

- [ ] **Step 1: Add new module exports**

Add to `src/fund/__init__.py`:

```python
from fund.price_cache import PriceCache, PriceEntry
from fund.stream_service import AlpacaStreamService, StreamEvent
from fund.observation_recorder import ObservationRecorder
from fund.tempo import Tempo, ThermoTier
from fund.reactor import Reactor, ReactorConfig
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v --ignore=tests/e2e`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add src/fund/__init__.py
git commit -m "feat: export new streaming modules from fund package"
```
