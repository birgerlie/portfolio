# Autonomous Portfolio & Strategy Selection System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Build a fully autonomous system that analyzes market conditions, selects the optimal trading strategy, composes portfolio weights, and generates execution instructions with zero manual decision-making.

**Architecture:** Four-layer pipeline: (1) Market Regime Detection analyzes RCA findings to classify current conditions (bull/bear/transition/consolidation), (2) Strategy Selection scores all 7 strategies against current regime using historical performance data, (3) Portfolio Composition uses epistemic beliefs + Kelly Criterion to weight stocks, (4) Execution Generator creates actionable buy/sell orders.

**Tech Stack:** Python 3.9+, existing trading_backtest framework (epistemic.py, decision.py, rca.py), numpy, dataclasses for configuration objects.

**Clean Code Rules:** Max 300 lines/file, 30 lines/function, 4 params/function, 3 levels nesting. Each component handles one responsibility.

---

## Task 1: Market Regime Detector

**Acceptance Criteria:**
- [ ] Unit tests pass (4 regimes: bull/bear/transition/consolidation)
- [ ] Integration test shows regime classification from real RCA results
- [ ] No function > 30 lines
- [ ] Identifies correct regime from market metrics
- [ ] Code compiles without warnings

**Files:**
- Create: `python/trading_backtest/regime.py`
- Test: `tests/unit/trading_backtest/test_regime.py`
- E2E Test: `tests/integration/test_regime_detection_e2e.py`

**Purpose:** RegimeDetector analyzes market metrics (average return, volatility, trend strength, positive percentage) from RCA analysis to classify current market conditions. Used to select appropriate strategy.

**Step 1: Write failing unit tests**

```python
# tests/unit/trading_backtest/test_regime.py
import pytest
from trading_backtest.regime import RegimeDetector, MarketRegime

def test_detect_bull_regime():
    """Bull: high returns (>10%), positive majority (>60%), low volatility (<20%)"""
    detector = RegimeDetector()
    metrics = {
        'avg_return': 0.15,      # +15%
        'volatility': 0.15,       # 15%
        'positive_pct': 0.75,     # 75% of stocks up
        'momentum': 0.20,         # +20% vs prior month
    }
    regime = detector.classify(metrics)
    assert regime == MarketRegime.BULL

def test_detect_bear_regime():
    """Bear: negative returns (<-5%), majority down (<40%), high volatility (>25%)"""
    detector = RegimeDetector()
    metrics = {
        'avg_return': -0.10,      # -10%
        'volatility': 0.30,       # 30%
        'positive_pct': 0.25,     # 25% up
        'momentum': -0.15,        # -15%
    }
    regime = detector.classify(metrics)
    assert regime == MarketRegime.BEAR

def test_detect_transition_regime():
    """Transition: mixed signals (5-10% return, 40-60% positive)"""
    detector = RegimeDetector()
    metrics = {
        'avg_return': 0.07,       # +7%
        'volatility': 0.18,       # 18%
        'positive_pct': 0.55,     # 55% up
        'momentum': 0.05,         # +5%
    }
    regime = detector.classify(metrics)
    assert regime == MarketRegime.TRANSITION

def test_detect_consolidation_regime():
    """Consolidation: very low returns (<2%), balanced (45-55%), low volatility"""
    detector = RegimeDetector()
    metrics = {
        'avg_return': 0.01,       # +1%
        'volatility': 0.10,       # 10%
        'positive_pct': 0.50,     # 50% up
        'momentum': 0.00,         # flat
    }
    regime = detector.classify(metrics)
    assert regime == MarketRegime.CONSOLIDATION
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/birger/code/SiliconDB2
pytest tests/unit/trading_backtest/test_regime.py -v
# Expected: FAILED - MarketRegime not defined, RegimeDetector not defined
```

**Step 3: Implement RegimeDetector**

```python
# python/trading_backtest/regime.py
from enum import Enum
from dataclasses import dataclass
from typing import Dict

class MarketRegime(Enum):
    """Market regime classification."""
    BULL = "bull"
    BEAR = "bear"
    TRANSITION = "transition"
    CONSOLIDATION = "consolidation"


@dataclass
class MarketMetrics:
    """Metrics for regime detection."""
    avg_return: float          # average return across stocks
    volatility: float          # portfolio volatility
    positive_pct: float        # % of stocks with positive returns
    momentum: float            # momentum signal (current vs prior)


class RegimeDetector:
    """Detects market regime from price/belief metrics."""

    def classify(self, metrics: Dict[str, float]) -> MarketRegime:
        """
        Classify market regime based on metrics.

        Returns: MarketRegime enum value
        """
        avg_ret = metrics['avg_return']
        vol = metrics['volatility']
        pos_pct = metrics['positive_pct']

        # Bull: high returns, positive majority, lower volatility
        if avg_ret > 0.10 and pos_pct > 0.60 and vol < 0.20:
            return MarketRegime.BULL

        # Bear: negative returns, majority down, high volatility
        if avg_ret < -0.05 and pos_pct < 0.40 and vol > 0.25:
            return MarketRegime.BEAR

        # Consolidation: minimal returns, balanced, low volatility
        if -0.02 <= avg_ret <= 0.02 and 0.45 <= pos_pct <= 0.55 and vol < 0.12:
            return MarketRegime.CONSOLIDATION

        # Transition: everything else
        return MarketRegime.TRANSITION
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/trading_backtest/test_regime.py -v
# Expected: PASSED (4 tests)
```

**Step 5: Write E2E test**

