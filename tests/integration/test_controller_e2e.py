import pytest
from trading_backtest.automation_controller import AutonomousController
from trading_backtest.regime import MarketRegime


def test_full_autonomous_pipeline():
    """End-to-end: from market data to execution plan."""
    controller = AutonomousController()

    # H1 2025 bull market conditions
    market_metrics = {
        'avg_return': 0.38,
        'volatility': 0.18,  # Must be < 0.20 for BULL classification
        'positive_pct': 0.90,
        'momentum': 0.38,
    }

    # Epistemic beliefs from analysis
    beliefs = {
        'NVDA': ('high_growth', 0.88),
        'AVGO': ('high_growth', 0.85),
        'NFLX': ('stable', 0.80),
        'META': ('high_growth', 0.82),
        'CRM': ('declining', 0.75),
    }

    # Current holdings
    current_portfolio = {
        'NVDA': 0.15,
        'AVGO': 0.10,
        'CRM': -0.05,
    }

    current_prices = {
        'NVDA': 875,
        'AVGO': 180,
        'NFLX': 250,
        'META': 500,
        'CRM': 130,
    }

    # Run full pipeline
    result = controller.analyze(
        market_metrics, beliefs,
        current_portfolio=current_portfolio,
        current_prices=current_prices,
    )

    # Verify pipeline outputs
    assert result.regime == MarketRegime.BULL
    assert result.selected_strategy.name == 'kelly_monthly_rebalance'
    assert len(result.portfolio.allocations) >= 3
    assert len(result.execution_plan.trades) >= 1
    assert result.confidence > 0.7

    # Verify execution plan has actionable orders
    assert any(t.type == 'SELL' for t in result.execution_plan.trades) or any(t.type == 'BUY' for t in result.execution_plan.trades)
