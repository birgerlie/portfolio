from dataclasses import dataclass
from typing import Dict, Tuple
from enum import Enum
from trading_backtest.regime import RegimeDetector, MarketRegime
from trading_backtest.strategy_selector import StrategySelector
from trading_backtest.portfolio_composer import PortfolioComposer
from trading_backtest.execution_generator import ExecutionPlanGenerator


# Belief type enum
class BeliefType(Enum):
    """Types of beliefs about stock movement."""
    HIGH_GROWTH = "high_growth"
    STABLE = "stable"
    DECLINING = "declining"


@dataclass
class Belief:
    """Epistemic belief about a stock."""
    symbol: str
    field: str
    belief_type: BeliefType
    confidence: float


@dataclass
class ControllerState:
    """State snapshot from autonomous controller analysis."""
    regime: MarketRegime
    selected_strategy: object  # StrategyScore
    portfolio: object          # PortfolioWeights
    execution_plan: object     # ExecutionPlan
    confidence: float          # overall decision confidence (0-1)


class AutonomousController:
    """Orchestrates the full autonomous trading pipeline."""

    def __init__(self):
        self.regime_detector = RegimeDetector()
        self.strategy_selector = StrategySelector()
        self.portfolio_composer = PortfolioComposer()
        self.execution_generator = ExecutionPlanGenerator()

    def analyze(self, market_metrics: Dict, beliefs_dict: Dict,
                current_portfolio: Dict = None,
                current_prices: Dict = None,
                strategy_hint: str = None) -> ControllerState:
        """
        Full pipeline: detect regime → select strategy → compose portfolio → generate execution.

        Args:
            market_metrics: Dictionary with avg_return, volatility, positive_pct, momentum
            beliefs_dict: Dictionary of {symbol: (belief_type, confidence)}
            current_portfolio: Current holdings {symbol: weight}
            current_prices: Current market prices {symbol: price}
            strategy_hint: Optional preferred strategy name

        Returns: ControllerState with complete analysis
        """
        # Step 1: Detect market regime
        regime = self.regime_detector.classify(market_metrics)

        # Step 2: Score and select strategy
        scores = self.strategy_selector.score_all_strategies(regime, market_metrics)
        selected_strategy = scores[0]  # Highest scoring

        # Step 3: Convert beliefs to portfolio weights
        beliefs = self._build_beliefs(beliefs_dict)
        portfolio = self.portfolio_composer.compose(beliefs, selected_strategy.name)

        # Step 4: Generate execution plan
        current_port = current_portfolio or {}
        current_price = current_prices or {s: 100 for s in beliefs_dict.keys()}

        execution_plan = self.execution_generator.generate(
            portfolio, current_port, current_price
        )

        # Calculate overall confidence
        confidence = (selected_strategy.confidence + portfolio.net_exposure) / 2

        return ControllerState(
            regime=regime,
            selected_strategy=selected_strategy,
            portfolio=portfolio,
            execution_plan=execution_plan,
            confidence=confidence,
        )

    def _build_beliefs(self, beliefs_dict: Dict) -> Dict:
        """Convert beliefs_dict format to Belief objects."""
        beliefs = {}
        for symbol, (belief_type_str, confidence) in beliefs_dict.items():
            belief_type = BeliefType.HIGH_GROWTH
            if 'declining' in belief_type_str.lower():
                belief_type = BeliefType.DECLINING
            elif 'stable' in belief_type_str.lower():
                belief_type = BeliefType.STABLE

            beliefs[symbol] = Belief(
                symbol=symbol,
                field='return',
                belief_type=belief_type,
                confidence=confidence,
            )
        return beliefs
