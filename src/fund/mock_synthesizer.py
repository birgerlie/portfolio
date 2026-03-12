"""Mock belief synthesizer for development without an OpenAI API key."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trading_backtest.epistemic import Belief


class MockSynthesizer:
    """Drop-in replacement for BeliefSynthesizer that generates deterministic narratives.

    Usage:
        synth = MockSynthesizer()
        text = synth.synthesize_weekly(beliefs, positions, thermo, regime)
    """

    def __init__(self, api_key: str = "mock", model: str = "mock") -> None:
        self.model = model

    def synthesize_weekly(
        self,
        beliefs: List[Belief],
        positions: Dict[str, Any],
        thermo_state: Dict[str, Any],
        regime: str,
    ) -> str:
        n_beliefs = len(beliefs)
        n_positions = len(positions)
        clarity = thermo_state.get("clarity_score", "n/a")
        health = thermo_state.get("market_health", "n/a")

        symbols = ", ".join(b.symbol for b in beliefs[:5]) or "none"
        high_conviction = [b for b in beliefs if b.probability >= 0.7]

        lines = [
            f"The fund is operating in a {regime} regime with {n_positions} active positions.",
            f"Epistemic clarity stands at {clarity} with market health rated {health}.",
            f"The system holds {n_beliefs} active beliefs across {symbols}.",
        ]
        if high_conviction:
            top = high_conviction[0]
            lines.append(
                f"Highest conviction: {top.symbol} at {top.probability:.0%} "
                f"({top.belief_type.value}, +{top.confirmations}/-{top.contradictions})."
            )
        else:
            lines.append("No positions currently exceed the 70% conviction threshold.")

        return " ".join(lines)

    def synthesize_position(
        self,
        symbol: str,
        belief: Optional[Belief],
        position: Dict[str, Any],
    ) -> str:
        mv = position.get("market_value", "unknown")
        pl = position.get("unrealized_pl_pct", 0)

        if belief:
            return (
                f"{symbol}: {belief.belief_type.value} conviction at {belief.probability:.0%} "
                f"(+{belief.confirmations}/-{belief.contradictions}). "
                f"Market value ${mv}, unrealised P&L {pl:+.1%}."
            )
        return f"{symbol}: no epistemic belief recorded. Market value ${mv}."

    def synthesize_decision(
        self,
        action: Dict[str, Any],
        beliefs: List[Belief],
        thermo: Dict[str, Any],
    ) -> str:
        action_type = action.get("type", "unknown")
        symbol = action.get("symbol", "unknown")
        qty = action.get("quantity", "?")
        price = action.get("price", "market")
        clarity = thermo.get("clarity_score", "n/a")

        relevant = {b.symbol: b for b in beliefs}
        if symbol in relevant:
            b = relevant[symbol]
            reason = f"{b.belief_type.value} belief at {b.probability:.0%}"
        else:
            reason = "no active belief"

        return (
            f"{action_type.upper()} {qty} {symbol} @ {price} — "
            f"{reason}, clarity {clarity}."
        )
