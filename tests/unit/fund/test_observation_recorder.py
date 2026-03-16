"""Unit tests for ObservationRecorder — all external dependencies are mocked."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from fund.observation_recorder import ObservationRecorder


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_price_entry(
    symbol: str = "AAPL",
    price: float = 150.0,
    vwap: float = 149.5,
    trade_count: int = 100,
    spread: float = 0.05,
    stale: bool = False,
) -> MagicMock:
    entry = MagicMock()
    entry.symbol = symbol
    entry.price = price
    entry.vwap = vwap
    entry.trade_count = trade_count
    entry.spread = spread
    entry.is_stale.return_value = stale
    return entry


def _make_recorder(batch_interval: float = 1.0):
    price_cache = MagicMock()
    silicondb_client = MagicMock()
    recorder = ObservationRecorder(price_cache, silicondb_client, batch_interval=batch_interval)
    return recorder, price_cache, silicondb_client


# ── __init__ ─────────────────────────────────────────────────────────────────

def test_init_stores_batch_interval():
    recorder, _, _ = _make_recorder(batch_interval=2.5)
    assert recorder.batch_interval == 2.5


def test_init_default_batch_interval():
    price_cache = MagicMock()
    silicondb = MagicMock()
    recorder = ObservationRecorder(price_cache, silicondb)
    assert recorder.batch_interval == 1.0


# ── record_symbol ─────────────────────────────────────────────────────────────

def test_record_symbol_marks_pending():
    recorder, _, _ = _make_recorder()
    recorder.record_symbol("AAPL")
    assert "AAPL" in recorder.pending_symbols


def test_record_symbol_dedup():
    """Recording same symbol twice should result in one entry (set semantics)."""
    recorder, _, _ = _make_recorder()
    recorder.record_symbol("AAPL")
    recorder.record_symbol("AAPL")
    assert len([s for s in recorder.pending_symbols if s == "AAPL"]) == 1


def test_record_multiple_symbols():
    recorder, _, _ = _make_recorder()
    recorder.record_symbol("AAPL")
    recorder.record_symbol("MSFT")
    recorder.record_symbol("GOOGL")
    assert recorder.pending_symbols == {"AAPL", "MSFT", "GOOGL"}


# ── flush ─────────────────────────────────────────────────────────────────────

def test_flush_calls_silicondb_for_pending_symbols():
    recorder, price_cache, silicondb = _make_recorder()
    price_cache.get.return_value = _make_price_entry("AAPL")

    recorder.record_symbol("AAPL")
    recorder.flush()

    silicondb.record_observation_batch.assert_called_once()


def test_flush_sends_correct_observation_structure():
    recorder, price_cache, silicondb = _make_recorder()
    entry = _make_price_entry("AAPL", price=150.0, vwap=149.5, trade_count=200, spread=0.05)
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    batch = silicondb.record_observation_batch.call_args[0][0]
    assert len(batch) > 0

    # Check that observations contain required fields
    external_ids = {obs["external_id"] for obs in batch}
    # Should include price, vwap, trade_intensity, spread observations
    assert any("AAPL:price" in eid for eid in external_ids)
    assert any("AAPL:vwap" in eid for eid in external_ids)
    assert any("AAPL:trade_intensity" in eid for eid in external_ids)
    assert any("AAPL:spread" in eid for eid in external_ids)


def test_flush_observation_has_required_keys():
    recorder, price_cache, silicondb = _make_recorder()
    price_cache.get.return_value = _make_price_entry("MSFT")

    recorder.record_symbol("MSFT")
    recorder.flush()

    batch = silicondb.record_observation_batch.call_args[0][0]
    first_obs = batch[0]
    assert "external_id" in first_obs
    assert "confirmed" in first_obs
    assert "source" in first_obs
    assert "metadata" in first_obs
    assert first_obs["confirmed"] is True
    assert first_obs["source"] == "alpaca_stream"


def test_flush_clears_pending_symbols():
    recorder, price_cache, silicondb = _make_recorder()
    price_cache.get.return_value = _make_price_entry("AAPL")

    recorder.record_symbol("AAPL")
    recorder.flush()

    assert len(recorder.pending_symbols) == 0


def test_flush_skips_stale_symbols():
    recorder, price_cache, silicondb = _make_recorder()
    stale_entry = _make_price_entry("AAPL", stale=True)
    price_cache.get.return_value = stale_entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    silicondb.record_observation_batch.assert_not_called()


def test_flush_skips_symbol_if_cache_returns_none():
    recorder, price_cache, silicondb = _make_recorder()
    price_cache.get.return_value = None

    recorder.record_symbol("AAPL")
    recorder.flush()

    silicondb.record_observation_batch.assert_not_called()


def test_flush_with_no_pending_symbols():
    recorder, price_cache, silicondb = _make_recorder()
    # Should not raise
    recorder.flush()
    silicondb.record_observation_batch.assert_not_called()


def test_flush_multiple_symbols():
    recorder, price_cache, silicondb = _make_recorder()

    def get_side_effect(symbol):
        return _make_price_entry(symbol)

    price_cache.get.side_effect = get_side_effect

    recorder.record_symbol("AAPL")
    recorder.record_symbol("MSFT")
    recorder.flush()

    # Should have observations for both symbols in a single batch call
    batch = silicondb.record_observation_batch.call_args[0][0]
    all_external_ids = {obs["external_id"] for obs in batch}
    assert any("AAPL" in eid for eid in all_external_ids)
    assert any("MSFT" in eid for eid in all_external_ids)


def test_flush_silicondb_error_is_caught_not_raised():
    recorder, price_cache, silicondb = _make_recorder()
    price_cache.get.return_value = _make_price_entry("AAPL")
    silicondb.record_observation_batch.side_effect = Exception("connection refused")

    recorder.record_symbol("AAPL")
    # Should not raise
    recorder.flush()


def test_flush_partial_silicondb_error_continues():
    """Batch is sent as a unit; a batch error is caught and does not raise."""
    recorder, price_cache, silicondb = _make_recorder()

    def get_side_effect(symbol):
        return _make_price_entry(symbol)

    price_cache.get.side_effect = get_side_effect
    silicondb.record_observation_batch.side_effect = Exception("transient error")

    recorder.record_symbol("AAPL")
    recorder.record_symbol("MSFT")
    # Should not raise
    recorder.flush()

    # Batch was attempted once
    assert silicondb.record_observation_batch.call_count == 1


# ── set_volume_baseline ───────────────────────────────────────────────────────

def test_set_volume_baseline_stores_value():
    recorder, _, _ = _make_recorder()
    recorder.set_volume_baseline("AAPL", 1_000_000)
    assert recorder._volume_baselines.get("AAPL") == 1_000_000


def test_set_volume_baseline_multiple_symbols():
    recorder, _, _ = _make_recorder()
    recorder.set_volume_baseline("AAPL", 1_000_000)
    recorder.set_volume_baseline("MSFT", 500_000)
    assert recorder._volume_baselines["AAPL"] == 1_000_000
    assert recorder._volume_baselines["MSFT"] == 500_000


# ── get_anomalies ─────────────────────────────────────────────────────────────

def test_get_anomalies_returns_empty_initially():
    recorder, _, _ = _make_recorder()
    assert recorder.get_anomalies() == []


def test_get_anomalies_clears_after_call():
    recorder, price_cache, silicondb = _make_recorder()
    # Set baseline and trigger anomaly via flush
    recorder.set_volume_baseline("AAPL", 100_000)
    # trade_count >> 2x baseline → anomaly
    entry = _make_price_entry("AAPL", trade_count=300_000)
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    anomalies_first = recorder.get_anomalies()
    assert "AAPL" in anomalies_first

    # Second call should return empty (cleared)
    anomalies_second = recorder.get_anomalies()
    assert anomalies_second == []


def test_get_anomalies_detects_volume_spike():
    recorder, price_cache, silicondb = _make_recorder()
    recorder.set_volume_baseline("AAPL", 100_000)
    # trade_count exactly at 2x = not anomaly, >2x = anomaly
    entry = _make_price_entry("AAPL", trade_count=200_001)
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    assert "AAPL" in recorder.get_anomalies()


def test_get_anomalies_no_spike_below_2x():
    recorder, price_cache, silicondb = _make_recorder()
    recorder.set_volume_baseline("AAPL", 100_000)
    entry = _make_price_entry("AAPL", trade_count=150_000)  # 1.5x, below threshold
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    assert "AAPL" not in recorder.get_anomalies()


def test_get_anomalies_no_baseline_no_anomaly():
    recorder, price_cache, silicondb = _make_recorder()
    # No baseline set — even high volume should not trigger anomaly
    entry = _make_price_entry("AAPL", trade_count=999_999)
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    assert recorder.get_anomalies() == []


# ── volume_anomaly in observation ────────────────────────────────────────────

def test_flush_includes_volume_anomaly_observation_when_spike():
    recorder, price_cache, silicondb = _make_recorder()
    recorder.set_volume_baseline("AAPL", 100_000)
    entry = _make_price_entry("AAPL", trade_count=300_000)
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    batch = silicondb.record_observation_batch.call_args[0][0]
    all_external_ids = {obs["external_id"] for obs in batch}
    assert "AAPL:volume_anomaly" in all_external_ids


def test_flush_no_volume_anomaly_observation_without_spike():
    recorder, price_cache, silicondb = _make_recorder()
    recorder.set_volume_baseline("AAPL", 100_000)
    entry = _make_price_entry("AAPL", trade_count=50_000)
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    batch = silicondb.record_observation_batch.call_args[0][0]
    all_external_ids = {obs["external_id"] for obs in batch}
    assert "AAPL:volume_anomaly" not in all_external_ids


# ── metadata content ──────────────────────────────────────────────────────────

def test_price_observation_metadata_contains_value():
    recorder, price_cache, silicondb = _make_recorder()
    entry = _make_price_entry("AAPL", price=155.25)
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    batch = silicondb.record_observation_batch.call_args[0][0]
    price_obs = next(obs for obs in batch if obs["external_id"] == "AAPL:price")
    assert price_obs["metadata"]["value"] == 155.25


def test_vwap_observation_metadata_contains_value():
    recorder, price_cache, silicondb = _make_recorder()
    entry = _make_price_entry("AAPL", vwap=149.80)
    price_cache.get.return_value = entry

    recorder.record_symbol("AAPL")
    recorder.flush()

    batch = silicondb.record_observation_batch.call_args[0][0]
    vwap_obs = next(obs for obs in batch if obs["external_id"] == "AAPL:vwap")
    assert vwap_obs["metadata"]["value"] == 149.80
