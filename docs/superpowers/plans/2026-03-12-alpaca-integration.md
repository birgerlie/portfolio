# Alpaca Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the trading engine to Alpaca for live/paper order execution and position sync, bridging the existing `ExecutionPlanGenerator` output to real broker API calls.

**Architecture:** A thin `AlpacaBroker` adapter wraps `alpaca-py`'s `TradingClient`. The `OrderExecutor` converts `TradeOrder` objects (from the existing execution generator) into Alpaca API calls, tracks order status, and syncs positions back to the fund engine for NAV calculation. All trades are journaled.

**Tech Stack:** `alpaca-py` SDK (`pip install alpaca-py`), Python dataclasses, existing `fund.journal.EventJournal`.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/fund/alpaca_broker.py` | `AlpacaBroker` — thin wrapper around `TradingClient` |
| `src/fund/order_executor.py` | `OrderExecutor` — converts `TradeOrder` → Alpaca orders, tracks fills |
| `src/fund/position_sync.py` | `PositionSync` — reconciles Alpaca positions with fund engine state |
| `tests/unit/fund/test_alpaca_broker.py` | Unit tests (mocked Alpaca client) |
| `tests/unit/fund/test_order_executor.py` | Unit tests |
| `tests/unit/fund/test_position_sync.py` | Unit tests |

---

## Chunk 1: Alpaca Broker Adapter

### Task 1: AlpacaBroker — Connection and Account

**Files:**
- Create: `tests/unit/fund/test_alpaca_broker.py`
- Create: `src/fund/alpaca_broker.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for the Alpaca broker adapter."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from fund.alpaca_broker import AlpacaBroker, AlpacaConfig, BrokerAccount, BrokerPosition


class TestAlpacaConfig:
    def test_paper_config(self):
        config = AlpacaConfig(api_key="test", secret_key="secret", paper=True)
        assert config.paper is True

    def test_live_config(self):
        config = AlpacaConfig(api_key="test", secret_key="secret", paper=False)
        assert config.paper is False


class TestAlpacaBrokerAccount:
    def test_get_account(self):
        mock_client = MagicMock()
        mock_account = MagicMock()
        mock_account.cash = "50000.00"
        mock_account.equity = "100000.00"
        mock_account.buying_power = "50000.00"
        mock_account.status = "ACTIVE"
        mock_client.get_account.return_value = mock_account

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        account = broker.get_account()
        assert account.cash == Decimal("50000.00")
        assert account.equity == Decimal("100000.00")
        assert account.status == "ACTIVE"

    def test_is_connected_true(self):
        mock_client = MagicMock()
        mock_client.get_account.return_value = MagicMock(status="ACTIVE")
        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client
        assert broker.is_connected() is True

    def test_is_connected_false_on_error(self):
        mock_client = MagicMock()
        mock_client.get_account.side_effect = Exception("API error")
        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client
        assert broker.is_connected() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/fund/test_alpaca_broker.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement AlpacaBroker with config and account**

```python
"""Thin adapter around Alpaca's TradingClient."""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from alpaca.trading.client import TradingClient


@dataclass
class AlpacaConfig:
    """Alpaca API credentials and mode."""
    api_key: str
    secret_key: str
    paper: bool = True


@dataclass
class BrokerAccount:
    """Simplified view of the Alpaca account."""
    cash: Decimal
    equity: Decimal
    buying_power: Decimal
    status: str


@dataclass
class BrokerPosition:
    """Simplified view of an Alpaca position."""
    symbol: str
    quantity: Decimal
    market_value: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    unrealized_pl: Decimal
    unrealized_pl_pct: float


@dataclass
class BrokerOrder:
    """Simplified view of an Alpaca order."""
    id: str
    symbol: str
    side: str  # "buy" or "sell"
    qty: Decimal
    order_type: str  # "market" or "limit"
    limit_price: Optional[Decimal]
    status: str  # "new", "filled", "partially_filled", "canceled", etc.
    filled_qty: Decimal
    filled_avg_price: Optional[Decimal]


class AlpacaBroker:
    """Thin wrapper around Alpaca TradingClient."""

    def __init__(self, config: AlpacaConfig):
        self._client = TradingClient(
            api_key=config.api_key,
            secret_key=config.secret_key,
            paper=config.paper,
        )

    def get_account(self) -> BrokerAccount:
        acct = self._client.get_account()
        return BrokerAccount(
            cash=Decimal(str(acct.cash)),
            equity=Decimal(str(acct.equity)),
            buying_power=Decimal(str(acct.buying_power)),
            status=str(acct.status),
        )

    def is_connected(self) -> bool:
        try:
            self._client.get_account()
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/fund/test_alpaca_broker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/alpaca_broker.py tests/unit/fund/test_alpaca_broker.py
git commit -m "feat(fund): alpaca broker adapter — config, account, connection check"
```

