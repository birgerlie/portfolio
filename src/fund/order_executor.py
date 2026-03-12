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
