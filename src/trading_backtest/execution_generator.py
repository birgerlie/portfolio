from dataclasses import dataclass
from typing import Dict, List
from trading_backtest.portfolio_composer import PortfolioWeights


@dataclass
class TradeOrder:
    """Single trade execution order."""
    symbol: str
    type: str              # BUY or SELL
    allocation: float      # target weight
    confidence: float      # 0-1 confidence in this trade
    reason: str            # why this trade is being made


@dataclass
class ExecutionPlan:
    """Complete execution plan for portfolio rebalancing."""
    trades: List[TradeOrder]
    strategy: str          # strategy name
    total_long: float      # total long exposure
    total_short: float     # total short exposure
    confidence: float      # overall plan confidence (0-1)
    cash_impact: float     # estimated cash impact


class ExecutionPlanGenerator:
    """Generates actionable buy/sell orders from portfolio weights."""

    def generate(self, target_weights: PortfolioWeights,
                 current_portfolio: Dict[str, float],
                 current_prices: Dict[str, float]) -> ExecutionPlan:
        """
        Convert target portfolio weights into execution orders.
        Sells losers first, then buys winners.
        """
        trades = []

        # Separate into sells and buys
        sells = []
        buys = []

        for alloc in target_weights.allocations:
            symbol = alloc.symbol
            target_weight = alloc.weight
            current_weight = current_portfolio.get(symbol, 0.0)

            if target_weight < current_weight:
                # Sell: reduce or close position
                sells.append((symbol, target_weight, current_weight, alloc.confidence, alloc.belief_type))
            elif target_weight > current_weight:
                # Buy: increase or open position
                buys.append((symbol, target_weight, current_weight, alloc.confidence, alloc.belief_type))

        # Generate sell orders first
        for symbol, target, current, confidence, belief_type in sells:
            delta = abs(target - current)
            trades.append(TradeOrder(
                symbol=symbol,
                type='SELL',
                allocation=target,
                confidence=confidence,
                reason=f"Reduce {symbol} from {current:.1%} to {target:.1%} ({belief_type})",
            ))

        # Then generate buy orders
        for symbol, target, current, confidence, belief_type in buys:
            delta = abs(target - current)
            trades.append(TradeOrder(
                symbol=symbol,
                type='BUY',
                allocation=target,
                confidence=confidence,
                reason=f"Increase {symbol} from {current:.1%} to {target:.1%} ({belief_type})",
            ))

        # Calculate execution metrics
        cash_impact = sum(
            current_prices.get(t.symbol, 0) * abs(t.allocation)
            for t in trades
        )

        # Average confidence across all trades
        avg_confidence = (
            sum(t.confidence for t in trades) / len(trades)
            if trades else 0.0
        )

        return ExecutionPlan(
            trades=trades,
            strategy=target_weights.strategy,
            total_long=target_weights.total_long,
            total_short=target_weights.total_short,
            confidence=avg_confidence,
            cash_impact=cash_impact,
        )
