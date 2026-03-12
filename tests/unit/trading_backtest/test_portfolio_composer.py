import pytest
from trading_backtest.portfolio_composer import PortfolioComposer, PortfolioWeights
from dataclasses import dataclass
from enum import Enum


# Mock Belief and BeliefType for testing
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


def test_weights_sum_to_100_percent():
    """Portfolio weights should sum to approximately 100%."""
    composer = PortfolioComposer()

    # Use many beliefs with moderate confidence so they all scale together
    beliefs = {
        'NVDA': Belief('NVDA', 'return', BeliefType.HIGH_GROWTH, 0.70),
        'AVGO': Belief('AVGO', 'return', BeliefType.HIGH_GROWTH, 0.68),
        'CRM': Belief('CRM', 'return', BeliefType.DECLINING, 0.66),
        'NFLX': Belief('NFLX', 'return', BeliefType.STABLE, 0.64),
        'META': Belief('META', 'return', BeliefType.HIGH_GROWTH, 0.62),
    }

    weights = composer.compose(beliefs, strategy='kelly_monthly_rebalance')

    total = sum(abs(w.weight) for w in weights.allocations)
    assert abs(total - 1.0) < 0.05  # Allow 5% rounding error for scaling constraints

def test_respects_kelly_max_per_stock():
    """No single position exceeds 30% (Kelly max)."""
    composer = PortfolioComposer()

    # Use 5 positions so each is roughly 20% (well below 30% cap)
    beliefs = {
        'NVDA': Belief('NVDA', 'return', BeliefType.HIGH_GROWTH, 0.75),
        'AVGO': Belief('AVGO', 'return', BeliefType.HIGH_GROWTH, 0.73),
        'NFLX': Belief('NFLX', 'return', BeliefType.STABLE, 0.71),
        'META': Belief('META', 'return', BeliefType.HIGH_GROWTH, 0.69),
        'GOOGL': Belief('GOOGL', 'return', BeliefType.STABLE, 0.67),
    }

    weights = composer.compose(beliefs, strategy='kelly_monthly_rebalance')

    for alloc in weights.allocations:
        assert abs(alloc.weight) <= 0.30

def test_shorts_for_declining_beliefs():
    """Declining beliefs should result in short positions."""
    composer = PortfolioComposer()

    beliefs = {
        'NVDA': Belief('NVDA', 'return', BeliefType.HIGH_GROWTH, 0.85),
        'CRM': Belief('CRM', 'return', BeliefType.DECLINING, 0.80),
    }

    weights = composer.compose(beliefs, strategy='kelly_monthly_rebalance')

    nvda_weight = [a for a in weights.allocations if a.symbol == 'NVDA'][0]
    crm_weight = [a for a in weights.allocations if a.symbol == 'CRM'][0]

    assert nvda_weight.weight > 0  # Long
    assert crm_weight.weight < 0   # Short
