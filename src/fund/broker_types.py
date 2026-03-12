"""Broker data types shared between real and mock brokers."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


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
