from dataclasses import dataclass
from typing import List, Dict
from trading_backtest.regime import MarketRegime


@dataclass
class StrategyScore:
    """Strategy evaluation result."""
    name: str                  # strategy name
    score: float               # 0-100 composite score
    expected_return: float     # expected return in this regime
    sharpe_ratio: float        # expected Sharpe ratio
    max_drawdown: float        # max drawdown risk
    confidence: float          # 0-1 confidence in prediction


class StrategySelector:
    """Selects optimal strategy based on market regime and metrics."""

    # Historical performance from 2025 backtest
    STRATEGY_PROFILES = {
        'kelly_monthly_rebalance': {
            'return': 0.3804,
            'sharpe': 1.8,
            'drawdown': -0.12,
            'volatility': 0.21,
            'bull_fit': 1.0,        # scores highest in bull
            'bear_fit': 0.4,
            'transition_fit': 0.8,
            'consolidation_fit': 0.3,
        },
        'kelly_inverse_hedge': {
            'return': 0.3466,
            'sharpe': 1.6,
            'drawdown': -0.15,
            'volatility': 0.22,
            'bull_fit': 0.8,
            'bear_fit': 0.85,       # good in bear
            'transition_fit': 0.75,
            'consolidation_fit': 0.5,
        },
        'equal_weight_inverse_hedge': {
            'return': 0.2710,
            'sharpe': 1.2,
            'drawdown': -0.18,
            'volatility': 0.24,
            'bull_fit': 0.6,
            'bear_fit': 0.7,
            'transition_fit': 0.65,
            'consolidation_fit': 0.6,
        },
        'kelly_dynamic_hedge': {
            'return': 0.2673,
            'sharpe': 1.15,
            'drawdown': -0.20,
            'volatility': 0.25,
            'bull_fit': 0.7,
            'bear_fit': 0.65,
            'transition_fit': 0.7,
            'consolidation_fit': 0.55,
        },
        'belief_weighted': {
            'return': 0.2064,
            'sharpe': 0.95,
            'drawdown': -0.25,
            'volatility': 0.28,
            'bull_fit': 0.5,
            'bear_fit': 0.6,
            'transition_fit': 0.6,
            'consolidation_fit': 0.4,
        },
        'stop_loss_20pct': {
            'return': 0.1875,
            'sharpe': 0.85,
            'drawdown': -0.20,
            'volatility': 0.29,
            'bull_fit': 0.4,
            'bear_fit': 0.7,
            'transition_fit': 0.5,
            'consolidation_fit': 0.65,
        },
        'equal_weight': {
            'return': 0.1821,
            'sharpe': 0.80,
            'drawdown': -0.28,
            'volatility': 0.30,
            'bull_fit': 0.5,
            'bear_fit': 0.5,
            'transition_fit': 0.5,
            'consolidation_fit': 0.5,
        },
    }

    def score_all_strategies(self, regime: MarketRegime,
                            metrics: Dict) -> List[StrategyScore]:
        """
        Score all strategies for current regime.
        Returns list sorted by score (highest first).
        """
        scores = []
        regime_key = f"{regime.value}_fit"

        for strategy_name, profile in self.STRATEGY_PROFILES.items():
            # Base fit score for regime
            regime_fit = profile.get(regime_key, 0.5)

            # Adjust for current market metrics
            return_adjustment = min(metrics.get('return', 0) / 0.15, 1.0)
            sharpe_adjustment = max(metrics.get('sharpe', 0.8) / 1.5, 0.5)

            # Composite score: regime fit (70%) + adjustments (30%)
            score = (regime_fit * 70) + (return_adjustment * 15) + (sharpe_adjustment * 15)
            score = max(0, min(100, score))  # Clamp 0-100

            scores.append(StrategyScore(
                name=strategy_name,
                score=score,
                expected_return=profile['return'],
                sharpe_ratio=profile['sharpe'],
                max_drawdown=profile['drawdown'],
                confidence=regime_fit,
            ))

        # Sort by score descending
        return sorted(scores, key=lambda s: s.score, reverse=True)
