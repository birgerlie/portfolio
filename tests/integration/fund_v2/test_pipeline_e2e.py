"""End-to-end: source → pipeline → hooks → actions → MCP."""
import json

from fund_v2.app import create_app
from silicondb.orm.mcp_server import create_mcp_server
from silicondb.orm.execution import Decision


def _parse(result):
    """Normalise call_tool result to dict (handles both str and dict returns)."""
    if isinstance(result, str):
        return json.loads(result)
    return result


def test_app_creates_and_registers_everything():
    """Verify the full app creation doesn't crash."""
    app = create_app(db_path=":memory:")
    assert app is not None
    assert len(app._hook_registry._hooks) > 0


def test_mcp_tools_return_data():
    """MCP tools return structured data from the engine."""
    app = create_app(db_path=":memory:")
    server = create_mcp_server(app)

    # Portfolio analysis on empty portfolio
    result = _parse(server.call_tool("portfolio_analysis", {}))
    assert result["position_count"] == 0

    # Regime assessment — returns "regime" key (not "factors"/"thermo")
    result = _parse(server.call_tool("regime_assessment", {}))
    assert "regime" in result
    assert "risk_on" in result


def test_execution_policy_gates_trades():
    """Execution policy correctly gates buy/sell vs alerts."""
    app = create_app(db_path=":memory:")
    policy = app._execution_policy

    assert policy.evaluate({"action_type": "volatility_alert", "confidence": 0.9}) == Decision.AUTO
    assert policy.evaluate({"action_type": "buy", "confidence": 0.7}) == Decision.HUMAN
    assert policy.evaluate({"action_type": "sell", "confidence": 0.96}) == Decision.AUTO
    assert policy.evaluate({"action_type": "sell", "confidence": 0.5}) == Decision.HUMAN


def test_hook_dispatch_creates_action():
    """Dispatching a prediction hook creates an action in the feed."""
    app = create_app(db_path=":memory:")

    # Dispatch regime shift prediction — hook is regime_shift_predicted,
    # which creates action_type="regime_shift_predicted" (not "risk_off_predicted")
    app.dispatch_hooks(
        "prediction", "MarketRegime", "risk_on",
        entity="default",
        prediction={
            "predicts_flip": True,
            "confidence": 0.7,
            "current_probability": 0.7,
            "predicted_probability": 0.3,
            "predicted": 0.3,  # field name used by regime_shift_predicted hook
        },
    )

    actions = app.get_actions(limit=10)
    assert len(actions) >= 1
    action_types = [a.get("action_type", "") for a in actions]
    assert "regime_shift_predicted" in action_types


def test_generate_signals_on_empty_portfolio():
    """Signal generation works even with no instruments."""
    app = create_app(db_path=":memory:")
    server = create_mcp_server(app)
    result = _parse(server.call_tool("generate_signals", {}))
    assert "signals" in result


def test_propose_trade_creates_action():
    """propose_trade tool creates an action in the feed."""
    app = create_app(db_path=":memory:")
    server = create_mcp_server(app)
    # Note: parameter is "reason", not "rationale"
    result = _parse(server.call_tool("propose_trade", {
        "symbol": "AAPL",
        "side": "buy",
        "reason": "integration test",
    }))
    assert "action_id" in result
    actions = app.get_actions(limit=10)
    assert len(actions) >= 1
