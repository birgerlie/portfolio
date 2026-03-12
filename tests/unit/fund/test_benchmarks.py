"""Tests for benchmark engine — standard benchmarks + alternative universes."""
import pytest
from fund.benchmarks import BenchmarkEngine


class TestBenchmarkComparison:
    def test_cumulative_return(self):
        engine = BenchmarkEngine()
        values = [100.0, 105.0, 110.0, 108.0, 115.0]
        assert engine.cumulative_return(values) == pytest.approx(0.15, abs=0.001)

    def test_cumulative_return_empty(self):
        engine = BenchmarkEngine()
        assert engine.cumulative_return([]) == 0.0

    def test_alpha_vs_benchmark(self):
        engine = BenchmarkEngine()
        assert engine.alpha(0.15, 0.10) == pytest.approx(0.05)

    def test_compare_all_benchmarks(self):
        engine = BenchmarkEngine()
        fund_values = [100.0, 110.0, 120.0]
        benchmark_values = {"SPY": [100.0, 105.0, 108.0], "QQQ": [100.0, 108.0, 115.0]}
        result = engine.compare(fund_values, benchmark_values)
        assert "SPY" in result
        assert "QQQ" in result
        assert result["SPY"]["alpha"] > 0


class TestAlternativeUniverses:
    def test_equal_weight_return(self):
        engine = BenchmarkEngine()
        stock_returns = {"A": [0.01, 0.02, -0.01], "B": [-0.01, 0.03, 0.02], "C": [0.02, -0.01, 0.01]}
        eq_return = engine.equal_weight_return(stock_returns)
        assert eq_return > 0

    def test_best_possible_return(self):
        engine = BenchmarkEngine()
        stock_returns = {"A": [0.05, -0.02, 0.01], "B": [-0.01, 0.08, -0.03], "C": [0.02, 0.01, 0.10]}
        best = engine.best_daily_pick_return(stock_returns)
        assert best == pytest.approx(0.2474, abs=0.001)

    def test_random_portfolio_return(self):
        engine = BenchmarkEngine()
        stock_returns = {"A": [0.01, 0.02], "B": [-0.01, 0.03]}
        median = engine.random_portfolio_median(stock_returns, n_simulations=100, seed=42)
        assert isinstance(median, float)


class TestCaptureRate:
    def test_capture_rate(self):
        engine = BenchmarkEngine()
        assert engine.capture_rate(0.15, 0.25) == pytest.approx(60.0)

    def test_capture_rate_zero_best(self):
        engine = BenchmarkEngine()
        assert engine.capture_rate(0.10, 0.0) == 0.0
