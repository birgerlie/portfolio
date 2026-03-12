import pytest
from trading_backtest.strategy_selector import StrategySelector, StrategyScore
from trading_backtest.regime import MarketRegime

def test_score_kelly_monthly_for_bull():
    """Kelly + monthly rebalance scores highest in bull market."""
    selector = StrategySelector()
    bull_metrics = {
        'return': 0.15,
        'sharpe': 1.5,
        'max_drawdown': -0.08,
    }
    scores = selector.score_all_strategies(MarketRegime.BULL, bull_metrics)

    kelly_monthly = [s for s in scores if s.name == 'kelly_monthly_rebalance'][0]
    equal_weight = [s for s in scores if s.name == 'equal_weight'][0]

    assert kelly_monthly.score > equal_weight.score

def test_score_inverse_hedge_for_bear():
    """Inverse hedge scores higher in bear market."""
    selector = StrategySelector()
    bear_metrics = {
        'return': -0.05,
        'sharpe': -0.5,
        'max_drawdown': -0.25,
    }
    scores = selector.score_all_strategies(MarketRegime.BEAR, bear_metrics)

    kelly_inverse = [s for s in scores if s.name == 'kelly_inverse_hedge'][0]
    equal_weight = [s for s in scores if s.name == 'equal_weight'][0]

    assert kelly_inverse.score > equal_weight.score

def test_returns_all_seven_strategies():
    """Selector returns exactly 7 strategies, ranked by score."""
    selector = StrategySelector()
    bull_metrics = {'return': 0.15, 'sharpe': 1.5, 'max_drawdown': -0.08}
    scores = selector.score_all_strategies(MarketRegime.BULL, bull_metrics)

    assert len(scores) == 7
    assert all(isinstance(s, StrategyScore) for s in scores)
    # Scores should be descending
    for i in range(len(scores) - 1):
        assert scores[i].score >= scores[i+1].score
