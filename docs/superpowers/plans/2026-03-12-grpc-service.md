# gRPC Service Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the gRPC server (Mac side) and proto definitions that expose fund state, positions, metrics, journal, and event streams to the cloud.

**Architecture:** Proto definitions → generated Python stubs → `FundServiceServicer` that delegates to existing fund engine classes. The Mac runs the gRPC server; the cloud connects as a client. Bidirectional streaming for events/metrics. Also includes a Supabase push client that syncs snapshots to Postgres for the web dashboard.

**Tech Stack:** `grpcio`, `grpcio-tools` (protobuf compiler), `supabase-py` for cloud sync, existing fund engine.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `proto/fund_service.proto` | Protobuf service + message definitions |
| `src/fund/proto/` | Generated Python stubs (from protoc) |
| `src/fund/grpc_server.py` | `FundServiceServicer` — implements all RPCs |
| `src/fund/grpc_runner.py` | Server startup, shutdown, port config |
| `src/fund/supabase_sync.py` | Push snapshots + journals to Supabase |
| `tests/unit/fund/test_grpc_server.py` | Unit tests (mocked fund engine) |
| `tests/integration/fund/test_grpc_integration.py` | Integration tests (real server + client) |

---

## Chunk 1: Proto Definitions and Code Generation

### Task 1: Proto File

**Files:**
- Create: `proto/fund_service.proto`

- [ ] **Step 1: Write the proto file**

```protobuf
syntax = "proto3";

package fund;

import "google/protobuf/timestamp.proto";
import "google/protobuf/empty.proto";
import "google/protobuf/struct.proto";

// ── Request/Response Messages ──────────────────────────────

message TimeRange {
  google.protobuf.Timestamp start = 1;
  google.protobuf.Timestamp end = 2;
}

message MemberId {
  string id = 1;
}

message WhatIfRequest {
  string member_id = 1;
  double amount = 2;  // hypothetical subscription amount
}

// ── Fund State ─────────────────────────────────────────────

message FundState {
  double nav = 1;
  double nav_per_unit = 2;
  double units_outstanding = 3;
  double high_water_mark = 4;
  double cash = 5;
  string inception_date = 6;
  EngineStatus engine_status = 7;
}

message EngineStatus {
  string status = 1;  // running / degraded / stopped
  bool alpaca_connected = 2;
  google.protobuf.Timestamp last_trade = 3;
  int32 active_positions = 4;
  string current_regime = 5;
  string next_action = 6;
  google.protobuf.Timestamp next_action_at = 7;
  google.protobuf.Timestamp timestamp = 8;
}

// ── NAV History ────────────────────────────────────────────

message WeeklyNAVRecord {
  string date = 1;
  double nav = 2;
  double nav_per_unit = 3;
  double gross_return_pct = 4;
  double net_return_pct = 5;
  double mgmt_fee_accrued = 6;
  double perf_fee_accrued = 7;
  double high_water_mark = 8;
  ThermoSnapshot thermo = 9;
  map<string, double> benchmarks = 10;
  string narrative_summary = 11;
}

// ── Member ─────────────────────────────────────────────────

message MemberPosition {
  string member_id = 1;
  string name = 2;
  double units = 3;
  double cost_basis = 4;
  double current_value = 5;
  double return_pct = 6;
  string lock_up_until = 7;
}

message WhatIfResponse {
  double units_received = 1;
  double nav_per_unit = 2;
  double projected_value_at_10pct = 3;
  double projected_value_at_neg10pct = 4;
}

// ── Positions & Universe ───────────────────────────────────

message PositionInfo {
  string symbol = 1;
  double quantity = 2;
  double market_value = 3;
  double avg_entry_price = 4;
  double current_price = 5;
  double unrealized_pl = 6;
  double unrealized_pl_pct = 7;
  double allocation_pct = 8;
}

message Positions {
  repeated PositionInfo positions = 1;
  double total_value = 2;
  double cash = 3;
}

message InstrumentInfo {
  string symbol = 1;
  string name = 2;
  string asset_class = 3;
  string thesis = 4;
  string proposed_by = 5;
  string added_date = 6;
  int32 votes_for = 7;
}

message InvestmentUniverseMsg {
  repeated InstrumentInfo instruments = 1;
  int32 max_size = 2;
}

// ── Benchmarks ─────────────────────────────────────────────

message BenchmarkData {
  map<string, double> standard_benchmarks = 1;  // SPY, QQQ, OBX
  double equal_weight_return = 2;
  double no_conviction_return = 3;
  double best_possible_return = 4;
  double random_avg_return = 5;
  double capture_rate = 6;
  double alpha = 7;
}

message UniverseComparison {
  BenchmarkData benchmarks = 1;
  string narrative = 2;  // "We captured 76% of available opportunity"
}

// ── Thermodynamic Metrics ──────────────────────────────────

message ThermoSnapshot {
  double clarity_score = 1;       // entropy → 0-100%
  double opportunity_score = 2;   // portfolio potential Φ → 0-100%
  double capture_rate = 3;        // actual vs potential
  string market_health = 4;       // green/yellow/red
  string momentum = 5;            // rising/steady/falling
  string interpretation = 6;      // plain language
}

// ── Belief & Decisions ─────────────────────────────────────

message BeliefReport {
  repeated BeliefEntry beliefs = 1;
  string synthesis = 2;  // OpenAI-generated narrative
}

message BeliefEntry {
  string symbol = 1;
  double probability = 2;
  string direction = 3;  // bullish/bearish/neutral
  int32 confirmations = 4;
  int32 contradictions = 5;
  double credibility_weighted = 6;
}

message Decision {
  google.protobuf.Timestamp timestamp = 1;
  string type = 2;  // regime_change, trade_executed, belief_update, etc.
  string summary = 3;
  google.protobuf.Struct data = 4;
}

// ── Events ─────────────────────────────────────────────────

message FundEvent {
  google.protobuf.Timestamp timestamp = 1;
  string event_type = 2;
  string title = 3;
  string description = 4;
  string severity = 5;  // info, warning, critical
  google.protobuf.Struct metadata = 6;
}

// ── Journal ────────────────────────────────────────────────

message JournalDate {
  string date = 1;  // YYYY-MM-DD
}

message DailyJournalMsg {
  string date = 1;
  repeated Decision entries = 2;
  string regime_summary = 3;
  int32 trades_executed = 4;
  double nav_change_pct = 5;
  google.protobuf.Struct belief_snapshot = 6;
  google.protobuf.Struct thermo_snapshot = 7;
}

// ── Service ────────────────────────────────────────────────

service FundService {
  // Fund state
  rpc GetCurrentState(google.protobuf.Empty) returns (FundState);
  rpc GetWeeklyNAVHistory(TimeRange) returns (stream WeeklyNAVRecord);

  // Member
  rpc GetMemberPosition(MemberId) returns (MemberPosition);
  rpc GetMemberWhatIf(WhatIfRequest) returns (WhatIfResponse);

  // Positions & universe
  rpc GetPositions(google.protobuf.Empty) returns (Positions);
  rpc GetUniverse(google.protobuf.Empty) returns (InvestmentUniverseMsg);

  // Benchmarks
  rpc GetBenchmarkComparison(TimeRange) returns (BenchmarkData);
  rpc GetAlternativeUniverses(TimeRange) returns (UniverseComparison);

  // Thermodynamic metrics
  rpc GetThermoMetrics(google.protobuf.Empty) returns (ThermoSnapshot);
  rpc StreamThermoMetrics(google.protobuf.Empty) returns (stream ThermoSnapshot);

  // Belief narratives
  rpc GetBeliefNarrative(TimeRange) returns (BeliefReport);

  // Decisions / journal
  rpc GetDecisionLog(TimeRange) returns (stream Decision);
  rpc GetDailyJournal(JournalDate) returns (DailyJournalMsg);

  // Events & notifications
  rpc StreamEvents(google.protobuf.Empty) returns (stream FundEvent);

  // Heartbeat (cloud polls or Mac pushes)
  rpc GetEngineStatus(google.protobuf.Empty) returns (EngineStatus);
}
```

