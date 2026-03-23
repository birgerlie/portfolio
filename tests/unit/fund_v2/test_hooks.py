"""Entity lifecycle hooks — propagation, Layer 2 derivation, prediction reactions."""
from unittest.mock import MagicMock, call

import pytest

import fund_v2.hooks as hooks_module
from fund_v2.hooks import (
    propagate_on_trade,
    cooccurrence_tracking,
    update_relative_strength,
    update_exhaustion,
    propagate_sector_pressure,
    propagate_macro_pressure,
    update_crowded,
    sector_rotation_log,
    portfolio_health_change,
    conviction_flip_warning,
    macro_regime_shift_predicted,
    sector_rotation_predicted,
    regime_shift_predicted,
    sentiment_surge_predicted,
)
from silicondb.orm.hooks import collect_hooks_from_module


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def app(mock_engine):
    """ORM App with MockEngine — same fixture as in conftest."""
    from silicondb.orm import App
    return App(mock_engine, internal_db_url="sqlite:///:memory:")


# ── Test 1: collect_hooks_finds_all ──────────────────────────────────────────

def test_collect_hooks_finds_all():
    """All 14 decorated hook functions are discoverable via collect_hooks_from_module."""
    found = collect_hooks_from_module(hooks_module)
    names = {h["callback"].__name__ for h in found}
    expected = {
        "propagate_on_trade",
        "cooccurrence_tracking",
        "update_relative_strength",
        "update_exhaustion",
        "propagate_sector_pressure",
        "propagate_macro_pressure",
        "update_crowded",
        "sector_rotation_log",
        "portfolio_health_change",
        "conviction_flip_warning",
        "macro_regime_shift_predicted",
        "sector_rotation_predicted",
        "regime_shift_predicted",
        "sentiment_surge_predicted",
    }
    assert names == expected


# ── Test 2: propagate_on_trade calls engine.propagate ────────────────────────

def test_propagate_hook_calls_engine(app):
    """propagate_on_trade observation hook calls engine.propagate for the entity."""
    app._engine.propagate = MagicMock(return_value=[])

    propagate_on_trade("instrument:AAPL", confirmed=True, source="alpaca", app=app)

    app._engine.propagate.assert_called_once_with("instrument:AAPL", confidence=0.6, decay=0.5)


# ── Test 3: update_relative_strength calls observe ──────────────────────────

def test_update_relative_strength_calls_observe(app):
    """update_relative_strength queries related positions and calls observe."""
    related = [{"external_id": "position:AAPL"}]
    app._engine.query_related = MagicMock(return_value=related)
    app._engine.observe = MagicMock()

    update_relative_strength("instrument:AAPL", old_value=0.4, new_value=0.7, app=app)

    app._engine.query_related.assert_called_once()
    app._engine.observe.assert_called_once_with(
        "position:AAPL", True, source="relative_strength_propagation"
    )


# ── Test 4: update_exhaustion triggers observe on extreme momentum ────────────

def test_update_exhaustion_on_extreme_momentum(app):
    """update_exhaustion calls observe(exhaustion) when price_trend_fast is high (>=0.85)."""
    app._engine.observe = MagicMock()

    update_exhaustion("instrument:AAPL", old_value=0.5, new_value=0.9, app=app)

    app._engine.observe.assert_called_once_with(
        "instrument:AAPL", True, source="exhaustion_signal"
    )


# ── Test 5: update_exhaustion skips normal momentum ──────────────────────────

def test_update_exhaustion_skips_normal_momentum(app):
    """update_exhaustion does NOT call observe when momentum is in the normal range."""
    app._engine.observe = MagicMock()

    update_exhaustion("instrument:AAPL", old_value=0.4, new_value=0.6, app=app)

    app._engine.observe.assert_not_called()


# ── Test 6: propagate_sector_pressure calls observe for each instrument ───────

