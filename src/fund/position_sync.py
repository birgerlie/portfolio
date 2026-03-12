"""Reconciles Alpaca positions with fund engine state."""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional


@dataclass
class SyncResult:
    """Result of syncing positions from Alpaca."""
    positions: list  # List of BrokerPosition
    cash: Decimal
    positions_value: Decimal
    total_value: Decimal

    def positions_by_symbol(self) -> dict:
        return {p.symbol: p for p in self.positions}


class PositionSync:
    """Syncs Alpaca positions with fund engine for NAV calculation."""

    def __init__(self, broker, journal=None):
        self._broker = broker
        self._journal = journal

    def sync(self) -> SyncResult:
        positions = self._broker.get_positions()
        account = self._broker.get_account()

        positions_value = sum((p.market_value for p in positions), Decimal("0"))
        total_value = account.cash + positions_value

        result = SyncResult(
            positions=positions,
            cash=account.cash,
            positions_value=positions_value,
            total_value=total_value,
        )

        if self._journal:
            self._journal.log(
                "position_sync",
                f"Synced {len(positions)} positions, total value ${total_value:,.2f}",
                {
                    "positions_count": len(positions),
                    "positions_value": float(positions_value),
                    "cash": float(account.cash),
                    "total_value": float(total_value),
                    "symbols": [p.symbol for p in positions],
                },
            )

        return result