```python
# tests/integration/test_regime_detection_e2e.py
import pytest
import yfinance as yf
import numpy as np
from trading_backtest.regime import RegimeDetector
from trading_backtest.rca import RCAEngine

def test_regime_detection_from_real_data():
    """Test regime detection from real market data (Jan-Sep 2025)."""
    detector = RegimeDetector()

    # Fetch real data
    symbols = ["NVDA", "AVGO", "NFLX", "META", "GOOGL"]
    returns = []

    for symbol in symbols:
        data = yf.download(symbol, start="2025-01-01", end="2025-09-30", progress=False)
        prices = data['Close'].values.flatten()
        ret = (prices[-1] - prices[0]) / prices[0]
        returns.append(ret)

    # Calculate metrics
    avg_return = np.mean(returns)
    volatility = np.std(returns)
    positive_count = sum(1 for r in returns if r > 0)
    positive_pct = positive_count / len(returns)

    metrics = {
        'avg_return': avg_return,
        'volatility': volatility,
        'positive_pct': positive_pct,
        'momentum': avg_return,  # simplified
    }

    regime = detector.classify(metrics)

    # H1 2025 was bullish: high returns, most stocks up
    assert regime in ["BULL", "TRANSITION"]  # Flexible for market variance
    assert avg_return > 0  # Markets were up overall
```

**Step 6: Verify acceptance criteria**

- [ ] Unit tests pass (4 regime classifications)
- [ ] E2E test passes with real data
- [ ] RegimeDetector.classify() < 20 lines
- [ ] No warnings, clean code

**Step 7: Commit**

```bash
git add python/trading_backtest/regime.py tests/unit/trading_backtest/test_regime.py tests/integration/test_regime_detection_e2e.py
git commit -m "feat: market regime detector (bull/bear/transition/consolidation)"
```

---

## Task 2: Strategy Evaluator & Selector

**Acceptance Criteria:**
- [ ] Unit tests pass (scores all 7 strategies correctly)
- [ ] Integration test shows strategy selection from regime
- [ ] StrategyScore dataclass tracks performance metrics
- [ ] No function > 30 lines
- [ ] Selects kelly+monthly-rebalance for bull regime

**Files:**
- Create: `python/trading_backtest/strategy_selector.py`
- Test: `tests/unit/trading_backtest/test_strategy_selector.py`
- E2E Test: `tests/integration/test_strategy_selection_e2e.py`

**Purpose:** StrategySelector scores all 7 strategies against current market regime using historical performance data from 2025 backtest. Returns ranked list with confidence scores.

**Step 1: Write failing unit tests**

```python
# tests/unit/trading_backtest/test_strategy_selector.py
import pytest
from trading_backtest.strategy_selector import StrategySelector, StrategyScore
from trading_backtest.regime import MarketRegime

def test_score_kelly_monthly_for_bull():
    """Kelly + monthly rebalance scores highest in bull market."""
    selector = StrategySelector()
    bull_metrics = {
        'return': 0.15,
        'sharpe': 1.5,
        'max_drawdown': -0.08,
    }
    scores = selector.score_all_strategies(MarketRegime.BULL, bull_metrics)

    kelly_monthly = [s for s in scores if s.name == 'kelly_monthly_rebalance'][0]
    equal_weight = [s for s in scores if s.name == 'equal_weight'][0]

    assert kelly_monthly.score > equal_weight.score

def test_score_inverse_hedge_for_bear():
    """Inverse hedge scores higher in bear market."""
    selector = StrategySelector()
    bear_metrics = {
        'return': -0.05,
        'sharpe': -0.5,
        'max_drawdown': -0.25,
    }
    scores = selector.score_all_strategies(MarketRegime.BEAR, bear_metrics)

    kelly_inverse = [s for s in scores if s.name == 'kelly_inverse_hedge'][0]
    equal_weight = [s for s in scores if s.name == 'equal_weight'][0]

    assert kelly_inverse.score > equal_weight.score

def test_returns_all_seven_strategies():
    """Selector returns exactly 7 strategies, ranked by score."""
    selector = StrategySelector()
    bull_metrics = {'return': 0.15, 'sharpe': 1.5, 'max_drawdown': -0.08}
    scores = selector.score_all_strategies(MarketRegime.BULL, bull_metrics)

    assert len(scores) == 7
    assert all(isinstance(s, StrategyScore) for s in scores)
    # Scores should be descending
    for i in range(len(scores) - 1):
        assert scores[i].score >= scores[i+1].score
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/trading_backtest/test_strategy_selector.py -v
# Expected: FAILED - StrategySelector not defined
```

**Step 3: Implement StrategySelector**

```python
# python/trading_backtest/strategy_selector.py
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/trading_backtest/test_strategy_selector.py -v
# Expected: PASSED (3 tests)
```

**Step 5: Write E2E test**

```python
# tests/integration/test_strategy_selection_e2e.py
import pytest
from trading_backtest.strategy_selector import StrategySelector
from trading_backtest.regime import RegimeDetector, MarketRegime

def test_strategy_selection_pipeline():
    """Full pipeline: detect regime → score strategies → recommend best."""
    detector = RegimeDetector()
    selector = StrategySelector()

    # Bull market metrics
    bull_metrics = {
        'avg_return': 0.15,
        'volatility': 0.15,
        'positive_pct': 0.75,
        'momentum': 0.20,
    }

    # Detect regime
    regime = detector.classify(bull_metrics)
    assert regime == MarketRegime.BULL

    # Score strategies for this regime
    scores = selector.score_all_strategies(regime, bull_metrics)
    best_strategy = scores[0]

    # Best strategy for bull should be kelly_monthly_rebalance
    assert best_strategy.name == 'kelly_monthly_rebalance'
    assert best_strategy.score > 70
    assert best_strategy.confidence > 0.8
```

**Step 6: Verify acceptance criteria**

- [ ] Unit tests pass (7 strategies scored)
- [ ] E2E test passes (regime → strategy selection)
- [ ] StrategySelector.score_all_strategies() < 25 lines
- [ ] Correct strategy selected for each regime

**Step 7: Commit**

```bash
git add python/trading_backtest/strategy_selector.py tests/unit/trading_backtest/test_strategy_selector.py tests/integration/test_strategy_selection_e2e.py
git commit -m "feat: strategy selector with regime-based scoring"
```

---

## Task 3: Portfolio Composer (Weight Calculation)

