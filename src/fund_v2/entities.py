"""Glass Box Fund V2 — entity definitions with layered belief model.

Belief layers:
  Layer 1 — Observable: directly measured from market data streams
  Layer 2 — Graph-derived: computed from relationships and propagation
  Layer 3 — Crowd: inferred from sentiment and social signals
  Computed — derived from other beliefs, auto-recomputes on change

Temporal partitions:
  market_session — pre_market / morning / afternoon / after_hours
  day_of_week — monday-sunday, aggregates to weekday/weekend
"""

from silicondb.orm import Entity, Field
from silicondb.orm.descriptors import (
    Belief,
    Relationship,
    Alert,
    Accumulator,
)


# ---------------------------------------------------------------------------
# Instrument — the primary trading entity
# ---------------------------------------------------------------------------

class Instrument(Entity):
    # Fields — stored as metadata + graph triples
    symbol = Field(str, required=True)
    name = Field(str)
    sector_name = Field(str, confidence=0.9)    # inferred from Yahoo Finance
    industry_name = Field(str, confidence=0.8)  # inferred from Yahoo Finance

    # Temporal: beliefs tracked per market session and day of week
    class Temporal:
        time_partitions = ["market_session", "day_of_week"]
        timestamp_field = "trade_timestamp"

    # Layer 1 — observable from market data
    price_trend_fast = Belief(initial=0.5)      # 15-min momentum
    price_trend_slow = Belief(initial=0.5)      # 5-day momentum
    spread_tight = Belief(initial=0.7)          # bid-ask spread health
    volume_normal = Belief(initial=0.6)         # volume within normal range

    # Layer 2 — graph-derived (learned from observation hooks)
    relative_strength = Belief(initial=0.5, learned=True)   # vs sector peers
    exhaustion = Belief(initial=0.2, learned=True)          # mean-reversion risk
    pressure = Belief(initial=0.5, learned=True)            # net macro/sector pressure

    # Layer 3 — crowd signals
    retail_sentiment = Belief(initial=0.5)
    mention_velocity = Belief(initial=0.2)
    crowded = Belief(initial=0.3)

    # Computed — auto-recompute when dependencies change
    entry_ready = Belief(
        computed=True,
        depends_on=["relative_strength", "exhaustion", "pressure", "crowded"],
        combine="weighted_mean",
        weights={"relative_strength": 0.4, "exhaustion": -0.3, "pressure": 0.2, "crowded": -0.1},
    )
    exit_ready = Belief(
        computed=True,
        depends_on=["exhaustion", "crowded", "pressure"],
        combine="weighted_mean",
        weights={"exhaustion": 0.5, "crowded": 0.3, "pressure": -0.2},
    )

    # Accumulators
    trade_pressure = Accumulator(preset="beliefChanges")

    # Alerts — current mode
    volatility_spike = Alert(
        trigger="volume_normal",
        threshold=0.2,
        above=False,
        severity="high",
        cooldown=300,
    )

    # Alerts — predicted mode (replaces @on_prediction hooks)
    predicted_strength_decline = Alert(
        trigger="relative_strength",
        threshold=0.3,
        mode="predicted",
        horizon_days=7,
        severity="high",
        cooldown=3600,
    )
    predicted_exhaustion = Alert(
        trigger="exhaustion",
        threshold=0.8,
        above=True,
        mode="predicted",
        horizon_days=5,
        severity="medium",
        cooldown=1800,
    )
    predicted_crowding = Alert(
        trigger="crowded",
        threshold=0.8,
        above=True,
        mode="predicted",
        horizon_days=7,
        severity="medium",
        cooldown=3600,
    )

    # Relationships
    in_sector = Relationship("Sector")
    in_industry = Relationship("Industry")
    tracks_index = Relationship("Index")
    driven_by = Relationship("MacroFactor", many=True)
    competes_with = Relationship("Instrument", many=True)

    class Source:
        origin = "alpaca.stream"
        sync = "stream"
        identity = "symbol"
        fields = {"symbol": "symbol"}
        observe = {
            "price": {"belief": "price_trend_fast", "true_strengthens": True},
            "trade_count": {"belief": "spread_tight", "true_strengthens": True},
        }


# ---------------------------------------------------------------------------
# Sector — GICS sector grouping
# ---------------------------------------------------------------------------

class Sector(Entity):
    sector_id = Field(str, required=True)
    name = Field(str)

    momentum = Belief(initial=0.5)          # sector-level momentum
    breadth = Belief(initial=0.5)           # how many components are rising
    rotating_in = Belief(initial=0.5)       # capital flow direction

    # Predicted sector rotation alert
    predicted_rotation_out = Alert(
        trigger="rotating_in",
        threshold=0.3,
        mode="predicted",
        horizon_days=7,
        severity="high",
        cooldown=7200,
    )

    instruments = Relationship("Instrument", many=True, inverse="in_sector")
    pressured_by = Relationship("MacroFactor", many=True)
    driven_by = Relationship("MacroFactor", many=True)


# ---------------------------------------------------------------------------
# Industry — sub-sector grouping
# ---------------------------------------------------------------------------