---

### Task 2: AlpacaBroker — Positions and Orders

**Files:**
- Modify: `tests/unit/fund/test_alpaca_broker.py`
- Modify: `src/fund/alpaca_broker.py`

- [ ] **Step 1: Write failing tests**

Add to `test_alpaca_broker.py`:

```python
class TestAlpacaBrokerPositions:
    def test_get_positions(self):
        mock_client = MagicMock()
        mock_pos = MagicMock()
        mock_pos.symbol = "NVDA"
        mock_pos.qty = "100"
        mock_pos.market_value = "85000.00"
        mock_pos.avg_entry_price = "800.00"
        mock_pos.current_price = "850.00"
        mock_pos.unrealized_pl = "5000.00"
        mock_pos.unrealized_plpc = "0.0625"
        mock_client.get_all_positions.return_value = [mock_pos]

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "NVDA"
        assert positions[0].quantity == Decimal("100")
        assert positions[0].market_value == Decimal("85000.00")

    def test_get_positions_empty(self):
        mock_client = MagicMock()
        mock_client.get_all_positions.return_value = []
        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client
        assert broker.get_positions() == []


class TestAlpacaBrokerOrders:
    def test_submit_market_buy(self):
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.symbol = "NVDA"
        mock_order.side = "buy"
        mock_order.qty = "100"
        mock_order.order_type = "market"
        mock_order.limit_price = None
        mock_order.status = "new"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_client.submit_order.return_value = mock_order

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        order = broker.submit_market_order("NVDA", Decimal("100"), "buy")
        assert order.id == "order-123"
        assert order.symbol == "NVDA"
        assert order.side == "buy"
        assert order.status == "new"
        mock_client.submit_order.assert_called_once()

    def test_submit_limit_buy(self):
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order-456"
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.qty = "50"
        mock_order.order_type = "limit"
        mock_order.limit_price = "150.00"
        mock_order.status = "new"
        mock_order.filled_qty = "0"
        mock_order.filled_avg_price = None
        mock_client.submit_order.return_value = mock_order

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        order = broker.submit_limit_order("AAPL", Decimal("50"), "buy", Decimal("150.00"))
        assert order.id == "order-456"
        assert order.order_type == "limit"
        mock_client.submit_order.assert_called_once()

    def test_get_order_status(self):
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.symbol = "NVDA"
        mock_order.side = "buy"
        mock_order.qty = "100"
        mock_order.order_type = "market"
        mock_order.limit_price = None
        mock_order.status = "filled"
        mock_order.filled_qty = "100"
        mock_order.filled_avg_price = "851.25"
        mock_client.get_order_by_id.return_value = mock_order

        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        order = broker.get_order("order-123")
        assert order.status == "filled"
        assert order.filled_qty == Decimal("100")
        assert order.filled_avg_price == Decimal("851.25")

    def test_cancel_order(self):
        mock_client = MagicMock()
        broker = AlpacaBroker.__new__(AlpacaBroker)
        broker._client = mock_client

        broker.cancel_order("order-123")
        mock_client.cancel_order_by_id.assert_called_once_with("order-123")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/fund/test_alpaca_broker.py -v`
Expected: FAIL — methods not defined

- [ ] **Step 3: Implement position and order methods**

