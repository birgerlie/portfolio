"""Entity lifecycle hooks for fund_v2 — propagation, Layer 2 derivation, prediction reactions.

14 hook functions across 4 categories:
  - Observation reactions: propagate_on_trade, cooccurrence_tracking
  - Layer 2 propagation: update_relative_strength, update_exhaustion,
      propagate_sector_pressure, propagate_macro_pressure, update_crowded
  - Belief change reactions: sector_rotation_log, portfolio_health_change
  - Prediction reactions: conviction_flip_warning, macro_regime_shift_predicted,
      sector_rotation_predicted, regime_shift_predicted, sentiment_surge_predicted
"""

from __future__ import annotations

import logging
from typing import Any

from silicondb.orm.hooks import on_belief_change, on_observation, on_prediction

_log = logging.getLogger(__name__)

# Thresholds
_EXTREME_THRESHOLD = 0.85   # momentum / sentiment extreme
_FLIP_CONFIDENCE_MIN = 0.5  # minimum confidence to act on a flip prediction
_SECTOR_DELTA_MIN = 0.1     # minimum delta for sector_rotation_log to create an action


# ── Observation reactions ─────────────────────────────────────────────────────


@on_observation("Instrument", "price_trend_fast")
def propagate_on_trade(entity: str, confirmed: bool, source: str, app: Any) -> None:
    """Propagate belief confidence through the graph on each trade observation."""
    app.engine.propagate(entity, confidence=0.6, decay=0.5)


@on_observation("Instrument", "trade_pressure")
def cooccurrence_tracking(entity: str, confirmed: bool, source: str, app: Any) -> None:
    """Track co-occurrence patterns when trade pressure observations arrive."""
    # Record accumulator push for co-occurrence tracking
    try:
        app.engine.accumulator_push(
            f"Instrument.trade_pressure",
            entity,
            weight=1.0 if confirmed else -0.5,
        )
    except Exception:
        _log.debug("cooccurrence_tracking: accumulator_push not available, skipping")


# ── Layer 2 propagation hooks ─────────────────────────────────────────────────


@on_belief_change("Instrument", "price_trend_fast", min_delta=0.05)
def update_relative_strength(entity: str, old_value: float, new_value: float, app: Any) -> None:
    """Mirror instrument relative_strength change to linked Position entities."""
    try:
        related = app.engine.query_related(entity, predicate="holds")
    except Exception:
        related = []

    confirmed = new_value >= 0.5
    for rel in related:
        rel_id = rel.get("external_id") or rel.get("id", "")
        if rel_id:
            app.engine.observe(rel_id, confirmed, source="relative_strength_propagation")


@on_belief_change("Instrument", "price_trend_fast", min_delta=0.05)
def update_exhaustion(entity: str, old_value: float, new_value: float, app: Any) -> None:
    """Observe exhaustion belief when momentum becomes extreme (>= 0.85 or <= 0.15)."""
    if new_value >= _EXTREME_THRESHOLD or new_value <= (1.0 - _EXTREME_THRESHOLD):
        confirmed = new_value >= _EXTREME_THRESHOLD
        app.engine.observe(entity, confirmed, source="exhaustion_signal")


@on_belief_change("Sector", "momentum", min_delta=0.05)
def propagate_sector_pressure(entity: str, old_value: float, new_value: float, app: Any) -> None:
    """Propagate sector momentum change to all instruments in the sector."""
    try:
        instruments = app.engine.query_related(entity, predicate="has_instrument")
    except Exception:
        instruments = []

    confirmed = new_value >= 0.5
    for inst in instruments:
        inst_id = inst.get("external_id") or inst.get("id", "")
        if inst_id:
            app.engine.observe(inst_id, confirmed, source="sector_pressure_propagation")


@on_belief_change("MacroFactor", "elevated", min_delta=0.05)
def propagate_macro_pressure(entity: str, old_value: float, new_value: float, app: Any) -> None:
    """Propagate macro factor elevation change to affected sectors and instruments."""
    try:
        affected = app.engine.query_related(entity, predicate="affects_sector")
    except Exception:
        affected = []

    confirmed = new_value >= 0.5
    for item in affected:
        item_id = item.get("external_id") or item.get("id", "")
        if item_id:
            app.engine.observe(item_id, confirmed, source="macro_pressure_propagation")


@on_belief_change("Instrument", "retail_sentiment", min_delta=0.05)
def update_crowded(entity: str, old_value: float, new_value: float, app: Any) -> None:
    """Observe crowded belief when retail sentiment becomes extreme (>= 0.85)."""
    if new_value >= _EXTREME_THRESHOLD or new_value <= (1.0 - _EXTREME_THRESHOLD):
        confirmed = new_value >= _EXTREME_THRESHOLD
        app.engine.observe(entity, confirmed, source="crowding_signal")


# ── Belief change reactions ───────────────────────────────────────────────────


@on_belief_change("Sector", "momentum", min_delta=0.1)
def sector_rotation_log(entity: str, old_value: float, new_value: float, app: Any) -> None:
    """Create a sector_rotation action when sector momentum shifts significantly (>= 0.1)."""
    delta = abs(new_value - old_value)
    if delta < _SECTOR_DELTA_MIN:
        return  # Guarded by min_delta decorator, but also checked directly

    direction = "improving" if new_value > old_value else "weakening"
    app.create_action(
        entity_type="sector",
        entity_id=entity,
        action_type="sector_rotation",
        description=f"Sector momentum {direction}: {old_value:.2f} → {new_value:.2f}",
        severity="medium",
        confidence=min(1.0, delta * 2),
    )


