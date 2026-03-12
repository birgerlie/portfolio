"""Unit tests for EmailReporter — no SMTP or OpenAI calls."""
import re
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from fund.email_reports import EmailReporter


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_reporter():
    return EmailReporter(
        smtp_host="smtp.example.com",
        smtp_port=587,
        from_addr="fund@example.com",
        username="fund@example.com",
        password="secret",
    )


def _snapshot():
    return {
        "date": "2026-03-07",
        "nav": 1_250_000.0,
        "nav_per_unit": 1.25,
        "units_outstanding": 1_000_000.0,
        "high_water_mark": 1.22,
        "cash": 150_000.0,
        "positions_count": 7,
    }


def _nav_history():
    return [
        {"date": "2026-02-28", "nav_per_unit": 1.20, "net_return_pct": 0.02},
        {"date": "2026-03-07", "nav_per_unit": 1.25, "net_return_pct": 0.042},
    ]


def _positions():
    return [
        {"symbol": "AAPL", "market_value": 200_000, "unrealized_pl_pct": 0.12, "allocation_pct": 0.16},
        {"symbol": "MSFT", "market_value": 180_000, "unrealized_pl_pct": 0.08, "allocation_pct": 0.144},
    ]


def _thermo():
    return {"clarity_score": 0.78, "opportunity_score": 0.65, "market_health": "green", "momentum": "rising"}


# ── __init__ ─────────────────────────────────────────────────────────────────

def test_init_stores_config():
    r = _make_reporter()
    assert r.smtp_host == "smtp.example.com"
    assert r.smtp_port == 587
    assert r.from_addr == "fund@example.com"


def test_init_optional_synthesizer_defaults_none():
    r = _make_reporter()
    assert r.belief_synthesizer is None


def test_init_with_synthesizer():
    synth = MagicMock()
    r = EmailReporter("host", 587, "a@b.com", synthesizer=synth)
    assert r.belief_synthesizer is synth


# ── generate_weekly_html ─────────────────────────────────────────────────────

def test_weekly_html_is_string():
    r = _make_reporter()
    html = r.generate_weekly_html(
        snapshot=_snapshot(),
        nav_history=_nav_history(),
        positions=_positions(),
        narrative="Strong week.",
        thermo=_thermo(),
    )
    assert isinstance(html, str)


def test_weekly_html_contains_nav():
    r = _make_reporter()
    html = r.generate_weekly_html(_snapshot(), _nav_history(), _positions(), "OK", _thermo())
    assert "1,250,000" in html or "1250000" in html


def test_weekly_html_contains_nav_per_unit():
    r = _make_reporter()
    html = r.generate_weekly_html(_snapshot(), _nav_history(), _positions(), "OK", _thermo())
    assert "1.25" in html


def test_weekly_html_contains_positions():
    r = _make_reporter()
    html = r.generate_weekly_html(_snapshot(), _nav_history(), _positions(), "OK", _thermo())
    assert "AAPL" in html
    assert "MSFT" in html


def test_weekly_html_contains_narrative():
    r = _make_reporter()
    html = r.generate_weekly_html(_snapshot(), _nav_history(), _positions(), "Strong week.", _thermo())
    assert "Strong week." in html


def test_weekly_html_contains_thermo():
    r = _make_reporter()
    html = r.generate_weekly_html(_snapshot(), _nav_history(), _positions(), "OK", _thermo())
    assert "0.78" in html or "78" in html  # clarity score


def test_weekly_html_dark_theme():
    r = _make_reporter()
    html = r.generate_weekly_html(_snapshot(), _nav_history(), _positions(), "OK", _thermo())
    # dark background colour somewhere in inline CSS
    assert "#0a0a0a" in html or "#111" in html or "background" in html


def test_weekly_html_valid_structure():
    r = _make_reporter()
    html = r.generate_weekly_html(_snapshot(), _nav_history(), _positions(), "OK", _thermo())
    assert html.strip().startswith("<!DOCTYPE html") or "<html" in html
    assert "</html>" in html


# ── generate_monthly_html ────────────────────────────────────────────────────

def test_monthly_html_is_string():
    r = _make_reporter()
    html = r.generate_monthly_html(
        snapshot=_snapshot(),
        nav_history=_nav_history(),
        positions=_positions(),
        narrative="Good month.",
        thermo=_thermo(),
        fee_statement={"mgmt_fee": 2083.33, "perf_fee": 5000.0, "total_fee": 7083.33},
        decisions=[
            {"type": "buy", "symbol": "AAPL", "quantity": 10, "summary": "Increased conviction"},
        ],
    )
    assert isinstance(html, str)


def test_monthly_html_contains_fee_statement():
    r = _make_reporter()
    html = r.generate_monthly_html(
        _snapshot(), _nav_history(), _positions(), "OK", _thermo(),
        fee_statement={"mgmt_fee": 2083.33, "perf_fee": 5000.0, "total_fee": 7083.33},
        decisions=[],
    )
    assert "2,083" in html or "2083" in html


def test_monthly_html_contains_decisions():
    r = _make_reporter()
    html = r.generate_monthly_html(
        _snapshot(), _nav_history(), _positions(), "OK", _thermo(),
        fee_statement={"mgmt_fee": 0, "perf_fee": 0, "total_fee": 0},
        decisions=[{"type": "buy", "symbol": "NVDA", "summary": "GPU play"}],
    )
    assert "NVDA" in html


# ── send_report ───────────────────────────────────────────────────────────────

@patch("fund.email_reports.smtplib.SMTP")
def test_send_report_connects_and_sends(mock_smtp_cls):
    smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=smtp)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    r = _make_reporter()
    r.send_report(
        to_addrs=["investor@example.com"],
        subject="Weekly Report",
        html="<html><body>Hello</body></html>",
    )

    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)


@patch("fund.email_reports.smtplib.SMTP")
def test_send_report_multiple_recipients(mock_smtp_cls):
    smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=smtp)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    r = _make_reporter()
    r.send_report(
        to_addrs=["a@x.com", "b@x.com"],
        subject="Monthly Report",
        html="<html></html>",
    )
    mock_smtp_cls.assert_called_once()


@patch("fund.email_reports.smtplib.SMTP")
def test_send_report_smtp_error_raises(mock_smtp_cls):
    mock_smtp_cls.side_effect = ConnectionRefusedError("refused")

    r = _make_reporter()
    with pytest.raises(ConnectionRefusedError):
        r.send_report(["x@y.com"], "Test", "<html></html>")