Add to `AlpacaBroker` class in `alpaca_broker.py`:

```python
    def get_positions(self) -> List[BrokerPosition]:
        positions = self._client.get_all_positions()
        return [
            BrokerPosition(
                symbol=p.symbol,
                quantity=Decimal(str(p.qty)),
                market_value=Decimal(str(p.market_value)),
                avg_entry_price=Decimal(str(p.avg_entry_price)),
                current_price=Decimal(str(p.current_price)),
                unrealized_pl=Decimal(str(p.unrealized_pl)),
                unrealized_pl_pct=float(p.unrealized_plpc),
            )
            for p in positions
        ]

    def submit_market_order(self, symbol: str, qty: Decimal, side: str) -> BrokerOrder:
        from alpaca.trading.requests import MarketOrderRequest
        req = MarketOrderRequest(symbol=symbol, qty=float(qty), side=side)
        return self._to_broker_order(self._client.submit_order(req))

    def submit_limit_order(self, symbol: str, qty: Decimal, side: str, limit_price: Decimal) -> BrokerOrder:
        from alpaca.trading.requests import LimitOrderRequest
        req = LimitOrderRequest(symbol=symbol, qty=float(qty), side=side, limit_price=float(limit_price))
        return self._to_broker_order(self._client.submit_order(req))

    def get_order(self, order_id: str) -> BrokerOrder:
        return self._to_broker_order(self._client.get_order_by_id(order_id))

    def cancel_order(self, order_id: str) -> None:
        self._client.cancel_order_by_id(order_id)

    def _to_broker_order(self, o) -> BrokerOrder:
        return BrokerOrder(
            id=str(o.id),
            symbol=str(o.symbol),
            side=str(o.side),
            qty=Decimal(str(o.qty)),
            order_type=str(o.order_type),
            limit_price=Decimal(str(o.limit_price)) if o.limit_price else None,
            status=str(o.status),
            filled_qty=Decimal(str(o.filled_qty)),
            filled_avg_price=Decimal(str(o.filled_avg_price)) if o.filled_avg_price else None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/fund/test_alpaca_broker.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/alpaca_broker.py tests/unit/fund/test_alpaca_broker.py
git commit -m "feat(fund): alpaca broker — positions, market/limit orders, cancel"
```

---

## Chunk 2: Order Executor

### Task 3: OrderExecutor — Convert TradeOrders to Alpaca Orders

The `OrderExecutor` bridges the existing `ExecutionPlanGenerator` output (`TradeOrder` with symbol, type, allocation) to actual Alpaca API calls. It converts target allocations to share quantities based on current portfolio value and prices.

