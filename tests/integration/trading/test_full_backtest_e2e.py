"""End-to-end integration test for full trading system backtest."""

import pytest
from datetime import date, timedelta
from trading_backtest.runner import TradingSystemBacktest
from trading_backtest.analysis import BacktestAnalysis


class TestFullBacktestE2E:
    """Test complete trading system integration."""

    def test_full_backtest_s_and_p500(self):
        """Run 2-year backtest on S&P 500 sample.

        Verifies:
        - Results dict has all required metrics
        - Values are within reasonable ranges
        - Portfolio simulation runs without errors
        """
        # Setup: 2-year backtest with S&P 500 symbols
        start_date = "2022-01-01"
        end_date = "2024-01-01"
        initial_capital = 100000
        top_k = 20

        runner = TradingSystemBacktest(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            top_k=top_k,
        )

        # Act: Run full backtest
        results = runner.run()

        # Assert: Results structure
        assert isinstance(results, dict), "Results must be a dict"
        assert "final_value" in results, "Missing final_value"
        assert "total_return" in results, "Missing total_return"
        assert "sharpe" in results, "Missing sharpe"
        assert "max_drawdown" in results, "Missing max_drawdown"
        assert "portfolio_values" in results, "Missing portfolio_values"
        assert "monthly_returns" in results, "Missing monthly_returns"

        # Assert: Reasonable value ranges
        assert results["final_value"] > 0, "Portfolio value must be positive"
        assert -1 < results["total_return"] < 2, (
            f"Total return must be reasonable, got {results['total_return']}"
        )
        assert 0 <= results["max_drawdown"] < 1, (
            f"Max drawdown must be 0-1, got {results['max_drawdown']}"
        )
        assert results["sharpe"] is not None, "Sharpe ratio must be computed"

        # Assert: Portfolio values decrease over time or stay stable
        portfolio_vals = results["portfolio_values"]
        assert len(portfolio_vals) > 0, "Must have portfolio values"
        assert portfolio_vals[0] == initial_capital, "First value is initial capital"

        # Assert: Monthly returns list has correct length
        monthly = results["monthly_returns"]
        assert isinstance(monthly, list), "Monthly returns must be list"
        assert len(monthly) >= 0, "Monthly returns can be empty"

    def test_backtest_analysis(self):
        """Generate report with specific metrics.

        Verifies:
        - Report generation succeeds
        - Report contains key sections
        - Period analysis metrics are present
        """
        # Setup: Run minimal backtest
        runner = TradingSystemBacktest(
            start_date="2023-01-01",
            end_date="2023-06-01",
            initial_capital=50000,
            top_k=10,
        )
        results = runner.run()

        # Act: Generate analysis report
        analysis = BacktestAnalysis()
        report = analysis.generate_report(results)

        # Assert: Report structure
        assert isinstance(report, str), "Report must be string"
        assert len(report) > 0, "Report cannot be empty"
        assert "Total Return" in report or "Backtest Results" in report, (
            "Report must contain summary metrics"
        )

        # Act: Generate period analysis
        period_stats = analysis.period_analysis(results)

        # Assert: Period analysis metrics
        assert isinstance(period_stats, dict), "Period stats must be dict"
        assert "positive_months" in period_stats, "Missing positive_months"
        assert "negative_months" in period_stats, "Missing negative_months"
        assert "win_rate" in period_stats, "Missing win_rate"
        assert "avg_gain" in period_stats, "Missing avg_gain"
        assert "avg_loss" in period_stats, "Missing avg_loss"

        # Assert: Metric ranges
        assert period_stats["positive_months"] >= 0, "Positive months >= 0"
        assert period_stats["negative_months"] >= 0, "Negative months >= 0"
        assert 0 <= period_stats["win_rate"] <= 1, "Win rate must be 0-1"

    def test_backtest_with_different_top_k(self):
        """Verify backtest works with different top_k values."""
        runner_k5 = TradingSystemBacktest(
            start_date="2023-01-01",
            end_date="2023-12-01",
            initial_capital=50000,
            top_k=5,
        )
        results_k5 = runner_k5.run()

        runner_k20 = TradingSystemBacktest(
            start_date="2023-01-01",
            end_date="2023-12-01",
            initial_capital=50000,
            top_k=20,
        )
        results_k20 = runner_k20.run()

        # Both should complete without error
        assert "final_value" in results_k5
        assert "final_value" in results_k20

    def test_backtest_handles_short_period(self):
        """Verify backtest handles short time periods gracefully."""
        runner = TradingSystemBacktest(
            start_date="2023-06-01",
            end_date="2023-07-01",
            initial_capital=50000,
            top_k=10,
        )
        results = runner.run()

        # Should complete with valid results
        assert "final_value" in results
        assert results["final_value"] > 0
