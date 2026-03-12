import pytest
import numpy as np
from trading_backtest.regime import RegimeDetector


def test_regime_detection_from_real_data():
    """Test regime detection from simulated market data."""
    detector = RegimeDetector()

    # Simulate H1 2025 bull market returns
    # NVDA +69%, AVGO +63%, NFLX +50%, META +46%, GOOGL +42%
    returns = [0.69, 0.63, 0.50, 0.46, 0.42]

    # Calculate metrics
    avg_return = np.mean(returns)
    volatility = np.std(returns)
    positive_count = sum(1 for r in returns if r > 0)
    positive_pct = positive_count / len(returns)

    metrics = {
        'avg_return': avg_return,
        'volatility': volatility,
        'positive_pct': positive_pct,
        'momentum': avg_return,  # simplified
    }

    regime = detector.classify(metrics)

    # H1 2025 was bullish: all stocks up, high returns
    assert regime.value == "bull"
    assert avg_return > 0.4  # Strong bull market
    assert positive_pct == 1.0  # All stocks up
