# Notifications Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Event-driven notification system that routes fund alerts (regime changes, trades, NAV, etc.) to Supabase Realtime (web push) and optionally email, with a Prisma model and a Next.js API route for the web app.

**Architecture:** `NotificationManager` receives typed events and routes them by priority: HIGH → email + Supabase push, MEDIUM/LOW → Supabase push only. Notifications are stored in Supabase `notifications` table; the web app subscribes via Supabase Realtime. The Prisma schema adds the `Notification` model so Prisma client can also query it.

**Tech Stack:** `SupabaseSync` (existing), optional `EmailReporter` (sub-project 6), Prisma (web), Next.js App Router API route.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/fund/notifications.py` | `NotificationManager` — event routing + Supabase push |
| `src/fund/__init__.py` | Export `NotificationManager` |
| `tests/unit/fund/test_notifications.py` | Unit tests with mocked dependencies |
| `web/prisma/schema.prisma` | Add `Notification` model |
| `web/src/app/api/notifications/route.ts` | GET/POST notification endpoints |

---

## Chunk 1: NotificationManager

### Task 1.1: Write failing tests first

- [ ] Create `tests/unit/fund/test_notifications.py`:

```python
"""Unit tests for NotificationManager."""
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest

from fund.notifications import NotificationManager, NotificationPriority, EventType


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_manager(with_email=False):
    supabase = MagicMock()
    email = MagicMock() if with_email else None
    return NotificationManager(supabase_sync=supabase, email_reporter=email), supabase, email


# ── NotificationPriority / EventType enums ────────────────────────────────────

def test_priority_values():
    assert NotificationPriority.HIGH.value == "high"
    assert NotificationPriority.MEDIUM.value == "medium"
    assert NotificationPriority.LOW.value == "low"


def test_event_type_values():
    assert EventType.REGIME_SHIFT.value == "regime_shift"
    assert EventType.TRADE_EXECUTED.value == "trade_executed"
    assert EventType.NAV_PUBLISHED.value == "nav_published"
    assert EventType.SUBSCRIPTION_PROCESSED.value == "subscription_processed"
    assert EventType.DANGER_ZONE.value == "danger_zone"
    assert EventType.FEE_STATEMENT.value == "fee_statement"
    assert EventType.CONVICTION_CHANGED.value == "conviction_changed"


# ── __init__ ──────────────────────────────────────────────────────────────────

def test_init_stores_supabase():
    mgr, sync, _ = _make_manager()
    assert mgr.supabase_sync is sync


def test_init_optional_email_defaults_none():
    mgr, _, _ = _make_manager()
    assert mgr.email_reporter is None


def test_init_with_email_reporter():
    mgr, _, email = _make_manager(with_email=True)
    assert mgr.email_reporter is email


# ── notify routing ────────────────────────────────────────────────────────────

def test_notify_high_priority_calls_supabase():
    mgr, sync, _ = _make_manager()
    mgr.notify(EventType.DANGER_ZONE, NotificationPriority.HIGH, {"msg": "danger"})
    sync.push_notification.assert_called_once()


def test_notify_medium_priority_calls_supabase():
    mgr, sync, _ = _make_manager()
    mgr.notify(EventType.TRADE_EXECUTED, NotificationPriority.MEDIUM, {"symbol": "AAPL"})
    sync.push_notification.assert_called_once()


def test_notify_low_priority_calls_supabase():
    mgr, sync, _ = _make_manager()
    mgr.notify(EventType.NAV_PUBLISHED, NotificationPriority.LOW, {"nav": 1.25})
    sync.push_notification.assert_called_once()


def test_notify_high_priority_calls_email_when_configured():
    mgr, sync, email = _make_manager(with_email=True)
    mgr.notify(
        EventType.DANGER_ZONE,
        NotificationPriority.HIGH,
        {"msg": "Market danger zone entered"},
        to_addrs=["investor@example.com"],
    )
    email.send_report.assert_called_once()


def test_notify_medium_priority_no_email():
    mgr, sync, email = _make_manager(with_email=True)
    mgr.notify(EventType.TRADE_EXECUTED, NotificationPriority.MEDIUM, {"symbol": "MSFT"})
    email.send_report.assert_not_called()


