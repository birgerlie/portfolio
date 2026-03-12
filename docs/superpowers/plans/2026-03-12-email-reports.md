# Email Reports Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and send beautiful HTML weekly/monthly fund reports via email using only Python stdlib — no external email deps.

**Architecture:** `EmailReporter` owns two concerns: (1) rendering HTML from fund state data, and (2) sending via SMTP. HTML uses inline CSS with a dark theme matching the web dashboard. An optional `BeliefSynthesizer` provides the narrative paragraph. The automation controller calls `EmailReporter` on schedule.

**Tech Stack:** `email` + `smtplib` (stdlib), optional `BeliefSynthesizer` for narrative, existing fund types (`WeeklyNAV`, `FeeBreakdown`, `BrokerPosition`).

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/fund/email_reports.py` | `EmailReporter` — HTML generation + SMTP sending |
| `src/fund/__init__.py` | Export `EmailReporter` |
| `tests/unit/fund/test_email_reports.py` | Unit tests (no SMTP calls, no OpenAI calls) |

---

## Chunk 1: EmailReporter Core

### Task 1.1: Write failing tests first

- [ ] Create `tests/unit/fund/test_email_reports.py`:

```python
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
```

- [ ] Verify tests fail:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/test_email_reports.py -v 2>&1 | head -20
# Expected: ModuleNotFoundError
```

### Task 1.2: Implement EmailReporter

- [ ] Create `src/fund/email_reports.py`:

