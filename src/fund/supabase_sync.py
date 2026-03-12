"""Push fund data to Supabase for the web dashboard."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


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
        snapshot["updated_at"] = datetime.now().isoformat()
        self._client.table("fund_snapshots").upsert(snapshot, on_conflict="date").execute()

    def push_journal(self, journal_data: Dict[str, Any]) -> None:
        """Push a daily journal. Upserts on date."""
        journal_data["updated_at"] = datetime.now().isoformat()
        self._client.table("journals").upsert(journal_data, on_conflict="date").execute()

    def push_heartbeat(self, heartbeat: Dict[str, Any]) -> None:
        """Push engine heartbeat. Upserts on singleton row."""
        heartbeat["updated_at"] = datetime.now().isoformat()
        self._client.table("engine_heartbeat").upsert(heartbeat, on_conflict="id").execute()

    def push_positions(self, positions: list) -> None:
        """Push current positions snapshot."""
        self._client.table("positions").upsert(
            [{"updated_at": datetime.now().isoformat(), **p} for p in positions],
            on_conflict="symbol",
        ).execute()
