"""Glass Box Fund V2 — entities with goal-relative free energy.

Every belief has a goal. Free energy measures how far reality is from the goal.
The system prioritizes by free energy — biggest gap gets attention first.
Goals can be static, temporal, learned, or inherited from the hierarchy.

Hierarchy:
  Portfolio (goal: risk-managed growth)
    └── Strategy (goal: performing in current regime)
          └── Sector (goal: healthy rotation)
                └── Instrument (goal: neutral conviction, earned from data)
                      └── Position (goal: profitable, within risk limits)
"""

from silicondb.orm import Entity, Field
from silicondb.orm.descriptors import (
    Belief,
    Relationship,
    Alert,
    Accumulator,
)


# ── Instrument ───────────────────────────────────────────────────────────────

class Instrument(Entity):
    symbol = Field(str, required=True)
    name = Field(str)
    sector_name = Field(str, confidence=0.9)
    industry_name = Field(str, confidence=0.8)

    class Temporal:
        time_partitions = ["market_session", "day_of_week"]
        timestamp_field = "trade_timestamp"

    # Layer 1 — observable. Goal = neutral. Earn conviction from data.
    price_trend_fast = Belief(initial=0.5, goal=0.5)      # goal: no bias
    price_trend_slow = Belief(initial=0.5, goal=0.5)      # goal: no bias
    spread_tight = Belief(initial=0.7, goal=0.8)           # goal: liquid
    volume_normal = Belief(initial=0.6, goal=0.6)          # goal: normal volume

    # Layer 2 — graph-derived. Goals set expectations for what "normal" looks like.
    relative_strength = Belief(initial=0.5, learned=True, goal=0.5)  # goal: average
    exhaustion = Belief(initial=0.2, learned=True, goal=0.2)         # goal: fresh, not exhausted
    pressure = Belief(initial=0.5, learned=True, goal=0.5)           # goal: no macro pressure

    # Layer 3 — crowd. Goals keep us away from extremes.
    retail_sentiment = Belief(initial=0.5, goal=0.5)       # goal: balanced sentiment
    mention_velocity = Belief(initial=0.2, goal=0.3)       # goal: moderate attention
    crowded = Belief(initial=0.3, goal=0.2)                # goal: uncrowded

    # Computed — free energy on these IS the trading signal
    entry_ready = Belief(
        computed=True,
        depends_on=["relative_strength", "exhaustion", "pressure", "crowded"],
        combine="weighted_mean",
        weights={"relative_strength": 0.4, "exhaustion": -0.3, "pressure": 0.2, "crowded": -0.1},
        goal=0.7,  # goal: we WANT entry_ready to be high
    )
    exit_ready = Belief(
        computed=True,
        depends_on=["exhaustion", "crowded", "pressure"],
        combine="weighted_mean",
        weights={"exhaustion": 0.5, "crowded": 0.3, "pressure": -0.2},
        goal=0.2,  # goal: we want exit_ready to be LOW (not exiting)
    )

    # Accumulators
    trade_pressure = Accumulator(preset="beliefChanges")

    # Alerts — current
    volatility_spike = Alert(trigger="volume_normal", threshold=0.2, above=False, severity="high", cooldown=300)

    # Alerts — predicted
    predicted_strength_decline = Alert(trigger="relative_strength", threshold=0.3, mode="predicted", horizon_days=7, severity="high", cooldown=3600)
    predicted_exhaustion = Alert(trigger="exhaustion", threshold=0.8, above=True, mode="predicted", horizon_days=5, severity="medium", cooldown=1800)
    predicted_crowding = Alert(trigger="crowded", threshold=0.8, above=True, mode="predicted", horizon_days=7, severity="medium", cooldown=3600)

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


# ── Sector ───────────────────────────────────────────────────────────────────

class Sector(Entity):
    sector_id = Field(str, required=True)
    name = Field(str)

    momentum = Belief(initial=0.5, goal=0.5)            # goal: neutral
    breadth = Belief(initial=0.5, goal=0.6)              # goal: broad participation
    rotating_in = Belief(initial=0.5, goal=0.5)          # goal: neutral (no forced rotation)

    # Predicted rotation alert
    predicted_rotation_out = Alert(trigger="rotating_in", threshold=0.3, mode="predicted", horizon_days=7, severity="high", cooldown=7200)

    instruments = Relationship("Instrument", many=True, inverse="in_sector")
    pressured_by = Relationship("MacroFactor", many=True)
    driven_by = Relationship("MacroFactor", many=True)


# ── Industry ─────────────────────────────────────────────────────────────────

class Industry(Entity):
    industry_id = Field(str, required=True)
    name = Field(str)

    in_sector = Relationship("Sector")
    instruments = Relationship("Instrument", many=True)


# ── Index ────────────────────────────────────────────────────────────────────

class Index(Entity):
    symbol = Field(str, required=True)
    name = Field(str)

    trend = Belief(initial=0.5, goal=0.5)

    components = Relationship("Instrument", many=True)

    class Source:
        origin = "alpaca.bars"
        sync = "stream"
        identity = "symbol"
        fields = {"symbol": "symbol"}
        observe = {"price": {"belief": "trend", "true_strengthens": True}}


# ── MacroFactor ──────────────────────────────────────────────────────────────