def test_propagate_sector_pressure_calls_observe(app):
    """propagate_sector_pressure calls engine.observe for each related instrument."""
    instruments = [
        {"external_id": "instrument:AAPL"},
        {"external_id": "instrument:MSFT"},
    ]
    app._engine.query_related = MagicMock(return_value=instruments)
    app._engine.observe = MagicMock()

    propagate_sector_pressure("sector:TECH", old_value=0.4, new_value=0.7, app=app)

    assert app._engine.observe.call_count == 2
    calls = [c.args[0] for c in app._engine.observe.call_args_list]
    assert "instrument:AAPL" in calls
    assert "instrument:MSFT" in calls


# ── Test 7: update_crowded triggers observe on extreme sentiment ──────────────

def test_update_crowded_on_extreme_sentiment(app):
    """update_crowded calls observe(crowded) when retail_sentiment is high (>=0.85)."""
    app._engine.observe = MagicMock()

    update_crowded("instrument:AAPL", old_value=0.5, new_value=0.9, app=app)

    app._engine.observe.assert_called_once_with(
        "instrument:AAPL", True, source="crowding_signal"
    )


# ── Test 8: conviction_flip skips on low confidence ──────────────────────────

def test_conviction_flip_skips_low_confidence(app):
    """conviction_flip_warning does not create an action when confidence is low."""
    app.create_action = MagicMock()

    prediction = {
        "predicts_flip": True,
        "confidence": 0.2,
        "predicted": 0.3,
    }
    conviction_flip_warning("instrument:AAPL", prediction=prediction, app=app)

    app.create_action.assert_not_called()


# ── Test 9: conviction_flip creates action on high confidence ─────────────────

def test_conviction_flip_creates_action_on_high_confidence(app):
    """conviction_flip_warning creates an action when confidence >= 0.5 and flip predicted."""
    app.create_action = MagicMock(return_value=1)

    prediction = {
        "predicts_flip": True,
        "confidence": 0.7,
        "predicted": 0.3,
    }
    conviction_flip_warning("instrument:AAPL", prediction=prediction, app=app)

    app.create_action.assert_called_once()
    kwargs = app.create_action.call_args.kwargs
    assert kwargs["entity_id"] == "instrument:AAPL"
    assert kwargs["severity"] in ("high", "medium", "critical")


# ── Test 10: sector_rotation_predicted creates action on flip ─────────────────

def test_sector_rotation_predicted_creates_action(app):
    """sector_rotation_predicted creates a sector_headwind_predicted action on flip."""
    app.create_action = MagicMock(return_value=1)

    prediction = {
        "predicts_flip": True,
        "confidence": 0.6,
        "predicted": 0.3,
    }
    sector_rotation_predicted("sector:TECH", prediction=prediction, app=app)

    app.create_action.assert_called_once()
    kwargs = app.create_action.call_args.kwargs
    assert kwargs["action_type"] == "sector_headwind_predicted"
    assert kwargs["entity_id"] == "sector:TECH"


# ── Test 11: regime_shift_predicted creates critical action ───────────────────

def test_regime_shift_predicted_creates_critical_action(app):
    """regime_shift_predicted creates a critical action for risk-off flip."""
    app.create_action = MagicMock(return_value=1)

    prediction = {
        "predicts_flip": True,
        "confidence": 0.8,
        "predicted": 0.2,  # flipping to risk-off
    }
    regime_shift_predicted("regime:global", prediction=prediction, app=app)

    app.create_action.assert_called_once()
    kwargs = app.create_action.call_args.kwargs
    assert kwargs["severity"] == "critical"
    assert kwargs["entity_id"] == "regime:global"


# ── Test 12: sector_rotation_skipped_for_small_delta ─────────────────────────

def test_sector_rotation_skipped_for_small_delta(app):
    """sector_rotation_log does NOT create an action when delta is small (<0.1)."""
    app.create_action = MagicMock(return_value=1)

    # Small delta — hook should skip
    sector_rotation_log("sector:TECH", old_value=0.5, new_value=0.55, app=app)

    app.create_action.assert_not_called()
