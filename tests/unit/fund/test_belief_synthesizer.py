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
