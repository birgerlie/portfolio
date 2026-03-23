"""Tests for fund_v2 MCP domain tools registration and responses."""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from silicondb.orm.mcp_server import create_mcp_server


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def registered_app(app):
    """App with all fund_v2 entities registered and tools loaded."""
    from fund_v2.entities import ALL_ENTITIES
    from fund_v2.tools import register_tools

    app.register(*ALL_ENTITIES)
    register_tools(app)
    return app


# ── Test 1: All 10 tools are discoverable ─────────────────────────────────────


def test_all_tools_are_discoverable(registered_app):
    """All 10 fund_v2 domain tools appear in create_mcp_server(app).list_tools()."""
    server = create_mcp_server(registered_app)
    tools = server.list_tools()
    tool_names = {t["name"] for t in tools}

    expected = {
        "portfolio_analysis",
        "regime_assessment",
        "belief_forecast",
        "prediction_accuracy",
        "propose_trade",
        "explain_instrument",
        "generate_signals",
        "trend_divergence",
        "contradictions",
        "signal_quality",
    }
    for name in expected:
        assert name in tool_names, f"Tool '{name}' missing from list_tools()"


# ── Test 2: portfolio_analysis returns correct structure ──────────────────────


def test_portfolio_analysis_returns_structure(registered_app):
    """portfolio_analysis returns dict with position_count and positions list."""
    server = create_mcp_server(registered_app)
    result = server.call_tool("portfolio_analysis", {})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert "position_count" in data
    assert "positions" in data
    assert isinstance(data["positions"], list)


# ── Test 3: regime_assessment returns regime data ─────────────────────────────


def test_regime_assessment_returns_regime_data(registered_app):
    """regime_assessment returns a dict with regime field."""
    server = create_mcp_server(registered_app)
    result = server.call_tool("regime_assessment", {})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert "regime" in data


# ── Test 4: belief_forecast returns forecast structure ────────────────────────


def test_belief_forecast_returns_structure(registered_app):
    """belief_forecast returns a dict with forecasts key."""
    server = create_mcp_server(registered_app)
    result = server.call_tool("belief_forecast", {})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert "forecasts" in data


# ── Test 5: prediction_accuracy returns stats ────────────────────────────────


def test_prediction_accuracy_returns_stats(registered_app):
    """prediction_accuracy returns stats dict from engine."""
    server = create_mcp_server(registered_app)
    result = server.call_tool("prediction_accuracy", {})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert isinstance(data, dict)


# ── Test 6: propose_trade creates an action ───────────────────────────────────


def test_propose_trade_creates_action(registered_app):
    """propose_trade calls app.create_action and returns an action_id."""
    registered_app.create_action = MagicMock(return_value=42)

    server = create_mcp_server(registered_app)
    result = server.call_tool("propose_trade", {
        "symbol": "AAPL",
        "side": "buy",
        "reason": "Strong momentum signal",
    })

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert registered_app.create_action.called
    assert "action_id" in data


# ── Test 7: contradictions returns contradictions list ────────────────────────


def test_contradictions_returns_list(registered_app):
    """contradictions returns a dict with contradictions list."""
    server = create_mcp_server(registered_app)
    result = server.call_tool("contradictions", {})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert "contradictions" in data
    assert isinstance(data["contradictions"], list)


# ── Test 8: generate_signals calls generate_signals_impl ─────────────────────


def test_generate_signals_tool_returns_signals_structure(registered_app):
    """generate_signals tool returns dict with signals, regime, count."""
    server = create_mcp_server(registered_app)
    result = server.call_tool("generate_signals", {})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert "signals" in data
    assert "count" in data


# ── Test 9: explain_instrument returns explanation ────────────────────────────


def test_explain_instrument_returns_explanation(registered_app):
    """explain_instrument returns a dict with symbol and belief info."""
    # Ingest a dummy instrument into the engine
    registered_app.engine.ingest(
        "instrument:AAPL",
        "Apple Inc",
        node_type="instrument",
        symbol="AAPL",
    )

    server = create_mcp_server(registered_app)
    result = server.call_tool("explain_instrument", {"symbol": "AAPL"})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert "symbol" in data


# ── Test 10: trend_divergence returns divergences ────────────────────────────


def test_trend_divergence_returns_structure(registered_app):
    """trend_divergence returns a dict with divergences list."""
    server = create_mcp_server(registered_app)
    result = server.call_tool("trend_divergence", {})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert "divergences" in data
    assert isinstance(data["divergences"], list)


# ── Test 11: signal_quality returns quality assessment ────────────────────────


def test_signal_quality_returns_assessment(registered_app):
    """signal_quality returns a dict with quality assessment info."""
    server = create_mcp_server(registered_app)
    result = server.call_tool("signal_quality", {})

    import json
    data = json.loads(result) if isinstance(result, str) else result

    assert isinstance(data, dict)
