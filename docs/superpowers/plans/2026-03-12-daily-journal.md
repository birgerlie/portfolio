# Daily Event Journal Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a crash-safe daily event journal that appends each entry to disk immediately and produces a final JSON summary at end of day.

**Architecture:** Each `log()` call appends a JSON line to `journals/YYYY-MM-DD.jsonl` (one entry per line, crash-safe). At end of day, `flush()` writes a final summary JSON and the JSONL becomes the append log. On startup, the journal recovers state by reading the current day's JSONL if it exists.

**Tech Stack:** Python dataclasses, JSON Lines for append-safe writes, no external dependencies.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/fund/journal.py` | `JournalEntry`, `DailyJournal`, `EventJournal` |
| `tests/unit/fund/test_journal.py` | Unit tests |

---

## Chunk 1: Daily Event Journal

### Task 1: JournalEntry Type

**Files:**
- Create: `tests/unit/fund/test_journal.py`
- Create: `src/fund/journal.py`

- [ ] **Step 1: Write failing tests for JournalEntry**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/fund/test_journal.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement JournalEntry**

```python
"""Daily event journal — crash-safe, append-on-write."""

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class JournalEntry:
    """Single event in the daily journal."""

    timestamp: datetime
    entry_type: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "entry_type": self.entry_type,
            "summary": self.summary,
            "data": self.data,
        }

    @staticmethod
    def from_dict(d: dict) -> "JournalEntry":
        return JournalEntry(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            entry_type=d["entry_type"],
            summary=d["summary"],
            data=d.get("data", {}),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/fund/test_journal.py::TestJournalEntry -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/fund/test_journal.py src/fund/journal.py
git commit -m "feat(fund): journal entry type with serialization"
```

---

### Task 2: EventJournal — Crash-Safe Append-on-Write

**Files:**
- Modify: `tests/unit/fund/test_journal.py`
- Modify: `src/fund/journal.py`

- [ ] **Step 1: Write failing tests for EventJournal**

Add to `test_journal.py`:

```python
import json
import os
import tempfile

from fund.journal import JournalEntry, DailyJournal, EventJournal


class TestEventJournal:
    def test_log_appends_to_disk_immediately(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            journal.log("trade_executed", "Bought NVDA", {"symbol": "NVDA"})

            # File should exist on disk already
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
            # Session 1: log some entries
            j1 = EventJournal(journal_dir=tmpdir)
            j1.log("trade_executed", "Bought NVDA", {"symbol": "NVDA"})
            j1.log("regime_change", "Bull to Bear", {})

            # Session 2: new instance (simulates restart after crash)
            j2 = EventJournal(journal_dir=tmpdir)
            assert len(j2.today.entries) == 2
            assert j2.today.entries[0].entry_type == "trade_executed"

            # New entries append correctly
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/fund/test_journal.py::TestEventJournal -v`
Expected: FAIL

- [ ] **Step 3: Implement DailyJournal and EventJournal**

Add to `src/fund/journal.py`:

```python
@dataclass
class DailyJournal:
    """All events for a single day."""

    date: date
    entries: List[JournalEntry] = field(default_factory=list)
    regime_summary: str = ""
    belief_snapshot: Dict[str, Any] = field(default_factory=dict)
    nav_change_pct: float = 0.0
    thermo_snapshot: Dict[str, Any] = field(default_factory=dict)

    @property
    def trades_executed(self) -> int:
        return sum(1 for e in self.entries if e.entry_type == "trade_executed")

    def to_dict(self) -> dict:
        return {
            "date": str(self.date),
            "entries": [e.to_dict() for e in self.entries],
            "regime_summary": self.regime_summary,
            "belief_snapshot": self.belief_snapshot,
            "trades_executed": self.trades_executed,
            "nav_change_pct": self.nav_change_pct,
            "thermo_snapshot": self.thermo_snapshot,
        }


class EventJournal:
    """Crash-safe daily event journal. Each log() appends to disk immediately."""

    def __init__(self, journal_dir: str = "journals"):
        self._journal_dir = journal_dir
        self._today = DailyJournal(date=date.today())
        self._recover()

    def _log_path(self) -> str:
        return os.path.join(self._journal_dir, f"{self._today.date}.jsonl")

    def _recover(self) -> None:
        """Recover entries from existing JSONL file (crash recovery)."""
        path = self._log_path()
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._today.entries.append(JournalEntry.from_dict(json.loads(line)))

    @property
    def today(self) -> DailyJournal:
        current = date.today()
        if self._today.date != current:
            self._today = DailyJournal(date=current)
        return self._today

    def log(self, entry_type: str, summary: str, data: Dict[str, Any] = None) -> None:
        entry = JournalEntry(
            timestamp=datetime.now(),
            entry_type=entry_type,
            summary=summary,
            data=data or {},
        )
        self.today.entries.append(entry)
        # Append to disk immediately — crash safe
        os.makedirs(self._journal_dir, exist_ok=True)
        with open(self._log_path(), "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def set_eod_summary(
        self,
        regime_summary: str = "",
        belief_snapshot: Optional[Dict[str, Any]] = None,
        nav_change_pct: float = 0.0,
        thermo_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.today.regime_summary = regime_summary
        self.today.belief_snapshot = belief_snapshot or {}
        self.today.nav_change_pct = nav_change_pct
        self.today.thermo_snapshot = thermo_snapshot or {}

    def flush(self) -> str:
        """Write final summary JSON for the day. Returns path to the summary file."""
        os.makedirs(self._journal_dir, exist_ok=True)
        summary_path = os.path.join(self._journal_dir, f"{self.today.date}.json")
        with open(summary_path, "w") as f:
            json.dump(self.today.to_dict(), f, indent=2)
        self._today = DailyJournal(date=self._today.date)
        # Clear the JSONL log since we have the summary
        jsonl_path = self._log_path()
        if os.path.exists(jsonl_path):
            os.remove(jsonl_path)
        return summary_path

    @staticmethod
    def load_date(d: date, journal_dir: str = "journals") -> DailyJournal:
        """Load a completed day's summary from disk."""
        path = os.path.join(journal_dir, f"{d}.json")
        with open(path) as f:
            data = json.load(f)
        return DailyJournal(
            date=d,
            entries=[JournalEntry.from_dict(e) for e in data["entries"]],
            regime_summary=data.get("regime_summary", ""),
            belief_snapshot=data.get("belief_snapshot", {}),
            nav_change_pct=data.get("nav_change_pct", 0.0),
            thermo_snapshot=data.get("thermo_snapshot", {}),
        )
```

Key design: `log()` appends a JSONL line immediately. On restart, `_recover()` replays the JSONL. `flush()` writes the final summary JSON and removes the JSONL.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/fund/test_journal.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Update `__init__.py` exports**

Add to `src/fund/__init__.py`:

```python
from fund.journal import JournalEntry, DailyJournal, EventJournal
```

And add `"JournalEntry", "DailyJournal", "EventJournal"` to `__all__`.

- [ ] **Step 6: Commit**

```bash
git add src/fund/journal.py src/fund/__init__.py tests/unit/fund/test_journal.py
git commit -m "feat(fund): crash-safe daily event journal with append-on-write"
```