```python
"""HTML email report generation and delivery for the fund."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional


class EmailReporter:
    """Generate and send HTML fund reports via SMTP."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        from_addr: str,
        username: str = "",
        password: str = "",
        synthesizer=None,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_addr = from_addr
        self._username = username
        self._password = password
        self.belief_synthesizer = synthesizer

    # ── public API ───────────────────────────────────────────────────────────

    def generate_weekly_html(
        self,
        snapshot: Dict[str, Any],
        nav_history: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        narrative: str,
        thermo: Dict[str, Any],
    ) -> str:
        """Render weekly report as HTML string with inline dark-theme CSS."""
        positions_rows = "\n".join(
            f"""
            <tr>
              <td>{p['symbol']}</td>
              <td style="text-align:right">${p.get('market_value', 0):,.0f}</td>
              <td style="text-align:right">{p.get('allocation_pct', 0)*100:.1f}%</td>
              <td style="text-align:right;color:{_pl_color(p.get('unrealized_pl_pct', 0))}">{p.get('unrealized_pl_pct', 0)*100:+.1f}%</td>
            </tr>"""
            for p in positions
        )

        nav_rows = "\n".join(
            f"""<tr><td>{h['date']}</td>
              <td style="text-align:right">${h.get('nav_per_unit', 0):.4f}</td>
              <td style="text-align:right;color:{_pl_color(h.get('net_return_pct', 0))}">{h.get('net_return_pct', 0)*100:+.2f}%</td>
            </tr>"""
            for h in nav_history[-8:]  # last 8 weeks
        )

        health_color = {"green": "#22c55e", "yellow": "#eab308", "red": "#ef4444"}.get(
            thermo.get("market_health", "green"), "#22c55e"
        )

        return _BASE_TEMPLATE.format(
            title="Weekly Fund Report",
            date=snapshot.get("date", ""),
            nav=f"${snapshot.get('nav', 0):,.0f}",
            nav_per_unit=f"${snapshot.get('nav_per_unit', 0):.4f}",
            units=f"{snapshot.get('units_outstanding', 0):,.0f}",
            hwm=f"${snapshot.get('high_water_mark', 0):.4f}",
            cash=f"${snapshot.get('cash', 0):,.0f}",
            positions_count=snapshot.get("positions_count", 0),
            narrative=narrative,
            clarity=f"{thermo.get('clarity_score', 0)*100:.0f}",
            opportunity=f"{thermo.get('opportunity_score', 0)*100:.0f}",
            market_health=thermo.get("market_health", "green").upper(),
            health_color=health_color,
            momentum=thermo.get("momentum", "steady").title(),
            positions_rows=positions_rows,
            nav_rows=nav_rows,
            extra_section="",
        )

    def generate_monthly_html(
        self,
        snapshot: Dict[str, Any],
        nav_history: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        narrative: str,
        thermo: Dict[str, Any],
        fee_statement: Dict[str, Any],
        decisions: List[Dict[str, Any]],
    ) -> str:
        """Render monthly report as HTML string."""
        decision_rows = "\n".join(
            f"<tr><td>{d.get('type','').upper()}</td><td>{d.get('symbol','')}</td><td>{d.get('summary','')}</td></tr>"
            for d in decisions
        )

        fee_section = f"""
        <h2 style="color:#a78bfa;margin-top:32px">Fee Statement</h2>
        <table style="{_TABLE_STYLE}">
          <tr><td>Management Fee</td><td style="text-align:right">${fee_statement.get('mgmt_fee', 0):,.2f}</td></tr>
          <tr><td>Performance Fee</td><td style="text-align:right">${fee_statement.get('perf_fee', 0):,.2f}</td></tr>
          <tr style="font-weight:bold"><td>Total Fees</td><td style="text-align:right">${fee_statement.get('total_fee', 0):,.2f}</td></tr>
        </table>
        <h2 style="color:#a78bfa;margin-top:32px">Decision Log</h2>
        <table style="{_TABLE_STYLE}">
          <thead><tr><th>Action</th><th>Symbol</th><th>Rationale</th></tr></thead>
          <tbody>{decision_rows}</tbody>
        </table>
        """

        base = self.generate_weekly_html(snapshot, nav_history, positions, narrative, thermo)
        # Replace extra_section placeholder already embedded in template
        return base.replace("<!--EXTRA_SECTION-->", fee_section)

    def send_report(self, to_addrs: List[str], subject: str, html: str) -> None:
        """Send an HTML email via SMTP with STARTTLS."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(to_addrs)
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.ehlo()
            server.starttls()
            if self._username and self._password:
                server.login(self._username, self._password)
            server.sendmail(self.from_addr, to_addrs, msg.as_string())


# ── private helpers ───────────────────────────────────────────────────────────

def _pl_color(pct: float) -> str:
    return "#22c55e" if pct >= 0 else "#ef4444"


_TABLE_STYLE = (
    "width:100%;border-collapse:collapse;color:#e5e7eb;"
    "font-family:monospace;font-size:13px"
)

_BASE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#0a0a0a;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:0 auto;padding:32px 16px">
<tr><td>

  <!-- Header -->
  <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:24px">
    <h1 style="margin:0;font-size:20px;color:#f9fafb">{title}</h1>
    <p style="margin:4px 0 0;color:#71717a;font-size:13px">{date}</p>
  </div>

  <!-- NAV Summary -->
  <h2 style="color:#a78bfa;margin-bottom:12px;font-size:15px;text-transform:uppercase;letter-spacing:.05em">Fund Summary</h2>
  <table style="{table_style}">
    <tr><td>Total NAV</td><td style="text-align:right;font-weight:bold;color:#f9fafb">{nav}</td></tr>
    <tr><td>NAV per Unit</td><td style="text-align:right">{nav_per_unit}</td></tr>
    <tr><td>Units Outstanding</td><td style="text-align:right">{units}</td></tr>
    <tr><td>High Water Mark</td><td style="text-align:right">{hwm}</td></tr>
    <tr><td>Cash</td><td style="text-align:right">{cash}</td></tr>
    <tr><td>Active Positions</td><td style="text-align:right">{positions_count}</td></tr>
  </table>

  <!-- Thermo -->
  <h2 style="color:#a78bfa;margin-top:32px;margin-bottom:12px;font-size:15px;text-transform:uppercase;letter-spacing:.05em">Market Thermodynamics</h2>
  <table style="{table_style}">
    <tr><td>Clarity</td><td style="text-align:right">{clarity}%</td></tr>
    <tr><td>Opportunity</td><td style="text-align:right">{opportunity}%</td></tr>
    <tr><td>Market Health</td><td style="text-align:right;color:{health_color}">{market_health}</td></tr>
    <tr><td>Momentum</td><td style="text-align:right">{momentum}</td></tr>
  </table>

  <!-- Narrative -->
  <h2 style="color:#a78bfa;margin-top:32px;margin-bottom:12px;font-size:15px;text-transform:uppercase;letter-spacing:.05em">Belief Narrative</h2>
  <p style="line-height:1.6;color:#d1d5db;background:#111827;padding:16px;border-radius:8px;border-left:3px solid #7c3aed">{narrative}</p>

  <!-- Positions -->
  <h2 style="color:#a78bfa;margin-top:32px;margin-bottom:12px;font-size:15px;text-transform:uppercase;letter-spacing:.05em">Positions</h2>
  <table style="{table_style}">
    <thead>
      <tr style="color:#71717a;border-bottom:1px solid #27272a">
        <th style="text-align:left;padding:4px 8px">Symbol</th>
        <th style="text-align:right;padding:4px 8px">Value</th>
        <th style="text-align:right;padding:4px 8px">Alloc</th>
        <th style="text-align:right;padding:4px 8px">P&amp;L</th>
      </tr>
    </thead>
    <tbody>{positions_rows}</tbody>
  </table>

  <!-- NAV History -->
  <h2 style="color:#a78bfa;margin-top:32px;margin-bottom:12px;font-size:15px;text-transform:uppercase;letter-spacing:.05em">Recent NAV History</h2>
  <table style="{table_style}">
    <thead>
      <tr style="color:#71717a;border-bottom:1px solid #27272a">
        <th style="text-align:left;padding:4px 8px">Date</th>
        <th style="text-align:right;padding:4px 8px">NAV/Unit</th>
        <th style="text-align:right;padding:4px 8px">Return</th>
      </tr>
    </thead>
    <tbody>{nav_rows}</tbody>
  </table>

  <!--EXTRA_SECTION-->

  <!-- Footer -->
  <div style="margin-top:40px;padding-top:16px;border-top:1px solid #27272a;color:#52525b;font-size:11px">
    <p style="margin:0">This is a private communication for fund members only.</p>
  </div>

</td></tr>
</table>
</body>
</html>
"""

# Inject table style constant into the template at import time
_BASE_TEMPLATE = _BASE_TEMPLATE.replace("{table_style}", _TABLE_STYLE)
```

