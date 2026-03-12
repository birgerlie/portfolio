"""Snapshot builder — assembles WeeklyNAV from all fund components."""
from datetime import date
from decimal import Decimal
from typing import Dict
from fund.types import Fund, WeeklyNAV
from fund.fees import FeeEngine
from fund.nav import NAVCalculator
from fund.thermo_metrics import ThermoMetrics
from fund.benchmarks import BenchmarkEngine


class SnapshotBuilder:
    def __init__(self, nav_calculator: NAVCalculator, fee_engine: FeeEngine,
                 thermo_metrics: ThermoMetrics, benchmark_engine: BenchmarkEngine):
        self.nav_calc = nav_calculator
        self.fee_engine = fee_engine
        self.thermo = thermo_metrics
        self.benchmarks = benchmark_engine

    def build(self, fund: Fund, positions: Dict[str, Dict], cash: Decimal,
              beliefs: Dict[str, float], prev_beliefs: Dict[str, float],
              volatility: float, prev_nav: Decimal, snapshot_date: date,
              benchmark_values: Dict[str, list], stock_returns: Dict[str, list]) -> WeeklyNAV:
        # NAV
        gross = self.nav_calc.gross_nav(positions, cash)
        fees = self.fee_engine.accrue_weekly(
            nav=gross, nav_per_unit=fund.nav_per_unit,
            high_water_mark=fund.high_water_mark, units_outstanding=fund.units_outstanding)
        net = self.nav_calc.net_nav(gross, fees)
        nav_per_unit = net / fund.units_outstanding if fund.units_outstanding > 0 else Decimal("0")
        gross_return = self.nav_calc.return_pct(prev_nav, gross)
        net_return = self.nav_calc.return_pct(prev_nav, net)

        # Thermo
        clarity = self.thermo.clarity_score(beliefs)
        opportunity = self.thermo.opportunity_score(beliefs, volatility)
        health = self.thermo.market_health(volatility)
        momentum = self.thermo.momentum(prev_beliefs, beliefs)
        interpretation = self.thermo.interpret(clarity, opportunity, health, momentum)

        # Benchmarks
        bench_results = {}
        if benchmark_values:
            bench_results = {name: self.benchmarks.cumulative_return(vals)
                             for name, vals in benchmark_values.items()}

        # Alternative universes
        eq_weight = self.benchmarks.equal_weight_return(stock_returns) if stock_returns else 0.0
        best = self.benchmarks.best_daily_pick_return(stock_returns) if stock_returns else 0.0
        rand = self.benchmarks.random_portfolio_median(stock_returns) if stock_returns else 0.0
        capture = self.benchmarks.capture_rate(net_return, best) if best > 0 else 0.0

        return WeeklyNAV(
            date=snapshot_date, nav=net, nav_per_unit=nav_per_unit,
            gross_return_pct=gross_return, mgmt_fee_accrued=fees.management_fee,
            perf_fee_accrued=fees.performance_fee, net_return_pct=net_return,
            high_water_mark=fund.high_water_mark, clarity_score=clarity,
            opportunity_score=opportunity, capture_rate=capture,
            market_health=health, momentum=momentum, benchmarks=bench_results,
            universe_equal_weight=eq_weight, universe_no_thermo=0.0,
            universe_best_possible=best, universe_random_avg=rand,
            narrative_summary=interpretation)
