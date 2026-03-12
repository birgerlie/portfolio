"""BacktestAnalysis: Generate reports and analyze backtest results."""

from typing import Dict, List, Any, Optional
import statistics


class BacktestAnalysis:
    """Analyze backtest results and generate reports."""

    def generate_report(
        self, results: Dict[str, Any], baseline_results: Optional[Dict] = None
    ) -> str:
        """Generate analysis report from backtest results.

        Args:
            results: Backtest results dict from TradingSystemBacktest.run()
            baseline_results: Optional baseline results for comparison

        Returns:
            Formatted report string
        """
        lines = ["=" * 60]
        lines.append("BACKTEST RESULTS SUMMARY")
        lines.append("=" * 60)

        lines.extend(self._format_main_metrics(results))
        lines.extend(self._format_risk_metrics(results))
        lines.extend(self._format_monthly_analysis(results))

        if baseline_results:
            lines.extend(self._format_comparison(results, baseline_results))

        lines.append("=" * 60)
        return "\n".join(lines)

    def _format_main_metrics(self, results: Dict[str, Any]) -> List[str]:
        """Format main performance metrics.

        Args:
            results: Backtest results

        Returns:
            List of formatted lines
        """
        lines = []
        final_val = results.get("final_value", 0)
        total_ret = results.get("total_return", 0)

        lines.append("")
        lines.append(f"Final Portfolio Value:  ${final_val:,.2f}")
        lines.append(f"Total Return:           {total_ret:+.2%}")
        lines.append("")

        return lines

    def _format_risk_metrics(self, results: Dict[str, Any]) -> List[str]:
        """Format risk-adjusted metrics.

        Args:
            results: Backtest results

        Returns:
            List of formatted lines
        """
        lines = []
        sharpe = results.get("sharpe", 0)
        max_dd = results.get("max_drawdown", 0)

        lines.append("Risk Metrics:")
        lines.append(f"  Sharpe Ratio:        {sharpe:.3f}")
        lines.append(f"  Max Drawdown:        {max_dd:.2%}")
        lines.append("")

        return lines

    def _format_monthly_analysis(self, results: Dict[str, Any]) -> List[str]:
        """Format monthly return statistics.

        Args:
            results: Backtest results

        Returns:
            List of formatted lines
        """
        lines = []
        monthly = results.get("monthly_returns", [])

        if not monthly:
            return lines

        period_stats = self.period_analysis(results)
        lines.append("Monthly Return Statistics:")
        lines.append(f"  Positive Months:     {period_stats['positive_months']}")
        lines.append(f"  Negative Months:     {period_stats['negative_months']}")
        lines.append(f"  Win Rate:            {period_stats['win_rate']:.1%}")
        lines.append(f"  Avg Gain (months+):  {period_stats['avg_gain']:+.2%}")
        lines.append(f"  Avg Loss (months-):  {period_stats['avg_loss']:+.2%}")
        lines.append("")

        return lines

    def _format_comparison(
        self, results: Dict[str, Any], baseline: Dict[str, Any]
    ) -> List[str]:
        """Format comparison with baseline.

        Args:
            results: Backtest results
            baseline: Baseline results for comparison

        Returns:
            List of formatted lines
        """
        lines = ["", "Comparison vs Baseline:"]

        ret_diff = results.get("total_return", 0) - baseline.get(
            "total_return", 0
        )
        lines.append(f"  Return Diff:         {ret_diff:+.2%}")

        sharpe_diff = results.get("sharpe", 0) - baseline.get("sharpe", 0)
        lines.append(f"  Sharpe Diff:         {sharpe_diff:+.3f}")

        dd_diff = baseline.get("max_drawdown", 0) - results.get(
            "max_drawdown", 0
        )
        lines.append(f"  Drawdown Improvement:{dd_diff:+.2%}")
        lines.append("")

        return lines

    def period_analysis(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze results by month.

        Args:
            results: Backtest results

        Returns:
            Dict with: positive_months, negative_months, win_rate,
                      avg_gain, avg_loss
        """
        monthly = results.get("monthly_returns", [])

        if not monthly:
            return self._empty_analysis()

        positive = [r for r in monthly if r > 0]
        negative = [r for r in monthly if r < 0]

        return self._compute_period_stats(monthly, positive, negative)

    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis dict."""
        return {
            "positive_months": 0,
            "negative_months": 0,
            "win_rate": 0.0,
            "avg_gain": 0.0,
            "avg_loss": 0.0,
        }

    def _compute_period_stats(
        self, monthly: List[float], positive: List[float], negative: List[float]
    ) -> Dict[str, Any]:
        """Compute period statistics.

        Args:
            monthly: All monthly returns
            positive: Positive returns
            negative: Negative returns

        Returns:
            Statistics dict
        """
        win_rate = len(positive) / len(monthly) if monthly else 0.0
        avg_gain = statistics.mean(positive) if positive else 0.0
        avg_loss = statistics.mean(negative) if negative else 0.0

        return {
            "positive_months": len(positive),
            "negative_months": len(negative),
            "win_rate": win_rate,
            "avg_gain": avg_gain,
            "avg_loss": avg_loss,
        }
