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
