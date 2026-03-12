from dataclasses import dataclass
from typing import Dict, List
import numpy as np


@dataclass
class Allocation:
    """Single stock allocation."""
    symbol: str
    weight: float              # -1.0 to +1.0 (negative = short)
    belief_type: str           # HIGH_GROWTH, STABLE, DECLINING, etc.
    confidence: float          # 0-1 confidence in this allocation


@dataclass
class PortfolioWeights:
    """Complete portfolio allocation."""
    allocations: List[Allocation]
    total_long: float          # sum of positive weights
    total_short: float         # sum of absolute short weights
    net_exposure: float        # long - short
    strategy: str              # which strategy generated this


class PortfolioComposer:
    """Composes portfolio weights from epistemic beliefs using Kelly Criterion."""

    KELLY_MAX = 0.30           # Max 30% per position
    MIN_CONVICTION = 0.50      # Min confidence to trade

    def compose(self, beliefs: Dict, strategy: str) -> PortfolioWeights:
        """
        Compose portfolio from beliefs using Kelly Criterion.
        Returns weights: sum(|weights|) = 1.0, each |weight| <= 0.30.
        """
        allocations = []

        # Step 1: Calculate Kelly sizes
        for symbol, belief in beliefs.items():
            if belief.confidence < self.MIN_CONVICTION:
                continue

            kelly_size = (2 * belief.confidence - 1)

            # Skip negligible signals
            if abs(kelly_size) < 0.05:
                continue

            belief_type_str = belief.belief_type.value if hasattr(belief.belief_type, 'value') else str(belief.belief_type).lower()

            if 'declining' in belief_type_str:
                kelly_size = -kelly_size

            allocations.append(Allocation(
                symbol=symbol,
                weight=kelly_size,
                belief_type=belief_type_str,
                confidence=belief.confidence,
            ))

        # Step 2: Scale so max Kelly size is KELLY_MAX
        max_kelly = max((abs(a.weight) for a in allocations), default=1.0)
        if max_kelly > self.KELLY_MAX:
            scale = self.KELLY_MAX / max_kelly
            for alloc in allocations:
                alloc.weight = alloc.weight * scale

        # Step 3: Normalize to sum to 1.0
        total_absolute = sum(abs(a.weight) for a in allocations)
        if total_absolute > 0:
            for alloc in allocations:
                alloc.weight = alloc.weight / total_absolute

        # Calculate portfolio metrics
        long_sum = sum(a.weight for a in allocations if a.weight > 0)
        short_sum = sum(abs(a.weight) for a in allocations if a.weight < 0)

        return PortfolioWeights(
            allocations=allocations,
            total_long=long_sum,
            total_short=short_sum,
            net_exposure=long_sum - short_sum,
            strategy=strategy,
        )