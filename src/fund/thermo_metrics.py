"""Plain-language thermodynamic metrics for the dashboard."""
import math
from typing import Dict


class ThermoMetrics:
    SIGMA_GREEN = 0.25
    SIGMA_YELLOW = 0.40
    SIGMA_CRIT = 0.50
    MOMENTUM_THRESHOLD = 0.03

    def _shannon_entropy(self, p: float) -> float:
        if p <= 0 or p >= 1:
            return 0.0
        return -p * math.log(p) - (1 - p) * math.log(1 - p)

    def clarity_score(self, beliefs: Dict[str, float]) -> float:
        if not beliefs:
            return 0.0
        # Clarity based on conviction distance from 0.5 (neutral)
        # High conviction (near 0 or 1) = high clarity
        # Near 0.5 = low clarity
        convictions = [abs(p - 0.5) for p in beliefs.values()]
        avg_conviction = sum(convictions) / len(convictions)
        clarity = avg_conviction * 100 * 2  # Scale to 0-100
        return max(0.0, min(100.0, clarity))

    def opportunity_score(self, beliefs: Dict[str, float], volatility: float) -> float:
        if not beliefs:
            return 0.0
        avg_conviction = sum(abs(p - 0.5) for p in beliefs.values()) / len(beliefs)
        avg_entropy = sum(self._shannon_entropy(p) for p in beliefs.values()) / len(beliefs)
        phi = avg_conviction - volatility * avg_entropy
        score = (phi + 0.3) / 0.8 * 100
        return max(0.0, min(100.0, score))

    def market_health(self, volatility: float) -> str:
        if volatility < self.SIGMA_GREEN:
            return "green"
        elif volatility < self.SIGMA_YELLOW:
            return "yellow"
        return "red"

    def momentum(self, prev_beliefs: Dict[str, float], curr_beliefs: Dict[str, float]) -> str:
        common = set(prev_beliefs) & set(curr_beliefs)
        if not common:
            return "steady"
        avg_dp = sum(curr_beliefs[s] - prev_beliefs[s] for s in common) / len(common)
        if avg_dp > self.MOMENTUM_THRESHOLD:
            return "rising"
        elif avg_dp < -self.MOMENTUM_THRESHOLD:
            return "falling"
        return "steady"

    def interpret(self, clarity: float, opportunity: float, health: str, momentum: str) -> str:
        if clarity > 70 and opportunity > 60 and health == "green":
            return "High conviction, good opportunity, calm market. System is running at full capacity."
        elif clarity > 50 and health in ("green", "yellow"):
            return "Moderate conviction with some uncertainty. System is selectively positioned."
        elif health == "red":
            return "Dangerous market conditions. System has moved to minimum exposure."
        elif clarity < 30:
            return "Mixed signals, limited opportunity. System is sizing positions conservatively."
        return f"Clarity at {clarity:.0f}%, opportunity at {opportunity:.0f}. Market health: {health}. Momentum: {momentum}."
