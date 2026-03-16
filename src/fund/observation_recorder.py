"""ObservationRecorder: batches price observations and sends them to SiliconDB."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ObservationRecorder:
    """Records market observations and batches them into SiliconDB.

    Args:
        price_cache: Object with a ``get(symbol) -> PriceEntry | None`` method.
            PriceEntry must expose: symbol, price, vwap, trade_count, spread,
            and ``is_stale() -> bool``.
        silicondb_client: SiliconDB client with an ``add_observation(dict)`` method.
        batch_interval: Interval hint (seconds) for callers scheduling ``flush()``.
            ObservationRecorder itself does not schedule — callers drive the loop.
    """

    def __init__(self, price_cache: Any, silicondb_client: Any, batch_interval: float = 1.0) -> None:
        self._price_cache = price_cache
        self._silicondb = silicondb_client
        self.batch_interval = batch_interval

        # Pending symbols to flush (set gives free dedup)
        self.pending_symbols: Set[str] = set()

        # 20-day average daily volume baselines keyed by symbol
        self._volume_baselines: Dict[str, float] = {}

        # Symbols flagged as volume anomalies since last get_anomalies() call
        self._anomalies: List[str] = []

    # ── public API ───────────────────────────────────────────────────────────

    def record_symbol(self, symbol: str) -> None:
        """Mark *symbol* as pending for the next flush.  Deduplicates automatically."""
        self.pending_symbols.add(symbol)

    def flush(self) -> None:
        """Send observations for all pending symbols to SiliconDB, then clear pending.

        Symbols whose cache entry is missing or stale (>30 s old) are silently
        skipped.  SiliconDB errors are caught and logged — never re-raised.
        """
        symbols = list(self.pending_symbols)
        self.pending_symbols.clear()

        for symbol in symbols:
            entry = self._price_cache.get(symbol)
            if entry is None:
                logger.debug("flush: no cache entry for %s, skipping", symbol)
                continue
            if entry.is_stale():
                logger.debug("flush: stale entry for %s, skipping", symbol)
                continue

            observations = self._build_observations(symbol, entry)
            for obs in observations:
                try:
                    self._silicondb.add_observation(obs)
                except Exception as exc:
                    logger.warning("SiliconDB error for %s observation %s: %s", symbol, obs.get("external_id"), exc)

    def set_volume_baseline(self, symbol: str, avg_daily_volume: float) -> None:
        """Set the 20-day average daily volume baseline for *symbol*."""
        self._volume_baselines[symbol] = avg_daily_volume

    def get_anomalies(self) -> List[str]:
        """Return symbols whose trade_count exceeded 2x their baseline during flush.

        Clears the anomaly list on return.
        """
        anomalies = list(self._anomalies)
        self._anomalies.clear()
        return anomalies

    # ── internals ────────────────────────────────────────────────────────────

    def _build_observations(self, symbol: str, entry: Any) -> List[Dict[str, Any]]:
        observations = [
            self._obs(f"{symbol}:price", {"value": entry.price, "symbol": symbol}),
            self._obs(f"{symbol}:vwap", {"value": entry.vwap, "symbol": symbol}),
            self._obs(f"{symbol}:trade_intensity", {"value": entry.trade_count, "symbol": symbol}),
            self._obs(f"{symbol}:spread", {"value": entry.spread, "symbol": symbol}),
        ]

        # Volume anomaly detection
        baseline = self._volume_baselines.get(symbol)
        if baseline is not None and entry.trade_count > baseline * 2:
            observations.append(
                self._obs(
                    f"{symbol}:volume_anomaly",
                    {
                        "value": entry.trade_count,
                        "baseline": baseline,
                        "ratio": entry.trade_count / baseline,
                        "symbol": symbol,
                    },
                )
            )
            if symbol not in self._anomalies:
                self._anomalies.append(symbol)

        return observations

    @staticmethod
    def _obs(external_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "external_id": external_id,
            "confirmed": True,
            "source": "alpaca_stream",
            "metadata": metadata,
        }
