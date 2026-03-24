"""Entity registration and descriptor validation."""
from fund_v2.entities import (
    Instrument, Sector, Industry, Index, MacroFactor,
    Position, Portfolio, MarketConcept, MarketRegime,
    ALL_ENTITIES,
)


# ── Instrument beliefs ──────────────────────────────────────────────────

def test_instrument_has_layer1_beliefs():
    assert "price_trend_fast" in Instrument._beliefs
    assert "price_trend_slow" in Instrument._beliefs
    assert "spread_tight" in Instrument._beliefs
    assert "volume_normal" in Instrument._beliefs


def test_instrument_has_layer2_beliefs():
    assert "relative_strength" in Instrument._beliefs
    assert "exhaustion" in Instrument._beliefs
    assert "pressure" in Instrument._beliefs


def test_instrument_has_layer3_beliefs():
    assert "retail_sentiment" in Instrument._beliefs
    assert "mention_velocity" in Instrument._beliefs
    assert "crowded" in Instrument._beliefs


def test_instrument_has_computed_beliefs():
    assert "entry_ready" in Instrument._beliefs
    assert Instrument._beliefs["entry_ready"].computed is True
    assert "exit_ready" in Instrument._beliefs
    assert Instrument._beliefs["exit_ready"].computed is True


def test_instrument_belief_count():
    # 4 observable + 3 derived + 3 crowd + 2 computed = 12
    assert len(Instrument._beliefs) == 12


# ── Temporal partitions ─────────────────────────────────────────────────

def test_instrument_has_temporal_partitions():
    temporal = Instrument._temporal
    assert temporal is not None
    assert "market_session" in temporal.time_partitions
    assert "day_of_week" in temporal.time_partitions
    assert temporal.timestamp_field == "trade_timestamp"


def test_market_regime_has_temporal_partitions():
    temporal = MarketRegime._temporal
    assert temporal is not None
    assert "market_session" in temporal.time_partitions


# ── Predicted alerts ────────────────────────────────────────────────────

def test_instrument_has_predicted_alerts():
    assert "predicted_strength_decline" in Instrument._alerts
    alert = Instrument._alerts["predicted_strength_decline"]
    assert alert.mode == "predicted"
    assert alert.horizon_days == 7
    assert alert.trigger == "relative_strength"


def test_instrument_has_predicted_exhaustion_alert():
    assert "predicted_exhaustion" in Instrument._alerts
    alert = Instrument._alerts["predicted_exhaustion"]
    assert alert.mode == "predicted"
    assert alert.trigger == "exhaustion"


def test_instrument_has_predicted_crowding_alert():
    assert "predicted_crowding" in Instrument._alerts
    alert = Instrument._alerts["predicted_crowding"]
    assert alert.mode == "predicted"
    assert alert.trigger == "crowded"


def test_sector_has_predicted_rotation_alert():
    assert "predicted_rotation_out" in Sector._alerts
    alert = Sector._alerts["predicted_rotation_out"]
    assert alert.mode == "predicted"
    assert alert.trigger == "rotating_in"


def test_macro_has_predicted_shift_alert():
    assert "predicted_macro_shift" in MacroFactor._alerts
    alert = MacroFactor._alerts["predicted_macro_shift"]
    assert alert.mode == "predicted"


def test_regime_has_predicted_risk_off():
    assert "predicted_risk_off" in MarketRegime._alerts
    alert = MarketRegime._alerts["predicted_risk_off"]
    assert alert.mode == "predicted"
    assert alert.severity == "critical"


def test_position_has_predicted_weakness():
    assert "predicted_weakness" in Position._alerts
    alert = Position._alerts["predicted_weakness"]
    assert alert.mode == "predicted"
    assert alert.trigger == "relative_strength"


# ── Current alerts ──────────────────────────────────────────────────────

def test_instrument_has_current_alerts():
    assert "volatility_spike" in Instrument._alerts
    alert = Instrument._alerts["volatility_spike"]
    assert alert.mode != "predicted"  # current mode


def test_position_has_stop_loss_alert():
    assert "stop_loss" in Position._alerts
    alert = Position._alerts["stop_loss"]
    assert alert.trigger == "relative_strength"
    assert alert.threshold == 0.25
    assert alert.severity == "critical"


def test_macro_factor_has_current_alert():
    assert "macro_shift" in MacroFactor._alerts


# ── Accumulators ────────────────────────────────────────────────────────

def test_instrument_has_accumulators():
    assert "trade_pressure" in Instrument._accumulators


# ── Relationships ───────────────────────────────────────────────────────

def test_instrument_relationships():
    assert "in_sector" in Instrument._relationships
    assert Instrument._relationships["in_sector"].target == "Sector"
    assert "competes_with" in Instrument._relationships
    assert Instrument._relationships["competes_with"].many is True


def test_sector_inverse_relationship():
    rel = Sector._relationships["instruments"]
    assert rel.many is True
    assert rel.inverse == "in_sector"


def test_sector_has_macro_relationships():
    assert "pressured_by" in Sector._relationships
    assert "driven_by" in Sector._relationships


def test_macro_has_proxy_relationship():
    assert "proxy" in MacroFactor._relationships
    assert MacroFactor._relationships["proxy"].target == "Instrument"


# ── Source bindings ─────────────────────────────────────────────────────

def test_instrument_source_binding():
    assert Instrument._source_binding is not None
    assert Instrument._source_binding.identity == "symbol"
    observe = Instrument._source_binding.observe
    assert len(observe) >= 2
    beliefs_mapped = [om.belief for om in observe]
    assert "price_trend_fast" in beliefs_mapped
    assert "spread_tight" in beliefs_mapped


def test_position_source_binding():
    assert Position._source_binding is not None
    assert Position._source_binding.identity == "symbol"


# ── Fields ──────────────────────────────────────────────────────────────

def test_instrument_has_fields():
    assert "symbol" in Instrument._fields
    assert Instrument._fields["symbol"].required is True
    assert "sector_name" in Instrument._fields
    assert Instrument._fields["sector_name"].confidence == 0.9


# ── Registration ────────────────────────────────────────────────────────

def test_all_entities_register(app):
    app.register(*ALL_ENTITIES)


def test_all_entities_includes_all():
    assert MarketRegime in ALL_ENTITIES
    assert Instrument in ALL_ENTITIES
    assert Sector in ALL_ENTITIES
    assert Position in ALL_ENTITIES
    assert len(ALL_ENTITIES) == 10  # added Strategy


def test_market_regime_has_beliefs():
    assert "risk_on" in MarketRegime._beliefs
    assert "trend_following" in MarketRegime._beliefs
    assert "mean_reverting_regime" in MarketRegime._beliefs
    assert "stable" in MarketRegime._beliefs
    assert len(MarketRegime._beliefs) == 4
