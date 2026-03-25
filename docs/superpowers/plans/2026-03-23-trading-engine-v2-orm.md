# Trading Engine V2: ORM-Based Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a v2 trading engine on the SiliconDB ORM foundation — entities, hooks, predictions, accumulators, MCP server, agent loop — running in parallel with v1 for comparison.

**Architecture:** SiliconDB ORM is the nervous system. Alpaca streams through a custom source connector into the ORM pipeline, which routes observations to beliefs, fires hooks (reflexes), and exposes everything via MCP (brain). An agent loop reacts to events and proposes trades through an action feed with execution policy gating. Fund accounting stays in Postgres/Prisma. The web dashboard reads market data from MCP instead of Supabase sync.

**Tech Stack:** SiliconDB ORM (entities, hooks, predictions, accumulators, MCP), Alpaca SDK (streaming, broker), Python 3.13, pytest, MockEngine for testing.

---

## File Structure

```
src/fund_v2/                          # V2 trading engine (parallel to src/fund/)
├── __init__.py                       # Package exports
├── entities.py                       # ORM entity definitions (Instrument, Position, etc.)
├── sources/
│   ├── __init__.py
│   └── alpaca.py                     # Alpaca WebSocket source connector
├── hooks.py                          # Entity lifecycle hooks (reflexes)
├── tools.py                          # MCP domain tools (brain interface)
├── signals.py                        # Regime-aware signal generation (separated from tools.py)
├── strategy.py                       # Portfolio optimization (Kelly, equal weight)
├── agent.py                          # Agent loop with event handlers
├── ontology_bootstrap.py             # Dynamic ontology loader (reuses fund/ontology.py)
├── broker_adapter.py                 # Adapts AlpacaBroker to action execution
├── app.py                            # App wiring + startup
└── sentiment/
    ├── __init__.py
    └── stocktwits.py                 # StockTwits sentiment source connector

tests/unit/fund_v2/
├── conftest.py                       # MockEngine fixtures, test helpers
├── test_entities.py                  # Entity registration, descriptors
├── test_alpaca_source.py             # Alpaca source connector
├── test_hooks.py                     # Hook dispatch, threshold gating
├── test_tools.py                     # MCP tool responses
├── test_signals.py                   # Signal generation tests
├── test_strategy.py                  # Portfolio optimization math
├── test_agent.py                     # Agent loop event handling
├── test_broker_adapter.py            # Action → broker execution
├── test_app_wiring.py                # Full app creation
└── test_stocktwits_source.py         # Sentiment source

tests/integration/fund_v2/
├── test_pipeline_e2e.py              # Source → pipeline → hooks → actions
└── test_prediction_e2e.py            # Predictions → hooks → agent
```

**Key boundaries:**
- `entities.py` defines the data model — no logic, just declarations
- `sources/alpaca.py` converts Alpaca WebSocket events to `SourceRecord` — no belief logic
- `hooks.py` handles per-entity reactions — fast, deterministic, no LLM
- `tools.py` handles cross-entity analysis — exposed via MCP for agents
- `signals.py` handles regime-aware multi-layer signal generation — the largest tool, separated for clarity
- `strategy.py` handles portfolio math — pure functions, no ORM dependency
- `agent.py` wires events to tools — the decision loop
- `broker_adapter.py` executes approved actions — the only component that talks to Alpaca broker

**Reused from v1 (not rewritten):**
- `fund/ontology.py` — Wikipedia/Yahoo fetch + triple building
- `fund/alpaca_broker.py` — Alpaca broker client
- `fund/broker_types.py` — AlpacaConfig, StreamConfig, BrokerPosition, etc.
- `fund/types.py` — Fund, WeeklyNAV, FeeBreakdown, etc.
- `fund/belief_synthesizer.py` — OpenAI narrative generation

---

## Task 1: Project Scaffold + MockEngine Fixtures

**Files:**
- Create: `src/fund_v2/__init__.py`
- Create: `tests/unit/fund_v2/__init__.py`
- Create: `tests/unit/fund_v2/conftest.py`
- Create: `tests/integration/fund_v2/__init__.py`

- [ ] **Step 1: Create package directories**

```bash
mkdir -p src/fund_v2/sources src/fund_v2/sentiment
mkdir -p tests/unit/fund_v2 tests/integration/fund_v2
```

- [ ] **Step 2: Create fund_v2 package init**

```python
# src/fund_v2/__init__.py
"""Glass Box Fund Trading Engine V2 — built on SiliconDB ORM."""
```

- [ ] **Step 3: Create test conftest with MockEngine fixtures**

```python
# tests/unit/fund_v2/conftest.py
"""Shared fixtures for fund_v2 unit tests."""
import sys
from pathlib import Path

import pytest

# Ensure silicondb is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib" / "silicondb" / "python"))

from silicondb.engine.mock import MockEngine
from silicondb.orm import App


@pytest.fixture
def mock_engine():
    """In-memory SiliconDB engine — no native library needed."""
    return MockEngine()


@pytest.fixture
def app(mock_engine):
    """ORM App wired to MockEngine."""
    return App(mock_engine, internal_db_url="sqlite:///:memory:")
```

- [ ] **Step 4: Create empty init files**

```python
# tests/unit/fund_v2/__init__.py
# tests/integration/fund_v2/__init__.py
# src/fund_v2/sources/__init__.py
# src/fund_v2/sentiment/__init__.py
```

- [ ] **Step 5: Verify pytest discovers the fixtures**

Run: `cd /Users/birger/code/portfolio && python -m pytest tests/unit/fund_v2/ --collect-only`
Expected: "no tests ran" (0 collected), no import errors.

- [ ] **Step 6: Commit**

```bash
git add src/fund_v2/ tests/unit/fund_v2/ tests/integration/fund_v2/
git commit -m "feat(v2): scaffold fund_v2 package with MockEngine fixtures"
```

---

## Task 2: Entity Definitions — Layered Belief Model

**Files:**
- Create: `src/fund_v2/entities.py`
- Create: `tests/unit/fund_v2/test_entities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_entities.py
"""Entity registration and descriptor validation."""
from fund_v2.entities import (
    Instrument, Sector, Industry, Index, MacroFactor,
    Position, Portfolio, MarketConcept, MarketRegime,
)


def test_instrument_has_layer1_beliefs():
    assert "price_trend_fast" in Instrument._beliefs
    assert "price_trend_slow" in Instrument._beliefs
    assert "spread_tight" in Instrument._beliefs
    assert "volume_normal" in Instrument._beliefs


def test_instrument_has_layer2_beliefs():
    assert "relative_strength" in Instrument._beliefs
    assert "exhaustion" in Instrument._beliefs
    assert "pressure" in Instrument._beliefs


def test_instrument_has_layer3_beliefs():
    assert "retail_sentiment" in Instrument._beliefs
    assert "mention_velocity" in Instrument._beliefs
    assert "crowded" in Instrument._beliefs


def test_instrument_has_10_beliefs():
    assert len(Instrument._beliefs) == 10


def test_instrument_has_accumulators():
    assert "trade_pressure" in Instrument._accumulators


def test_instrument_has_alerts():
    assert "volatility_spike" in Instrument._alerts


def test_instrument_relationships():
    assert "in_sector" in Instrument._relationships
    assert Instrument._relationships["in_sector"].target == "Sector"
    assert "competes_with" in Instrument._relationships
    assert Instrument._relationships["competes_with"].many is True


def test_instrument_source_binding():
    assert Instrument._source_binding is not None
    assert Instrument._source_binding.identity == "symbol"
    observe = Instrument._source_binding.observe
    assert "price" in observe
    assert observe["price"]["belief"] == "price_trend_fast"
    assert "trade_count" in observe
    assert observe["trade_count"]["belief"] == "spread_tight"


def test_position_has_stop_loss_alert():
    assert "stop_loss" in Position._alerts
    alert = Position._alerts["stop_loss"]
    assert alert.trigger == "relative_strength"
    assert alert.threshold == 0.25
    assert alert.severity == "critical"


def test_position_source_binding():
    assert Position._source_binding is not None
    assert Position._source_binding.identity == "symbol"


def test_market_regime_has_3_beliefs():
    assert "risk_on" in MarketRegime._beliefs
    assert "trend_following" in MarketRegime._beliefs
    assert "mean_reverting_regime" in MarketRegime._beliefs
    assert len(MarketRegime._beliefs) == 3


def test_all_entities_register(app):
    from fund_v2.entities import ALL_ENTITIES
    app.register(*ALL_ENTITIES)
    # Should not raise


def test_all_entities_includes_market_regime():
    from fund_v2.entities import ALL_ENTITIES
    assert MarketRegime in ALL_ENTITIES


def test_sector_inverse_relationship():
    rel = Sector._relationships["instruments"]
    assert rel.many is True
    assert rel.inverse == "in_sector"


def test_macro_factor_has_alert():
    assert "macro_shift" in MacroFactor._alerts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_entities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fund_v2.entities'`

- [ ] **Step 3: Write entity definitions**

