"""Live engine loop: fetch prices, detect regime, run controller, sync to Supabase."""

import logging
import os
import statistics
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import uuid4

from trading_backtest.automation_controller import AutonomousController
from trading_backtest.backtest_runner import compute_returns
from trading_backtest.data import fetch_historical_data
from trading_backtest.epistemic import BeliefType as EpBeliefType, EpistemicEngine, Belief as EpBelief

from fund.supabase_sync import SupabaseSync
from fund.types import Fund, WeeklyNAV

logger = logging.getLogger(__name__)


def _fetch_current_price(symbol: str) -> Optional[float]:
    """Fetch latest price for a symbol via yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning("Failed to fetch price for %s: %s", symbol, e)
        return None


def _fetch_returns_90d(symbol: str) -> List[float]:
    """Fetch 90-day daily returns for a symbol."""
    try:
        end = date.today()
        start = end - timedelta(days=95)
        data = fetch_historical_data(symbol, start.isoformat(), end.isoformat())
        return compute_returns(data.closes)
    except Exception as e:
        logger.warning("Failed to fetch returns for %s: %s", symbol, e)
        return []


def _classify_belief(returns: List[float]) -> tuple:
    """Classify a stock's belief type from recent returns."""
    if len(returns) < 5:
        return ("stable", 0.5)

    avg_ret = statistics.mean(returns[-20:]) if len(returns) >= 20 else statistics.mean(returns)
    vol = statistics.stdev(returns[-20:]) if len(returns) >= 20 else statistics.stdev(returns)

    if avg_ret > 0.002 and vol < 0.03:
        return ("high_growth", min(0.9, 0.5 + avg_ret * 50))
    elif avg_ret < -0.002:
        return ("declining", min(0.9, 0.5 + abs(avg_ret) * 50))
    else:
        return ("stable", 0.5 + min(0.3, (1 / (vol * 100 + 1))))


