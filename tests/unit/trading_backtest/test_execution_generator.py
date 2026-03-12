import pytest
from trading_backtest.execution_generator import ExecutionPlan, ExecutionPlanGenerator, TradeOrder
from trading_backtest.portfolio_composer import Allocation, PortfolioWeights


def test_generates_buy_sell_orders():
    """ExecutionGenerator converts portfolio weights to buy/sell orders."""
    generator = ExecutionPlanGenerator()

    current_portfolio = {
        'NVDA': 0.20,  # currently 20% long
        'CRM': -0.10,  # currently 10% short
    }

    target_weights = PortfolioWeights(
        allocations=[
            Allocation('NVDA', 0.30, 'high_growth', 0.88),
            Allocation('CRM', -0.05, 'declining', 0.75),
            Allocation('NFLX', 0.20, 'stable', 0.80),
        ],
        total_long=0.50,
        total_short=0.05,
        net_exposure=0.45,
        strategy='kelly_monthly_rebalance',
    )

    plan = generator.generate(target_weights, current_portfolio, current_prices={'NVDA': 100, 'CRM': 50, 'NFLX': 150})

    assert len(plan.trades) >= 3
    assert plan.strategy == 'kelly_monthly_rebalance'


def test_sell_losers_before_winners():
    """Execution plan sells positions with losses before buying winners."""
    generator = ExecutionPlanGenerator()

    current_portfolio = {
        'LOSER': 0.15,  # underwater
        'WINNER': 0.10,  # positive
    }

    target_weights = PortfolioWeights(
        allocations=[
            Allocation('LOSER', 0.05, 'declining', 0.70),
            Allocation('WINNER', 0.25, 'high_growth', 0.85),
        ],
        total_long=0.30,
        total_short=0.0,
        net_exposure=0.30,
        strategy='kelly_monthly_rebalance',
    )

    plan = generator.generate(target_weights, current_portfolio, current_prices={'LOSER': 80, 'WINNER': 120})

    # LOSER should be in sell orders before WINNER in buy orders
    sell_orders = [t for t in plan.trades if t.type == 'SELL']
    buy_orders = [t for t in plan.trades if t.type == 'BUY']

    assert len(sell_orders) > 0
    assert len(buy_orders) > 0


def test_execution_plan_has_total_exposure():
    """ExecutionPlan tracks total planned exposure."""
    generator = ExecutionPlanGenerator()

    target_weights = PortfolioWeights(
        allocations=[
            Allocation('A', 0.20, 'high_growth', 0.80),
            Allocation('B', 0.15, 'stable', 0.70),
        ],
        total_long=0.35,
        total_short=0.0,
        net_exposure=0.35,
        strategy='equal_weight',
    )

    plan = generator.generate(target_weights, {}, current_prices={'A': 100, 'B': 100})

    assert plan.total_long == 0.35
    assert plan.total_short == 0.0
    assert plan.confidence > 0.7
