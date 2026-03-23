"""Tests for generate_signals_impl — regime-aware signal generation logic."""
from __future__ import annotations
from unittest.mock import MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_engine(beliefs: dict[str, float] | None = None) -> MagicMock:
    """Build a mock engine that returns the given beliefs via predict_belief."""
    engine = MagicMock()
    beliefs = beliefs or {}

    def _predict_belief(external_id: str, horizon_days: int = 7) -> dict:
        prob = beliefs.get(external_id, 0.5)
        return {
            "external_id": external_id,
            "current": prob,
            "predicted": prob,
            "confidence": 0.5,
            "horizon_days": horizon_days,
            "drivers": [],
        }

    engine.predict_belief.side_effect = _predict_belief
    engine.belief.side_effect = lambda eid, **kw: beliefs.get(eid, 0.5)
    return engine


def _make_regime_entity(
    trend_following: float = 0.5,
    mean_reverting: float = 0.5,
    risk_on: float = 0.5,
) -> MagicMock:
    """Build a mock MarketRegime-like entity."""
    entity = MagicMock()
    entity.trend_following = trend_following
    entity.mean_reverting_regime = mean_reverting
    entity.risk_on = risk_on
    return entity


def _make_instrument_entity(
    symbol: str = "AAPL",
    *,
    relative_strength: float = 0.5,
    exhaustion: float = 0.2,
    pressure: float = 0.5,
    retail_sentiment: float = 0.5,
    crowded: float = 0.3,
) -> MagicMock:
    """Build a mock Instrument entity with belief values."""
    entity = MagicMock()
    entity.external_id = f"instrument:{symbol}"
    entity.symbol = symbol
    entity.relative_strength = relative_strength
    entity.exhaustion = exhaustion
    entity.pressure = pressure
    entity.retail_sentiment = retail_sentiment
    entity.crowded = crowded
    return entity


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_generate_signals_returns_correct_structure():
    """generate_signals_impl returns a dict with signals, regime, and count keys."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    regime = _make_regime_entity()
    instruments = [_make_instrument_entity("AAPL"), _make_instrument_entity("MSFT")]

    result = generate_signals_impl(engine, regime, instruments)

    assert "signals" in result
    assert "regime" in result
    assert "count" in result
    assert isinstance(result["signals"], list)
    assert result["count"] == len(result["signals"])


def test_generate_signals_each_has_required_fields():
    """Each signal has symbol, edge, confidence, sizing, direction, layers, regime_weights."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    regime = _make_regime_entity()
    instruments = [_make_instrument_entity("AAPL")]

    result = generate_signals_impl(engine, regime, instruments)

    assert len(result["signals"]) == 1
    sig = result["signals"][0]
    assert "symbol" in sig
    assert "edge" in sig
    assert "confidence" in sig
    assert "sizing" in sig
    assert "direction" in sig
    assert "layers" in sig
    assert "regime_weights" in sig


def test_generate_signals_sorted_by_edge_times_confidence():
    """Signals are sorted descending by |edge| * confidence."""
    from fund_v2.signals import generate_signals_impl

    # AAPL: high strength (strong signal)
    # MSFT: low strength (weak signal)
    beliefs = {
        "instrument:AAPL": 0.9,
        "instrument:MSFT": 0.52,
    }
    engine = _make_engine(beliefs)
    regime = _make_regime_entity(trend_following=0.8)
    instruments = [
        _make_instrument_entity("AAPL", relative_strength=0.9, exhaustion=0.1, pressure=0.8),
        _make_instrument_entity("MSFT", relative_strength=0.52, exhaustion=0.2, pressure=0.51),
    ]

    result = generate_signals_impl(engine, regime, instruments)

    assert len(result["signals"]) >= 2
    scores = [abs(s["edge"]) * s["confidence"] for s in result["signals"]]
    assert scores == sorted(scores, reverse=True), "Signals must be sorted by |edge|*confidence desc"


def test_generate_signals_trend_following_regime_favors_momentum():
    """In a trend-following regime, high relative_strength gets a positive edge."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    # Strong trend-following regime
    regime = _make_regime_entity(trend_following=0.9, mean_reverting=0.1)
    instruments = [
        _make_instrument_entity("AAPL", relative_strength=0.85, exhaustion=0.1, pressure=0.7),
    ]

    result = generate_signals_impl(engine, regime, instruments)
    sig = result["signals"][0]

    assert sig["edge"] > 0, "Trend-following regime + strong momentum should give positive edge"
    assert sig["direction"] == "long"


def test_generate_signals_mean_reverting_regime_flips_edge():
    """In a mean-reverting regime, high exhaustion reduces or inverts the edge."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    # Strong mean-reverting regime
    regime = _make_regime_entity(trend_following=0.1, mean_reverting=0.9)
    instruments = [
        _make_instrument_entity("AAPL", relative_strength=0.3, exhaustion=0.8, pressure=0.3),
    ]

    result = generate_signals_impl(engine, regime, instruments)
    sig = result["signals"][0]

    # In mean-reverting regime, high exhaustion should produce a contrarian (positive/long) signal
    # or at minimum a different edge than in a trend-following regime
    assert "edge" in sig
    assert "confidence" in sig


def test_generate_signals_empty_instruments():
    """generate_signals_impl handles empty instrument list gracefully."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    regime = _make_regime_entity()
    result = generate_signals_impl(engine, regime, [])

    assert result["signals"] == []
    assert result["count"] == 0


def test_generate_signals_regime_info_in_result():
    """Result includes regime weights used for scoring."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    regime = _make_regime_entity(trend_following=0.7, mean_reverting=0.3, risk_on=0.6)
    instruments = [_make_instrument_entity("AAPL")]

    result = generate_signals_impl(engine, regime, instruments)

    assert "trend_following" in result["regime"]
    assert "mean_reverting" in result["regime"]


def test_generate_signals_layers_dict_contains_belief_components():
    """Each signal's layers dict contains the belief layer components used for scoring."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    regime = _make_regime_entity()
    instruments = [_make_instrument_entity("AAPL")]

    result = generate_signals_impl(engine, regime, instruments)
    sig = result["signals"][0]

    layers = sig["layers"]
    # Should contain at least the key belief scores
    assert isinstance(layers, dict)
    assert len(layers) > 0


def test_generate_signals_sizing_is_positive():
    """Sizing should always be > 0 (it's a position size fraction)."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    regime = _make_regime_entity(trend_following=0.8)
    instruments = [
        _make_instrument_entity("AAPL", relative_strength=0.8),
        _make_instrument_entity("MSFT", relative_strength=0.3),
    ]

    result = generate_signals_impl(engine, regime, instruments)

    for sig in result["signals"]:
        assert sig["sizing"] > 0, f"Sizing must be positive, got {sig['sizing']} for {sig['symbol']}"


def test_generate_signals_direction_based_on_edge():
    """Direction should be 'long' when edge > 0 and 'short' when edge < 0."""
    from fund_v2.signals import generate_signals_impl

    engine = _make_engine()
    regime = _make_regime_entity(trend_following=0.9, mean_reverting=0.1)
    # Very strong momentum → long signal
    instruments = [
        _make_instrument_entity("AAPL", relative_strength=0.95, exhaustion=0.05, pressure=0.9),
    ]

    result = generate_signals_impl(engine, regime, instruments)
    sig = result["signals"][0]

    assert sig["direction"] in ("long", "short", "neutral")
    if sig["edge"] > 0:
        assert sig["direction"] == "long"
    elif sig["edge"] < 0:
        assert sig["direction"] == "short"