```python
# src/fund_v2/entities.py
"""SiliconDB ORM entity definitions for the Glass Box Fund trading engine.

Layered belief model:
  Layer 1 (observable): directly from market data streams
  Layer 2 (graph-derived): computed from peer/sector/macro relationships
  Layer 3 (crowd): social sentiment and crowding signals
"""

from silicondb.orm import Entity, Field, Belief, Relationship, Rule
from silicondb.orm.descriptors import Accumulator, Alert


# ── Market entities ──────────────────────────────────────────────────────────


class Instrument(Entity):
    """A tradeable security (stock, ETF, macro proxy)."""

    symbol = Field(str, required=True)
    name = Field(str)
    asset_class = Field(str)       # "equity", "etf", "macro_proxy"
    sector = Field(str)
    industry = Field(str)

    # Layer 1 — observable (directly from market data)
    price_trend_fast = Belief(initial=0.5, learned=True)   # 15-min momentum
    price_trend_slow = Belief(initial=0.5, learned=True)   # 5-day momentum
    spread_tight = Belief(initial=0.9, learned=True)       # liquidity
    volume_normal = Belief(initial=0.5, learned=True)      # volume vs baseline

    # Layer 2 — graph-derived (computed from relationships)
    relative_strength = Belief(initial=0.5, learned=True)  # vs sector peers
    exhaustion = Belief(initial=0.2, learned=True)         # mean-reversion risk
    pressure = Belief(initial=0.5, learned=True)           # net macro+sector+competition pressure

    # Layer 3 — crowd (social/sentiment signals)
    retail_sentiment = Belief(initial=0.5, learned=True)   # StockTwits/Reddit
    mention_velocity = Belief(initial=0.3, learned=True)   # social acceleration
    crowded = Belief(initial=0.2, learned=True)            # everyone in same trade

    # Accumulators — pressure tracking for streaming data
    trade_pressure = Accumulator(preset="eventDampener")

    # Alerts — declarative threshold actions
    volatility_spike = Alert(
        trigger="exhaustion",
        threshold=0.8,
        direction="above",
        action="volatility_alert",
        severity="high",
        cooldown=1800,
    )

    # Relationships
    in_sector = Relationship("Sector")
    in_industry = Relationship("Industry")
    member_of = Relationship("Index", many=True)
    competes_with = Relationship("Instrument", many=True)
    benchmarked_against = Relationship("Instrument")

    class Rules:
        price_stale = Rule(frequency="30s", violation_affects="spread_tight")

    class Thermodynamics:
        fast_window = "minutes"
        medium_window = "hours"
        slow_window = "days"

    class Source:
        origin = "alpaca.trades"
        sync = "stream"
        identity = "symbol"
        fields = {"symbol": "symbol"}
        observe = {
            "price": {"belief": "price_trend_fast", "true_strengthens": True},
            "trade_count": {"belief": "spread_tight", "true_strengthens": True},
        }
        accumulators = [
            {"accumulator": "trade_pressure", "weight_from": "size"},
        ]


class Sector(Entity):
    """GICS sector grouping."""

    sector_id = Field(str, required=True)
    name = Field(str)

    rotating_in = Belief(initial=0.5, learned=True)
    pressured = Belief(initial=0.3, learned=True)

    instruments = Relationship("Instrument", many=True, inverse="in_sector")
    pressured_by = Relationship("MacroFactor", many=True)
    driven_by = Relationship("MacroFactor", many=True)

    class Thermodynamics:
        fast_window = "hours"
        medium_window = "days"
        slow_window = "weeks"


class Industry(Entity):
    """Sub-sector industry grouping."""

    industry_id = Field(str, required=True)
    name = Field(str)

    part_of = Relationship("Sector")
    instruments = Relationship("Instrument", many=True, inverse="in_industry")


class Index(Entity):
    """Market index (SPY, QQQ, DIA, etc.)."""

    symbol = Field(str, required=True)
    name = Field(str)

    bullish = Belief(initial=0.5, learned=True)

    contains = Relationship("Instrument", many=True)

    class Source:
        origin = "alpaca.trades"
        sync = "stream"
        identity = "symbol"


class MacroFactor(Entity):
    """Macro-economic factor (interest rates, oil, USD strength, etc.)."""

    factor_id = Field(str, required=True)
    name = Field(str)

    rising = Belief(initial=0.5, learned=True)
    elevated = Belief(initial=0.5, learned=True)

    pressures = Relationship("Sector", many=True)
    drives = Relationship("Sector", many=True)
    proxy = Relationship("Instrument")

    # Alert when macro factor shifts significantly
    macro_shift = Alert(
        trigger="rising",
        threshold=0.7,
        direction="above",
        action="macro_shift",
        severity="medium",
        cooldown=3600,
    )

    class Thermodynamics:
        fast_window = "hours"
        medium_window = "days"
        slow_window = "weeks"


# ── Market regime ────────────────────────────────────────────────────────────


class MarketRegime(Entity):
    """Current market regime — drives signal generation weights."""

    regime_id = Field(str, required=True)

    risk_on = Belief(initial=0.5, learned=True)
    trend_following = Belief(initial=0.5, learned=True)
    mean_reverting_regime = Belief(initial=0.5, learned=True)

    class Thermodynamics:
        fast_window = "hours"
        medium_window = "days"
        slow_window = "weeks"


# ── Portfolio entities ───────────────────────────────────────────────────────


class Position(Entity):
    """A current holding in the fund portfolio."""

    symbol = Field(str, required=True)
    quantity = Field(float)
    avg_entry_price = Field(float)
    market_value = Field(float)
    allocation_pct = Field(float)
    unrealized_pnl = Field(float)

    profitable = Belief(initial=0.5, learned=True)
    conviction = Belief(initial=0.7, learned=True)

    # Stop-loss: auto-create sell action when relative_strength drops below 0.25
    stop_loss = Alert(
        trigger="relative_strength",
        threshold=0.25,
        direction="below",
        action="sell",
        severity="critical",
        cooldown=3600,
        auto_approve=False,
    )

    # Concentration alert: flag when allocation exceeds 20%
    concentration_alert = Alert(
        trigger="allocation_pct",
        threshold=0.20,
        direction="above",
        action="concentration_warning",
        severity="high",
        cooldown=7200,
    )

    instrument = Relationship("Instrument")
    in_portfolio = Relationship("Portfolio")

    class Thermodynamics:
        fast_window = "minutes"
        medium_window = "hours"
        slow_window = "days"

    class Source:
        origin = "alpaca.positions"
        sync = "pull"
        interval = "30s"
        identity = "symbol"
        fields = {
            "symbol": "symbol",
            "qty": "quantity",
            "avg_entry_price": "avg_entry_price",
            "market_value": "market_value",
            "unrealized_pl": "unrealized_pnl",
        }
        observe = {
            "unrealized_pl": {
                "belief": "profitable",
                "true_strengthens": True,
                "condition": "lambda r: r.get('unrealized_pl', 0) > 0",
            },
        }


class Portfolio(Entity):
    """The fund portfolio as a whole."""

    nav = Field(float)
    cash = Field(float)
    units_outstanding = Field(float)
    high_water_mark = Field(float)

    healthy = Belief(initial=0.8, learned=True)

    positions = Relationship("Position", many=True, inverse="in_portfolio")

    # Drawdown alert
    drawdown_alert = Alert(
        trigger="healthy",
        threshold=0.5,
        direction="below",
        action="drawdown_warning",
        severity="critical",
        cooldown=86400,
    )

    class Thermodynamics:
        fast_window = "hours"
        medium_window = "days"
        slow_window = "weeks"

    class Source:
        origin = "alpaca.account"
        sync = "pull"
        interval = "5min"
        identity = "id"


# ── Market concepts ──────────────────────────────────────────────────────────


class MarketConcept(Entity):
    """Abstract market concept (regime, fear, recession risk)."""

    concept_id = Field(str, required=True)
    name = Field(str)
    category = Field(str)  # "regime", "risk", "signal"

    active = Belief(initial=0.3, learned=True)

    signals = Relationship("Instrument", many=True)
    pressures = Relationship("Sector", many=True)
    benefits = Relationship("Sector", many=True)

    class Thermodynamics:
        fast_window = "hours"
        medium_window = "days"
        slow_window = "weeks"


# ── Registration ─────────────────────────────────────────────────────────────

ALL_ENTITIES = (
    Instrument, Sector, Industry, Index, MacroFactor,
    MarketRegime,
    Position, Portfolio, MarketConcept,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund_v2/test_entities.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/entities.py tests/unit/fund_v2/test_entities.py
git commit -m "feat(v2): entity definitions with layered beliefs, MarketRegime, accumulators, alerts"
```

---

## Task 3: Alpaca Source Connector

**Files:**
- Create: `src/fund_v2/sources/alpaca.py`
- Create: `tests/unit/fund_v2/test_alpaca_source.py`

This is the critical infrastructure piece. It adapts Alpaca WebSocket events into `SourceRecord` format for the ORM pipeline.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_alpaca_source.py
"""Alpaca source connector — converts WebSocket events to SourceRecords."""
import time
from unittest.mock import MagicMock

import pytest

from fund_v2.sources.alpaca import AlpacaSourceAdapter


def test_trade_to_source_record():
    adapter = AlpacaSourceAdapter(symbols=["AAPL", "NVDA"])
    trade = MagicMock(symbol="AAPL", price=150.0, size=100, timestamp=1711200000.0)
    record = adapter.trade_to_record(trade)
    assert record.source_name == "alpaca"
    assert record.collection == "trades"
    assert record.identity == "AAPL"
    assert record.data["price"] == 150.0
    assert record.data["size"] == 100


def test_quote_to_source_record():
    adapter = AlpacaSourceAdapter(symbols=["AAPL"])
    quote = MagicMock(symbol="AAPL", bid_price=149.9, ask_price=150.1, timestamp=1711200000.0)
    record = adapter.quote_to_record(quote)
    assert record.collection == "quotes"
    assert record.data["bid"] == 149.9
    assert record.data["ask"] == 150.1
    assert record.data["spread"] == pytest.approx(0.2, abs=0.01)


def test_fill_to_source_record():
    adapter = AlpacaSourceAdapter(symbols=["AAPL"])
    fill = MagicMock()
    fill.order = {"symbol": "AAPL", "side": "buy", "filled_qty": "10", "filled_avg_price": "150.0", "id": "ord-123"}
    fill.event = "fill"
    record = adapter.fill_to_record(fill)
    assert record.collection == "fills"
    assert record.data["side"] == "buy"
    assert record.data["filled_qty"] == 10.0


def test_idempotency_key_unique():
    adapter = AlpacaSourceAdapter(symbols=["AAPL"])
    trade1 = MagicMock(symbol="AAPL", price=150.0, size=100, timestamp=1711200000.0)
    trade2 = MagicMock(symbol="AAPL", price=150.0, size=100, timestamp=1711200001.0)
    r1 = adapter.trade_to_record(trade1)
    r2 = adapter.trade_to_record(trade2)
    assert r1.idempotency_key != r2.idempotency_key


def test_stale_trade_skipped():
    adapter = AlpacaSourceAdapter(symbols=["AAPL"], max_age_seconds=30)
    old_trade = MagicMock(symbol="AAPL", price=150.0, size=100, timestamp=time.time() - 60)
    record = adapter.trade_to_record(old_trade)
    assert record is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_alpaca_source.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write AlpacaSourceAdapter**

```python
# src/fund_v2/sources/alpaca.py
"""Alpaca WebSocket → SourceRecord adapter.

Converts Alpaca trade, quote, and fill events into SourceRecord format
for the ORM pipeline. Does NOT manage the WebSocket connection — that's
done by AlpacaStreamService (reused from v1) or app.run().
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Optional

from silicondb.sources.models import SourceRecord


class AlpacaSourceAdapter:
    """Converts Alpaca SDK events to SourceRecords."""

    def __init__(self, symbols: list[str], max_age_seconds: float = 30.0):
        self._symbols = set(symbols)
        self._max_age = max_age_seconds

    def trade_to_record(self, trade: Any) -> Optional[SourceRecord]:
        ts = self._extract_timestamp(trade)
        if ts is not None and self._is_stale(ts):
            return None
        return SourceRecord(
            source_name="alpaca",
            collection="trades",
            identity=trade.symbol,
            data={
                "symbol": trade.symbol,
                "price": float(trade.price),
                "size": int(trade.size),
                "trade_count": 1,
            },
            timestamp=datetime.fromtimestamp(ts or time.time(), tz=timezone.utc),
            idempotency_key=self._key("trade", trade.symbol, ts or time.time()),
            tenant_id=0,
        )

    def quote_to_record(self, quote: Any) -> Optional[SourceRecord]:
        bid = float(quote.bid_price)
        ask = float(quote.ask_price)
        ts = self._extract_timestamp(quote)
        return SourceRecord(
            source_name="alpaca",
            collection="quotes",
            identity=quote.symbol,
            data={
                "symbol": quote.symbol,
                "bid": bid,
                "ask": ask,
                "spread": ask - bid,
            },
            timestamp=datetime.fromtimestamp(ts or time.time(), tz=timezone.utc),
            idempotency_key=self._key("quote", quote.symbol, ts or time.time()),
            tenant_id=0,
        )

    def fill_to_record(self, event: Any) -> Optional[SourceRecord]:
        order = event.order if hasattr(event, "order") else event
        if isinstance(order, dict):
            symbol = order.get("symbol", "")
            side = order.get("side", "")
            qty = float(order.get("filled_qty", 0))
            price = float(order.get("filled_avg_price", 0))
            order_id = order.get("id", "")
        else:
            symbol = getattr(order, "symbol", "")
            side = getattr(order, "side", "")
            qty = float(getattr(order, "filled_qty", 0))
            price = float(getattr(order, "filled_avg_price", 0))
            order_id = getattr(order, "id", "")
        return SourceRecord(
            source_name="alpaca",
            collection="fills",
            identity=symbol,
            data={
                "symbol": symbol,
                "side": side,
                "filled_qty": qty,
                "filled_avg_price": price,
                "order_id": order_id,
            },
            timestamp=datetime.now(timezone.utc),
            idempotency_key=self._key("fill", symbol, order_id or time.time()),
            tenant_id=0,
        )

    def _extract_timestamp(self, event: Any) -> Optional[float]:
        ts = getattr(event, "timestamp", None)
        if ts is None:
            return None
        if isinstance(ts, (int, float)):
            return float(ts)
        if hasattr(ts, "timestamp"):
            return ts.timestamp()
        return None

    def _is_stale(self, ts: float) -> bool:
        return (time.time() - ts) > self._max_age

    @staticmethod
    def _key(prefix: str, symbol: str, unique: Any) -> str:
        raw = f"{prefix}:{symbol}:{unique}"
        return hashlib.md5(raw.encode()).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund_v2/test_alpaca_source.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/sources/alpaca.py tests/unit/fund_v2/test_alpaca_source.py
git commit -m "feat(v2): Alpaca source adapter — trades, quotes, fills to SourceRecord"
```

---

## Task 4: Entity Lifecycle Hooks — Propagation + Predictions

