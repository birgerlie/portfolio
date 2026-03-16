"""QuoteAggregator — windowed quote batching with thread-safe flush."""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Dict, List, Optional


class QuoteAggregator:
    """Accumulates bid/ask quotes per symbol within a time window.

    Call record() as quotes arrive, then flush() at the end of each window
    to obtain aggregated statistics and reset state.
    """

    def __init__(self, window_seconds: float = 1.0) -> None:
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._data: Dict[str, _SymbolBucket] = {}

    def record(
        self,
        symbol: str,
        bid: float,
        ask: float,
        timestamp: datetime,
    ) -> None:
        """Store the latest bid/ask and accumulate spread statistics."""
        with self._lock:
            if symbol not in self._data:
                self._data[symbol] = _SymbolBucket()
            self._data[symbol].update(bid, ask, timestamp)

    def symbols(self) -> List[str]:
        """Return list of symbols that have pending (unflushed) quotes."""
        with self._lock:
            return list(self._data.keys())

    def flush(self) -> Dict[str, dict]:
        """Return aggregated stats for all symbols and clear internal state.

        Returns:
            Dict keyed by symbol, each value containing:
                latest_bid, latest_ask, mean_spread,
                min_spread, max_spread, quote_count
        """
        with self._lock:
            result = {symbol: bucket.to_dict() for symbol, bucket in self._data.items()}
            self._data.clear()
        return result


class _SymbolBucket:
    """Internal accumulator for a single symbol."""

    def __init__(self) -> None:
        self.latest_bid: float = 0.0
        self.latest_ask: float = 0.0
        self.spreads: List[float] = []
        self.quote_count: int = 0
        self.latest_timestamp: Optional[datetime] = None

    def update(self, bid: float, ask: float, timestamp: datetime) -> None:
        self.latest_bid = bid
        self.latest_ask = ask
        self.spreads.append(ask - bid)
        self.quote_count += 1
        self.latest_timestamp = timestamp

    def to_dict(self) -> dict:
        spreads = self.spreads
        return {
            "latest_bid": self.latest_bid,
            "latest_ask": self.latest_ask,
            "mean_spread": sum(spreads) / len(spreads),
            "min_spread": min(spreads),
            "max_spread": max(spreads),
            "quote_count": self.quote_count,
        }
