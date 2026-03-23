"""Alpaca WebSocket → SourceRecord adapter.

Converts Alpaca trade, quote, and fill events into SourceRecord format
for the ORM pipeline. Does NOT manage the WebSocket connection.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Optional

from silicondb.sources.models import SourceRecord


class AlpacaSourceAdapter:
    """Converts Alpaca SDK events to SourceRecords."""

    def __init__(self, symbols: list[str], max_age_seconds: Optional[float] = None):
        self._symbols = set(symbols)
        self._max_age = max_age_seconds

    def trade_to_record(self, trade: Any) -> Optional[SourceRecord]:
        ts = self._extract_timestamp(trade)
        if ts is not None and self._max_age is not None and self._is_stale(ts):
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
        return self._max_age is not None and (time.time() - ts) > self._max_age

    @staticmethod
    def _key(prefix: str, symbol: str, unique: Any) -> str:
        raw = f"{prefix}:{symbol}:{unique}"
        return hashlib.md5(raw.encode()).hexdigest()
