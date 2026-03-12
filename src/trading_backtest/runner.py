"""TradingSystemBacktest: Integration of all 6 components."""

from datetime import datetime
from typing import Dict, List, Any

from trading_backtest.data import fetch_sp500_symbols
from trading_backtest.credibility import SourceCredibility
from trading_backtest.epistemic import EpistemicEngine
from trading_backtest.decision import DecisionEngine
from trading_backtest.rca import RCAEngine
from trading_backtest.backtest import Backtester
from trading_backtest.backtest_runner import next_month
from trading_backtest.recommendation_engine import generate_candidates
from trading_backtest.trade_executor import (
    execute_trades,
    update_portfolio_prices,
)


class TradingSystemBacktest:
    """Complete trading system backtest runner.

    Integrates data, credibility, epistemic, decision, RCA, and backtest
    components into a unified trading system.
    """

    def __init__(
        self,
        start_date: str,
        end_date: str,
        initial_capital: float,
        top_k: int = 20,
    ):
        """Initialize backtest system.

        Args:
            start_date: Start date as YYYY-MM-DD string
            end_date: End date as YYYY-MM-DD string
            initial_capital: Initial portfolio value
            top_k: Number of top recommendations per month
        """
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d")
        self.initial_capital = initial_capital
        self.top_k = top_k

        self._init_components()

    def _init_components(self) -> None:
        """Initialize all 6 components."""
        self.backtester = Backtester(self.initial_capital)
        self.decision_engine = DecisionEngine()
        self.epistemic_engine = EpistemicEngine()
        self.rca_engine = RCAEngine()

        self.epistemic_engine.tracker.add_source(
            SourceCredibility(source_name="market_data", trust=0.9)
        )

    def run(self) -> Dict[str, Any]:
        """Run backtest over date range.

        Returns:
            Dict with: final_value, total_return, sharpe, max_drawdown,
                      portfolio_values, monthly_returns
        """
        portfolio_values = [self.initial_capital]
        current_date = self.start_date

        while current_date <= self.end_date:
            self._process_month(current_date, portfolio_values)
            current_date = next_month(current_date)

        return self._compute_results(portfolio_values)

    def _process_month(
        self, month_date: datetime, portfolio_values: List[float]
    ) -> None:
        """Process one month of trading.

        Args:
            month_date: Current month
            portfolio_values: List to append monthly portfolio value to
        """
        symbols = self._get_symbols_for_month()
        if not symbols:
            portfolio_values.append(self.backtester.portfolio_value)
            return

        candidates = generate_candidates(
            symbols, month_date, self.epistemic_engine
        )
        if not candidates:
            portfolio_values.append(self.backtester.portfolio_value)
            return

        recommended = self.decision_engine.recommend_actions(
            candidates, k=self.top_k
        )
        execute_trades(recommended, self.backtester, month_date, self.top_k)
        update_portfolio_prices(self.backtester, month_date)
        portfolio_values.append(self.backtester.portfolio_value)

    def _get_symbols_for_month(self) -> List[str]:
        """Get S&P 500 symbols for backtest.

        Returns:
            List of stock symbols (capped for performance)
        """
        try:
            symbols = fetch_sp500_symbols()
            return symbols[:50]
        except Exception:
            return ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]

    def _compute_results(self, portfolio_values: List[float]) -> Dict[str, Any]:
        """Compute final backtest results.

        Args:
            portfolio_values: List of portfolio values over time

        Returns:
            Dict with all metrics
        """
        if not portfolio_values:
            portfolio_values = [self.initial_capital]

        final_val = portfolio_values[-1]
        total_ret = (final_val - self.initial_capital) / self.initial_capital
        monthly_ret = self.backtester.calculate_monthly_returns(
            portfolio_values
        )

        return {
            "final_value": final_val,
            "total_return": total_ret,
            "sharpe": self.backtester.calculate_sharpe_ratio(monthly_ret),
            "max_drawdown": self.backtester.calculate_max_drawdown(
                portfolio_values
            ),
            "portfolio_values": portfolio_values,
            "monthly_returns": monthly_ret,
        }
