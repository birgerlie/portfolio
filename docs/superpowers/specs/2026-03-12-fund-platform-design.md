# Fund Platform Design Spec

> An investment club modeled as a real NAV-based fund, with a thermodynamic trading engine on a Mac at home, a beautiful Apple-inspired web app in the cloud, and narrative AI-synthesized reports.

---

## 1. System Architecture

```
Mac (Home)                                    Cloud
┌─────────────────────────┐    async gRPC    ┌──────────────────────────┐
│ Trading Engine           │◄──────────────►│ Web App (Next.js)         │
│                          │  bidirectional  │                           │
│ ├── Regime Detector      │    streaming    │ ├── User Accounts         │
│ ├── Strategy Selector    │                │ ├── Dashboard (Apple-style)│
│ ├── Kelly Sizing         │                │ ├── Stripe Payments        │
│ ├── Epistemic Engine     │                │ ├── Notification Center    │
│ ├── Thermodynamic Engine │                │ └── gRPC Client            │
│ ├── Fund Engine (new)    │                │                           │
│ ├── Alpaca Integration   │                └──────────────────────────┘
│ ├── Benchmark Engine     │                           │
│ ├── Belief Synthesizer   │                           ▼
│ └── gRPC Server          │                ┌──────────────────────────┐
│                          │                │ Email Service              │
└─────────────────────────┘                │ ├── OpenAI narrative gen   │
                                           │ ├── Weekly reports         │
                                           │ └── Event notifications   │
                                           └──────────────────────────┘
```

**Key principle:** Mac initiates outbound gRPC connection to cloud. No inbound firewall holes. If Mac is offline, cloud serves cached last-known state with a "last updated" indicator.

### Connection Model
The Mac establishes an outbound gRPC connection to the cloud server and holds a bidirectional stream open. The cloud sends requests over this stream (request-response over streaming). If the Mac disconnects, the cloud falls back to cached data and shows a staleness badge ("Data from 2h ago"). Reconnection is automatic.

### Persistence
- **Mac:** SQLite for fund state, positions, transaction ledger, belief history
- **Cloud:** Postgres for user accounts, cached fund snapshots, Stripe records
- Cloud DB is populated by gRPC pushes from Mac (every snapshot is persisted)

### Deployment
- **Cloud:** Vercel (Next.js frontend) + Railway/Fly.io (API server + gRPC endpoint + Postgres)
- **Mac:** Python process running as launchd service
- **gRPC tunnel:** Mac connects outbound to cloud gRPC endpoint (standard TLS, no firewall config needed)

### Authentication
- **Members:** NextAuth.js with email magic links (simple, no passwords)
- **Admin (fund manager):** Same auth + admin role flag
- **gRPC:** Mutual TLS between Mac and cloud server (pre-shared certs)

---

## 2. Fund Model

### Structure
- NAV-based unit fund (investment club, modeled as real hedge fund)
- Weekly NAV calculation
- Monthly subscription/redemption window (1-month notice)
- 3-month initial lock-up after joining

### Fee Structure (2 and 20)
- **Management fee:** 2% annually, accrued weekly (NAV × 0.02 ÷ 52)
- **Performance fee:** 20% of gains above high-water mark, crystallized monthly
- **High-water mark:** Never resets. No performance fee until prior peak exceeded.
- Fees are deducted from NAV — members never see a bill, it's baked into unit price.

### Fee Calculation

```python
# Weekly
weekly_mgmt_fee = nav * 0.02 / 52

# Monthly crystallization
if nav_per_unit > high_water_mark:
    gain_per_unit = nav_per_unit - high_water_mark
    perf_fee = gain_per_unit * units_outstanding * 0.20
    high_water_mark = nav_per_unit
else:
    perf_fee = 0

# NAV always reported net of fees
nav_per_unit = (gross_nav - accrued_fees) / units_outstanding
```

