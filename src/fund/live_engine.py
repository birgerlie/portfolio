"""Live engine — thin wiring layer that connects streaming, observation, and reaction components."""

import logging
import queue
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ANSI colors for console event log
_C = {
    "trade": "\033[36m",     # cyan
    "quote": "\033[34m",     # blue
    "fill": "\033[32m",      # green
    "anomaly": "\033[33m",   # yellow
    "thermo": "\033[35m",    # magenta
    "regime": "\033[91m",    # bright red
    "reset": "\033[0m",
}


def _log_event(kind: str, symbol: str, detail: str = "") -> None:
    """Print a colored event line to console."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    color = _C.get(kind, "")
    reset = _C["reset"]
    tag = kind.upper().ljust(7)
    sym = symbol.ljust(6) if symbol else "      "
    print(f"{color}[{ts}] {tag} {sym} {detail}{reset}")


class LiveEngine:
    """Consumes events from AlpacaStreamService and coordinates observation recording,
    anomaly reaction, and Supabase heartbeat sync."""

    def __init__(
        self,
        symbols: list,
        fund,
        supabase,
        synthesizer,
        stream_service,          # AlpacaStreamService
        observation_recorder,    # ObservationRecorder
        reactor,                 # Reactor
        tempo,                   # Tempo
        silicondb_client,
        interval_seconds: int = 300,
        verbose: bool = True,
    ):
        self._symbols = symbols
        self._fund = fund
        self._supabase = supabase
        self._synthesizer = synthesizer
        self._stream = stream_service
        self._recorder = observation_recorder
        self._reactor = reactor
        self._tempo = tempo
        self._silicondb = silicondb_client
        self._interval = interval_seconds
        self._verbose = verbose
        self._stop_event = threading.Event()
        self._event_queue = stream_service._event_queue
        self._event_count = 0

    def start(self):
        self._stream.start()
        self._consumer_thread = threading.Thread(
            target=self._consume_events, daemon=True, name="event-consumer",
        )
        self._consumer_thread.start()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="heartbeat",
        )
        self._heartbeat_thread.start()
        logger.info("LiveEngine started: streaming + consumer + heartbeat")

    def stop(self):
        self._stop_event.set()
        self._stream.stop()
        logger.info("LiveEngine stopped")

    # ── queue consumer ────────────────────────────────────────────────────────

    def _consume_events(self):
        while not self._stop_event.is_set():
            try:
                event = self._event_queue.get(timeout=1.0)
            except queue.Empty:
                self._recorder.flush()
                continue

            self._event_count += 1

            if event.kind == "trade":
                self._recorder.record_symbol(event.symbol)
                if self._verbose:
                    price = event.data.get("price", "")
                    size = event.data.get("size", "")
                    _log_event("trade", event.symbol, f"${price} x{size}")
            elif event.kind == "quote":
                if self._verbose:
                    bid = event.data.get("bid", "")
                    ask = event.data.get("ask", "")
                    _log_event("quote", event.symbol, f"bid=${bid} ask=${ask}")
            elif event.kind == "fill":
                self._handle_fill(event)
                if self._verbose:
                    side = event.data.get("side", "")
                    qty = event.data.get("filled_qty", "")
                    price = event.data.get("filled_avg_price", "")
                    _log_event("fill", event.data.get("symbol", ""), f"{side} {qty} @ ${price}")

            self._recorder.flush()

            for symbol in self._recorder.get_anomalies():
                self._reactor.on_volume_anomaly({"symbol": symbol})
                if self._verbose:
                    _log_event("anomaly", symbol, "volume 2x+ baseline")

    def _handle_fill(self, event):
        try:
            self._supabase.push_heartbeat(self._build_heartbeat())
        except Exception as e:
            logger.error("Fill sync failed: %s", e)

    # ── heartbeat ─────────────────────────────────────────────────────────────

    def _heartbeat_loop(self):
        while not self._stop_event.wait(self._interval):
            try:
                self._supabase.push_heartbeat(self._build_heartbeat())
            except Exception as e:
                logger.error("Heartbeat failed: %s", e)

    def _build_heartbeat(self):
        return {
            "status": "running",
            "alpaca_connected": self._stream.is_running,
            "active_positions": len(self._symbols),
            "current_regime": "unknown",
            "next_action": "streaming",
            "dropped_events": self._stream.dropped_events,
        }