- [ ] **Step 2: Generate Python stubs**

```bash
pip3 install --break-system-packages grpcio grpcio-tools
mkdir -p src/fund/proto
python3 -m grpc_tools.protoc \
  -I proto \
  --python_out=src/fund/proto \
  --grpc_python_out=src/fund/proto \
  --pyi_out=src/fund/proto \
  proto/fund_service.proto
touch src/fund/proto/__init__.py
```

- [ ] **Step 3: Fix imports in generated code**

The generated `fund_service_pb2_grpc.py` will import `fund_service_pb2` without a package prefix. Add a fixup:

```bash
# Fix relative import in generated grpc file
sed -i '' 's/import fund_service_pb2/from fund.proto import fund_service_pb2/' src/fund/proto/fund_service_pb2_grpc.py
```

- [ ] **Step 4: Verify imports work**

Run: `PYTHONPATH=src python3 -c "from fund.proto import fund_service_pb2, fund_service_pb2_grpc; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add proto/ src/fund/proto/
git commit -m "feat(fund): gRPC proto definitions and generated stubs"
```

---

## Chunk 2: gRPC Server — Core RPCs

### Task 2: FundServiceServicer — State, Positions, Universe

**Files:**
- Create: `tests/unit/fund/test_grpc_server.py`
- Create: `src/fund/grpc_server.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for the gRPC server servicer."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import grpc
from google.protobuf.empty_pb2 import Empty

from fund.grpc_server import FundServiceServicer
from fund.proto import fund_service_pb2


class MockContext:
    """Minimal gRPC context for testing."""
    def set_code(self, code): self.code = code
    def set_details(self, details): self.details = details


def make_servicer(fund=None, members=None, broker=None, universe=None,
                  journal=None, thermo=None, benchmarks=None, health=None):
    """Create a servicer with mocked dependencies."""
    return FundServiceServicer(
        fund=fund or MagicMock(),
        members=members or {},
        broker=broker or MagicMock(),
        universe=universe or MagicMock(),
        journal=journal or MagicMock(),
        thermo=thermo or MagicMock(),
        benchmarks=benchmarks or MagicMock(),
        health=health or MagicMock(),
    )


class TestGetCurrentState:
    def test_returns_fund_state(self):
        fund = MagicMock()
        fund.nav = Decimal("100000")
        fund.nav_per_unit = Decimal("105")
        fund.units_outstanding = Decimal("952.38")
        fund.high_water_mark = Decimal("105")
        fund.inception_date = date(2026, 1, 1)

        broker = MagicMock()
        broker.get_account.return_value = MagicMock(cash=Decimal("15000"))

        health = MagicMock()
        health.create_heartbeat.return_value = MagicMock(
            status="running", alpaca_connected=True, last_trade=None,
            active_positions=3, current_regime="BULL",
            next_action="rebalance", next_action_at=None,
            timestamp=datetime.now(),
        )

        servicer = make_servicer(fund=fund, broker=broker, health=health)
        response = servicer.GetCurrentState(Empty(), MockContext())

        assert response.nav == 100000.0
        assert response.nav_per_unit == 105.0
        assert response.engine_status.status == "running"


class TestGetPositions:
    def test_returns_positions(self):
        broker = MagicMock()
        broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"),
                      market_value=Decimal("85000"), avg_entry_price=Decimal("800"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000"),
                      unrealized_pl_pct=0.0625),
        ]
        broker.get_account.return_value = MagicMock(cash=Decimal("15000"))

        servicer = make_servicer(broker=broker)
        response = servicer.GetPositions(Empty(), MockContext())

        assert len(response.positions) == 1
        assert response.positions[0].symbol == "NVDA"
        assert response.total_value == 100000.0
        assert response.cash == 15000.0


class TestGetUniverse:
    def test_returns_universe(self):
        universe = MagicMock()
        universe.max_size = 20
        universe._instruments = {
            "NVDA": MagicMock(symbol="NVDA", name="NVIDIA", asset_class="equity",
                              thesis="AI leader", proposed_by="alice",
                              added_date=date(2026, 1, 15), votes_for=5),
        }

        servicer = make_servicer(universe=universe)
        response = servicer.GetUniverse(Empty(), MockContext())

        assert response.max_size == 20
        assert len(response.instruments) == 1
        assert response.instruments[0].symbol == "NVDA"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_server.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement FundServiceServicer (core RPCs)**

```python
"""gRPC server implementing the FundService."""

