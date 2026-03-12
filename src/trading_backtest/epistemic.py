"""Epistemic engine for probabilistic belief system with credibility weighting."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from trading_backtest.credibility import CredibilityTracker, SourceCredibility


class BeliefType(Enum):
    """Enumeration of belief types."""

    UNDERVALUED = "undervalued"
    OVERVALUED = "overvalued"
    HIGH_GROWTH = "high_growth"
    STABLE = "stable"
    DECLINING = "declining"
    RECOVERY = "recovery"


@dataclass
class Belief:
    """Probabilistic belief about a stock attribute."""

    symbol: str
    attribute: str
    belief_type: BeliefType
    probability: float = 0.5
    confirmations: int = 0
    contradictions: int = 0
    sources: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def add_confirmation(self, source_name: str, credibility: float) -> None:
        """Record a confirmation from a source."""
        self.confirmations += 1
        if source_name not in self.sources:
            self.sources[source_name] = {"confirmations": 0, "contradictions": 0}
        self.sources[source_name]["confirmations"] += 1

    def add_contradiction(self, source_name: str, credibility: float) -> None:
        """Record a contradiction from a source."""
        self.contradictions += 1
        if source_name not in self.sources:
            self.sources[source_name] = {"confirmations": 0, "contradictions": 0}
        self.sources[source_name]["contradictions"] += 1

    def remove_source(self, source_name: str) -> None:
        """Remove all contributions from a source."""
        if source_name in self.sources:
            source_data = self.sources[source_name]
            self.confirmations -= source_data["confirmations"]
            self.contradictions -= source_data["contradictions"]
            del self.sources[source_name]


class EpistemicEngine:
    """Maintain beliefs with credibility-weighted Bayesian updates."""

    # Laplace smoothing constant
    LAPLACE_SMOOTHING = 1.0

    # Fraud credibility threshold
    FRAUD_THRESHOLD = 0.30

    def __init__(self):
        """Initialize epistemic engine."""
        self.tracker = CredibilityTracker()
        self._beliefs: Dict[str, Belief] = {}

    def add_belief(self, belief: Belief) -> None:
        """Register a belief for tracking."""
        key = f"{belief.symbol}:{belief.attribute}"
        self._beliefs[key] = belief

    def _get_belief_key(self, belief: Belief) -> str:
        """Generate cache key for belief."""
        return f"{belief.symbol}:{belief.attribute}"

    def update_belief(
        self,
        belief: Belief,
        source_name: str,
        confirmation: bool,
    ) -> None:
        """Update belief probability with credibility-weighted Bayesian update.

        P(belief) = (α + Σ cred(s) × conf) / (α + Σ cred(s) × conf + contra)
        """
        # Track belief if not already tracked
        key = self._get_belief_key(belief)
        if key not in self._beliefs:
            self.add_belief(belief)

        if confirmation:
            belief.add_confirmation(source_name, credibility=0.0)
        else:
            belief.add_contradiction(source_name, credibility=0.0)

        self._recompute_probability(belief)

    def _recompute_probability(self, belief: Belief) -> None:
        """Recompute probability using credibility-weighted formula.

        P(belief) = (α + Σ cred(s) × conf) / (α + Σ cred(s) × (conf + contra))
        Both confirmations and contradictions are weighted by source credibility.
        """
        weighted_confirms = self._compute_weighted_sum(
            belief, is_confirmation=True
        )
        weighted_contradicts = self._compute_weighted_sum(
            belief, is_confirmation=False
        )

        numerator = self.LAPLACE_SMOOTHING + weighted_confirms
        denominator = (
            self.LAPLACE_SMOOTHING
            + weighted_confirms
            + weighted_contradicts
        )

        belief.probability = numerator / denominator if denominator > 0 else 0.5

    def _compute_weighted_sum(
        self, belief: Belief, is_confirmation: bool
    ) -> float:
        """Compute weighted sum of confirmations or contradictions."""
        weighted_sum = 0.0

        for source_name, counts in belief.sources.items():
            source = self.tracker.get_source(source_name)
            if not source:
                continue

            credibility = source.credibility
            if is_confirmation:
                weighted_sum += credibility * counts["confirmations"]
            else:
                weighted_sum += credibility * counts["contradictions"]

        return weighted_sum

    def discount_fraudster(self, fraudster_name: str) -> None:
        """Remove fraudster's contributions from all beliefs.

        Treats fraudster's claims as invalid by tracking them as contradictions.
        """
        # Find all beliefs touched by fraudster
        affected_beliefs = self._find_beliefs_by_source(fraudster_name)

        fraudster = self.tracker.get_source(fraudster_name)

        for belief in affected_beliefs:
            if fraudster_name in belief.sources:
                fraudster_data = belief.sources[fraudster_name]

                # Remove their original contributions
                belief.confirmations -= fraudster_data["confirmations"]
                belief.contradictions -= fraudster_data["contradictions"]

                # Invert confirmations to contradictions in sources
                # (keep their low credibility to down-weight them)
                belief.sources[fraudster_name] = {
                    "confirmations": 0,
                    "contradictions": fraudster_data["confirmations"],
                }

            self._recompute_probability(belief)

    def _find_beliefs_by_source(self, source_name: str) -> list:
        """Find all beliefs that include this source."""
        affected = []
        for belief in self._beliefs.values():
            if source_name in belief.sources:
                affected.append(belief)
        return affected

    def detect_anomaly(self, belief: Belief) -> Dict[str, any]:
        """Detect anomalies in belief confidence without updating."""
        evidence_count = belief.confirmations + belief.contradictions
        confidence = belief.probability

        # Anomaly: high confidence with sparse evidence
        is_anomaly = confidence > 0.80 and evidence_count < 3

        return {
            "is_anomaly": is_anomaly,
            "confidence": confidence,
            "evidence_count": evidence_count,
            "source_count": len(belief.sources),
        }