### Cash Management
- Fund maintains a 5% cash reserve for redemptions
- If a redemption exceeds cash reserve, positions are sold to cover (pro-rata across holdings)
- Cash reserve is replenished from next subscription inflows
- Cash earns risk-free rate (included in NAV)

### Subscription Flow
1. Member requests subscription via web app
2. Stripe creates a payment intent (funds held, not captured)
3. Request queued until next monthly window
4. On window date: payment captured, units = amount ÷ nav_per_unit
5. Units issued, lock-up timer starts (3 months)
6. Confirmation email sent

### Redemption Flow
1. Member requests redemption (units or amount)
2. Check: past lock-up period? If not, reject.
3. Request queued until next monthly window (1-month notice required)
4. On window date: payout = units × nav_per_unit
5. If payout > cash reserve, sell positions to cover
6. Units cancelled, bank transfer initiated (Stripe Connect payouts)
7. Confirmation email sent

### NAV: Weekly vs Real-Time
- **Official NAV:** Calculated weekly (Friday close). Used for subscriptions, redemptions, and fee calculations.
- **Indicative NAV:** Real-time estimate shown on dashboard (based on live Alpaca positions). Marked as "estimated" until next official NAV.

### Fee Proceeds
- Fees are deducted from fund NAV (reducing nav_per_unit)
- Fee proceeds accumulate in the fund's cash position
- Fund manager can withdraw fee proceeds monthly via separate Stripe payout

---

## 3. Data Model

### Core Fund State
```python
Fund:
    nav: Decimal                  # Total net asset value
    units_outstanding: Decimal    # Total units issued
    nav_per_unit: Decimal         # nav / units_outstanding
    high_water_mark: Decimal      # Per-unit HWM for performance fee
    inception_date: date
```

### Member
```python
Member:
    id: str
    name: str
    email: str
    units: Decimal
    cost_basis: Decimal           # Total amount invested
    join_date: date
    lock_up_until: date           # join_date + 3 months
```

### Transaction Ledger (immutable)
```python
Transaction:
    member_id: str
    type: subscribe | redeem
    units: Decimal
    nav_per_unit: Decimal
    amount: Decimal
    fee_breakdown: FeeBreakdown
    timestamp: datetime
    status: pending | processed | rejected
```

### Weekly NAV Snapshot
```python
WeeklyNAV:
    date: date
    nav: Decimal
    nav_per_unit: Decimal
    gross_return_pct: float
    mgmt_fee_accrued: Decimal
    perf_fee_accrued: Decimal
    net_return_pct: float
    high_water_mark: Decimal

    # Thermodynamic metrics
    clarity_score: float          # 0-100
    opportunity_score: float      # 0-100
    capture_rate: float           # 0-100
    market_health: str            # green / yellow / red
    momentum: str                 # rising / steady / falling

    # Benchmarks
    benchmarks: dict[str, float]  # {SPY: +2.1%, QQQ: +3.4%, ...}

    # Alternative universes
    universe_equal_weight: float
    universe_no_thermo: float
    universe_perfect_hindsight: float
    universe_random_avg: float

    # Belief narrative (OpenAI-synthesized)
    narrative_summary: str
    position_narratives: dict[str, str]
```

---

## 4. Investment Universe

- **Max 20 instruments**
- **Monthly club vote** to add/remove
- Trading engine can only trade within this universe

```python
InvestmentUniverse:
    instruments: list[Instrument]   # max 20
    max_size: 20
    review_frequency: monthly

Instrument:
    symbol: str
    name: str
    asset_class: equity | etf
    thesis: str                     # why it belongs
    proposed_by: str                # member who proposed
    added_date: date
    votes_for: int                  # monthly retention votes
```

### Monthly Vote Process
1. Proposals open 1st–7th of each month (any member can propose with thesis)
2. Voting window: 8th–14th (each member gets one vote per proposal: yes/no)
3. Simple majority to add. Simple majority to remove.
4. If universe > 20 after additions, lowest-voted instruments get dropped
5. Fund manager has no veto — purely democratic
6. Changes take effect on next trading day after vote closes
7. Trading engine only trades within current universe