**Acceptance Criteria:**
- [ ] Unit tests pass (validates weights sum to 100%)
- [ ] Integration test shows weights from epistemic beliefs
- [ ] Respects Kelly Criterion sizing (max 30% per stock)
- [ ] PortfolioWeights dataclass tracks allocations
- [ ] No function > 30 lines

**Files:**
- Create: `python/trading_backtest/portfolio_composer.py`
- Modify: `python/trading_backtest/epistemic.py` (add export for current beliefs)
- Test: `tests/unit/trading_backtest/test_portfolio_composer.py`
- E2E Test: `tests/integration/test_portfolio_composition_e2e.py`

**Purpose:** PortfolioComposer takes epistemic beliefs about each stock and Kelly-sizes positions. Enforces constraints: max 30% per stock, weights sum to 100%, minimum 5% shorts for hedging.

**Step 1: Write failing unit tests**

```python
# tests/unit/trading_backtest/test_portfolio_composer.py
import pytest
from trading_backtest.portfolio_composer import PortfolioComposer, PortfolioWeights
from trading_backtest.epistemic import Belief, BeliefType

def test_weights_sum_to_100_percent():
    """Portfolio weights should sum to 100%."""
    composer = PortfolioComposer()

    beliefs = {
        'NVDA': Belief('NVDA', 'return', BeliefType.HIGH_GROWTH, 0.85),
        'AVGO': Belief('AVGO', 'return', BeliefType.HIGH_GROWTH, 0.80),
        'CRM': Belief('CRM', 'return', BeliefType.DECLINING, 0.75),
        'NFLX': Belief('NFLX', 'return', BeliefType.STABLE, 0.70),
    }

    weights = composer.compose(beliefs, strategy='kelly_monthly_rebalance')

    total = sum(abs(w.weight) for w in weights.allocations)
    assert abs(total - 1.0) < 0.01  # Allow 1% rounding error

def test_respects_kelly_max_per_stock():
    """No single position exceeds 30% (Kelly max)."""
    composer = PortfolioComposer()

    beliefs = {
        'NVDA': Belief('NVDA', 'return', BeliefType.HIGH_GROWTH, 0.95),
        'AVGO': Belief('AVGO', 'return', BeliefType.STABLE, 0.50),
    }

    weights = composer.compose(beliefs, strategy='kelly_monthly_rebalance')

    for alloc in weights.allocations:
        assert abs(alloc.weight) <= 0.30

def test_shorts_for_declining_beliefs():
    """Declining beliefs should result in short positions."""
    composer = PortfolioComposer()

    beliefs = {
        'NVDA': Belief('NVDA', 'return', BeliefType.HIGH_GROWTH, 0.85),
        'CRM': Belief('CRM', 'return', BeliefType.DECLINING, 0.80),
    }

    weights = composer.compose(beliefs, strategy='kelly_monthly_rebalance')

    nvda_weight = [a for a in weights.allocations if a.symbol == 'NVDA'][0]
    crm_weight = [a for a in weights.allocations if a.symbol == 'CRM'][0]

    assert nvda_weight.weight > 0  # Long
    assert crm_weight.weight < 0   # Short
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/trading_backtest/test_portfolio_composer.py -v
# Expected: FAILED - PortfolioComposer not defined
```

**Step 3: Implement PortfolioComposer**

```python
# python/trading_backtest/portfolio_composer.py
from dataclasses import dataclass
from typing import Dict, List
import numpy as np
from trading_backtest.epistemic import Belief, BeliefType


@dataclass
class Allocation:
    """Single stock allocation."""
    symbol: str
    weight: float              # -1.0 to +1.0 (negative = short)
    belief_type: str           # HIGH_GROWTH, STABLE, DECLINING, etc.
    confidence: float          # 0-1 confidence in this allocation


@dataclass
class PortfolioWeights:
    """Complete portfolio allocation."""
    allocations: List[Allocation]
    total_long: float          # sum of positive weights
    total_short: float         # sum of absolute short weights
    net_exposure: float        # long - short
    strategy: str              # which strategy generated this


class PortfolioComposer:
    """Composes portfolio weights from epistemic beliefs using Kelly Criterion."""

    KELLY_MAX = 0.30           # Max 30% per position
    MIN_CONVICTION = 0.50      # Min confidence to trade

    def compose(self, beliefs: Dict[str, Belief],
                strategy: str) -> PortfolioWeights:
        """
        Compose portfolio from beliefs using strategy rules.
        Returns normalized weights summing to 100%.
        """
        allocations = []
        raw_weights = {}

        for symbol, belief in beliefs.items():
            if belief.probability < self.MIN_CONVICTION:
                continue  # Skip low-conviction beliefs

            # Kelly size based on belief type
            kelly_weight = self._kelly_size(belief)
            raw_weights[symbol] = kelly_weight

        if not raw_weights:
            return PortfolioWeights([], 0, 0, 0, strategy)

        # Normalize to 100% exposure
        total_abs = sum(abs(w) for w in raw_weights.values())

        for symbol, raw_weight in raw_weights.items():
            normalized = raw_weight / total_abs if total_abs > 0 else 0
            # Clamp to Kelly max
            clamped = max(-self.KELLY_MAX, min(self.KELLY_MAX, normalized))

            belief = beliefs[symbol]
            allocations.append(Allocation(
                symbol=symbol,
                weight=clamped,
                belief_type=belief.belief_type.value,
                confidence=belief.probability,
            ))

        # Recalculate totals after clamping
        total_long = sum(max(0, a.weight) for a in allocations)
        total_short = sum(abs(min(0, a.weight)) for a in allocations)

        return PortfolioWeights(
            allocations=allocations,
            total_long=total_long,
            total_short=total_short,
            net_exposure=total_long - total_short,
            strategy=strategy,
        )

    def _kelly_size(self, belief: Belief) -> float:
        """
        Calculate Kelly position size from belief.
        Positive for HIGH_GROWTH, negative for DECLINING.
        """
        # Map belief type to direction
        direction_map = {
            BeliefType.HIGH_GROWTH: 1.0,
            BeliefType.STABLE: 0.2,
            BeliefType.RECOVERY: 0.5,
            BeliefType.DECLINING: -1.0,
        }

        direction = direction_map.get(belief.belief_type, 0)
        confidence = belief.probability

        # Kelly formula simplified: f = (p - q) / b where b=1 (even odds)
        # Adjusted for confidence
        kelly_frac = (2 * confidence - 1) * direction

        return kelly_frac * self.KELLY_MAX
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/trading_backtest/test_portfolio_composer.py -v
# Expected: PASSED (3 tests)
```

