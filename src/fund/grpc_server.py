"""gRPC server implementing the FundService."""

import queue
import time
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
        self._event_queue = queue.Queue()
        self._nav_history = []  # List[WeeklyNAV], populated by engine

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
                symbol=str(inst.symbol),
                name=str(inst.name),
                asset_class=str(inst.asset_class),
                thesis=str(inst.thesis),
                proposed_by=str(inst.proposed_by),
                added_date=str(inst.added_date),
                votes_for=int(inst.votes_for),
            ))

        return fund_service_pb2.InvestmentUniverseMsg(
            instruments=instruments,
            max_size=self._universe.max_size,
        )

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
        while context.is_active():
            snapshot = self.GetThermoMetrics(request, context)
            yield snapshot
            time.sleep(5)  # Push every 5 seconds

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