class MacroFactor(Entity):
    factor_id = Field(str, required=True)
    name = Field(str)

    elevated = Belief(initial=0.4, goal=0.4)             # goal: not elevated
    trending = Belief(initial=0.5, goal=0.5)             # goal: stable

    macro_shift = Alert(trigger="elevated", threshold=0.7, above=True, severity="high", cooldown=3600)
    predicted_macro_shift = Alert(trigger="elevated", threshold=0.7, above=True, mode="predicted", horizon_days=7, severity="critical", cooldown=7200)

    affects_sector = Relationship("Sector", many=True)
    affects_instrument = Relationship("Instrument", many=True)
    correlated_with = Relationship("MacroFactor", many=True)
    proxy = Relationship("Instrument")


# ── Strategy ─────────────────────────────────────────────────────────────────

class Strategy(Entity):
    """A trading strategy — beliefs about its own performance, learned from outcomes."""
    strategy_name = Field(str, required=True)

    # Performance beliefs — observed from trade outcomes
    performing = Belief(initial=0.5, goal={
        "learned": True,
        "optimize_for": "pnl",
        "window": "90days",
        "min": 0.3,
        "max": 0.9,
    })

    # Does current regime suit this strategy?
    regime_fit = Belief(initial=0.5, goal={
        "temporal": {
            "weekday_morning": 0.7,   # momentum works in morning
            "weekday_afternoon": 0.5,  # less reliable
            "weekend": 0.4,            # crypto weekends are different
            "default": 0.6,
        }
    })

    # Is the edge still fresh? (not crowded/arbitraged)
    edge_fresh = Belief(initial=0.7, goal=0.7)

    # Predicted decay
    predicted_decay = Alert(trigger="performing", threshold=0.3, mode="predicted", horizon_days=7, severity="high", cooldown=7200)

    class Temporal:
        time_partitions = ["market_session", "day_of_week"]
        timestamp_field = "trade_timestamp"

    suited_for_regime = Relationship("MarketRegime")


# ── MarketRegime ─────────────────────────────────────────────────────────────

class MarketRegime(Entity):
    regime_id = Field(str, required=True)

    risk_on = Belief(initial=0.5, goal=0.5)              # goal: neutral (no bias)
    trend_following = Belief(initial=0.5, goal=0.5)
    mean_reverting_regime = Belief(initial=0.5, goal=0.5)
    stable = Belief(initial=0.8, goal=0.8)               # goal: we prefer stability

    class Temporal:
        time_partitions = ["market_session"]
        timestamp_field = "observation_timestamp"

    predicted_risk_off = Alert(trigger="risk_on", threshold=0.3, mode="predicted", horizon_days=7, severity="critical", cooldown=14400)


# ── Position ─────────────────────────────────────────────────────────────────

class Position(Entity):
    symbol = Field(str, required=True)

    profitable = Belief(initial=0.5, goal=0.7)           # goal: profitable
    within_risk_limits = Belief(initial=0.8, goal=0.9)   # goal: well within limits
    relative_strength = Belief(initial=0.5, learned=True, goal=0.6)  # goal: outperforming

    # Current alerts
    stop_loss = Alert(trigger="relative_strength", threshold=0.25, above=False, severity="critical", cooldown=60, auto_approve=True)
    concentration_alert = Alert(trigger="within_risk_limits", threshold=0.3, above=False, severity="high", cooldown=600)

    # Predicted alerts
    predicted_weakness = Alert(trigger="relative_strength", threshold=0.3, mode="predicted", horizon_days=5, severity="high", cooldown=3600)

    instrument = Relationship("Instrument")

    class Source:
        origin = "alpaca.positions"
        sync = "pull"
        interval = "1min"
        identity = "symbol"
        fields = {"symbol": "symbol"}
        observe = {"unrealized_plpc": {"belief": "profitable", "true_strengthens": True}}


# ── Portfolio ────────────────────────────────────────────────────────────────

class Portfolio(Entity):
    """The fund portfolio — system-level goals cascade down through the hierarchy."""

    drawdown_contained = Belief(initial=0.8, goal=0.9)   # goal: minimal drawdown
    diversified = Belief(initial=0.5, goal=0.7)           # goal: well diversified
    risk_budgeted = Belief(initial=0.8, goal=0.8)         # goal: within risk budget

    # Computed: overall health = weakest link
    overall_health = Belief(
        computed=True,
        depends_on=["drawdown_contained", "diversified", "risk_budgeted"],
        combine="min",
        goal=0.8,  # goal: all three healthy
    )

    drawdown_alert = Alert(trigger="drawdown_contained", threshold=0.3, above=False, severity="critical", cooldown=300)

    positions = Relationship("Position", many=True)
    active_strategy = Relationship("Strategy")

    class Source:
        origin = "alpaca.account"
        sync = "pull"
        interval = "1min"
        identity = "account_id"
        observe = {"equity": {"belief": "drawdown_contained", "true_strengthens": True}}


# ── MarketConcept ────────────────────────────────────────────────────────────

class MarketConcept(Entity):
    concept_id = Field(str, required=True)
    name = Field(str)

    active = Belief(initial=0.5, goal=0.5)

    related_instruments = Relationship("Instrument", many=True)
    related_sectors = Relationship("Sector", many=True)
    driven_by_macro = Relationship("MacroFactor", many=True)


# ── ALL_ENTITIES ─────────────────────────────────────────────────────────────

ALL_ENTITIES = (
    Instrument,
    Sector,
    Industry,
    Index,
    MacroFactor,
    Strategy,
    MarketRegime,
    Position,
    Portfolio,
    MarketConcept,
)
