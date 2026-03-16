"""Tempo module — maps SiliconDB thermodynamic temperature to analysis cooldown values."""
from __future__ import annotations

from enum import Enum
from typing import Optional


class ThermoTier(Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    CRITICAL = "critical"

    @classmethod
    def from_temperature(cls, temp: float, cold: float = 0.3, warm: float = 0.6, hot: float = 0.8) -> "ThermoTier":
        if temp < cold:
            return cls.COLD
        elif temp < warm:
            return cls.WARM
        elif temp < hot:
            return cls.HOT
        else:
            return cls.CRITICAL


_COOLDOWN_MAP: dict[ThermoTier, Optional[int]] = {
    ThermoTier.COLD: None,
    ThermoTier.WARM: 30_000,
    ThermoTier.HOT: 10_000,
    ThermoTier.CRITICAL: 5_000,
}


class Tempo:
    def __init__(
        self,
        silicondb_client=None,
        cold_threshold: float = 0.3,
        warm_threshold: float = 0.6,
        hot_threshold: float = 0.8,
    ) -> None:
        self._silicondb_client = silicondb_client
        self._cold_threshold = cold_threshold
        self._warm_threshold = warm_threshold
        self._hot_threshold = hot_threshold
        self._temperature: float = 0.0
        self._tier: ThermoTier = ThermoTier.COLD

    @property
    def current_tier(self) -> ThermoTier:
        return self._tier

    @property
    def temperature(self) -> float:
        return self._temperature

    def update_temperature(self, temp: float) -> bool:
        new_tier = ThermoTier.from_temperature(
            temp,
            cold=self._cold_threshold,
            warm=self._warm_threshold,
            hot=self._hot_threshold,
        )
        self._temperature = temp
        changed = new_tier != self._tier
        self._tier = new_tier
        return changed

    def get_cooldown_ms(self) -> Optional[int]:
        return _COOLDOWN_MAP[self._tier]

    def should_analyze(self) -> bool:
        return self._tier != ThermoTier.COLD
