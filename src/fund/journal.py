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
