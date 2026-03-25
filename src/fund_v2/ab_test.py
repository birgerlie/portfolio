"""A/B test framework — compare signal strategies across historical periods with P&L.

Each strategy is a function that takes beliefs and returns (direction, size).
Tests run the same data through each strategy and measures:
  - Accuracy (% correct direction)
  - Avg win / avg loss size
  - Expected P&L after costs
  - Sharpe ratio

Usage:
    SILICONDB_LIBRARY_PATH=lib/silicondb/.build/release \
    PYTHONPATH=src:lib/silicondb/python \
    python3 -m fund_v2.ab_test
"""

from __future__ import annotations

import logging
import math
import tempfile
import shutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from trading_backtest.data import fetch_historical_data, StockData

logger = logging.getLogger(__name__)


# ── Strategies to compare ────────────────────────────────────────────────────

def strategy_simple(beliefs: Dict[str, float], **ctx) -> Tuple[str, float]:
    """The 70% version: just read fast/slow trend, threshold at 0.5."""
    fast = beliefs.get("price_trend_fast", 0.5)
    slow = beliefs.get("price_trend_slow", 0.5)
    avg = fast * 0.6 + slow * 0.4

    if avg > 0.55:
        return "buy", min(0.10, (avg - 0.5) * 0.5)
    elif avg < 0.45:
        return "sell", min(0.10, (0.5 - avg) * 0.5)
    return "neutral", 0.0


def strategy_energy_gap(beliefs: Dict[str, float], **ctx) -> Tuple[str, float]:
    """Energy gap: signal when beliefs are far from neutral goal (0.5)."""
    fast = beliefs.get("price_trend_fast", 0.5)
    slow = beliefs.get("price_trend_slow", 0.5)
    exh = beliefs.get("exhaustion", 0.2)

    # Energy gap from neutral
    fast_gap = fast - 0.5
    slow_gap = slow - 0.5
    edge = fast_gap * 0.6 + slow_gap * 0.4

    # Exhaustion penalty
    if exh > 0.7:
        edge *= 0.5

    fe = abs(edge)
    cost = ctx.get("cost_bps", 10) / 10000

    if fe < cost * 2:
        return "neutral", 0.0

    direction = "buy" if edge > 0 else "sell"
    size = min(0.10, fe * 0.3)
    return direction, size


def strategy_energy_gap_thermo(beliefs: Dict[str, float], **ctx) -> Tuple[str, float]:
    """Energy gap + thermodynamic filter: only signal when free energy is high."""
    direction, size = strategy_energy_gap(beliefs, **ctx)
    if direction == "neutral":
        return direction, size

    # Thermo filter: boost when node has high free energy
    node_fe = ctx.get("node_free_energy", 0)
    if node_fe > 0.5:
        size *= 1.3  # 30% boost for thermodynamically active instruments
    elif node_fe < 0.1 and size > 0:
        size *= 0.7  # 30% reduction for thermodynamically calm instruments

    return direction, min(0.10, size)


def strategy_energy_gap_accum(beliefs: Dict[str, float], **ctx) -> Tuple[str, float]:
    """Energy gap + accumulator pressure ratio."""
    direction, size = strategy_energy_gap(beliefs, **ctx)

    buy_pressure = ctx.get("buy_pressure", 0.5)
    sell_pressure = ctx.get("sell_pressure", 0.5)
    total = buy_pressure + sell_pressure

    if total < 0.01:
        return direction, size

    ratio = buy_pressure / total

    # Accumulator confirms direction → boost
    if (direction == "buy" and ratio > 0.6) or (direction == "sell" and ratio < 0.4):
        size *= 1.3
    # Accumulator contradicts → reduce
    elif (direction == "buy" and ratio < 0.4) or (direction == "sell" and ratio > 0.6):
        size *= 0.5

    return direction, min(0.10, size)