---

## 5. Benchmark & Alternative Universe Engine

### Standard Benchmarks
| Benchmark | Ticker | Why |
|-----------|--------|-----|
| S&P 500 | SPY | Standard US equity |
| Nasdaq 100 | QQQ | Tech-heavy comparison |
| Oslo Bors | OBX | Norwegian local benchmark |
| Risk-free rate | 3-month T-bill | Shows risk premium |
| 60/40 Portfolio | Blended | Classic balanced allocation |

### Alternative Universes (Storytelling Benchmarks)

| Universe | What it shows | How calculated |
|----------|---------------|----------------|
| **Actual fund** | What we did | Real positions + thermodynamics |
| **Equal weight** | No intelligence | Equal split across universe, rebalanced monthly |
| **No conviction** | System without thermodynamics | Same entry/exit signals, but equal-weight sizing (no Kelly, no entropy-based adjustments) |
| **Best possible** | Theoretical max | Best single-stock daily pick from the universe (not combinatorial — just "what if you picked the best stock each day") |
| **Random** | Monkey benchmark | 1000 random portfolio Monte Carlo, show median |

### Weekly Narrative
> "This week the fund returned +1.8%. Equal weight would have given +0.9%. Our conviction system added +0.9%. The best possible was +2.4% — we captured 75% of available opportunity."

### Personal "What If"
For each member:
> "If you had joined 3 months earlier, your return would be 12% instead of 8%."

---

## 6. Thermodynamic Metrics (Plain Language)

The thermodynamic engine runs under the hood. Members see five plain-language gauges:

| Metric | Range | Derived from | What members see |
|--------|-------|-------------|-------------------|
| **Clarity** | 0–100% | 1 − S(portfolio) normalized | "How sure the system is about its positions" |
| **Opportunity** | 0–100 | Φ(t) normalized to historical range | "How much upside the system sees right now" |
| **Capture Rate** | 0–100% | Actual return ÷ theoretical max | "How much of the opportunity we turned into money" |
| **Market Health** | Green / Yellow / Red | σ distance from σ_crit | "Can the system operate well in current conditions" |
| **Momentum** | Rising / Steady / Falling | dp/dt averaged across positions | "Is overall conviction strengthening or weakening" |

### Dashboard Interpretation (auto-generated)

```
Clarity 82% + Opportunity 71 + Market Health Green
→ "High conviction, good opportunity, calm market.
   System is running at full capacity."

Clarity 45% + Opportunity 35 + Market Health Yellow
→ "Mixed signals, limited opportunity, elevated volatility.
   System is sizing positions conservatively."

Clarity 20% + Opportunity 15 + Market Health Red
→ "Very uncertain, low opportunity, dangerous conditions.
   System has moved to minimum exposure."
```

### Per-Position Metrics
```
NVDA:
  Conviction: 88% (strong bullish)
  Clarity trend: ↑ rising for 6 weeks
  Summary: "Evidence continues to confirm. Full position maintained."

AAPL:
  Conviction: 52% (neutral)
  Clarity trend: → flat
  Summary: "Not enough signal. Small allocation maintained."
```

---

## 7. Belief Synthesis (OpenAI + Epistemic Engine)

The epistemic engine provides Bayesian truth. OpenAI translates it to narrative.

### Input to OpenAI (per position)
```
- Belief type + probability
- Confirmation/contradiction count
- Source names + credibility scores
- Anomaly detection flags
- Thermodynamic metrics (clarity, momentum)
- Position sizing and changes
- Belief evolution over time
- Forward prediction from trajectory integration
```

### Fallback
If OpenAI is unavailable, fall back to template-based narratives:
> "{symbol} conviction is {probability}% ({belief_type}). {confirmations} confirmations, {contradictions} contradictions. Position: {allocation}%."

### Output Tiers

**Dashboard (1 sentence per position):**
> "Nvidia conviction strengthened to 88% on continued datacenter strength."

