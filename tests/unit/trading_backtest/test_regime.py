import pytest
from trading_backtest.regime import RegimeDetector, MarketRegime

def test_detect_bull_regime():
    """Bull: high returns (>10%), positive majority (>60%), low volatility (<20%)"""
    detector = RegimeDetector()
    metrics = {
        'avg_return': 0.15,      # +15%
        'volatility': 0.15,       # 15%
        'positive_pct': 0.75,     # 75% of stocks up
        'momentum': 0.20,         # +20% vs prior month
    }
    regime = detector.classify(metrics)
    assert regime == MarketRegime.BULL

def test_detect_bear_regime():
    """Bear: negative returns (<-5%), majority down (<40%), high volatility (>25%)"""
    detector = RegimeDetector()
    metrics = {
        'avg_return': -0.10,      # -10%
        'volatility': 0.30,       # 30%
        'positive_pct': 0.25,     # 25% up
        'momentum': -0.15,        # -15%
    }
    regime = detector.classify(metrics)
    assert regime == MarketRegime.BEAR

def test_detect_transition_regime():
    """Transition: mixed signals (5-10% return, 40-60% positive)"""
    detector = RegimeDetector()
    metrics = {
        'avg_return': 0.07,       # +7%
        'volatility': 0.18,       # 18%
        'positive_pct': 0.55,     # 55% up
        'momentum': 0.05,         # +5%
    }
    regime = detector.classify(metrics)
    assert regime == MarketRegime.TRANSITION

def test_detect_consolidation_regime():
    """Consolidation: very low returns (<2%), balanced (45-55%), low volatility"""
    detector = RegimeDetector()
    metrics = {
        'avg_return': 0.01,       # +1%
        'volatility': 0.10,       # 10%
        'positive_pct': 0.50,     # 50% up
        'momentum': 0.00,         # flat
    }
    regime = detector.classify(metrics)
    assert regime == MarketRegime.CONSOLIDATION
