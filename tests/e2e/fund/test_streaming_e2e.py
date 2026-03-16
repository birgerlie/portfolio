"""End-to-end tests for streaming trading engine components.

These tests connect to the real Alpaca paper trading API and are gated by
environment variables. They will be skipped unless ALPACA_PAPER_KEY and
ALPACA_PAPER_SECRET are set.

Run with:
    PYTHONPATH=src ALPACA_PAPER_KEY=<key> ALPACA_PAPER_SECRET=<secret> \
        python3 -m pytest tests/e2e/fund/test_streaming_e2e.py -v --tb=short
"""

import os
import queue
import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from fund.alpaca_broker import AlpacaBroker
from fund.broker_types import AlpacaConfig, StreamConfig
from fund.observation_recorder import ObservationRecorder
from fund.price_cache import PriceCache
from fund.reactor import Reactor, ReactorConfig
from fund.stream_service import AlpacaStreamService, StreamEvent
from fund.tempo import Tempo

ALPACA_KEY = os.environ.get("ALPACA_PAPER_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_PAPER_SECRET")

pytestmark = pytest.mark.skipif(
    not ALPACA_KEY or not ALPACA_SECRET,
    reason="ALPACA_PAPER_KEY and ALPACA_PAPER_SECRET not set",
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_alpaca_config() -> AlpacaConfig:
    return AlpacaConfig(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET, paper=True)


def _make_stream_service(
    symbols: list[str],
    price_cache: PriceCache | None = None,
    event_queue: queue.Queue | None = None,
    maxsize: int = 1000,
) -> AlpacaStreamService:
    if price_cache is None:
        price_cache = PriceCache()
    if event_queue is None:
        event_queue = queue.Queue(maxsize=maxsize)
    stream_config = StreamConfig(portfolio_symbols=symbols, data_feed="iex")
    return AlpacaStreamService(
        alpaca_config=_make_alpaca_config(),
        stream_config=stream_config,
        price_cache=price_cache,
        event_queue=event_queue,
    )


def _wait_for_price(price_cache: PriceCache, symbol: str, timeout: float = 10.0) -> bool:
    """Poll price_cache until symbol has a non-zero price or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = price_cache.get(symbol)
        if entry is not None and entry.price > Decimal("0"):
            return True
        time.sleep(0.25)
    return False


def _wait_for_queue_event(event_queue: queue.Queue, timeout: float = 10.0) -> StreamEvent | None:
    """Block until an event arrives on the queue or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return event_queue.get(timeout=0.5)
        except queue.Empty:
            continue
    return None


# ---------------------------------------------------------------------------
# Test 1: PriceCache + AlpacaStreamService integration
# ---------------------------------------------------------------------------

def test_price_cache_updated_by_stream():
    """Connect to Alpaca paper streams for SPY, verify PriceCache gets updated.

    Outside market hours trades may not arrive — skip if no data after 10s.
    """
    price_cache = PriceCache()
    svc = _make_stream_service(["SPY"], price_cache=price_cache)

    svc.start()
    try:
        got_price = _wait_for_price(price_cache, "SPY", timeout=10.0)
        if not got_price:
            pytest.skip("No SPY trade data received within 10s (likely outside market hours)")

        entry = price_cache.get("SPY")
        assert entry is not None
        assert entry.symbol == "SPY"
        assert entry.price > Decimal("0"), f"Expected non-zero price, got {entry.price}"
    finally:
        svc.stop()

    assert not svc.is_running, "Expected stream to be stopped after stop()"


# ---------------------------------------------------------------------------
# Test 2: Full pipeline: Stream → PriceCache → ObservationRecorder → Mock SiliconDB
# ---------------------------------------------------------------------------

def test_full_pipeline_stream_to_observation_recorder():
    """Start streaming SPY, wait for price, record observation, verify SiliconDB call."""
    price_cache = PriceCache()
    mock_silicondb = MagicMock()
    recorder = ObservationRecorder(price_cache=price_cache, silicondb_client=mock_silicondb)
    svc = _make_stream_service(["SPY"], price_cache=price_cache)

    svc.start()
    try:
        got_price = _wait_for_price(price_cache, "SPY", timeout=10.0)
        if not got_price:
            pytest.skip("No SPY trade data received within 10s (likely outside market hours)")

        recorder.record_symbol("SPY")
        recorder.flush()
    finally:
        svc.stop()

    mock_silicondb.record_observation_batch.assert_called_once()
    batch = mock_silicondb.record_observation_batch.call_args[0][0]
    assert isinstance(batch, list), "Expected batch to be a list"
    assert len(batch) > 0, "Expected at least one observation in batch"

    external_ids = [obs["external_id"] for obs in batch]
    assert any("SPY:price" in eid for eid in external_ids), (
        f"Expected SPY:price in observations, got: {external_ids}"
    )


# ---------------------------------------------------------------------------
# Test 3: StreamService queue integration
# ---------------------------------------------------------------------------

def test_stream_events_appear_on_queue():
    """Start streaming with a small queue; verify StreamEvent structure."""
    event_queue: queue.Queue = queue.Queue(maxsize=100)
    svc = _make_stream_service(["SPY"], event_queue=event_queue, maxsize=100)

    svc.start()
    try:
        event = _wait_for_queue_event(event_queue, timeout=10.0)
        if event is None:
            pytest.skip("No queue events received within 10s (likely outside market hours)")

        assert isinstance(event, StreamEvent), f"Expected StreamEvent, got {type(event)}"
        assert event.kind in ("trade", "quote", "fill"), f"Unexpected kind: {event.kind}"
        assert isinstance(event.symbol, str) and len(event.symbol) > 0, "symbol must be non-empty"
        assert isinstance(event.data, dict), "data must be a dict"
        assert isinstance(event.timestamp, float), "timestamp must be a float"
    finally:
        svc.stop()


# ---------------------------------------------------------------------------
# Test 4: AlpacaBroker + StreamService together
# ---------------------------------------------------------------------------

def test_broker_and_stream_together():
    """Connect broker, start stream, submit a far limit order, cancel it, stop stream."""
    config = _make_alpaca_config()
    broker = AlpacaBroker(config)

    assert broker.is_connected(), "Broker must connect with valid paper credentials"

    # Determine symbol to stream: use a held position or fall back to SPY
    positions = broker.get_positions()
    stream_symbol = positions[0].symbol if positions else "SPY"

    event_queue: queue.Queue = queue.Queue(maxsize=100)
    svc = _make_stream_service([stream_symbol], event_queue=event_queue)

    svc.start()
    submitted_order = None
    try:
        # Submit a limit order far below market — extremely unlikely to fill
        limit_price = Decimal("1.00")  # $1 limit for SPY/any stock — won't fill
        submitted_order = broker.submit_limit_order(
            symbol=stream_symbol,
            qty=Decimal("1"),
            side="buy",
            limit_price=limit_price,
        )
        assert submitted_order.id, "Order must have an ID"
        assert submitted_order.symbol == stream_symbol
        assert "limit" in submitted_order.order_type.lower()

        # Give stream a moment to run
        time.sleep(2)

    finally:
        # Cancel the order
        if submitted_order is not None:
            try:
                refreshed = broker.get_order(submitted_order.id)
                cancellable = {"new", "accepted", "pending_new", "held", "partially_filled"}
                if refreshed.status.lower() in cancellable:
                    broker.cancel_order(submitted_order.id)
                    time.sleep(1)
                    cancelled = broker.get_order(submitted_order.id)
                    assert "cancel" in cancelled.status.lower(), (
                        f"Expected cancelled status, got {cancelled.status}"
                    )
            except Exception:
                pass  # Best-effort cleanup

        svc.stop()

    assert not svc.is_running, "Stream must be stopped after stop()"


# ---------------------------------------------------------------------------
# Test 5: Tempo + Reactor integration (no real SiliconDB)
# ---------------------------------------------------------------------------

def test_tempo_reactor_on_micro_shift():
    """Create Tempo (warm), create Reactor with mock SiliconDB, trigger on_micro_shift."""
    price_cache = PriceCache()
    mock_silicondb = MagicMock()
    mock_broker = MagicMock()
    mock_supabase = MagicMock()

    tempo = Tempo()
    tempo.update_temperature(0.5)  # warm tier
    assert tempo.should_analyze(), "Tempo at 0.5 should be in warm tier and allow analysis"

    reactor_config = ReactorConfig(portfolio_symbols=["SPY"])
    reactor = Reactor(
        silicondb_client=mock_silicondb,
        broker=mock_broker,
        supabase_sync=mock_supabase,
        price_cache=price_cache,
        tempo=tempo,
        config=reactor_config,
    )

    svc = _make_stream_service(["SPY"], price_cache=price_cache)

    svc.start()
    try:
        got_price = _wait_for_price(price_cache, "SPY", timeout=10.0)
        if not got_price:
            # Inject a synthetic price to still exercise reactor path
            from decimal import Decimal
            from datetime import datetime, timezone
            price_cache.update_trade(
                "SPY", Decimal("500.00"), Decimal("10"), datetime.now(tz=timezone.utc)
            )

        reactor.on_micro_shift({"symbol": "SPY"})
    finally:
        svc.stop()

    mock_silicondb.propagate.assert_called_once_with(
        external_id="SPY:return",
        confidence=0.7,
        decay=0.5,
    )
    mock_silicondb.add_cooccurrences.assert_called_once()
