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
