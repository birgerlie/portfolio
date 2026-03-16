"""Thread-safe price cache updated by Alpaca websocket streams."""

import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional


@dataclass
class PriceEntry:
    symbol: str
    price: Decimal
    bid: Optional[Decimal]
    ask: Optional[Decimal]
    spread: Optional[Decimal]
    vwap: Decimal
    trade_count: int
    total_volume: Decimal
    last_trade_ts: Optional[datetime]
    last_quote_ts: Optional[datetime]
    prev_price: Optional[Decimal] = None

    def is_stale(self, max_age_seconds: float, now: Optional[datetime] = None) -> bool:
        """Return True if the most recent timestamp is older than max_age_seconds."""
        if now is None:
            now = datetime.now(tz=timezone.utc)
        timestamps = [ts for ts in (self.last_trade_ts, self.last_quote_ts) if ts is not None]
        if not timestamps:
            return True
        most_recent = max(timestamps)
        age = (now - most_recent).total_seconds()
        return age > max_age_seconds

    @property
    def price_return(self) -> Optional[float]:
        """Compute (current - previous) / previous, or None if no previous price."""
        if self.prev_price is None:
            return None
        return float((self.price - self.prev_price) / self.prev_price)


class PriceCache:
    """Thread-safe store of PriceEntry objects, keyed by symbol."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Internal accumulator state for VWAP: symbol -> (cumulative_pv, cumulative_volume)
        self._vwap_state: dict[str, tuple[Decimal, Decimal]] = {}
        self._entries: dict[str, PriceEntry] = {}

    def update_trade(
        self,
        symbol: str,
        price: Decimal,
        size: Decimal,
        timestamp: "datetime | float",
    ) -> None:
        """Update price, running VWAP, trade count, and total volume for symbol.

        *timestamp* may be a :class:`datetime` (timezone-aware) or a Unix
        timestamp float (will be converted to UTC datetime automatically).
        """
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        with self._lock:
            existing = self._entries.get(symbol)
            if existing is not None:
                prev_price = existing.price
                trade_count = existing.trade_count + 1
                total_volume = existing.total_volume + size
                bid = existing.bid
                ask = existing.ask
                spread = existing.spread
                last_quote_ts = existing.last_quote_ts
            else:
                prev_price = None
                trade_count = 1
                total_volume = size
                bid = None
                ask = None
                spread = None
                last_quote_ts = None

            # Running VWAP
            prev_pv, prev_vol = self._vwap_state.get(symbol, (Decimal("0"), Decimal("0")))
            cum_pv = prev_pv + price * size
            cum_vol = prev_vol + size
            vwap = cum_pv / cum_vol
            self._vwap_state[symbol] = (cum_pv, cum_vol)

            self._entries[symbol] = PriceEntry(
                symbol=symbol,
                price=price,
                bid=bid,
                ask=ask,
                spread=spread,
                vwap=vwap,
                trade_count=trade_count,
                total_volume=total_volume,
                last_trade_ts=timestamp,
                last_quote_ts=last_quote_ts,
                prev_price=prev_price,
            )

    def update_quote(
        self,
        symbol: str,
        bid: Decimal,
        ask: Decimal,
        timestamp: datetime,
    ) -> None:
        """Update bid, ask, and spread for symbol."""
        with self._lock:
            existing = self._entries.get(symbol)
            spread = ask - bid
            if existing is not None:
                self._entries[symbol] = PriceEntry(
                    symbol=symbol,
                    price=existing.price,
                    bid=bid,
                    ask=ask,
                    spread=spread,
                    vwap=existing.vwap,
                    trade_count=existing.trade_count,
                    total_volume=existing.total_volume,
                    last_trade_ts=existing.last_trade_ts,
                    last_quote_ts=timestamp,
                    prev_price=existing.prev_price,
                )
            else:
                self._entries[symbol] = PriceEntry(
                    symbol=symbol,
                    price=Decimal("0"),
                    bid=bid,
                    ask=ask,
                    spread=spread,
                    vwap=Decimal("0"),
                    trade_count=0,
                    total_volume=Decimal("0"),
                    last_trade_ts=None,
                    last_quote_ts=timestamp,
                    prev_price=None,
                )

    def get(self, symbol: str) -> Optional[PriceEntry]:
        """Return a copy of the PriceEntry for symbol, or None if not tracked."""
        with self._lock:
            entry = self._entries.get(symbol)
            if entry is None:
                return None
            return copy.copy(entry)

    def relative_return(self, symbol: str, benchmark: str) -> Optional[float]:
        """Return symbol price_return minus benchmark price_return, or None if either is unavailable."""
        sym_entry = self.get(symbol)
        bench_entry = self.get(benchmark)
        if sym_entry is None or bench_entry is None:
            return None
        sym_ret = sym_entry.price_return
        bench_ret = bench_entry.price_return
        if sym_ret is None or bench_ret is None:
            return None
        return sym_ret - bench_ret

    def all_symbols(self) -> list[str]:
        """Return a list of all tracked symbols."""
        with self._lock:
            return list(self._entries.keys())

    def snapshot(self) -> dict[str, PriceEntry]:
        """Return a dict of copies of all PriceEntry objects."""
        with self._lock:
            return {symbol: copy.copy(entry) for symbol, entry in self._entries.items()}
