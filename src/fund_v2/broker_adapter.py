"""Adapts approved actions from the action feed to Alpaca broker calls."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

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