**Files:**
- Create: `tests/unit/fund/test_order_executor.py`
- Create: `src/fund/order_executor.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for the order executor."""

from decimal import Decimal
from unittest.mock import MagicMock

from fund.order_executor import OrderExecutor, ExecutedOrder


class TestOrderExecutor:
    def _make_broker(self):
        broker = MagicMock()
        broker.get_account.return_value = MagicMock(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        mock_order = MagicMock()
        mock_order.id = "order-1"
        mock_order.symbol = "NVDA"
        mock_order.side = "buy"
        mock_order.qty = Decimal("10")
        mock_order.order_type = "market"
        mock_order.status = "new"
        mock_order.filled_qty = Decimal("0")
        mock_order.filled_avg_price = None
        broker.submit_market_order.return_value = mock_order
        return broker

    def test_execute_buy_order(self):
        broker = self._make_broker()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        result = executor.execute_buy(
            symbol="NVDA",
            target_allocation=0.30,
            current_price=Decimal("850"),
            portfolio_value=Decimal("100000"),
        )

        assert result.symbol == "NVDA"
        assert result.side == "buy"
        assert result.qty > 0
        broker.submit_market_order.assert_called_once()
        journal.log.assert_called_once()

    def test_execute_sell_order(self):
        broker = self._make_broker()
        broker.submit_market_order.return_value.side = "sell"
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        result = executor.execute_sell(
            symbol="NVDA",
            qty=Decimal("10"),
            current_price=Decimal("850"),
        )

        assert result.side == "sell"
        broker.submit_market_order.assert_called_once()
        journal.log.assert_called_once()

    def test_execute_buy_calculates_shares_from_allocation(self):
        broker = self._make_broker()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        executor.execute_buy(
            symbol="NVDA",
            target_allocation=0.30,
            current_price=Decimal("850"),
            portfolio_value=Decimal("100000"),
        )

        # 30% of 100k = 30k / 850 = 35 shares (truncated to whole shares)
        call_args = broker.submit_market_order.call_args
        assert call_args.kwargs["qty"] == Decimal("35")

    def test_execute_buy_zero_allocation_skips(self):
        broker = self._make_broker()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        result = executor.execute_buy(
            symbol="NVDA",
            target_allocation=0.0,
            current_price=Decimal("850"),
            portfolio_value=Decimal("100000"),
        )

        assert result is None
        broker.submit_market_order.assert_not_called()

    def test_journal_entry_on_trade(self):
        broker = self._make_broker()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        executor.execute_buy(
            symbol="NVDA",
            target_allocation=0.30,
            current_price=Decimal("850"),
            portfolio_value=Decimal("100000"),
        )

        journal.log.assert_called_once()
        call_args = journal.log.call_args[0]
        assert call_args[0] == "trade_executed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/fund/test_order_executor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement OrderExecutor**

```python
"""Converts trading engine decisions into Alpaca API calls."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Optional


@dataclass
class ExecutedOrder:
    """Record of an order submitted to Alpaca."""
    order_id: str
    symbol: str
    side: str
    qty: Decimal
    order_type: str
    status: str


class OrderExecutor:
    """Bridges TradeOrder objects to Alpaca broker calls."""

    def __init__(self, broker, journal=None):
        self._broker = broker
        self._journal = journal

    def execute_buy(
        self,
        symbol: str,
        target_allocation: float,
        current_price: Decimal,
        portfolio_value: Decimal,
    ) -> Optional[ExecutedOrder]:
        target_value = portfolio_value * Decimal(str(target_allocation))
        qty = (target_value / current_price).to_integral_value(rounding=ROUND_DOWN)
        if qty <= 0:
            return None

        order = self._broker.submit_market_order(symbol=symbol, qty=qty, side="buy")
        result = ExecutedOrder(
            order_id=order.id,
            symbol=symbol,
            side="buy",
            qty=qty,
            order_type="market",
            status=str(order.status),
        )

        if self._journal:
            self._journal.log(
                "trade_executed",
                f"BUY {qty} {symbol} @ ~${current_price} ({target_allocation:.0%} allocation)",
                {"symbol": symbol, "side": "buy", "qty": float(qty),
                 "price": float(current_price), "allocation": target_allocation,
                 "order_id": order.id},
            )
        return result

    def execute_sell(
        self,
        symbol: str,
        qty: Decimal,
        current_price: Decimal,
    ) -> Optional[ExecutedOrder]:
        if qty <= 0:
            return None

        order = self._broker.submit_market_order(symbol=symbol, qty=qty, side="sell")
        result = ExecutedOrder(
            order_id=order.id,
            symbol=symbol,
            side="sell",
            qty=qty,
            order_type="market",
            status=str(order.status),
        )

        if self._journal:
            self._journal.log(
                "trade_executed",
                f"SELL {qty} {symbol} @ ~${current_price}",
                {"symbol": symbol, "side": "sell", "qty": float(qty),
                 "price": float(current_price), "order_id": order.id},
            )
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/fund/test_order_executor.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/order_executor.py tests/unit/fund/test_order_executor.py
git commit -m "feat(fund): order executor — allocation to shares, journal integration"
```

---

### Task 4: OrderExecutor — Execute Full Plan

**Files:**
- Modify: `tests/unit/fund/test_order_executor.py`
- Modify: `src/fund/order_executor.py`

- [ ] **Step 1: Write failing tests**

Add to `test_order_executor.py`:

```python
class TestExecutePlan:
    def test_execute_plan_sells_first_then_buys(self):
        """Sells should execute before buys to free up cash."""
        broker = MagicMock()
        order_counter = {"n": 0}

        def mock_submit(symbol=None, qty=None, side=None):
            order_counter["n"] += 1
            m = MagicMock()
            m.id = f"order-{order_counter['n']}"
            m.symbol = symbol
            m.side = side
            m.qty = str(qty)
            m.order_type = "market"
            m.status = "new"
            m.filled_qty = "0"
            m.filled_avg_price = None
            return m

        broker.submit_market_order.side_effect = mock_submit
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        current_positions = {"AAPL": Decimal("50"), "NVDA": Decimal("0")}
        current_prices = {"AAPL": Decimal("180"), "NVDA": Decimal("850")}

        # Sell AAPL (reduce), Buy NVDA (new position)
        trades = [
            {"symbol": "AAPL", "side": "SELL", "qty": Decimal("20")},
            {"symbol": "NVDA", "side": "BUY", "allocation": 0.25},
        ]

        results = executor.execute_plan(
            trades=trades,
            current_prices=current_prices,
            portfolio_value=Decimal("100000"),
        )

        assert len(results) == 2
        # Verify sells happened first (submit_market_order called with kwargs)
        calls = broker.submit_market_order.call_args_list
        assert calls[0].kwargs["side"] == "sell"
        assert calls[1].kwargs["side"] == "buy"

    def test_execute_plan_skips_zero_qty(self):
        broker = MagicMock()
        journal = MagicMock()
        executor = OrderExecutor(broker=broker, journal=journal)

        trades = [
            {"symbol": "NVDA", "side": "BUY", "allocation": 0.0},
        ]

        results = executor.execute_plan(
            trades=trades,
            current_prices={"NVDA": Decimal("850")},
            portfolio_value=Decimal("100000"),
        )

        assert len(results) == 0
        broker.submit_market_order.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/fund/test_order_executor.py::TestExecutePlan -v`
Expected: FAIL

- [ ] **Step 3: Implement `execute_plan`**

Add to `OrderExecutor`:

```python
    def execute_plan(
        self,
        trades: list,
        current_prices: dict,
        portfolio_value: Decimal,
    ) -> list:
        """Execute a list of trades. Sells first, then buys."""
        sells = [t for t in trades if t["side"] == "SELL"]
        buys = [t for t in trades if t["side"] == "BUY"]
        results = []

        for t in sells:
            result = self.execute_sell(
                symbol=t["symbol"],
                qty=t["qty"],
                current_price=current_prices[t["symbol"]],
            )
            if result:
                results.append(result)

        for t in buys:
            result = self.execute_buy(
                symbol=t["symbol"],
                target_allocation=t["allocation"],
                current_price=current_prices[t["symbol"]],
                portfolio_value=portfolio_value,
            )
            if result:
                results.append(result)

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/fund/test_order_executor.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/order_executor.py tests/unit/fund/test_order_executor.py
git commit -m "feat(fund): execute full trade plan — sells first, then buys"
```

---

## Chunk 3: Position Sync

### Task 5: PositionSync — Reconcile Alpaca with Fund Engine

**Files:**
- Create: `tests/unit/fund/test_position_sync.py`
- Create: `src/fund/position_sync.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for position synchronization between Alpaca and fund engine."""

