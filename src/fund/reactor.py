"""Reactor — dispatches percolator rule events to SiliconDB, broker, and Supabase."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

from fund.tempo import Tempo

logger = logging.getLogger(__name__)


@dataclass
class ReactorConfig:
    portfolio_symbols: List[str]
    reference_symbols: List[str] = field(default_factory=list)


class Reactor:
    def __init__(
        self,
        silicondb_client,
        broker,
        supabase_sync,
        price_cache,
        tempo: Tempo,
        config: ReactorConfig,
    ) -> None:
        self._silicondb = silicondb_client
        self._broker = broker
        self._supabase_sync = supabase_sync
        self._price_cache = price_cache
        self._tempo = tempo
        self._config = config
        self._trade_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Nervous tier (observation)
    # ------------------------------------------------------------------

    def on_micro_shift(self, event: dict) -> None:
        symbol = event.get("symbol", "")
        try:
            self._silicondb.propagate(
                external_id=f"{symbol}:return",
                confidence=0.7,
                decay=0.5,
            )
        except Exception:
            logger.exception("on_micro_shift: propagate failed for symbol=%s", symbol)

        try:
            self._silicondb.add_cooccurrences(
                ids=[f"{s}:return" for s in self._config.portfolio_symbols],
                session_id="stream",
            )
        except Exception:
            logger.exception("on_micro_shift: add_cooccurrences failed")

    # ------------------------------------------------------------------
    # Standard tier (analysis)
    # ------------------------------------------------------------------

    def on_significant_shift(self, event: dict) -> None:
        if not self._tempo.should_analyze():
            logger.debug("on_significant_shift: skipped (tempo is cold)")
            return
        try:
            self._silicondb.epistemic_briefing(
                topic="market",
                budget=30,
                anchor_ratio=0.3,
                hops=2,
                neighbor_k=5,
            )
        except Exception:
            logger.exception("on_significant_shift: epistemic_briefing failed")

    def on_thermo_shift(self, event: dict) -> None:
        try:
            prev_tier = self._tempo.current_tier
            changed = self._tempo.update_temperature(event["temperature"])
            if changed:
                logger.info(
                    "on_thermo_shift: tier changed %s -> %s",
                    prev_tier,
                    self._tempo.current_tier,
                )
        except Exception:
            logger.exception("on_thermo_shift: failed to update temperature")

    # ------------------------------------------------------------------
    # Strategic tier (trading)
    # ------------------------------------------------------------------

    def on_regime_change(self, event: dict) -> None:
        try:
            with self._trade_lock:
                for trade in event.get("trades", []):
                    symbol = trade["symbol"]
                    qty = Decimal(str(trade["qty"]))
                    side = trade["side"]
                    try:
                        self._broker.submit_market_order(symbol, qty, side)
                    except Exception:
                        logger.exception(
                            "on_regime_change: submit_market_order failed symbol=%s", symbol
                        )
                try:
                    self._supabase_sync.push_snapshot(event)
                except Exception:
                    logger.exception("on_regime_change: push_snapshot failed")
        except Exception:
            logger.exception("on_regime_change: unexpected error")

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def on_volume_anomaly(self, event: dict) -> None:
        try:
            self._silicondb.record_observation_batch(
                observations=[
                    {
                        "type": "volume_anomaly",
                        **event,
                    }
                ]
            )
        except Exception:
            logger.exception("on_volume_anomaly: record_observation_batch failed")

    def on_lead_lag_discovered(self, event: dict) -> None:
        try:
            self._silicondb.insert_triples(triples=[event])
        except Exception:
            logger.exception("on_lead_lag_discovered: insert_triples failed")