**Step 5: Write E2E test**

```python
# tests/integration/test_portfolio_composition_e2e.py
import pytest
from trading_backtest.portfolio_composer import PortfolioComposer
from trading_backtest.epistemic import Belief, BeliefType

def test_portfolio_composition_from_real_beliefs():
    """Test portfolio composition from actual market beliefs."""
    composer = PortfolioComposer()

    # Beliefs from H1 2025 backtest
    beliefs = {
        'NVDA': Belief('NVDA', 'return', BeliefType.HIGH_GROWTH, 0.85),
        'AVGO': Belief('AVGO', 'return', BeliefType.HIGH_GROWTH, 0.80),
        'NFLX': Belief('NFLX', 'return', BeliefType.HIGH_GROWTH, 0.75),
        'META': Belief('META', 'return', BeliefType.STABLE, 0.70),
        'CRM': Belief('CRM', 'return', BeliefType.DECLINING, 0.75),
    }

    weights = composer.compose(beliefs, strategy='kelly_monthly_rebalance')

    # Should be long biased in bull market
    assert weights.net_exposure > 0

    # Should have shorts (CRM declining)
    assert weights.total_short > 0

    # All weights should sum properly
    total = weights.total_long + weights.total_short
    assert total > 0.8  # At least 80% deployed
```

**Step 6: Verify acceptance criteria**

- [ ] Weights sum to 100% (within 1% rounding)
- [ ] No position exceeds 30% Kelly max
- [ ] Declining beliefs short
- [ ] High growth beliefs long
- [ ] _kelly_size() < 15 lines

**Step 7: Commit**

```bash
git add python/trading_backtest/portfolio_composer.py tests/unit/trading_backtest/test_portfolio_composer.py tests/integration/test_portfolio_composition_e2e.py
git commit -m "feat: portfolio composer using Kelly Criterion and epistemic beliefs"
```

---

## Task 4: Execution Plan Generator

**Acceptance Criteria:**
- [ ] Unit tests pass (generates correct buy/sell orders)
- [ ] Integration test shows execution from portfolio weights
- [ ] ExecutionPlan includes current positions, target positions, deltas
- [ ] Orders respect market open/close times
- [ ] No function > 25 lines

**Files:**
- Create: `python/trading_backtest/execution.py`
- Test: `tests/unit/trading_backtest/test_execution.py`
- E2E Test: `tests/integration/test_execution_e2e.py`

**Purpose:** ExecutionGenerator converts portfolio target weights into actionable buy/sell orders, respecting current holdings and calculating order sizes.

**Step 1: Write failing unit tests**

```python
# tests/unit/trading_backtest/test_execution.py
import pytest
from datetime import datetime
from trading_backtest.execution import ExecutionGenerator, ExecutionOrder, OrderType
from trading_backtest.portfolio_composer import Allocation, PortfolioWeights

def test_generates_buy_orders_for_new_positions():
    """Buy orders for positions not currently held."""
    gen = ExecutionGenerator(portfolio_value=100_000)

    current = {'NVDA': 0}  # Not held
    target = PortfolioWeights([
        Allocation('NVDA', 0.20, 'HIGH_GROWTH', 0.85),  # Want 20%
    ], 0.20, 0, 0.20, 'kelly_monthly')

    orders = gen.generate(current, target)

    nvda_orders = [o for o in orders if o.symbol == 'NVDA']
    assert len(nvda_orders) == 1
    assert nvda_orders[0].order_type == OrderType.BUY
    assert nvda_orders[0].quantity > 0

def test_generates_sell_orders_to_reduce_positions():
    """Sell orders for position sizing down."""
    gen = ExecutionGenerator(portfolio_value=100_000)

    current = {'NVDA': 0.30}  # Currently 30%
    target = PortfolioWeights([
        Allocation('NVDA', 0.15, 'HIGH_GROWTH', 0.85),  # Reduce to 15%
    ], 0.15, 0, 0.15, 'kelly_monthly')

    orders = gen.generate(current, target)

    nvda_orders = [o for o in orders if o.symbol == 'NVDA']
    assert len(nvda_orders) == 1
    assert nvda_orders[0].order_type == OrderType.SELL

def test_no_order_for_unchanged_positions():
    """No order if position already at target."""
    gen = ExecutionGenerator(portfolio_value=100_000)

    current = {'NVDA': 0.20}  # Already 20%
    target = PortfolioWeights([
        Allocation('NVDA', 0.20, 'HIGH_GROWTH', 0.85),  # Same
    ], 0.20, 0, 0.20, 'kelly_monthly')

    orders = gen.generate(current, target)

    # Should be empty or only cash rebalancing
    assert len(orders) == 0 or all(o.symbol == 'CASH' for o in orders)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/trading_backtest/test_execution.py -v
# Expected: FAILED - ExecutionGenerator not defined
```

**Step 3: Implement ExecutionGenerator**

