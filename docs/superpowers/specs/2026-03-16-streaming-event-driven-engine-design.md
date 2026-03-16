# Streaming Event-Driven Trading Engine

**Date:** 2026-03-16
**Status:** Draft

## Overview

Replace the polling-based trading engine with a real-time, event-driven architecture. Alpaca websocket streams feed market data continuously into SiliconDB, whose percolator rules drive analysis and trading decisions. SiliconDB's thermodynamic state acts as an adaptive clock — the system thinks faster when the market is information-rich and slows down when it's quiet.

## Goals

- Real-time market data via Alpaca websockets (replace Yahoo Finance polling)
- Instant order fill notifications via Alpaca trading stream
- SiliconDB percolator as the decision orchestrator (not application code)
- Adaptive analysis tempo based on thermodynamic state
- Multi-scale observation with consensus-based trading
- Expanded ontology with macro proxies, temporal relationships, and volume signals
- Supabase sync on meaningful events (trades, strategy changes), not just periodic
- Configurable broker: Alpaca paper (default) / Alpaca live (future)
- Broker state hydrated from Supabase on startup

## Non-Goals

- Full async rewrite of the engine
- Backtesting parity with live engine (Nautilus-style)
- HFT-level latency optimization
- Custom MockBroker (use Alpaca paper + mocked HTTP for tests)

## Architecture

### Threading Model

The engine uses two threads:

**Async stream thread** — runs its own `asyncio.run()` event loop. Owns both Alpaca websocket connections. Stream callbacks (on_trade, on_quote, on_fill) run in this loop. They update `PriceCache` (thread-safe via `threading.Lock`) and post events to a bounded `queue.Queue(maxsize=1000)`.

**Main sync thread** — runs `ObservationRecorder` (reads from PriceCache, writes to SiliconDB), the `Reactor` (consumes events from the queue), the heartbeat timer, and all SiliconDB/Supabase/AlpacaBroker sync calls. This is the existing engine thread — it just reads from the queue instead of sleeping for 5 minutes.

**Bridge:** The stream thread never calls SiliconDB or AlpacaBroker directly. It writes to PriceCache and posts to the queue. The sync thread consumes from the queue and does all the work. This avoids async/sync mixing entirely.

**Backpressure:** If the queue is full (1000 events), the stream thread drops the oldest event and increments a `dropped_events` counter exposed in the health check. This prevents blocked calls from piling up when SiliconDB is slow.

### Core Principle: SiliconDB as the Clock

The engine has no fixed analysis interval. SiliconDB's thermodynamic state determines tempo:

| Thermo State | Temperature | Percolator Cooldown | Behavior |
|---|---|---|---|
| Cold | < 0.3 | N/A | Heartbeat only (5 min). No reactive analysis. |
| Warm | 0.3 - 0.6 | 30s | Percolator events trigger analysis. |
| Hot | 0.6 - 0.8 | 10s | Faster reaction, more aggressive briefings. |
| Critical | > 0.8 | 5s | Maximum alertness. Consider de-risking. |

Cooldowns are updated dynamically on the percolator rules via SiliconDB API.

### Multi-Scale Percolator Rules

Three tiers inspired by the Delta Engine's multi-threshold agents:

