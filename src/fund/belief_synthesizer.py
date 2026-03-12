"""OpenAI-powered narrative synthesis for the epistemic belief engine."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from trading_backtest.epistemic import Belief

logger = logging.getLogger(__name__)

_WEEKLY_SYSTEM = (
    "You are a concise quantitative fund analyst. "
    "Write one paragraph (4-6 sentences) summarising the fund's epistemic belief state, "
    "market regime, and key conviction positions. "
    "Be factual, not promotional. Use plain English."
)

_POSITION_SYSTEM = (
    "You are a concise quantitative fund analyst. "
    "Write one or two sentences explaining the epistemic conviction for a single position. "
    "Include the probability, confirmation/contradiction ratio, and P&L context."
)

_DECISION_SYSTEM = (
    "You are a concise quantitative fund analyst. "
    "Write one sentence explaining why this trade was executed, grounded in beliefs and market conditions."
)


class _DiskCache:
    """Simple content-hash disk cache for synthesis results."""

    def __init__(self, cache_dir: str = "/tmp/fund-synthesis-cache"):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, system: str, prompt: str) -> str:
        h = hashlib.sha256(f"{system}\n---\n{prompt}".encode()).hexdigest()[:16]
        return h

    def get(self, system: str, prompt: str) -> Optional[str]:
        path = self._dir / f"{self._key(system, prompt)}.txt"
        if path.exists():
            return path.read_text()
        return None

    def put(self, system: str, prompt: str, result: str) -> None:
        path = self._dir / f"{self._key(system, prompt)}.txt"
        path.write_text(result)


class BeliefSynthesizer:
    """Generate human-readable narratives from the epistemic engine's belief state."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", cache: bool = True) -> None:
        self._client = OpenAI(api_key=api_key)
        self.model = model
        self._cache = _DiskCache() if cache else None

    # ── public API ──────────────────────────────────────────────────────────

    def synthesize_weekly(
        self,
        beliefs: List[Belief],
        positions: Dict[str, Any],
        thermo_state: Dict[str, Any],
        regime: str,
    ) -> str:
        """Generate a weekly portfolio narrative paragraph."""
        prompt = self._weekly_prompt(beliefs, positions, thermo_state, regime)
        return self._complete(_WEEKLY_SYSTEM, prompt, fallback="Belief synthesis unavailable.")

    def synthesize_position(
        self,
        symbol: str,
        belief: Optional[Belief],
        position: Dict[str, Any],
    ) -> str:
        """Generate a per-position conviction narrative."""
        prompt = self._position_prompt(symbol, belief, position)
        return self._complete(_POSITION_SYSTEM, prompt, fallback=f"No synthesis available for {symbol}.")

    def synthesize_decision(
        self,
        action: Dict[str, Any],
        beliefs: List[Belief],
        thermo: Dict[str, Any],
    ) -> str:
        """Explain a trading decision in one sentence."""
        prompt = self._decision_prompt(action, beliefs, thermo)
        return self._complete(_DECISION_SYSTEM, prompt, fallback="Decision rationale unavailable.")

    # ── prompt builders ─────────────────────────────────────────────────────

    def _weekly_prompt(
        self,
        beliefs: List[Belief],
        positions: Dict[str, Any],
        thermo: Dict[str, Any],
        regime: str,
    ) -> str:
        belief_lines = "\n".join(
            f"  - {b.symbol}: {b.belief_type.value}, p={b.probability:.2f}, "
            f"+{b.confirmations}/-{b.contradictions}"
            for b in beliefs
        ) or "  (none)"

        position_lines = "\n".join(
            f"  - {sym}: {int(data.get('allocation_pct', 0) * 100)}% allocation"
            for sym, data in positions.items()
        ) or "  (none)"

        return (
            f"Regime: {regime}\n"
            f"Thermo: clarity={thermo.get('clarity_score', 'n/a')}, "
            f"market_health={thermo.get('market_health', 'n/a')}\n"
            f"Active beliefs:\n{belief_lines}\n"
            f"Positions:\n{position_lines}\n"
            "Write the weekly belief narrative."
        )

    def _position_prompt(
        self,
        symbol: str,
        belief: Optional[Belief],
        position: Dict[str, Any],
    ) -> str:
        if belief:
            belief_str = (
                f"belief_type={belief.belief_type.value}, "
                f"probability={belief.probability:.2f}, "
                f"confirmations={belief.confirmations}, "
                f"contradictions={belief.contradictions}"
            )
        else:
            belief_str = "no belief recorded"

        return (
            f"Symbol: {symbol}\n"
            f"Belief: {belief_str}\n"
            f"Market value: {position.get('market_value', 'n/a')}\n"
            f"Unrealised P&L: {position.get('unrealized_pl_pct', 'n/a')}\n"
            "Write the position conviction narrative."
        )

    def _decision_prompt(
        self,
        action: Dict[str, Any],
        beliefs: List[Belief],
        thermo: Dict[str, Any],
    ) -> str:
        relevant = {b.symbol: b for b in beliefs}
        symbol = action.get("symbol", "")
        belief_str = "no belief"
        if symbol in relevant:
            b = relevant[symbol]
            belief_str = f"p={b.probability:.2f}, {b.belief_type.value}"

        return (
            f"Action: {action.get('type', 'unknown')} {action.get('quantity', '')} "
            f"{symbol} @ {action.get('price', 'market')}\n"
            f"Belief: {belief_str}\n"
            f"Thermo: clarity={thermo.get('clarity_score', 'n/a')}, "
            f"health={thermo.get('market_health', 'n/a')}\n"
            "Explain this trade in one sentence."
        )

    # ── internal ─────────────────────────────────────────────────────────────

    def _complete(self, system: str, user: str, fallback: str) -> str:
        # Check cache first
        if self._cache:
            cached = self._cache.get(system, user)
            if cached is not None:
                logger.debug("Cache hit for synthesis request")
                return cached

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=300,
                temperature=0.4,
            )
            result = resp.choices[0].message.content.strip()

            # Cache the result
            if self._cache:
                self._cache.put(system, user, result)

            return result
        except Exception as exc:
            logger.warning("BeliefSynthesizer OpenAI error: %s", exc)
            return fallback
