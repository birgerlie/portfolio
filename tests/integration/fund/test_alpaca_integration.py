"""Integration tests: EventJournal + OrderExecutor + PositionSync working together.

Uses a mocked AlpacaBroker but a REAL EventJournal backed by a temp directory.
"""

import json
import os
import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from fund.alpaca_broker import BrokerOrder, BrokerPosition, BrokerAccount
from fund.journal import EventJournal
from fund.order_executor import OrderExecutor
from fund.position_sync import PositionSync


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_broker_order(order_id: str, symbol: str, side: str, qty: Decimal) -> BrokerOrder:
    return BrokerOrder(
        id=order_id,
        symbol=symbol,
        side=side,
        qty=qty,
        order_type="market",
        limit_price=None,
        status="filled",
        filled_qty=qty,
        filled_avg_price=Decimal("150.00"),
    )


def _make_broker_position(symbol: str, qty: Decimal, price: Decimal) -> BrokerPosition:
    market_value = qty * price
    return BrokerPosition(
        symbol=symbol,
        quantity=qty,
        market_value=market_value,
        avg_entry_price=price,
        current_price=price,
        unrealized_pl=Decimal("0"),
        unrealized_pl_pct=0.0,
    )


def _make_broker_account(cash: Decimal) -> BrokerAccount:
    return BrokerAccount(
        cash=cash,
        equity=cash,
        buying_power=cash,
        status="ACTIVE",
    )


def _read_jsonl(path: str) -> list:
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _journal_path(journal_dir: str) -> str:
    return os.path.join(journal_dir, f"{date.today()}.jsonl")


# ---------------------------------------------------------------------------
# Scenario 1: Full trade cycle
# ---------------------------------------------------------------------------

class TestFullTradeCycle:
    def test_buy_journaled_on_disk_and_position_sync_appended(self):
        """Execute a buy via OrderExecutor, verify JSONL on disk, then sync positions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)

            broker = MagicMock()
            broker.submit_market_order.return_value = _make_broker_order(
                "ord-001", "AAPL", "buy", Decimal("10")
            )
            broker.get_positions.return_value = [
                _make_broker_position("AAPL", Decimal("10"), Decimal("175.00"))
            ]
            broker.get_account.return_value = _make_broker_account(Decimal("82500.00"))

            executor = OrderExecutor(broker=broker, journal=journal)
            sync = PositionSync(broker=broker, journal=journal)

            # Execute a buy
            result = executor.execute_buy(
                symbol="AAPL",
                target_allocation=0.175,
                current_price=Decimal("175.00"),
                portfolio_value=Decimal("100000"),
            )
            assert result is not None
            assert result.symbol == "AAPL"
            assert result.side == "buy"

            # JSONL file must exist with a trade_executed entry
            jsonl = _journal_path(tmpdir)
            assert os.path.exists(jsonl), "JSONL file must be written after buy"
            entries = _read_jsonl(jsonl)
            assert len(entries) == 1
            assert entries[0]["entry_type"] == "trade_executed"
            assert entries[0]["data"]["symbol"] == "AAPL"
            assert entries[0]["data"]["side"] == "buy"

            # Sync positions — must append a position_sync entry
            sync_result = sync.sync()
            assert sync_result.positions_count() == 1 if hasattr(sync_result, "positions_count") else len(sync_result.positions) == 1

            entries = _read_jsonl(jsonl)
            assert len(entries) == 2
            types = [e["entry_type"] for e in entries]
            assert types == ["trade_executed", "position_sync"]

            # In-memory journal must also reflect both entries
            assert len(journal.today.entries) == 2


# ---------------------------------------------------------------------------
# Scenario 2: Sell-then-buy flow
# ---------------------------------------------------------------------------

class TestSellThenBuyFlow:
    def _broker_for_plan(self):
        broker = MagicMock()
        call_count = {"n": 0}

        def submit(symbol=None, qty=None, side=None):
            call_count["n"] += 1
            return _make_broker_order(f"ord-{call_count['n']:03d}", symbol, side, qty)

        broker.submit_market_order.side_effect = submit
        return broker

    def test_all_trades_journaled_sells_before_buys(self):
        """execute_plan should journal sells first, then buys — verify on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)
            broker = self._broker_for_plan()
            executor = OrderExecutor(broker=broker, journal=journal)

            trades = [
                {"symbol": "TSLA", "side": "SELL", "qty": Decimal("5")},
                {"symbol": "MSFT", "side": "SELL", "qty": Decimal("3")},
                {"symbol": "NVDA", "side": "BUY", "allocation": 0.20},
                {"symbol": "AAPL", "side": "BUY", "allocation": 0.15},
            ]
            current_prices = {
                "TSLA": Decimal("200.00"),
                "MSFT": Decimal("380.00"),
                "NVDA": Decimal("850.00"),
                "AAPL": Decimal("175.00"),
            }

            results = executor.execute_plan(
                trades=trades,
                current_prices=current_prices,
                portfolio_value=Decimal("100000"),
            )

            assert len(results) == 4

            # Check on-disk order
            entries = _read_jsonl(_journal_path(tmpdir))
            assert len(entries) == 4, f"Expected 4 journal entries, got {len(entries)}"

            sides = [e["data"]["side"] for e in entries]
            # First two must be sells
            assert sides[0] == "sell", "First journaled trade must be a sell"
            assert sides[1] == "sell", "Second journaled trade must be a sell"
            # Last two must be buys
            assert sides[2] == "buy", "Third journaled trade must be a buy"
            assert sides[3] == "buy", "Fourth journaled trade must be a buy"

            symbols_sold = {e["data"]["symbol"] for e in entries if e["data"]["side"] == "sell"}
            assert symbols_sold == {"TSLA", "MSFT"}

            symbols_bought = {e["data"]["symbol"] for e in entries if e["data"]["side"] == "buy"}
            assert symbols_bought == {"NVDA", "AAPL"}


