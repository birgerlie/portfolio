"""Tests for SignalTracker belief graph signal detection."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from fund.signal_tracker import Signal, SignalTracker


# ── helpers ─────────────────────────────────────────────────────────────────


def make_silicondb(uncertain: list | None = None, thermo_map: dict | None = None) -> MagicMock:
    """Build a mock SiliconDB client."""
    client = MagicMock()
    client.get_uncertain_beliefs.return_value = uncertain or []

    thermo_map = thermo_map or {}

    def _node_thermo(node_key: str) -> float:
        symbol = node_key.split(":")[0]
        return thermo_map.get(symbol, 0.5)

    client.node_thermo.side_effect = _node_thermo
    return client


# ── tests ────────────────────────────────────────────────────────────────────


class TestInit:
    def test_empty_signals_on_init(self):
        tracker = SignalTracker(make_silicondb(), portfolio_symbols=[])
        assert tracker.get_signals() == []

    def test_empty_decayed_on_init(self):
        tracker = SignalTracker(make_silicondb(), portfolio_symbols=[])
        assert tracker.get_decayed() == []


class TestSignalDetection:
    def test_low_entropy_symbol_detected_as_signal(self):
        """Symbol NOT in uncertain set → low entropy → signal if temp sufficient."""
        db = make_silicondb(uncertain=[], thermo_map={"NVDA": 0.5})
        tracker = SignalTracker(db, portfolio_symbols=[])
        new = tracker.update(["NVDA"])
        assert len(new) == 1
        assert new[0].symbol == "NVDA"
        assert new[0].status == "active"

    def test_high_entropy_symbol_not_a_signal(self):
        """Symbol in uncertain set → noise, no signal created."""
        db = make_silicondb(uncertain=["AAPL"], thermo_map={"AAPL": 0.5})
        tracker = SignalTracker(db, portfolio_symbols=[])
        new = tracker.update(["AAPL"])
        assert new == []
        assert tracker.get_signals() == []

    def test_signal_strength_formula(self):
        """signal_strength = (1 - 0.2) * max(temperature, 0.01)."""
        db = make_silicondb(uncertain=[], thermo_map={"TSLA": 0.75})
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["TSLA"])
        sigs = tracker.get_signals()
        assert len(sigs) == 1
        expected = (1.0 - 0.2) * 0.75
        assert abs(sigs[0].signal_strength - expected) < 1e-9

    def test_below_threshold_not_added(self):
        """signal_strength <= 0.1 should not be stored."""
        # temperature = 0.01 → strength = 0.8 * 0.01 = 0.008, well below 0.1
        db = make_silicondb(uncertain=[], thermo_map={"WEAK": 0.01})
        tracker = SignalTracker(db, portfolio_symbols=[])
        new = tracker.update(["WEAK"])
        assert new == []
        assert tracker.get_signals() == []


class TestPortfolioExclusion:
    def test_portfolio_symbols_excluded(self):
        db = make_silicondb(uncertain=[], thermo_map={"AAPL": 1.0, "MSFT": 1.0})
        tracker = SignalTracker(db, portfolio_symbols=["AAPL"])
        new = tracker.update(["AAPL", "MSFT"])
        symbols = [s.symbol for s in new]
        assert "AAPL" not in symbols
        assert "MSFT" in symbols

    def test_crypto_pairs_excluded(self):
        """Symbols containing '/' are crypto and must be skipped."""
        db = make_silicondb(uncertain=[], thermo_map={"BTC/USD": 1.0})
        tracker = SignalTracker(db, portfolio_symbols=[])
        new = tracker.update(["BTC/USD"])
        assert new == []


class TestSignalRanking:
    def test_higher_temperature_ranks_higher(self):
        db = make_silicondb(
            uncertain=[],
            thermo_map={"LOW": 0.2, "HIGH": 0.9, "MID": 0.5},
        )
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["LOW", "HIGH", "MID"])
        ranked = tracker.get_signals()
        assert ranked[0].symbol == "HIGH"
        assert ranked[-1].symbol == "LOW"

    def test_ranked_descending_by_strength(self):
        db = make_silicondb(uncertain=[], thermo_map={"A": 0.3, "B": 0.8, "C": 0.5})
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["A", "B", "C"])
        ranked = tracker.get_signals()
        strengths = [s.signal_strength for s in ranked]
        assert strengths == sorted(strengths, reverse=True)


class TestSignalDecay:
    def test_symbol_becomes_uncertain_marks_decayed(self):
        """Symbol that was a signal and appears in uncertain set should decay."""
        # First cycle: signal detected
        db = make_silicondb(uncertain=[], thermo_map={"NVDA": 0.9})
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["NVDA"])
        assert len(tracker.get_signals()) == 1

        # Second cycle: symbol becomes uncertain
        db.get_uncertain_beliefs.return_value = ["NVDA"]
        tracker.update(["NVDA"])
        assert tracker.get_signals() == []
        assert "NVDA" in tracker.get_decayed()

    def test_decayed_list_resets_each_update(self):
        db = make_silicondb(uncertain=[], thermo_map={"NVDA": 0.9})
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["NVDA"])

        db.get_uncertain_beliefs.return_value = ["NVDA"]
        tracker.update(["NVDA"])
        assert "NVDA" in tracker.get_decayed()

        # Third cycle with no new decays
        db.get_uncertain_beliefs.return_value = []
        tracker.update([])
        assert tracker.get_decayed() == []

    def test_decayed_signal_can_return(self):
        """A decayed symbol reappears as low-entropy → re-detected as new signal."""
        db = make_silicondb(uncertain=[], thermo_map={"NVDA": 0.9})
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["NVDA"])

        # Decay it
        db.get_uncertain_beliefs.return_value = ["NVDA"]
        tracker.update(["NVDA"])
        assert tracker.get_signals() == []

        # Recover
        db.get_uncertain_beliefs.return_value = []
        new = tracker.update(["NVDA"])
        assert len(new) == 1
        assert new[0].symbol == "NVDA"
        assert new[0].status == "active"


class TestSignalHistory:
    def test_history_appended_each_cycle(self):
        db = make_silicondb(uncertain=[], thermo_map={"MSFT": 0.6})
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["MSFT"])
        tracker.update(["MSFT"])
        history = tracker.get_signal_history("MSFT")
        assert len(history) == 2

    def test_history_entry_has_required_keys(self):
        db = make_silicondb(uncertain=[], thermo_map={"MSFT": 0.6})
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["MSFT"])
        entry = tracker.get_signal_history("MSFT")[0]
        assert {"time", "strength", "entropy", "temperature"} <= entry.keys()

    def test_empty_history_for_unknown_symbol(self):
        tracker = SignalTracker(make_silicondb(), portfolio_symbols=[])
        assert tracker.get_signal_history("UNKNOWN") == []

    def test_history_values_correct(self):
        db = make_silicondb(uncertain=[], thermo_map={"GOOG": 0.7})
        tracker = SignalTracker(db, portfolio_symbols=[])
        tracker.update(["GOOG"])
        entry = tracker.get_signal_history("GOOG")[0]
        assert entry["entropy"] == pytest.approx(0.2)
        assert entry["temperature"] == pytest.approx(0.7)
        assert entry["strength"] == pytest.approx(0.8 * 0.7)


class TestErrorHandling:
    def test_get_uncertain_beliefs_error_handled_gracefully(self):
        db = MagicMock()
        db.get_uncertain_beliefs.side_effect = RuntimeError("network error")
        db.node_thermo.return_value = 0.5

        tracker = SignalTracker(db, portfolio_symbols=[])
        # Should not raise; uncertain_set falls back to empty
        result = tracker.update(["AAPL"])
        # AAPL treated as low entropy since uncertain_set is empty
        assert isinstance(result, list)

    def test_node_thermo_error_handled_gracefully(self):
        db = make_silicondb(uncertain=[])
        db.node_thermo.side_effect = RuntimeError("thermo error")

        tracker = SignalTracker(db, portfolio_symbols=[])
        # Should not raise; temperature falls back to 0.0
        result = tracker.update(["AAPL"])
        # With temperature=0.0, strength = 0.8 * 0.01 = 0.008 → below threshold → no signal
        assert result == []

    def test_partial_failure_continues(self):
        """node_thermo fails for one symbol but not the other."""
        call_count = 0

        def thermo(node_key: str) -> float:
            nonlocal call_count
            call_count += 1
            if "FAIL" in node_key:
                raise RuntimeError("boom")
            return 0.9

        db = make_silicondb(uncertain=[])
        db.node_thermo.side_effect = thermo

        tracker = SignalTracker(db, portfolio_symbols=[])
        new = tracker.update(["FAIL", "GOOD"])
        symbols = [s.symbol for s in new]
        assert "GOOD" in symbols
        assert "FAIL" not in symbols


class TestSignalDataclass:
    def test_signal_has_all_required_fields(self):
        now = datetime.utcnow()
        sig = Signal(
            symbol="NVDA",
            signal_strength=0.72,
            entropy=0.2,
            node_temperature=0.9,
            belief_type="conviction",
            conviction=0.72,
            first_seen=now,
            last_seen=now,
            status="active",
        )
        assert sig.symbol == "NVDA"
        assert sig.signal_strength == pytest.approx(0.72)
        assert sig.entropy == pytest.approx(0.2)
        assert sig.node_temperature == pytest.approx(0.9)
        assert sig.belief_type == "conviction"
        assert sig.conviction == pytest.approx(0.72)
        assert sig.first_seen == now
        assert sig.last_seen == now
        assert sig.status == "active"

    def test_signal_default_status_is_active(self):
        now = datetime.utcnow()
        sig = Signal(
            symbol="AAPL",
            signal_strength=0.5,
            entropy=0.2,
            node_temperature=0.6,
            belief_type="conviction",
            conviction=0.5,
            first_seen=now,
            last_seen=now,
        )
        assert sig.status == "active"
