import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TimeRange(_message.Message):
    __slots__ = ("start", "end")
    START_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    start: _timestamp_pb2.Timestamp
    end: _timestamp_pb2.Timestamp
    def __init__(self, start: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class MemberId(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class WhatIfRequest(_message.Message):
    __slots__ = ("member_id", "amount")
    MEMBER_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    member_id: str
    amount: float
    def __init__(self, member_id: _Optional[str] = ..., amount: _Optional[float] = ...) -> None: ...

class FundState(_message.Message):
    __slots__ = ("nav", "nav_per_unit", "units_outstanding", "high_water_mark", "cash", "inception_date", "engine_status")
    NAV_FIELD_NUMBER: _ClassVar[int]
    NAV_PER_UNIT_FIELD_NUMBER: _ClassVar[int]
    UNITS_OUTSTANDING_FIELD_NUMBER: _ClassVar[int]
    HIGH_WATER_MARK_FIELD_NUMBER: _ClassVar[int]
    CASH_FIELD_NUMBER: _ClassVar[int]
    INCEPTION_DATE_FIELD_NUMBER: _ClassVar[int]
    ENGINE_STATUS_FIELD_NUMBER: _ClassVar[int]
    nav: float
    nav_per_unit: float
    units_outstanding: float
    high_water_mark: float
    cash: float
    inception_date: str
    engine_status: EngineStatus
    def __init__(self, nav: _Optional[float] = ..., nav_per_unit: _Optional[float] = ..., units_outstanding: _Optional[float] = ..., high_water_mark: _Optional[float] = ..., cash: _Optional[float] = ..., inception_date: _Optional[str] = ..., engine_status: _Optional[_Union[EngineStatus, _Mapping]] = ...) -> None: ...

class EngineStatus(_message.Message):
    __slots__ = ("status", "alpaca_connected", "last_trade", "active_positions", "current_regime", "next_action", "next_action_at", "timestamp")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ALPACA_CONNECTED_FIELD_NUMBER: _ClassVar[int]
    LAST_TRADE_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_REGIME_FIELD_NUMBER: _ClassVar[int]
    NEXT_ACTION_FIELD_NUMBER: _ClassVar[int]
    NEXT_ACTION_AT_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    status: str
    alpaca_connected: bool
    last_trade: _timestamp_pb2.Timestamp
    active_positions: int
    current_regime: str
    next_action: str
    next_action_at: _timestamp_pb2.Timestamp
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, status: _Optional[str] = ..., alpaca_connected: bool = ..., last_trade: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., active_positions: _Optional[int] = ..., current_regime: _Optional[str] = ..., next_action: _Optional[str] = ..., next_action_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class WeeklyNAVRecord(_message.Message):
    __slots__ = ("date", "nav", "nav_per_unit", "gross_return_pct", "net_return_pct", "mgmt_fee_accrued", "perf_fee_accrued", "high_water_mark", "thermo", "benchmarks", "narrative_summary")
    class BenchmarksEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    DATE_FIELD_NUMBER: _ClassVar[int]
    NAV_FIELD_NUMBER: _ClassVar[int]
    NAV_PER_UNIT_FIELD_NUMBER: _ClassVar[int]
    GROSS_RETURN_PCT_FIELD_NUMBER: _ClassVar[int]
    NET_RETURN_PCT_FIELD_NUMBER: _ClassVar[int]
    MGMT_FEE_ACCRUED_FIELD_NUMBER: _ClassVar[int]
    PERF_FEE_ACCRUED_FIELD_NUMBER: _ClassVar[int]
    HIGH_WATER_MARK_FIELD_NUMBER: _ClassVar[int]
    THERMO_FIELD_NUMBER: _ClassVar[int]
    BENCHMARKS_FIELD_NUMBER: _ClassVar[int]
    NARRATIVE_SUMMARY_FIELD_NUMBER: _ClassVar[int]
    date: str
    nav: float
    nav_per_unit: float
    gross_return_pct: float
    net_return_pct: float
    mgmt_fee_accrued: float
    perf_fee_accrued: float
    high_water_mark: float
    thermo: ThermoSnapshot
    benchmarks: _containers.ScalarMap[str, float]
    narrative_summary: str
    def __init__(self, date: _Optional[str] = ..., nav: _Optional[float] = ..., nav_per_unit: _Optional[float] = ..., gross_return_pct: _Optional[float] = ..., net_return_pct: _Optional[float] = ..., mgmt_fee_accrued: _Optional[float] = ..., perf_fee_accrued: _Optional[float] = ..., high_water_mark: _Optional[float] = ..., thermo: _Optional[_Union[ThermoSnapshot, _Mapping]] = ..., benchmarks: _Optional[_Mapping[str, float]] = ..., narrative_summary: _Optional[str] = ...) -> None: ...

class MemberPosition(_message.Message):
    __slots__ = ("member_id", "name", "units", "cost_basis", "current_value", "return_pct", "lock_up_until")
    MEMBER_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    UNITS_FIELD_NUMBER: _ClassVar[int]
    COST_BASIS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_VALUE_FIELD_NUMBER: _ClassVar[int]
    RETURN_PCT_FIELD_NUMBER: _ClassVar[int]
    LOCK_UP_UNTIL_FIELD_NUMBER: _ClassVar[int]
    member_id: str
    name: str
    units: float
    cost_basis: float
    current_value: float
    return_pct: float
    lock_up_until: str
    def __init__(self, member_id: _Optional[str] = ..., name: _Optional[str] = ..., units: _Optional[float] = ..., cost_basis: _Optional[float] = ..., current_value: _Optional[float] = ..., return_pct: _Optional[float] = ..., lock_up_until: _Optional[str] = ...) -> None: ...

class WhatIfResponse(_message.Message):
    __slots__ = ("units_received", "nav_per_unit", "projected_value_at_10pct", "projected_value_at_neg10pct")
    UNITS_RECEIVED_FIELD_NUMBER: _ClassVar[int]
    NAV_PER_UNIT_FIELD_NUMBER: _ClassVar[int]
    PROJECTED_VALUE_AT_10PCT_FIELD_NUMBER: _ClassVar[int]
    PROJECTED_VALUE_AT_NEG10PCT_FIELD_NUMBER: _ClassVar[int]
    units_received: float
    nav_per_unit: float
    projected_value_at_10pct: float
    projected_value_at_neg10pct: float
    def __init__(self, units_received: _Optional[float] = ..., nav_per_unit: _Optional[float] = ..., projected_value_at_10pct: _Optional[float] = ..., projected_value_at_neg10pct: _Optional[float] = ...) -> None: ...

class PositionInfo(_message.Message):
    __slots__ = ("symbol", "quantity", "market_value", "avg_entry_price", "current_price", "unrealized_pl", "unrealized_pl_pct", "allocation_pct")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    MARKET_VALUE_FIELD_NUMBER: _ClassVar[int]
    AVG_ENTRY_PRICE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_PRICE_FIELD_NUMBER: _ClassVar[int]
    UNREALIZED_PL_FIELD_NUMBER: _ClassVar[int]
    UNREALIZED_PL_PCT_FIELD_NUMBER: _ClassVar[int]
    ALLOCATION_PCT_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    quantity: float
    market_value: float
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_pl_pct: float
    allocation_pct: float
    def __init__(self, symbol: _Optional[str] = ..., quantity: _Optional[float] = ..., market_value: _Optional[float] = ..., avg_entry_price: _Optional[float] = ..., current_price: _Optional[float] = ..., unrealized_pl: _Optional[float] = ..., unrealized_pl_pct: _Optional[float] = ..., allocation_pct: _Optional[float] = ...) -> None: ...

class Positions(_message.Message):
    __slots__ = ("positions", "total_value", "cash")
    POSITIONS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_VALUE_FIELD_NUMBER: _ClassVar[int]
    CASH_FIELD_NUMBER: _ClassVar[int]
    positions: _containers.RepeatedCompositeFieldContainer[PositionInfo]
    total_value: float
    cash: float
    def __init__(self, positions: _Optional[_Iterable[_Union[PositionInfo, _Mapping]]] = ..., total_value: _Optional[float] = ..., cash: _Optional[float] = ...) -> None: ...

class InstrumentInfo(_message.Message):
    __slots__ = ("symbol", "name", "asset_class", "thesis", "proposed_by", "added_date", "votes_for")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ASSET_CLASS_FIELD_NUMBER: _ClassVar[int]
    THESIS_FIELD_NUMBER: _ClassVar[int]
    PROPOSED_BY_FIELD_NUMBER: _ClassVar[int]
    ADDED_DATE_FIELD_NUMBER: _ClassVar[int]
    VOTES_FOR_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    name: str
    asset_class: str
    thesis: str
    proposed_by: str
    added_date: str
    votes_for: int
    def __init__(self, symbol: _Optional[str] = ..., name: _Optional[str] = ..., asset_class: _Optional[str] = ..., thesis: _Optional[str] = ..., proposed_by: _Optional[str] = ..., added_date: _Optional[str] = ..., votes_for: _Optional[int] = ...) -> None: ...

class InvestmentUniverseMsg(_message.Message):
    __slots__ = ("instruments", "max_size")
    INSTRUMENTS_FIELD_NUMBER: _ClassVar[int]
    MAX_SIZE_FIELD_NUMBER: _ClassVar[int]
    instruments: _containers.RepeatedCompositeFieldContainer[InstrumentInfo]
    max_size: int
    def __init__(self, instruments: _Optional[_Iterable[_Union[InstrumentInfo, _Mapping]]] = ..., max_size: _Optional[int] = ...) -> None: ...

class BenchmarkData(_message.Message):
    __slots__ = ("standard_benchmarks", "equal_weight_return", "no_conviction_return", "best_possible_return", "random_avg_return", "capture_rate", "alpha")
    class StandardBenchmarksEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    STANDARD_BENCHMARKS_FIELD_NUMBER: _ClassVar[int]
    EQUAL_WEIGHT_RETURN_FIELD_NUMBER: _ClassVar[int]
    NO_CONVICTION_RETURN_FIELD_NUMBER: _ClassVar[int]
    BEST_POSSIBLE_RETURN_FIELD_NUMBER: _ClassVar[int]
    RANDOM_AVG_RETURN_FIELD_NUMBER: _ClassVar[int]
    CAPTURE_RATE_FIELD_NUMBER: _ClassVar[int]
    ALPHA_FIELD_NUMBER: _ClassVar[int]
    standard_benchmarks: _containers.ScalarMap[str, float]
    equal_weight_return: float
    no_conviction_return: float
    best_possible_return: float
    random_avg_return: float
    capture_rate: float
    alpha: float
    def __init__(self, standard_benchmarks: _Optional[_Mapping[str, float]] = ..., equal_weight_return: _Optional[float] = ..., no_conviction_return: _Optional[float] = ..., best_possible_return: _Optional[float] = ..., random_avg_return: _Optional[float] = ..., capture_rate: _Optional[float] = ..., alpha: _Optional[float] = ...) -> None: ...

class UniverseComparison(_message.Message):
    __slots__ = ("benchmarks", "narrative")
    BENCHMARKS_FIELD_NUMBER: _ClassVar[int]
    NARRATIVE_FIELD_NUMBER: _ClassVar[int]
    benchmarks: BenchmarkData
    narrative: str
    def __init__(self, benchmarks: _Optional[_Union[BenchmarkData, _Mapping]] = ..., narrative: _Optional[str] = ...) -> None: ...

class ThermoSnapshot(_message.Message):
    __slots__ = ("clarity_score", "opportunity_score", "capture_rate", "market_health", "momentum", "interpretation")
    CLARITY_SCORE_FIELD_NUMBER: _ClassVar[int]
    OPPORTUNITY_SCORE_FIELD_NUMBER: _ClassVar[int]
    CAPTURE_RATE_FIELD_NUMBER: _ClassVar[int]
    MARKET_HEALTH_FIELD_NUMBER: _ClassVar[int]
    MOMENTUM_FIELD_NUMBER: _ClassVar[int]
    INTERPRETATION_FIELD_NUMBER: _ClassVar[int]
    clarity_score: float
    opportunity_score: float
    capture_rate: float
    market_health: str
    momentum: str
    interpretation: str
    def __init__(self, clarity_score: _Optional[float] = ..., opportunity_score: _Optional[float] = ..., capture_rate: _Optional[float] = ..., market_health: _Optional[str] = ..., momentum: _Optional[str] = ..., interpretation: _Optional[str] = ...) -> None: ...

class BeliefReport(_message.Message):
    __slots__ = ("beliefs", "synthesis")
    BELIEFS_FIELD_NUMBER: _ClassVar[int]
    SYNTHESIS_FIELD_NUMBER: _ClassVar[int]
    beliefs: _containers.RepeatedCompositeFieldContainer[BeliefEntry]
    synthesis: str
    def __init__(self, beliefs: _Optional[_Iterable[_Union[BeliefEntry, _Mapping]]] = ..., synthesis: _Optional[str] = ...) -> None: ...

class BeliefEntry(_message.Message):
    __slots__ = ("symbol", "probability", "direction", "confirmations", "contradictions", "credibility_weighted")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    PROBABILITY_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    CONFIRMATIONS_FIELD_NUMBER: _ClassVar[int]
    CONTRADICTIONS_FIELD_NUMBER: _ClassVar[int]
    CREDIBILITY_WEIGHTED_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    probability: float
    direction: str
    confirmations: int
    contradictions: int
    credibility_weighted: float
    def __init__(self, symbol: _Optional[str] = ..., probability: _Optional[float] = ..., direction: _Optional[str] = ..., confirmations: _Optional[int] = ..., contradictions: _Optional[int] = ..., credibility_weighted: _Optional[float] = ...) -> None: ...

class Decision(_message.Message):
    __slots__ = ("timestamp", "type", "summary", "data")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    timestamp: _timestamp_pb2.Timestamp
    type: str
    summary: str
    data: _struct_pb2.Struct
    def __init__(self, timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., type: _Optional[str] = ..., summary: _Optional[str] = ..., data: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class FundEvent(_message.Message):
    __slots__ = ("timestamp", "event_type", "title", "description", "severity", "metadata")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    timestamp: _timestamp_pb2.Timestamp
    event_type: str
    title: str
    description: str
    severity: str
    metadata: _struct_pb2.Struct
    def __init__(self, timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., event_type: _Optional[str] = ..., title: _Optional[str] = ..., description: _Optional[str] = ..., severity: _Optional[str] = ..., metadata: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class JournalDate(_message.Message):
    __slots__ = ("date",)
    DATE_FIELD_NUMBER: _ClassVar[int]
    date: str
    def __init__(self, date: _Optional[str] = ...) -> None: ...

class DailyJournalMsg(_message.Message):
    __slots__ = ("date", "entries", "regime_summary", "trades_executed", "nav_change_pct", "belief_snapshot", "thermo_snapshot")
    DATE_FIELD_NUMBER: _ClassVar[int]
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    REGIME_SUMMARY_FIELD_NUMBER: _ClassVar[int]
    TRADES_EXECUTED_FIELD_NUMBER: _ClassVar[int]
    NAV_CHANGE_PCT_FIELD_NUMBER: _ClassVar[int]
    BELIEF_SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    THERMO_SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    date: str
    entries: _containers.RepeatedCompositeFieldContainer[Decision]
    regime_summary: str
    trades_executed: int
    nav_change_pct: float
    belief_snapshot: _struct_pb2.Struct
    thermo_snapshot: _struct_pb2.Struct
    def __init__(self, date: _Optional[str] = ..., entries: _Optional[_Iterable[_Union[Decision, _Mapping]]] = ..., regime_summary: _Optional[str] = ..., trades_executed: _Optional[int] = ..., nav_change_pct: _Optional[float] = ..., belief_snapshot: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., thermo_snapshot: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...