from decimal import Decimal
from unittest.mock import MagicMock

from fund.position_sync import PositionSync, SyncResult


class TestPositionSync:
    def test_sync_returns_total_value(self):
        broker = MagicMock()
        broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"), market_value=Decimal("85000"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000")),
            MagicMock(symbol="AAPL", quantity=Decimal("50"), market_value=Decimal("9000"),
                      current_price=Decimal("180"), unrealized_pl=Decimal("500")),
        ]
        broker.get_account.return_value = MagicMock(cash=Decimal("6000"))

        sync = PositionSync(broker=broker)
        result = sync.sync()

        assert result.positions_value == Decimal("94000")
        assert result.cash == Decimal("6000")
        assert result.total_value == Decimal("100000")
        assert len(result.positions) == 2

    def test_sync_empty_portfolio(self):
        broker = MagicMock()
        broker.get_positions.return_value = []
        broker.get_account.return_value = MagicMock(cash=Decimal("100000"))

        sync = PositionSync(broker=broker)
        result = sync.sync()

        assert result.positions_value == Decimal("0")
        assert result.cash == Decimal("100000")
        assert result.total_value == Decimal("100000")

    def test_sync_detects_discrepancy(self):
        broker = MagicMock()
        broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"), market_value=Decimal("85000"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000")),
        ]
        broker.get_account.return_value = MagicMock(cash=Decimal("15000"))

        sync = PositionSync(broker=broker)
        result = sync.sync()

        # Check that we can compare with expected fund NAV
        expected_nav = Decimal("99000")
        discrepancy = result.total_value - expected_nav
        assert discrepancy == Decimal("1000")

    def test_positions_as_dict(self):
        broker = MagicMock()
        broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"), market_value=Decimal("85000"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000")),
        ]
        broker.get_account.return_value = MagicMock(cash=Decimal("15000"))

        sync = PositionSync(broker=broker)
        result = sync.sync()

        positions_dict = result.positions_by_symbol()
        assert "NVDA" in positions_dict
        assert positions_dict["NVDA"].quantity == Decimal("100")

    def test_sync_journals_event(self):
        broker = MagicMock()
        broker.get_positions.return_value = []
        broker.get_account.return_value = MagicMock(cash=Decimal("100000"))
        journal = MagicMock()

        sync = PositionSync(broker=broker, journal=journal)
        sync.sync()

        journal.log.assert_called_once()
        call_args = journal.log.call_args
        assert call_args[0][0] == "position_sync"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/fund/test_position_sync.py -v`
Expected: FAIL

- [ ] **Step 3: Implement PositionSync**

```python
"""Reconciles Alpaca positions with fund engine state."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class SyncResult:
    """Result of syncing positions from Alpaca."""
    positions: list  # List of BrokerPosition
    cash: Decimal
    positions_value: Decimal
    total_value: Decimal

    def positions_by_symbol(self) -> dict:
        return {p.symbol: p for p in self.positions}


class PositionSync:
    """Syncs Alpaca positions with fund engine for NAV calculation."""

    def __init__(self, broker, journal=None):
        self._broker = broker
        self._journal = journal

    def sync(self) -> SyncResult:
        positions = self._broker.get_positions()
        account = self._broker.get_account()

        positions_value = sum(p.market_value for p in positions)
        total_value = account.cash + positions_value

        result = SyncResult(
            positions=positions,
            cash=account.cash,
            positions_value=positions_value,
            total_value=total_value,
        )

        if self._journal:
            self._journal.log(
                "position_sync",
                f"Synced {len(positions)} positions, total value ${total_value:,.2f}",
                {
                    "positions_count": len(positions),
                    "positions_value": float(positions_value),
                    "cash": float(account.cash),
                    "total_value": float(total_value),
                    "symbols": [p.symbol for p in positions],
                },
            )

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/fund/test_position_sync.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/position_sync.py tests/unit/fund/test_position_sync.py
git commit -m "feat(fund): position sync — reconcile Alpaca positions with fund engine"
```

---

### Task 6: Update Exports

**Files:**
- Modify: `src/fund/__init__.py`

- [ ] **Step 1: Add new exports**

Add to `src/fund/__init__.py`:

```python
from fund.alpaca_broker import AlpacaBroker, AlpacaConfig, BrokerAccount, BrokerPosition, BrokerOrder
from fund.order_executor import OrderExecutor, ExecutedOrder
from fund.position_sync import PositionSync, SyncResult
```

Add all new names to `__all__`.

- [ ] **Step 2: Run all fund tests**

Run: `python3 -m pytest tests/unit/fund/ -v`
Expected: All tests PASS (existing 71 + new ~20)

- [ ] **Step 3: Commit**

```bash
git add src/fund/__init__.py
git commit -m "feat(fund): export alpaca broker, order executor, position sync"
```