# ---------------------------------------------------------------------------
# Scenario 3: Journal crash recovery
# ---------------------------------------------------------------------------

class TestJournalCrashRecovery:
    def test_new_journal_instance_recovers_entries_from_disk(self):
        """After crash, a new EventJournal on the same dir must recover entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First session: log two trades
            journal1 = EventJournal(journal_dir=tmpdir)

            broker = MagicMock()
            broker.submit_market_order.return_value = _make_broker_order(
                "ord-001", "GOOG", "buy", Decimal("2")
            )
            executor = OrderExecutor(broker=broker, journal=journal1)

            executor.execute_buy(
                symbol="GOOG",
                target_allocation=0.10,
                current_price=Decimal("140.00"),
                portfolio_value=Decimal("100000"),
            )

            broker.submit_market_order.return_value = _make_broker_order(
                "ord-002", "AMZN", "buy", Decimal("3")
            )
            executor.execute_buy(
                symbol="AMZN",
                target_allocation=0.12,
                current_price=Decimal("180.00"),
                portfolio_value=Decimal("100000"),
            )

            assert len(journal1.today.entries) == 2

            # Simulate crash: create a brand-new journal instance on the same dir
            journal2 = EventJournal(journal_dir=tmpdir)

            recovered = journal2.today.entries
            assert len(recovered) == 2, (
                f"Crash recovery should load 2 entries, got {len(recovered)}"
            )

            recovered_types = [e.entry_type for e in recovered]
            assert all(t == "trade_executed" for t in recovered_types)

            recovered_symbols = {e.data["symbol"] for e in recovered}
            assert recovered_symbols == {"GOOG", "AMZN"}

            # Original entries must have matching order_ids
            original_ids = {e.data["order_id"] for e in journal1.today.entries}
            recovered_ids = {e.data["order_id"] for e in recovered}
            assert original_ids == recovered_ids


# ---------------------------------------------------------------------------
# Scenario 4: EOD flush after trading
# ---------------------------------------------------------------------------

class TestEODFlushAfterTrading:
    def test_flush_summary_has_correct_trades_executed_count(self):
        """After trades + flush, the summary JSON must reflect correct counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = EventJournal(journal_dir=tmpdir)

            broker = MagicMock()
            call_count = {"n": 0}

            def submit(symbol=None, qty=None, side=None):
                call_count["n"] += 1
                return _make_broker_order(f"ord-{call_count['n']:03d}", symbol, side, qty)

            broker.submit_market_order.side_effect = submit
            broker.get_positions.return_value = [
                _make_broker_position("NVDA", Decimal("10"), Decimal("850.00")),
                _make_broker_position("AAPL", Decimal("20"), Decimal("175.00")),
            ]
            broker.get_account.return_value = _make_broker_account(Decimal("64500.00"))

            executor = OrderExecutor(broker=broker, journal=journal)
            sync = PositionSync(broker=broker, journal=journal)

            # Execute two buys
            executor.execute_buy(
                symbol="NVDA",
                target_allocation=0.085,
                current_price=Decimal("850.00"),
                portfolio_value=Decimal("100000"),
            )
            executor.execute_buy(
                symbol="AAPL",
                target_allocation=0.035,
                current_price=Decimal("175.00"),
                portfolio_value=Decimal("100000"),
            )
            # Sync positions once
            sync.sync()

            # Set EOD metadata and flush
            journal.set_eod_summary(
                regime_summary="Bull market, high clarity",
                nav_change_pct=1.5,
                belief_snapshot={"clarity": 0.85},
                thermo_snapshot={"temperature": 0.42},
            )
            summary_path = journal.flush()

            assert os.path.exists(summary_path), "Summary JSON must be written by flush()"

            with open(summary_path) as f:
                summary = json.load(f)

            # Two trade_executed entries
            assert summary["trades_executed"] == 2, (
                f"Expected 2 trades_executed, got {summary['trades_executed']}"
            )

            # All 3 entries present (2 trades + 1 position_sync)
            all_entries = summary["entries"]
            assert len(all_entries) == 3, (
                f"Expected 3 total entries in summary, got {len(all_entries)}"
            )

            entry_types = [e["entry_type"] for e in all_entries]
            assert entry_types.count("trade_executed") == 2
            assert entry_types.count("position_sync") == 1

            # EOD metadata preserved
            assert summary["regime_summary"] == "Bull market, high clarity"
            assert summary["nav_change_pct"] == 1.5

            # JSONL file must be removed after flush
            jsonl = _journal_path(tmpdir)
            assert not os.path.exists(jsonl), "JSONL should be removed after flush()"
