"""Regime-aware signal generation for fund_v2.

generate_signals_impl scores each instrument across 5 belief layers,
weights the score by the current market regime, and returns signals
sorted by |edge| * confidence.

Belief layers used:
  - relative_strength  (Layer 2 — graph-derived)
  - exhaustion         (Layer 2 — overbought/oversold)
  - pressure           (Layer 2 — net order pressure)
  - retail_sentiment   (Layer 3 — crowd)
  - crowded            (Layer 3 — position crowding)
"""

from __future__ import annotations

from typing import Any


def _regime_weights(regime: Any) -> dict[str, float]:
    """Derive scoring weights from regime belief values.

    In a trend-following regime, momentum (relative_strength, pressure)
    dominates. In a mean-reverting regime, exhaustion and contrarian
    signals get more weight. Crowding is always a penalty.
    """
    tf = float(getattr(regime, "trend_following", 0.5))
    mr = float(getattr(regime, "mean_reverting_regime", 0.5))

    return {
        "price_trend_fast": 0.25 + 0.15 * tf,          # primary momentum signal
        "price_trend_slow": 0.20 + 0.10 * tf,          # trend confirmation
        "relative_strength": 0.15 + 0.15 * tf - 0.05 * mr,
        "exhaustion": 0.10 + 0.20 * mr - 0.05 * tf,   # contrarian weight
        "pressure": 0.15 + 0.10 * tf - 0.05 * mr,
        "retail_sentiment": 0.05 + 0.05 * mr,
        "crowded": -(0.10 + 0.05 * tf),                # always negative
    }


def _score_instrument(
    instrument: Any,
    engine: Any,
    weights: dict[str, float],
) -> tuple[float, float, dict[str, float]]:
    """Score a single instrument; return (edge, confidence, layers).

    Edge is the weighted sum of belief signals, signed so that:
      - positive edge = long candidate
      - negative edge = short candidate

    Confidence is derived from the prediction certainty of the
    instrument's primary belief (relative_strength).
    """
    eid = getattr(instrument, "external_id", None) or f"instrument:{getattr(instrument, 'symbol', '')}"

    # Read ALL beliefs — Layer 1 (observable) drives direction when Layer 2/3 are unavailable
    fast = float(getattr(instrument, "price_trend_fast", 0.5))
    slow = float(getattr(instrument, "price_trend_slow", 0.5))
    rs   = float(getattr(instrument, "relative_strength", 0.5))
    exh  = float(getattr(instrument, "exhaustion", 0.2))
    prs  = float(getattr(instrument, "pressure", 0.5))
    snt  = float(getattr(instrument, "retail_sentiment", 0.5))
    cwd  = float(getattr(instrument, "crowded", 0.3))

    # Centre beliefs around 0 so > 0.5 is bullish, < 0.5 is bearish
    layers = {
        "price_trend_fast": fast - 0.5,     # primary directional signal
        "price_trend_slow": slow - 0.5,     # confirmation signal
        "relative_strength": rs - 0.5,
        "exhaustion": 0.5 - exh,            # high exhaustion → contrarian (bearish momentum)
        "pressure": prs - 0.5,
        "retail_sentiment": snt - 0.5,
        "crowded": cwd - 0.5,
    }

    edge = sum(weights.get(k, 0.0) * v for k, v in layers.items())
    edge = max(-1.0, min(1.0, edge))

    # Confidence: use prediction confidence if available, else half-width from neutral
    pred = None
    try:
        pred = engine.predict_belief(eid, horizon_days=7)
    except Exception:
        pass

    if pred and isinstance(pred, dict) and "confidence" in pred:
        confidence = float(pred.get("confidence", 0.5))
    else:
        confidence = min(1.0, abs(edge) * 2 + 0.1)  # proxy

    # Foresight: if prediction agrees with current direction, boost confidence
    if pred and isinstance(pred, dict):
        predicted = float(pred.get("predicted", rs))
        current   = float(pred.get("current", rs))
        if (predicted - 0.5) * edge > 0:          # same direction
            confidence = min(1.0, confidence + 0.1)

    return edge, confidence, {k: round(v + 0.5, 4) for k, v in layers.items()}  # denormalize for readability


def generate_signals_impl(
    engine: Any,
    regime: Any,
    instruments: list[Any],
) -> dict[str, Any]:
    """Generate regime-aware signals for a list of instruments.

    Args:
        engine:      SiliconDB engine (or mock) for prediction queries.
        regime:      MarketRegime entity with trend_following /
                     mean_reverting_regime / risk_on beliefs.
        instruments: List of Instrument entities.

    Returns:
        {
            "signals": [...],   # sorted by |edge| * confidence desc
            "regime":  {...},   # regime belief values used
            "count":   int,
        }

    Each signal:
        {
            "symbol":         str,
            "edge":           float,   # -1..1
            "confidence":     float,   # 0..1
            "sizing":         float,   # fractional position size
            "direction":      str,     # "long" | "short" | "neutral"
            "layers":         dict,    # per-layer belief scores
            "regime_weights": dict,    # weights applied this run
        }
    """
    weights = _regime_weights(regime)

    signals = []
    for inst in instruments:
        symbol = getattr(inst, "symbol", None) or str(inst)
        edge, confidence, layers = _score_instrument(inst, engine, weights)

        direction = "long" if edge > 0.01 else "short" if edge < -0.01 else "neutral"

        # Sizing: Kelly-inspired, scaled by confidence, floored at a minimum
        raw_sizing = abs(edge) * confidence
        sizing = max(0.01, min(0.25, raw_sizing))

        signals.append({
            "symbol":         symbol,
            "edge":           round(edge, 4),
            "confidence":     round(confidence, 4),
            "sizing":         round(sizing, 4),
            "direction":      direction,
            "layers":         layers,
            "regime_weights": {k: round(v, 4) for k, v in weights.items()},
        })

    # Sort by |edge| * confidence descending
    signals.sort(key=lambda s: abs(s["edge"]) * s["confidence"], reverse=True)

    return {
        "signals": signals,
        "regime": {
            "trend_following":      round(float(getattr(regime, "trend_following", 0.5)), 4),
            "mean_reverting":       round(float(getattr(regime, "mean_reverting_regime", 0.5)), 4),
            "risk_on":              round(float(getattr(regime, "risk_on", 0.5)), 4),
        },
        "count": len(signals),
    }