def test_notify_high_no_email_reporter_still_pushes_supabase():
    mgr, sync, _ = _make_manager(with_email=False)
    mgr.notify(EventType.DANGER_ZONE, NotificationPriority.HIGH, {})
    sync.push_notification.assert_called_once()


# ── push_to_supabase ──────────────────────────────────────────────────────────

def test_push_to_supabase_calls_sync():
    mgr, sync, _ = _make_manager()
    notification = {
        "event_type": "regime_shift",
        "priority": "high",
        "title": "Regime changed",
        "data": {},
    }
    mgr.push_to_supabase(notification)
    sync.push_notification.assert_called_once()
    passed = sync.push_notification.call_args[0][0]
    assert passed["event_type"] == "regime_shift"


def test_push_to_supabase_adds_created_at():
    mgr, sync, _ = _make_manager()
    mgr.push_to_supabase({"event_type": "nav_published", "priority": "low", "title": "NAV", "data": {}})
    passed = sync.push_notification.call_args[0][0]
    assert "created_at" in passed


def test_push_to_supabase_adds_read_false():
    mgr, sync, _ = _make_manager()
    mgr.push_to_supabase({"event_type": "nav_published", "priority": "low", "title": "NAV", "data": {}})
    passed = sync.push_notification.call_args[0][0]
    assert passed.get("read") is False


# ── notify payload structure ──────────────────────────────────────────────────

def test_notify_passes_correct_event_type_string():
    mgr, sync, _ = _make_manager()
    mgr.notify(EventType.REGIME_SHIFT, NotificationPriority.MEDIUM, {"old": "bull", "new": "bear"})
    passed = sync.push_notification.call_args[0][0]
    assert passed["event_type"] == "regime_shift"


def test_notify_passes_priority_string():
    mgr, sync, _ = _make_manager()
    mgr.notify(EventType.FEE_STATEMENT, NotificationPriority.LOW, {})
    passed = sync.push_notification.call_args[0][0]
    assert passed["priority"] == "low"


def test_notify_includes_data():
    mgr, sync, _ = _make_manager()
    mgr.notify(EventType.CONVICTION_CHANGED, NotificationPriority.MEDIUM, {"symbol": "NVDA", "old_p": 0.5, "new_p": 0.8})
    passed = sync.push_notification.call_args[0][0]
    assert passed["data"]["symbol"] == "NVDA"


# ── convenience methods ───────────────────────────────────────────────────────

def test_regime_shift_convenience():
    mgr, sync, _ = _make_manager()
    mgr.regime_shift(old_regime="bull", new_regime="bear")
    passed = sync.push_notification.call_args[0][0]
    assert passed["event_type"] == "regime_shift"
    assert passed["priority"] == "high"


def test_trade_executed_convenience():
    mgr, sync, _ = _make_manager()
    mgr.trade_executed(symbol="AAPL", action="buy", quantity=10, price=185.0)
    passed = sync.push_notification.call_args[0][0]
    assert passed["event_type"] == "trade_executed"


def test_nav_published_convenience():
    mgr, sync, _ = _make_manager()
    mgr.nav_published(nav=1_250_000.0, nav_per_unit=1.25, change_pct=0.042)
    passed = sync.push_notification.call_args[0][0]
    assert passed["event_type"] == "nav_published"
```

- [ ] Verify tests fail:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/test_notifications.py -v 2>&1 | head -20
# Expected: ModuleNotFoundError
```

### Task 1.2: Implement NotificationManager

- [ ] Create `src/fund/notifications.py`:

```python
"""Event-driven notification routing for the fund engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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
```

- [ ] Add `push_notification` to `SupabaseSync` so tests don't break at runtime (it's called via the mock in tests, but needs to exist in the real class):

Edit `src/fund/supabase_sync.py` — add after `push_positions`:

```python
    def push_notification(self, notification: dict) -> None:
        """Insert a notification row for web push via Supabase Realtime."""
        self._client.table("notifications").insert(notification).execute()
```

