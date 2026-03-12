"""Event-driven notification routing for the fund engine."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NotificationPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventType(Enum):
    REGIME_SHIFT = "regime_shift"
    TRADE_EXECUTED = "trade_executed"
    NAV_PUBLISHED = "nav_published"
    SUBSCRIPTION_PROCESSED = "subscription_processed"
    DANGER_ZONE = "danger_zone"
    FEE_STATEMENT = "fee_statement"
    CONVICTION_CHANGED = "conviction_changed"


# Default titles for each event type
_DEFAULT_TITLES: Dict[str, str] = {
    EventType.REGIME_SHIFT.value: "Market Regime Changed",
    EventType.TRADE_EXECUTED.value: "Trade Executed",
    EventType.NAV_PUBLISHED.value: "Weekly NAV Published",
    EventType.SUBSCRIPTION_PROCESSED.value: "Subscription Processed",
    EventType.DANGER_ZONE.value: "Danger Zone Alert",
    EventType.FEE_STATEMENT.value: "Monthly Fee Statement",
    EventType.CONVICTION_CHANGED.value: "Conviction Updated",
}


class NotificationManager:
    """Route fund events to Supabase push and optional email."""

    def __init__(self, supabase_sync, email_reporter=None) -> None:
        self.supabase_sync = supabase_sync
        self.email_reporter = email_reporter

    # ── public API ───────────────────────────────────────────────────────────

    def notify(
        self,
        event_type: EventType,
        priority: NotificationPriority,
        data: Dict[str, Any],
        title: Optional[str] = None,
        to_addrs: Optional[List[str]] = None,
    ) -> None:
        """Route a notification to configured channels based on priority."""
        resolved_title = title or _DEFAULT_TITLES.get(event_type.value, event_type.value)
        notification = {
            "event_type": event_type.value,
            "priority": priority.value,
            "title": resolved_title,
            "data": data,
        }

        # All priorities → Supabase push (web realtime)
        self.push_to_supabase(notification)

        # HIGH priority → also send email if reporter is configured
        if priority == NotificationPriority.HIGH and self.email_reporter and to_addrs:
            try:
                html = self._simple_alert_html(resolved_title, event_type.value, data)
                self.email_reporter.send_report(
                    to_addrs=to_addrs,
                    subject=f"[FUND ALERT] {resolved_title}",
                    html=html,
                )
            except Exception as exc:
                logger.warning("Failed to send notification email: %s", exc)

    def push_to_supabase(self, notification: Dict[str, Any]) -> None:
        """Insert a notification into Supabase for web push via Realtime."""
        row = {
            **notification,
            "read": False,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.supabase_sync.push_notification(row)

    # ── convenience methods ──────────────────────────────────────────────────

    def regime_shift(self, old_regime: str, new_regime: str, **kwargs) -> None:
        """Fire a HIGH-priority regime shift notification."""
        self.notify(
            EventType.REGIME_SHIFT,
            NotificationPriority.HIGH,
            data={"old_regime": old_regime, "new_regime": new_regime},
            title=f"Regime shifted: {old_regime} → {new_regime}",
            **kwargs,
        )

    def trade_executed(self, symbol: str, action: str, quantity: float, price: float, **kwargs) -> None:
        """Fire a MEDIUM-priority trade notification."""
        self.notify(
            EventType.TRADE_EXECUTED,
            NotificationPriority.MEDIUM,
            data={"symbol": symbol, "action": action, "quantity": quantity, "price": price},
            title=f"{action.upper()} {quantity} {symbol} @ ${price:.2f}",
            **kwargs,
        )

    def nav_published(self, nav: float, nav_per_unit: float, change_pct: float, **kwargs) -> None:
        """Fire a MEDIUM-priority NAV publication notification."""
        self.notify(
            EventType.NAV_PUBLISHED,
            NotificationPriority.MEDIUM,
            data={"nav": nav, "nav_per_unit": nav_per_unit, "change_pct": change_pct},
            title=f"NAV ${nav_per_unit:.4f}/unit ({change_pct*100:+.2f}%)",
            **kwargs,
        )

    def danger_zone(self, message: str, to_addrs: Optional[List[str]] = None, **kwargs) -> None:
        """Fire a HIGH-priority danger zone alert."""
        self.notify(
            EventType.DANGER_ZONE,
            NotificationPriority.HIGH,
            data={"message": message},
            title=f"Danger Zone: {message}",
            to_addrs=to_addrs,
            **kwargs,
        )

    def conviction_changed(self, symbol: str, old_p: float, new_p: float, **kwargs) -> None:
        """Fire a LOW-priority conviction change notification."""
        self.notify(
            EventType.CONVICTION_CHANGED,
            NotificationPriority.LOW,
            data={"symbol": symbol, "old_probability": old_p, "new_probability": new_p},
            title=f"{symbol} conviction: {old_p:.0%} → {new_p:.0%}",
            **kwargs,
        )

    # ── private ───────────────────────────────────────────────────────────────

    def _simple_alert_html(self, title: str, event_type: str, data: Dict[str, Any]) -> str:
        rows = "\n".join(
            f"<tr><td style='color:#9ca3af;padding:4px 8px'>{k}</td>"
            f"<td style='padding:4px 8px'>{v}</td></tr>"
            for k, v in data.items()
        )
        return f"""<!DOCTYPE html>
<html><body style="background:#0a0a0a;color:#e5e7eb;font-family:sans-serif;padding:32px">
<h1 style="color:#ef4444;font-size:18px">{title}</h1>
<p style="color:#71717a;font-size:13px">Event: {event_type}</p>
<table style="border-collapse:collapse;margin-top:16px">{rows}</table>
</body></html>"""
