# Belief Synthesizer Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use OpenAI to generate human-readable narratives from the epistemic engine's belief state. Wire the result into the gRPC server's `GetBeliefNarrative` RPC (currently a placeholder) and log narratives to the event journal.

**Architecture:** `BeliefSynthesizer` wraps the OpenAI chat completions API. It takes beliefs (from `EpistemicEngine`), positions, thermo state, and regime, then returns plain-English paragraphs. The gRPC server holds an optional synthesizer and calls it in `GetBeliefNarrative`. The journal logs each synthesis as a structured entry.

**Tech Stack:** `openai>=1.0` (already a transitive dep via trading stack), existing `EpistemicEngine`, `Belief`, `BeliefType`, `EventJournal`, `FundServiceServicer`, `fund_service_pb2`.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/fund/belief_synthesizer.py` | `BeliefSynthesizer` — OpenAI prompts, three synthesis methods |
| `src/fund/grpc_server.py` | Wire synthesizer into `GetBeliefNarrative` |
| `src/fund/__init__.py` | Export `BeliefSynthesizer` |
| `tests/unit/fund/test_belief_synthesizer.py` | Unit tests with mocked OpenAI |

---

## Chunk 1: BeliefSynthesizer Core

### Task 1.1: Write failing tests first

- [ ] Create `tests/unit/fund/test_belief_synthesizer.py`:

```python
"""Unit tests for BeliefSynthesizer — all OpenAI calls are mocked."""
from unittest.mock import MagicMock, patch
import pytest

from fund.belief_synthesizer import BeliefSynthesizer
from trading_backtest.epistemic import Belief, BeliefType


# ── fixtures ────────────────────────────────────────────────────────────────

def _make_synthesizer():
    return BeliefSynthesizer(api_key="test-key", model="gpt-4o-mini")


def _make_belief(symbol="AAPL", probability=0.72):
    b = Belief(
        symbol=symbol,
        attribute="valuation",
        belief_type=BeliefType.UNDERVALUED,
        probability=probability,
        confirmations=5,
        contradictions=1,
    )
    return b


def _mock_completion(text: str):
    """Return a minimal OpenAI completion mock."""
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── BeliefSynthesizer.__init__ ───────────────────────────────────────────────

def test_init_stores_model():
    bs = _make_synthesizer()
    assert bs.model == "gpt-4o-mini"


def test_init_custom_model():
    bs = BeliefSynthesizer(api_key="k", model="gpt-4o")
    assert bs.model == "gpt-4o"


# ── synthesize_weekly ────────────────────────────────────────────────────────