```python
# python/trading_backtest/execution.py
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import Dict, List
from trading_backtest.portfolio_composer import PortfolioWeights


class OrderType(Enum):
    """Order direction."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class ExecutionOrder:
    """Single execution order."""
    symbol: str
    order_type: OrderType
    quantity: int              # shares
    target_weight: float       # desired portfolio weight
    current_weight: float      # current portfolio weight
    priority: int              # 1=high, 3=low
    timestamp: datetime = None


class ExecutionPlan:
    """Complete execution plan."""
    orders: List[ExecutionOrder]
    estimated_turnover: float  # % of portfolio to trade
    estimated_cost: float      # estimated transaction costs
    estimated_time: str        # "< 5 min", "< 1 hour", etc.


class ExecutionGenerator:
    """Generates execution orders from portfolio target weights."""

    REBALANCE_THRESHOLD = 0.02  # Only reorder if > 2% drift

    def __init__(self, portfolio_value: float, current_prices: Dict[str, float] = None):
        """
        Initialize with portfolio value and optional current prices.

        Args:
            portfolio_value: Total portfolio value in dollars
            current_prices: Dict of symbol -> current price (defaults to $100)
        """
        self.portfolio_value = portfolio_value
        self.current_prices = current_prices or {}

    def generate(self, current_weights: Dict[str, float],
                 target_weights: PortfolioWeights) -> List[ExecutionOrder]:
        """
        Generate execution orders from current to target weights.

        Returns: List of orders sorted by priority (highest first)
        """
        orders = []

        # Process target positions
        for allocation in target_weights.allocations:
            symbol = allocation.symbol
            target = allocation.weight
            current = current_weights.get(symbol, 0)

            # Skip if within rebalance threshold
            if abs(target - current) < self.REBALANCE_THRESHOLD:
                continue

            # Determine order type
            if target > current:
                order_type = OrderType.BUY
            else:
                order_type = OrderType.SELL

            # Calculate quantity (simplified: assumes $100/share)
            price = self.current_prices.get(symbol, 100.0)
            dollar_amount = abs(target - current) * self.portfolio_value
            quantity = int(dollar_amount / price)

            # Priority based on conviction
            priority = 1 if allocation.confidence > 0.80 else 2
            if abs(target - current) < 0.05:
                priority = 3

            orders.append(ExecutionOrder(
                symbol=symbol,
                order_type=order_type,
                quantity=quantity,
                target_weight=target,
                current_weight=current,
                priority=priority,
            ))

        # Process positions to close (not in target)
        for symbol, current in current_weights.items():
            if current > 0 and symbol not in [a.symbol for a in target_weights.allocations]:
                orders.append(ExecutionOrder(
                    symbol=symbol,
                    order_type=OrderType.SELL,
                    quantity=int(current * self.portfolio_value / 100),
                    target_weight=0,
                    current_weight=current,
                    priority=2,
                ))

        # Sort by priority
        return sorted(orders, key=lambda o: o.priority)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/trading_backtest/test_execution.py -v
# Expected: PASSED (3 tests)
```

**Step 5: Write E2E test**

```python
# tests/integration/test_execution_e2e.py
import pytest
from trading_backtest.execution import ExecutionGenerator, OrderType
from trading_backtest.portfolio_composer import Allocation, PortfolioWeights

def test_execution_from_portfolio_weights():
    """Test execution generation from real portfolio weights."""
    gen = ExecutionGenerator(
        portfolio_value=100_000,
        current_prices={'NVDA': 120, 'AVGO': 150, 'CRM': 90}
    )

    current_weights = {'NVDA': 0.10}  # 10% in NVDA

    target_weights = PortfolioWeights([
        Allocation('NVDA', 0.25, 'HIGH_GROWTH', 0.85),   # Buy to 25%
        Allocation('AVGO', 0.20, 'HIGH_GROWTH', 0.80),   # New position
        Allocation('CRM', -0.05, 'DECLINING', 0.75),     # Short
    ], 0.45, 0.05, 0.40, 'kelly_monthly')

    orders = gen.generate(current_weights, target_weights)

    # Should have buy orders for NVDA increase and AVGO new
    buy_orders = [o for o in orders if o.order_type == OrderType.BUY]
    assert len(buy_orders) >= 2

    # Should have sell order for CRM short
    sell_orders = [o for o in orders if o.order_type == OrderType.SELL]
    assert len(sell_orders) >= 1

    # Orders should be sorted by priority
    if len(orders) > 1:
        for i in range(len(orders) - 1):
            assert orders[i].priority <= orders[i+1].priority
```

**Step 6: Verify acceptance criteria**

- [ ] Buy orders for increasing positions
- [ ] Sell orders for decreasing positions
- [ ] No orders for unchanged positions
- [ ] Orders sorted by priority
- [ ] generate() < 25 lines

**Step 7: Commit**

```bash
git add python/trading_backtest/execution.py tests/unit/trading_backtest/test_execution.py tests/integration/test_execution_e2e.py
git commit -m "feat: execution plan generator from portfolio target weights"
```

---

## Task 5: Automation Controller (Main Orchestrator)

**Acceptance Criteria:**
- [ ] Unit tests pass (orchestrates full pipeline)
- [ ] Integration test runs full end-to-end
- [ ] AutomationResult dataclass captures outcome
- [ ] Handles all error cases gracefully
- [ ] No function > 30 lines

**Files:**
- Create: `python/trading_backtest/automation.py`
- Modify: `python/run_autonomous_portfolio.py` (main entry point)
- Test: `tests/unit/trading_backtest/test_automation.py`
- E2E Test: `tests/integration/test_automation_e2e.py`

**Purpose:** AutomationController orchestrates the full pipeline: (1) fetch current data, (2) run RCA analysis, (3) detect regime, (4) select strategy, (5) compose portfolio, (6) generate execution plan. Returns automated recommendations.

**Step 1: Write failing unit tests**

```python
# tests/unit/trading_backtest/test_automation.py
import pytest
from datetime import datetime
from trading_backtest.automation import AutomationController, AutomationResult

def test_generates_complete_recommendation():
    """Controller generates complete strategy recommendation."""
    controller = AutomationController(
        symbols=['NVDA', 'AVGO', 'NFLX', 'META', 'CRM'],
        portfolio_value=100_000
    )

    result = controller.run()

    assert result is not None
    assert result.regime in ['BULL', 'BEAR', 'TRANSITION', 'CONSOLIDATION']
    assert result.selected_strategy is not None
    assert len(result.execution_orders) > 0
    assert result.timestamp is not None

def test_handles_missing_data_gracefully():
    """Controller handles API failures gracefully."""
    controller = AutomationController(
        symbols=['FAKE_SYMBOL_XYZ'],
        portfolio_value=100_000
    )

    result = controller.run()

    # Should not crash, should return error state
    assert result is not None
    assert result.success == False
    assert result.error_message is not None

def test_returns_all_required_fields():
    """Result includes all required fields for trading."""
    controller = AutomationController(
        symbols=['NVDA', 'AVGO'],
        portfolio_value=50_000
    )

    result = controller.run()

    if result.success:
        assert result.regime is not None
        assert result.selected_strategy is not None
        assert result.portfolio_weights is not None
        assert result.execution_orders is not None
        assert result.confidence_score > 0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/trading_backtest/test_automation.py -v
# Expected: FAILED - AutomationController not defined
```

