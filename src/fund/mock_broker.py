"""Mock Alpaca broker for development and testing without API keys."""

import uuid
from decimal import Decimal
from typing import Dict, List, Optional

from fund.broker_types import BrokerAccount, BrokerOrder, BrokerPosition


class MockBroker:
    """Drop-in replacement for AlpacaBroker that simulates order execution in memory.

    Usage:
        broker = MockBroker(cash=Decimal("100000"))
        broker.seed_price("AAPL", Decimal("185.50"))
        order = broker.submit_market_order("AAPL", Decimal("10"), "buy")
    """

    def __init__(self, cash: Decimal = Decimal("100000")) -> None:
        self._cash = cash
        self._positions: Dict[str, _MockPosition] = {}
        self._orders: Dict[str, BrokerOrder] = {}
        self._prices: Dict[str, Decimal] = {}

    # ── setup helpers ────────────────────────────────────────────────────────

    def seed_price(self, symbol: str, price: Decimal) -> None:
        """Set the current market price for a symbol."""
        self._prices[symbol] = price

    def seed_prices(self, prices: Dict[str, Decimal]) -> None:
        """Set multiple prices at once."""
        self._prices.update(prices)

    def seed_position(self, symbol: str, qty: Decimal, avg_price: Decimal) -> None:
        """Pre-load a position (e.g. to simulate existing holdings)."""
        self._positions[symbol] = _MockPosition(
            symbol=symbol, qty=qty, avg_entry_price=avg_price,
        )
        if symbol not in self._prices:
            self._prices[symbol] = avg_price

    # ── AlpacaBroker-compatible interface ─────────────────────────────────────

    def get_account(self) -> BrokerAccount:
        equity = self._cash + sum(
            p.qty * self._prices.get(p.symbol, p.avg_entry_price)
            for p in self._positions.values()
        )
        return BrokerAccount(
            cash=self._cash,
            equity=equity,
            buying_power=self._cash,
            status="ACTIVE",
        )

    def is_connected(self) -> bool:
        return True

    def get_positions(self) -> List[BrokerPosition]:
        result = []
        for p in self._positions.values():
            if p.qty <= 0:
                continue
            price = self._prices.get(p.symbol, p.avg_entry_price)
            mv = p.qty * price
            cost = p.qty * p.avg_entry_price
            upl = mv - cost
            upl_pct = float(upl / cost) if cost else 0.0
            result.append(BrokerPosition(
                symbol=p.symbol,
                quantity=p.qty,
                market_value=mv,
                avg_entry_price=p.avg_entry_price,
                current_price=price,
                unrealized_pl=upl,
                unrealized_pl_pct=upl_pct,
            ))
        return result

    def submit_market_order(self, symbol: str, qty: Decimal, side: str) -> BrokerOrder:
        price = self._prices.get(symbol, Decimal("100"))
        return self._execute(symbol, qty, side, "market", price)

    def submit_limit_order(
        self, symbol: str, qty: Decimal, side: str, limit_price: Decimal,
    ) -> BrokerOrder:
        return self._execute(symbol, qty, side, "limit", limit_price)

    def get_order(self, order_id: str) -> BrokerOrder:
        if order_id not in self._orders:
            raise ValueError(f"Order {order_id} not found")
        return self._orders[order_id]

    def cancel_order(self, order_id: str) -> None:
        if order_id in self._orders:
            old = self._orders[order_id]
            self._orders[order_id] = BrokerOrder(
                id=old.id, symbol=old.symbol, side=old.side, qty=old.qty,
                order_type=old.order_type, limit_price=old.limit_price,
                status="canceled", filled_qty=Decimal("0"), filled_avg_price=None,
            )

    # ── internals ────────────────────────────────────────────────────────────

    def _execute(
        self, symbol: str, qty: Decimal, side: str, order_type: str, price: Decimal,
    ) -> BrokerOrder:
        oid = str(uuid.uuid4())

        if side == "buy":
            cost = qty * price
            self._cash -= cost
            if symbol in self._positions:
                p = self._positions[symbol]
                total_cost = p.qty * p.avg_entry_price + cost
                p.qty += qty
                p.avg_entry_price = total_cost / p.qty if p.qty else Decimal("0")
            else:
                self._positions[symbol] = _MockPosition(
                    symbol=symbol, qty=qty, avg_entry_price=price,
                )
        else:  # sell
            if symbol in self._positions:
                self._positions[symbol].qty -= qty
                if self._positions[symbol].qty <= 0:
                    del self._positions[symbol]
            self._cash += qty * price

        order = BrokerOrder(
            id=oid, symbol=symbol, side=side, qty=qty,
            order_type=order_type,
            limit_price=price if order_type == "limit" else None,
            status="filled", filled_qty=qty, filled_avg_price=price,
        )
        self._orders[oid] = order
        return order


class _MockPosition:
    __slots__ = ("symbol", "qty", "avg_entry_price")

    def __init__(self, symbol: str, qty: Decimal, avg_entry_price: Decimal) -> None:
        self.symbol = symbol
        self.qty = qty
        self.avg_entry_price = avg_entry_price
