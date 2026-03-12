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
