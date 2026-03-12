import pytest
from trading_backtest.execution_generator import ExecutionPlanGenerator
from trading_backtest.portfolio_composer import Allocation, PortfolioWeights


def test_end_to_end_execution_planning():
    """Generate execution plan from portfolio rebalancing scenario."""
    generator = ExecutionPlanGenerator()

    # Current state: holding some positions
    current_portfolio = {
        'NVDA': 0.15,   # currently 15%
        'AVGO': 0.10,   # currently 10%
        'CRM': -0.08,   # short 8%
        'NFLX': 0.0,    # not holding
    }

    # Target: rebalance based on new market regime
    target_weights = PortfolioWeights(
        allocations=[
            Allocation('NVDA', 0.25, 'high_growth', 0.88),  # increase
            Allocation('AVGO', 0.15, 'high_growth', 0.85),  # increase
            Allocation('CRM', -0.03, 'declining', 0.75),    # reduce short
            Allocation('NFLX', 0.12, 'stable', 0.80),       # add new
        ],
        total_long=0.52,
        total_short=0.03,
        net_exposure=0.49,
        strategy='kelly_monthly_rebalance',
    )

    current_prices = {
        'NVDA': 875,
        'AVGO': 180,
        'CRM': 130,
        'NFLX': 250,
    }

    plan = generator.generate(target_weights, current_portfolio, current_prices)

    # Verify plan structure
    assert len(plan.trades) >= 3
    assert plan.strategy == 'kelly_monthly_rebalance'
    assert plan.total_long == 0.52
    assert plan.total_short == 0.03
    assert 0.7 < plan.confidence <= 1.0
    assert plan.cash_impact > 0

    # Verify sell orders come before buy orders
    sell_indices = [i for i, t in enumerate(plan.trades) if t.type == 'SELL']
    buy_indices = [i for i, t in enumerate(plan.trades) if t.type == 'BUY']

    if sell_indices and buy_indices:
        assert max(sell_indices) <= min(buy_indices)  # All sells before buys