from datetime import datetime
from decimal import Decimal

import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.struct_pb2 import Struct

from fund.proto import fund_service_pb2
from fund.proto import fund_service_pb2_grpc


def _to_timestamp(dt):
    """Convert datetime to protobuf Timestamp."""
    if dt is None:
        return Timestamp()
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def _to_struct(d):
    """Convert dict to protobuf Struct."""
    s = Struct()
    if d:
        s.update(d)
    return s


class FundServiceServicer(fund_service_pb2_grpc.FundServiceServicer):
    """Implements all FundService RPCs by delegating to fund engine components."""

    def __init__(self, fund, members, broker, universe, journal, thermo, benchmarks, health):
        self._fund = fund
        self._members = members  # dict of member_id -> Member
        self._broker = broker  # AlpacaBroker
        self._universe = universe  # InvestmentUniverse
        self._journal = journal  # EventJournal
        self._thermo = thermo  # ThermoMetrics
        self._benchmarks = benchmarks  # BenchmarkEngine
        self._health = health  # HealthMonitor

    def GetCurrentState(self, request, context):
        account = self._broker.get_account()
        heartbeat = self._health.create_heartbeat()

        engine_status = fund_service_pb2.EngineStatus(
            status=heartbeat.status,
            alpaca_connected=heartbeat.alpaca_connected,
            last_trade=_to_timestamp(heartbeat.last_trade),
            active_positions=heartbeat.active_positions,
            current_regime=heartbeat.current_regime,
            next_action=heartbeat.next_action,
            next_action_at=_to_timestamp(heartbeat.next_action_at),
            timestamp=_to_timestamp(heartbeat.timestamp),
        )

        return fund_service_pb2.FundState(
            nav=float(self._fund.nav),
            nav_per_unit=float(self._fund.nav_per_unit),
            units_outstanding=float(self._fund.units_outstanding),
            high_water_mark=float(self._fund.high_water_mark),
            cash=float(account.cash),
            inception_date=str(self._fund.inception_date),
            engine_status=engine_status,
        )

    def GetPositions(self, request, context):
        positions = self._broker.get_positions()
        account = self._broker.get_account()
        total_pos_value = sum(float(p.market_value) for p in positions)
        total_value = total_pos_value + float(account.cash)

        pos_msgs = []
        for p in positions:
            alloc = float(p.market_value) / total_value if total_value > 0 else 0
            pos_msgs.append(fund_service_pb2.PositionInfo(
                symbol=p.symbol,
                quantity=float(p.quantity),
                market_value=float(p.market_value),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                unrealized_pl=float(p.unrealized_pl),
                unrealized_pl_pct=p.unrealized_pl_pct,
                allocation_pct=alloc,
            ))

        return fund_service_pb2.Positions(
            positions=pos_msgs,
            total_value=total_value,
            cash=float(account.cash),
        )

    def GetUniverse(self, request, context):
        instruments = []
        for inst in self._universe._instruments.values():
            instruments.append(fund_service_pb2.InstrumentInfo(
                symbol=inst.symbol,
                name=inst.name,
                asset_class=inst.asset_class,
                thesis=inst.thesis,
                proposed_by=inst.proposed_by,
                added_date=str(inst.added_date),
                votes_for=inst.votes_for,
            ))

        return fund_service_pb2.InvestmentUniverseMsg(
            instruments=instruments,
            max_size=self._universe.max_size,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/grpc_server.py tests/unit/fund/test_grpc_server.py
git commit -m "feat(fund): gRPC servicer — fund state, positions, universe"
```

---

### Task 3: FundServiceServicer — Member, Thermo, Journal RPCs

**Files:**
- Modify: `tests/unit/fund/test_grpc_server.py`
- Modify: `src/fund/grpc_server.py`

- [ ] **Step 1: Write failing tests**

Add to `test_grpc_server.py`:

```python
class TestGetMemberPosition:
    def test_returns_member_data(self):
        fund = MagicMock()
        fund.nav_per_unit = Decimal("105")

        member = MagicMock()
        member.id = "m1"
        member.name = "Alice"
        member.units = Decimal("100")
        member.cost_basis = Decimal("10000")
        member.lock_up_until = date(2026, 6, 1)
        member.value_at_nav.return_value = Decimal("10500")
        member.return_pct.return_value = 0.05

        servicer = make_servicer(fund=fund, members={"m1": member})
        req = fund_service_pb2.MemberId(id="m1")
        response = servicer.GetMemberPosition(req, MockContext())

        assert response.name == "Alice"
        assert response.units == 100.0
        assert response.return_pct == 0.05

    def test_unknown_member_returns_error(self):
        servicer = make_servicer()
        ctx = MockContext()
        req = fund_service_pb2.MemberId(id="unknown")
        servicer.GetMemberPosition(req, ctx)
        assert ctx.code == grpc.StatusCode.NOT_FOUND


class TestGetThermoMetrics:
    def test_returns_thermo_snapshot(self):
        thermo = MagicMock()
        thermo.clarity_score.return_value = 0.78
        thermo.opportunity_score.return_value = 0.65
        thermo.market_health.return_value = "green"
        thermo.momentum.return_value = "rising"
        thermo.interpret.return_value = "Strong clarity, good opportunity"

        servicer = make_servicer(thermo=thermo)
        response = servicer.GetThermoMetrics(Empty(), MockContext())

        assert response.clarity_score == 0.78
        assert response.market_health == "green"


class TestGetDailyJournal:
    def test_returns_journal_for_date(self):
        journal = MagicMock()
        journal.load_date.return_value = MagicMock(
            date=date(2026, 3, 12),
            entries=[
                MagicMock(timestamp=datetime(2026, 3, 12, 10, 0), entry_type="trade_executed",
                          summary="Bought NVDA", data={"symbol": "NVDA"}),
            ],
            regime_summary="Bull all day",
            trades_executed=1,
            nav_change_pct=0.02,
            belief_snapshot={"NVDA": 0.85},
            thermo_snapshot={"clarity": 0.78},
        )

        servicer = make_servicer(journal=journal)
        req = fund_service_pb2.JournalDate(date="2026-03-12")
        response = servicer.GetDailyJournal(req, MockContext())

        assert response.date == "2026-03-12"
        assert response.trades_executed == 1
        assert response.regime_summary == "Bull all day"
        assert len(response.entries) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_server.py -v`
Expected: FAIL — methods not defined

- [ ] **Step 3: Implement member, thermo, and journal RPCs**

Add to `FundServiceServicer` in `grpc_server.py`:

```python
    def GetMemberPosition(self, request, context):
        member = self._members.get(request.id)
        if not member:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Member {request.id} not found")
            return fund_service_pb2.MemberPosition()

        nav_per_unit = self._fund.nav_per_unit
        return fund_service_pb2.MemberPosition(
            member_id=member.id,
            name=member.name,
            units=float(member.units),
            cost_basis=float(member.cost_basis),
            current_value=float(member.value_at_nav(nav_per_unit)),
            return_pct=member.return_pct(nav_per_unit),
            lock_up_until=str(member.lock_up_until),
        )

    def GetMemberWhatIf(self, request, context):
        nav_per_unit = float(self._fund.nav_per_unit)
        if nav_per_unit <= 0:
            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
            context.set_details("Fund not yet initialized")
            return fund_service_pb2.WhatIfResponse()

        units = request.amount / nav_per_unit
        return fund_service_pb2.WhatIfResponse(
            units_received=units,
            nav_per_unit=nav_per_unit,
            projected_value_at_10pct=request.amount * 1.10,
            projected_value_at_neg10pct=request.amount * 0.90,
        )

    def GetThermoMetrics(self, request, context):
        return fund_service_pb2.ThermoSnapshot(
            clarity_score=self._thermo.clarity_score(),
            opportunity_score=self._thermo.opportunity_score(),
            capture_rate=0.0,  # populated when benchmarks available
            market_health=self._thermo.market_health(),
            momentum=self._thermo.momentum(),
            interpretation=self._thermo.interpret(),
        )

    def GetEngineStatus(self, request, context):
        heartbeat = self._health.create_heartbeat()
        return fund_service_pb2.EngineStatus(
            status=heartbeat.status,
            alpaca_connected=heartbeat.alpaca_connected,
            last_trade=_to_timestamp(heartbeat.last_trade),
            active_positions=heartbeat.active_positions,
            current_regime=heartbeat.current_regime,
            next_action=heartbeat.next_action,
            next_action_at=_to_timestamp(heartbeat.next_action_at),
            timestamp=_to_timestamp(heartbeat.timestamp),
        )

    def GetDailyJournal(self, request, context):
        from datetime import date as date_type
        try:
            d = date_type.fromisoformat(request.date)
            daily = self._journal.load_date(d)
        except (FileNotFoundError, ValueError) as e:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(str(e))
            return fund_service_pb2.DailyJournalMsg()

        entries = []
        for e in daily.entries:
            ts = e.timestamp if isinstance(e.timestamp, datetime) else datetime.fromisoformat(str(e.timestamp))
            entry_type = e.entry_type if hasattr(e, 'entry_type') else e.get('entry_type', '')
            summary = e.summary if hasattr(e, 'summary') else e.get('summary', '')
            data = e.data if hasattr(e, 'data') else e.get('data', {})
            entries.append(fund_service_pb2.Decision(
                timestamp=_to_timestamp(ts),
                type=entry_type,
                summary=summary,
                data=_to_struct(data),
            ))

        return fund_service_pb2.DailyJournalMsg(
            date=request.date,
            entries=entries,
            regime_summary=daily.regime_summary,
            trades_executed=daily.trades_executed,
            nav_change_pct=daily.nav_change_pct,
            belief_snapshot=_to_struct(daily.belief_snapshot),
            thermo_snapshot=_to_struct(daily.thermo_snapshot),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/grpc_server.py tests/unit/fund/test_grpc_server.py
git commit -m "feat(fund): gRPC servicer — member, thermo, journal RPCs"
```

---

## Chunk 3: Server Runner and Streaming

### Task 4: gRPC Server Runner

**Files:**
- Create: `src/fund/grpc_runner.py`
- Create: `tests/unit/fund/test_grpc_runner.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for gRPC server runner."""

from unittest.mock import MagicMock, patch

from fund.grpc_runner import create_server


class TestCreateServer:
    @patch("fund.grpc_runner.grpc.server")
    def test_creates_server_on_port(self, mock_grpc_server):
        mock_server = MagicMock()
        mock_grpc_server.return_value = mock_server

        servicer = MagicMock()
        server = create_server(servicer, port=50051)

        assert server == mock_server
        mock_server.add_insecure_port.assert_called_once_with("[::]:50051")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement gRPC server runner**

```python
"""gRPC server startup and lifecycle."""

from concurrent import futures

import grpc

from fund.proto import fund_service_pb2_grpc


def create_server(servicer, port=50051, max_workers=10):
    """Create and configure a gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    fund_service_pb2_grpc.add_FundServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    return server


def run_server(servicer, port=50051):
    """Start the gRPC server and block until terminated."""
    server = create_server(servicer, port=port)
    server.start()
    print(f"Fund gRPC server started on port {port}")
    server.wait_for_termination()
    return server
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/grpc_runner.py tests/unit/fund/test_grpc_runner.py
git commit -m "feat(fund): gRPC server runner with configurable port"
```

---

### Task 5: Streaming RPCs — Events and Thermo

**Files:**
- Modify: `tests/unit/fund/test_grpc_server.py`
- Modify: `src/fund/grpc_server.py`

- [ ] **Step 1: Write failing tests**

Add to `test_grpc_server.py`:

```python
import threading
import time


class TestStreamEvents:
    def test_stream_yields_events(self):
        servicer = make_servicer()
        # Add events to the servicer's event queue
        servicer.push_event("trade_executed", "Bought NVDA", "info", {"symbol": "NVDA"})
        servicer.push_event("regime_change", "Bull to Bear", "warning", {})

        ctx = MockContext()
        ctx.is_active = lambda: True
        events = list(servicer._drain_events())

        assert len(events) == 2
        assert events[0].event_type == "trade_executed"
        assert events[1].event_type == "regime_change"


class TestPushEvent:
    def test_push_event_adds_to_queue(self):
        servicer = make_servicer()
        servicer.push_event("trade_executed", "Bought NVDA", "info", {"symbol": "NVDA"})
        assert servicer._event_queue.qsize() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_server.py::TestStreamEvents -v`
Expected: FAIL

- [ ] **Step 3: Implement streaming and event queue**

Add to `FundServiceServicer.__init__`:

```python
        import queue
        self._event_queue = queue.Queue()
```

Add methods:

```python
    def push_event(self, event_type, title, severity="info", metadata=None):
        """Push an event to the stream queue (called by engine components)."""
        event = fund_service_pb2.FundEvent(
            timestamp=_to_timestamp(datetime.now()),
            event_type=event_type,
            title=title,
            description=title,
            severity=severity,
            metadata=_to_struct(metadata or {}),
        )
        self._event_queue.put(event)

    def _drain_events(self):
        """Drain all queued events (for testing)."""
        events = []
        while not self._event_queue.empty():
            events.append(self._event_queue.get_nowait())
        return events

    def StreamEvents(self, request, context):
        """Server-streaming RPC that yields events as they occur."""
        while context.is_active():
            try:
                event = self._event_queue.get(timeout=1.0)
                yield event
            except Exception:
                continue

    def StreamThermoMetrics(self, request, context):
        """Server-streaming RPC that yields thermo snapshots periodically."""
        import time
        while context.is_active():
            snapshot = self.GetThermoMetrics(request, context)
            yield snapshot
            time.sleep(5)  # Push every 5 seconds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/grpc_server.py tests/unit/fund/test_grpc_server.py
git commit -m "feat(fund): gRPC streaming — events and thermo metrics"
```

---

### Task 5b: Remaining RPCs — NAV History, Benchmarks, Belief, Decision Log

These RPCs return data from the fund engine. Some data sources (belief synthesis via OpenAI) will be fully implemented in sub-project 5; for now we implement the RPC with what's available.

**Files:**
- Modify: `tests/unit/fund/test_grpc_server.py`
- Modify: `src/fund/grpc_server.py`

- [ ] **Step 1: Write failing tests**

Add to `test_grpc_server.py`:

```python
class TestGetWeeklyNAVHistory:
    def test_returns_nav_records(self):
        servicer = make_servicer()
        servicer._nav_history = [
            MagicMock(date=date(2026, 3, 5), nav=Decimal("98000"), nav_per_unit=Decimal("103"),
                      gross_return_pct=0.01, net_return_pct=0.008, mgmt_fee_accrued=Decimal("38"),
                      perf_fee_accrued=Decimal("0"), high_water_mark=Decimal("103"),
                      clarity_score=0.75, opportunity_score=0.6, capture_rate=0.5,
                      market_health="green", momentum="rising",
                      benchmarks={"SPY": 0.005}, narrative_summary="Good week"),
        ]

        req = fund_service_pb2.TimeRange()
        records = list(servicer.GetWeeklyNAVHistory(req, MockContext()))
        assert len(records) == 1
        assert records[0].nav == 98000.0
        assert records[0].nav_per_unit == 103.0


class TestGetBenchmarkComparison:
    def test_returns_benchmark_data(self):
        benchmarks = MagicMock()
        benchmarks.compare.return_value = {"SPY": 0.05, "QQQ": 0.08}
        benchmarks.equal_weight_return.return_value = 0.06
        benchmarks.best_daily_pick_return.return_value = 0.12
        benchmarks.random_portfolio_median.return_value = 0.04
        benchmarks.capture_rate.return_value = 0.76

        servicer = make_servicer(benchmarks=benchmarks)
        req = fund_service_pb2.TimeRange()
        response = servicer.GetBenchmarkComparison(req, MockContext())

        assert response.capture_rate == 0.76
        assert response.equal_weight_return == 0.06


class TestGetDecisionLog:
    def test_returns_decisions_from_journal(self):
        journal = MagicMock()
        journal.today = MagicMock(
            entries=[
                MagicMock(timestamp=datetime(2026, 3, 12, 10, 0), entry_type="trade_executed",
                          summary="Bought NVDA", data={"symbol": "NVDA"}),
                MagicMock(timestamp=datetime(2026, 3, 12, 11, 0), entry_type="regime_change",
                          summary="Bull to Bear", data={}),
            ]
        )

        servicer = make_servicer(journal=journal)
        req = fund_service_pb2.TimeRange()
        decisions = list(servicer.GetDecisionLog(req, MockContext()))

        assert len(decisions) == 2
        assert decisions[0].type == "trade_executed"
        assert decisions[1].type == "regime_change"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_server.py -v`
Expected: FAIL — methods not defined

- [ ] **Step 3: Implement remaining RPCs**

Add to `FundServiceServicer.__init__`:

```python
        self._nav_history = []  # List[WeeklyNAV], populated by engine
```

Add methods to `FundServiceServicer`:

```python
    def GetWeeklyNAVHistory(self, request, context):
        """Server-streaming: yield historical WeeklyNAV records."""
        for nav in self._nav_history:
            thermo = fund_service_pb2.ThermoSnapshot(
                clarity_score=nav.clarity_score,
                opportunity_score=nav.opportunity_score,
                capture_rate=nav.capture_rate,
                market_health=nav.market_health,
                momentum=nav.momentum,
            )
            yield fund_service_pb2.WeeklyNAVRecord(
                date=str(nav.date),
                nav=float(nav.nav),
                nav_per_unit=float(nav.nav_per_unit),
                gross_return_pct=nav.gross_return_pct,
                net_return_pct=nav.net_return_pct,
                mgmt_fee_accrued=float(nav.mgmt_fee_accrued),
                perf_fee_accrued=float(nav.perf_fee_accrued),
                high_water_mark=float(nav.high_water_mark),
                thermo=thermo,
                benchmarks=nav.benchmarks,
                narrative_summary=nav.narrative_summary,
            )

    def GetBenchmarkComparison(self, request, context):
        standard = self._benchmarks.compare()
        return fund_service_pb2.BenchmarkData(
            standard_benchmarks=standard,
            equal_weight_return=self._benchmarks.equal_weight_return(),
            no_conviction_return=0.0,  # placeholder
            best_possible_return=self._benchmarks.best_daily_pick_return(),
            random_avg_return=self._benchmarks.random_portfolio_median(),
            capture_rate=self._benchmarks.capture_rate(),
            alpha=0.0,  # computed from standard benchmarks
        )

    def GetAlternativeUniverses(self, request, context):
        benchmarks = self.GetBenchmarkComparison(request, context)
        cr = benchmarks.capture_rate
        narrative = f"We captured {cr:.0%} of available opportunity."
        return fund_service_pb2.UniverseComparison(
            benchmarks=benchmarks,
            narrative=narrative,
        )

    def GetBeliefNarrative(self, request, context):
        """Returns belief state. Full OpenAI synthesis added in sub-project 5."""
        return fund_service_pb2.BeliefReport(
            beliefs=[],
            synthesis="Belief synthesis will be available after OpenAI integration.",
        )

    def GetDecisionLog(self, request, context):
        """Server-streaming: yield today's journal entries as decisions."""
        for e in self._journal.today.entries:
            ts = e.timestamp if isinstance(e.timestamp, datetime) else datetime.now()
            yield fund_service_pb2.Decision(
                timestamp=_to_timestamp(ts),
                type=e.entry_type,
                summary=e.summary,
                data=_to_struct(e.data),
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_grpc_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/grpc_server.py tests/unit/fund/test_grpc_server.py
git commit -m "feat(fund): gRPC remaining RPCs — NAV history, benchmarks, decisions"
```

---

## Chunk 4: Supabase Sync and Integration Tests

### Task 6: Supabase Sync Client

**Files:**
- Create: `tests/unit/fund/test_supabase_sync.py`
- Create: `src/fund/supabase_sync.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Supabase sync client."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

from fund.supabase_sync import SupabaseSync, SupabaseConfig


class TestSupabaseConfig:
    def test_create_config(self):
        config = SupabaseConfig(url="https://abc.supabase.co", key="test-key")
        assert config.url == "https://abc.supabase.co"


class TestSupabaseSyncSnapshot:
    def test_push_fund_snapshot(self):
        mock_client = MagicMock()
        sync = SupabaseSync.__new__(SupabaseSync)
        sync._client = mock_client

        snapshot = {
            "date": "2026-03-12",
            "nav": 100000,
            "nav_per_unit": 105,
            "positions_count": 3,
        }

        sync.push_snapshot(snapshot)

        mock_client.table.assert_called_once_with("fund_snapshots")
        mock_client.table().upsert.assert_called_once()

    def test_push_journal(self):
        mock_client = MagicMock()
        sync = SupabaseSync.__new__(SupabaseSync)
        sync._client = mock_client

        journal_data = {
            "date": "2026-03-12",
            "entries": [{"type": "trade_executed", "summary": "Bought NVDA"}],
            "trades_executed": 1,
        }

        sync.push_journal(journal_data)

        mock_client.table.assert_called_once_with("journals")
        mock_client.table().upsert.assert_called_once()

    def test_push_heartbeat(self):
        mock_client = MagicMock()
        sync = SupabaseSync.__new__(SupabaseSync)
        sync._client = mock_client

        heartbeat = {
            "status": "running",
            "alpaca_connected": True,
            "active_positions": 3,
        }

        sync.push_heartbeat(heartbeat)

        mock_client.table.assert_called_once_with("engine_heartbeat")
        mock_client.table().upsert.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_supabase_sync.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SupabaseSync**

```python
"""Push fund data to Supabase for the web dashboard."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


@dataclass
class SupabaseConfig:
    """Supabase connection config."""
    url: str
    key: str  # service role key for server-side writes


class SupabaseSync:
    """Syncs fund state to Supabase Postgres."""

    def __init__(self, config: SupabaseConfig):
        from supabase import create_client
        self._client = create_client(config.url, config.key)

    def push_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Push a fund state snapshot. Upserts on date."""
        snapshot["updated_at"] = datetime.now().isoformat()
        self._client.table("fund_snapshots").upsert(snapshot, on_conflict="date").execute()

    def push_journal(self, journal_data: Dict[str, Any]) -> None:
        """Push a daily journal. Upserts on date."""
        journal_data["updated_at"] = datetime.now().isoformat()
        self._client.table("journals").upsert(journal_data, on_conflict="date").execute()

    def push_heartbeat(self, heartbeat: Dict[str, Any]) -> None:
        """Push engine heartbeat. Upserts on singleton row."""
        heartbeat["updated_at"] = datetime.now().isoformat()
        self._client.table("engine_heartbeat").upsert(heartbeat, on_conflict="id").execute()

    def push_positions(self, positions: list) -> None:
        """Push current positions snapshot."""
        self._client.table("positions").upsert(
            [{"updated_at": datetime.now().isoformat(), **p} for p in positions],
            on_conflict="symbol",
        ).execute()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/test_supabase_sync.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fund/supabase_sync.py tests/unit/fund/test_supabase_sync.py
git commit -m "feat(fund): supabase sync — push snapshots, journals, heartbeat"
```

---

### Task 7: gRPC Integration Test

**Files:**
- Create: `tests/integration/fund/test_grpc_integration.py`

- [ ] **Step 1: Write integration test with real gRPC server**

```python
"""Integration test: start real gRPC server, connect client, test RPCs."""

import threading
import time
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import grpc
from google.protobuf.empty_pb2 import Empty

from fund.grpc_server import FundServiceServicer
from fund.grpc_runner import create_server
from fund.proto import fund_service_pb2
from fund.proto import fund_service_pb2_grpc


def _start_test_server(servicer, port):
    server = create_server(servicer, port=port)
    server.start()
    return server


class TestGRPCIntegration:
    def setup_method(self):
        self.fund = MagicMock()
        self.fund.nav = Decimal("100000")
        self.fund.nav_per_unit = Decimal("105")
        self.fund.units_outstanding = Decimal("952.38")
        self.fund.high_water_mark = Decimal("105")
        self.fund.inception_date = date(2026, 1, 1)

        self.broker = MagicMock()
        self.broker.get_account.return_value = MagicMock(
            cash=Decimal("15000"), equity=Decimal("100000"),
            buying_power=Decimal("15000"), status="ACTIVE",
        )
        self.broker.get_positions.return_value = [
            MagicMock(symbol="NVDA", quantity=Decimal("100"),
                      market_value=Decimal("85000"), avg_entry_price=Decimal("800"),
                      current_price=Decimal("850"), unrealized_pl=Decimal("5000"),
                      unrealized_pl_pct=0.0625),
        ]

        self.health = MagicMock()
        self.health.create_heartbeat.return_value = MagicMock(
            status="running", alpaca_connected=True, last_trade=None,
            active_positions=1, current_regime="BULL",
            next_action="monitor", next_action_at=None,
            timestamp=datetime.now(),
        )

        self.thermo = MagicMock()
        self.thermo.clarity_score.return_value = 0.78
        self.thermo.opportunity_score.return_value = 0.65
        self.thermo.market_health.return_value = "green"
        self.thermo.momentum.return_value = "rising"
        self.thermo.interpret.return_value = "Strong clarity"

        self.servicer = FundServiceServicer(
            fund=self.fund, members={}, broker=self.broker,
            universe=MagicMock(_instruments={}, max_size=20),
            journal=MagicMock(), thermo=self.thermo,
            benchmarks=MagicMock(), health=self.health,
        )

        self.port = 50099  # test port
        self.server = _start_test_server(self.servicer, self.port)
        time.sleep(0.1)  # wait for server start

        self.channel = grpc.insecure_channel(f"localhost:{self.port}")
        self.stub = fund_service_pb2_grpc.FundServiceStub(self.channel)

    def teardown_method(self):
        self.channel.close()
        self.server.stop(grace=0)

    def test_get_current_state(self):
        response = self.stub.GetCurrentState(Empty())
        assert response.nav == 100000.0
        assert response.nav_per_unit == 105.0
        assert response.engine_status.status == "running"
        assert response.engine_status.alpaca_connected is True

    def test_get_positions(self):
        response = self.stub.GetPositions(Empty())
        assert len(response.positions) == 1
        assert response.positions[0].symbol == "NVDA"
        assert response.total_value == 100000.0

    def test_get_thermo_metrics(self):
        response = self.stub.GetThermoMetrics(Empty())
        assert response.clarity_score == 0.78
        assert response.market_health == "green"

    def test_get_engine_status(self):
        response = self.stub.GetEngineStatus(Empty())
        assert response.status == "running"
        assert response.current_regime == "BULL"

    def test_stream_events(self):
        self.servicer.push_event("trade_executed", "Bought NVDA", "info")

        events = []
        # Use a short deadline to avoid hanging
        try:
            for event in self.stub.StreamEvents(Empty(), timeout=2):
                events.append(event)
                if len(events) >= 1:
                    break
        except grpc.RpcError:
            pass

        assert len(events) == 1
        assert events[0].event_type == "trade_executed"
```

- [ ] **Step 2: Run integration tests**

Run: `PYTHONPATH=src python3 -m pytest tests/integration/fund/test_grpc_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/fund/test_grpc_integration.py
git commit -m "test(fund): gRPC integration tests — real server + client"
```

---

### Task 8: Update Exports

**Files:**
- Modify: `src/fund/__init__.py`

- [ ] **Step 1: Add new exports**

Add to `src/fund/__init__.py`:

```python
from fund.grpc_server import FundServiceServicer
from fund.grpc_runner import create_server, run_server
from fund.supabase_sync import SupabaseSync, SupabaseConfig
```

Add all new names to `__all__`.

- [ ] **Step 2: Run all tests**

Run: `PYTHONPATH=src python3 -m pytest tests/unit/fund/ tests/integration/fund/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/fund/__init__.py
git commit -m "feat(fund): export gRPC server, runner, supabase sync"
```
