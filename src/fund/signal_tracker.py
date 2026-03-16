"""Belief graph signal detection for non-portfolio symbols."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    symbol: str
    signal_strength: float
    entropy: float
    node_temperature: float
    belief_type: str
    conviction: float
    first_seen: datetime
    last_seen: datetime
    status: str = "active"  # "active" or "decayed"


class SignalTracker:
    """Detect and track conviction signals from the SiliconDB belief graph."""

    def __init__(self, silicondb_client: Any, portfolio_symbols: List[str]) -> None:
        self._silicondb = silicondb_client
        self._portfolio_symbols: set = set(portfolio_symbols)
        self._signals: Dict[str, Signal] = {}
        self._decayed_since_last_update: List[str] = []
        self._history: Dict[str, List[dict]] = {}

    # ── public API ──────────────────────────────────────────────────────────

    def update(self, all_symbols: List[str]) -> List[Signal]:
        """Query SiliconDB and return NEW signals detected this cycle."""
        self._decayed_since_last_update = []
        new_signals: List[Signal] = []

        # Step 1: fetch uncertain symbols (high entropy / noisy)
        try:
            uncertain_set: set = set(
                self._silicondb.get_uncertain_beliefs(min_entropy=0.5, k=200)
            )
        except Exception as exc:
            logger.warning("SignalTracker: get_uncertain_beliefs failed: %s", exc)
            uncertain_set = set()

        for symbol in all_symbols:
            # Skip portfolio holdings and crypto pairs
            if symbol in self._portfolio_symbols or "/" in symbol:
                continue

            if symbol in uncertain_set:
                # High entropy → noise; decay any existing signal
                if symbol in self._signals and self._signals[symbol].status == "active":
                    self._signals[symbol].status = "decayed"
                    self._decayed_since_last_update.append(symbol)
                continue

            # Low entropy → conviction forming
            entropy = 0.2

            # Get node temperature
            try:
                node_temperature: float = self._silicondb.node_thermo(f"{symbol}:return")
            except Exception as exc:
                logger.warning("SignalTracker: node_thermo(%s) failed: %s", symbol, exc)
                node_temperature = 0.0

            signal_strength = (1.0 - entropy) * max(node_temperature, 0.01)

            if signal_strength > 0.1:
                now = datetime.utcnow()
                conviction = signal_strength  # use strength as conviction proxy

                if symbol in self._signals:
                    sig = self._signals[symbol]
                    is_new = sig.status == "decayed"
                    sig.signal_strength = signal_strength
                    sig.entropy = entropy
                    sig.node_temperature = node_temperature
                    sig.conviction = conviction
                    sig.last_seen = now
                    sig.status = "active"
                    if is_new:
                        sig.first_seen = now
                        new_signals.append(sig)
                else:
                    sig = Signal(
                        symbol=symbol,
                        signal_strength=signal_strength,
                        entropy=entropy,
                        node_temperature=node_temperature,
                        belief_type="conviction",
                        conviction=conviction,
                        first_seen=now,
                        last_seen=now,
                        status="active",
                    )
                    self._signals[symbol] = sig
                    new_signals.append(sig)

                # Track history
                if symbol not in self._history:
                    self._history[symbol] = []
                self._history[symbol].append(
                    {
                        "time": now,
                        "strength": signal_strength,
                        "entropy": entropy,
                        "temperature": node_temperature,
                    }
                )

        return new_signals

    def get_signals(self) -> List[Signal]:
        """Return active signals ranked by strength (descending)."""
        active = [s for s in self._signals.values() if s.status == "active"]
        return sorted(active, key=lambda s: s.signal_strength, reverse=True)

    def get_decayed(self) -> List[str]:
        """Return symbols that decayed since last update."""
        return list(self._decayed_since_last_update)

    def get_signal_history(self, symbol: str) -> List[dict]:
        """Return conviction trajectory for a symbol."""
        return list(self._history.get(symbol, []))