**Step 3: Implement AutomationController**

```python
# python/trading_backtest/automation.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
import yfinance as yf
import numpy as np

from trading_backtest.regime import RegimeDetector, MarketRegime
from trading_backtest.strategy_selector import StrategySelector
from trading_backtest.portfolio_composer import PortfolioComposer, PortfolioWeights
from trading_backtest.execution import ExecutionGenerator, ExecutionOrder
from trading_backtest.epistemic import EpistemicEngine, Belief, BeliefType
from trading_backtest.rca import RCAEngine


@dataclass
class AutomationResult:
    """Result of autonomous portfolio analysis."""
    success: bool
    timestamp: datetime
    regime: Optional[str] = None
    market_metrics: Dict = field(default_factory=dict)
    selected_strategy: Optional[str] = None
    strategy_confidence: float = 0.0
    portfolio_weights: Optional[PortfolioWeights] = None
    execution_orders: List[ExecutionOrder] = field(default_factory=list)
    confidence_score: float = 0.0  # 0-100
    error_message: Optional[str] = None


class AutomationController:
    """Orchestrates autonomous portfolio selection pipeline."""

    def __init__(self, symbols: List[str], portfolio_value: float,
                 current_positions: Dict[str, float] = None):
        """
        Initialize controller.

        Args:
            symbols: Stocks to analyze
            portfolio_value: Total portfolio value
            current_positions: Dict of symbol -> current weight (0-1)
        """
        self.symbols = symbols
        self.portfolio_value = portfolio_value
        self.current_positions = current_positions or {}

        # Initialize engines
        self.regime_detector = RegimeDetector()
        self.strategy_selector = StrategySelector()
        self.portfolio_composer = PortfolioComposer()
        self.execution_gen = ExecutionGenerator(portfolio_value)
        self.epistemic = EpistemicEngine()

    def run(self) -> AutomationResult:
        """
        Run full autonomous portfolio analysis pipeline.

        Returns: AutomationResult with recommendations
        """
        try:
            # Step 1: Fetch data and analyze
            beliefs = self._analyze_stocks()
            if not beliefs:
                return AutomationResult(
                    success=False,
                    timestamp=datetime.now(),
                    error_message="No valid stock data fetched"
                )

            # Step 2: Detect market regime
            metrics = self._calculate_metrics(beliefs)
            regime = self.regime_detector.classify(metrics)

            # Step 3: Select strategy
            strategy_scores = self.strategy_selector.score_all_strategies(regime, metrics)
            best_strategy = strategy_scores[0]

            # Step 4: Compose portfolio
            portfolio_weights = self.portfolio_composer.compose(
                beliefs,
                strategy=best_strategy.name
            )

            # Step 5: Generate execution plan
            execution_orders = self.execution_gen.generate(
                self.current_positions,
                portfolio_weights
            )

            # Calculate overall confidence
            strategy_confidence = best_strategy.confidence
            avg_belief_confidence = np.mean([b.probability for b in beliefs.values()])
            overall_confidence = (strategy_confidence * 0.6) + (avg_belief_confidence * 0.4)

            return AutomationResult(
                success=True,
                timestamp=datetime.now(),
                regime=regime.value,
                market_metrics=metrics,
                selected_strategy=best_strategy.name,
                strategy_confidence=strategy_confidence,
                portfolio_weights=portfolio_weights,
                execution_orders=execution_orders,
                confidence_score=overall_confidence * 100,
            )

        except Exception as e:
            return AutomationResult(
                success=False,
                timestamp=datetime.now(),
                error_message=str(e)
            )

    def _analyze_stocks(self) -> Dict[str, Belief]:
        """Fetch data and create epistemic beliefs for each stock."""
        beliefs = {}

        for symbol in self.symbols:
            try:
                data = yf.download(symbol, start="2025-01-01", end="2025-09-30", progress=False)
                if len(data) < 10:
                    continue

                prices = data['Close'].values.flatten()
                returns = np.diff(prices) / prices[:-1]

                period_return = (prices[-1] - prices[0]) / prices[0]
                volatility = np.std(returns)

                # Classify belief
                if period_return > 0.20:
                    belief_type = BeliefType.HIGH_GROWTH
                    confidence = min(0.95, 0.7 + (period_return / 0.3))
                elif period_return > 0.05:
                    belief_type = BeliefType.STABLE
                    confidence = 0.65
                elif period_return > 0:
                    belief_type = BeliefType.RECOVERY
                    confidence = 0.60
                else:
                    belief_type = BeliefType.DECLINING
                    confidence = min(0.95, 0.7 + abs(period_return))

                belief = Belief(symbol, 'return', belief_type, confidence)
                self.epistemic.add_belief(belief)
                beliefs[symbol] = belief

            except Exception:
                continue  # Skip on error

        return beliefs

    def _calculate_metrics(self, beliefs: Dict[str, Belief]) -> Dict:
        """Calculate market metrics from beliefs."""
        returns = []

        for belief in beliefs.values():
            if belief.belief_type == BeliefType.HIGH_GROWTH:
                returns.append(0.15)
            elif belief.belief_type == BeliefType.STABLE:
                returns.append(0.07)
            elif belief.belief_type == BeliefType.RECOVERY:
                returns.append(0.03)
            else:
                returns.append(-0.10)

        if not returns:
            returns = [0]

        avg_return = np.mean(returns)
        volatility = np.std(returns) if len(returns) > 1 else 0.15

        positive_count = sum(1 for b in beliefs.values()
                           if b.belief_type in [BeliefType.HIGH_GROWTH, BeliefType.STABLE])
        positive_pct = positive_count / len(beliefs) if beliefs else 0.5

        return {
            'return': avg_return,
            'volatility': volatility,
            'positive_pct': positive_pct,
            'sharpe': avg_return / max(volatility, 0.01),
        }
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/trading_backtest/test_automation.py -v
# Expected: PASSED (3 tests)
```

