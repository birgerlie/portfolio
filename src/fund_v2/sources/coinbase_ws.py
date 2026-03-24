"""Coinbase WebSocket feed — free, no API key, thousands of trades/minute.

Connects to Coinbase Exchange WebSocket and pushes trade events into a queue
in the same format as AlpacaStreamService for compatibility.

Usage:
    feed = CoinbaseWebSocket(symbols=["BTC-USD", "ETH-USD", "SOL-USD"])
    feed.start(event_queue)
    # events appear in queue as StreamEvent(kind="trade", symbol="BTCUSD", data={...})
    feed.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, List, Optional

import websockets

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-feed.exchange.coinbase.com"


@dataclass
class StreamEvent:
    """Compatible with fund.stream_service.StreamEvent."""
    kind: str
    symbol: str
    data: dict
    timestamp: float


class CoinbaseWebSocket:
    """Free real-time trade feed from Coinbase Exchange.

    No API key needed. BTC-USD alone generates 1000+ trades/minute.
    """

    def __init__(self, symbols: List[str]):
        # Coinbase uses "BTC-USD" format
        self._symbols = symbols
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._queue: Optional[queue.Queue] = None
        self.trade_count = 0
        self.dropped_events = 0
        self.is_running = False

    def start(self, event_queue: queue.Queue):
        """Start consuming trades in a background thread."""
        self._queue = event_queue
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="coinbase-ws")
        self._thread.start()
        self.is_running = True
        logger.info("Coinbase WebSocket started for %s", self._symbols)

    def stop(self):
        """Stop the WebSocket connection."""
        self._stop_event.set()
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Coinbase WebSocket stopped. %d trades received.", self.trade_count)

    def _run(self):
        """Thread entry point — runs async event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._connect())
        except Exception as e:
            logger.error("Coinbase WebSocket error: %s", e)
        finally:
            loop.close()

    async def _connect(self):
        """Connect and subscribe to trade channels."""
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(WS_URL, ping_interval=30) as ws:
                    # Subscribe to matches (trades) for our symbols
                    subscribe = {
                        "type": "subscribe",
                        "product_ids": self._symbols,
                        "channels": ["matches"],
                    }
                    await ws.send(json.dumps(subscribe))
                    logger.info("Subscribed to %s on Coinbase", self._symbols)

                    while not self._stop_event.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        except asyncio.TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            logger.warning("Coinbase WebSocket connection closed, reconnecting...")
                            break

                        try:
                            msg = json.loads(raw)
                            if msg.get("type") == "match" or msg.get("type") == "last_match":
                                self._handle_trade(msg)
                        except Exception as e:
                            logger.debug("Parse error: %s", e)

            except Exception as e:
                if not self._stop_event.is_set():
                    logger.warning("Coinbase WebSocket connection failed: %s, retrying in 5s", e)
                    await asyncio.sleep(5)

    def _handle_trade(self, msg: dict):
        """Convert Coinbase trade to StreamEvent and push to queue."""
        product_id = msg.get("product_id", "")  # "BTC-USD"
        symbol = product_id.replace("-", "")      # "BTCUSD"

        price = float(msg.get("price", 0))
        size = float(msg.get("size", 0))
        side = msg.get("side", "")  # "buy" or "sell"
        trade_id = msg.get("trade_id", "")
        ts = msg.get("time", "")

        event = StreamEvent(
            kind="trade",
            symbol=symbol,
            data={
                "price": price,
                "size": size,
                "side": side,
                "trade_id": trade_id,
                "time": ts,
            },
            timestamp=time.time(),
        )

        if self._queue is not None:
            try:
                self._queue.put_nowait(event)
                self.trade_count += 1
            except queue.Full:
                self.dropped_events += 1

        if self.trade_count % 1000 == 0 and self.trade_count > 0:
            logger.info("Coinbase: %d trades received (%d dropped)", self.trade_count, self.dropped_events)