class Industry(Entity):
    industry_id = Field(str, required=True)
    name = Field(str)

    in_sector = Relationship("Sector")
    instruments = Relationship("Instrument", many=True)


# ---------------------------------------------------------------------------
# Index — benchmark / market index (e.g. SPY, QQQ)
# ---------------------------------------------------------------------------

class Index(Entity):
    symbol = Field(str, required=True)
    name = Field(str)

    trend = Belief(initial=0.5)

    components = Relationship("Instrument", many=True)

    class Source:
        origin = "alpaca.bars"
        sync = "stream"
        identity = "symbol"
        fields = {"symbol": "symbol"}
        observe = {
            "price": {"belief": "trend", "true_strengthens": True},
        }


# ---------------------------------------------------------------------------
# MacroFactor — macro regime drivers (interest rates, oil, fear, etc.)
# ---------------------------------------------------------------------------

class MacroFactor(Entity):
    factor_id = Field(str, required=True)
    name = Field(str)

    elevated = Belief(initial=0.4)
    trending = Belief(initial=0.5)

    # Current alert
    macro_shift = Alert(
        trigger="elevated",
        threshold=0.7,
        above=True,
        severity="high",
        cooldown=3600,
    )
    # Predicted alert — early warning
    predicted_macro_shift = Alert(
        trigger="elevated",
        threshold=0.7,
        above=True,
        mode="predicted",
        horizon_days=7,
        severity="critical",
        cooldown=7200,
    )

    affects_sector = Relationship("Sector", many=True)
    affects_instrument = Relationship("Instrument", many=True)
    correlated_with = Relationship("MacroFactor", many=True)
    proxy = Relationship("Instrument")  # e.g. TLT proxies interest_rates


# ---------------------------------------------------------------------------
# MarketRegime — current market environment classification
# ---------------------------------------------------------------------------

class MarketRegime(Entity):
    regime_id = Field(str, required=True)

    risk_on = Belief(initial=0.5)
    trend_following = Belief(initial=0.5)
    mean_reverting_regime = Belief(initial=0.5)

    # Temporal: regime beliefs vary by market session
    class Temporal:
        time_partitions = ["market_session"]
        timestamp_field = "observation_timestamp"

    # Predicted regime shift — the highest-value alert in the system
    predicted_risk_off = Alert(
        trigger="risk_on",
        threshold=0.3,
        mode="predicted",
        horizon_days=7,
        severity="critical",
        cooldown=14400,
    )


# ---------------------------------------------------------------------------
# Position — a live holding in the portfolio
# ---------------------------------------------------------------------------

class Position(Entity):
    symbol = Field(str, required=True)

    profitable = Belief(initial=0.5)
    within_risk_limits = Belief(initial=0.8)
    relative_strength = Belief(initial=0.5, learned=True)

    # Current alerts
    stop_loss = Alert(
        trigger="relative_strength",
        threshold=0.25,
        above=False,
        severity="critical",
        cooldown=60,
        auto_approve=True,
    )
    concentration_alert = Alert(
        trigger="within_risk_limits",
        threshold=0.3,
        above=False,
        severity="high",
        cooldown=600,
    )

    # Predicted alert — early exit warning
    predicted_weakness = Alert(
        trigger="relative_strength",
        threshold=0.3,
        mode="predicted",
        horizon_days=5,
        severity="high",
        cooldown=3600,
    )

    instrument = Relationship("Instrument")

    class Source:
        origin = "alpaca.positions"
        sync = "pull"
        interval = "1min"
        identity = "symbol"
        fields = {"symbol": "symbol"}
        observe = {
            "unrealized_plpc": {"belief": "profitable", "true_strengthens": True},
        }


# ---------------------------------------------------------------------------
# Portfolio — the fund's aggregate state
# ---------------------------------------------------------------------------

class Portfolio(Entity):
    drawdown_contained = Belief(initial=0.8)

    drawdown_alert = Alert(
        trigger="drawdown_contained",
        threshold=0.3,
        above=False,
        severity="critical",
        cooldown=300,
    )

    positions = Relationship("Position", many=True)

    class Source:
        origin = "alpaca.account"
        sync = "pull"
        interval = "1min"
        identity = "account_id"
        observe = {
            "equity": {"belief": "drawdown_contained", "true_strengthens": True},
        }


# ---------------------------------------------------------------------------
# MarketConcept — abstract market idea (e.g. "AI wave", "rate hike cycle")
# ---------------------------------------------------------------------------

class MarketConcept(Entity):
    concept_id = Field(str, required=True)
    name = Field(str)

    active = Belief(initial=0.5)

    related_instruments = Relationship("Instrument", many=True)
    related_sectors = Relationship("Sector", many=True)
    driven_by_macro = Relationship("MacroFactor", many=True)


# ---------------------------------------------------------------------------
# ALL_ENTITIES — tuple used by app.register()
# ---------------------------------------------------------------------------

ALL_ENTITIES = (
    Instrument,
    Sector,
    Industry,
    Index,
    MacroFactor,
    MarketRegime,
    Position,
    Portfolio,
    MarketConcept,
)
