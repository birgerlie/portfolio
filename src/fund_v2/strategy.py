"""Portfolio optimization strategies — pure math, no ORM dependency."""
from __future__ import annotations
import math


def equal_weights(symbols: list[str], cash_reserve: float = 0.1) -> dict[str, float]:
    """Equal allocation across all symbols."""
    available = 1.0 - cash_reserve
    w = available / max(len(symbols), 1)
    return {s: w for s in symbols}


def belief_weights(
    convictions: dict[str, float],
    cash_reserve: float = 0.1,
) -> dict[str, float]:
    """Allocate proportional to conviction strength."""
    total = sum(convictions.values()) or 1.0
    available = 1.0 - cash_reserve
    return {s: (c / total) * available for s, c in convictions.items()}


def kelly_weights(
    convictions: dict[str, float],
    max_position: float = 0.20,
    cash_reserve: float = 0.1,
) -> dict[str, float]:
    """Simplified Kelly criterion: f = 2p - 1, capped at max_position."""
    raw = {}
    for s, p in convictions.items():
        f = max(0.0, 2 * p - 1)
        raw[s] = min(f, max_position)
    total = sum(raw.values()) or 1.0
    available = 1.0 - cash_reserve
    if total > available:
        scale = available / total
        return {s: w * scale for s, w in raw.items()}
    return raw


def compute_trades(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    portfolio_value: float,
    prices: dict[str, float],
    min_trade_pct: float = 0.02,
) -> list[dict]:
    """Compute trades to move from current to target weights.

    Returns list of {"symbol", "side", "qty", "value"} dicts.
    Sells come before buys.
    """
    trades = []
    all_symbols = set(current_weights) | set(target_weights)
    for symbol in sorted(all_symbols):
        curr = current_weights.get(symbol, 0.0)
        tgt = target_weights.get(symbol, 0.0)
        delta = tgt - curr
        if abs(delta) < min_trade_pct:
            continue
        price = prices.get(symbol, 0)
        if price <= 0:
            continue
        value = abs(delta) * portfolio_value
        qty = int(value / price)
        if qty <= 0:
            continue
        trades.append({
            "symbol": symbol,
            "side": "buy" if delta > 0 else "sell",
            "qty": qty,
            "value": qty * price,
        })
    # Sells first, then buys
    trades.sort(key=lambda t: (0 if t["side"] == "sell" else 1, t["symbol"]))
    return trades