**Step 5: Write E2E test**

```python
# tests/integration/test_automation_e2e.py
import pytest
from trading_backtest.automation import AutomationController

def test_full_autonomous_pipeline():
    """Test complete automation pipeline."""
    controller = AutomationController(
        symbols=['NVDA', 'AVGO', 'NFLX', 'META', 'CRM'],
        portfolio_value=100_000
    )

    result = controller.run()

    assert result.success
    assert result.regime in ['BULL', 'BEAR', 'TRANSITION', 'CONSOLIDATION']
    assert result.selected_strategy in [
        'kelly_monthly_rebalance',
        'kelly_inverse_hedge',
        'equal_weight_inverse_hedge',
        'kelly_dynamic_hedge',
        'belief_weighted',
        'stop_loss_20pct',
        'equal_weight',
    ]
    assert result.confidence_score > 0
    assert result.confidence_score <= 100
    assert len(result.execution_orders) > 0
```

**Step 6: Verify acceptance criteria**

- [ ] Full pipeline runs successfully
- [ ] Detects regime correctly
- [ ] Selects best strategy
- [ ] Generates execution orders
- [ ] Error handling works (returns success=False)
- [ ] _analyze_stocks() < 25 lines
- [ ] _calculate_metrics() < 20 lines

**Step 7: Commit**

```bash
git add python/trading_backtest/automation.py tests/unit/trading_backtest/test_automation.py tests/integration/test_automation_e2e.py
git commit -m "feat: automation controller - full autonomous pipeline orchestration"
```

---

## Task 6: Command-Line Interface & Main Entry Point

**Acceptance Criteria:**
- [ ] Script runs without errors
- [ ] Outputs readable strategy recommendation
- [ ] Accepts command-line arguments (symbols, portfolio value)
- [ ] Can be run daily as cron job
- [ ] Includes markdown output for reporting

**Files:**
- Create: `python/run_autonomous_portfolio.py`
- Create: `python/run_autonomous_portfolio_daily.sh`
- Test: `tests/integration/test_main_cli_e2e.py`

**Purpose:** Main entry point that runs AutomationController and displays formatted output. Can be scheduled as daily job.

**Step 1: Implement main script**

```python
# python/run_autonomous_portfolio.py
#!/usr/bin/env python3
"""
Autonomous Portfolio & Strategy Selection System

Run daily to get automated portfolio recommendations without manual analysis.
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from trading_backtest.automation import AutomationController


def format_result(result):
    """Format automation result as readable output."""
    print("\n" + "="*70)
    print("🤖 AUTONOMOUS PORTFOLIO ANALYZER")
    print("="*70)
    print(f"\nGenerated: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    if not result.success:
        print(f"\n❌ Error: {result.error_message}")
        return

    print(f"\n📊 MARKET ANALYSIS")
    print(f"  Regime: {result.regime.upper()}")
    print(f"  Return: {result.market_metrics.get('return', 0):+.1%}")
    print(f"  Volatility: {result.market_metrics.get('volatility', 0):.1%}")
    print(f"  Positive: {result.market_metrics.get('positive_pct', 0):.0%}")

    print(f"\n🎯 STRATEGY RECOMMENDATION")
    print(f"  Selected: {result.selected_strategy}")
    print(f"  Confidence: {result.confidence_score:.0f}%")
    print(f"  Expected Return: {result.portfolio_weights.allocations[0].weight * 100:+.0f}%")

    print(f"\n📍 PORTFOLIO ALLOCATION")
    print(f"  Long Exposure: +{result.portfolio_weights.total_long:.0%}")
    print(f"  Short Exposure: -{result.portfolio_weights.total_short:.0%}")
    print(f"  Net Exposure: {result.portfolio_weights.net_exposure:+.0%}")

    print(f"\n⚡ EXECUTION PLAN ({len(result.execution_orders)} orders)")

    buys = [o for o in result.execution_orders if o.order_type.value == 'buy']
    sells = [o for o in result.execution_orders if o.order_type.value == 'sell']

    if buys:
        print(f"\n  BUY:")
        for order in buys[:5]:
            print(f"    • {order.symbol}: {order.quantity} shares @ {order.target_weight:+.0%}")

    if sells:
        print(f"\n  SELL:")
        for order in sells[:5]:
            print(f"    • {order.symbol}: {order.quantity} shares @ {order.target_weight:+.0%}")

    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(description='Autonomous Portfolio Analyzer')
    parser.add_argument('--symbols', type=str, default='NVDA,AVGO,NFLX,META,GOOGL,MSFT,TSLA,CRM,AAPL,AMZN',
                       help='Comma-separated stock symbols')
    parser.add_argument('--portfolio-value', type=float, default=100_000,
                       help='Total portfolio value (default: $100k)')
    parser.add_argument('--output', type=str, default=None,
                       help='Output file (default: stdout)')

    args = parser.parse_args()
    symbols = args.symbols.split(',')

    print(f"Analyzing {len(symbols)} stocks...")

    controller = AutomationController(
        symbols=symbols,
        portfolio_value=args.portfolio_value
    )

    result = controller.run()
    format_result(result)

    if args.output:
        with open(args.output, 'w') as f:
            # Write markdown output
            f.write(f"# Autonomous Portfolio Analysis\n\n")
            f.write(f"**Generated:** {result.timestamp.isoformat()}\n\n")
            f.write(f"## Result\n\n")
            if result.success:
                f.write(f"- **Regime:** {result.regime}\n")
                f.write(f"- **Strategy:** {result.selected_strategy}\n")
                f.write(f"- **Confidence:** {result.confidence_score:.0f}%\n")
            else:
                f.write(f"- **Error:** {result.error_message}\n")


if __name__ == '__main__':
    main()
```

