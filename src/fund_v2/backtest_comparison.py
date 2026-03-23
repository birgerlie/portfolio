"""V1 vs V2 signal comparison on historical data.

Downloads OHLCV for a set of symbols over a specific period,
feeds day-by-day into both engines, and compares:
  1. When each version first detected regime/sector shifts
  2. Signal accuracy (did the price move in the signaled direction?)
  3. Graph propagation value (did v2 flag things before v1?)

Usage:
    python -m fund_v2.backtest_comparison --period svb
    python -m fund_v2.backtest_comparison --period rate_hike
    python -m fund_v2.backtest_comparison --period rotation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from trading_backtest.data import fetch_historical_data, StockData

logger = logging.getLogger(__name__)


# ── Test periods ─────────────────────────────────────────────────────────────

@dataclass
class TestPeriod:
    name: str
    start: str          # YYYY-MM-DD
    end: str
    description: str
    key_event_date: str  # when the event happened
    propagation_path: str  # what v2 should catch
    symbols: List[str] = field(default_factory=list)
    macro_proxies: List[str] = field(default_factory=list)


PERIODS = {
    "svb": TestPeriod(
        name="SVB Crisis",
        start="2023-02-15",
        end="2023-04-15",
        description="SVB collapse → regional bank contagion → flight to safety",
        key_event_date="2023-03-09",
        propagation_path="SVB → KRE (regional banks) → XLF (financials) → tech rally",
        symbols=["JPM", "BAC", "GS", "MS", "WFC", "C",      # big banks
                 "AAPL", "MSFT", "NVDA", "GOOG", "META",      # tech (beneficiary)
                 "XLF", "KRE",                                  # financial ETFs
                 "SPY", "QQQ"],                                  # benchmarks
        macro_proxies=["TLT", "UVXY", "GLD", "IWM"],
    ),
    "rate_hike": TestPeriod(
        name="Rate Hike Cycle",
        start="2022-01-01",
        end="2022-07-01",
        description="Fed hawkish pivot → tech selloff → energy outperformance",
        key_event_date="2022-01-05",
        propagation_path="TLT drops → interest_rates:rising → pressures technology → QQQ drops",
        symbols=["AAPL", "MSFT", "NVDA", "GOOG", "META", "AMZN",  # tech (victims)
                 "XOM", "CVX", "COP",                                # energy (beneficiaries)
                 "SPY", "QQQ"],
        macro_proxies=["TLT", "USO", "UUP", "UVXY", "GLD", "IWM"],
    ),
    "rotation": TestPeriod(
        name="Great Rotation",
        start="2024-07-01",
        end="2024-08-15",
        description="Mega-cap → small-cap rotation after soft CPI",
        key_event_date="2024-07-11",
        propagation_path="IWM surges, QQQ stalls → relative_strength diverges",
        symbols=["AAPL", "MSFT", "NVDA", "GOOG", "META", "AMZN",  # mega-cap
                 "SPY", "QQQ"],
        macro_proxies=["TLT", "IWM", "UVXY", "UUP"],
    ),
    "covid": TestPeriod(
        name="COVID Crash",
        start="2020-02-15",
        end="2020-04-15",
        description="Market crash → V-shaped recovery",
        key_event_date="2020-03-16",
        propagation_path="UVXY spikes → market_fear → all sectors pressured → exhaustion → recovery",
        symbols=["AAPL", "MSFT", "AMZN", "GOOG",
                 "JPM", "BAC",
                 "XOM", "CVX",
                 "SPY", "QQQ"],
        macro_proxies=["TLT", "USO", "UVXY", "GLD", "IWM"],
    ),
    "pivot": TestPeriod(
        name="Fed Pivot Rally",
        start="2023-10-15",
        end="2023-12-31",
        description="Treasury yield peaks, reverses → risk-on rally",
        key_event_date="2023-10-27",
        propagation_path="TLT reverses → interest_rates pressure eases → tech rips",
        symbols=["AAPL", "MSFT", "NVDA", "GOOG", "META", "AMZN",
                 "SPY", "QQQ"],
        macro_proxies=["TLT", "UVXY", "GLD", "IWM", "UUP"],
    ),
}


# ── Data loading ─────────────────────────────────────────────────────────────

def load_period_data(period: TestPeriod) -> Dict[str, StockData]:
    """Download OHLCV for all symbols in a test period."""
    all_symbols = list(set(period.symbols + period.macro_proxies))
    data = {}
    for symbol in sorted(all_symbols):
        try:
            sd = fetch_historical_data(symbol, period.start, period.end)
            if sd and sd.dates:
                data[symbol] = sd
                logger.info("Loaded %s: %d days", symbol, len(sd.dates))
            else:
                logger.warning("No data for %s", symbol)
        except Exception as e:
            logger.warning("Failed to load %s: %s", symbol, e)
    return data


# ── V2 Signal Engine (offline) ───────────────────────────────────────────────

@dataclass
class DailySignal:
    date: date
    symbol: str
    direction: str       # "long" or "short"
    edge: float
    confidence: float
    layer: str           # which layer triggered: "momentum", "pressure", "sentiment", etc.


@dataclass
class DetectionEvent:
    date: date
    event_type: str      # "regime_shift", "sector_pressure", "exhaustion", etc.
    description: str
    days_before_price: int = 0  # how many days before price confirmed


def compute_daily_beliefs(
    data: Dict[str, StockData],
    day_idx: int,
    lookback: int = 20,
) -> Dict[str, Dict[str, float]]:
    """Compute layered beliefs for each symbol on a given day.

    Uses simple price-derived heuristics (no actual SiliconDB needed):
      - price_trend_fast: 5-day return normalized to [0, 1]
      - price_trend_slow: 20-day return normalized to [0, 1]
      - volume_normal: volume / 20-day avg volume, capped at [0, 1]
      - relative_strength: computed per sector after all symbols processed
      - exhaustion: RSI-like, how close to 0 or 1 the fast trend is
    """
    beliefs = {}

    for symbol, sd in data.items():
        if day_idx >= len(sd.closes):
            continue

        close = sd.closes[day_idx]

        # Fast momentum: 5-day return
        fast_start = max(0, day_idx - 5)
        fast_ret = (close - sd.closes[fast_start]) / sd.closes[fast_start] if sd.closes[fast_start] > 0 else 0
        price_trend_fast = max(0.0, min(1.0, 0.5 + fast_ret * 10))  # scale: 10% move = full range

        # Slow momentum: 20-day return
        slow_start = max(0, day_idx - lookback)
        slow_ret = (close - sd.closes[slow_start]) / sd.closes[slow_start] if sd.closes[slow_start] > 0 else 0
        price_trend_slow = max(0.0, min(1.0, 0.5 + slow_ret * 5))

        # Volume relative to 20-day average
        vol = sd.volumes[day_idx] if day_idx < len(sd.volumes) else 0
        avg_vol = sum(sd.volumes[max(0, day_idx - lookback):day_idx + 1]) / max(1, min(lookback, day_idx + 1))
        volume_normal = max(0.0, min(1.0, vol / avg_vol)) if avg_vol > 0 else 0.5

        # Exhaustion: how extreme is the fast trend
        exhaustion = abs(price_trend_fast - 0.5) * 2  # 0 = neutral, 1 = extreme

        beliefs[symbol] = {
            "price_trend_fast": round(price_trend_fast, 4),
            "price_trend_slow": round(price_trend_slow, 4),
            "volume_normal": round(volume_normal, 4),
            "exhaustion": round(exhaustion, 4),
            "close": close,
        }

    # Compute relative strength (vs all symbols — simplified, no sector grouping)
    slow_trends = [b["price_trend_slow"] for b in beliefs.values()]
    avg_slow = sum(slow_trends) / len(slow_trends) if slow_trends else 0.5
    for symbol, b in beliefs.items():
        b["relative_strength"] = round(max(0.0, min(1.0, 0.5 + (b["price_trend_slow"] - avg_slow))), 4)

    return beliefs


def compute_macro_pressure(
    data: Dict[str, StockData],
    day_idx: int,
    macro_proxies: List[str],
) -> Dict[str, float]:
    """Compute macro pressure signals from proxy instruments.

    Returns pressure scores: >0.5 = headwind, <0.5 = tailwind.
    """
    pressures = {}
    for proxy in macro_proxies:
        if proxy not in data or day_idx >= len(data[proxy].closes):
            continue
        sd = data[proxy]
        close = sd.closes[day_idx]
        prev = sd.closes[max(0, day_idx - 5)]
        ret_5d = (close - prev) / prev if prev > 0 else 0

        if proxy == "TLT":
            # TLT falling = rates rising = pressure on tech
            pressures["interest_rate_pressure"] = max(0.0, min(1.0, 0.5 - ret_5d * 10))
        elif proxy == "UVXY":
            # UVXY rising = fear rising = pressure on risk assets
            pressures["fear_pressure"] = max(0.0, min(1.0, 0.5 + ret_5d * 5))
        elif proxy == "USO":
            # USO rising = energy benefits, industrials pressured
            pressures["oil_pressure"] = max(0.0, min(1.0, 0.5 + ret_5d * 5))
        elif proxy == "IWM":
            # IWM vs SPY divergence = rotation signal
            if "SPY" in data and day_idx < len(data["SPY"].closes):
                spy_ret = (data["SPY"].closes[day_idx] - data["SPY"].closes[max(0, day_idx - 5)]) / data["SPY"].closes[max(0, day_idx - 5)]
                pressures["rotation_signal"] = max(0.0, min(1.0, 0.5 + (ret_5d - spy_ret) * 10))
        elif proxy == "GLD":
            # GLD rising = safety bid = risk-off signal
            pressures["safety_bid"] = max(0.0, min(1.0, 0.5 + ret_5d * 5))

    return pressures


def run_v2_signals(
    data: Dict[str, StockData],
    period: TestPeriod,
) -> Tuple[List[DailySignal], List[DetectionEvent]]:
    """Run v2-style layered signal generation on historical data.

    This simulates what the ORM + hooks + predictions would do,
    using the same belief computation logic but offline.
    """
    signals: List[DailySignal] = []
    events: List[DetectionEvent] = []

    if not data:
        return signals, events

    # Get trading days from SPY (most complete)
    ref_symbol = "SPY" if "SPY" in data else list(data.keys())[0]
    n_days = len(data[ref_symbol].dates)

    prev_beliefs: Dict[str, Dict[str, float]] = {}
    prev_pressures: Dict[str, float] = {}

    for day_idx in range(20, n_days):  # skip first 20 days for lookback
        today = data[ref_symbol].dates[day_idx]
        beliefs = compute_daily_beliefs(data, day_idx)
        pressures = compute_macro_pressure(data, day_idx, period.macro_proxies)

        # Detect regime shifts from macro pressure changes
        for pressure_name, value in pressures.items():
            prev_value = prev_pressures.get(pressure_name, 0.5)
            delta = value - prev_value
            if abs(delta) > 0.15:
                events.append(DetectionEvent(
                    date=today,
                    event_type="macro_pressure_shift",
                    description=f"{pressure_name}: {prev_value:.2f} → {value:.2f} (delta={delta:+.2f})",
                ))

        # Detect relative strength shifts
        for symbol, b in beliefs.items():
            if symbol in period.macro_proxies:
                continue
            prev = prev_beliefs.get(symbol, {})
            prev_rs = prev.get("relative_strength", 0.5)
            curr_rs = b["relative_strength"]

            # Relative strength flip
            if prev_rs > 0.5 > curr_rs or prev_rs < 0.5 < curr_rs:
                events.append(DetectionEvent(
                    date=today,
                    event_type="relative_strength_flip",
                    description=f"{symbol}: relative_strength flipped {prev_rs:.2f} → {curr_rs:.2f}",
                ))

            # Exhaustion signal
            if b["exhaustion"] > 0.7 and prev.get("exhaustion", 0) <= 0.7:
                events.append(DetectionEvent(
                    date=today,
                    event_type="exhaustion_signal",
                    description=f"{symbol}: exhaustion crossed 0.7 ({b['exhaustion']:.2f})",
                ))

            # Generate entry/exit signals
            # V2 logic: relative_strength + pressure + exhaustion
            momentum_score = (curr_rs - 0.5) * 2
            pressure_adj = sum(pressures.values()) / max(len(pressures), 1) - 0.5
            exhaustion_penalty = b["exhaustion"] * 0.3 if b["exhaustion"] > 0.5 else 0

            edge = momentum_score - pressure_adj * 0.4 - exhaustion_penalty
            edge = max(-1.0, min(1.0, edge))

            if abs(edge) > 0.15:
                signals.append(DailySignal(
                    date=today,
                    symbol=symbol,
                    direction="long" if edge > 0 else "short",
                    edge=round(edge, 4),
                    confidence=round(min(1.0, abs(edge) * 1.5), 4),
                    layer="momentum+pressure" if abs(pressure_adj) > 0.1 else "momentum",
                ))

        prev_beliefs = beliefs
        prev_pressures = pressures

    return signals, events


# ── V1 Signal Engine (offline) ───────────────────────────────────────────────

def run_v1_signals(
    data: Dict[str, StockData],
    period: TestPeriod,
) -> Tuple[List[DailySignal], List[DetectionEvent]]:
    """Run v1-style signal generation: simple momentum + volatility heuristic.

    V1 uses: avg_return, volatility, positive_pct — no graph, no layers.
    """
    signals: List[DailySignal] = []
    events: List[DetectionEvent] = []

    if not data:
        return signals, events

    ref_symbol = "SPY" if "SPY" in data else list(data.keys())[0]
    n_days = len(data[ref_symbol].dates)

    prev_regime = None

    for day_idx in range(20, n_days):
        today = data[ref_symbol].dates[day_idx]

        returns = []
        for symbol, sd in data.items():
            if symbol in period.macro_proxies or day_idx >= len(sd.closes):
                continue
            prev = sd.closes[max(0, day_idx - 1)]
            curr = sd.closes[day_idx]
            if prev > 0:
                returns.append((curr - prev) / prev)

        if not returns:
            continue

        avg_return = sum(returns) / len(returns)
        vol = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
        pos_pct = len([r for r in returns if r > 0]) / len(returns)

        # V1 regime detection: simple thresholds
        if avg_return > 0.002 and pos_pct > 0.6:
            regime = "bull"
        elif avg_return < -0.002 and pos_pct < 0.4:
            regime = "bear"
        else:
            regime = "consolidation"

        if prev_regime and regime != prev_regime:
            events.append(DetectionEvent(
                date=today,
                event_type="regime_change",
                description=f"Regime: {prev_regime} → {regime} (avg_ret={avg_return:.4f}, vol={vol:.4f})",
            ))

        prev_regime = regime

        # V1 signals: buy in bull, sell in bear
        for symbol, sd in data.items():
            if symbol in period.macro_proxies or day_idx >= len(sd.closes):
                continue
            prev = sd.closes[max(0, day_idx - 5)]
            curr = sd.closes[day_idx]
            ret_5d = (curr - prev) / prev if prev > 0 else 0

            if regime == "bull" and ret_5d > 0.02:
                signals.append(DailySignal(
                    date=today, symbol=symbol, direction="long",
                    edge=round(ret_5d, 4), confidence=round(pos_pct, 4),
                    layer="momentum_only",
                ))
            elif regime == "bear" and ret_5d < -0.02:
                signals.append(DailySignal(
                    date=today, symbol=symbol, direction="short",
                    edge=round(ret_5d, 4), confidence=round(1 - pos_pct, 4),
                    layer="momentum_only",
                ))

    return signals, events


# ── Comparison ───────────────────────────────────────────────────────────────

@dataclass
class SignalAccuracy:
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0


def evaluate_signal_accuracy(
    signals: List[DailySignal],
    data: Dict[str, StockData],
    forward_days: int = 5,
) -> SignalAccuracy:
    """Check if signals predicted the right direction over forward_days."""
    correct = 0
    total = 0

    for sig in signals:
        if sig.symbol not in data:
            continue
        sd = data[sig.symbol]
        try:
            day_idx = sd.dates.index(sig.date)
        except ValueError:
            continue
        fwd_idx = min(day_idx + forward_days, len(sd.closes) - 1)
        if fwd_idx <= day_idx:
            continue

        fwd_return = (sd.closes[fwd_idx] - sd.closes[day_idx]) / sd.closes[day_idx]
        total += 1
        if (sig.direction == "long" and fwd_return > 0) or (sig.direction == "short" and fwd_return < 0):
            correct += 1

    accuracy = correct / total if total > 0 else 0.0
    return SignalAccuracy(total=total, correct=correct, accuracy=accuracy)


def evaluate_detection_timing(
    events: List[DetectionEvent],
    data: Dict[str, StockData],
    key_event_date: str,
) -> Dict[str, Any]:
    """How many days before/after the key event did each version detect something?"""
    key_date = date.fromisoformat(key_event_date)
    first_detection = None
    detection_count_before = 0
    detection_count_after = 0

    for evt in events:
        days_diff = (evt.date - key_date).days
        if first_detection is None or evt.date < first_detection:
            first_detection = evt.date
        if days_diff < 0:
            detection_count_before += 1
        else:
            detection_count_after += 1

    days_lead = (key_date - first_detection).days if first_detection else 0

    return {
        "first_detection": str(first_detection) if first_detection else None,
        "days_lead": days_lead,
        "detections_before_event": detection_count_before,
        "detections_after_event": detection_count_after,
        "total_events": len(events),
    }


def run_comparison(period_name: str) -> Dict[str, Any]:
    """Run full V1 vs V2 comparison for a test period."""
    period = PERIODS[period_name]
    print(f"\n{'='*70}")
    print(f"  {period.name}: {period.description}")
    print(f"  {period.start} → {period.end}")
    print(f"  Key event: {period.key_event_date}")
    print(f"  Propagation: {period.propagation_path}")
    print(f"{'='*70}\n")

    # Load data
    print("Loading historical data...")
    data = load_period_data(period)
    print(f"Loaded {len(data)} symbols\n")

    # Run both engines
    print("Running V1 signals...")
    v1_signals, v1_events = run_v1_signals(data, period)
    print(f"  {len(v1_signals)} signals, {len(v1_events)} events")

    print("Running V2 signals...")
    v2_signals, v2_events = run_v2_signals(data, period)
    print(f"  {len(v2_signals)} signals, {len(v2_events)} events\n")

    # Evaluate signal accuracy
    print("Evaluating signal accuracy (5-day forward)...")
    v1_acc = evaluate_signal_accuracy(v1_signals, data, forward_days=5)
    v2_acc = evaluate_signal_accuracy(v2_signals, data, forward_days=5)
    print(f"  V1: {v1_acc.correct}/{v1_acc.total} correct ({v1_acc.accuracy:.1%})")
    print(f"  V2: {v2_acc.correct}/{v2_acc.total} correct ({v2_acc.accuracy:.1%})\n")

    # Evaluate detection timing
    print("Evaluating detection timing vs key event...")
    v1_timing = evaluate_detection_timing(v1_events, data, period.key_event_date)
    v2_timing = evaluate_detection_timing(v2_events, data, period.key_event_date)
    print(f"  V1: first detection {v1_timing['first_detection']}, {v1_timing['days_lead']}d lead, {v1_timing['detections_before_event']} events before")
    print(f"  V2: first detection {v2_timing['first_detection']}, {v2_timing['days_lead']}d lead, {v2_timing['detections_before_event']} events before\n")

    # V2-specific: graph propagation events
    pressure_events = [e for e in v2_events if e.event_type == "macro_pressure_shift"]
    rs_flips = [e for e in v2_events if e.event_type == "relative_strength_flip"]
    exhaustion_events = [e for e in v2_events if e.event_type == "exhaustion_signal"]

    print("V2 graph-derived events:")
    print(f"  Macro pressure shifts: {len(pressure_events)}")
    print(f"  Relative strength flips: {len(rs_flips)}")
    print(f"  Exhaustion signals: {len(exhaustion_events)}")

    if pressure_events:
        print("\n  First 5 macro pressure shifts:")
        for e in pressure_events[:5]:
            print(f"    {e.date}: {e.description}")

    if rs_flips:
        print("\n  First 5 relative strength flips:")
        for e in rs_flips[:5]:
            print(f"    {e.date}: {e.description}")

    return {
        "period": period_name,
        "v1_accuracy": v1_acc.accuracy,
        "v2_accuracy": v2_acc.accuracy,
        "accuracy_delta": v2_acc.accuracy - v1_acc.accuracy,
        "v1_timing": v1_timing,
        "v2_timing": v2_timing,
        "v2_pressure_events": len(pressure_events),
        "v2_rs_flips": len(rs_flips),
        "v2_exhaustion_events": len(exhaustion_events),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="V1 vs V2 signal comparison")
    parser.add_argument("--period", choices=list(PERIODS.keys()), default="svb",
                        help="Test period to run")
    parser.add_argument("--all", action="store_true", help="Run all periods")
    args = parser.parse_args()

    if args.all:
        results = []
        for name in PERIODS:
            results.append(run_comparison(name))

        print(f"\n{'='*70}")
        print("  SUMMARY")
        print(f"{'='*70}")
        print(f"{'Period':<15} {'V1 Acc':>8} {'V2 Acc':>8} {'Delta':>8} {'V1 Lead':>8} {'V2 Lead':>8}")
        print("-" * 60)
        for r in results:
            print(f"{r['period']:<15} {r['v1_accuracy']:>7.1%} {r['v2_accuracy']:>7.1%} {r['accuracy_delta']:>+7.1%} {r['v1_timing']['days_lead']:>7}d {r['v2_timing']['days_lead']:>7}d")
    else:
        run_comparison(args.period)


if __name__ == "__main__":
    main()
