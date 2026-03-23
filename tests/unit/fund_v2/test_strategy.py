"""Portfolio optimization — pure math, no ORM dependency."""
import pytest

from fund_v2.strategy import kelly_weights, equal_weights, belief_weights, compute_trades


def test_equal_weights_distributes_evenly():
    symbols = ["AAPL", "NVDA", "MSFT"]
    weights = equal_weights(symbols, cash_reserve=0.1)
    assert len(weights) == 3
    assert sum(weights.values()) == pytest.approx(0.9, abs=0.01)
    assert all(w == pytest.approx(0.3, abs=0.01) for w in weights.values())


def test_belief_weights_scales_by_conviction():
    convictions = {"AAPL": 0.8, "NVDA": 0.4, "MSFT": 0.6}
    weights = belief_weights(convictions, cash_reserve=0.1)
    assert weights["AAPL"] > weights["MSFT"] > weights["NVDA"]
    assert sum(weights.values()) == pytest.approx(0.9, abs=0.01)


def test_kelly_weights_respects_max_position():
    convictions = {"AAPL": 0.95}
    weights = kelly_weights(convictions, max_position=0.20, cash_reserve=0.1)
    assert weights["AAPL"] <= 0.20


def test_compute_trades_generates_buys_and_sells():
    current = {"AAPL": 0.30, "NVDA": 0.20}
    target = {"AAPL": 0.15, "NVDA": 0.35}
    trades = compute_trades(current, target, portfolio_value=100000, prices={"AAPL": 150, "NVDA": 500})
    sells = [t for t in trades if t["side"] == "sell"]
    buys = [t for t in trades if t["side"] == "buy"]
    assert len(sells) == 1 and sells[0]["symbol"] == "AAPL"
    assert len(buys) == 1 and buys[0]["symbol"] == "NVDA"


def test_compute_trades_skips_tiny_changes():
    current = {"AAPL": 0.20}
    target = {"AAPL": 0.201}
    trades = compute_trades(current, target, portfolio_value=100000, prices={"AAPL": 150}, min_trade_pct=0.02)
    assert trades == []
