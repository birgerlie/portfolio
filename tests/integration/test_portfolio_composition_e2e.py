import pytest
import numpy as np
from trading_backtest.portfolio_composer import PortfolioComposer
from dataclasses import dataclass
from enum import Enum


# Mock Belief and BeliefType
class BeliefType(Enum):
    HIGH_GROWTH = "high_growth"
    STABLE = "stable"
    DECLINING = "declining"


@dataclass
class Belief:
    symbol: str
    field: str
    belief_type: BeliefType
    confidence: float


def test_portfolio_composition_from_beliefs():
    """End-to-end: convert epistemic beliefs to portfolio weights."""
    composer = PortfolioComposer()

    # H1 2025 beliefs based on actual market performance
    beliefs = {
        'NVDA': Belief('NVDA', 'return', BeliefType.HIGH_GROWTH, 0.88),
        'AVGO': Belief('AVGO', 'return', BeliefType.HIGH_GROWTH, 0.85),
        'NFLX': Belief('NFLX', 'return', BeliefType.STABLE, 0.80),
        'CRM': Belief('CRM', 'return', BeliefType.DECLINING, 0.75),
        'META': Belief('META', 'return', BeliefType.HIGH_GROWTH, 0.82),
    }

    weights = composer.compose(beliefs, strategy='kelly_monthly_rebalance')

    # Verify portfolio properties
    assert len(weights.allocations) == 5
    assert weights.strategy == 'kelly_monthly_rebalance'

    # Check weights constraints
    total_absolute = sum(abs(a.weight) for a in weights.allocations)
    assert 0.95 < total_absolute < 1.05  # Near 100%

    # Check individual caps
    for alloc in weights.allocations:
        assert abs(alloc.weight) <= 0.30

    # Verify long/short separation
    assert weights.total_long > 0
    assert weights.total_short > 0
    assert weights.net_exposure < 1.0
