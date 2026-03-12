"""Tests for the daily event journal."""

import json
import os
import tempfile
from datetime import date, datetime

from fund.journal import JournalEntry, DailyJournal, EventJournal


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


class TestEventJournal:
    def test_log_appends_to_disk_immediately(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            journal.log("trade_executed", "Bought NVDA", {"symbol": "NVDA"})

            log_path = os.path.join(tmpdir, f"{date.today()}.jsonl")
            assert os.path.exists(log_path)
            with open(log_path) as f:
                lines = f.readlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["entry_type"] == "trade_executed"

    def test_log_multiple_entries_all_on_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            journal.log("regime_change", "Bull to Bear", {})
            journal.log("trade_executed", "Sold AAPL", {"symbol": "AAPL"})

            log_path = os.path.join(tmpdir, f"{date.today()}.jsonl")
            with open(log_path) as f:
                lines = f.readlines()
            assert len(lines) == 2

    def test_entries_in_memory_match_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            journal.log("trade_executed", "Bought NVDA", {"symbol": "NVDA"})
            assert len(journal.today.entries) == 1
            assert journal.today.entries[0].entry_type == "trade_executed"

    def test_today_property_returns_current_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            assert journal.today.date == date.today()

    def test_recovery_from_crash(self):
        """Simulate crash by creating new EventJournal on same directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            j1 = EventJournal(journal_dir=tmpdir)
            j1.log("trade_executed", "Bought NVDA", {"symbol": "NVDA"})
            j1.log("regime_change", "Bull to Bear", {})

            j2 = EventJournal(journal_dir=tmpdir)
            assert len(j2.today.entries) == 2
            assert j2.today.entries[0].entry_type == "trade_executed"

            j2.log("belief_update", "AAPL up", {})
            assert len(j2.today.entries) == 3

    def test_flush_writes_summary_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            journal.log("trade_executed", "Bought NVDA", {"symbol": "NVDA"})
            journal.log("regime_change", "Bull all day", {"regime": "BULL"})
            journal.set_eod_summary(
                regime_summary="Bull all day",
                belief_snapshot={"NVDA": 0.85},
                nav_change_pct=0.02,
                thermo_snapshot={"clarity": 0.78},
            )

            path = journal.flush()

            assert path.endswith(".json")
            with open(path) as f:
                data = json.load(f)
            assert data["date"] == str(date.today())
            assert len(data["entries"]) == 2
            assert data["regime_summary"] == "Bull all day"
            assert data["nav_change_pct"] == 0.02
            assert data["trades_executed"] == 1

    def test_flush_resets_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            journal.log("trade_executed", "Bought NVDA", {})
            journal.flush()
            assert len(journal.today.entries) == 0

    def test_trades_executed_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            journal.log("regime_change", "Bull", {})
            journal.log("trade_executed", "Bought NVDA", {})
            journal.log("trade_executed", "Sold AAPL", {})
            journal.log("belief_update", "NVDA up", {})
            assert journal.today.trades_executed == 2

    def test_load_past_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            journal.log("trade_executed", "Bought NVDA", {"symbol": "NVDA"})
            journal.flush()

            loaded = EventJournal.load_date(date.today(), journal_dir=tmpdir)
            assert loaded.date == date.today()
            assert len(loaded.entries) == 1
            assert loaded.entries[0].entry_type == "trade_executed"
