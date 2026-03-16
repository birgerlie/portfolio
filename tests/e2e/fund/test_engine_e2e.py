"""End-to-end tests for LiveEngine startup, shutdown, and heartbeat.

These tests connect to the real Alpaca paper trading API and are gated by
environment variables. They will be skipped unless ALPACA_PAPER_KEY and
ALPACA_PAPER_SECRET are set.

Run with:
    PYTHONPATH=src ALPACA_PAPER_KEY=<key> ALPACA_PAPER_SECRET=<secret> \
        python3 -m pytest tests/e2e/fund/test_engine_e2e.py -v --tb=short
"""

import os
import queue
import time
from unittest.mock import MagicMock

import pytest

from fund.alpaca_broker import AlpacaBroker
from fund.broker_types import AlpacaConfig, StreamConfig
from fund.live_engine import LiveEngine
from fund.observation_recorder import ObservationRecorder
from fund.price_cache import PriceCache
from fund.reactor import Reactor, ReactorConfig
from fund.stream_service import AlpacaStreamService
from fund.tempo import Tempo

ALPACA_KEY = os.environ.get("ALPACA_PAPER_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_PAPER_SECRET")

pytestmark = pytest.mark.skipif(
    not ALPACA_KEY or not ALPACA_SECRET,
    reason="ALPACA_PAPER_KEY and ALPACA_PAPER_SECRET not set",
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _build_engine(
    symbols: list[str] | None = None,
    interval_seconds: int = 300,
    mock_silicondb: MagicMock | None = None,
    mock_supabase: MagicMock | None = None,
) -> tuple[LiveEngine, MagicMock, MagicMock]:
    """Construct a fully wired LiveEngine with real Alpaca connections.

    Returns (engine, mock_silicondb, mock_supabase) so callers can assert on
    the mocks.
    """
    if symbols is None:
        symbols = ["SPY"]
    if mock_silicondb is None:
        mock_silicondb = MagicMock()
    if mock_supabase is None:
        mock_supabase = MagicMock()

    alpaca_config = AlpacaConfig(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET, paper=True)
    broker = AlpacaBroker(alpaca_config)

    price_cache = PriceCache()
    event_queue: queue.Queue = queue.Queue(maxsize=1000)

    stream_config = StreamConfig(portfolio_symbols=symbols, data_feed="iex")
    stream_svc = AlpacaStreamService(
        alpaca_config=alpaca_config,
        stream_config=stream_config,
        price_cache=price_cache,
        event_queue=event_queue,
    )

    recorder = ObservationRecorder(
        price_cache=price_cache,
        silicondb_client=mock_silicondb,
    )

    tempo = Tempo()
    tempo.update_temperature(0.5)  # warm tier so analysis is active

    reactor_config = ReactorConfig(portfolio_symbols=symbols)
    reactor = Reactor(
        silicondb_client=mock_silicondb,
        broker=broker,
        supabase_sync=mock_supabase,
        price_cache=price_cache,
        tempo=tempo,
        config=reactor_config,
    )

    engine = LiveEngine(
        symbols=symbols,
        fund=None,           # not needed for stream / heartbeat tests
        supabase=mock_supabase,
        synthesizer=None,    # not needed for stream / heartbeat tests
        stream_service=stream_svc,
        observation_recorder=recorder,
        reactor=reactor,
        tempo=tempo,
        silicondb_client=mock_silicondb,
        interval_seconds=interval_seconds,
    )

    return engine, mock_silicondb, mock_supabase


# ---------------------------------------------------------------------------
# Test 6: LiveEngine startup and shutdown
# ---------------------------------------------------------------------------

def test_live_engine_startup_and_shutdown():
    """Build all real components, start engine, wait 5s, verify running, stop cleanly."""
    engine, _, _ = _build_engine(symbols=["SPY"])

    engine.start()
    try:
        time.sleep(5)
        assert engine._stream.is_running, "Stream must be running 5 seconds after start()"
        assert not engine._stop_event.is_set(), "Stop event must not be set while running"
    finally:
        engine.stop()

    # After stop, stream should no longer be running
    assert not engine._stream.is_running, "Stream must stop after engine.stop()"
    assert engine._stop_event.is_set(), "Stop event must be set after engine.stop()"


# ---------------------------------------------------------------------------
# Test 7: LiveEngine heartbeat fires
# ---------------------------------------------------------------------------

def test_live_engine_heartbeat_fires():
    """Start LiveEngine with a short interval, verify push_heartbeat called at least once."""
    mock_supabase = MagicMock()
    engine, _, _ = _build_engine(
        symbols=["SPY"],
        interval_seconds=2,
        mock_supabase=mock_supabase,
    )

    engine.start()
    try:
        # Wait long enough for at least one heartbeat cycle (interval=2s, wait 5s)
        time.sleep(5)
    finally:
        engine.stop()

    assert mock_supabase.push_heartbeat.call_count >= 1, (
        f"Expected push_heartbeat to be called at least once, "
        f"got {mock_supabase.push_heartbeat.call_count} calls"
    )

    # Verify heartbeat payload shape
    call_args = mock_supabase.push_heartbeat.call_args_list[0]
    payload = call_args[0][0]
    assert isinstance(payload, dict)
    assert payload.get("status") == "running"
    assert "alpaca_connected" in payload
    assert "active_positions" in payload
    assert "dropped_events" in payload
