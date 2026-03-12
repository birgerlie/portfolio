"""Benchmark engine — standard benchmarks and alternative universe comparison."""
import random
from typing import Dict, List, Optional


class BenchmarkEngine:
    def cumulative_return(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        return (values[-1] - values[0]) / values[0]

    def alpha(self, fund_return: float, benchmark_return: float) -> float:
        return fund_return - benchmark_return

    def compare(self, fund_values: List[float], benchmark_values: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]:
        fund_return = self.cumulative_return(fund_values)
        result = {}
        for name, values in benchmark_values.items():
            bench_return = self.cumulative_return(values)
            result[name] = {"return": bench_return, "alpha": self.alpha(fund_return, bench_return)}
        return result

    def equal_weight_return(self, stock_returns: Dict[str, List[float]]) -> float:
        if not stock_returns:
            return 0.0
        symbols = list(stock_returns.keys())
        n_days = len(next(iter(stock_returns.values())))
        cumulative = 1.0
        for day in range(n_days):
            daily_avg = sum(stock_returns[s][day] for s in symbols) / len(symbols)
            cumulative *= (1 + daily_avg)
        return cumulative - 1

    def best_daily_pick_return(self, stock_returns: Dict[str, List[float]]) -> float:
        if not stock_returns:
            return 0.0
        symbols = list(stock_returns.keys())
        n_days = len(next(iter(stock_returns.values())))
        cumulative = 1.0
        for day in range(n_days):
            best = max(stock_returns[s][day] for s in symbols)
            cumulative *= (1 + best)
        return cumulative - 1

    def random_portfolio_median(self, stock_returns: Dict[str, List[float]],
                                 n_simulations: int = 1000, seed: Optional[int] = None) -> float:
        if not stock_returns:
            return 0.0
        if seed is not None:
            random.seed(seed)
        symbols = list(stock_returns.keys())
        n_days = len(next(iter(stock_returns.values())))
        results = []
        for _ in range(n_simulations):
            weights = [random.random() for _ in symbols]
            total = sum(weights)
            weights = [w / total for w in weights]
            cumulative = 1.0
            for day in range(n_days):
                daily = sum(weights[i] * stock_returns[s][day] for i, s in enumerate(symbols))
                cumulative *= (1 + daily)
            results.append(cumulative - 1)
        results.sort()
        return results[len(results) // 2]

    def capture_rate(self, actual: float, best_possible: float) -> float:
        if best_possible <= 0:
            return 0.0
        return (actual / best_possible) * 100