STRATEGIES = {
    "A_simple": strategy_simple,
    "B_energy_gap": strategy_energy_gap,
    "C_gap_thermo": strategy_energy_gap_thermo,
    "D_gap_accum": strategy_energy_gap_accum,
}


# ── Test periods ─────────────────────────────────────────────────────────────

PERIODS = {
    "svb": ("2023-02-15", "2023-04-15", ["JPM", "BAC", "GS", "AAPL", "MSFT", "NVDA", "SPY", "QQQ"]),
    "rate_hike": ("2022-01-01", "2022-07-01", ["AAPL", "MSFT", "NVDA", "GOOG", "META", "XOM", "SPY", "QQQ"]),
    "rotation": ("2024-07-01", "2024-08-15", ["AAPL", "MSFT", "NVDA", "GOOG", "META", "SPY", "QQQ"]),
    "covid": ("2020-02-15", "2020-04-15", ["AAPL", "MSFT", "AMZN", "GOOG", "JPM", "XOM", "SPY", "QQQ"]),
    "pivot": ("2023-10-15", "2023-12-31", ["AAPL", "MSFT", "NVDA", "GOOG", "META", "SPY", "QQQ"]),
}


# ── Simulation ───────────────────────────────────────────────────────────────

@dataclass
class TradeResult:
    date: Any
    symbol: str
    direction: str
    size: float
    entry_price: float
    exit_price: float
    return_pct: float
    correct: bool


