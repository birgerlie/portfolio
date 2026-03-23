"""Trading agent loop for the Glass Box Fund.

Connects to SiliconDB via event stream, reacts to belief changes and thermo shifts,
proposes trades through the action feed.
"""
from silicondb.agent.loop import AgentLoop


def create_agent(app) -> AgentLoop:
    """Create the trading agent loop with event handlers."""
    loop = AgentLoop(app, poll_interval=1.0)

    @loop.on("action_recommended", severity="critical")
    def handle_critical(event, app):
        payload = event.get("payload", {})
        action_type = payload.get("action_type", "")
        entity_id = payload.get("entity_id", "")
        print(f"[CRITICAL] {action_type} for {entity_id}: {payload.get('description', '')}")

    @loop.on("action_recommended", severity="high")
    def handle_high_priority(event, app):
        payload = event.get("payload", {})
        entity_id = payload.get("entity_id", "")
        prediction = app.engine.predict_belief(f"{entity_id}:relative_strength", horizon_days=7)
        if prediction and getattr(prediction, "predicts_flip", False):
            print(f"[AGENT] {entity_id}: relative_strength flip predicted")

    @loop.on("thermo_shift")
    def handle_thermo(event, app):
        payload = event.get("payload", {})
        temperature = payload.get("temperature", 0)
        tier = payload.get("tier", "unknown")
        print(f"[THERMO] System temperature: {temperature:.3f} (tier: {tier})")
        if tier in ("hot", "critical"):
            app.engine.epistemic_briefing(
                topic="market", budget=20, anchor_ratio=0.3, hops=2, neighbor_k=5,
            )

    @loop.on("action_recommended", action_type="risk_off_predicted")
    def handle_risk_off(event, app):
        print("[REGIME] Risk-off predicted — triggering full portfolio review")

    @loop.on("action_recommended", action_type="sector_headwind_predicted")
    def handle_sector_headwind(event, app):
        payload = event.get("payload", {})
        print(f"[SECTOR] Headwind predicted: {payload.get('description', '')}")

    @loop.on("belief_changed")
    def handle_belief_delta(event, app):
        payload = event.get("payload", {})
        node_id = payload.get("node_id", "")
        if ":relative_strength" not in node_id and ":price_trend_slow" not in node_id:
            return
        symbol = node_id.split(":")[0]
        flips = app.engine.predicted_flips(horizon_days=14, min_confidence=0.6, k=5)
        if flips:
            for flip in flips:
                if hasattr(flip, "node_id") and symbol in flip.node_id:
                    print(f"[PREDICTION] {symbol} flip predicted")

    return loop
