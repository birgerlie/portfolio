"""AlpacaStreamService: manages two Alpaca websocket connections in a background thread."""

import asyncio
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

from alpaca.data.enums import DataFeed
from alpaca.data.live.crypto import CryptoDataStream
from alpaca.data.live.stock import StockDataStream
from alpaca.trading.stream import TradingStream

from fund.broker_types import AlpacaConfig, StreamConfig
from fund.price_cache import PriceCache


@dataclass
class StreamEvent:
    """An event emitted by the stream service to the engine thread."""

    kind: str  # "trade", "quote", "fill"
    symbol: str
    data: dict
    timestamp: float = field(default_factory=time.time)


class AlpacaStreamService:
    """Manages StockDataStream and TradingStream in a background async thread.

    Updates a PriceCache on every tick and posts StreamEvents to a queue.Queue
    for the synchronous engine thread to consume.
    """

    def __init__(
        self,
        alpaca_config: AlpacaConfig,
        stream_config: StreamConfig,
        price_cache: PriceCache,
        event_queue: queue.Queue,
    ) -> None:
        self._alpaca_config = alpaca_config
        self._stream_config = stream_config
        self._price_cache = price_cache
        self._event_queue = event_queue

        self._extra_symbols: list[str] = []
        self._lock = threading.Lock()

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

        self.dropped_events: int = 0

        # Stream objects created in background thread
        self._stock_stream: Optional[StockDataStream] = None
        self._trading_stream: Optional[TradingStream] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def all_stream_symbols(self) -> list[str]:
        with self._lock:
            base = list(self._stream_config.all_stream_symbols)
            extra = list(self._extra_symbols)
        combined = sorted(set(base + extra))
        return combined

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe_symbol(self, symbol: str) -> None:
        """Add a symbol to the stream at runtime."""
        with self._lock:
            if symbol not in self._extra_symbols:
                self._extra_symbols.append(symbol)

    def start(self) -> None:
        """Launch background thread with its own asyncio event loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="AlpacaStreamThread")
        self._thread.start()

    def stop(self) -> None:
        """Stop the event loop and join the background thread."""
        if not self._running:
            return
        self._running = False
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # ------------------------------------------------------------------
    # Event handlers (called from async context, must be thread-safe)
    # ------------------------------------------------------------------

    async def _handle_trade(self, trade) -> None:
        self._handle_trade_sync(trade)

    async def _handle_quote(self, quote) -> None:
        self._handle_quote_sync(quote)

    async def _handle_fill(self, data) -> None:
        self._handle_fill_sync(data)

    def _handle_trade_sync(self, trade) -> None:
        """Update PriceCache with trade data and post StreamEvent to queue."""
        symbol = trade.symbol
        price = Decimal(str(trade.price))
        size = Decimal(str(trade.size))
        timestamp = trade.timestamp

        self._price_cache.update_trade(symbol, price, size, timestamp)

        event = StreamEvent(
            kind="trade",
            symbol=symbol,
            data={
                "price": float(price),
                "size": float(size),
                "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
            },
        )
        self._post_event(event)

    def _handle_quote_sync(self, quote) -> None:
        """Update PriceCache with quote data and post StreamEvent to queue."""
        symbol = quote.symbol
        bid = Decimal(str(quote.bid_price))
        ask = Decimal(str(quote.ask_price))
        timestamp = quote.timestamp

        self._price_cache.update_quote(symbol, bid, ask, timestamp)

        event = StreamEvent(
            kind="quote",
            symbol=symbol,
            data={
                "bid": float(bid),
                "ask": float(ask),
                "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
            },
        )
        self._post_event(event)

    def _handle_fill_sync(self, data) -> None:
        """Post StreamEvent(kind='fill') to queue."""
        symbol = getattr(data, "symbol", None) or data.get("symbol", "")
        event = StreamEvent(
            kind="fill",
            symbol=symbol,
            data=data if isinstance(data, dict) else vars(data),
        )
        self._post_event(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post_event(self, event: StreamEvent) -> None:
        """Post event to queue. If full, increment dropped_events."""
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            self.dropped_events += 1

    def _run_loop(self) -> None:
        """Entry point for background thread: creates event loop and runs streams."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._stream_main())
        except RuntimeError as exc:
            # "Event loop stopped before Future completed." is expected when
            # stop() calls loop.stop() externally to shut down the service.
            if "Event loop stopped before Future completed" not in str(exc):
                raise
        finally:
            self._loop.close()
            self._loop = None

    async def _stream_main(self) -> None:
        """Set up and run Alpaca stock, crypto, and trading streams."""
        # Alpaca IEX limits to ~400 symbols. Prioritize: portfolio > reference > macro > tracked
        MAX_STOCK_SYMBOLS = 200  # Alpaca IEX limit ~405 total subscriptions
        all_syms = self.all_stream_symbols
        if len(all_syms) > MAX_STOCK_SYMBOLS:
            # Keep priority symbols, fill rest from tracked
            priority = sorted(set(
                self._stream_config.portfolio_symbols +
                self._stream_config.reference_symbols +
                self._stream_config.macro_proxies
            ))
            remaining_slots = MAX_STOCK_SYMBOLS - len(priority)
            tracked = [s for s in self._stream_config.tracked_symbols if s not in priority]
            symbols = priority + tracked[:remaining_slots]
            logger.info("Capped stock symbols to %d (priority=%d, tracked=%d/%d)",
                        len(symbols), len(priority), min(remaining_slots, len(tracked)), len(tracked))
        else:
            symbols = all_syms
        crypto_symbols = self._stream_config.all_crypto

        self._stock_stream = StockDataStream(
            api_key=self._alpaca_config.api_key,
            secret_key=self._alpaca_config.secret_key,
            feed=DataFeed(self._stream_config.data_feed),
        )
        self._trading_stream = TradingStream(
            api_key=self._alpaca_config.api_key,
            secret_key=self._alpaca_config.secret_key,
            paper=self._alpaca_config.paper,
        )

        if symbols:
            # Subscribe trades for all symbols, quotes only for priority (portfolio+reference+macro)
            # This halves the subscription count for tracked symbols
            self._stock_stream.subscribe_trades(self._handle_trade, *symbols)
            priority = sorted(set(
                self._stream_config.portfolio_symbols +
                self._stream_config.reference_symbols +
                self._stream_config.macro_proxies
            ))
            if priority:
                self._stock_stream.subscribe_quotes(self._handle_quote, *priority)
            logger.info("Subscribed: %d trade streams, %d quote streams", len(symbols), len(priority))

        self._trading_stream.subscribe_trade_updates(self._handle_fill)

        # Crypto stream (24/7, separate websocket)
        streams = [
            self._stock_stream._run_forever(),
            self._trading_stream._run_forever(),
        ]

        if crypto_symbols:
            self._crypto_stream = CryptoDataStream(
                api_key=self._alpaca_config.api_key,
                secret_key=self._alpaca_config.secret_key,
            )
            self._crypto_stream.subscribe_trades(self._handle_trade, *crypto_symbols)
            self._crypto_stream.subscribe_quotes(self._handle_quote, *crypto_symbols)
            streams.append(self._crypto_stream._run_forever())

        await asyncio.gather(*streams, return_exceptions=True)
