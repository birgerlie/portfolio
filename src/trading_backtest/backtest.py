"""Backtesting framework for portfolio simulation."""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List
import statistics


@dataclass
class Position:
    """Represents a single stock position."""

    symbol: str
    quantity: float
    entry_price: float
    entry_date: date
    current_price: float = 0.0

    @property
    def cost_basis(self) -> float:
        """Total cost to acquire position."""
        return self.quantity * self.entry_price

    @property
    def market_value(self) -> float:
        """Current market value of position."""
        return self.quantity * self.current_price

    @property
    def gain(self) -> float:
        """Unrealized gain/loss in dollars."""
        return self.market_value - self.cost_basis

    @property
    def return_pct(self) -> float:
        """Unrealized return as percentage."""
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price


@dataclass
class Trade:
    """Record of a buy or sell transaction."""

    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: float
    date: date


@dataclass
class Backtester:
    """Portfolio backtester for simulation and metrics."""

    initial_capital: float
    cash: float = field(init=False)
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)

    def __post_init__(self):
        """Initialize cash from initial capital."""
        self.cash = self.initial_capital

    def buy(self, symbol: str, quantity: float, price: float, date: date) -> None:
        """Execute a buy order."""
        cost = quantity * price
        self.cash -= cost

        if symbol in self.positions:
            pos = self.positions[symbol]
            # Update average cost basis
            total_qty = pos.quantity + quantity
            total_cost = pos.cost_basis + cost
            pos.quantity = total_qty
            pos.entry_price = total_cost / total_qty
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
                entry_date=date,
                current_price=price,
            )

        self.trades.append(Trade(symbol=symbol, side="BUY", quantity=quantity, price=price, date=date))

    def sell(self, symbol: str, quantity: float, price: float, date: date) -> None:
        """Execute a sell order."""
        proceeds = quantity * price
        self.cash += proceeds

        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.quantity -= quantity
            if pos.quantity <= 0:
                del self.positions[symbol]

        self.trades.append(Trade(symbol=symbol, side="SELL", quantity=quantity, price=price, date=date))

    def update_price(self, symbol: str, price: float) -> None:
        """Update current price for a position."""
        if symbol in self.positions:
            self.positions[symbol].current_price = price

    @property
    def portfolio_value(self) -> float:
        """Total portfolio value (cash + positions)."""
        positions_value = sum(pos.market_value for pos in self.positions.values())
        return self.cash + positions_value

    @property
    def total_gain(self) -> float:
        """Sum of all unrealized gains."""
        return sum(pos.gain for pos in self.positions.values())

    def calculate_monthly_returns(self, portfolio_values: List[float]) -> List[float]:
        """Calculate monthly returns from portfolio values."""
        if len(portfolio_values) < 2:
            return []

        returns = []
        for i in range(1, len(portfolio_values)):
            prev_value = portfolio_values[i - 1]
            curr_value = portfolio_values[i]
            if prev_value > 0:
                monthly_return = (curr_value - prev_value) / prev_value
                returns.append(monthly_return)

        return returns

    def calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """Calculate Sharpe ratio from returns."""
        if len(returns) < 2:
            return 0.0

        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)

        if std_return == 0:
            return 0.0

        return mean_return / std_return

    def calculate_max_drawdown(self, portfolio_values: List[float]) -> float:
        """Calculate maximum drawdown from peak to trough."""
        if len(portfolio_values) < 2:
            return 0.0

        max_dd = 0.0
        peak = portfolio_values[0]

        for value in portfolio_values[1:]:
            if value > peak:
                peak = value
            else:
                drawdown = (peak - value) / peak
                max_dd = max(max_dd, drawdown)

        return max_dd
