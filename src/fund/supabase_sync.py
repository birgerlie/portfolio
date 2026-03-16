"""Push fund data to Supabase for the web dashboard."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

logger = logging.getLogger(__name__)


def _id() -> str:
    return str(uuid4())


@dataclass
class SupabaseConfig:
    """Supabase connection config."""
    url: str
    key: str  # service role key for server-side writes


class SupabaseSync:
    """Syncs fund state to Supabase Postgres."""

    def __init__(self, config: SupabaseConfig):
        from supabase import create_client
        self._client = create_client(config.url, config.key)

    def push_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Push a fund state snapshot. Upserts on date."""
        snapshot.setdefault("id", _id())
        snapshot["updated_at"] = datetime.now().isoformat()
        self._client.table("fund_snapshots").upsert(snapshot, on_conflict="date").execute()

    def push_journal(self, journal_data: Dict[str, Any]) -> None:
        """Push a daily journal. Upserts on date."""
        journal_data.setdefault("id", _id())
        journal_data["updated_at"] = datetime.now().isoformat()
        self._client.table("journals").upsert(journal_data, on_conflict="date").execute()

    def push_heartbeat(self, heartbeat: Dict[str, Any]) -> None:
        """Push engine heartbeat. Upserts on singleton row."""
        heartbeat.setdefault("id", "singleton")
        heartbeat["updated_at"] = datetime.now().isoformat()
        self._client.table("engine_heartbeat").upsert(heartbeat, on_conflict="id").execute()

    def push_positions(self, positions: list) -> None:
        """Push current positions snapshot."""
        self._client.table("positions").upsert(
            [{"id": _id(), "updated_at": datetime.now().isoformat(), **p} for p in positions],
            on_conflict="symbol",
        ).execute()

    def push_notification(self, notification: dict) -> None:
        """Insert a notification row for web push via Supabase Realtime."""
        notification.setdefault("id", _id())
        self._client.table("notifications").insert(notification).execute()

    def load_fund_state(self) -> dict:
        """Load latest fund snapshot from Supabase for startup hydration."""
        try:
            result = self._client.table("fund_snapshots").select("*").order("updated_at", desc=True).limit(1).execute()
            if result.data:
                return result.data[0]
            return {}
        except Exception as e:
            logger.error("Failed to load fund state: %s", e)
            return {}

    def load_members(self) -> list:
        """Load all members from Supabase."""
        try:
            result = self._client.table("members").select("*").execute()
            return result.data or []
        except Exception as e:
            logger.error("Failed to load members: %s", e)
            return []

    def load_positions(self) -> list:
        """Load current positions from Supabase."""
        try:
            result = self._client.table("positions").select("*").execute()
            return result.data or []
        except Exception as e:
            logger.error("Failed to load positions: %s", e)
            return []

    def push_signals(self, signals: list) -> None:
        """Upsert active signals to Supabase."""
        try:
            for sig in signals:
                self._client.table("signals").upsert({
                    "symbol": sig["symbol"],
                    "signal_strength": sig["signal_strength"],
                    "entropy": sig["entropy"],
                    "node_temperature": sig["node_temperature"],
                    "belief_type": sig.get("belief_type", "unknown"),
                    "conviction": sig.get("conviction", 0),
                    "last_seen": datetime.utcnow().isoformat(),
                    "status": sig.get("status", "active"),
                }, on_conflict="symbol,status").execute()
        except Exception as e:
            logger.error("Failed to push signals: %s", e)
