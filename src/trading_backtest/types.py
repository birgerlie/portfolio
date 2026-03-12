"""Data types for trading backtest module."""

from dataclasses import dataclass
from enum import Enum
from typing import List
from datetime import date


class SourceCredibility(Enum):
    """Credibility levels for data sources."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class StockData:
    """OHLCV data for a stock."""

    symbol: str
    dates: List[date]
    opens: List[float]
    highs: List[float]
    lows: List[float]
    closes: List[float]
    volumes: List[int]
    source: SourceCredibility = SourceCredibility.HIGH
