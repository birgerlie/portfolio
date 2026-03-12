"""Investment universe — curated list of max 20 instruments."""
from typing import Dict, List, Optional
from fund.types import Instrument


class InvestmentUniverse:
    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        self._instruments: Dict[str, Instrument] = {}

    @property
    def instruments(self) -> List[Instrument]:
        return list(self._instruments.values())

    @property
    def symbols(self) -> List[str]:
        return list(self._instruments.keys())

    def get(self, symbol: str) -> Optional[Instrument]:
        return self._instruments.get(symbol)

    def add(self, instrument: Instrument) -> None:
        if len(self._instruments) >= self.max_size:
            raise ValueError(f"Universe is full ({self.max_size}). Remove an instrument or drop lowest-voted first.")
        self._instruments[instrument.symbol] = instrument

    def remove(self, symbol: str) -> None:
        self._instruments.pop(symbol, None)

    def vote(self, symbol: str, votes: int) -> None:
        if symbol in self._instruments:
            self._instruments[symbol].votes_for = votes

    def drop_lowest(self) -> Instrument:
        if not self._instruments:
            raise ValueError("Universe is empty")
        lowest = min(self._instruments.values(), key=lambda i: i.votes_for)
        del self._instruments[lowest.symbol]
        return lowest