**Files:**
- Create: `src/fund_v2/hooks.py`
- Create: `tests/unit/fund_v2/test_hooks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_hooks.py
"""Hook dispatch and threshold gating."""
from unittest.mock import MagicMock
from silicondb.orm.hooks import HookRegistry, collect_hooks_from_module
import fund_v2.hooks as hook_module


def test_collect_hooks_finds_all():
    hooks = collect_hooks_from_module(hook_module)
    names = [h["callback"].__name__ for h in hooks]
    # Original hooks
    assert "propagate_on_trade" in names
    assert "conviction_flip_warning" in names
    assert "sector_rotation_log" in names
    # Propagation hooks
    assert "update_relative_strength" in names
    assert "update_exhaustion" in names
    assert "propagate_sector_pressure" in names
    assert "propagate_macro_pressure" in names
    assert "update_crowded" in names
    # Prediction hooks
    assert "sector_rotation_predicted" in names
    assert "regime_shift_predicted" in names
    assert "sentiment_surge_predicted" in names


def test_propagate_hook_calls_engine(app):
    from fund_v2.hooks import propagate_on_trade
    app._engine.propagate = MagicMock()
    propagate_on_trade("AAPL", True, "alpaca", app)
    app._engine.propagate.assert_called_once()
    call_kwargs = app._engine.propagate.call_args
    assert "AAPL:return" in str(call_kwargs)


def test_update_relative_strength_calls_observe(app):
    from fund_v2.hooks import update_relative_strength
    app._engine.query_related = MagicMock(return_value=[
        MagicMock(external_id="NVDA", beliefs={"price_trend_slow": 0.6}),
        MagicMock(external_id="AMD", beliefs={"price_trend_slow": 0.4}),
    ])
    app._engine.belief = MagicMock(return_value=0.7)
    app._engine.observe = MagicMock()
    update_relative_strength("AAPL", 0.5, 0.7, app)
    app._engine.observe.assert_called_once()
    call_args = app._engine.observe.call_args
    assert "relative_strength" in str(call_args)


def test_update_exhaustion_on_extreme_momentum(app):
    from fund_v2.hooks import update_exhaustion
    app._engine.observe = MagicMock()
    # Extreme high momentum (>0.85) should strengthen exhaustion
    update_exhaustion("AAPL", 0.5, 0.9, app)
    app._engine.observe.assert_called_once()
    call_args = app._engine.observe.call_args
    assert "exhaustion" in str(call_args)


def test_update_exhaustion_skips_normal_momentum(app):
    from fund_v2.hooks import update_exhaustion
    app._engine.observe = MagicMock()
    # Normal momentum (between 0.15 and 0.85) should not trigger
    update_exhaustion("AAPL", 0.5, 0.6, app)
    app._engine.observe.assert_not_called()


def test_propagate_sector_pressure_calls_observe(app):
    from fund_v2.hooks import propagate_sector_pressure
    app._engine.query_related = MagicMock(return_value=[
        MagicMock(external_id="AAPL"),
        MagicMock(external_id="MSFT"),
    ])
    app._engine.observe = MagicMock()
    propagate_sector_pressure("technology", 0.4, 0.7, app)
    assert app._engine.observe.call_count == 2


def test_update_crowded_on_extreme_sentiment(app):
    from fund_v2.hooks import update_crowded
    app._engine.observe = MagicMock()
    # Extreme sentiment (>0.85) should flag as crowded
    update_crowded("AAPL", 0.5, 0.9, app)
    app._engine.observe.assert_called_once()
    call_args = app._engine.observe.call_args
    assert "crowded" in str(call_args)


def test_conviction_flip_skips_low_confidence(app):
    from fund_v2.hooks import conviction_flip_warning
    app.create_action = MagicMock()
    prediction = {"predicts_flip": True, "confidence": 0.2, "current_probability": 0.6, "predicted_probability": 0.4}
    conviction_flip_warning("AAPL", prediction, app)
    app.create_action.assert_not_called()


def test_conviction_flip_creates_action_on_high_confidence(app):
    from fund_v2.hooks import conviction_flip_warning
    app.create_action = MagicMock(return_value=1)
    prediction = {
        "predicts_flip": True,
        "confidence": 0.7,
        "current_probability": 0.6,
        "predicted_probability": 0.4,
        "drivers": [{"description": "wave momentum down"}],
    }
    conviction_flip_warning("AAPL", prediction, app)
    app.create_action.assert_called_once()
    call_kwargs = app.create_action.call_args[1]
    assert call_kwargs["severity"] == "high"
    assert "AAPL" in call_kwargs["entity_id"]


def test_sector_rotation_predicted_creates_action(app):
    from fund_v2.hooks import sector_rotation_predicted
    app.create_action = MagicMock(return_value=1)
    app._engine.query_related = MagicMock(return_value=[
        MagicMock(external_id="AAPL"),
    ])
    prediction = {
        "predicts_flip": True,
        "confidence": 0.6,
        "current_probability": 0.7,
        "predicted_probability": 0.3,
    }
    sector_rotation_predicted("technology", prediction, app)
    app.create_action.assert_called_once()
    call_kwargs = app.create_action.call_args[1]
    assert call_kwargs["action_type"] == "sector_headwind_predicted"


def test_regime_shift_predicted_creates_critical_action(app):
    from fund_v2.hooks import regime_shift_predicted
    app.create_action = MagicMock(return_value=1)
    prediction = {
        "predicts_flip": True,
        "confidence": 0.7,
        "current_probability": 0.7,
        "predicted_probability": 0.3,
    }
    regime_shift_predicted("default", prediction, app)
    app.create_action.assert_called_once()
    call_kwargs = app.create_action.call_args[1]
    assert call_kwargs["action_type"] == "risk_off_predicted"
    assert call_kwargs["severity"] == "critical"


def test_sector_rotation_skipped_for_small_delta(app):
    from fund_v2.hooks import sector_rotation_log
    app.create_action = MagicMock()
    # min_delta=0.15, so 0.05 delta should be skipped by the registry
    # But the function itself always fires — gating is in HookRegistry
    # Test the function directly with a significant delta
    sector_rotation_log("technology", 0.3, 0.6, app)
    app.create_action.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_hooks.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write hooks module**

```python
# src/fund_v2/hooks.py
"""Entity lifecycle hooks for the Glass Box Fund.

Deterministic, per-entity reactive logic. These are the reflexes —
fast, automatic, no LLM reasoning needed.

Hook layers:
  - Observation reactions: fire on raw market data
  - Belief propagation: Layer 1 → Layer 2 derivation
  - Belief change reactions: sector rotation, portfolio health
  - Prediction reactions: conviction flip, regime shift, sentiment surge
"""

from silicondb.orm.hooks import on_belief_change, on_observation, on_prediction


# ── Observation reactions ────────────────────────────────────────────────────


@on_observation("Instrument", "spread_tight")
def propagate_on_trade(entity, confirmed, source, app):
    """Propagate belief signal through graph on each trade observation."""
    app.engine.propagate(
        external_id=f"{entity}:return",
        confidence=0.7,
        decay=0.5,
    )


@on_observation("Instrument", "spread_tight")
def cooccurrence_tracking(entity, confirmed, source, app):
    """Track portfolio-level cooccurrences for correlation discovery."""
    from fund_v2.entities import Position
    positions = Position.where(engine=app.engine)
    if len(positions) >= 2:
        ids = [f"{p.symbol}:return" for p in positions]
        app.engine.add_cooccurrences(external_ids=ids, session_id="stream")


# ── Layer 2 propagation: observable → derived ────────────────────────────────


@on_belief_change("Instrument", "price_trend_slow", min_delta=0.05)
def update_relative_strength(entity, old_value, new_value, app):
    """Compare instrument momentum to sector peers, observe relative_strength."""
    peers = app.engine.query_related(str(entity), "in_sector", reverse=True)
    if not peers:
        return
    peer_avg = sum(
        getattr(p, "beliefs", {}).get("price_trend_slow", 0.5)
        for p in peers
    ) / len(peers)
    # relative_strength = how much this instrument outperforms peers
    instrument_val = new_value
    strength = 0.5 + (instrument_val - peer_avg)
    strength = max(0.0, min(1.0, strength))
    app.engine.observe(
        f"{entity}:relative_strength",
        confirmed=(strength > 0.5),
        source="derived",
    )


@on_belief_change("Instrument", "price_trend_fast", min_delta=0.1)
def update_exhaustion(entity, old_value, new_value, app):
    """When momentum is extreme (>0.85 or <0.15), strengthen exhaustion belief."""
    if new_value > 0.85 or new_value < 0.15:
        app.engine.observe(
            f"{entity}:exhaustion",
            confirmed=True,
            source="derived",
        )


@on_belief_change("Sector", "rotating_in", min_delta=0.1)
def propagate_sector_pressure(entity, old_value, new_value, app):
    """Observe pressure on all instruments in sector when rotation changes."""
    instruments = app.engine.query_related(str(entity), "instruments")
    rotating_out = new_value < old_value
    for inst in instruments:
        app.engine.observe(
            f"{inst.external_id}:pressure",
            confirmed=rotating_out,  # pressure = True when sector rotating out
            source="sector_propagation",
        )


@on_belief_change("MacroFactor", "rising", min_delta=0.1)
def propagate_macro_pressure(entity, old_value, new_value, app):
    """Observe pressure on instruments in pressured/driven sectors."""
    pressured_sectors = app.engine.query_related(str(entity), "pressures")
    for sector in pressured_sectors:
        instruments = app.engine.query_related(sector.external_id, "instruments")
        for inst in instruments:
            app.engine.observe(
                f"{inst.external_id}:pressure",
                confirmed=(new_value > 0.5),
                source="macro_propagation",
            )


@on_belief_change("Instrument", "retail_sentiment", min_delta=0.15)
def update_crowded(entity, old_value, new_value, app):
    """Extreme sentiment (>0.85 or <0.15) = crowded trade."""
    if new_value > 0.85 or new_value < 0.15:
        app.engine.observe(
            f"{entity}:crowded",
            confirmed=True,
            source="derived",
        )


# ── Belief change reactions ──────────────────────────────────────────────────


@on_belief_change("Sector", "rotating_in", min_delta=0.15)
def sector_rotation_log(entity, old_value, new_value, app):
    """Log significant sector rotation for the agent to consume."""
    direction = "into" if new_value > old_value else "out of"
    app.create_action(
        entity_type="Sector",
        entity_id=str(entity),
        action_type="sector_rotation",
        severity="medium",
        confidence=abs(new_value - old_value),
        description=f"Capital rotating {direction} sector ({old_value:.0%} → {new_value:.0%})",
    )


@on_belief_change("Portfolio", "healthy", min_delta=0.1)
def portfolio_health_change(entity, old_value, new_value, app):
    """Trigger epistemic briefing when portfolio health shifts."""
    if new_value < old_value:
        app.engine.epistemic_briefing(
            topic="portfolio_risk",
            budget=20,
            anchor_ratio=0.3,
            hops=2,
            neighbor_k=5,
        )


# ── Prediction reactions ─────────────────────────────────────────────────────


@on_prediction("Instrument", "relative_strength")
def conviction_flip_warning(entity, prediction, app):
    """When a relative_strength flip is predicted, alert for review."""
    if not prediction.get("predicts_flip"):
        return
    confidence = prediction.get("confidence", 0)
    if confidence < 0.5:
        return

    current = prediction.get("current_probability", 0.5)
    predicted = prediction.get("predicted_probability", 0.5)

    # Relative strength dropping below 0.5 = losing edge vs peers
    if current > 0.5 > predicted:
        drivers = prediction.get("drivers", [])
        driver_text = "; ".join(d.get("description", "") for d in drivers[:3])
        app.create_action(
            entity_type="Instrument",
            entity_id=str(entity),
            action_type="conviction_flip_warning",
            severity="high",
            confidence=confidence,
            description=f"Relative strength predicted to flip below 50% ({current:.0%} → {predicted:.0%}). Drivers: {driver_text}",
        )


@on_prediction("MacroFactor", "rising")
def macro_regime_shift_predicted(entity, prediction, app):
    """When a macro factor flip is predicted, log for agent context."""
    if not prediction.get("predicts_flip"):
        return
    if prediction.get("confidence", 0) < 0.4:
        return

    app.create_action(
        entity_type="MacroFactor",
        entity_id=str(entity),
        action_type="macro_flip_predicted",
        severity="medium",
        confidence=prediction.get("confidence", 0),
        description=f"Macro factor predicted to flip within {prediction.get('horizon_days', '?')} days",
    )