@patch("fund.belief_synthesizer.OpenAI")
def test_synthesize_weekly_calls_openai(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion("Weekly summary here.")

    bs = BeliefSynthesizer(api_key="k")
    beliefs = [_make_belief("AAPL"), _make_belief("MSFT", 0.6)]
    result = bs.synthesize_weekly(
        beliefs=beliefs,
        positions={"AAPL": {"allocation_pct": 0.25}, "MSFT": {"allocation_pct": 0.15}},
        thermo_state={"clarity_score": 0.8, "market_health": "green"},
        regime="bull",
    )

    assert result == "Weekly summary here."
    client.chat.completions.create.assert_called_once()
    call_kwargs = client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "gpt-4o-mini"


@patch("fund.belief_synthesizer.OpenAI")
def test_synthesize_weekly_empty_beliefs(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion("No active beliefs.")

    bs = BeliefSynthesizer(api_key="k")
    result = bs.synthesize_weekly(beliefs=[], positions={}, thermo_state={}, regime="unknown")
    assert isinstance(result, str)
    assert len(result) > 0


@patch("fund.belief_synthesizer.OpenAI")
def test_synthesize_weekly_openai_error_returns_fallback(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.side_effect = Exception("API error")

    bs = BeliefSynthesizer(api_key="k")
    result = bs.synthesize_weekly(beliefs=[], positions={}, thermo_state={}, regime="bull")
    assert "unavailable" in result.lower() or "error" in result.lower()


# ── synthesize_position ──────────────────────────────────────────────────────

@patch("fund.belief_synthesizer.OpenAI")
def test_synthesize_position_returns_string(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion("AAPL is undervalued.")

    bs = BeliefSynthesizer(api_key="k")
    result = bs.synthesize_position(
        symbol="AAPL",
        belief=_make_belief("AAPL"),
        position={"market_value": 50000, "unrealized_pl_pct": 0.12},
    )
    assert result == "AAPL is undervalued."


@patch("fund.belief_synthesizer.OpenAI")
def test_synthesize_position_no_belief(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion("No belief recorded.")

    bs = BeliefSynthesizer(api_key="k")
    result = bs.synthesize_position(symbol="TSLA", belief=None, position={})
    assert isinstance(result, str)


# ── synthesize_decision ──────────────────────────────────────────────────────

@patch("fund.belief_synthesizer.OpenAI")
def test_synthesize_decision_returns_string(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion("Bought AAPL because conviction rose.")

    bs = BeliefSynthesizer(api_key="k")
    result = bs.synthesize_decision(
        action={"type": "buy", "symbol": "AAPL", "quantity": 10, "price": 185.0},
        beliefs=[_make_belief("AAPL")],
        thermo={"clarity_score": 0.85, "market_health": "green"},
    )
    assert "AAPL" in result or isinstance(result, str)


@patch("fund.belief_synthesizer.OpenAI")
def test_synthesize_decision_sell_action(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_completion("Sold MSFT to reduce risk.")

    bs = BeliefSynthesizer(api_key="k")
    result = bs.synthesize_decision(
        action={"type": "sell", "symbol": "MSFT", "quantity": 5, "price": 380.0},
        beliefs=[],
        thermo={"clarity_score": 0.4, "market_health": "red"},
    )
    assert isinstance(result, str)


@patch("fund.belief_synthesizer.OpenAI")
def test_synthesize_decision_error_returns_fallback(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.side_effect = RuntimeError("timeout")

    bs = BeliefSynthesizer(api_key="k")
    result = bs.synthesize_decision(action={"type": "hold"}, beliefs=[], thermo={})
    assert isinstance(result, str)
```

- [ ] Verify tests fail (no implementation yet):

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/test_belief_synthesizer.py -v 2>&1 | head -20
# Expected: ModuleNotFoundError or ImportError
```

### Task 1.2: Implement BeliefSynthesizer

- [ ] Create `src/fund/belief_synthesizer.py`:

```python
"""OpenAI-powered narrative synthesis for the epistemic belief engine."""

from __future__ import annotations

import logging
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


class BeliefSynthesizer:
    """Generate human-readable narratives from the epistemic engine's belief state."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = OpenAI(api_key=api_key)
        self.model = model

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
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("BeliefSynthesizer OpenAI error: %s", exc)
            return fallback
```

- [ ] Verify tests pass:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/test_belief_synthesizer.py -v
```

- [ ] Commit:

```bash
cd /Users/birger/code/portfolio
git add src/fund/belief_synthesizer.py tests/unit/fund/test_belief_synthesizer.py
git commit -m "$(cat <<'EOF'
feat: add BeliefSynthesizer with OpenAI-powered narrative generation

Three synthesis methods (weekly, position, decision) with structured
prompts, graceful error fallback, and full unit test coverage via mocked
OpenAI client.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 2: gRPC Integration and Export

### Task 2.1: Wire synthesizer into GetBeliefNarrative

- [ ] Modify `src/fund/grpc_server.py` — update `__init__` to accept optional synthesizer and update the placeholder RPC:

```python
# In FundServiceServicer.__init__, add parameter after health:
#   belief_synthesizer=None
# Then store it:
#   self._synthesizer = belief_synthesizer

# Replace GetBeliefNarrative:
def GetBeliefNarrative(self, request, context):
    """Return belief state with optional OpenAI synthesis."""
    from fund.proto import fund_service_pb2

    # Build BeliefEntry list from engine state (passed via _epistemic_beliefs attr)
    beliefs_raw = getattr(self, "_epistemic_beliefs", {})
    entries = []
    for symbol, b in beliefs_raw.items():
        entries.append(fund_service_pb2.BeliefEntry(
            symbol=b.symbol,
            probability=b.probability,
            direction=b.belief_type.value,
            confirmations=b.confirmations,
            contradictions=b.contradictions,
            credibility_weighted=b.probability,  # raw probability as proxy
        ))

    synthesis = "Belief synthesis unavailable — no synthesizer configured."
    if self._synthesizer and entries:
        positions_raw = getattr(self, "_last_positions", {})
        thermo = {
            "clarity_score": self._thermo.clarity_score(),
            "market_health": self._thermo.market_health(),
        }
        regime = getattr(self._health.create_heartbeat(), "current_regime", "unknown")
        synthesis = self._synthesizer.synthesize_weekly(
            beliefs=list(beliefs_raw.values()),
            positions=positions_raw,
            thermo_state=thermo,
            regime=regime,
        )
        # Log to journal
        self._journal.log(
            entry_type="belief_narrative",
            summary=synthesis[:120],
            data={"full_text": synthesis},
        )

    return fund_service_pb2.BeliefReport(beliefs=entries, synthesis=synthesis)
```

Apply the edit:

```python
# In grpc_server.py __init__ signature, change:
#   def __init__(self, fund, members, broker, universe, journal, thermo, benchmarks, health):
# to:
#   def __init__(self, fund, members, broker, universe, journal, thermo, benchmarks, health, belief_synthesizer=None):
# Add after self._health = health:
#   self._synthesizer = belief_synthesizer
#   self._epistemic_beliefs = {}   # symbol -> Belief; set by engine
#   self._last_positions = {}      # symbol -> dict; set by engine
```

- [ ] Modify `src/fund/__init__.py` — add export:

```python
from fund.belief_synthesizer import BeliefSynthesizer
# Add "BeliefSynthesizer" to __all__
```

- [ ] Verify existing gRPC server tests still pass:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/test_grpc_server.py -v
```

- [ ] Run all belief synthesizer tests:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/test_belief_synthesizer.py tests/unit/fund/test_grpc_server.py -v
```

- [ ] Commit:

```bash
cd /Users/birger/code/portfolio
git add src/fund/grpc_server.py src/fund/__init__.py
git commit -m "$(cat <<'EOF'
feat: wire BeliefSynthesizer into GetBeliefNarrative gRPC RPC

Replaces the placeholder with real OpenAI synthesis when a synthesizer
is configured. Logs narrative to EventJournal. Synthesizer is optional
so existing deploys without an OpenAI key are unaffected.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Done Criteria

- [ ] `BeliefSynthesizer` has three public methods: `synthesize_weekly`, `synthesize_position`, `synthesize_decision`
- [ ] All OpenAI calls are wrapped with try/except returning a fallback string
- [ ] `GetBeliefNarrative` returns real synthesis when synthesizer is present, placeholder when not
- [ ] Journal receives a `belief_narrative` entry after each synthesis
- [ ] All unit tests pass: `pytest tests/unit/fund/test_belief_synthesizer.py -v`
- [ ] `BeliefSynthesizer` is exported from `fund.__init__`
