"""Glass Box Fund V2 — entity definitions with layered belief model.

Belief layers:
  Layer 1 — Observable: directly measured from market data streams
  Layer 2 — Graph-derived: computed from relationships and propagation
  Layer 3 — Crowd: inferred from sentiment and social signals
"""

from silicondb.orm import Entity
from silicondb.orm.descriptors import (
    Belief,
    Relationship,
    Alert,
    Accumulator,
)


# ---------------------------------------------------------------------------
# Instrument — the primary trading entity
# Layer 1: 4 observable beliefs (price, spread, volume)
# Layer 2: 3 graph-derived beliefs (relative strength, exhaustion, pressure)
# Layer 3: 3 crowd beliefs (retail sentiment, mention velocity, crowded)
# ---------------------------------------------------------------------------

class Instrument(Entity):
    # Layer 1 — observable from market data
    price_trend_fast = Belief(initial=0.5)          # short-term price momentum
    price_trend_slow = Belief(initial=0.5)          # long-term price momentum
    spread_tight = Belief(initial=0.7)              # bid-ask spread health
    volume_normal = Belief(initial=0.6)             # volume within normal range

    # Layer 2 — graph-derived (learned from observation hooks, not from Source)
    relative_strength = Belief(initial=0.5, learned=True)
    exhaustion = Belief(initial=0.2, learned=True)   # buying/selling exhaustion
    pressure = Belief(initial=0.5, learned=True)     # net macro/sector pressure

    # Layer 3 — crowd signals
    retail_sentiment = Belief(initial=0.5)
    mention_velocity = Belief(initial=0.2)
    crowded = Belief(initial=0.3)

    # Computed beliefs — auto-recompute when dependencies change
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

    # Alerts
    volatility_spike = Alert(
        trigger="volume_normal",
        threshold=0.2,
        above=False,
        severity="high",
        cooldown=300,
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
        observe = {
            "price": {"belief": "price_trend_fast", "true_strengthens": True},
            "trade_count": {"belief": "spread_tight", "true_strengthens": True},
        }




# ---------------------------------------------------------------------------
# Sector — industry grouping
# ---------------------------------------------------------------------------

class Sector(Entity):
    momentum = Belief(initial=0.5)
    breadth = Belief(initial=0.5)

    instruments = Relationship("Instrument", many=True, inverse="in_sector")


# ---------------------------------------------------------------------------
# Industry — sub-sector grouping
# ---------------------------------------------------------------------------

class Industry(Entity):
    in_sector = Relationship("Sector")
    instruments = Relationship("Instrument", many=True)


# ---------------------------------------------------------------------------
# Index — benchmark / market index (e.g. SPY, QQQ)
# ---------------------------------------------------------------------------

class Index(Entity):
    trend = Belief(initial=0.5)

    components = Relationship("Instrument", many=True)

    class Source:
        origin = "alpaca.bars"
        sync = "stream"
        identity = "symbol"
        observe = {
            "price": {"belief": "trend", "true_strengthens": True},
        }




# ---------------------------------------------------------------------------
# MacroFactor — macro regime drivers (e.g. interest rates, inflation)
# ---------------------------------------------------------------------------

class MacroFactor(Entity):
    elevated = Belief(initial=0.4)
    trending = Belief(initial=0.5)

    macro_shift = Alert(
        trigger="elevated",
        threshold=0.7,
        above=True,
        severity="high",
        cooldown=3600,
    )

    affects_sector = Relationship("Sector", many=True)
    affects_instrument = Relationship("Instrument", many=True)
    correlated_with = Relationship("MacroFactor", many=True)


# ---------------------------------------------------------------------------
# MarketRegime — current market environment classification
# ---------------------------------------------------------------------------

class MarketRegime(Entity):
    risk_on = Belief(initial=0.5)
    trend_following = Belief(initial=0.5)
    mean_reverting_regime = Belief(initial=0.5)


# ---------------------------------------------------------------------------
# Position — a live holding in the portfolio
# ---------------------------------------------------------------------------

class Position(Entity):
    profitable = Belief(initial=0.5)
    within_risk_limits = Belief(initial=0.8)
    relative_strength = Belief(initial=0.5, learned=True)  # mirrored from Instrument for alert trigger

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

    class Source:
        origin = "alpaca.positions"
        sync = "pull"
        interval = "1min"
        identity = "symbol"
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