@dataclass
class StrategyResult:
    name: str
    period: str
    trades: List[TradeResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if not self.trades:
            return 0
        return sum(1 for t in self.trades if t.correct) / len(self.trades)

    @property
    def avg_win(self) -> float:
        wins = [t.return_pct for t in self.trades if t.correct]
        return sum(wins) / len(wins) if wins else 0

    @property
    def avg_loss(self) -> float:
        losses = [t.return_pct for t in self.trades if not t.correct]
        return sum(losses) / len(losses) if losses else 0

    @property
    def total_pnl(self) -> float:
        return sum(t.return_pct * t.size for t in self.trades)

    @property
    def sharpe(self) -> float:
        if len(self.trades) < 2:
            return 0
        returns = [t.return_pct * t.size for t in self.trades]
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / len(returns)
        std = math.sqrt(var) if var > 0 else 0.001
        return mean / std * math.sqrt(252)  # annualized

    @property
    def trade_count(self) -> int:
        return len(self.trades)


def simulate_period(
    period_name: str,
    strategy_fn: Callable,
    strategy_name: str,
    cost_bps: float = 10,
    forward_days: int = 5,
) -> StrategyResult:
    """Run a strategy on historical data for one period."""
    start, end, symbols = PERIODS[period_name]
    result = StrategyResult(name=strategy_name, period=period_name)

    # Load data
    data: Dict[str, StockData] = {}
    for sym in symbols:
        try:
            sd = fetch_historical_data(sym, start, end)
            if sd and sd.dates:
                data[sym] = sd
        except Exception:
            pass

    if not data:
        return result

    ref = data.get("SPY", list(data.values())[0])
    n = len(ref.dates)
    lookback = 20

    # Simulate day by day
    for day_idx in range(lookback, n - forward_days):
        for symbol, sd in data.items():
            if day_idx >= len(sd.closes) or day_idx + forward_days >= len(sd.closes):
                continue

            close = sd.closes[day_idx]
            fwd_close = sd.closes[day_idx + forward_days]

            # Compute beliefs from price history
            fast_start = max(0, day_idx - 5)
            fast_ret = (close - sd.closes[fast_start]) / sd.closes[fast_start] if sd.closes[fast_start] > 0 else 0
            fast = max(0, min(1, 0.5 + fast_ret * 10))

            slow_start = max(0, day_idx - lookback)
            slow_ret = (close - sd.closes[slow_start]) / sd.closes[slow_start] if sd.closes[slow_start] > 0 else 0
            slow = max(0, min(1, 0.5 + slow_ret * 5))

            vol = sd.volumes[day_idx] if day_idx < len(sd.volumes) else 0
            avg_vol = sum(sd.volumes[max(0, day_idx - lookback):day_idx + 1]) / max(1, min(lookback, day_idx + 1))
            exh = abs(fast - 0.5) * 2

            beliefs = {
                "price_trend_fast": fast,
                "price_trend_slow": slow,
                "exhaustion": exh,
                "relative_strength": 0.5,
                "pressure": 0.5,
            }

            # Run strategy
            direction, size = strategy_fn(beliefs, cost_bps=cost_bps)

            if direction == "neutral" or size < 0.005:
                continue

            # Measure outcome
            fwd_return = (fwd_close - close) / close
            cost = cost_bps / 10000
            if direction == "sell":
                net_return = -fwd_return - cost  # short: profit when price falls
            else:
                net_return = fwd_return - cost

            result.trades.append(TradeResult(
                date=ref.dates[day_idx],
                symbol=symbol,
                direction=direction,
                size=size,
                entry_price=close,
                exit_price=fwd_close,
                return_pct=net_return,
                correct=net_return > 0,
            ))

    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def run_ab_test():
    """Run all strategies across all periods and compare."""
    print("=" * 80)
    print("  A/B TEST — Strategy Comparison Across 5 Market Regimes")
    print("  Measuring: Accuracy, Avg Win, Avg Loss, P&L, Sharpe")
    print("  Cost assumption: 10 bps round-trip")
    print("=" * 80)

    all_results: Dict[str, List[StrategyResult]] = {name: [] for name in STRATEGIES}

    for period_name in PERIODS:
        print(f"\n{'─'*60}")
        print(f"  Period: {period_name}")
        print(f"{'─'*60}")

        for strat_name, strat_fn in STRATEGIES.items():
            result = simulate_period(period_name, strat_fn, strat_name)
            all_results[strat_name].append(result)

            if result.trade_count > 0:
                print(
                    f"  {strat_name:<20} "
                    f"acc={result.accuracy:>5.1%}  "
                    f"trades={result.trade_count:>4}  "
                    f"avg_win={result.avg_win:>+6.2%}  "
                    f"avg_loss={result.avg_loss:>+6.2%}  "
                    f"pnl={result.total_pnl:>+7.4f}  "
                    f"sharpe={result.sharpe:>5.2f}"
                )
            else:
                print(f"  {strat_name:<20} no trades")

    # Summary
    print(f"\n{'='*80}")
    print("  SUMMARY — Aggregated Across All Periods")
    print(f"{'='*80}")
    print(f"  {'Strategy':<20} {'Accuracy':>8} {'Trades':>7} {'Avg Win':>8} {'Avg Loss':>9} {'Total PnL':>10} {'Sharpe':>7}")
    print(f"  {'-'*70}")

    for strat_name, results in all_results.items():
        all_trades = [t for r in results for t in r.trades]
        if not all_trades:
            print(f"  {strat_name:<20} no trades")
            continue

        accuracy = sum(1 for t in all_trades if t.correct) / len(all_trades)
        wins = [t.return_pct for t in all_trades if t.correct]
        losses = [t.return_pct for t in all_trades if not t.correct]
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        total_pnl = sum(t.return_pct * t.size for t in all_trades)

        returns = [t.return_pct * t.size for t in all_trades]
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        sharpe = mean_r / max(math.sqrt(var_r), 0.0001) * math.sqrt(252)

        winner = "  ◀ BEST" if total_pnl == max(
            sum(t.return_pct * t.size for r in v for t in r.trades)
            for v in all_results.values() if any(r.trades for r in v)
        ) else ""

        print(
            f"  {strat_name:<20} {accuracy:>7.1%} {len(all_trades):>7} "
            f"{avg_win:>+7.2%} {avg_loss:>+8.2%} {total_pnl:>+9.4f} {sharpe:>7.2f}{winner}"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_ab_test()
