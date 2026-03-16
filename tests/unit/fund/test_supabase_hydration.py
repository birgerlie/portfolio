"""Tests for SupabaseSync startup hydration methods."""

from unittest.mock import MagicMock

from fund.supabase_sync import SupabaseSync


def _make_sync(client):
    """Create a SupabaseSync instance without calling __init__."""
    instance = SupabaseSync.__new__(SupabaseSync)
    instance._client = client
    return instance


class TestLoadFundState:
    def test_returns_dict_from_data(self):
        client = MagicMock()
        snapshot = {"id": "abc", "nav": 100000.0}
        client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [snapshot]
        sync = _make_sync(client)
        result = sync.load_fund_state()
        assert result == snapshot

    def test_returns_empty_dict_when_no_data(self):
        client = MagicMock()
        client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        sync = _make_sync(client)
        result = sync.load_fund_state()
        assert result == {}

    def test_returns_empty_dict_on_exception(self):
        client = MagicMock()
        client.table.side_effect = Exception("connection error")
        sync = _make_sync(client)
        result = sync.load_fund_state()
        assert result == {}


class TestLoadMembers:
    def test_returns_list_of_members(self):
        client = MagicMock()
        members = [{"id": "1", "email": "a@example.com"}, {"id": "2", "email": "b@example.com"}]
        client.table.return_value.select.return_value.execute.return_value.data = members
        sync = _make_sync(client)
        result = sync.load_members()
        assert result == members

    def test_returns_empty_list_when_no_data(self):
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = []
        sync = _make_sync(client)
        result = sync.load_members()
        assert result == []

    def test_returns_empty_list_on_exception(self):
        client = MagicMock()
        client.table.side_effect = Exception("connection error")
        sync = _make_sync(client)
        result = sync.load_members()
        assert result == []


class TestLoadPositions:
    def test_returns_list_of_positions(self):
        client = MagicMock()
        positions = [{"symbol": "AAPL", "qty": 10}, {"symbol": "MSFT", "qty": 5}]
        client.table.return_value.select.return_value.execute.return_value.data = positions
        sync = _make_sync(client)
        result = sync.load_positions()
        assert result == positions

    def test_returns_empty_list_when_no_data(self):
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = []
        sync = _make_sync(client)
        result = sync.load_positions()
        assert result == []

    def test_returns_empty_list_on_exception(self):
        client = MagicMock()
        client.table.side_effect = Exception("connection error")
        sync = _make_sync(client)
        result = sync.load_positions()
        assert result == []
