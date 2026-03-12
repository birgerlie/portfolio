import pytest
from trading_backtest.strategy_selector import StrategySelector
from trading_backtest.regime import RegimeDetector, MarketRegime

def test_strategy_selection_pipeline():
    """Full pipeline: detect regime → score strategies → recommend best."""
    detector = RegimeDetector()
    selector = StrategySelector()

    # Bull market metrics
    bull_metrics = {
        'avg_return': 0.15,
        'volatility': 0.15,
        'positive_pct': 0.75,
        'momentum': 0.20,
    }

    # Detect regime
    regime = detector.classify(bull_metrics)
    assert regime == MarketRegime.BULL

    # Score strategies for this regime
    scores = selector.score_all_strategies(regime, bull_metrics)
    best_strategy = scores[0]

    # Best strategy for bull should be kelly_monthly_rebalance
    assert best_strategy.name == 'kelly_monthly_rebalance'
    assert best_strategy.score > 70
    assert best_strategy.confidence > 0.8
