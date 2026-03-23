"""Entity registration and descriptor validation."""
from fund_v2.entities import (
    Instrument, Sector, Industry, Index, MacroFactor,
    Position, Portfolio, MarketConcept, MarketRegime,
)


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


def test_instrument_has_10_beliefs():
    assert len(Instrument._beliefs) == 10


def test_instrument_has_accumulators():
    assert "trade_pressure" in Instrument._accumulators


def test_instrument_has_alerts():
    assert "volatility_spike" in Instrument._alerts


def test_instrument_relationships():
    assert "in_sector" in Instrument._relationships
    assert Instrument._relationships["in_sector"].target == "Sector"
    assert "competes_with" in Instrument._relationships
    assert Instrument._relationships["competes_with"].many is True


def test_instrument_source_binding():
    assert Instrument._source_binding is not None
    assert Instrument._source_binding.identity == "symbol"
    observe = Instrument._source_binding.observe
    assert "price" in observe
    assert observe["price"]["belief"] == "price_trend_fast"
    assert "trade_count" in observe
    assert observe["trade_count"]["belief"] == "spread_tight"


def test_position_has_stop_loss_alert():
    assert "stop_loss" in Position._alerts
    alert = Position._alerts["stop_loss"]
    assert alert.trigger == "relative_strength"
    assert alert.threshold == 0.25
    assert alert.severity == "critical"


def test_position_source_binding():
    assert Position._source_binding is not None
    assert Position._source_binding.identity == "symbol"


def test_market_regime_has_3_beliefs():
    assert "risk_on" in MarketRegime._beliefs
    assert "trend_following" in MarketRegime._beliefs
    assert "mean_reverting_regime" in MarketRegime._beliefs
    assert len(MarketRegime._beliefs) == 3


def test_all_entities_register(app):
    from fund_v2.entities import ALL_ENTITIES
    app.register(*ALL_ENTITIES)


def test_all_entities_includes_market_regime():
    from fund_v2.entities import ALL_ENTITIES
    assert MarketRegime in ALL_ENTITIES


def test_sector_inverse_relationship():
    rel = Sector._relationships["instruments"]
    assert rel.many is True
    assert rel.inverse == "in_sector"


def test_macro_factor_has_alert():
    assert "macro_shift" in MacroFactor._alerts
