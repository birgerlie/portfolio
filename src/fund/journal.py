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
