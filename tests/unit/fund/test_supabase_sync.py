"""Tests for Supabase sync client."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

from fund.supabase_sync import SupabaseSync, SupabaseConfig


class TestSupabaseConfig:
    def test_create_config(self):
        config = SupabaseConfig(url="https://abc.supabase.co", key="test-key")
        assert config.url == "https://abc.supabase.co"


class TestSupabaseSyncSnapshot:
    def test_push_fund_snapshot(self):
        mock_client = MagicMock()
        sync = SupabaseSync.__new__(SupabaseSync)
        sync._client = mock_client

        snapshot = {
            "date": "2026-03-12",
            "nav": 100000,
            "nav_per_unit": 105,
            "positions_count": 3,
        }

        sync.push_snapshot(snapshot)

        mock_client.table.assert_called_once_with("fund_snapshots")
        mock_client.table().upsert.assert_called_once()

    def test_push_journal(self):
        mock_client = MagicMock()
        sync = SupabaseSync.__new__(SupabaseSync)
        sync._client = mock_client

        journal_data = {
            "date": "2026-03-12",
            "entries": [{"type": "trade_executed", "summary": "Bought NVDA"}],
            "trades_executed": 1,
        }

        sync.push_journal(journal_data)

        mock_client.table.assert_called_once_with("journals")
        mock_client.table().upsert.assert_called_once()

    def test_push_heartbeat(self):
        mock_client = MagicMock()
        sync = SupabaseSync.__new__(SupabaseSync)
        sync._client = mock_client

        heartbeat = {
            "status": "running",
            "alpaca_connected": True,
            "active_positions": 3,
        }

        sync.push_heartbeat(heartbeat)

        mock_client.table.assert_called_once_with("engine_heartbeat")
        mock_client.table().upsert.assert_called_once()