**Nervous (low threshold) — observation layer:**
- `belief-micro-shift`: fires on belief change > 0.05 (SiliconDB computes belief delta internally when a new observation updates a belief's probability; the percolator condition references this delta)
- Handler: propagate beliefs, record cooccurrences, update lead/lag
- No cooldown, does NOT trigger trading analysis
- Rate: up to 14 events/sec (one per symbol per 1s batch). SiliconDB percolator handles this throughput — the Nervous handler is lightweight (propagate + cooccurrence only).

**Standard (medium threshold) — analysis layer:**
- `belief-significant-shift`: fires on belief change > 0.15 or contradiction > 0.3
- `thermo-shift`: fires on temperature tier change
- Handler: request epistemic briefing, re-evaluate regime, update adaptive tempo
- Cooldown: adaptive (see tempo table)

**Strategic (high threshold) — trading layer:**
- `regime-change`: fires when regime classification shifts
- `critical-contradiction`: fires on contradiction score > 0.7
- Handler: run portfolio composer, execute trades, sync to Supabase
- Cooldown: 60s minimum

**Consensus requirement:** Trading only happens when a Strategic rule fires. Strategic rules depend on beliefs being well-propagated by Nervous and Standard tiers. The system builds conviction before acting.

### Event Flow

```
Alpaca trade stream
  -> record observation in SiliconDB
    -> [Nervous] belief-micro-shift
      -> propagate beliefs, record cooccurrences
        -> [Standard] thermo-shift (if tier changed)
          -> update adaptive tempo
          -> request epistemic briefing
            -> [Standard] belief-significant-shift (if beliefs diverge)
              -> re-evaluate regime
                -> [Strategic] regime-change (if regime shifted)
                  -> run portfolio composer
                  -> execute trades via Alpaca
                  -> sync to Supabase immediately

Alpaca order fill stream
  -> update positions + NAV
  -> record portfolio triples in SiliconDB
  -> sync to Supabase immediately

Heartbeat (5 min, always runs)
  -> snapshot beliefs
  -> sync full state to Supabase
  -> narrative synthesis (if any Standard+ events since last heartbeat)
  -> health check
```

### Streaming Layer

`AlpacaStreamService` manages two websocket connections in a dedicated async thread:

**Market Data Stream (`StockDataStream`):**
- Reference symbols (always): SPY, QQQ, IWM, DIA
- Macro proxies (always): TLT, USO, UUP, UVXY, GLD
- Portfolio symbols (configurable): AAPL, MSFT, NVDA, GOOG, AMZN
- Subscribes to trades + quotes
- Data feed: IEX (paper), SIP (live) — configurable

**Trading Stream (`TradingStream`):**
- Subscribes to order fill updates
- Paper mode connects to `paper-api.alpaca.markets`

**Stream handlers:**

On trade received:
1. Update PriceCache (price, size, timestamp, running VWAP, trade intensity)
2. Record SiliconDB observation (batched per symbol per 1s window)
3. If reference symbol: compute relative returns for portfolio stocks

On quote received:
1. Update PriceCache (bid, ask, spread)
2. Record observation only if spread changes >10% (avoid noise)

On order fill:
1. Update in-memory positions and NAV
2. Record portfolio triples in SiliconDB
3. Sync to Supabase immediately
4. Log to journal

### Reference Symbols

SPY, QQQ, IWM, DIA always stream regardless of portfolio composition. They provide the reference frame:

- Portfolio stock beliefs are contextualized against their index (relative returns)
- Regime detection uses index signals as primary input
- New ontology edge: `SYMBOL -> benchmarked_against -> INDEX`
- "NVDA -2% while QQQ -3%" is a relative strength signal, not bearish

## Ontology Changes

### New Observable Types Per Ticker

Added to existing 7 (price, volume, return, volatility, market_cap, momentum, rsi):
- `vwap` — volume-weighted average price from trade stream
- `spread` — bid-ask spread from quote stream
- `trade_intensity` — trades per minute
- `volume_anomaly` — current volume vs 20-day average

### Macro Proxies as First-Class Nodes

ETF proxies wired into the existing macro ontology:

| Macro Concept | ETF Proxy | Ontology Edge |
|---|---|---|
| interest_rates | TLT | `TLT -> proxy_for -> interest_rates` |
| oil_prices | USO | `USO -> proxy_for -> oil_prices` |
| usd_strength | UUP | `UUP -> proxy_for -> usd_strength` |
| market_fear | UVXY | `UVXY -> proxy_for -> market_fear` |
| gold_prices | GLD | `GLD -> proxy_for -> gold_prices` |
| sp500 | SPY | already exists |
| nasdaq100 | QQQ | already exists |
| small_cap | IWM | `IWM -> proxy_for -> russell2000` |

When TLT trade streams in, observation propagates: `TLT -> proxy_for -> interest_rates -> pressures -> technology`. Macro signals reach portfolio stocks through existing ontology edges.

### Temporal Relationships (Auto-Discovered)

New predicate types — NOT seeded, discovered by SiliconDB cooccurrence engine:
- `leads` — "NVDA price moves precede AMD moves"
- `co_moves_with` — symmetric correlation
- `inversely_correlated` — "TLT moves opposite SPY"

New percolator rule: `lead-lag-discovered` — fires when temporal relationship detected. Handler adds triple to ontology.

### Volume/Flow Layer

Dynamic triples added when volume anomalies detected:
- `SYMBOL:volume_anomaly -> signals -> unusual_activity`
- Handler increases uncertainty on that symbol's beliefs

New percolator rule: `volume-anomaly` — fires when trade_intensity exceeds 2x 20-day average.

### Volume Anomaly Bootstrap

On startup, `ObservationRecorder` fetches 20 trading days of historical volume data from Alpaca's bars API (`GET /v2/stocks/{symbol}/bars`) for all streamed symbols. This establishes the baseline for anomaly detection. Until the baseline is loaded, volume anomaly detection is disabled (the percolator rule is registered but the threshold is set to infinity). The existing `fetch_historical_data` method in `live_engine.py` is replaced by this mechanism.

### Ontology Summary

| Layer | Current | Adding |
|---|---|---|
| Observables per ticker | 7 | +4 (vwap, spread, trade_intensity, volume_anomaly) |
| Macro observation | Not streamed | 8 ETF proxies with proxy_for edges |
| Temporal | None | leads, co_moves_with, inversely_correlated (auto) |
| Volume signals | None | volume-anomaly percolator rule |
| Reference framing | None | benchmarked_against edges |
| New percolator rules | — | +2 (lead-lag-discovered, volume-anomaly) |

## Broker Integration

### Modes

```
BROKER_MODE=paper  -> AlpacaBroker(paper=True)   # Alpaca paper environment
BROKER_MODE=live   -> AlpacaBroker(paper=False)   # Real money (future)
```

No custom MockBroker. Alpaca paper IS the simulation. MockBroker deleted. Unit tests mock Alpaca HTTP responses directly.

### Startup Sequence

1. Connect to Supabase -> load fund state (members, NAV, units, pending transactions)
2. Connect to Alpaca paper -> get account + positions
3. Reconcile positions:
   - Alpaca is truth for positions and cash (it's the actual broker)
   - Supabase is truth for members, units, and fund accounting
   - If Alpaca has positions not in Supabase: log warning, add to Supabase, alert admin
   - If Supabase has positions not in Alpaca: log error, mark as stale in Supabase, alert admin
   - Engine starts regardless — reconciliation issues are logged, not blocking
4. Load ontology into SiliconDB
5. Register percolator rules (all three tiers)
6. Wire event handlers
7. Start Alpaca streams
8. Start percolator event subscription
9. Start heartbeat timer

### Configuration

```env
# Broker
BROKER_MODE=paper
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_DATA_FEED=iex

# Symbols
PORTFOLIO_SYMBOLS=AAPL,MSFT,NVDA,GOOG,AMZN
REFERENCE_SYMBOLS=SPY,QQQ,IWM,DIA
MACRO_PROXIES=TLT,USO,UUP,UVXY,GLD

# Engine
SILICONDB_URL=http://127.0.0.1:8642
HEARTBEAT_INTERVAL=300
THERMO_COLD=0.3
THERMO_WARM=0.6
THERMO_HOT=0.8

# Supabase
NEXT_PUBLIC_SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

## Module Structure

### New Files

```
src/fund/
  stream_service.py        # AlpacaStreamService — manages both websockets
  price_cache.py           # Thread-safe price/volume/VWAP cache
  observation_recorder.py  # Translates stream events -> SiliconDB observations
  tempo.py                 # Adaptive tempo — reads thermo, sets cooldowns
  reactor.py               # Event handlers for each percolator rule tier
```

### Modified Files

```
src/fund/
  live_engine.py           # Stripped to wiring only: startup, heartbeat, connections
  ontology.py              # Macro proxies, temporal predicates, volume layer, benchmarks
  run_server.py            # New startup: hydrate from Supabase, connect streams
  broker_types.py          # Add StreamConfig dataclass
```

### Deleted Files

```
src/fund/
  mock_broker.py           # Replaced by mocking Alpaca HTTP in tests
```

### Module Responsibilities

**stream_service.py** — Owns the async thread. Starts/stops StockDataStream + TradingStream. Routes raw events to observation_recorder and price_cache. No business logic.

**price_cache.py** — Thread-safe dict. Updated by stream handlers, read by engine and observation recorder. Computes running VWAP, trade intensity, spread, relative returns vs reference symbols.

**observation_recorder.py** — Translates price cache updates into SiliconDB observations. Batches per symbol per 1s window. Computes volume anomaly detection (current vs 20-day average).

**tempo.py** — Subscribes to thermo-shift events. Maps temperature to cooldown values. Updates percolator rule cooldowns dynamically via SiliconDB API.

**reactor.py** — One handler per percolator rule tier (percolator-driven only):
- `on_micro_shift()` — propagate beliefs, cooccurrences
- `on_significant_shift()` — epistemic briefing, regime check
- `on_regime_change()` — portfolio composer, trade execution, Supabase sync
- `on_volume_anomaly()` — increase uncertainty for symbol
- `on_lead_lag_discovered()` — add temporal triple to ontology

**stream_service.py** — also handles order fills directly (stream-driven, not percolator):
- `on_order_fill()` — update positions, record portfolio triples in SiliconDB, sync Supabase

**live_engine.py** — Wiring layer only. Startup: hydrate from Supabase -> connect Alpaca -> load ontology -> register percolator rules -> wire handlers -> start streams -> start heartbeat.

### Dependency Flow

```
run_server.py
  -> LiveEngine (wiring)
       |- AlpacaBroker (REST for orders)
       |- AlpacaStreamService
       |    |- PriceCache
       |    '- ObservationRecorder -> SiliconDB
       |- Reactor
       |    |- reads PriceCache
       |    |- calls SiliconDB (briefing, propagation, regime)
       |    |- calls AlpacaBroker (trade execution)
       |    '- calls SupabaseSync
       |- Tempo -> SiliconDB (thermo state)
       '- SupabaseSync -> Supabase
```

## Testing Strategy

**Unit tests:** Mock Alpaca HTTP responses (using `responses` or `respx`). Test each reactor handler in isolation. Test observation batching logic. Test tempo thresholds.

**Integration tests:** Hit Alpaca paper API. Verify stream connection, order submission, fill reception. Verify SiliconDB observation flow end-to-end.

**Key test scenarios:**
- Cold market: only heartbeats fire, no reactive analysis
- Hot market: rapid percolator events, debouncing works correctly
- Regime change: full cascade from observation to trade execution
- Volume anomaly: uncertainty increases, beliefs adjust
- Startup reconciliation: Supabase + Alpaca state merge correctly
- Stream disconnect/reconnect: engine degrades gracefully
- Percolator cascade ordering: Nervous completes before Standard fires
- Concurrent Strategic events: portfolio composer has a lock, second event waits
- SiliconDB goes down mid-operation: reactor handlers timeout after 5s, skip, log error

## Stream Disconnect & Degraded Mode

**Alpaca stream disconnects:** alpaca-py reconnects automatically with exponential backoff. During disconnection:
- PriceCache entries gain a `stale_since` timestamp
- ObservationRecorder skips observations for stale symbols (>30s old)
- Reactor continues processing percolator events from pre-disconnect beliefs
- Heartbeat health check reports stream status (connected/reconnecting/disconnected)

**SiliconDB unavailable:** SiliconDB is a hard dependency for reactive analysis but NOT for basic operation. If SiliconDB is down:
- ObservationRecorder queues observations (bounded, drops oldest on overflow)
- Reactor handlers timeout after 5s and skip (no analysis, no trades)
- Heartbeat still runs (syncs positions/NAV to Supabase from PriceCache)
- Engine logs errors, health check reports degraded state

**Market hours:** The stream goes quiet outside market hours (no trades = no events = Cold state). No explicit session awareness needed — the thermo-adaptive tempo handles this naturally. Pre-market/after-hours trades on IEX are sparse and will keep the engine in Cold/Warm state. The heartbeat always runs regardless of market hours.

## Dynamic Symbol Subscription

When the portfolio composer decides to enter a new symbol:
1. AlpacaBroker executes the trade
2. On fill confirmation, `stream_service.subscribe_trades(new_symbol)` is called
3. ObservationRecorder fetches 20-day volume baseline for the new symbol
4. New ontology triples are inserted (benchmarked_against, observables)

When a symbol is fully exited:
1. Stream subscription is kept for 24h (to observe post-exit behavior)
2. After 24h with zero position, unsubscribe and remove from PriceCache

## SiliconDBBeliefBridge Migration

The existing `SiliconDBBeliefBridge` class (live_engine.py, ~400 lines) is decomposed:
- Ontology loading -> stays in `ontology.py` (already there, minor additions)
- `record_price_observations()` -> `observation_recorder.py`
- `propagate_beliefs()`, `detect_anomalies()`, `get_uncertain()` -> `reactor.py` handlers
- `epistemic_briefing()` -> `reactor.py` `on_significant_shift()`
- `thermo_state()` -> `tempo.py`
- Percolator setup -> `live_engine.py` startup wiring
- SSE event listener -> replaced by queue-based event consumption

## Dependencies on SiliconDB

This design requires the following SiliconDB issues to be resolved:

- **#293** — Epistemic briefing HTTP endpoint (Standard tier handler)
- **#294** — Thermo state HTTP endpoint (Tempo module)
- **#295** — Sync event methods in HTTP client (percolator subscription)
- **#297** — gRPC parity for above (optional, HTTP sufficient for v1)

The design can proceed with HTTP-only transport initially. gRPC optimization is a future enhancement.

## Future: Theme Discovery (Phase 2)

Once `enableThemeDiscovery` is available in SiliconDB, the ontology can evolve dynamically. SiliconDB surfaces emergent themes ("AI infrastructure rally", "rate-sensitive selloff") from the belief graph. These become new percolator rules and ontology nodes without code changes. This is explicitly deferred to a second phase after the streaming architecture is stable.