**Step 2: Create cron script**

```bash
#!/bin/bash
# python/run_autonomous_portfolio_daily.sh

# Run autonomous portfolio analyzer every morning at 8 AM
# Add to crontab: 0 8 * * * /Users/birger/code/SiliconDB2/python/run_autonomous_portfolio_daily.sh

set -e
cd /Users/birger/code/SiliconDB2

export PYTHONPATH=/Users/birger/code/SiliconDB2/python:$PYTHONPATH

# Run analyzer
python python/run_autonomous_portfolio.py \
  --symbols "NVDA,AVGO,NFLX,META,GOOGL,MSFT,TSLA,CRM,AAPL,AMZN" \
  --portfolio-value 100000 \
  --output "reports/portfolio_recommendation_$(date +%Y%m%d).md"

echo "✅ Autonomous analysis complete. Report saved."
```

**Step 3: Write E2E test**

```python
# tests/integration/test_main_cli_e2e.py
import pytest
import subprocess
from pathlib import Path

def test_cli_runs_successfully():
    """Test that CLI script runs without errors."""
    result = subprocess.run([
        'python', 'python/run_autonomous_portfolio.py',
        '--symbols', 'NVDA,AVGO',
        '--portfolio-value', '50000',
    ], cwd='/Users/birger/code/SiliconDB2', capture_output=True, text=True)

    assert result.returncode == 0
    assert 'AUTONOMOUS PORTFOLIO' in result.stdout
    assert 'MARKET ANALYSIS' in result.stdout

def test_cli_generates_output_file():
    """Test that CLI can save output to file."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        output_file = f.name

    try:
        result = subprocess.run([
            'python', 'python/run_autonomous_portfolio.py',
            '--symbols', 'NVDA,AVGO',
            '--output', output_file,
        ], cwd='/Users/birger/code/SiliconDB2', capture_output=True, text=True)

        assert result.returncode == 0
        assert Path(output_file).exists()

        with open(output_file) as f:
            content = f.read()
            assert '# Autonomous Portfolio' in content
    finally:
        Path(output_file).unlink()
```

**Step 4: Run E2E test**

```bash
pytest tests/integration/test_main_cli_e2e.py -v
# Expected: PASSED (2 tests)
```

**Step 5: Verify acceptance criteria**

- [ ] CLI runs without errors
- [ ] Outputs readable strategy recommendation
- [ ] Accepts --symbols and --portfolio-value args
- [ ] Can save to markdown file
- [ ] bash script executable and cron-compatible

**Step 6: Commit**

```bash
chmod +x python/run_autonomous_portfolio_daily.sh
git add python/run_autonomous_portfolio.py python/run_autonomous_portfolio_daily.sh tests/integration/test_main_cli_e2e.py
git commit -m "feat: CLI interface for autonomous portfolio analyzer"
```

---

## Test Plan

### Unit Tests
- `tests/unit/trading_backtest/test_regime.py` — Market regime detection (4 regimes)
- `tests/unit/trading_backtest/test_strategy_selector.py` — Strategy scoring and selection (7 strategies)
- `tests/unit/trading_backtest/test_portfolio_composer.py` — Weight calculation with Kelly Criterion
- `tests/unit/trading_backtest/test_execution.py` — Order generation from portfolio targets
- `tests/unit/trading_backtest/test_automation.py` — Full pipeline orchestration

### Integration Tests
- `tests/integration/test_regime_detection_e2e.py` — Regime from real market data
- `tests/integration/test_strategy_selection_e2e.py` — Strategy selection pipeline
- `tests/integration/test_portfolio_composition_e2e.py` — Portfolio composition from beliefs
- `tests/integration/test_execution_e2e.py` — Execution plan generation
- `tests/integration/test_automation_e2e.py` — Full autonomous analysis
- `tests/integration/test_main_cli_e2e.py` — CLI script execution

### Running Tests

```bash
# All tests
pytest tests/

# Unit only (fast)
pytest tests/unit/trading_backtest/test_*.py -v

# Integration only (with real data)
pytest tests/integration/test_*_e2e.py -v

# Specific test
pytest tests/unit/trading_backtest/test_regime.py::test_detect_bull_regime -v
```

---

## Success Metrics

- ✅ **Market regime detection:** Correctly classifies bull/bear/transition/consolidation from market metrics
- ✅ **Strategy selection:** Recommends kelly_monthly_rebalance for bull, kelly_inverse_hedge for bear
- ✅ **Portfolio composition:** Weights sum to 100%, respect Kelly max of 30% per stock
- ✅ **Execution plan:** Generates correct buy/sell orders with priority sorting
- ✅ **Automation:** Full pipeline runs end-to-end with zero manual input
- ✅ **CLI:** Can be run daily via cron with consistent output format

---

## Notes

1. **Regime Detection** uses simple rules (return, volatility, positive percentage). Can be enhanced with machine learning if needed.

2. **Strategy Profiles** are hardcoded from 2025 backtest results. In production, should be updated monthly with live performance data.

3. **Kelly Sizing** uses simplified formula. Production version should include volatility-adjusted payoff ratios.

4. **Execution** assumes $100/share prices as default. In production, fetch real prices from yfinance.

5. **Daily Scheduling** via `run_autonomous_portfolio_daily.sh` can be added to crontab:
   ```bash
   0 8 * * * /Users/birger/code/SiliconDB2/python/run_autonomous_portfolio_daily.sh
   ```

6. **Future Enhancements:**
   - Real-time price feeds instead of yfinance daily downloads
   - Regime detection with ML (Hidden Markov Model)
   - Dynamic strategy profile updates based on live performance
   - Integration with actual trading infrastructure (Alpaca, Interactive Brokers)
   - Risk monitoring and position limit enforcement
   - Slippage and market impact estimation