**Weekly Email (full narrative per position):**
> "The system's conviction in Nvidia strengthened again this week (88%, up from 85%). Seven independent signals now support the high-growth thesis — strong datacenter revenue, expanding AI adoption, and consistent earnings beats. One contradicting signal (valuation stretched vs historical P/E) remains, but comes from a source with declining credibility (42% trust). The system has increased the position to full Kelly sizing."

**Monthly Report (fund-level synthesis):**
> Full narrative covering regime state, all positions, fee impact, benchmark comparison, and forward outlook.

**Decision Log (per trade):**
> "Increased NVDA from 25% to 30%. Reason: conviction crossed 85% threshold with 6 confirmations from high-credibility sources. Thermodynamic clarity at 78%, market health green."

---

## 8. Alpaca Integration

The trading engine connects to Alpaca for live execution.

### Capabilities
- Paper trading for testing
- Live trading for real positions
- Real-time position and P&L data
- Order execution (market, limit)
- Portfolio sync (Alpaca positions → fund NAV calculation)

### Flow
```
Trading Engine decision → Execution Generator → Alpaca API → Order filled
                                                             ↓
                                              Fund Engine updates NAV
                                                             ↓
                                              gRPC pushes to cloud
```

---

## 9. gRPC Interface

```protobuf
service FundService {
  // Fund state
  rpc GetCurrentState(Empty) returns (FundState);
  rpc GetWeeklyNAVHistory(TimeRange) returns (stream WeeklyNAV);

  // Member-specific
  rpc GetMemberPosition(MemberId) returns (MemberPosition);
  rpc GetMemberWhatIf(WhatIfRequest) returns (WhatIfResponse);

  // Positions & universe
  rpc GetPositions(Empty) returns (Positions);
  rpc GetUniverse(Empty) returns (InvestmentUniverse);

  // Benchmarks
  rpc GetBenchmarkComparison(TimeRange) returns (BenchmarkData);
  rpc GetAlternativeUniverses(TimeRange) returns (UniverseComparison);

  // Thermodynamic metrics
  rpc GetThermoMetrics(Empty) returns (ThermoSnapshot);
  rpc StreamThermoMetrics(Empty) returns (stream ThermoSnapshot);

  // Belief narratives
  rpc GetBeliefNarrative(TimeRange) returns (BeliefReport);

  // Decisions log
  rpc GetDecisionLog(TimeRange) returns (stream Decision);

  // Events & notifications
  rpc StreamEvents(Empty) returns (stream FundEvent);
}
```

---

## 10. Web App Design (Apple-Inspired)

### Design Language
- Dark mode first
- SF Pro / Inter typography
- Large hero numbers, dramatic whitespace
- Smooth scroll-triggered animations
- Minimal chrome — no borders, no busy grids
- Muted palette with one accent color
- Cards with subtle shadows
- Full-width cinematic sections

### Tech Stack
- Next.js (React, SSR)
- Tailwind CSS
- Framer Motion (animations)
- Recharts / D3 (charts)
- Stripe React components
- gRPC-web client

### Page Flow (Narrative Scroll)

**Hero — Full Viewport**
Just the number. Animates up from cost basis to current value on page load.
```
                    €127,450
              ↑ 27.4% since you joined

        [ smooth parallax NAV curve fades in behind ]
```

**The System Is Thinking — Activity Rings**
Three rings animate in (like Apple Watch). Clarity. Opportunity. Market Health. Fill up first, then labels fade in. You feel the state before you read it.

**The Story — One Sentence, Large Type**
OpenAI-generated narrative, centered:
> "This week the system saw clarity strengthen across 4 positions. It increased exposure to NVDA and trimmed META. The fund captured 76% of available opportunity."

**The Race — Animated Benchmark Comparison**
Five lines (fund, SPY, equal weight, random, theoretical max) race from left to right as you scroll. Your fund pulls ahead. Hover any point for the decision that caused divergence.