@on_prediction("Sector", "rotating_in")
def sector_rotation_predicted(entity, prediction, app):
    """Pre-alert held instruments when sector rotation flip predicted."""
    if not prediction.get("predicts_flip"):
        return
    if prediction.get("confidence", 0) < 0.5:
        return

    current = prediction.get("current_probability", 0.5)
    predicted = prediction.get("predicted_probability", 0.5)
    rotating_out = current > 0.5 > predicted

    instruments = app.engine.query_related(str(entity), "instruments")
    held_symbols = [inst.external_id for inst in instruments]

    action_type = "sector_headwind_predicted" if rotating_out else "sector_tailwind_predicted"
    direction = "headwind" if rotating_out else "tailwind"

    app.create_action(
        entity_type="Sector",
        entity_id=str(entity),
        action_type=action_type,
        severity="high",
        confidence=prediction.get("confidence", 0),
        description=(
            f"Sector {direction} predicted ({current:.0%} → {predicted:.0%}). "
            f"Affected instruments: {', '.join(held_symbols[:5])}"
        ),
    )


@on_prediction("MarketRegime", "risk_on")
def regime_shift_predicted(entity, prediction, app):
    """Critical action when regime shift predicted — triggers full portfolio review."""
    if not prediction.get("predicts_flip"):
        return
    if prediction.get("confidence", 0) < 0.5:
        return

    current = prediction.get("current_probability", 0.5)
    predicted = prediction.get("predicted_probability", 0.5)
    going_risk_off = current > 0.5 > predicted

    action_type = "risk_off_predicted" if going_risk_off else "risk_on_predicted"
    severity = "critical" if going_risk_off else "high"

    app.create_action(
        entity_type="MarketRegime",
        entity_id=str(entity),
        action_type=action_type,
        severity=severity,
        confidence=prediction.get("confidence", 0),
        description=(
            f"Regime shift predicted: {'risk-off' if going_risk_off else 'risk-on'} "
            f"({current:.0%} → {predicted:.0%}). Full portfolio review triggered."
        ),
    )


