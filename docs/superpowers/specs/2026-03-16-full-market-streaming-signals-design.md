# Full Market Streaming + Signal Detection

**Date:** 2026-03-16
**Status:** Draft

## Overview

Expand streaming from 17 symbols to ~610 (full S&P 500 + NASDAQ 100 + crypto + macro proxies). All trades observed in SiliconDB. Quotes aggregated per 1s window. A new SignalTracker uses SiliconDB's belief graph properties (entropy, propagation reach, node thermo) to surface high-conviction symbols the portfolio doesn't hold. Watch + Signal only — no auto-trading of new symbols.

## Goals

- Stream all S&P 500 + NASDAQ 100 symbols (~600 stocks) plus existing crypto and macro proxies
- Every trade → SiliconDB observation (real price discovery events)
- Quotes aggregated per symbol per 1s window → single spread observation per window
- Signal detection via belief graph dynamics, not hardcoded thresholds
- Ranked candidate list synced to Supabase for dashboard visibility
- Existing portfolio trading unchanged

## Non-Goals

- Auto-trading new signal symbols (Scout/Scale/Decay — future)
- Adversarial portfolio (depends on this, separate issue #2)
- Meta-beliefs (depends on this, separate issue #3)
- Theme-level allocation (future, after theme discovery matures)

## Design

### Expanded Streaming

**Current:** 14 stocks + 3 crypto = 17 symbols.
**New:** ~600 stocks + 3 crypto + 8 macro proxies = ~610 symbols.

**Symbol source:** `ontology.fetch_index_compositions()` already fetches S&P 500 + NASDAQ 100 tickers from Wikipedia (cached daily). We pass this full list to StreamConfig instead of just the 5 portfolio symbols.

**Observation rules:**
- Trades (all symbols): every trade → `record_symbol()` → SiliconDB observation on flush
- Quotes (all symbols): aggregate per symbol per 1s batch window. Store latest bid/ask and mean spread in PriceCache. Flush as single `SYMBOL:spread` observation per window — not one per quote tick.

**Queue sizing:** Increase from 1,000 to 10,000. Drop-oldest-on-overflow behavior unchanged. 600 symbols during peak market could produce 5,000-10,000 events/sec.

**Observation batching:** Current 1s batch window stays. With 600 symbols, a single flush could contain 600-2000 observations. SiliconDB's `record_observation_batch` handles this.

### Quote Aggregation

New class `QuoteAggregator` in `observation_recorder.py`:

Per symbol, per 1s window, tracks:
- Latest bid, latest ask
- Min spread, max spread, mean spread over window
- Quote count in window

On flush: emits one `SYMBOL:spread` observation with mean spread as value. This replaces the current behavior where every quote triggers a spread observation.

### Signal Detection via Belief Graph

Instead of hardcoded thresholds, use SiliconDB's own metrics:

**Watch** — default state for all ~600 symbols. SiliconDB accumulates beliefs from trade observations. No action.

**Signal** — a symbol graduates when any of these SiliconDB-native signals fire:

1. **Entropy drop** — symbol's belief entropy decreases significantly. Queried via `get_uncertain_beliefs()` — symbols that leave the uncertain list have collapsing uncertainty (market making up its mind).

2. **Propagation reach** — symbol's belief propagated through the ontology and affected 3+ related symbols in the same direction. Tracked via cooccurrence engine.

3. **Thermo contribution** — symbol's `node_thermo()` shows it contributing to network temperature. Hot nodes = market attention.

**Signal ranking:**
```
signal_strength = (1 - entropy) * propagation_reach * node_temperature
```

Surfaces symbols where: market has high conviction, signal propagated through related stocks, and belief is thermodynamically active.

**Signal decay** — symbol drops from Signal when entropy rises above uncertain threshold. No arbitrary cycle counts.

### SignalTracker Module

New file: `src/fund/signal_tracker.py`

```python
class SignalTracker:
    def __init__(self, silicondb_client, portfolio_symbols):
        ...

    def update(self, all_symbols: list) -> list:
        """Query SiliconDB for entropy, propagation, node_thermo.
        Returns list of new signals detected this cycle."""

    def get_signals(self) -> list:
        """Ranked list of active signal symbols by signal_strength."""

    def get_signal_history(self, symbol: str) -> list:
        """Conviction trajectory for a symbol over time."""

    def get_decayed(self) -> list:
        """Symbols that dropped from Signal back to Watch."""
```

Called in the percolator loop's `_run_analysis_cycle()` when `should_analyze` is True.

### Database

New Supabase table `signals`:

| Column | Type | Description |
|---|---|---|
| id | cuid | Primary key |
| symbol | string | Ticker |
| signal_strength | float | Composite score |
| entropy | float | Belief entropy |
| propagation_reach | int | Number of related symbols affected |
| node_temperature | float | Thermo contribution |
| belief_type | string | high_growth / stable / declining |
| conviction | float | Raw belief conviction |
| first_seen | datetime | When signal first detected |
| last_seen | datetime | Last cycle signal was active |
| status | string | active / decayed |

New Prisma model in `web/prisma/schema.prisma`. Synced from engine via `SupabaseSync.push_signals()`.

## Module Changes

### Modified Files

| File | Change |
|---|---|
| `src/fund/stream_service.py` | Accept full ticker list, subscribe all to StockDataStream |
| `src/fund/observation_recorder.py` | Add QuoteAggregator, aggregate quotes per 1s window |
| `src/fund/live_engine.py` | Queue size 10k, integrate SignalTracker in analysis cycle, log signals |
| `src/fund/run_server.py` | Load full ticker list from ontology, pass to StreamConfig |
| `src/fund/supabase_sync.py` | Add push_signals() method |
| `src/fund/broker_types.py` | StreamConfig accepts full ticker list (all_tracked_symbols property) |
| `web/prisma/schema.prisma` | Add Signal model |

### New Files

| File | Purpose |
|---|---|
| `src/fund/signal_tracker.py` | Belief graph signal detection and ranking |
| `tests/unit/fund/test_signal_tracker.py` | SignalTracker tests |
| `tests/unit/fund/test_quote_aggregator.py` | QuoteAggregator tests |

## Console Output

New event type for signals:
```
[SIGNAL] AMD    strength=0.82 entropy=0.15 propagation=5 thermo=0.7 (high_growth)
[SIGNAL] TSLA   strength=0.71 entropy=0.22 propagation=3 thermo=0.6 (declining)
[DECAY]  INTC   signal decayed — entropy rose to 0.65
```

## Testing

- Unit tests for SignalTracker with mocked SiliconDB (entropy, node_thermo, uncertain_beliefs)
- Unit tests for QuoteAggregator (windowing, mean spread, flush behavior)
- Integration test: stream 10 symbols → build beliefs → detect signal
- Verify queue handles 10k events without dropping excessively
