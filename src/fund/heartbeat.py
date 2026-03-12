"""Engine health monitor — heartbeat creation and status evaluation."""
from datetime import datetime, timedelta
from typing import Optional
from fund.types import EngineHealth


class HealthMonitor:
    HEARTBEAT_GREEN = timedelta(minutes=2)
    HEARTBEAT_YELLOW = timedelta(minutes=5)
    NOTIFY_MANAGER = timedelta(minutes=5)
    NOTIFY_MEMBERS = timedelta(minutes=15)

    def create_heartbeat(self, alpaca_connected: bool, last_trade: Optional[datetime],
                         active_positions: int, current_regime: str,
                         next_action: str, next_action_at: Optional[datetime]) -> EngineHealth:
        status = "running" if alpaca_connected else "degraded"
        return EngineHealth(status=status, alpaca_connected=alpaca_connected,
                            last_trade=last_trade, active_positions=active_positions,
                            current_regime=current_regime, next_action=next_action,
                            next_action_at=next_action_at)

    def display_status(self, last_heartbeat: datetime) -> str:
        age = datetime.now() - last_heartbeat
        if age < self.HEARTBEAT_GREEN:
            return "green"
        elif age < self.HEARTBEAT_YELLOW:
            return "yellow"
        return "red"

    def should_notify_manager(self, last_heartbeat: datetime) -> bool:
        return (datetime.now() - last_heartbeat) > self.NOTIFY_MANAGER

    def should_notify_members(self, last_heartbeat: datetime) -> bool:
        return (datetime.now() - last_heartbeat) > self.NOTIFY_MEMBERS
