"""Broker data types shared between real and mock brokers."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional


@dataclass
class AlpacaConfig:
    """Alpaca API credentials and mode."""
    api_key: str
    secret_key: str
    paper: bool = True


@dataclass
class StreamConfig:
    """Configuration for Alpaca streaming connections."""
    portfolio_symbols: List[str] = field(default_factory=list)
    reference_symbols: List[str] = field(default_factory=list)
    macro_proxies: List[str] = field(default_factory=list)
    crypto_symbols: List[str] = field(default_factory=list)
    tracked_symbols: List[str] = field(default_factory=list)
    data_feed: str = "iex"

    @property
    def all_symbols(self) -> list:
        """Portfolio + reference + macro (backward compat)."""
        return sorted(set(self.portfolio_symbols + self.reference_symbols + self.macro_proxies))

    @property
    def all_stream_symbols(self) -> list:
        """All symbols to subscribe to (portfolio + reference + macro + tracked)."""
        return sorted(set(
            self.portfolio_symbols + self.reference_symbols +
            self.macro_proxies + self.tracked_symbols
        ))

    @property
    def all_crypto(self) -> list:
        return sorted(set(self.crypto_symbols))


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
