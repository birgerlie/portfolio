"""Tests for the Tempo module — ThermoTier enum and Tempo class."""
import pytest
from fund.tempo import ThermoTier, Tempo


class TestThermoTier:
    def test_enum_values_exist(self):
        assert ThermoTier.COLD
        assert ThermoTier.WARM
        assert ThermoTier.HOT
        assert ThermoTier.CRITICAL

    def test_from_temperature_cold(self):
        assert ThermoTier.from_temperature(0.0) == ThermoTier.COLD
        assert ThermoTier.from_temperature(0.29) == ThermoTier.COLD

    def test_from_temperature_warm(self):
        assert ThermoTier.from_temperature(0.3) == ThermoTier.WARM
        assert ThermoTier.from_temperature(0.59) == ThermoTier.WARM

    def test_from_temperature_hot(self):
        assert ThermoTier.from_temperature(0.6) == ThermoTier.HOT
        assert ThermoTier.from_temperature(0.79) == ThermoTier.HOT

    def test_from_temperature_critical(self):
        assert ThermoTier.from_temperature(0.8) == ThermoTier.CRITICAL
        assert ThermoTier.from_temperature(1.0) == ThermoTier.CRITICAL

    def test_from_temperature_custom_thresholds(self):
        assert ThermoTier.from_temperature(0.1, cold=0.2, warm=0.5, hot=0.7) == ThermoTier.COLD
        assert ThermoTier.from_temperature(0.3, cold=0.2, warm=0.5, hot=0.7) == ThermoTier.WARM
        assert ThermoTier.from_temperature(0.6, cold=0.2, warm=0.5, hot=0.7) == ThermoTier.HOT
        assert ThermoTier.from_temperature(0.9, cold=0.2, warm=0.5, hot=0.7) == ThermoTier.CRITICAL

    def test_from_temperature_exact_boundaries(self):
        # Boundary: cold threshold
        assert ThermoTier.from_temperature(0.3) == ThermoTier.WARM
        # Boundary: warm threshold
        assert ThermoTier.from_temperature(0.6) == ThermoTier.HOT
        # Boundary: hot threshold
        assert ThermoTier.from_temperature(0.8) == ThermoTier.CRITICAL


class TestTempo:
    def test_default_init(self):
        t = Tempo()
        assert t.current_tier == ThermoTier.COLD
        assert t.temperature == 0.0

    def test_init_with_thresholds(self):
        t = Tempo(cold_threshold=0.2, warm_threshold=0.5, hot_threshold=0.7)
        assert t.current_tier == ThermoTier.COLD

    def test_update_temperature_no_tier_change(self):
        t = Tempo()
        changed = t.update_temperature(0.1)
        assert changed is False
        assert t.current_tier == ThermoTier.COLD
        assert t.temperature == 0.1

    def test_update_temperature_tier_change_cold_to_warm(self):
        t = Tempo()
        changed = t.update_temperature(0.5)
        assert changed is True
        assert t.current_tier == ThermoTier.WARM
        assert t.temperature == 0.5

    def test_update_temperature_tier_change_to_hot(self):
        t = Tempo()
        t.update_temperature(0.7)
        assert t.current_tier == ThermoTier.HOT

    def test_update_temperature_tier_change_to_critical(self):
        t = Tempo()
        changed = t.update_temperature(0.9)
        assert changed is True
        assert t.current_tier == ThermoTier.CRITICAL

    def test_update_temperature_same_tier_returns_false(self):
        t = Tempo()
        t.update_temperature(0.5)  # -> WARM
        changed = t.update_temperature(0.55)  # still WARM
        assert changed is False
        assert t.temperature == 0.55

    def test_update_temperature_downgrade(self):
        t = Tempo()
        t.update_temperature(0.9)  # CRITICAL
        changed = t.update_temperature(0.1)  # back to COLD
        assert changed is True
        assert t.current_tier == ThermoTier.COLD

    def test_get_cooldown_ms_cold(self):
        t = Tempo()
        assert t.get_cooldown_ms() is None

    def test_get_cooldown_ms_warm(self):
        t = Tempo()
        t.update_temperature(0.5)
        assert t.get_cooldown_ms() == 30_000

    def test_get_cooldown_ms_hot(self):
        t = Tempo()
        t.update_temperature(0.7)
        assert t.get_cooldown_ms() == 10_000

    def test_get_cooldown_ms_critical(self):
        t = Tempo()
        t.update_temperature(0.9)
        assert t.get_cooldown_ms() == 5_000

    def test_should_analyze_cold(self):
        t = Tempo()
        assert t.should_analyze() is False

    def test_should_analyze_warm(self):
        t = Tempo()
        t.update_temperature(0.5)
        assert t.should_analyze() is True

    def test_should_analyze_hot(self):
        t = Tempo()
        t.update_temperature(0.7)
        assert t.should_analyze() is True

    def test_should_analyze_critical(self):
        t = Tempo()
        t.update_temperature(0.9)
        assert t.should_analyze() is True

    def test_init_with_silicondb_client(self):
        mock_client = object()
        t = Tempo(silicondb_client=mock_client)
        assert t.current_tier == ThermoTier.COLD
