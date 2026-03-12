import pytest
from trading_backtest.automation_controller import AutonomousController, ControllerState
from trading_backtest.regime import MarketRegime


def test_controller_full_pipeline():
    """AutonomousController orchestrates: regime → strategy → weights → execution."""
    controller = AutonomousController()

    # Current market data and beliefs
    market_metrics = {
        'avg_return': 0.15,
        'volatility': 0.15,
        'positive_pct': 0.75,
        'momentum': 0.20,
    }

    beliefs = {
        'NVDA': ('high_growth', 0.88),
        'AVGO': ('high_growth', 0.85),
        'NFLX': ('stable', 0.80),
    }

    result = controller.analyze(market_metrics, beliefs, strategy_hint='kelly_monthly_rebalance')

    assert result is not None
    assert hasattr(result, 'regime')
    assert hasattr(result, 'selected_strategy')
    assert hasattr(result, 'portfolio')
    assert hasattr(result, 'execution_plan')


def test_controller_detects_market_regime():
    """Controller correctly identifies market regime from metrics."""
    controller = AutonomousController()

    bull_metrics = {
        'avg_return': 0.15,
        'volatility': 0.15,
        'positive_pct': 0.75,
        'momentum': 0.20,
    }

    beliefs = {'NVDA': ('high_growth', 0.80)}

    result = controller.analyze(bull_metrics, beliefs)

    assert result.regime == MarketRegime.BULL


def test_controller_selects_best_strategy():
    """Controller selects highest-scoring strategy for regime."""
    controller = AutonomousController()

    metrics = {'avg_return': 0.15, 'volatility': 0.15, 'positive_pct': 0.75, 'momentum': 0.20}
    beliefs = {'NVDA': ('high_growth', 0.80), 'AVGO': ('high_growth', 0.75), 'NFLX': ('stable', 0.70)}

    result = controller.analyze(metrics, beliefs)

    # In bull market, kelly_monthly_rebalance should be selected
    assert result.selected_strategy.name == 'kelly_monthly_rebalance'