@on_belief_change("Portfolio", "drawdown_contained", min_delta=0.05)
def portfolio_health_change(entity: str, old_value: float, new_value: float, app: Any) -> None:
    """Log portfolio health changes; escalate if drawdown_contained drops sharply."""
    delta = old_value - new_value  # positive = health declining
    if delta >= 0.15:
        app.create_action(
            entity_type="portfolio",
            entity_id=entity,
            action_type="portfolio_health_alert",
            description=f"Portfolio drawdown containment declining: {old_value:.2f} → {new_value:.2f}",
            severity="high",
            confidence=min(1.0, delta * 3),
        )


# ── Prediction reactions ──────────────────────────────────────────────────────


@on_prediction("Instrument", "price_trend_fast")
def conviction_flip_warning(entity: str, prediction: dict, app: Any) -> None:
    """Warn when an instrument's conviction is predicted to flip, if confidence >= 0.5."""
    if not prediction.get("predicts_flip"):
        return
    confidence = prediction.get("confidence", 0.0)
    if confidence < _FLIP_CONFIDENCE_MIN:
        return

    predicted = prediction.get("predicted", 0.5)
    direction = "bullish" if predicted >= 0.5 else "bearish"
    app.create_action(
        entity_type="instrument",
        entity_id=entity,
        action_type="conviction_flip_warning",
        description=f"Conviction flip predicted → {direction} (confidence {confidence:.0%})",
        severity="high",
        confidence=confidence,
    )


@on_prediction("MacroFactor", "elevated")
def macro_regime_shift_predicted(entity: str, prediction: dict, app: Any) -> None:
    """Alert when a macro factor is predicted to flip to elevated regime."""
    if not prediction.get("predicts_flip"):
        return
    confidence = prediction.get("confidence", 0.0)
    if confidence < _FLIP_CONFIDENCE_MIN:
        return

    predicted = prediction.get("predicted", 0.5)
    direction = "elevated" if predicted >= 0.5 else "receding"
    app.create_action(
        entity_type="macrofactor",
        entity_id=entity,
        action_type="macro_regime_shift_predicted",
        description=f"Macro factor predicted to become {direction} (confidence {confidence:.0%})",
        severity="high",
        confidence=confidence,
    )


@on_prediction("Sector", "momentum")
def sector_rotation_predicted(entity: str, prediction: dict, app: Any) -> None:
    """Create sector_headwind_predicted action when sector momentum is predicted to flip."""
    if not prediction.get("predicts_flip"):
        return
    confidence = prediction.get("confidence", 0.0)
    if confidence < _FLIP_CONFIDENCE_MIN:
        return

    predicted = prediction.get("predicted", 0.5)
    direction = "tailwind" if predicted >= 0.5 else "headwind"
    app.create_action(
        entity_type="sector",
        entity_id=entity,
        action_type="sector_headwind_predicted",
        description=f"Sector rotation predicted → {direction} (confidence {confidence:.0%})",
        severity="medium",
        confidence=confidence,
    )


@on_prediction("MarketRegime", "risk_on")
def regime_shift_predicted(entity: str, prediction: dict, app: Any) -> None:
    """Create a critical action when a risk-on/risk-off regime flip is predicted."""
    if not prediction.get("predicts_flip"):
        return
    confidence = prediction.get("confidence", 0.0)
    if confidence < _FLIP_CONFIDENCE_MIN:
        return

    predicted = prediction.get("predicted", 0.5)
    regime = "risk-on" if predicted >= 0.5 else "risk-off"
    app.create_action(
        entity_type="marketregime",
        entity_id=entity,
        action_type="regime_shift_predicted",
        description=f"Market regime shift predicted → {regime} (confidence {confidence:.0%})",
        severity="critical",
        confidence=confidence,
    )


@on_prediction("Instrument", "retail_sentiment")
def sentiment_surge_predicted(entity: str, prediction: dict, app: Any) -> None:
    """Alert when retail sentiment is predicted to surge (flip to high)."""
    if not prediction.get("predicts_flip"):
        return
    confidence = prediction.get("confidence", 0.0)
    if confidence < _FLIP_CONFIDENCE_MIN:
        return

    predicted = prediction.get("predicted", 0.5)
    direction = "surge" if predicted >= 0.5 else "collapse"
    app.create_action(
        entity_type="instrument",
        entity_id=entity,
        action_type="sentiment_surge_predicted",
        description=f"Retail sentiment {direction} predicted (confidence {confidence:.0%})",
        severity="medium",
        confidence=confidence,
    )


@on_prediction("Instrument", "relative_strength")
def relative_strength_shift_predicted(entity: str, prediction: dict, app: Any) -> None:
    """Alert when an instrument's relative strength is predicted to flip significantly."""
    if not prediction.get("predicts_flip"):
        return
    confidence = prediction.get("confidence", 0.0)
    if confidence < _FLIP_CONFIDENCE_MIN:
        return

    predicted = prediction.get("predicted", 0.5)
    direction = "strengthening" if predicted >= 0.5 else "weakening"
    app.create_action(
        entity_type="instrument",
        entity_id=entity,
        action_type="crowding_risk_predicted",
        description=f"Relative strength predicted {direction} (confidence {confidence:.0%})",
        severity="medium",
        confidence=confidence,
    )
