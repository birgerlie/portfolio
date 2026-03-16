"""Integration test: stream event -> PriceCache -> ObservationRecorder -> SiliconDB mock."""

import queue
import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fund.price_cache import PriceCache
from fund.observation_recorder import ObservationRecorder
from fund.stream_service import StreamEvent
from fund.tempo import Tempo
from fund.reactor import Reactor, ReactorConfig


class TestStreamingPipeline:
    def test_trade_event_flows_through_pipeline(self):
        """Simulates: trade arrives -> cache updated -> observation recorded -> reactor fires."""
        price_cache = PriceCache()
        silicondb = MagicMock()
        silicondb.epistemic_briefing.return_value = {"anchors": [], "surprises": []}
        recorder = ObservationRecorder(price_cache, silicondb)
        tempo = Tempo()
        tempo.update_temperature(0.5)  # Warm
        reactor = Reactor(
            silicondb_client=silicondb,
            broker=MagicMock(),
            supabase_sync=MagicMock(),
            price_cache=price_cache,
            tempo=tempo,
            config=ReactorConfig(portfolio_symbols=["AAPL"], reference_symbols=["SPY"]),
        )

        ts = time.time()
        price_cache.update_trade("AAPL", Decimal("152.50"), Decimal("200"), ts)
        recorder.record_symbol("AAPL")
        recorder.flush()

        assert silicondb.record_observation_batch.call_count == 1
        batch = silicondb.record_observation_batch.call_args[0][0]
        assert any("AAPL:price" == obs["external_id"] for obs in batch)

        reactor.on_micro_shift({"symbol": "AAPL", "delta": 0.06})
        silicondb.propagate.assert_called()

        reactor.on_significant_shift({"symbol": "AAPL", "delta": 0.2})
        silicondb.epistemic_briefing.assert_called()

    def test_cold_market_only_heartbeat(self):
        silicondb = MagicMock()
        tempo = Tempo()  # COLD
        reactor = Reactor(
            silicondb_client=silicondb,
            broker=MagicMock(),
            supabase_sync=MagicMock(),
            price_cache=PriceCache(),
            tempo=tempo,
            config=ReactorConfig(portfolio_symbols=["AAPL"], reference_symbols=["SPY"]),
        )
        reactor.on_significant_shift({"symbol": "AAPL", "delta": 0.2})
        silicondb.epistemic_briefing.assert_not_called()

    def test_queue_overflow_drops_events(self):
        small_queue = queue.Queue(maxsize=2)
        for i in range(5):
            evt = StreamEvent(kind="trade", symbol="AAPL", data={"price": 150 + i})
            try:
                small_queue.put_nowait(evt)
            except queue.Full:
                pass
        assert small_queue.qsize() == 2
