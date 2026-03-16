"""Unit tests for Reactor event handlers."""
from __future__ import annotations

import threading
from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest

from fund.reactor import Reactor, ReactorConfig
from fund.tempo import Tempo


@pytest.fixture()
def config():
    return ReactorConfig(
        portfolio_symbols=["AAPL", "MSFT", "GOOG"],
        reference_symbols=["SPY"],
    )


@pytest.fixture()
def deps():
    return {
        "silicondb_client": MagicMock(),
        "broker": MagicMock(),
        "supabase_sync": MagicMock(),
        "price_cache": MagicMock(),
    }


@pytest.fixture()
def tempo():
    return Tempo()


@pytest.fixture()
def reactor(deps, tempo, config):
    return Reactor(
        silicondb_client=deps["silicondb_client"],
        broker=deps["broker"],
        supabase_sync=deps["supabase_sync"],
        price_cache=deps["price_cache"],
        tempo=tempo,
        config=config,
    )


# ------------------------------------------------------------------
# Nervous tier
# ------------------------------------------------------------------

class TestOnMicroShift:
    def test_calls_propagate(self, reactor, deps):
        reactor.on_micro_shift({"symbol": "AAPL", "shift": 0.01})
        deps["silicondb_client"].propagate.assert_called_once_with(
            external_id="AAPL:return",
            confidence=0.7,
            decay=0.5,
        )

    def test_calls_add_cooccurrences(self, reactor, deps, config):
        reactor.on_micro_shift({"symbol": "AAPL", "shift": 0.01})
        deps["silicondb_client"].add_cooccurrences.assert_called_once_with(
            ids=[f"{s}:return" for s in config.portfolio_symbols],
            session_id="stream",
        )

    def test_propagate_error_handled_gracefully(self, reactor, deps):
        deps["silicondb_client"].propagate.side_effect = TimeoutError("timeout")
        # Should not raise
        reactor.on_micro_shift({"symbol": "AAPL"})
        # add_cooccurrences should still be called
        deps["silicondb_client"].add_cooccurrences.assert_called_once()

    def test_add_cooccurrences_error_handled_gracefully(self, reactor, deps):
        deps["silicondb_client"].add_cooccurrences.side_effect = RuntimeError("fail")
        reactor.on_micro_shift({"symbol": "MSFT"})  # should not raise


# ------------------------------------------------------------------
# Standard tier
# ------------------------------------------------------------------

class TestOnSignificantShift:
    def test_skipped_when_cold(self, reactor, deps, tempo):
        # Default tempo is cold (temperature=0.0)
        reactor.on_significant_shift({"shift": 0.05})
        deps["silicondb_client"].epistemic_briefing.assert_not_called()

    def test_calls_briefing_when_warm(self, reactor, deps, tempo):
        tempo.update_temperature(0.5)  # WARM tier
        reactor.on_significant_shift({"shift": 0.05})
        deps["silicondb_client"].epistemic_briefing.assert_called_once_with(
            topic="market",
            budget=30,
            anchor_ratio=0.3,
            hops=2,
            neighbor_k=5,
        )

    def test_briefing_error_handled_gracefully(self, reactor, deps, tempo):
        tempo.update_temperature(0.5)
        deps["silicondb_client"].epistemic_briefing.side_effect = ConnectionError("down")
        reactor.on_significant_shift({"shift": 0.05})  # should not raise


class TestOnThermoShift:
    def test_updates_temperature(self, reactor, tempo):
        reactor.on_thermo_shift({"temperature": 0.7})
        assert tempo.temperature == 0.7

    def test_missing_key_handled(self, reactor):
        reactor.on_thermo_shift({})  # should not raise


# ------------------------------------------------------------------
# Strategic tier
# ------------------------------------------------------------------

class TestOnRegimeChange:
    def test_executes_trades(self, reactor, deps):
        event = {
            "trades": [
                {"symbol": "AAPL", "qty": "10", "side": "buy"},
                {"symbol": "MSFT", "qty": "5", "side": "sell"},
            ]
        }
        reactor.on_regime_change(event)
        assert deps["broker"].submit_market_order.call_count == 2
        deps["broker"].submit_market_order.assert_any_call("AAPL", Decimal("10"), "buy")
        deps["broker"].submit_market_order.assert_any_call("MSFT", Decimal("5"), "sell")

    def test_syncs_supabase(self, reactor, deps):
        event = {"trades": []}
        reactor.on_regime_change(event)
        deps["supabase_sync"].push_snapshot.assert_called_once_with(event)

    def test_has_trade_lock(self, reactor):
        assert isinstance(reactor._trade_lock, type(threading.Lock()))

    def test_broker_error_handled_gracefully(self, reactor, deps):
        deps["broker"].submit_market_order.side_effect = RuntimeError("broker down")
        event = {"trades": [{"symbol": "AAPL", "qty": "1", "side": "buy"}]}
        reactor.on_regime_change(event)  # should not raise
        # snapshot should still be attempted
        deps["supabase_sync"].push_snapshot.assert_called_once()

    def test_supabase_error_handled_gracefully(self, reactor, deps):
        deps["supabase_sync"].push_snapshot.side_effect = Exception("supabase error")
        reactor.on_regime_change({"trades": []})  # should not raise

    def test_empty_trades(self, reactor, deps):
        reactor.on_regime_change({"trades": []})
        deps["broker"].submit_market_order.assert_not_called()
        deps["supabase_sync"].push_snapshot.assert_called_once()


# ------------------------------------------------------------------
# Discovery
# ------------------------------------------------------------------

class TestOnVolumeAnomaly:
    def test_records_observation(self, reactor, deps):
        event = {"symbol": "TSLA", "volume_ratio": 3.5}
        reactor.on_volume_anomaly(event)
        deps["silicondb_client"].record_observation_batch.assert_called_once()
        call_kwargs = deps["silicondb_client"].record_observation_batch.call_args
        observations = call_kwargs[1]["observations"]
        assert observations[0]["type"] == "volume_anomaly"
        assert observations[0]["symbol"] == "TSLA"

    def test_silicondb_error_handled_gracefully(self, reactor, deps):
        deps["silicondb_client"].record_observation_batch.side_effect = TimeoutError("timeout")
        reactor.on_volume_anomaly({"symbol": "TSLA"})  # should not raise


class TestOnLeadLagDiscovered:
    def test_inserts_triple(self, reactor, deps):
        event = {"subject": "AAPL:return", "predicate": "leads", "object": "MSFT:return", "lag_ms": 500}
        reactor.on_lead_lag_discovered(event)
        deps["silicondb_client"].insert_triples.assert_called_once_with(triples=[event])

    def test_silicondb_error_handled_gracefully(self, reactor, deps):
        deps["silicondb_client"].insert_triples.side_effect = RuntimeError("fail")
        reactor.on_lead_lag_discovered({"subject": "X", "predicate": "leads", "object": "Y"})  # should not raise
