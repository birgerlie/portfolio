from enum import Enum
from dataclasses import dataclass
from typing import Dict


class MarketRegime(Enum):
    """Market regime classification."""
    BULL = "bull"
    BEAR = "bear"
    TRANSITION = "transition"
    CONSOLIDATION = "consolidation"


@dataclass
class MarketMetrics:
    """Metrics for regime detection."""
    avg_return: float          # average return across stocks
    volatility: float          # portfolio volatility
    positive_pct: float        # % of stocks with positive returns
    momentum: float            # momentum signal (current vs prior)


class RegimeDetector:
    """Detects market regime from price/belief metrics."""

    def classify(self, metrics: Dict[str, float]) -> MarketRegime:
        """
        Classify market regime based on metrics.

        Returns: MarketRegime enum value
        """
        avg_ret = metrics['avg_return']
        vol = metrics['volatility']
        pos_pct = metrics['positive_pct']

        # Bull: high returns, positive majority, lower volatility
        if avg_ret > 0.10 and pos_pct > 0.60 and vol < 0.20:
            return MarketRegime.BULL

        # Bear: negative returns, majority down, high volatility
        if avg_ret < -0.05 and pos_pct < 0.40 and vol > 0.25:
            return MarketRegime.BEAR

        # Consolidation: minimal returns, balanced, low volatility
        if -0.02 <= avg_ret <= 0.02 and 0.45 <= pos_pct <= 0.55 and vol < 0.12:
            return MarketRegime.CONSOLIDATION

        # Transition: everything else
        return MarketRegime.TRANSITION
