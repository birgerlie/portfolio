"""Thin adapter around Alpaca's TradingClient."""

from decimal import Decimal
from typing import List, Optional

from alpaca.trading.client import TradingClient

from fund.broker_types import AlpacaConfig, BrokerAccount, BrokerPosition, BrokerOrder


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
        from alpaca.trading.enums import TimeInForce
        req = MarketOrderRequest(symbol=symbol, qty=float(qty), side=side, time_in_force=TimeInForce.DAY)
        return self._to_broker_order(self._client.submit_order(req))

    def submit_limit_order(self, symbol: str, qty: Decimal, side: str, limit_price: Decimal) -> BrokerOrder:
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import TimeInForce
        req = LimitOrderRequest(symbol=symbol, qty=float(qty), side=side, limit_price=float(limit_price), time_in_force=TimeInForce.DAY)
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
