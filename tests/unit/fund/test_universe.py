"""Tests for investment universe — max 20, voting."""
from datetime import date
import pytest
from fund.universe import InvestmentUniverse
from fund.types import Instrument


class TestUniverse:
    def test_add_instrument(self):
        universe = InvestmentUniverse()
        inst = Instrument(symbol="NVDA", name="Nvidia", asset_class="equity",
                          thesis="AI compute leader", proposed_by="Alice", added_date=date(2026, 1, 1))
        universe.add(inst)
        assert len(universe.instruments) == 1
        assert universe.get("NVDA") == inst

    def test_max_20_instruments(self):
        universe = InvestmentUniverse(max_size=20)
        for i in range(20):
            universe.add(Instrument(symbol=f"SYM{i}", name=f"Stock {i}", asset_class="equity",
                                    thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1)))
        assert len(universe.instruments) == 20
        with pytest.raises(ValueError, match="full"):
            universe.add(Instrument(symbol="SYM20", name="Stock 20", asset_class="equity",
                                    thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1)))

    def test_remove_instrument(self):
        universe = InvestmentUniverse()
        universe.add(Instrument(symbol="NVDA", name="Nvidia", asset_class="equity",
                                thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1)))
        universe.remove("NVDA")
        assert len(universe.instruments) == 0

    def test_vote_for_instrument(self):
        universe = InvestmentUniverse()
        universe.add(Instrument(symbol="NVDA", name="Nvidia", asset_class="equity",
                                thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1)))
        universe.vote("NVDA", votes=3)
        assert universe.get("NVDA").votes_for == 3

    def test_drop_lowest_voted(self):
        universe = InvestmentUniverse(max_size=3)
        for i, sym in enumerate(["A", "B", "C"]):
            universe.add(Instrument(symbol=sym, name=sym, asset_class="equity",
                                    thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1), votes_for=i))
        dropped = universe.drop_lowest()
        assert dropped.symbol == "A"
        assert len(universe.instruments) == 2

    def test_symbols_list(self):
        universe = InvestmentUniverse()
        universe.add(Instrument(symbol="NVDA", name="Nvidia", asset_class="equity",
                                thesis="test", proposed_by="Alice", added_date=date(2026, 1, 1)))
        universe.add(Instrument(symbol="AAPL", name="Apple", asset_class="equity",
                                thesis="test", proposed_by="Bob", added_date=date(2026, 1, 1)))
        assert set(universe.symbols) == {"NVDA", "AAPL"}
