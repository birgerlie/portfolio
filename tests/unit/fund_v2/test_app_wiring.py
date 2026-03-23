"""App wiring — entity registration, hooks, tools, policy."""
from fund_v2.app import create_app
from silicondb.orm.execution import Decision


def test_create_app_returns_app():
    app = create_app(db_path=":memory:")
    assert app is not None


def test_create_app_has_hooks():
    app = create_app(db_path=":memory:")
    hooks = app._hook_registry.get_hooks("prediction", "Instrument", "relative_strength")
    assert len(hooks) >= 1


def test_create_app_has_tools():
    from silicondb.orm.mcp_server import create_mcp_server
    app = create_app(db_path=":memory:")
    server = create_mcp_server(app)
    tool_names = [t["name"] for t in server.list_tools()]
    assert "portfolio_analysis" in tool_names
    assert "generate_signals" in tool_names


def test_execution_policy_blocks_unapproved_buy():
    app = create_app(db_path=":memory:")
    policy = app._execution_policy
    decision = policy.evaluate({"action_type": "buy", "confidence": 0.5})
    assert decision == Decision.HUMAN


def test_execution_policy_auto_approves_alert():
    app = create_app(db_path=":memory:")
    policy = app._execution_policy
    decision = policy.evaluate({"action_type": "volatility_alert", "confidence": 0.9})
    assert decision == Decision.AUTO


def test_execution_policy_confidence_gate_sell():
    app = create_app(db_path=":memory:")
    policy = app._execution_policy
    decision = policy.evaluate({"action_type": "sell", "confidence": 0.96})
    assert decision == Decision.AUTO


def test_execution_policy_auto_approves_prediction_actions():
    app = create_app(db_path=":memory:")
    policy = app._execution_policy
    for action_type in ["sector_headwind_predicted", "risk_off_predicted", "risk_on_predicted",
                        "crowding_risk_predicted", "capitulation_predicted"]:
        decision = policy.evaluate({"action_type": action_type, "confidence": 0.7})
        assert decision == Decision.AUTO, f"{action_type} should be auto-approved"
