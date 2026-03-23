"""Agent loop — event handlers for trading decisions."""
from unittest.mock import MagicMock
from fund_v2.agent import create_agent


def test_agent_registers_handlers(app):
    loop = create_agent(app)
    assert loop is not None
    assert len(loop._handlers) > 0


def test_critical_handler_logs(app, capsys):
    loop = create_agent(app)
    event = {
        "event_type": "action_recommended",
        "payload": {
            "severity": "critical",
            "action_type": "sell",
            "entity_id": "AAPL",
            "description": "stop-loss triggered",
        },
    }
    # Dispatch matching handlers using _Registration dataclass attributes
    for reg in loop._handlers:
        if reg.event_type == "action_recommended" and reg.matches(event):
            reg.handler(event, app)
    captured = capsys.readouterr()
    assert "CRITICAL" in captured.out or "stop-loss" in captured.out


def test_thermo_handler_runs_briefing(app):
    app._engine.epistemic_briefing = MagicMock(return_value={"anchors": ["NVDA"]})
    loop = create_agent(app)
    event = {
        "event_type": "thermo_shift",
        "payload": {"temperature": 0.8, "tier": "hot"},
    }
    for reg in loop._handlers:
        if reg.event_type == "thermo_shift" and reg.matches(event):
            reg.handler(event, app)
    app._engine.epistemic_briefing.assert_called_once()