**The Constellation — Position Map**
Each stock is a dot. Sized by allocation. Positioned on conviction × clarity grid. Dots drift slowly. Tap one to expand into a card with the belief narrative and evidence trail.

**The Engine Room — Detail Section**
For members who want depth. Position list, fee breakdown, transaction history, decision log. Clean and minimal but complete.

**Your Journey — Personal Timeline**
When you joined, what the NAV was, each subscription, total fees paid, net return. Plus the "what if" calculation.

### Additional Pages
- **/invest** — Stripe payment flow for new subscriptions
- **/redeem** — Redemption request flow
- **/universe** — Current investment universe, propose/vote
- **/reports** — Archive of weekly/monthly reports
- **/settings** — Profile, notification preferences

---

## 11. Email Reports

### Weekly Report
- OpenAI-synthesized narrative covering:
  - Fund performance vs benchmarks
  - Regime state and changes
  - Position changes and why
  - Thermodynamic metrics in plain language
  - Forward outlook
- Beautiful HTML email template (Apple-inspired)
- Sent every Monday morning

### Monthly Report
- Everything in weekly, plus:
  - Fee statement (management + performance)
  - Personal return breakdown
  - Alternative universe comparison
  - Investment universe changes (votes)
  - Full decision log

### Event Notifications (Email + Push)

| Event | Priority | Channel |
|-------|----------|---------|
| Regime shift (bull→bear etc.) | High | Email + Push |
| Trade executed | Medium | Push |
| Weekly NAV published | Medium | Email + Push |
| Subscription/redemption processed | High | Email |
| Approaching danger zone (σ near critical) | High | Email + Push |
| Monthly fee statement | Low | Email |
| Position conviction changed significantly | Medium | Push |

**Push notifications:** Web push (browser notifications) initially. No mobile app needed — the web app is responsive and supports PWA push. Future: native mobile app if needed.

---

## 12. Legal & Member Agreement

This is an investment club, not a regulated fund. However, to model it properly:

- **Member agreement:** Simple contract covering: fee structure, lock-up terms, voting rights, redemption notice period, risk acknowledgment
- **Disclaimer:** "This is a private investment club. Past performance does not guarantee future results. Members may lose their entire investment."
- **Tax:** Each member is responsible for their own tax reporting. The system provides annual statements with cost basis and realized gains.
- **Audit trail:** All transactions, NAV calculations, and decisions are immutably logged

---

## 13. Sub-Projects & Build Order

| # | Sub-project | Description | Dependencies |
|---|-------------|-------------|-------------|
| 1 | **Fund Engine** | NAV, units, fees, HWM, benchmarks, thermo metrics | None |
| 2 | **Alpaca Integration** | Live trading, position sync | Fund Engine |
| 3 | **gRPC Service** | Async bidirectional streaming, proto definitions | Fund Engine |
| 4 | **Web App** | Next.js dashboard, Stripe, user accounts | gRPC Service |
| 5 | **Belief Synthesizer** | OpenAI narrative generation from epistemic state | Fund Engine |
| 6 | **Email Reports** | Weekly/monthly HTML emails | Belief Synthesizer |
| 7 | **Notifications** | Event-driven alerts (email, push) | gRPC Service |

Build in order. Each sub-project gets its own implementation plan.

---

## 14. Testing Strategy

- **Fund Engine:** Unit tests for NAV calculation, fee math, HWM edge cases, subscription/redemption flows. Property-based tests for fee invariants (fees never negative, HWM never decreases, units balance).
- **Alpaca:** Paper trading validation period (minimum 4 weeks) before live trading. Reconciliation tests: Alpaca positions vs fund engine state.
- **gRPC:** Integration tests with mock Mac server. Connection drop / reconnection tests.
- **Web App:** E2E tests (Playwright) for critical flows: login, view dashboard, subscribe, redeem.
- **Belief Synthesis:** Snapshot tests for OpenAI prompts. Fallback template tests.

---

**Document Version:** 1.1
**Date:** 2026-03-12
**Status:** Design Spec — Awaiting Review