- [ ] Verify tests pass:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/test_email_reports.py -v
```

- [ ] Commit:

```bash
cd /Users/birger/code/portfolio
git add src/fund/email_reports.py tests/unit/fund/test_email_reports.py
git commit -m "$(cat <<'EOF'
feat: add EmailReporter with dark-theme HTML templates and SMTP delivery

Weekly and monthly HTML report generation using only stdlib email/smtplib.
Dark-theme inline CSS for email client compatibility. Full unit test
coverage with mocked SMTP.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 2: Export

### Task 2.1: Export EmailReporter

- [ ] Modify `src/fund/__init__.py` — add:

```python
from fund.email_reports import EmailReporter
# Add "EmailReporter" to __all__
```

- [ ] Verify full fund unit tests pass:

```bash
cd /Users/birger/code/portfolio
pytest tests/unit/fund/ -v --tb=short
```

- [ ] Commit:

```bash
cd /Users/birger/code/portfolio
git add src/fund/__init__.py
git commit -m "$(cat <<'EOF'
chore: export EmailReporter from fund package

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Done Criteria

- [ ] `EmailReporter` has `generate_weekly_html`, `generate_monthly_html`, `send_report`
- [ ] HTML output starts with `<!DOCTYPE html>` and contains dark background (`#0a0a0a`)
- [ ] `generate_monthly_html` includes fee statement and decision log sections
- [ ] `send_report` uses `smtplib.SMTP` with STARTTLS and optional login
- [ ] All unit tests pass: `pytest tests/unit/fund/test_email_reports.py -v`
- [ ] `EmailReporter` is exported from `fund.__init__`