class LiveEngine:
    """Runs the full trading pipeline on a schedule and syncs to Supabase."""

    def __init__(
        self,
        symbols: List[str],
        fund: Fund,
        supabase: Optional[SupabaseSync],
        synthesizer=None,
        interval_seconds: int = 300,
    ):
        self.symbols = symbols
        self.fund = fund
        self.supabase = supabase
        self.synthesizer = synthesizer
        self.interval = interval_seconds
        self.controller = AutonomousController()
        self.epistemic = EpistemicEngine()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # State
        self.current_prices: Dict[str, float] = {}
        self.current_regime = "transition"
        self.last_analysis = None

    def start(self):
        """Start the engine loop in a background thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Live engine started (interval=%ds)", self.interval)

    def stop(self):
        """Stop the engine loop."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Live engine stopped")

    def _loop(self):
        """Main loop: run analysis, sync, sleep, repeat."""
        # Run immediately on start
        self._tick()
        while not self._stop.is_set():
            self._stop.wait(self.interval)
            if not self._stop.is_set():
                self._tick()

    def _tick(self):
        """Single iteration: fetch data, analyze, sync."""
        try:
            print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Live engine tick...")
            self._fetch_prices()
            self._run_analysis()
            self._sync_to_supabase()
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Tick complete. Regime: {self.current_regime}")
        except Exception as e:
            logger.error("Live engine tick failed: %s", e)
            print(f"  [ERROR] Tick failed: {e}")

    def _fetch_prices(self):
        """Fetch current prices for all symbols."""
        print("    Fetching live prices...")
        for symbol in self.symbols:
            price = _fetch_current_price(symbol)
            if price is not None:
                self.current_prices[symbol] = price
        print(f"    Got prices for {len(self.current_prices)}/{len(self.symbols)} symbols")

    def _run_analysis(self):
        """Run the full trading pipeline."""
        print("    Running analysis pipeline...")

        # 1. Compute market metrics from recent returns
        all_returns = {}
        for symbol in self.symbols:
            rets = _fetch_returns_90d(symbol)
            if rets:
                all_returns[symbol] = rets

        if not all_returns:
            print("    No return data available, skipping analysis")
            return

        # Aggregate market metrics
        avg_returns = [statistics.mean(r) for r in all_returns.values()]
        vols = [statistics.stdev(r) for r in all_returns.values() if len(r) > 1]
        positive_count = sum(1 for r in avg_returns if r > 0)

        market_metrics = {
            "avg_return": statistics.mean(avg_returns) * 252,  # annualize
            "volatility": statistics.mean(vols) * (252 ** 0.5) if vols else 0.2,
            "positive_pct": positive_count / len(avg_returns) if avg_returns else 0.5,
            "momentum": statistics.mean(avg_returns) * 20,  # 1-month momentum
        }

        # 2. Build beliefs from price action
        beliefs_dict = {}
        for symbol, returns in all_returns.items():
            btype, conf = _classify_belief(returns)
            beliefs_dict[symbol] = (btype, conf)

            # Also update the epistemic engine
            ep_belief_type = {
                "high_growth": EpBeliefType.HIGH_GROWTH,
                "declining": EpBeliefType.DECLINING,
                "stable": EpBeliefType.STABLE,
            }.get(btype, EpBeliefType.STABLE)

            belief = EpBelief(
                symbol=symbol,
                attribute="return",
                belief_type=ep_belief_type,
                probability=conf,
            )
            self.epistemic.add_belief(belief)

            # Check for anomalies
            anomaly = self.epistemic.detect_anomaly(belief)
            if anomaly["is_anomaly"]:
                print(f"    ANOMALY: {symbol} — high confidence ({conf:.2f}) with sparse evidence")

        # 3. Compute current portfolio weights
        total_value = sum(
            self.current_prices.get(s, 0) for s in self.symbols
        )
        current_portfolio = {}
        if total_value > 0:
            for s in self.symbols:
                p = self.current_prices.get(s, 0)
                if p > 0:
                    current_portfolio[s] = p / total_value

        # 4. Run the controller
        result = self.controller.analyze(
            market_metrics=market_metrics,
            beliefs_dict=beliefs_dict,
            current_portfolio=current_portfolio,
            current_prices=self.current_prices,
        )

        self.current_regime = result.regime.value
        self.last_analysis = result

        print(f"    Regime: {result.regime.value}")
        print(f"    Strategy: {result.selected_strategy.name} (confidence: {result.selected_strategy.confidence:.2f})")
        print(f"    Trades suggested: {len(result.execution_plan.trades)}")

        for trade in result.execution_plan.trades[:5]:
            print(f"      {trade.type} {trade.symbol} → {trade.allocation:.1%} ({trade.reason})")

    def _sync_to_supabase(self):
        """Push current state to Supabase."""
        if not self.supabase:
            return

        print("    Syncing to Supabase...")

        # Heartbeat
        self.supabase.push_heartbeat({
            "id": "singleton",
            "status": "running",
            "alpaca_connected": False,
            "last_trade": None,
            "active_positions": len(self.current_prices),
            "current_regime": self.current_regime,
            "next_action": f"Next analysis in {self.interval}s",
            "next_action_at": (datetime.now() + timedelta(seconds=self.interval)).isoformat(),
        })

        # Fund snapshot
        total_nav = sum(self.current_prices.get(s, 0) for s in self.symbols)
        if total_nav > 0:
            self.fund.nav = Decimal(str(round(total_nav, 2)))

        self.supabase.push_snapshot({
            "id": str(uuid4()),
            "date": str(date.today()),
            "nav": float(self.fund.nav),
            "nav_per_unit": float(self.fund.nav_per_unit),
            "units_outstanding": float(self.fund.units_outstanding),
            "high_water_mark": float(self.fund.high_water_mark),
            "cash": 0,
            "positions_count": len(self.current_prices),
        })

        # Positions
        total_value = float(self.fund.nav)
        positions = []
        for symbol in self.symbols:
            price = self.current_prices.get(symbol)
            if not price:
                continue
            positions.append({
                "symbol": symbol,
                "quantity": 1.0,
                "market_value": price,
                "avg_entry_price": price * 0.95,  # placeholder
                "current_price": price,
                "unrealized_pl": price * 0.05,
                "unrealized_pl_pct": 5.0,
                "allocation_pct": price / total_value if total_value > 0 else 0,
            })
        if positions:
            self.supabase.push_positions(positions)

        # Weekly NAV entry (once per tick, upserted on date)
        weekly_return = 0.0
        if self.last_analysis:
            mkt = self.last_analysis
            weekly_return = mkt.confidence * 0.01  # rough proxy

        try:
            self.supabase._client.table("weekly_nav").upsert({
                "id": str(uuid4()),
                "date": str(date.today()),
                "nav": float(self.fund.nav),
                "nav_per_unit": float(self.fund.nav_per_unit),
                "gross_return_pct": weekly_return,
                "net_return_pct": weekly_return - 0.0004,
                "mgmt_fee_accrued": 0,
                "perf_fee_accrued": 0,
                "high_water_mark": float(self.fund.high_water_mark),
                "clarity_score": 0,
                "opportunity_score": 0,
                "capture_rate": 0,
                "market_health": "green" if self.current_regime == "bull" else "yellow" if self.current_regime == "transition" else "red",
                "momentum": "rising" if weekly_return > 0 else "steady",
                "benchmarks": {},
                "narrative_summary": "",
            }, on_conflict="date").execute()
        except Exception as e:
            logger.warning("Failed to upsert weekly_nav: %s", e)

        # Journal entry with analysis
        if self.last_analysis:
            result = self.last_analysis
            trades = [
                {
                    "type": t.type,
                    "symbol": t.symbol,
                    "allocation": round(t.allocation, 4),
                    "reason": t.reason,
                }
                for t in result.execution_plan.trades[:10]
            ]
            try:
                self.supabase.push_journal({
                    "id": str(uuid4()),
                    "date": str(date.today()),
                    "entries": {
                        "regime": result.regime.value,
                        "strategy": result.selected_strategy.name,
                        "strategy_confidence": round(result.selected_strategy.confidence, 2),
                        "overall_confidence": round(result.confidence, 2),
                        "trades": trades,
                        "prices": {s: round(p, 2) for s, p in self.current_prices.items()},
                    },
                    "regime_summary": f"Market regime: {result.regime.value}. Strategy: {result.selected_strategy.name} (confidence {result.selected_strategy.confidence:.0%}). {len(trades)} trade suggestions.",
                    "trades_executed": 0,
                    "nav_change_pct": 0,
                })
            except Exception as e:
                logger.warning("Failed to upsert journal: %s", e)

        print("    Sync complete")
