"""Glass Box Fund — ORM app wiring.

Single entry point that registers entities, sources, hooks, tools,
execution policy, and starts the MCP server + agent loop.
"""
from silicondb.orm import App
from silicondb.orm.execution import ExecutionPolicy

from fund_v2.entities import ALL_ENTITIES
import fund_v2.hooks as hook_module
from fund_v2.tools import register_tools


def create_app(db_path: str = None, db_url: str = None, tenant_id: int = 3, **kwargs) -> App:
    """Create and configure the trading fund ORM app.

    Args:
        tenant_id: Multi-tenant isolation. Default 3 (Chargo=1, V1=2, V2=3).
    """
    if db_path == ":memory:":
        from silicondb.engine.mock import MockEngine
        engine = MockEngine()
        app = App(engine, internal_db_url="sqlite:///:memory:", tenant_id=tenant_id)
    elif db_url:
        app = App.from_url(db_url, tenant_id=tenant_id, **kwargs)
    else:
        app = App.from_path(db_path or "/data/fund", dimension=384, tenant_id=tenant_id, **kwargs)

    # Register entities
    app.register(*ALL_ENTITIES)

    # Register hooks — App.register_hooks() scans modules for @on_* decorators
    app.register_hooks(hook_module)

    # Register MCP tools
    register_tools(app)

    # Execution policy
    app._execution_policy = ExecutionPolicy(
        auto_approve=[
            "volatility_alert",
            "macro_shift",
            "sector_rotation",
            "conviction_flip_warning",
            "macro_flip_predicted",
            "concentration_warning",
            "drawdown_warning",
            "sector_headwind_predicted",
            "sector_tailwind_predicted",
            "risk_off_predicted",
            "risk_on_predicted",
            "crowding_risk_predicted",
            "capitulation_predicted",
        ],
        human_approve=["buy", "sell"],
        confidence_gate={"sell": 0.95},
        simulation_only=["rebalance"],
        cooldown={"buy": 3600, "sell": 1800},
    )

    return app
