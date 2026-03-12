"""End-to-end tests for Alpaca paper trading integration.

These tests connect to the real Alpaca paper trading API and are gated by
environment variables. They will be skipped unless ALPACA_PAPER_KEY and
ALPACA_PAPER_SECRET are set.
"""

import os
import tempfile
import time
from decimal import Decimal

import pytest

from fund.alpaca_broker import AlpacaBroker, AlpacaConfig
from fund.order_executor import OrderExecutor
from fund.position_sync import PositionSync
from fund.journal import EventJournal

ALPACA_KEY = os.environ.get("ALPACA_PAPER_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_PAPER_SECRET")

pytestmark = pytest.mark.skipif(
    not ALPACA_KEY or not ALPACA_SECRET,
    reason="ALPACA_PAPER_KEY and ALPACA_PAPER_SECRET not set",
)


@pytest.fixture
def broker():
    config = AlpacaConfig(
        api_key=ALPACA_KEY,
        secret_key=ALPACA_SECRET,
        paper=True,
    )
    return AlpacaBroker(config)


@pytest.fixture
def journal_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_connect_and_get_account(broker):
    """Broker connects and returns a valid BrokerAccount."""
    assert broker.is_connected(), "Expected is_connected() to return True with valid credentials"

    account = broker.get_account()
    assert account is not None
    assert isinstance(account.status, str)
    assert len(account.status) > 0
    assert account.cash > Decimal("0"), f"Expected cash > 0, got {account.cash}"
    assert account.equity >= Decimal("0")
    assert account.buying_power >= Decimal("0")


def test_get_positions(broker):
    """get_positions() returns a list (may be empty for a fresh paper account)."""
    positions = broker.get_positions()
    assert isinstance(positions, list)
    # Each position should have the expected fields
    for p in positions:
        assert isinstance(p.symbol, str)
        assert isinstance(p.quantity, Decimal)
        assert isinstance(p.market_value, Decimal)
        assert isinstance(p.avg_entry_price, Decimal)
        assert isinstance(p.current_price, Decimal)
        assert isinstance(p.unrealized_pl, Decimal)
        assert isinstance(p.unrealized_pl_pct, float)


def test_submit_and_cancel_market_order(broker):
    """Submit a market buy for 1 share of SPY, verify order fields, then cancel."""
    order = broker.submit_market_order(symbol="SPY", qty=Decimal("1"), side="buy")

    assert order.id, "Order ID must not be empty"
    assert order.symbol == "SPY"
    assert "buy" in order.side.lower()
    assert order.qty == Decimal("1")
    assert "market" in order.order_type.lower()
    assert order.status, "Order must have a status"

    # Give the exchange a moment to accept the order before cancelling
    time.sleep(1)

    # Refresh order status
    refreshed = broker.get_order(order.id)
    assert refreshed.id == order.id

    # Cancel only if the order is still open (not already filled)
    cancellable_statuses = {"new", "accepted", "pending_new", "held", "partially_filled"}
    if refreshed.status.lower() in cancellable_statuses:
        broker.cancel_order(order.id)
        # Verify it is now cancelled
        time.sleep(1)
        cancelled = broker.get_order(order.id)
        assert "cancel" in cancelled.status.lower(), (
            f"Expected cancelled status, got {cancelled.status}"
        )


def test_full_pipeline(broker, journal_dir):
    """Execute a buy via OrderExecutor, sync positions, verify journal entries, flush EOD."""
    journal = EventJournal(journal_dir=journal_dir)
    executor = OrderExecutor(broker=broker, journal=journal)
    sync = PositionSync(broker=broker, journal=journal)

    account = broker.get_account()
    portfolio_value = account.equity if account.equity > Decimal("0") else account.cash

    # Use a small fixed allocation that results in exactly 1 share
    # We fetch a rough price estimate via a limit-order approach: just use $1 of
    # allocation against a large portfolio_value to get qty=1 share is not
    # guaranteed, so instead call execute_buy with allocation sized to buy 1 share.
    # Approximate SPY price to size the allocation for 1 share.
    # We use a conservative high price so qty rounds down to 1.
    approx_spy_price = Decimal("600")  # conservative upper bound
    target_allocation = float(approx_spy_price / portfolio_value) + 0.001

    result = executor.execute_buy(
        symbol="SPY",
        target_allocation=target_allocation,
        current_price=approx_spy_price,
        portfolio_value=portfolio_value,
    )

    order_submitted = result is not None

    if order_submitted:
        assert result.symbol == "SPY"
        assert result.side == "buy"
        assert result.qty >= Decimal("1")
        assert result.order_id

    # Sync positions regardless of whether order went through
    sync_result = sync.sync()
    assert sync_result is not None
    assert isinstance(sync_result.positions, list)
    assert sync_result.total_value > Decimal("0")
    assert sync_result.cash >= Decimal("0")

    # Journal must have at least the position_sync entry
    entries = journal.today.entries
    assert len(entries) >= 1, "Expected at least one journal entry after sync"

    entry_types = {e.entry_type for e in entries}
    assert "position_sync" in entry_types, f"Expected position_sync entry, got {entry_types}"

    if order_submitted:
        assert "trade_executed" in entry_types, (
            f"Expected trade_executed entry after buy, got {entry_types}"
        )

    # Flush EOD summary
    journal.set_eod_summary(
        regime_summary="e2e test run",
        nav_change_pct=0.0,
    )
    summary_path = journal.flush()
    assert os.path.exists(summary_path), f"Summary file not found: {summary_path}"

    # Cleanup: cancel any open orders we submitted
    if order_submitted and result:
        try:
            order_status = broker.get_order(result.order_id)
            cancellable = {"new", "accepted", "pending_new", "held", "partially_filled"}
            if order_status.status.lower() in cancellable:
                broker.cancel_order(result.order_id)
        except Exception:
            pass  # Best-effort cleanup
