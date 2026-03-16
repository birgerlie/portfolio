"""Integration: observations → SiliconDB beliefs → signal detection + quote aggregation."""

import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fund.price_cache import PriceCache
from fund.observation_recorder import ObservationRecorder
from fund.signal_tracker import SignalTracker


class TestSignalPipeline:
    def test_observation_to_signal_flow(self):
        """Observations build beliefs, SignalTracker detects signals."""
        silicondb = MagicMock()
        silicondb.get_uncertain_beliefs.return_value = []
        silicondb.node_thermo.return_value = {"temperature": 0.7}

        price_cache = PriceCache()
        recorder = ObservationRecorder(price_cache, silicondb)
        tracker = SignalTracker(silicondb, portfolio_symbols=["AAPL"])

        # Simulate trades for AMD (not in portfolio)
        ts = time.time()
        price_cache.update_trade("AMD", Decimal("150"), Decimal("1000"), ts)
        recorder.record_symbol("AMD")
        recorder.flush()
        assert silicondb.record_observation_batch.called

        # Run signal detection
        new_signals = tracker.update(["AAPL", "AMD"])
        assert any(s.symbol == "AMD" for s in new_signals)
        assert new_signals[0].signal_strength > 0

    def test_portfolio_symbols_not_signaled(self):
        """Portfolio symbols should not appear as signals."""
        silicondb = MagicMock()
        silicondb.get_uncertain_beliefs.return_value = []
        silicondb.node_thermo.return_value = {"temperature": 0.8}

        tracker = SignalTracker(silicondb, portfolio_symbols=["AAPL", "MSFT"])
        new_signals = tracker.update(["AAPL", "MSFT", "AMD"])
        signal_symbols = [s.symbol for s in new_signals]
        assert "AAPL" not in signal_symbols
        assert "MSFT" not in signal_symbols
        assert "AMD" in signal_symbols

    def test_quote_aggregation_flow(self):
        """Quotes aggregate and flush as single spread observation."""
        silicondb = MagicMock()
        price_cache = PriceCache()
        recorder = ObservationRecorder(price_cache, silicondb)

        ts = time.time()
        for i in range(10):
            recorder.record_quote("AAPL", 149.9 + i * 0.01, 150.1 + i * 0.01, ts + i * 0.1)
        recorder.flush()

        # Should have called record_observation_batch for quote spreads
        calls = silicondb.record_observation_batch.call_args_list
        all_obs = []
        for call in calls:
            all_obs.extend(call[0][0])
        spread_obs = [o for o in all_obs if "spread" in o["external_id"]]
        assert len(spread_obs) > 0
        assert spread_obs[0]["metadata"]["symbol"] == "AAPL"

    def test_signal_decay_on_high_entropy(self):
        """Signals decay when entropy rises."""
        silicondb = MagicMock()
        silicondb.get_uncertain_beliefs.return_value = []
        silicondb.node_thermo.return_value = {"temperature": 0.6}

        tracker = SignalTracker(silicondb, portfolio_symbols=["AAPL"])

        # Cycle 1: AMD has signal
        tracker.update(["AAPL", "AMD"])
        assert any(s.symbol == "AMD" for s in tracker.get_signals())

        # Cycle 2: AMD now uncertain
        silicondb.get_uncertain_beliefs.return_value = [
            {"external_id": "AMD:return", "entropy": 0.9}
        ]
        tracker.update(["AAPL", "AMD"])
        assert "AMD" in tracker.get_decayed()
        assert not any(s.symbol == "AMD" for s in tracker.get_signals())
