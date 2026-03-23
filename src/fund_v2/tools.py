"""MCP domain tools for fund_v2 — registered via @app.tool() decorators.

Registers 10 tools:
  portfolio_analysis   — current positions + belief summary
  regime_assessment    — current market regime classification
  belief_forecast      — short-horizon prediction for all instruments
  prediction_accuracy  — historical prediction stats from engine
  propose_trade        — create a trade action via app.create_action()
  explain_instrument   — full belief breakdown for one symbol
  generate_signals     — regime-aware signal ranking
  trend_divergence     — fast/slow trend divergence detection
  contradictions       — conflicting belief pairs across instruments
  signal_quality       — overall signal quality assessment
"""

from __future__ import annotations

import logging
from typing import Any

from fund_v2.signals import generate_signals_impl

_log = logging.getLogger(__name__)


def register_tools(app: Any) -> None:
    """Register all 10 fund_v2 domain tools on *app* via @app.tool()."""

    # ── 1. portfolio_analysis ─────────────────────────────────────────────────

    @app.tool("portfolio_analysis")
    def portfolio_analysis() -> dict:
        """Return current portfolio positions with belief summary.

        Scans all Position entities and returns their profitable /
        within_risk_limits beliefs alongside the live position count.
        """
        positions = app.engine.scan(node_type="position")
        enriched = []
        for pos in positions:
            eid = pos.get("external_id", "")
            enriched.append({
                "external_id": eid,
                "symbol": pos.get("symbol", eid.split(":")[-1]),
                "profitable": app.engine.belief(eid),
            })
        return {
            "position_count": len(enriched),
            "positions": enriched,
        }

    # ── 2. regime_assessment ──────────────────────────────────────────────────

    @app.tool("regime_assessment")
    def regime_assessment() -> dict:
        """Return current market regime classification.

        Reads the first MarketRegime entity's beliefs (risk_on,
        trend_following, mean_reverting_regime) and interprets the
        dominant regime label.
        """
        regimes = app.engine.scan(node_type="marketregime")
        if not regimes:
            return {
                "regime": "unknown",
                "risk_on": 0.5,
                "trend_following": 0.5,
                "mean_reverting": 0.5,
            }

        r = regimes[0]
        eid = r.get("external_id", "")
        risk_on = app.engine.belief(eid)

        return {
            "regime": r.get("external_id", "unknown"),
            "risk_on": round(risk_on, 4),
            "trend_following": round(r.get("trend_following", 0.5), 4),
            "mean_reverting": round(r.get("mean_reverting_regime", 0.5), 4),
            "entity": r,
        }

    # ── 3. belief_forecast ────────────────────────────────────────────────────

    @app.tool("belief_forecast")
    def belief_forecast(horizon_days: int = 7) -> dict:
        """Return short-horizon belief predictions for all instruments.

        Uses engine.predict_beliefs() to get forward-looking
        confidence scores across the entire instrument universe.
        """
        instruments = app.engine.scan(node_type="instrument")
        eids = [i.get("external_id", "") for i in instruments if i.get("external_id")]

        forecasts = []
        if hasattr(app.engine, "predict_beliefs"):
            preds = app.engine.predict_beliefs(eids, horizon_days=horizon_days)
            forecasts = preds if isinstance(preds, list) else []
        else:
            for eid in eids:
                pred = app.engine.predict_belief(eid, horizon_days=horizon_days)
                if pred:
                    forecasts.append(pred)

        return {
            "horizon_days": horizon_days,
            "forecasts": forecasts,
            "count": len(forecasts),
        }

    # ── 4. prediction_accuracy ────────────────────────────────────────────────

    @app.tool("prediction_accuracy")
    def prediction_accuracy() -> dict:
        """Return historical prediction accuracy statistics from the engine.

        Wraps engine.prediction_stats() to expose mean absolute error,
        validated count, and total predictions made.
        """
        stats = {}
        if hasattr(app.engine, "prediction_stats"):
            try:
                stats = app.engine.prediction_stats() or {}
            except Exception as exc:
                _log.warning("prediction_stats failed: %s", exc)
        return stats

    # ── 5. propose_trade ──────────────────────────────────────────────────────

    @app.tool("propose_trade")
    def propose_trade(
        symbol: str = "",
        side: str = "buy",
        reason: str = "",
        confidence: float = 0.6,
    ) -> dict:
        """Propose a trade as a recommended action.

        Creates a trade_proposal action via app.create_action() with the
        given symbol, side (buy/sell), and reasoning text.

        Args:
            symbol:     Ticker symbol (e.g. "AAPL").
            side:       "buy" or "sell".
            reason:     Free-text rationale for the trade.
            confidence: Conviction score 0–1.
        """
        description = f"{side.upper()} {symbol}: {reason}" if reason else f"{side.upper()} {symbol}"
        action_id = app.create_action(
            entity_type="instrument",
            entity_id=f"instrument:{symbol}" if symbol else "instrument:unknown",
            action_type="trade_proposal",
            description=description,
            severity="medium",
            confidence=confidence,
            origin="tool",
        )
        return {
            "action_id": action_id,
            "symbol": symbol,
            "side": side,
            "description": description,
        }

    # ── 6. explain_instrument ─────────────────────────────────────────────────

    @app.tool("explain_instrument")
    def explain_instrument(symbol: str = "") -> dict:
        """Return a full belief breakdown for one instrument.

        Fetches the instrument document, all beliefs, and any active
        predictions for the given ticker symbol.

        Args:
            symbol: Ticker symbol (e.g. "AAPL").
        """
        eid = f"instrument:{symbol}" if symbol else "instrument:unknown"
        doc = app.engine.get(eid) or {}
        belief = app.engine.belief(eid)
        pred = None
        if hasattr(app.engine, "predict_belief"):
            try:
                pred = app.engine.predict_belief(eid, horizon_days=7)
            except Exception:
                pass
        return {
            "symbol": symbol,
            "external_id": eid,
            "belief": round(belief, 4),
            "document": doc,
            "prediction": pred,
        }

    # ── 7. generate_signals ───────────────────────────────────────────────────

    @app.tool("generate_signals")
    def generate_signals(regime_id: str = "") -> dict:
        """Generate regime-aware ranked signals for all instruments.

        Scores each instrument's belief layers against the current
        market regime and returns signals sorted by |edge| * confidence.

        Args:
            regime_id: Optional MarketRegime entity ID. If omitted the
                       first registered regime is used.
        """
        # Fetch regime entity (as a simple namespace from doc dict)
        regime_doc: dict = {}
        if regime_id:
            regime_doc = app.engine.get(regime_id) or {}
        else:
            regimes = app.engine.scan(node_type="marketregime")
            regime_doc = regimes[0] if regimes else {}

        # Wrap as a simple object for generate_signals_impl
        class _Regime:
            trend_following      = float(regime_doc.get("trend_following", 0.5))
            mean_reverting_regime = float(regime_doc.get("mean_reverting_regime", 0.5))
            risk_on              = float(regime_doc.get("risk_on", 0.5))

        # Fetch instruments
        inst_docs = app.engine.scan(node_type="instrument")

        class _Instrument:
            def __init__(self, doc: dict) -> None:
                self.external_id      = doc.get("external_id", "")
                self.symbol           = doc.get("symbol", self.external_id.split(":")[-1])
                self.relative_strength = float(doc.get("relative_strength", 0.5))
                self.exhaustion       = float(doc.get("exhaustion", 0.2))
                self.pressure         = float(doc.get("pressure", 0.5))
                self.retail_sentiment = float(doc.get("retail_sentiment", 0.5))
                self.crowded          = float(doc.get("crowded", 0.3))

        instruments = [_Instrument(d) for d in inst_docs]
        return generate_signals_impl(app.engine, _Regime(), instruments)

    # ── 8. trend_divergence ───────────────────────────────────────────────────

    @app.tool("trend_divergence")
    def trend_divergence(min_divergence: float = 0.15) -> dict:
        """Detect instruments where fast and slow trend beliefs diverge.

        A divergence is flagged when |price_trend_fast - price_trend_slow|
        exceeds min_divergence. This often signals a momentum acceleration
        or reversal in progress.

        Args:
            min_divergence: Minimum belief delta to report (default 0.15).
        """
        instruments = app.engine.scan(node_type="instrument")
        divergences = []
        for inst in instruments:
            eid = inst.get("external_id", "")
            fast = float(inst.get("price_trend_fast", 0.5))
            slow = float(inst.get("price_trend_slow", 0.5))
            delta = fast - slow
            if abs(delta) >= min_divergence:
                divergences.append({
                    "external_id": eid,
                    "symbol": inst.get("symbol", eid.split(":")[-1]),
                    "fast": round(fast, 4),
                    "slow": round(slow, 4),
                    "delta": round(delta, 4),
                    "direction": "accelerating" if delta > 0 else "decelerating",
                })
        divergences.sort(key=lambda x: abs(x["delta"]), reverse=True)
        return {"divergences": divergences, "count": len(divergences)}

    # ── 9. contradictions ─────────────────────────────────────────────────────

    @app.tool("contradictions")
    def contradictions() -> dict:
        """Find conflicting belief pairs across the instrument universe.

        Checks three contradiction patterns:
          1. momentum vs exhaustion  — strong trend AND high exhaustion
          2. sentiment vs pressure   — bullish crowd AND bearish order flow
          3. strength vs crowding    — high relative_strength AND crowded

        Returns a list of contradiction dicts, one per conflicting
        instrument, with the specific pattern and belief values.
        """
        instruments = app.engine.scan(node_type="instrument")
        found = []

        for inst in instruments:
            eid  = inst.get("external_id", "")
            sym  = inst.get("symbol", eid.split(":")[-1])
            fast = float(inst.get("price_trend_fast", 0.5))
            exh  = float(inst.get("exhaustion", 0.2))
            snt  = float(inst.get("retail_sentiment", 0.5))
            prs  = float(inst.get("pressure", 0.5))
            rs   = float(inst.get("relative_strength", 0.5))
            cwd  = float(inst.get("crowded", 0.3))

            # Pattern 1: momentum vs exhaustion
            if fast >= 0.7 and exh >= 0.7:
                found.append({
                    "symbol": sym,
                    "external_id": eid,
                    "pattern": "momentum_exhaustion",
                    "description": "Strong momentum alongside high exhaustion — potential reversal",
                    "values": {"price_trend_fast": round(fast, 4), "exhaustion": round(exh, 4)},
                })

            # Pattern 2: sentiment vs pressure
            if snt >= 0.7 and prs <= 0.35:
                found.append({
                    "symbol": sym,
                    "external_id": eid,
                    "pattern": "sentiment_pressure_divergence",
                    "description": "Bullish retail sentiment but bearish order pressure",
                    "values": {"retail_sentiment": round(snt, 4), "pressure": round(prs, 4)},
                })

            # Pattern 3: strength vs crowding
            if rs >= 0.7 and cwd >= 0.7:
                found.append({
                    "symbol": sym,
                    "external_id": eid,
                    "pattern": "strength_crowding",
                    "description": "High relative strength in a crowded position — exit risk",
                    "values": {"relative_strength": round(rs, 4), "crowded": round(cwd, 4)},
                })

        return {"contradictions": found, "count": len(found)}

    # ── 10. signal_quality ────────────────────────────────────────────────────

    @app.tool("signal_quality")
    def signal_quality() -> dict:
        """Assess overall signal quality across the instrument universe.

        Computes summary statistics over all instrument belief layers:
          - mean / std of relative_strength and exhaustion
          - fraction of instruments with high confidence predictions
          - overall quality tier (high / medium / low)
        """
        instruments = app.engine.scan(node_type="instrument")
        if not instruments:
            return {"quality_tier": "unknown", "instrument_count": 0}

        strengths = [float(i.get("relative_strength", 0.5)) for i in instruments]
        exhaustions = [float(i.get("exhaustion", 0.2)) for i in instruments]

        mean_rs  = sum(strengths) / len(strengths)
        mean_exh = sum(exhaustions) / len(exhaustions)

        # Variance via running sum
        var_rs = sum((x - mean_rs) ** 2 for x in strengths) / len(strengths)

        # High confidence = low exhaustion AND extreme strength (signal differentiation)
        high_conf = sum(
            1 for rs, exh in zip(strengths, exhaustions)
            if abs(rs - 0.5) > 0.2 and exh < 0.5
        )
        high_conf_pct = high_conf / len(instruments)

        quality_tier = (
            "high"   if high_conf_pct >= 0.5 and var_rs > 0.01
            else "medium" if high_conf_pct >= 0.25
            else "low"
        )

        return {
            "quality_tier": quality_tier,
            "instrument_count": len(instruments),
            "mean_relative_strength": round(mean_rs, 4),
            "mean_exhaustion": round(mean_exh, 4),
            "high_confidence_pct": round(high_conf_pct, 4),
            "strength_variance": round(var_rs, 6),
        }
