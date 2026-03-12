"""Tests for the daily event journal."""

from datetime import date, datetime

from fund.journal import JournalEntry


class TestJournalEntry:
    def test_create_entry(self):
        entry = JournalEntry(
            timestamp=datetime(2026, 3, 12, 10, 30, 0),
            entry_type="trade_executed",
            summary="Bought 100 shares of NVDA at $850",
            data={"symbol": "NVDA", "side": "BUY", "quantity": 100, "price": 850.0},
        )
        assert entry.entry_type == "trade_executed"
        assert entry.summary == "Bought 100 shares of NVDA at $850"
        assert entry.data["symbol"] == "NVDA"

    def test_entry_to_dict_and_back(self):
        entry = JournalEntry(
            timestamp=datetime(2026, 3, 12, 10, 30, 0),
            entry_type="regime_change",
            summary="Regime shifted from BULL to TRANSITION",
            data={"from": "BULL", "to": "TRANSITION"},
        )
        d = entry.to_dict()
        assert d["timestamp"] == "2026-03-12T10:30:00"
        assert d["entry_type"] == "regime_change"
        assert d["data"]["from"] == "BULL"

        restored = JournalEntry.from_dict(d)
        assert restored.entry_type == entry.entry_type
        assert restored.summary == entry.summary
        assert restored.data == entry.data