- [ ] Verify tests pass:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/test_notifications.py -v
```

- [ ] Commit:

```bash
cd /Users/birger/code/portfolio
git add src/fund/notifications.py src/fund/supabase_sync.py tests/unit/fund/test_notifications.py
git commit -m "$(cat <<'EOF'
feat: add NotificationManager with priority-based routing to Supabase and email

Seven event types, three priority levels. HIGH priority routes to email
when EmailReporter is configured. Convenience methods for common events
(regime_shift, trade_executed, nav_published, danger_zone, conviction_changed).
Adds push_notification to SupabaseSync.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 2: Prisma Model + Next.js API Route

### Task 2.1: Add Notification Prisma model

- [ ] Edit `web/prisma/schema.prisma` — append after the last model:

```prisma
// ── Notifications ──────────────────────────────────────────────────────────

model Notification {
  id          String   @id @default(cuid())
  eventType   String   @map("event_type")
  priority    String   // high / medium / low
  title       String
  data        Json     @default("{}")
  read        Boolean  @default(false)
  createdAt   DateTime @map("created_at") @default(now())

  @@map("notifications")
}
```

- [ ] Commit schema:

```bash
cd /Users/birger/code/portfolio
git add web/prisma/schema.prisma
git commit -m "$(cat <<'EOF'
feat: add Notification Prisma model for web push notifications

Maps to Supabase notifications table. Frontend subscribes via Realtime
for live updates; Prisma client used for server-side queries.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

### Task 2.2: Next.js notifications API route

- [ ] Verify the `web/src/app/api/` directory structure:

```bash
ls /Users/birger/code/portfolio/web/src/app/api/
```

- [ ] Create `web/src/app/api/notifications/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

/**
 * GET /api/notifications
 * Returns recent notifications, newest first.
 * Query params:
 *   limit  — max rows (default 50)
 *   unread — if "true", only unread notifications
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const limit = Math.min(parseInt(searchParams.get("limit") ?? "50", 10), 200);
  const unreadOnly = searchParams.get("unread") === "true";

  const where = unreadOnly ? { read: false } : {};

  const notifications = await prisma.notification.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: limit,
  });

  return NextResponse.json({ notifications });
}

/**
 * POST /api/notifications/mark-read
 * Body: { ids: string[] }  — mark specific notifications as read.
 * Body: { all: true }      — mark all as read.
 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));

  if (body.all === true) {
    await prisma.notification.updateMany({ data: { read: true } });
    return NextResponse.json({ ok: true, updated: "all" });
  }

  const ids: string[] = Array.isArray(body.ids) ? body.ids : [];
  if (ids.length === 0) {
    return NextResponse.json({ error: "Provide ids[] or all:true" }, { status: 400 });
  }

  const result = await prisma.notification.updateMany({
    where: { id: { in: ids } },
    data: { read: true },
  });

  return NextResponse.json({ ok: true, updated: result.count });
}
```

- [ ] Export `NotificationManager` from `src/fund/__init__.py`:

```python
from fund.notifications import NotificationManager
# Add "NotificationManager" to __all__
```

- [ ] Run full unit test suite to confirm no regressions:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/ -v --tb=short
```

- [ ] Commit:

```bash
cd /Users/birger/code/portfolio
git add web/src/app/api/notifications/route.ts src/fund/__init__.py
git commit -m "$(cat <<'EOF'
feat: add notifications API route and export NotificationManager

GET /api/notifications supports limit and unread filters.
POST marks individual or all notifications as read.
NotificationManager exported from fund package.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Done Criteria

- [ ] `NotificationManager` has `notify`, `push_to_supabase`, and five convenience methods
- [ ] Priority routing: HIGH → Supabase + email (when configured), MEDIUM/LOW → Supabase only
- [ ] `SupabaseSync.push_notification` inserts to `notifications` table
- [ ] Prisma `Notification` model added to `web/prisma/schema.prisma`
- [ ] `GET /api/notifications` returns recent notifications with optional unread filter
- [ ] `POST /api/notifications` marks notifications as read
- [ ] All unit tests pass: `pytest tests/unit/fund/test_notifications.py -v`
- [ ] `NotificationManager` is exported from `fund.__init__`