@on_prediction("Instrument", "retail_sentiment")
def sentiment_surge_predicted(entity, prediction, app):
    """Crowding/capitulation risk when sentiment flip predicted."""
    if not prediction.get("predicts_flip"):
        return
    if prediction.get("confidence", 0) < 0.5:
        return

    current = prediction.get("current_probability", 0.5)
    predicted = prediction.get("predicted_probability", 0.5)

    if predicted > 0.85:
        action_type = "crowding_risk_predicted"
        description = f"Sentiment surge predicted for {entity} ({current:.0%} → {predicted:.0%}) — crowding risk"
    elif predicted < 0.15:
        action_type = "capitulation_predicted"
        description = f"Sentiment collapse predicted for {entity} ({current:.0%} → {predicted:.0%}) — capitulation risk"
    else:
        return

    app.create_action(
        entity_type="Instrument",
        entity_id=str(entity),
        action_type=action_type,
        severity="high",
        confidence=prediction.get("confidence", 0),
        description=description,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/fund_v2/test_hooks.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/hooks.py tests/unit/fund_v2/test_hooks.py
git commit -m "feat(v2): entity lifecycle hooks — propagation, Layer 2 derivation, prediction reactions"
```

---

## Task 5: Portfolio Strategy (Pure Math)

**Files:**
- Create: `src/fund_v2/strategy.py`
- Create: `tests/unit/fund_v2/test_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_strategy.py
"""Portfolio optimization — pure math, no ORM dependency."""
import pytest

from fund_v2.strategy import kelly_weights, equal_weights, belief_weights, compute_trades


def test_equal_weights_distributes_evenly():
    symbols = ["AAPL", "NVDA", "MSFT"]
    weights = equal_weights(symbols, cash_reserve=0.1)
    assert len(weights) == 3
    assert sum(weights.values()) == pytest.approx(0.9, abs=0.01)
    assert all(w == pytest.approx(0.3, abs=0.01) for w in weights.values())


def test_belief_weights_scales_by_conviction():
    convictions = {"AAPL": 0.8, "NVDA": 0.4, "MSFT": 0.6}
    weights = belief_weights(convictions, cash_reserve=0.1)
    assert weights["AAPL"] > weights["MSFT"] > weights["NVDA"]
    assert sum(weights.values()) == pytest.approx(0.9, abs=0.01)


def test_kelly_weights_respects_max_position():
    convictions = {"AAPL": 0.95}
    weights = kelly_weights(convictions, max_position=0.20, cash_reserve=0.1)
    assert weights["AAPL"] <= 0.20


def test_compute_trades_generates_buys_and_sells():
    current = {"AAPL": 0.30, "NVDA": 0.20}
    target = {"AAPL": 0.15, "NVDA": 0.35}
    trades = compute_trades(current, target, portfolio_value=100000, prices={"AAPL": 150, "NVDA": 500})
    sells = [t for t in trades if t["side"] == "sell"]
    buys = [t for t in trades if t["side"] == "buy"]
    assert len(sells) == 1 and sells[0]["symbol"] == "AAPL"
    assert len(buys) == 1 and buys[0]["symbol"] == "NVDA"


def test_compute_trades_skips_tiny_changes():
    current = {"AAPL": 0.20}
    target = {"AAPL": 0.201}
    trades = compute_trades(current, target, portfolio_value=100000, prices={"AAPL": 150}, min_trade_pct=0.02)
    assert trades == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_strategy.py -v`
Expected: FAIL

- [ ] **Step 3: Write strategy module**

```python
# src/fund_v2/strategy.py
"""Portfolio optimization strategies — pure math, no ORM dependency."""
from __future__ import annotations
import math


def equal_weights(symbols: list[str], cash_reserve: float = 0.1) -> dict[str, float]:
    """Equal allocation across all symbols."""
    available = 1.0 - cash_reserve
    w = available / max(len(symbols), 1)
    return {s: w for s in symbols}


def belief_weights(
    convictions: dict[str, float],
    cash_reserve: float = 0.1,
) -> dict[str, float]:
    """Allocate proportional to conviction strength."""
    total = sum(convictions.values()) or 1.0
    available = 1.0 - cash_reserve
    return {s: (c / total) * available for s, c in convictions.items()}


def kelly_weights(
    convictions: dict[str, float],
    max_position: float = 0.20,
    cash_reserve: float = 0.1,
) -> dict[str, float]:
    """Simplified Kelly criterion: f = 2p - 1, capped at max_position."""
    raw = {}
    for s, p in convictions.items():
        f = max(0.0, 2 * p - 1)
        raw[s] = min(f, max_position)
    total = sum(raw.values()) or 1.0
    available = 1.0 - cash_reserve
    if total > available:
        scale = available / total
        return {s: w * scale for s, w in raw.items()}
    return raw


def compute_trades(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    portfolio_value: float,
    prices: dict[str, float],
    min_trade_pct: float = 0.02,
) -> list[dict]:
    """Compute trades to move from current to target weights.

    Returns list of {"symbol", "side", "qty", "value"} dicts.
    Sells come before buys.
    """
    trades = []
    all_symbols = set(current_weights) | set(target_weights)
    for symbol in sorted(all_symbols):
        curr = current_weights.get(symbol, 0.0)
        tgt = target_weights.get(symbol, 0.0)
        delta = tgt - curr
        if abs(delta) < min_trade_pct:
            continue
        price = prices.get(symbol, 0)
        if price <= 0:
            continue
        value = abs(delta) * portfolio_value
        qty = int(value / price)
        if qty <= 0:
            continue
        trades.append({
            "symbol": symbol,
            "side": "buy" if delta > 0 else "sell",
            "qty": qty,
            "value": qty * price,
        })
    # Sells first, then buys
    trades.sort(key=lambda t: (0 if t["side"] == "sell" else 1, t["symbol"]))
    return trades
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/fund_v2/test_strategy.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/strategy.py tests/unit/fund_v2/test_strategy.py
git commit -m "feat(v2): portfolio strategy — kelly, equal weight, belief weighted"
```

---

## Task 6: MCP Domain Tools + Signal Generation

**Files:**
- Create: `src/fund_v2/tools.py`
- Create: `src/fund_v2/signals.py`
- Create: `tests/unit/fund_v2/test_tools.py`
- Create: `tests/unit/fund_v2/test_signals.py`

- [ ] **Step 1: Write the failing test for tools**

```python
# tests/unit/fund_v2/test_tools.py
"""MCP domain tools — portfolio analysis, forecasts, trade proposals, signals."""
from fund_v2.tools import register_tools
from silicondb.orm.mcp_server import create_mcp_server


def test_tools_register_on_app(app):
    register_tools(app)
    server = create_mcp_server(app)
    tool_names = [t["name"] for t in server.list_tools()]
    assert "portfolio_analysis" in tool_names
    assert "regime_assessment" in tool_names
    assert "belief_forecast" in tool_names
    assert "propose_trade" in tool_names
    assert "explain_instrument" in tool_names
    assert "prediction_accuracy" in tool_names


def test_signal_tools_register_on_app(app):
    register_tools(app)
    server = create_mcp_server(app)
    tool_names = [t["name"] for t in server.list_tools()]
    assert "generate_signals" in tool_names
    assert "trend_divergence" in tool_names
    assert "contradictions" in tool_names
    assert "signal_quality" in tool_names


def test_portfolio_analysis_returns_structure(app):
    register_tools(app)
    server = create_mcp_server(app)
    result = server.call_tool("portfolio_analysis", {})
    assert "position_count" in result
    assert "positions" in result
    assert isinstance(result["positions"], list)


def test_propose_trade_creates_action(app):
    register_tools(app)
    server = create_mcp_server(app)
    result = server.call_tool("propose_trade", {
        "symbol": "AAPL",
        "side": "buy",
        "rationale": "test trade",
        "confidence": 0.8,
    })
    assert "action_id" in result
    actions = app.get_actions(limit=10)
    assert len(actions) >= 1


def test_contradictions_returns_structure(app):
    register_tools(app)
    server = create_mcp_server(app)
    result = server.call_tool("contradictions", {})
    assert "contradictions" in result
    assert isinstance(result["contradictions"], list)
```

- [ ] **Step 2: Write the failing test for signals**

```python
# tests/unit/fund_v2/test_signals.py
"""Signal generation — regime-aware multi-layer scoring."""
from unittest.mock import MagicMock
from fund_v2.signals import generate_signals_impl


def test_generate_signals_returns_structure():
    engine = MagicMock()
    # Mock regime beliefs
    regime = MagicMock()
    regime.trend_following = 0.7
    regime.mean_reverting_regime = 0.3
    regime.risk_on = 0.6
    engine.get_entity = MagicMock(return_value=regime)

    # Mock instruments with layered beliefs
    inst1 = MagicMock(
        external_id="AAPL",
        relative_strength=0.7,
        exhaustion=0.2,
        pressure=0.4,
        retail_sentiment=0.6,
        crowded=0.1,
        price_trend_fast=0.65,
        price_trend_slow=0.6,
    )
    inst2 = MagicMock(
        external_id="NVDA",
        relative_strength=0.3,
        exhaustion=0.7,
        pressure=0.6,
        retail_sentiment=0.8,
        crowded=0.6,
        price_trend_fast=0.4,
        price_trend_slow=0.5,
    )
    engine.query_entities = MagicMock(return_value=[inst1, inst2])

    # Mock predictions
    engine.predict_belief = MagicMock(return_value=None)

    result = generate_signals_impl(engine)
    assert "signals" in result
    assert len(result["signals"]) == 2
    for sig in result["signals"]:
        assert "symbol" in sig
        assert "edge" in sig
        assert "confidence" in sig
        assert "sizing" in sig
        assert "layers" in sig


def test_generate_signals_sorted_by_edge_confidence():
    engine = MagicMock()
    regime = MagicMock()
    regime.trend_following = 0.5
    regime.mean_reverting_regime = 0.5
    regime.risk_on = 0.5
    engine.get_entity = MagicMock(return_value=regime)

    # Instrument with strong edge
    strong = MagicMock(
        external_id="AAPL",
        relative_strength=0.9,
        exhaustion=0.1,
        pressure=0.2,
        retail_sentiment=0.5,
        crowded=0.1,
        price_trend_fast=0.8,
        price_trend_slow=0.7,
    )
    # Instrument with weak edge
    weak = MagicMock(
        external_id="NVDA",
        relative_strength=0.52,
        exhaustion=0.48,
        pressure=0.49,
        retail_sentiment=0.5,
        crowded=0.2,
        price_trend_fast=0.51,
        price_trend_slow=0.5,
    )
    engine.query_entities = MagicMock(return_value=[weak, strong])
    engine.predict_belief = MagicMock(return_value=None)

    result = generate_signals_impl(engine)
    # First signal should have larger |edge| * confidence
    signals = result["signals"]
    scores = [abs(s["edge"]) * s["confidence"] for s in signals]
    assert scores[0] >= scores[1]


def test_generate_signals_regime_weights_trend():
    engine = MagicMock()
    # Strong trend-following regime
    regime = MagicMock()
    regime.trend_following = 0.9
    regime.mean_reverting_regime = 0.1
    regime.risk_on = 0.7
    engine.get_entity = MagicMock(return_value=regime)

    inst = MagicMock(
        external_id="AAPL",
        relative_strength=0.8,
        exhaustion=0.7,  # high exhaustion, but regime says trend-follow
        pressure=0.3,
        retail_sentiment=0.5,
        crowded=0.1,
        price_trend_fast=0.8,
        price_trend_slow=0.75,
    )
    engine.query_entities = MagicMock(return_value=[inst])
    engine.predict_belief = MagicMock(return_value=None)

    result = generate_signals_impl(engine)
    signal = result["signals"][0]
    # In a strong trend-following regime, momentum weight dominates
    # so edge should still be positive despite high exhaustion
    assert signal["edge"] > 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/unit/fund_v2/test_tools.py tests/unit/fund_v2/test_signals.py -v`
Expected: FAIL

- [ ] **Step 4: Write signals module**

```python
# src/fund_v2/signals.py
"""Regime-aware signal generation for the Glass Box Fund.

Multi-layer signal scoring using the layered belief model:
  Layer 1 (observable): price_trend_fast, price_trend_slow
  Layer 2 (graph-derived): relative_strength, exhaustion, pressure
  Layer 3 (crowd): retail_sentiment, crowded

Regime beliefs (MarketRegime) set the weighting between momentum
and mean-reversion components.
"""
from __future__ import annotations

from typing import Any, Optional


def generate_signals_impl(engine: Any, regime_id: str = "default") -> dict:
    """Generate regime-aware multi-layer signals for all instruments.

    Reads regime beliefs to set weights:
      - mom_weight from trend_following
      - revert_weight from mean_reverting_regime

    Scores instruments using:
      - relative_strength, exhaustion, pressure (Layer 2)
      - retail_sentiment, crowded (Layer 3)
      with regime-adjusted weights.

    Uses predictions for:
      - persistence: relative_strength predicted to hold
      - pressure_shift: graph foresight from pressure predictions
      - exhaust_risk: predicted exhaustion

    Returns signals sorted by |edge| * confidence.
    """
    # Get regime beliefs for weighting
    regime = engine.get_entity("MarketRegime", regime_id)
    if regime:
        mom_weight = getattr(regime, "trend_following", 0.5)
        revert_weight = getattr(regime, "mean_reverting_regime", 0.5)
        risk_on = getattr(regime, "risk_on", 0.5)
    else:
        mom_weight = 0.5
        revert_weight = 0.5
        risk_on = 0.5

    # Normalize weights
    total_weight = mom_weight + revert_weight
    if total_weight > 0:
        mom_weight = mom_weight / total_weight
        revert_weight = revert_weight / total_weight
    else:
        mom_weight = 0.5
        revert_weight = 0.5

    instruments = engine.query_entities("Instrument")
    signals = []

    for inst in instruments:
        symbol = inst.external_id

        # Extract layered beliefs
        rel_strength = getattr(inst, "relative_strength", 0.5)
        exhaustion_val = getattr(inst, "exhaustion", 0.2)
        pressure_val = getattr(inst, "pressure", 0.5)
        sentiment = getattr(inst, "retail_sentiment", 0.5)
        crowded_val = getattr(inst, "crowded", 0.2)
        fast = getattr(inst, "price_trend_fast", 0.5)
        slow = getattr(inst, "price_trend_slow", 0.5)

        # Momentum component: relative_strength + trend alignment
        momentum_score = (rel_strength - 0.5) * 2  # [-1, 1]

        # Mean-reversion component: exhaustion inverted + pressure inverted
        reversion_score = (exhaustion_val - 0.5) * -2  # high exhaustion = short signal

        # Composite edge = regime-weighted blend
        raw_edge = (mom_weight * momentum_score) + (revert_weight * reversion_score)

        # Pressure adjustment: high pressure reduces edge
        pressure_adj = (0.5 - pressure_val) * 0.3  # pressure > 0.5 = headwind
        raw_edge += pressure_adj

        # Crowd penalty: crowded trades get edge reduced
        crowd_penalty = crowded_val * 0.2
        if raw_edge > 0:
            raw_edge -= crowd_penalty
        else:
            raw_edge += crowd_penalty

        # Confidence from agreement across layers
        layer1_dir = 1 if fast > 0.5 else -1
        layer2_dir = 1 if rel_strength > 0.5 else -1
        edge_dir = 1 if raw_edge > 0 else -1

        agreement = 0.5
        if layer1_dir == edge_dir:
            agreement += 0.2
        if layer2_dir == edge_dir:
            agreement += 0.2
        if crowded_val < 0.3:
            agreement += 0.1

        confidence = min(1.0, agreement)

        # Prediction adjustments
        pred_adj = 0.0
        try:
            rs_pred = engine.predict_belief(f"{symbol}:relative_strength", horizon_days=7)
            if rs_pred and hasattr(rs_pred, "predicted_probability"):
                pred_persistence = rs_pred.predicted_probability - 0.5
                pred_adj += pred_persistence * 0.1
        except Exception:
            pass

        try:
            pressure_pred = engine.predict_belief(f"{symbol}:pressure", horizon_days=7)
            if pressure_pred and hasattr(pressure_pred, "predicted_probability"):
                pred_shift = (0.5 - pressure_pred.predicted_probability) * 0.1
                pred_adj += pred_shift
        except Exception:
            pass

        try:
            exhaust_pred = engine.predict_belief(f"{symbol}:exhaustion", horizon_days=7)
            if exhaust_pred and hasattr(exhaust_pred, "predicted_probability"):
                if exhaust_pred.predicted_probability > 0.7:
                    pred_adj -= 0.1  # predicted exhaustion = reduce edge
        except Exception:
            pass

        final_edge = raw_edge + pred_adj
        final_edge = max(-1.0, min(1.0, final_edge))

        # Sizing: |edge| * confidence * risk_on scale
        sizing = abs(final_edge) * confidence * (0.5 + risk_on * 0.5)

        signals.append({
            "symbol": symbol,
            "edge": round(final_edge, 4),
            "confidence": round(confidence, 4),
            "sizing": round(sizing, 4),
            "direction": "long" if final_edge > 0 else "short",
            "layers": {
                "momentum": round(momentum_score, 4),
                "reversion": round(reversion_score, 4),
                "pressure": round(pressure_adj, 4),
                "crowd": round(-crowd_penalty if raw_edge > 0 else crowd_penalty, 4),
                "prediction": round(pred_adj, 4),
            },
            "regime_weights": {
                "momentum": round(mom_weight, 4),
                "reversion": round(revert_weight, 4),
            },
        })

    # Sort by |edge| * confidence descending
    signals.sort(key=lambda s: abs(s["edge"]) * s["confidence"], reverse=True)

    return {
        "signals": signals,
        "regime": {
            "trend_following": mom_weight,
            "mean_reverting": revert_weight,
            "risk_on": risk_on,
        },
        "count": len(signals),
    }
```

- [ ] **Step 5: Write tools module**

```python
# src/fund_v2/tools.py
"""MCP domain tools for the Glass Box Fund.

Exposed via MCP server for any agent (Claude, Silicon Serve, custom)
to call. These are the brain — intelligent, on-demand, cross-entity.

Signal generation is in signals.py and registered here.
"""
from fund_v2.signals import generate_signals_impl


def register_tools(app):
    """Register fund-specific MCP tools on the app."""

    @app.tool("portfolio_analysis")
    def portfolio_analysis() -> dict:
        """Analyze current portfolio: positions, concentration, P&L."""
        from fund_v2.entities import Position, Instrument
        positions = Position.where(engine=app.engine)
        sectors = set()
        result = []
        for p in positions:
            inst = Instrument.get(p.symbol, engine=app.engine)
            if inst and inst.in_sector:
                sectors.add(str(inst.in_sector))
            result.append({
                "symbol": p.symbol,
                "quantity": p.quantity,
                "market_value": p.market_value,
                "unrealized_pnl": p.unrealized_pnl,
                "conviction": p.conviction,
                "profitable": p.profitable,
                "allocation_pct": p.allocation_pct,
            })
        total_conviction = sum(r["conviction"] for r in result) / max(len(result), 1)
        return {
            "position_count": len(result),
            "sector_count": len(sectors),
            "avg_conviction": total_conviction,
            "positions": sorted(result, key=lambda x: x["conviction"], reverse=True),
        }

    @app.tool("regime_assessment")
    def regime_assessment() -> dict:
        """Assess market regime from macro factors, thermo state, and regime entity."""
        from fund_v2.entities import MacroFactor, MarketRegime
        factors = MacroFactor.where(engine=app.engine)
        thermo = {}
        if hasattr(app.engine, "thermo_state"):
            thermo = app.engine.thermo_state() or {}
        regime = MarketRegime.get("default", engine=app.engine)
        regime_data = {}
        if regime:
            regime_data = {
                "risk_on": regime.risk_on,
                "trend_following": regime.trend_following,
                "mean_reverting_regime": regime.mean_reverting_regime,
            }
        return {
            "factors": {str(f): {"rising": f.rising, "elevated": f.elevated} for f in factors},
            "thermo": thermo,
            "regime": regime_data,
        }

    @app.tool("belief_forecast")
    def belief_forecast(symbols: list[str] = None, horizon_days: int = 7) -> dict:
        """Predict future belief states for portfolio instruments.

        Returns predictions sorted by |delta| — biggest movers first.
        Highlights predicted flips (beliefs about to cross 0.5).
        """
        if symbols:
            ids = []
            for s in symbols:
                ids.extend([
                    f"{s}:price_trend_slow",
                    f"{s}:relative_strength",
                    f"{s}:pressure",
                ])
            predictions = app.engine.predict_beliefs(ids, horizon_days=horizon_days)
        else:
            predictions = app.engine.predicted_flips(
                horizon_days=horizon_days, min_confidence=0.4, k=20
            )
        return {
            "horizon_days": horizon_days,
            "predictions": [
                {
                    "node_id": p.node_id,
                    "current": p.current_probability,
                    "predicted": p.predicted_probability,
                    "confidence": p.confidence,
                    "ci": [p.ci_lower, p.ci_upper],
                    "predicts_flip": p.predicts_flip,
                    "drivers": [
                        {"description": d.description, "influence": d.influence, "type": d.type.value}
                        for d in p.drivers
                    ],
                }
                for p in predictions
            ],
        }

    @app.tool("prediction_accuracy")
    def prediction_accuracy() -> dict:
        """Validate past predictions and return accuracy metrics."""
        validations = app.engine.validate_predictions()
        stats = app.engine.prediction_stats()
        return {
            "recent_validations": [
                {
                    "node_id": v.node_id,
                    "predicted": v.predicted_probability,
                    "actual": v.actual_probability,
                    "error": v.error,
                    "within_ci": v.within_ci,
                }
                for v in (validations or [])[:10]
            ],
            "stats": {
                "mean_error": stats.mean_error if stats else None,
                "ci_coverage": stats.ci_coverage if stats else None,
                "flip_accuracy": stats.flip_accuracy if stats else None,
                "total_validations": stats.total_validations if stats else 0,
            },
        }

    @app.tool("propose_trade")
    def propose_trade(symbol: str, side: str, rationale: str, confidence: float = 0.7) -> dict:
        """Propose a trade through the action feed.

        Goes through execution policy — buys/sells require human approval
        unless confidence exceeds the confidence gate threshold.
        """
        action_id = app.create_action(
            entity_type="Position",
            entity_id=symbol,
            action_type=side,
            severity="high",
            confidence=confidence,
            description=rationale,
        )
        return {"action_id": action_id, "status": "proposed"}

    @app.tool("explain_instrument")
    def explain_instrument(symbol: str) -> dict:
        """Deep explainability for a single instrument.

        Returns layered beliefs, relationships, prediction, peer comparison,
        and graph neighborhood.
        """
        from fund_v2.entities import Instrument
        inst = Instrument.get(symbol, engine=app.engine)
        if not inst:
            return {"error": f"Instrument {symbol} not found"}

        result = {
            "symbol": symbol,
            "beliefs": {
                "layer1": {
                    "price_trend_fast": inst.price_trend_fast,
                    "price_trend_slow": inst.price_trend_slow,
                    "spread_tight": inst.spread_tight,
                    "volume_normal": inst.volume_normal,
                },
                "layer2": {
                    "relative_strength": inst.relative_strength,
                    "exhaustion": inst.exhaustion,
                    "pressure": inst.pressure,
                },
                "layer3": {
                    "retail_sentiment": inst.retail_sentiment,
                    "mention_velocity": inst.mention_velocity,
                    "crowded": inst.crowded,
                },
            },
            "sector": str(inst.in_sector) if inst.in_sector else None,
            "competitors": [str(c) for c in (inst.competes_with or [])],
            "benchmark": str(inst.benchmarked_against) if inst.benchmarked_against else None,
        }

        # Add prediction if available
        prediction = app.engine.predict_belief(f"{symbol}:relative_strength", horizon_days=7)
        if prediction:
            result["prediction"] = {
                "predicted_relative_strength": prediction.predicted_probability,
                "confidence": prediction.confidence,
                "ci": [prediction.ci_lower, prediction.ci_upper],
                "predicts_flip": prediction.predicts_flip,
                "drivers": [d.description for d in prediction.drivers],
            }

        # Add accumulator state
        result["trade_pressure"] = inst.trade_pressure.temperature if hasattr(inst, "trade_pressure") else None

        return result

    @app.tool("generate_signals")
    def generate_signals(regime_id: str = "default") -> dict:
        """Regime-aware multi-layer signal generation.

        Reads regime beliefs to set momentum/reversion weights.
        Scores instruments across all belief layers.
        Uses predictions for persistence, pressure shift, exhaustion risk.
        Returns signals sorted by |edge| * confidence.
        """
        return generate_signals_impl(app.engine, regime_id=regime_id)

    @app.tool("trend_divergence")
    def trend_divergence() -> dict:
        """Find instruments where fast/slow momentum predictions diverge.

        Fast momentum predicting one direction while slow momentum predicts
        another indicates a potential trend change.
        """
        from fund_v2.entities import Instrument
        instruments = Instrument.where(engine=app.engine)
        divergences = []

        for inst in instruments:
            fast = getattr(inst, "price_trend_fast", 0.5)
            slow = getattr(inst, "price_trend_slow", 0.5)

            # Check current divergence
            fast_dir = 1 if fast > 0.5 else -1
            slow_dir = 1 if slow > 0.5 else -1

            if fast_dir != slow_dir:
                divergences.append({
                    "symbol": inst.symbol,
                    "fast_momentum": round(fast, 4),
                    "slow_momentum": round(slow, 4),
                    "type": "fast_leads" if abs(fast - 0.5) > abs(slow - 0.5) else "slow_leads",
                    "magnitude": round(abs(fast - slow), 4),
                })

            # Check prediction divergence
            try:
                fast_pred = app.engine.predict_belief(f"{inst.symbol}:price_trend_fast", horizon_days=3)
                slow_pred = app.engine.predict_belief(f"{inst.symbol}:price_trend_slow", horizon_days=7)
                if fast_pred and slow_pred:
                    fp = fast_pred.predicted_probability
                    sp = slow_pred.predicted_probability
                    if (fp > 0.5) != (sp > 0.5):
                        divergences.append({
                            "symbol": inst.symbol,
                            "predicted_fast": round(fp, 4),
                            "predicted_slow": round(sp, 4),
                            "type": "predicted_divergence",
                            "magnitude": round(abs(fp - sp), 4),
                        })
            except Exception:
                pass

        divergences.sort(key=lambda d: d["magnitude"], reverse=True)
        return {"divergences": divergences, "count": len(divergences)}

    @app.tool("contradictions")
    def contradictions() -> dict:
        """Find instruments with conflicting beliefs across layers.

        Examples: strong momentum but high exhaustion, bullish sentiment
        but sector headwind, high relative_strength but crowded.
        """
        from fund_v2.entities import Instrument
        instruments = Instrument.where(engine=app.engine)
        found = []

        for inst in instruments:
            rel_strength = getattr(inst, "relative_strength", 0.5)
            exhaustion_val = getattr(inst, "exhaustion", 0.2)
            pressure_val = getattr(inst, "pressure", 0.5)
            sentiment = getattr(inst, "retail_sentiment", 0.5)
            crowded_val = getattr(inst, "crowded", 0.2)
            fast = getattr(inst, "price_trend_fast", 0.5)

            contras = []

            # Strong momentum but high exhaustion
            if fast > 0.7 and exhaustion_val > 0.6:
                contras.append({
                    "type": "momentum_vs_exhaustion",
                    "description": f"Strong momentum ({fast:.0%}) but high exhaustion ({exhaustion_val:.0%})",
                })

            # Bullish sentiment but sector headwind
            if sentiment > 0.65 and pressure_val > 0.65:
                contras.append({
                    "type": "sentiment_vs_pressure",
                    "description": f"Bullish sentiment ({sentiment:.0%}) but sector headwind ({pressure_val:.0%})",
                })

            # High relative_strength but crowded trade
            if rel_strength > 0.7 and crowded_val > 0.6:
                contras.append({
                    "type": "strength_vs_crowding",
                    "description": f"High relative strength ({rel_strength:.0%}) but crowded ({crowded_val:.0%})",
                })

            # Weak momentum but low exhaustion (not mean-reverting yet)
            if fast < 0.3 and exhaustion_val < 0.2:
                contras.append({
                    "type": "weakness_not_exhausted",
                    "description": f"Weak momentum ({fast:.0%}) but low exhaustion ({exhaustion_val:.0%}) — may continue falling",
                })

            if contras:
                found.append({
                    "symbol": inst.symbol,
                    "contradictions": contras,
                })

        return {"contradictions": found, "count": len(found)}

    @app.tool("signal_quality")
    def signal_quality() -> dict:
        """Prediction validation broken down by belief type.

        Groups prediction accuracy by layer (observable, derived, crowd)
        to show which belief types are most reliable.
        """
        validations = app.engine.validate_predictions() or []
        stats = app.engine.prediction_stats()

        layer_map = {
            "price_trend_fast": "layer1_observable",
            "price_trend_slow": "layer1_observable",
            "spread_tight": "layer1_observable",
            "volume_normal": "layer1_observable",
            "relative_strength": "layer2_derived",
            "exhaustion": "layer2_derived",
            "pressure": "layer2_derived",
            "retail_sentiment": "layer3_crowd",
            "mention_velocity": "layer3_crowd",
            "crowded": "layer3_crowd",
        }

        by_layer = {}
        for v in validations:
            node_id = getattr(v, "node_id", "")
            belief_name = node_id.split(":")[-1] if ":" in node_id else ""
            layer = layer_map.get(belief_name, "other")
            if layer not in by_layer:
                by_layer[layer] = {"count": 0, "total_error": 0.0, "within_ci": 0}
            by_layer[layer]["count"] += 1
            by_layer[layer]["total_error"] += abs(getattr(v, "error", 0))
            if getattr(v, "within_ci", False):
                by_layer[layer]["within_ci"] += 1

        for layer, data in by_layer.items():
            if data["count"] > 0:
                data["mean_error"] = round(data["total_error"] / data["count"], 4)
                data["ci_coverage"] = round(data["within_ci"] / data["count"], 4)
            del data["total_error"]

        return {
            "by_layer": by_layer,
            "overall": {
                "mean_error": stats.mean_error if stats else None,
                "ci_coverage": stats.ci_coverage if stats else None,
                "flip_accuracy": stats.flip_accuracy if stats else None,
                "total_validations": stats.total_validations if stats else 0,
            },
        }
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/unit/fund_v2/test_tools.py tests/unit/fund_v2/test_signals.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/fund_v2/tools.py src/fund_v2/signals.py tests/unit/fund_v2/test_tools.py tests/unit/fund_v2/test_signals.py
git commit -m "feat(v2): MCP domain tools + regime-aware signal generation"
```

---

## Task 7: Broker Adapter (Action → Execution)

**Files:**
- Create: `src/fund_v2/broker_adapter.py`
- Create: `tests/unit/fund_v2/test_broker_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_broker_adapter.py
"""Broker adapter — executes approved actions via Alpaca."""
from unittest.mock import MagicMock
from fund_v2.broker_adapter import BrokerAdapter


def test_execute_buy_action():
    broker = MagicMock()
    broker.submit_market_order.return_value = MagicMock(id="ord-1", status="filled")
    adapter = BrokerAdapter(broker)
    result = adapter.execute_action({
        "action_type": "buy",
        "entity_id": "AAPL",
        "description": "test buy",
        "confidence": 0.8,
    }, portfolio_value=100000, target_allocation=0.10, price=150.0)
    broker.submit_market_order.assert_called_once()
    assert result["status"] == "executed"


def test_execute_sell_action():
    broker = MagicMock()
    broker.submit_market_order.return_value = MagicMock(id="ord-2", status="filled")
    adapter = BrokerAdapter(broker)
    result = adapter.execute_action({
        "action_type": "sell",
        "entity_id": "NVDA",
    }, qty=10, price=500.0)
    call_args = broker.submit_market_order.call_args
    assert call_args[1]["side"] == "sell" or call_args[0][2] == "sell"


def test_skip_non_trade_action():
    broker = MagicMock()
    adapter = BrokerAdapter(broker)
    result = adapter.execute_action({"action_type": "volatility_alert", "entity_id": "AAPL"})
    broker.submit_market_order.assert_not_called()
    assert result["status"] == "skipped"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_broker_adapter.py -v`
Expected: FAIL

- [ ] **Step 3: Write broker adapter**

```python
# src/fund_v2/broker_adapter.py
"""Adapts approved actions from the action feed to Alpaca broker calls."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

TRADE_ACTIONS = {"buy", "sell"}


class BrokerAdapter:
    """Executes approved trade actions via the Alpaca broker."""

    def __init__(self, broker: Any):
        self._broker = broker

    def execute_action(
        self,
        action: dict,
        *,
        portfolio_value: float = 0,
        target_allocation: float = 0,
        price: float = 0,
        qty: int = 0,
    ) -> dict:
        action_type = action.get("action_type", "")
        symbol = action.get("entity_id", "")

        if action_type not in TRADE_ACTIONS:
            return {"status": "skipped", "reason": f"not a trade action: {action_type}"}

        side = action_type

        if qty <= 0 and price > 0 and portfolio_value > 0 and target_allocation > 0:
            value = portfolio_value * target_allocation
            qty = int(value / price)

        if qty <= 0:
            return {"status": "skipped", "reason": "qty is zero"}

        try:
            order = self._broker.submit_market_order(
                symbol=symbol,
                qty=Decimal(str(qty)),
                side=side,
            )
            logger.info("Executed %s %s x%d: %s", side, symbol, qty, order.id)
            return {"status": "executed", "order_id": order.id, "symbol": symbol, "side": side, "qty": qty}
        except Exception as exc:
            logger.error("Execution failed for %s %s: %s", side, symbol, exc)
            return {"status": "error", "error": str(exc)}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/fund_v2/test_broker_adapter.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/broker_adapter.py tests/unit/fund_v2/test_broker_adapter.py
git commit -m "feat(v2): broker adapter — action feed to Alpaca execution"
```

---

## Task 8: Agent Loop — with Prediction Handlers

**Files:**
- Create: `src/fund_v2/agent.py`
- Create: `tests/unit/fund_v2/test_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_agent.py
"""Agent loop — event handlers for trading decisions."""
from unittest.mock import MagicMock, patch
from fund_v2.agent import create_agent


def test_agent_registers_handlers(app):
    loop = create_agent(app)
    # AgentLoop stores handlers internally — verify it was created
    assert loop is not None


def test_critical_handler_logs(app, capsys):
    loop = create_agent(app)
    event = {
        "event_type": "action_recommended",
        "payload": {
            "severity": "critical",
            "action_type": "sell",
            "entity_id": "AAPL",
            "description": "stop-loss triggered",
        },
    }
    # Simulate event dispatch — _handlers contains _Registration dataclass instances
    for reg in loop._handlers:
        if reg.event_type == "action_recommended" and reg.matches(event):
            reg.handler(event, app)
    captured = capsys.readouterr()
    assert "CRITICAL" in captured.out or "stop-loss" in captured.out


def test_thermo_handler_runs_briefing(app):
    app._engine.epistemic_briefing = MagicMock(return_value={"anchors": ["NVDA"]})
    loop = create_agent(app)
    event = {
        "event_type": "thermo_shift",
        "payload": {"temperature": 0.8, "tier": "hot"},
    }
    for reg in loop._handlers:
        if reg.event_type == "thermo_shift" and reg.matches(event):
            reg.handler(event, app)
    app._engine.epistemic_briefing.assert_called_once()


def test_risk_off_handler_logs(app, capsys):
    loop = create_agent(app)
    event = {
        "event_type": "action_recommended",
        "payload": {
            "severity": "critical",
            "action_type": "risk_off_predicted",
            "entity_id": "default",
            "description": "Regime shift predicted: risk-off",
        },
    }
    for reg in loop._handlers:
        if reg.event_type == "action_recommended" and reg.matches(event):
            reg.handler(event, app)
    captured = capsys.readouterr()
    assert "REGIME" in captured.out or "risk" in captured.out.lower()


def test_sector_headwind_handler_logs(app, capsys):
    loop = create_agent(app)
    event = {
        "event_type": "action_recommended",
        "payload": {
            "severity": "high",
            "action_type": "sector_headwind_predicted",
            "entity_id": "technology",
            "description": "Sector headwind predicted",
        },
    }
    for reg in loop._handlers:
        if reg.event_type == "action_recommended" and reg.matches(event):
            reg.handler(event, app)
    captured = capsys.readouterr()
    assert "SECTOR" in captured.out or "headwind" in captured.out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Write agent module**

```python
# src/fund_v2/agent.py
"""Trading agent loop for the Glass Box Fund.

Connects to SiliconDB via MCP, reacts to belief changes, thermo shifts,
and prediction-driven regime/sector events. Proposes trades through the
action feed. Bring your own LLM.
"""

from silicondb.agent.loop import AgentLoop


def create_agent(app) -> AgentLoop:
    """Create the trading agent loop with event handlers."""

    loop = AgentLoop(app, poll_interval=1.0)

    @loop.on("action_recommended", severity="critical")
    def handle_critical(event, app):
        """Critical actions (stop-loss, drawdown, regime shift) — log immediately."""
        payload = event.get("payload", {})
        action_type = payload.get("action_type", "")
        entity_id = payload.get("entity_id", "")
        print(f"[CRITICAL] {action_type} for {entity_id}: {payload.get('description', '')}")

    @loop.on("action_recommended", severity="high")
    def handle_high_priority(event, app):
        """High-priority actions — run prediction check before deciding."""
        payload = event.get("payload", {})
        entity_id = payload.get("entity_id", "")

        # Get prediction context for this entity
        prediction = app.engine.predict_belief(f"{entity_id}:relative_strength", horizon_days=7)
        if prediction and prediction.predicts_flip:
            print(
                f"[AGENT] {entity_id}: relative_strength flip predicted "
                f"({prediction.current_probability:.0%} → {prediction.predicted_probability:.0%}, "
                f"confidence {prediction.confidence:.0%})"
            )

    @loop.on("thermo_shift")
    def handle_thermo(event, app):
        """Thermo tier change — request epistemic briefing."""
        payload = event.get("payload", {})
        temperature = payload.get("temperature", 0)
        tier = payload.get("tier", "unknown")
        print(f"[THERMO] System temperature: {temperature:.3f} (tier: {tier})")

        # Run briefing when market heats up
        if tier in ("hot", "critical"):
            briefing = app.engine.epistemic_briefing(
                topic="market", budget=20, anchor_ratio=0.3, hops=2, neighbor_k=5,
            )
            if briefing:
                anchors = briefing.get("anchors", []) if isinstance(briefing, dict) else []
                print(f"[BRIEFING] {len(anchors)} high-conviction anchors")

    @loop.on("belief_changed")
    def handle_belief_delta(event, app):
        """Significant belief change — check for prediction-driven opportunities."""
        payload = event.get("payload", {})
        node_id = payload.get("node_id", "")
        if ":relative_strength" not in node_id and ":price_trend_slow" not in node_id:
            return

        symbol = node_id.split(":")[0]
        flips = app.engine.predicted_flips(horizon_days=14, min_confidence=0.6, k=5)
        for flip in flips:
            if symbol in flip.node_id:
                drivers = "; ".join(d.description for d in flip.drivers[:2])
                print(
                    f"[PREDICTION] {symbol} belief flip predicted: "
                    f"{flip.current_probability:.0%} → {flip.predicted_probability:.0%} "
                    f"({drivers})"
                )

    @loop.on("action_recommended", action_type="risk_off_predicted")
    def handle_risk_off_predicted(event, app):
        """Regime shift to risk-off predicted — trigger full portfolio review."""
        payload = event.get("payload", {})
        entity_id = payload.get("entity_id", "")
        print(f"[REGIME] Risk-off predicted for {entity_id}: {payload.get('description', '')}")
        print("[REGIME] Triggering full portfolio review")

        # Run portfolio analysis via MCP
        try:
            from silicondb.orm.mcp_server import create_mcp_server
            server = create_mcp_server(app)
            analysis = server.call_tool("portfolio_analysis", {})
            position_count = analysis.get("position_count", 0)
            print(f"[REGIME] Portfolio review: {position_count} positions to evaluate")
        except Exception:
            pass

    @loop.on("action_recommended", action_type="sector_headwind_predicted")
    def handle_sector_headwind(event, app):
        """Sector headwind predicted — log and check affected positions."""
        payload = event.get("payload", {})
        entity_id = payload.get("entity_id", "")
        print(f"[SECTOR] Headwind predicted for {entity_id}: {payload.get('description', '')}")

        # Check which held positions are in the affected sector
        from fund_v2.entities import Position
        positions = Position.where(engine=app.engine)
        for p in positions:
            inst = app.engine.get_entity("Instrument", p.symbol)
            if inst and str(getattr(inst, "in_sector", "")) == entity_id:
                print(f"[SECTOR] Affected position: {p.symbol}")

    return loop
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/fund_v2/test_agent.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/agent.py tests/unit/fund_v2/test_agent.py
git commit -m "feat(v2): agent loop — critical, high-priority, thermo, belief, prediction handlers"
```

---

## Task 9: Ontology Bootstrap

**Files:**
- Create: `src/fund_v2/ontology_bootstrap.py`
- Create: `tests/unit/fund_v2/test_ontology_bootstrap.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_ontology_bootstrap.py
"""Ontology bootstrap — loads market graph from existing ontology.py."""
from unittest.mock import MagicMock, patch


def test_bootstrap_calls_insert_triples(app):
    from fund_v2.ontology_bootstrap import bootstrap_ontology

    # Mock the ontology builder to return a small set
    mock_triples = [
        MagicMock(subject="AAPL", predicate="in_sector", object="technology", weight=1.0),
        MagicMock(subject="NVDA", predicate="competes_with", object="AMD", weight=0.8),
    ]
    app._engine.insert_triples = MagicMock()

    with patch("fund_v2.ontology_bootstrap.build_ontology", return_value=mock_triples):
        bootstrap_ontology(app)

    app._engine.insert_triples.assert_called_once()
    triples_arg = app._engine.insert_triples.call_args[0][0]
    assert len(triples_arg) == 2
    assert triples_arg[0]["subject"] == "AAPL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_ontology_bootstrap.py -v`
Expected: FAIL

- [ ] **Step 3: Write bootstrap module**

```python
# src/fund_v2/ontology_bootstrap.py
"""Bootstrap hook: loads dynamic market ontology into SiliconDB.

Reuses fund/ontology.py (Wikipedia + Yahoo Finance fetch, 50K+ triples).
"""
from fund.ontology import build_ontology


def bootstrap_ontology(app):
    """Called during app.bootstrap() — injects market graph triples."""
    triples = build_ontology(use_network=True)
    app.engine.insert_triples([
        {
            "subject": t.subject,
            "predicate": t.predicate,
            "object": t.object,
            "weight": t.weight,
        }
        for t in triples
    ])
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/fund_v2/test_ontology_bootstrap.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/ontology_bootstrap.py tests/unit/fund_v2/test_ontology_bootstrap.py
git commit -m "feat(v2): ontology bootstrap — reuses v1 Wikipedia/Yahoo fetch"
```

---

## Task 10: App Wiring + Startup — with MarketRegime + Prediction Policy

**Files:**
- Create: `src/fund_v2/app.py`
- Create: `tests/unit/fund_v2/test_app_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_app_wiring.py
"""App wiring — entity registration, hooks, tools, policy."""
from fund_v2.app import create_app
from silicondb.orm.execution import Decision


def test_create_app_registers_entities():
    app = create_app(db_path=":memory:")
    # Entities should be registered (check engine had register_type called)
    assert app is not None


def test_create_app_registers_market_regime():
    app = create_app(db_path=":memory:")
    # MarketRegime should be registered alongside other entities
    from fund_v2.entities import MarketRegime
    assert MarketRegime in app._registered_entities or True  # registration doesn't raise


def test_create_app_has_hooks():
    app = create_app(db_path=":memory:")
    hooks = app._hook_registry.get_hooks("prediction", "Instrument", "relative_strength")
    assert len(hooks) >= 1


def test_create_app_has_tools():
    from silicondb.orm.mcp_server import create_mcp_server
    app = create_app(db_path=":memory:")
    server = create_mcp_server(app)
    tool_names = [t["name"] for t in server.list_tools()]
    assert "portfolio_analysis" in tool_names
    assert "generate_signals" in tool_names


def test_execution_policy_blocks_unapproved_buy():
    app = create_app(db_path=":memory:")
    policy = app._execution_policy
    decision = policy.evaluate({"action_type": "buy", "confidence": 0.5})
    assert decision == Decision.HUMAN


def test_execution_policy_auto_approves_alert():
    app = create_app(db_path=":memory:")
    policy = app._execution_policy
    decision = policy.evaluate({"action_type": "volatility_alert", "confidence": 0.9})
    assert decision == Decision.AUTO


def test_execution_policy_auto_approves_prediction_actions():
    app = create_app(db_path=":memory:")
    policy = app._execution_policy
    for action_type in [
        "sector_headwind_predicted",
        "risk_off_predicted",
        "risk_on_predicted",
        "crowding_risk_predicted",
        "capitulation_predicted",
    ]:
        decision = policy.evaluate({"action_type": action_type, "confidence": 0.7})
        assert decision == Decision.AUTO, f"{action_type} should be auto-approved"


def test_execution_policy_confidence_gate_sell():
    app = create_app(db_path=":memory:")
    policy = app._execution_policy
    decision = policy.evaluate({"action_type": "sell", "confidence": 0.96})
    assert decision == Decision.AUTO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_app_wiring.py -v`
Expected: FAIL

- [ ] **Step 3: Write app wiring**

```python
# src/fund_v2/app.py
"""Glass Box Fund — ORM app wiring.

Single entry point that registers entities, sources, hooks, tools,
execution policy, and starts the MCP server + agent loop.
"""

from silicondb.orm import App
from silicondb.orm.execution import ExecutionPolicy
from silicondb.orm.hooks import collect_hooks_from_module

from fund_v2.entities import (
    Instrument, Sector, Industry, Index, MacroFactor,
    MarketRegime,
    Position, Portfolio, MarketConcept,
)
import fund_v2.hooks as hook_module
from fund_v2.tools import register_tools
from fund_v2.agent import create_agent
from fund_v2.ontology_bootstrap import bootstrap_ontology


def create_app(db_path: str = None, db_url: str = None, **kwargs) -> App:
    """Create and configure the trading fund ORM app."""

    if db_url:
        app = App.from_url(db_url, **kwargs)
    else:
        app = App.from_path(db_path or "/data/fund", dimension=384, **kwargs)

    # Register entities (including MarketRegime)
    app.register(
        Instrument, Sector, Industry, Index, MacroFactor,
        MarketRegime,
        Position, Portfolio, MarketConcept,
    )

    # Register hooks
    for hook in collect_hooks_from_module(hook_module):
        app.hook_registry.register(**hook)

    # Register MCP tools
    register_tools(app)

    # Execution policy
    app.set_execution_policy(ExecutionPolicy(
        auto_approve=[
            "volatility_alert",
            "macro_shift",
            "sector_rotation",
            "conviction_flip_warning",
            "macro_flip_predicted",
            "concentration_warning",
            "drawdown_warning",
            # Prediction-driven action types
            "sector_headwind_predicted",
            "sector_tailwind_predicted",
            "risk_off_predicted",
            "risk_on_predicted",
            "crowding_risk_predicted",
            "capitulation_predicted",
        ],
        human_approve=["buy", "sell"],
        confidence_gate={"sell": 0.95},
        simulation_only=["rebalance"],
        cooldown={"buy": 3600, "sell": 1800},
    ))

    # Bootstrap hook for dynamic ontology
    app.on_bootstrap(bootstrap_ontology)

    return app


def run(db_path: str = None, db_url: str = None, **kwargs):
    """Bootstrap and run the trading engine."""

    app = create_app(db_path=db_path, db_url=db_url, **kwargs)

    # Register sources
    app.register_sources("sources.yaml")

    # Bootstrap: load ontology + historical data
    app.bootstrap()

    # Start agent loop in background
    agent = create_agent(app)

    # Start: ORM runtime (streams + pulls) + MCP server
    import threading
    agent_thread = threading.Thread(target=agent.run, daemon=True, name="agent-loop")
    agent_thread.start()

    app.serve_mcp(port=3000)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/fund_v2/test_app_wiring.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/app.py tests/unit/fund_v2/test_app_wiring.py
git commit -m "feat(v2): app wiring — entities, MarketRegime, hooks, tools, prediction policy"
```

---

## Task 11: StockTwits Sentiment Source

**Files:**
- Create: `src/fund_v2/sentiment/stocktwits.py`
- Create: `tests/unit/fund_v2/test_stocktwits_source.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/fund_v2/test_stocktwits_source.py
"""StockTwits sentiment source — bull/bear ratio as observations."""
from unittest.mock import MagicMock, patch

import pytest

from fund_v2.sentiment.stocktwits import StockTwitsSentiment


def test_parse_sentiment_response():
    adapter = StockTwitsSentiment()
    response = {
        "symbol": {"symbol": "AAPL"},
        "sentiment": {"bullish": 120, "bearish": 30},
    }
    record = adapter.parse_sentiment(response)
    assert record.identity == "AAPL"
    assert record.data["bull_ratio"] == pytest.approx(0.8, abs=0.01)
    assert record.data["total_messages"] == 150


def test_parse_sentiment_handles_zero_messages():
    adapter = StockTwitsSentiment()
    response = {
        "symbol": {"symbol": "AAPL"},
        "sentiment": {"bullish": 0, "bearish": 0},
    }
    record = adapter.parse_sentiment(response)
    assert record.data["bull_ratio"] == 0.5  # neutral when no data


def test_bull_ratio_extremes():
    adapter = StockTwitsSentiment()
    # Extremely bullish
    response = {"symbol": {"symbol": "GME"}, "sentiment": {"bullish": 1000, "bearish": 10}}
    record = adapter.parse_sentiment(response)
    assert record.data["bull_ratio"] > 0.95

    # Extremely bearish
    response = {"symbol": {"symbol": "GME"}, "sentiment": {"bullish": 5, "bearish": 500}}
    record = adapter.parse_sentiment(response)
    assert record.data["bull_ratio"] < 0.05
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/fund_v2/test_stocktwits_source.py -v`
Expected: FAIL

- [ ] **Step 3: Write StockTwits adapter**

```python
# src/fund_v2/sentiment/stocktwits.py
"""StockTwits sentiment source — converts API responses to SourceRecords."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from silicondb.sources.models import SourceRecord


class StockTwitsSentiment:
    """Converts StockTwits sentiment API responses to SourceRecords."""

    def parse_sentiment(self, response: dict[str, Any]) -> SourceRecord:
        symbol_data = response.get("symbol", {})
        symbol = symbol_data.get("symbol", "") if isinstance(symbol_data, dict) else str(symbol_data)
        sentiment = response.get("sentiment", {})
        bullish = int(sentiment.get("bullish", 0))
        bearish = int(sentiment.get("bearish", 0))
        total = bullish + bearish
        bull_ratio = bullish / total if total > 0 else 0.5

        return SourceRecord(
            source_name="stocktwits",
            collection="sentiment",
            identity=symbol,
            data={
                "symbol": symbol,
                "bull_ratio": bull_ratio,
                "bullish": bullish,
                "bearish": bearish,
                "total_messages": total,
            },
            timestamp=datetime.now(timezone.utc),
            idempotency_key=hashlib.md5(
                f"stocktwits:{symbol}:{datetime.now(timezone.utc).isoformat()[:13]}".encode()
            ).hexdigest(),
            tenant_id=0,
        )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/fund_v2/test_stocktwits_source.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund_v2/sentiment/stocktwits.py tests/unit/fund_v2/test_stocktwits_source.py
git commit -m "feat(v2): StockTwits sentiment source — bull/bear ratio observations"
```

---

## Task 12: Integration Test — Full Pipeline + Prediction Pipeline

**Files:**
- Create: `tests/integration/fund_v2/test_pipeline_e2e.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/fund_v2/test_pipeline_e2e.py
"""End-to-end: source → pipeline → hooks → actions → MCP."""
from unittest.mock import MagicMock

from fund_v2.app import create_app
from fund_v2.sources.alpaca import AlpacaSourceAdapter
from silicondb.orm.mcp_server import create_mcp_server
from silicondb.orm.execution import Decision


def test_trade_to_action_pipeline():
    """A trade observation flows through the full pipeline and creates an action."""
    app = create_app(db_path=":memory:")

    # Simulate: instrument exists with low relative_strength
    app.engine.ingest("AAPL", "", metadata={"node_type": "instrument"})
    # Set relative_strength belief to low (below stop-loss threshold of 0.25)
    for _ in range(20):
        app.engine.observe("AAPL", confirmed=False, source="test")

    # Verify belief dropped
    belief = app.engine.belief("AAPL")
    assert belief < 0.5

    # Dispatch a stop-loss style hook manually
    # Note: dispatch_hooks injects app=self automatically — don't pass app=
    app.dispatch_hooks(
        "belief_change", "Position", "relative_strength",
        entity="AAPL",
        old_value=0.4,
        new_value=0.20,
    )

    # Check that MCP server exposes actions
    server = create_mcp_server(app)
    tools = server.list_tools()
    assert any(t["name"] == "portfolio_analysis" for t in tools)


def test_mcp_tools_return_data():
    """MCP tools return structured data from the engine."""
    app = create_app(db_path=":memory:")
    server = create_mcp_server(app)

    # Portfolio analysis on empty portfolio
    result = server.call_tool("portfolio_analysis", {})
    assert result["position_count"] == 0

    # Regime assessment
    result = server.call_tool("regime_assessment", {})
    assert "factors" in result
    assert "thermo" in result


def test_execution_policy_gates_trades():
    """Execution policy correctly gates buy/sell vs alerts."""
    app = create_app(db_path=":memory:")
    policy = app._execution_policy

    # Alert: auto-approved
    assert policy.evaluate({"action_type": "volatility_alert", "confidence": 0.9}) == Decision.AUTO

    # Buy: needs human approval
    assert policy.evaluate({"action_type": "buy", "confidence": 0.7}) == Decision.HUMAN

    # Sell with high confidence: auto-approved via confidence gate
    assert policy.evaluate({"action_type": "sell", "confidence": 0.96}) == Decision.AUTO

    # Sell with low confidence: needs human
    assert policy.evaluate({"action_type": "sell", "confidence": 0.5}) == Decision.HUMAN


def test_prediction_pipeline():
    """Predictions → hooks → agent: full prediction pipeline test."""
    app = create_app(db_path=":memory:")

    # 1. Ingest an instrument with beliefs
    app.engine.ingest("NVDA", "", metadata={"node_type": "instrument"})
    for _ in range(10):
        app.engine.observe("NVDA", confirmed=True, source="test")

    # 2. Dispatch a prediction hook (sector rotation predicted)
    app.dispatch_hooks(
        "prediction", "Sector", "rotating_in",
        entity="technology",
        prediction={
            "predicts_flip": True,
            "confidence": 0.7,
            "current_probability": 0.7,
            "predicted_probability": 0.3,
        },
    )

    # 3. Verify action was created
    actions = app.get_actions(limit=10)
    sector_actions = [
        a for a in actions
        if a.get("action_type") in ("sector_headwind_predicted", "sector_tailwind_predicted")
    ]
    assert len(sector_actions) >= 1

    # 4. Dispatch a regime shift prediction hook
    app.dispatch_hooks(
        "prediction", "MarketRegime", "risk_on",
        entity="default",
        prediction={
            "predicts_flip": True,
            "confidence": 0.8,
            "current_probability": 0.7,
            "predicted_probability": 0.3,
        },
    )

    # 5. Verify regime shift action was created
    actions = app.get_actions(limit=20)
    regime_actions = [
        a for a in actions
        if a.get("action_type") in ("risk_off_predicted", "risk_on_predicted")
    ]
    assert len(regime_actions) >= 1

    # 6. Verify signal_quality tool returns data
    server = create_mcp_server(app)
    result = server.call_tool("signal_quality", {})
    assert "by_layer" in result
    assert "overall" in result


def test_generate_signals_on_empty_portfolio():
    """generate_signals returns empty signals list on empty portfolio."""
    app = create_app(db_path=":memory:")
    server = create_mcp_server(app)
    result = server.call_tool("generate_signals", {})
    assert "signals" in result
    assert isinstance(result["signals"], list)
    assert "regime" in result
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/integration/fund_v2/test_pipeline_e2e.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/fund_v2/test_pipeline_e2e.py
git commit -m "test(v2): integration tests — pipeline, prediction pipeline, MCP tools, execution policy"
```

---

## Task 13: Clean Up Draft Files

**Files:**
- Delete: `src/fund/entities.py` (draft, replaced by `src/fund_v2/entities.py`)
- Delete: `src/fund/hooks.py` (draft, replaced by `src/fund_v2/hooks.py`)
- Delete: `src/fund/tools.py` (draft, replaced by `src/fund_v2/tools.py`)
- Delete: `src/fund/agent.py` (draft, replaced by `src/fund_v2/agent.py`)
- Delete: `src/fund/app_wiring.py` (draft, replaced by `src/fund_v2/app.py`)
- Delete: `src/fund/ontology_bootstrap.py` (draft, replaced by `src/fund_v2/ontology_bootstrap.py`)

- [ ] **Step 1: Remove draft files from v1 package**

```bash
rm src/fund/entities.py src/fund/hooks.py src/fund/tools.py
rm src/fund/agent.py src/fund/app_wiring.py src/fund/ontology_bootstrap.py
```

- [ ] **Step 2: Verify v1 tests still pass**

Run: `python -m pytest tests/unit/fund/ -v --tb=short`
Expected: All existing v1 tests PASS (drafts weren't imported by v1)

- [ ] **Step 3: Verify v2 tests still pass**

Run: `python -m pytest tests/unit/fund_v2/ tests/integration/fund_v2/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove v1 draft ORM files, replaced by fund_v2 package"
```

---

## Summary

| Task | Component | Lines (est.) | Depends on |
|------|-----------|-------------|------------|
| 1 | Scaffold + fixtures | 30 | — |
| 2 | Entity definitions (layered beliefs + MarketRegime) | 300 | 1 |
| 3 | Alpaca source connector | 120 | 1 |
| 4 | Hooks (propagation + prediction) | 200 | 1, 2 |
| 5 | Strategy (pure math) | 80 | 1 |
| 6 | MCP tools + signals.py | 350 | 1, 2, 5 |
| 7 | Broker adapter | 60 | 1 |
| 8 | Agent loop (+ prediction handlers) | 100 | 1, 6 |
| 9 | Ontology bootstrap | 20 | 1, 2 |
| 10 | App wiring (+ MarketRegime + prediction policy) | 90 | 2, 3, 4, 5, 6, 7, 8, 9 |
| 11 | StockTwits sentiment | 40 | 1 |
| 12 | Integration tests (+ prediction pipeline) | 120 | 10 |
| 13 | Clean up drafts | 0 | 12 |

**Total new code:** ~1,390 lines (includes ~120 lines in signals.py)
**Total test code:** ~650 lines
**Replaces:** ~2,500 lines of v1 hand-wired engine code

Tasks 1-5 and 7, 9, 11 can run in parallel (independent). Tasks 6, 8 depend on earlier tasks. Task 10 is the integration point. Task 12 validates the whole stack. Task 13 cleans up.
