"""Recommendation generation using belief tracking."""

from datetime import datetime
from typing import List

from trading_backtest.backtest_runner import get_historical_returns
from trading_backtest.decision import StockAction, ActionType
from trading_backtest.epistemic import Belief, BeliefType, EpistemicEngine


def generate_candidates(
    symbols: List[str],
    month_date: datetime,
    epistemic_engine: EpistemicEngine,
) -> List[StockAction]:
    """Generate buy/sell candidates for symbols.

    Args:
        symbols: Stock symbols to evaluate
        month_date: Current month
        epistemic_engine: Engine for tracking beliefs

    Returns:
        List of StockAction candidates
    """
    candidates = []

    for symbol in symbols:
        success, exp_return, volatility = get_historical_returns(
            symbol, month_date
        )

        if not success:
            continue

        action = _create_action(symbol, exp_return, volatility)
        candidates.append(action)
        track_belief(symbol, exp_return, epistemic_engine)

    return candidates


def _create_action(
    symbol: str, exp_return: float, volatility: float
) -> StockAction:
    """Create StockAction from analysis.

    Args:
        symbol: Stock symbol
        exp_return: Expected return
        volatility: Volatility

    Returns:
        StockAction instance
    """
    action_type = ActionType.BUY if exp_return > 0 else ActionType.HOLD
    return StockAction(
        symbol=symbol,
        action_type=action_type,
        expected_return=exp_return,
        volatility=volatility,
        transaction_cost=0.001,
        tax_cost=0.0,
        liquidity_cost=0.0,
    )


def track_belief(
    symbol: str, expected_return: float, epistemic_engine: EpistemicEngine
) -> None:
    """Track stock belief using epistemic engine.

    Args:
        symbol: Stock symbol
        expected_return: Expected return from analysis
        epistemic_engine: Engine for tracking beliefs
    """
    belief_type = (
        BeliefType.HIGH_GROWTH if expected_return > 0.01
        else BeliefType.STABLE if expected_return > -0.01
        else BeliefType.DECLINING
    )

    belief = Belief(
        symbol=symbol,
        attribute="price_direction",
        belief_type=belief_type,
        probability=0.5,
    )

    is_confirmation = expected_return > 0
    epistemic_engine.update_belief(
        belief, source_name="market_data", confirmation=is_confirmation
    )
