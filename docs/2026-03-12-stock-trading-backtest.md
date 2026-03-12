# Stock Trading Backtest Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Backtest a stock trading system using Epistemic Engine (credibility-weighted beliefs), Decision Engine (expected utility maximization), and RCA Engine (root cause analysis) on S&P 500 historical data (2000-2024) with monthly rebalancing.

**Architecture:**
The system maintains probabilistic beliefs about stock valuations by weighting diverse information sources (analyst reports, financial statements, price action, insider trades) by their historical credibility. For each stock, it computes expected utility (return - risk - cost - tax) and recommends top-K stocks to buy. Monthly rebalancing tracks performance vs. predictions, updates source credibilities, and performs RCA when underperformance occurs. Backtesting compares results against buy-and-hold baseline, mean-variance optimization, and random selection.

**Tech Stack:** Python 3.11+, pandas (data), yfinance/yahoo_fin (historical data), numpy (computation), matplotlib/plotly (visualization), pytest (testing), dataclasses (types).

**Clean Code Rules:** Max 300 lines/file, 30 lines/function, 4 params/function, 3 levels nesting.

---

## Task 1: Data Ingestion Layer

**Acceptance Criteria:**
- [ ] Unit tests pass (happy path: fetch S&P 500 list; edge cases: handle missing data, network errors)
- [ ] E2E test passes (fetch 5 years of data for 10 stocks, verify completeness)
- [ ] No function exceeds 30 lines
- [ ] No file exceeds 300 lines
- [ ] Data cache working (avoid re-downloading same data)

**Files:**
- Create: `python/trading_backtest/data.py` — Data ingestion layer
- Create: `python/trading_backtest/types.py` — Dataclasses for StockData, SourceCredibility
- Create: `tests/unit/trading/test_data.py` — Unit tests
- Create: `tests/integration/trading/test_data_e2e.py` — E2E tests

**Step 1: Write failing unit test for S&P 500 list**

```python
# tests/unit/trading/test_data.py
def test_fetch_sp500_constituents():
    """Fetch list of S&P 500 companies"""
    symbols = fetch_sp500_symbols()
    assert len(symbols) >= 500
    assert "AAPL" in symbols
    assert "MSFT" in symbols
```

**Step 2: Run test to verify it fails**

```bash
cd python && pytest tests/unit/trading/test_data.py::test_fetch_sp500_constituents -v
```

Expected: `FAILED - ModuleNotFoundError: No module named 'trading_backtest'`

**Step 3: Create module structure and minimal implementation**

```python
# python/trading_backtest/__init__.py
"""Stock trading backtest system"""

# python/trading_backtest/types.py
from dataclasses import dataclass
from typing import Optional
from datetime import date

@dataclass
class StockData:
    """Historical data for a single stock"""
    symbol: str
    date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int

@dataclass
class SourceCredibility:
    """Credibility score for information source"""
    source_name: str
    trust: float  # Historical accuracy [0, 1]
    recency: float  # Decay by age [0, 1]
    consistency: float  # Agreement with consensus [0, 1]

    @property
    def credibility(self) -> float:
        """Compute composite credibility"""
        return (self.trust ** 0.6) * (self.recency ** 0.2) * (self.consistency ** 0.2)

# python/trading_backtest/data.py
import pandas as pd
from typing import List
import yfinance as yf

def fetch_sp500_symbols() -> List[str]:
    """Fetch list of S&P 500 company symbols"""
    table = pd.read_html(
        'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    )
    return table[0]['Symbol'].tolist()

def fetch_historical_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch historical OHLCV data for symbol"""
    try:
        data = yf.download(symbol, start=start_date, end=end_date, progress=False)
        return data
    except Exception as e:
        raise ValueError(f"Failed to fetch {symbol}: {e}")
```

**Step 4: Run test to verify it passes**

```bash
cd python && pytest tests/unit/trading/test_data.py::test_fetch_sp500_constituents -v
```

Expected: `PASSED`

**Step 5: Write additional unit tests for data fetching**

```python
# tests/unit/trading/test_data.py
def test_fetch_historical_data_valid_symbol():
    """Fetch historical data for valid symbol"""
    data = fetch_historical_data("AAPL", "2023-01-01", "2023-12-31")
    assert len(data) > 200  # ~250 trading days in year
    assert "Close" in data.columns

def test_fetch_historical_data_invalid_symbol():
    """Handle invalid symbol gracefully"""
    with pytest.raises(ValueError):
        fetch_historical_data("INVALID_SYMBOL_XYZ", "2023-01-01", "2023-12-31")
```

**Step 6: Write E2E test**

```python
# tests/integration/trading/test_data_e2e.py
def test_fetch_sp500_historical_data():
    """End-to-end: fetch S&P 500 data for backtest"""
    symbols = fetch_sp500_symbols()[:10]  # First 10 for speed

    for symbol in symbols:
        data = fetch_historical_data(symbol, "2023-01-01", "2023-12-31")
        assert len(data) > 200
        assert data["Close"].notna().sum() > 0
```

**Step 7: Verify acceptance criteria**

- [ ] Unit tests pass: `pytest tests/unit/trading/test_data.py -v`
- [ ] E2E test passes: `pytest tests/integration/trading/test_data_e2e.py -v`
- [ ] data.py is 25 lines (under 30)
- [ ] types.py is 20 lines (under 30)
- [ ] Linting clean: `ruff check python/trading_backtest/`

**Step 8: Commit**

```bash
git add python/trading_backtest/__init__.py python/trading_backtest/types.py python/trading_backtest/data.py
git add tests/unit/trading/test_data.py tests/integration/trading/test_data_e2e.py
git commit -m "feat: add data ingestion layer for stock trading backtest"
```

---

## Task 2: Source Credibility Tracking

**Acceptance Criteria:**
- [ ] Unit tests pass (compute credibility, update trust from outcomes, compute consistency)
- [ ] E2E test passes (simulate analyst predictions, update credibility, verify persistence)
- [ ] No function exceeds 30 lines
- [ ] No file exceeds 300 lines

**Files:**
- Create: `python/trading_backtest/credibility.py` — Source credibility management
- Create: `tests/unit/trading/test_credibility.py` — Unit tests
- Create: `tests/integration/trading/test_credibility_e2e.py` — E2E tests

**Step 1: Write failing unit test**

```python
# tests/unit/trading/test_credibility.py
def test_credibility_computation():
    """Credibility = trust^0.6 * recency^0.2 * consistency^0.2"""
    cred = SourceCredibility(
        source_name="Goldman Sachs",
        trust=0.75,
        recency=0.90,
        consistency=0.85
    )
    expected = (0.75 ** 0.6) * (0.90 ** 0.2) * (0.85 ** 0.2)
    assert abs(cred.credibility - expected) < 0.001
```

**Step 2: Run test (fails)**

```bash
cd python && pytest tests/unit/trading/test_credibility.py::test_credibility_computation -v
```

**Step 3: Implement credibility module**

```python
# python/trading_backtest/credibility.py
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime, timedelta

@dataclass
class SourceCredibility:
    """Tracks source reliability over time"""
    source_name: str
    trust: float = 0.5  # Initial neutral
    recency: float = 1.0  # Full weight initially
    consistency: float = 0.5  # Initial neutral

    @property
    def credibility(self) -> float:
        """Compute composite credibility score"""
        return (self.trust ** 0.6) * (self.recency ** 0.2) * (self.consistency ** 0.2)

@dataclass
class PredictionRecord:
    """Track prediction and actual outcome"""
    source: str
    prediction: float  # e.g., expected stock return
    actual: float  # e.g., actual stock return
    date: datetime

class CredibilityTracker:
    """Manage source credibilities"""

    def __init__(self):
        self.sources: Dict[str, SourceCredibility] = {}
        self.predictions: List[PredictionRecord] = []

    def register_source(self, source_name: str) -> None:
        """Register new information source"""
        if source_name not in self.sources:
            self.sources[source_name] = SourceCredibility(source_name)

    def record_prediction(self, source: str, prediction: float,
                         actual: float) -> None:
        """Record prediction outcome"""
        self.register_source(source)
        self.predictions.append(
            PredictionRecord(source, prediction, actual, datetime.now())
        )
        self._update_trust(source)

    def _update_trust(self, source: str) -> None:
        """Update trust from prediction accuracy"""
        preds = [p for p in self.predictions if p.source == source]
        if not preds:
            return

        # Compute directional accuracy (did prediction go right direction?)
        correct = sum(
            1 for p in preds
            if (p.prediction > 0 and p.actual > 0) or
               (p.prediction < 0 and p.actual < 0)
        )
        accuracy = correct / len(preds)

        # Update trust with smoothing
        cred = self.sources[source]
        cred.trust = 0.8 * cred.trust + 0.2 * accuracy

    def _update_recency(self) -> None:
        """Decay recency by age of predictions"""
        now = datetime.now()
        for source in self.sources.values():
            preds = [p for p in self.predictions if p.source == source.source_name]
            if preds:
                age_days = (now - preds[-1].date).days
                source.recency = max(0.5, 1.0 - (age_days / 365.0) * 0.5)

    def get_credibility(self, source: str) -> float:
        """Get credibility for source"""
        self._update_recency()
        if source not in self.sources:
            return 0.5  # Default neutral
        return self.sources[source].credibility
```

**Step 4: Run test (passes)**

```bash
cd python && pytest tests/unit/trading/test_credibility.py::test_credibility_computation -v
```

Expected: `PASSED`

**Step 5: Write additional tests**

```python
# tests/unit/trading/test_credibility.py
def test_update_trust_from_predictions():
    """Trust increases when predictions accurate"""
    tracker = CredibilityTracker()
    tracker.register_source("Analyst A")

    # Analyst A predicts +5%, actual is +4% (correct direction)
    tracker.record_prediction("Analyst A", prediction=5.0, actual=4.0)

    # Analyst A predicts +3%, actual is +8% (correct direction)
    tracker.record_prediction("Analyst A", prediction=3.0, actual=8.0)

    trust_after = tracker.sources["Analyst A"].trust
    assert trust_after > 0.5  # Improved from initial 0.5

def test_credibility_decreases_with_age():
    """Recency decays credibility over time"""
    tracker = CredibilityTracker()
    tracker.register_source("Old Source")

    # Simulate old prediction (365 days ago)
    old_pred = PredictionRecord("Old Source", 5.0, 5.0,
                               datetime.now() - timedelta(days=365))
    tracker.predictions.append(old_pred)

    recency_before = tracker.sources["Old Source"].recency
    tracker._update_recency()
    recency_after = tracker.sources["Old Source"].recency

    assert recency_after < recency_before
```

**Step 6: Write E2E test**

```python
# tests/integration/trading/test_credibility_e2e.py
def test_credibility_tracking_full_cycle():
    """End-to-end: track analyst credibility over time"""
    tracker = CredibilityTracker()

    # Analyst A makes 10 predictions
    for i in range(10):
        predicted = 5.0 + (i % 3 - 1)  # +5, +4, +6 pattern
        actual = 5.0 + (i % 3)  # +5, +6, +7 pattern (slightly off)
        tracker.record_prediction("Analyst A", predicted, actual)

    cred = tracker.get_credibility("Analyst A")
    assert 0.5 < cred < 1.0  # Should be improved but not perfect
```

**Step 7: Verify acceptance criteria**

- [ ] Unit tests pass: `pytest tests/unit/trading/test_credibility.py -v`
- [ ] E2E tests pass: `pytest tests/integration/trading/test_credibility_e2e.py -v`
- [ ] credibility.py is 65 lines (under 300)
- [ ] All functions < 30 lines
- [ ] Linting clean

**Step 8: Commit**

```bash
git add python/trading_backtest/credibility.py
git add tests/unit/trading/test_credibility.py tests/integration/trading/test_credibility_e2e.py
git commit -m "feat: add source credibility tracking with trust/recency/consistency"
```

---

## Task 3: Epistemic Engine (Belief Maintenance)

**Acceptance Criteria:**
- [ ] Unit tests pass (credibility-weighted Bayesian updates, retroactive discounting)
- [ ] E2E test passes (maintain beliefs about 5 stocks across 12 months)
- [ ] No function exceeds 30 lines
- [ ] No file exceeds 300 lines

**Files:**
- Create: `python/trading_backtest/epistemic.py` — Epistemic engine
- Create: `tests/unit/trading/test_epistemic.py` — Unit tests
- Create: `tests/integration/trading/test_epistemic_e2e.py` — E2E tests

**Step 1: Write failing unit test**

```python
# tests/unit/trading/test_epistemic.py
def test_credibility_weighted_belief_update():
    """Update belief P(undervalued) based on credibility-weighted evidence"""
    engine = EpistemicEngine()

    # Register sources
    engine.register_source("Goldman", credibility=0.75)
    engine.register_source("RetailBlog", credibility=0.20)

    # Both sources say AAPL is undervalued
    engine.observe("AAPL", "undervalued", source="Goldman")
    engine.observe("AAPL", "undervalued", source="RetailBlog")

    belief = engine.get_belief("AAPL", "undervalued")

    # Goldman dominates, so belief should be high
    assert 0.70 < belief < 0.95
```

**Step 2: Run test (fails)**

```bash
cd python && pytest tests/unit/trading/test_epistemic.py -v
```

**Step 3: Implement epistemic engine**

```python
# python/trading_backtest/epistemic.py
from dataclasses import dataclass, field
from typing import Dict, Tuple, List
from enum import Enum

class BeliefType(Enum):
    """Types of beliefs about stocks"""
    UNDERVALUED = "undervalued"
    OVERVALUED = "overvalued"
    HIGH_GROWTH = "high_growth"
    LOW_GROWTH = "low_growth"
    HIGH_RISK = "high_risk"
    LOW_RISK = "low_risk"

@dataclass
class Belief:
    """Probabilistic belief about stock attribute"""
    symbol: str
    attribute: BeliefType
    probability: float = 0.5
    confirmations: int = 0
    contradictions: int = 0
    sources: Dict[str, float] = field(default_factory=dict)  # source -> credibility

class EpistemicEngine:
    """Maintains accurate beliefs despite noisy/adversarial data"""

    def __init__(self):
        self.beliefs: Dict[Tuple[str, BeliefType], Belief] = {}
        self.source_credibilities: Dict[str, float] = {}
        self.anomalies: List[Tuple[str, str]] = []

    def register_source(self, source_name: str, credibility: float) -> None:
        """Register information source with credibility"""
        self.source_credibilities[source_name] = credibility

    def observe(self, symbol: str, attribute: str, source: str,
                confirms: bool = True) -> None:
        """Record observation from source"""
        belief_type = BeliefType(attribute)
        key = (symbol, belief_type)

        if key not in self.beliefs:
            self.beliefs[key] = Belief(symbol, belief_type)

        belief = self.beliefs[key]
        credibility = self.source_credibilities.get(source, 0.5)

        # Update counters
        if confirms:
            belief.confirmations += credibility
        else:
            belief.contradictions += credibility

        # Store source contribution
        belief.sources[source] = credibility

        # Update probability: Beta-Binomial
        alpha = 1  # Prior
        beta = 1  # Prior
        p_confirms = alpha + belief.confirmations
        p_contradicts = beta + belief.contradictions

        belief.probability = p_confirms / (p_confirms + p_contradicts)

    def get_belief(self, symbol: str, attribute: str) -> float:
        """Get probability of attribute for symbol"""
        key = (symbol, BeliefType(attribute))
        if key not in self.beliefs:
            return 0.5  # Default neutral
        return self.beliefs[key].probability

    def detect_anomaly(self, symbol: str, signal: str) -> bool:
        """Detect unusual pattern without updating beliefs"""
        self.anomalies.append((symbol, signal))
        return True  # Flag for investigation

    def retroactive_discount(self, fraudulent_source: str,
                            fraudulent_credibility: float = 0.0) -> None:
        """Remove fraudulent source's contributions from all beliefs"""
        for key, belief in self.beliefs.items():
            if fraudulent_source not in belief.sources:
                continue

            # Subtract fraudster's contribution
            removed_weight = belief.sources[fraudulent_source]

            if fraudulent_credibility > removed_weight:
                # Fraudster contributed confirmations
                belief.confirmations -= removed_weight
            else:
                # Fraudster contributed contradictions
                belief.contradictions -= removed_weight

            # Recompute probability
            alpha = 1
            beta = 1
            p_confirms = alpha + belief.confirmations
            p_contradicts = beta + belief.contradictions
            belief.probability = p_confirms / (p_confirms + p_contradicts)

            # Remove fraudster from sources
            del belief.sources[fraudulent_source]
```

**Step 4: Run test (passes)**

```bash
cd python && pytest tests/unit/trading/test_epistemic.py -v
```

**Step 5: Write additional tests**

```python
# tests/unit/trading/test_epistemic.py
def test_retroactive_discounting():
    """Remove fraudulent source from all beliefs"""
    engine = EpistemicEngine()
    engine.register_source("Fraudster", credibility=0.8)
    engine.register_source("Honest", credibility=0.7)

    # Fraudster says AAPL undervalued
    engine.observe("AAPL", "undervalued", source="Fraudster", confirms=True)
    belief_before = engine.get_belief("AAPL", "undervalued")

    # Discover fraud
    engine.retroactive_discount("Fraudster", fraudulent_credibility=0.0)
    belief_after = engine.get_belief("AAPL", "undervalued")

    # Belief should revert closer to default
    assert belief_after < belief_before
    assert belief_after == 0.5  # Reset to neutral

def test_energy_field_anomaly():
    """Detect anomalies without updating beliefs"""
    engine = EpistemicEngine()

    # Unusual trading volume in AAPL
    is_anomaly = engine.detect_anomaly("AAPL", "volume_spike")
    assert is_anomaly

    # Anomaly recorded but doesn't affect beliefs yet
    belief = engine.get_belief("AAPL", "high_risk")
    assert belief == 0.5  # Unchanged
```

**Step 6: Write E2E test**

```python
# tests/integration/trading/test_epistemic_e2e.py
def test_epistemic_engine_full_cycle():
    """End-to-end: maintain beliefs about stocks over time"""
    engine = EpistemicEngine()
    engine.register_source("Goldman", 0.75)
    engine.register_source("RetailBlog", 0.20)
    engine.register_source("Fraudster", 0.0)

    # Month 1: Sources report on AAPL
    engine.observe("AAPL", "undervalued", "Goldman", confirms=True)
    engine.observe("AAPL", "undervalued", "RetailBlog", confirms=True)
    belief_m1 = engine.get_belief("AAPL", "undervalued")
    assert belief_m1 > 0.6

    # Month 2: Fraudster joins
    engine.observe("AAPL", "undervalued", "Fraudster", confirms=False)
    belief_m2 = engine.get_belief("AAPL", "undervalued")
    assert belief_m2 < belief_m1  # Decreased due to Fraudster's low credibility

    # Month 3: Discover fraud
    engine.retroactive_discount("Fraudster")
    belief_m3 = engine.get_belief("AAPL", "undervalued")
    assert belief_m3 > belief_m2  # Belief recovers
```

**Step 7: Verify acceptance criteria**

- [ ] All unit tests pass
- [ ] All E2E tests pass
- [ ] epistemic.py is 110 lines (under 300)
- [ ] All functions < 30 lines
- [ ] Linting clean

**Step 8: Commit**

```bash
git add python/trading_backtest/epistemic.py
git add tests/unit/trading/test_epistemic.py tests/integration/trading/test_epistemic_e2e.py
git commit -m "feat: add epistemic engine with credibility-weighted beliefs and retroactive discounting"
```

---

## Task 4: Decision Engine (Action Recommendation)

**Acceptance Criteria:**
- [ ] Unit tests pass (expected utility, state-dependent utility, multi-objective)
- [ ] E2E test passes (recommend portfolio of 20 stocks with constraints)
- [ ] No function exceeds 30 lines
- [ ] No file exceeds 300 lines

**Files:**
- Create: `python/trading_backtest/decision.py` — Decision engine
- Create: `tests/unit/trading/test_decision.py` — Unit tests
- Create: `tests/integration/trading/test_decision_e2e.py` — E2E tests

**Step 1: Write failing unit test**

```python
# tests/unit/trading/test_decision.py
def test_expected_utility_computation():
    """E[U] = expected_return - risk - cost - tax"""
    engine = DecisionEngine()

    action = StockAction(
        symbol="AAPL",
        action_type="buy",
        expected_return=0.10,  # 10% expected return
        volatility=0.20,  # 20% volatility
        transaction_cost=0.001,  # 0.1% cost
        tax_cost=0.02  # 2% tax
    )

    utility = engine.compute_utility(action, weights={
        'return': 1.0,
        'risk': 0.5,
        'cost': 1.0,
        'tax': 1.0
    })

    # Utility = 10% - 0.5*20% - 0.1% - 2% = 5.9%
    expected = 0.10 - 0.5*0.20 - 0.001 - 0.02
    assert abs(utility - expected) < 0.001
```

**Step 2: Run test (fails)**

```bash
cd python && pytest tests/unit/trading/test_decision.py -v
```

**Step 3: Implement decision engine**

```python
# python/trading_backtest/decision.py
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class StockAction:
    """Action recommendation for stock"""
    symbol: str
    action_type: str  # "buy", "sell", "hold"
    expected_return: float
    volatility: float
    transaction_cost: float
    tax_cost: float
    liquidity_cost: float = 0.0

class DecisionEngine:
    """Recommend optimal portfolio actions"""

    def __init__(self):
        self.predictions: List[Dict] = []

    def compute_utility(self, action: StockAction,
                       weights: Dict[str, float]) -> float:
        """Compute expected utility of action"""
        utility = (
            weights.get('return', 1.0) * action.expected_return -
            weights.get('risk', 0.5) * action.volatility -
            weights.get('cost', 1.0) * action.transaction_cost -
            weights.get('tax', 1.0) * action.tax_cost -
            weights.get('liquidity', 0.5) * action.liquidity_cost
        )
        return utility

    def recommend_actions(self, actions: List[StockAction],
                         weights: Dict[str, float],
                         top_k: int = 20) -> List[StockAction]:
        """Recommend top-K actions by utility"""
        utilities = [
            (self.compute_utility(a, weights), a)
            for a in actions
        ]
        utilities.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in utilities[:top_k]]

    def record_prediction(self, symbol: str, prediction: float,
                         actual: float) -> None:
        """Record prediction outcome for learning"""
        self.predictions.append({
            'symbol': symbol,
            'prediction': prediction,
            'actual': actual
        })

    def get_prediction_accuracy(self, symbol: str) -> float:
        """Compute directional accuracy for symbol"""
        preds = [p for p in self.predictions if p['symbol'] == symbol]
        if not preds:
            return 0.5

        correct = sum(
            1 for p in preds
            if (p['prediction'] > 0 and p['actual'] > 0) or
               (p['prediction'] < 0 and p['actual'] < 0)
        )
        return correct / len(preds)
```

**Step 4: Run test (passes)**

```bash
cd python && pytest tests/unit/trading/test_decision.py -v
```

**Step 5: Write additional tests**

```python
# tests/unit/trading/test_decision.py
def test_recommend_top_k_actions():
    """Recommend top-K stocks by utility"""
    engine = DecisionEngine()

    actions = [
        StockAction("AAPL", "buy", 0.10, 0.20, 0.001, 0.02),
        StockAction("MSFT", "buy", 0.12, 0.18, 0.001, 0.02),
        StockAction("GOOG", "buy", 0.08, 0.25, 0.001, 0.02),
    ]

    recommendations = engine.recommend_actions(
        actions,
        weights={'return': 1.0, 'risk': 0.5, 'cost': 1.0, 'tax': 1.0},
        top_k=2
    )

    assert len(recommendations) == 2
    assert recommendations[0].symbol == "MSFT"  # Highest utility
    assert recommendations[1].symbol == "AAPL"

def test_prediction_accuracy():
    """Track prediction accuracy by symbol"""
    engine = DecisionEngine()

    engine.record_prediction("AAPL", 0.10, 0.08)  # +10% predicted, +8% actual
    engine.record_prediction("AAPL", 0.05, 0.06)  # +5% predicted, +6% actual

    accuracy = engine.get_prediction_accuracy("AAPL")
    assert accuracy == 1.0  # Both predictions correct direction
```

**Step 6: Write E2E test**

```python
# tests/integration/trading/test_decision_e2e.py
def test_decision_engine_portfolio_selection():
    """End-to-end: select optimal portfolio"""
    engine = DecisionEngine()

    # Generate 30 candidate actions
    actions = []
    for i in range(30):
        actions.append(StockAction(
            symbol=f"STOCK_{i:02d}",
            action_type="buy",
            expected_return=0.08 + (i % 5) * 0.01,
            volatility=0.15 + (i % 5) * 0.02,
            transaction_cost=0.001,
            tax_cost=0.02
        ))

    # Select top 20
    recommendations = engine.recommend_actions(actions, top_k=20)

    assert len(recommendations) == 20
    # Top stocks should have higher expected return
    assert recommendations[0].expected_return > recommendations[19].expected_return
```

**Step 7: Verify acceptance criteria**

- [ ] All unit tests pass
- [ ] All E2E tests pass
- [ ] decision.py is 80 lines (under 300)
- [ ] All functions < 30 lines
- [ ] Linting clean

**Step 8: Commit**

```bash
git add python/trading_backtest/decision.py
git add tests/unit/trading/test_decision.py tests/integration/trading/test_decision_e2e.py
git commit -m "feat: add decision engine with expected utility maximization"
```

---

## Task 5: RCA Engine (Root Cause Analysis)

**Acceptance Criteria:**
- [ ] Unit tests pass (backward propagation, temporal analysis, contribution scoring)
- [ ] E2E test passes (analyze underperformance, identify root causes)
- [ ] No function exceeds 30 lines
- [ ] No file exceeds 300 lines

**Files:**
- Create: `python/trading_backtest/rca.py` — RCA engine
- Create: `tests/unit/trading/test_rca.py` — Unit tests
- Create: `tests/integration/trading/test_rca_e2e.py` — E2E tests

**Step 1: Write failing unit test**

```python
# tests/unit/trading/test_rca.py
def test_backward_propagation():
    """Identify root causes by backward propagation"""
    engine = RCAEngine()

    # Build cause graph: Portfolio → Tech Sector → Apple → Fed Policy
    engine.add_edge("Portfolio", "TechSector", weight=0.8)
    engine.add_edge("TechSector", "Apple", weight=0.9)
    engine.add_edge("Apple", "FedPolicy", weight=0.7)

    # Portfolio underperformed
    root_causes = engine.backward_propagate("Portfolio",
                                           magnitude=-0.05)

    # Should identify FedPolicy as root cause (furthest up chain)
    causes_dict = {c['node']: c['impact'] for c in root_causes}
    assert "FedPolicy" in causes_dict
```

**Step 2: Run test (fails)**

```bash
cd python && pytest tests/unit/trading/test_rca.py -v
```

**Step 3: Implement RCA engine**

```python
# python/trading_backtest/rca.py
from dataclasses import dataclass
from typing import Dict, List, Tuple
from collections import defaultdict

@dataclass
class CauseContribution:
    """Quantified contribution of root cause"""
    node: str
    direct_impact: float
    weighted_impact: float
    credibility: float = 1.0
    temporal_precedence: int = 0  # Lower = earlier

class RCAEngine:
    """Root Cause Analysis via backward propagation"""

    def __init__(self):
        self.graph: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        self.anomalies: List[Dict] = []
        self.timeline: Dict[str, int] = {}  # node -> time of change

    def add_edge(self, source: str, target: str, weight: float) -> None:
        """Add edge: source -> target (cause -> effect)"""
        self.graph[source].append((target, weight))

    def record_anomaly(self, node: str, magnitude: float,
                      time_step: int) -> None:
        """Record observed anomaly"""
        self.anomalies.append({
            'node': node,
            'magnitude': magnitude,
            'time': time_step
        })
        self.timeline[node] = time_step

    def backward_propagate(self, anomaly_node: str,
                          magnitude: float,
                          decay: float = 0.7) -> List[Dict]:
        """Find root causes via backward propagation"""
        causes = {}
        queue = [(anomaly_node, magnitude, 0, 0)]
        visited = set()

        while queue:
            node, impact, hops, time = queue.pop(0)

            if node in visited:
                continue
            visited.add(node)

            # Find incoming edges (reverse graph)
            for source in self.graph:
                targets = [t for t, w in self.graph[source] if t == node]
                if targets:
                    weight = [w for t, w in self.graph[source] if t == node][0]
                    new_impact = impact * weight * (decay ** hops)
                    temporal = self.timeline.get(source, hops)

                    if source not in causes:
                        causes[source] = {
                            'node': source,
                            'impact': new_impact,
                            'temporal': temporal
                        }
                    else:
                        causes[source]['impact'] += new_impact

                    queue.append((source, new_impact, hops + 1, temporal))

        # Sort by impact
        sorted_causes = sorted(causes.values(),
                              key=lambda x: x['impact'],
                              reverse=True)
        return sorted_causes

    def temporal_analysis(self) -> List[Tuple[str, int]]:
        """Identify which event occurred first (likely root cause)"""
        return sorted(self.timeline.items(), key=lambda x: x[1])

    def explain(self, anomaly_node: str, magnitude: float) -> str:
        """Generate explanation of root cause"""
        causes = self.backward_propagate(anomaly_node, magnitude)
        temporal = self.temporal_analysis()

        if not causes:
            return "No root causes identified"

        explanation = f"Anomaly in {anomaly_node} ({magnitude:.2%})\n"
        explanation += "Root causes:\n"

        for cause in causes[:3]:  # Top 3
            explanation += f"  - {cause['node']}: {cause['impact']:.2%}\n"

        return explanation
```

**Step 4: Run test (passes)**

```bash
cd python && pytest tests/unit/trading/test_rca.py -v
```

**Step 5: Write additional tests**

```python
# tests/unit/trading/test_rca.py
def test_temporal_analysis():
    """Identify which event changed first"""
    engine = RCAEngine()

    engine.record_anomaly("FedPolicy", 1.0, time_step=0)
    engine.record_anomaly("InterestRates", 1.0, time_step=1)
    engine.record_anomaly("TechSector", 1.0, time_step=2)
    engine.record_anomaly("Portfolio", -0.05, time_step=3)

    temporal = engine.temporal_analysis()

    # FedPolicy changed first (time_step 0)
    assert temporal[0][0] == "FedPolicy"
    # Portfolio changed last (time_step 3)
    assert temporal[-1][0] == "Portfolio"

def test_contribution_scoring():
    """Quantify each cause's contribution"""
    engine = RCAEngine()

    engine.add_edge("FedPolicy", "InterestRates", weight=0.9)
    engine.add_edge("InterestRates", "TechSector", weight=0.8)
    engine.add_edge("TechSector", "Portfolio", weight=0.7)

    causes = engine.backward_propagate("Portfolio", -0.07)

    # Should identify all three causes with declining impact
    assert len(causes) >= 2
    assert causes[0]['impact'] > causes[1]['impact']
```

**Step 6: Write E2E test**

```python
# tests/integration/trading/test_rca_e2e.py
def test_rca_full_analysis():
    """End-to-end: analyze portfolio underperformance"""
    engine = RCAEngine()

    # Build financial causality graph
    engine.add_edge("FedPolicy", "InterestRates", 0.9)
    engine.add_edge("InterestRates", "TechMultiple", 0.8)
    engine.add_edge("TechMultiple", "Apple", 0.85)
    engine.add_edge("Apple", "TechSector", 0.9)
    engine.add_edge("TechSector", "Portfolio", 0.7)

    # Record timeline
    engine.record_anomaly("FedPolicy", 1.0, time_step=0)
    engine.record_anomaly("InterestRates", 1.0, time_step=1)
    engine.record_anomaly("TechMultiple", 1.0, time_step=2)
    engine.record_anomaly("Portfolio", -0.08, time_step=5)

    # Analyze
    causes = engine.backward_propagate("Portfolio", -0.08)
    explanation = engine.explain("Portfolio", -0.08)

    assert len(causes) > 0
    assert "FedPolicy" in explanation
    assert "Portfolio" in explanation
```

**Step 7: Verify acceptance criteria**

- [ ] All unit tests pass
- [ ] All E2E tests pass
- [ ] rca.py is 95 lines (under 300)
- [ ] All functions < 30 lines
- [ ] Linting clean

**Step 8: Commit**

```bash
git add python/trading_backtest/rca.py
git add tests/unit/trading/test_rca.py tests/integration/trading/test_rca_e2e.py
git commit -m "feat: add RCA engine with backward propagation and temporal analysis"
```

---

## Task 6: Backtesting Framework

**Acceptance Criteria:**
- [ ] Unit tests pass (monthly rebalancing, portfolio tracking, metrics computation)
- [ ] E2E test passes (run 2-year backtest on 10 stocks, compare vs baseline)
- [ ] No function exceeds 30 lines
- [ ] No file exceeds 300 lines

**Files:**
- Create: `python/trading_backtest/backtest.py` — Backtesting engine
- Create: `tests/unit/trading/test_backtest.py` — Unit tests
- Create: `tests/integration/trading/test_backtest_e2e.py` — E2E tests

**Step 1: Write failing unit test**

```python
# tests/unit/trading/test_backtest.py
def test_portfolio_tracking():
    """Track portfolio value over time"""
    backtest = Backtester(initial_capital=100000)

    # Buy 100 shares at $100
    backtest.buy("AAPL", quantity=100, price=100.0)
    assert backtest.portfolio_value() == 100000  # No change yet

    # Price goes to $110
    backtest.update_price("AAPL", 110.0)
    assert backtest.portfolio_value() == 101000  # $1000 gain
```

**Step 2: Run test (fails)**

```bash
cd python && pytest tests/unit/trading/test_backtest.py -v
```

**Step 3: Implement backtester**

```python
# python/trading_backtest/backtest.py
from dataclasses import dataclass
from typing import Dict, List
from datetime import date

@dataclass
class Position:
    """Stock position in portfolio"""
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    entry_date: date

    def market_value(self) -> float:
        return self.quantity * self.current_price

    def gain(self) -> float:
        return (self.current_price - self.entry_price) * self.quantity

    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price

class Backtester:
    """Simulate portfolio trading over time"""

    def __init__(self, initial_capital: float):
        self.capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Dict] = []
        self.metrics: List[Dict] = []

    def buy(self, symbol: str, quantity: int, price: float) -> None:
        """Buy shares"""
        cost = quantity * price
        if cost > self.cash:
            raise ValueError(f"Insufficient cash")

        if symbol not in self.positions:
            self.positions[symbol] = Position(
                symbol, quantity, price, price, date.today()
            )
        else:
            pos = self.positions[symbol]
            total_shares = pos.quantity + quantity
            avg_price = (pos.quantity * pos.entry_price + cost) / total_shares
            pos.quantity = total_shares
            pos.entry_price = avg_price

        self.cash -= cost
        self.trades.append({
            'symbol': symbol,
            'action': 'buy',
            'quantity': quantity,
            'price': price,
            'date': date.today()
        })

    def sell(self, symbol: str, quantity: int, price: float) -> None:
        """Sell shares"""
        if symbol not in self.positions:
            raise ValueError(f"No position in {symbol}")

        pos = self.positions[symbol]
        if quantity > pos.quantity:
            raise ValueError(f"Can't sell {quantity}")

        proceeds = quantity * price
        self.cash += proceeds
        pos.quantity -= quantity

        if pos.quantity == 0:
            del self.positions[symbol]

        self.trades.append({
            'symbol': symbol,
            'action': 'sell',
            'quantity': quantity,
            'price': price,
            'date': date.today()
        })

    def update_price(self, symbol: str, new_price: float) -> None:
        """Update stock price"""
        if symbol in self.positions:
            self.positions[symbol].current_price = new_price

    def portfolio_value(self) -> float:
        """Total portfolio value"""
        stock_value = sum(p.market_value() for p in self.positions.values())
        return self.cash + stock_value

    def monthly_return(self, start_value: float) -> float:
        """Return for this month"""
        end_value = self.portfolio_value()
        return (end_value - start_value) / start_value

    def sharpe_ratio(self, returns: List[float]) -> float:
        """Sharpe ratio"""
        if not returns:
            return 0.0

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5

        if std_dev == 0:
            return 0.0
        return mean_return / std_dev

    def max_drawdown(self, portfolio_values: List[float]) -> float:
        """Maximum drawdown from peak"""
        if not portfolio_values:
            return 0.0

        max_dd = 0.0
        peak = portfolio_values[0]

        for value in portfolio_values[1:]:
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)
            peak = max(peak, value)

        return max_dd
```

**Step 4: Run test (passes)**

```bash
cd python && pytest tests/unit/trading/test_backtest.py -v
```

**Step 5: Write additional tests**

```python
# tests/unit/trading/test_backtest.py
def test_monthly_return_calculation():
    """Compute monthly return"""
    backtest = Backtester(100000)
    backtest.buy("AAPL", 100, 100.0)

    start_value = backtest.portfolio_value()
    backtest.update_price("AAPL", 110.0)

    monthly_ret = backtest.monthly_return(start_value)
    assert abs(monthly_ret - 0.01) < 0.001  # 1% return

def test_sharpe_ratio():
    """Compute Sharpe ratio"""
    backtest = Backtester(100000)

    returns = [0.01, 0.02, 0.01, -0.01, 0.03]
    sharpe = backtest.sharpe_ratio(returns)

    assert sharpe > 0  # Positive returns

def test_max_drawdown():
    """Track maximum drawdown"""
    backtest = Backtester(100000)

    portfolio_values = [100000, 105000, 95000, 98000, 110000]
    max_dd = backtest.max_drawdown(portfolio_values)

    assert abs(max_dd - 0.095) < 0.001
```

**Step 6: Write E2E test**

```python
# tests/integration/trading/test_backtest_e2e.py
def test_backtest_full_cycle():
    """End-to-end: run multi-month backtest"""
    backtest = Backtester(100000)

    portfolio_values = []
    returns = []

    # Simulate 12 months
    for month in range(12):
        start_value = backtest.portfolio_value()

        # Buy some stocks
        if month == 0:
            backtest.buy("AAPL", 50, 100.0)
            backtest.buy("MSFT", 50, 100.0)

        # Prices change
        aapl_price = 100.0 + month * 0.5
        msft_price = 100.0 + month * 0.7
        backtest.update_price("AAPL", aapl_price)
        backtest.update_price("MSFT", msft_price)

        end_value = backtest.portfolio_value()
        portfolio_values.append(end_value)
        returns.append((end_value - start_value) / start_value)

    # Compute metrics
    sharpe = backtest.sharpe_ratio(returns)
    max_dd = backtest.max_drawdown(portfolio_values)
    total_return = (portfolio_values[-1] - 100000) / 100000

    assert total_return > 0  # Should be profitable
    assert sharpe > 0
    assert 0 < max_dd < 1
```

**Step 7: Verify acceptance criteria**

- [ ] All unit tests pass
- [ ] All E2E tests pass
- [ ] backtest.py is 130 lines (under 300)
- [ ] All functions < 30 lines
- [ ] Linting clean

**Step 8: Commit**

```bash
git add python/trading_backtest/backtest.py
git add tests/unit/trading/test_backtest.py tests/integration/trading/test_backtest_e2e.py
git commit -m "feat: add backtesting framework with portfolio tracking and metrics"
```

---

## Task 7: End-to-End Integration & Results Analysis

**Acceptance Criteria:**
- [ ] E2E test passes (run full backtest on S&P 500 sample, 2000-2024)
- [ ] Compare results: Trading System vs. Buy-Hold vs. Mean-Variance vs. Random
- [ ] Generate report with: returns, Sharpe, max drawdown, period breakdown
- [ ] Analyze RCA findings (when underperformed, what was root cause?)
- [ ] Generate visualizations: equity curve, monthly returns, sector allocation

**Files:**
- Create: `python/trading_backtest/runner.py` — Main backtest runner
- Create: `python/trading_backtest/analysis.py` — Results analysis
- Create: `tests/integration/trading/test_full_backtest_e2e.py` — Full E2E
- Create: `python/trading_backtest/requirements.txt` — Dependencies

**Step 1: Create requirements.txt**

```
pandas>=1.3.0
numpy>=1.20.0
yfinance>=0.1.70
matplotlib>=3.4.0
plotly>=5.0.0
pytest>=6.0.0
```

**Step 2: Create main runner**

```python
# python/trading_backtest/runner.py
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd
from .data import fetch_sp500_symbols, fetch_historical_data
from .decision import DecisionEngine, StockAction
from .backtest import Backtester

class TradingSystemBacktest:
    """Run full backtest of trading system"""

    def __init__(self, start_date: str, end_date: str,
                 initial_capital: float = 100000,
                 top_k: int = 20):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.top_k = top_k
        self.decision = DecisionEngine()
        self.backtest = Backtester(initial_capital)
        self.results: Dict = {}

    def run(self) -> Dict:
        """Run full backtest"""
        symbols = fetch_sp500_symbols()[:100]

        all_data = {}
        for symbol in symbols:
            try:
                data = fetch_historical_data(symbol, self.start_date,
                                            self.end_date)
                all_data[symbol] = data
            except:
                continue

        start_date = pd.Timestamp(self.start_date)
        end_date = pd.Timestamp(self.end_date)
        current_date = start_date

        portfolio_values = []
        monthly_returns = []

        while current_date < end_date:
            month_end = current_date + timedelta(days=30)

            actions = self._generate_actions(all_data, current_date)
            recommendations = self.decision.recommend_actions(
                actions, top_k=self.top_k
            )

            self._execute_trades(recommendations, all_data)

            portfolio_val = self.backtest.portfolio_value()
            portfolio_values.append(portfolio_val)

            if len(portfolio_values) > 1:
                monthly_ret = (portfolio_values[-1] - portfolio_values[-2]
                              ) / portfolio_values[-2]
                monthly_returns.append(monthly_ret)

            current_date = month_end

        self.results = {
            'portfolio_values': portfolio_values,
            'monthly_returns': monthly_returns,
            'final_value': portfolio_values[-1] if portfolio_values else self.initial_capital,
            'total_return': (portfolio_values[-1] - self.initial_capital
                           ) / self.initial_capital if portfolio_values else 0,
            'sharpe': self.backtest.sharpe_ratio(monthly_returns),
            'max_drawdown': self.backtest.max_drawdown(portfolio_values)
        }

        return self.results

    def _generate_actions(self, all_data: Dict, start_date):
        """Generate action recommendations"""
        actions = []

        for symbol, data in all_data.items():
            period_data = data[data.index >= start_date]

            if len(period_data) < 5:
                continue

            start_price = period_data['Close'].iloc[0]
            end_price = period_data['Close'].iloc[-1]
            expected_return = (end_price - start_price) / start_price

            returns = period_data['Close'].pct_change().dropna()
            volatility = returns.std() * (252 ** 0.5)

            action = StockAction(
                symbol=symbol,
                action_type="buy",
                expected_return=expected_return,
                volatility=volatility,
                transaction_cost=0.001,
                tax_cost=0.02
            )
            actions.append(action)

        return actions

    def _execute_trades(self, recommendations, all_data):
        """Execute recommended trades"""
        for action in recommendations:
            if action.symbol not in all_data:
                continue

            data = all_data[action.symbol]
            if len(data) == 0:
                continue

            price = data['Close'].iloc[-1]
            quantity = int(50000 / price)
            try:
                self.backtest.buy(action.symbol, quantity, price)
            except:
                continue
```

**Step 3: Create analysis module**

```python
# python/trading_backtest/analysis.py
from typing import Dict

class BacktestAnalysis:
    """Analyze backtest results"""

    @staticmethod
    def generate_report(results: Dict, baseline_results: Dict = None) -> str:
        """Generate summary report"""
        report = "=" * 60 + "\n"
        report += "BACKTEST RESULTS\n"
        report += "=" * 60 + "\n\n"

        report += f"Final Portfolio Value: ${results['final_value']:,.2f}\n"
        report += f"Total Return: {results['total_return']:.2%}\n"
        report += f"Sharpe Ratio: {results['sharpe']:.3f}\n"
        report += f"Max Drawdown: {results['max_drawdown']:.2%}\n"

        if baseline_results:
            report += "\nVS. BASELINE:\n"
            return_diff = (results['total_return'] -
                          baseline_results['total_return'])
            sharpe_diff = results['sharpe'] - baseline_results['sharpe']
            dd_diff = (results['max_drawdown'] -
                      baseline_results['max_drawdown'])

            report += f"Return Difference: {return_diff:+.2%}\n"
            report += f"Sharpe Difference: {sharpe_diff:+.3f}\n"
            report += f"Drawdown Difference: {dd_diff:+.2%}\n"

        report += "\n" + "=" * 60 + "\n"
        return report

    @staticmethod
    def period_analysis(results: Dict) -> Dict:
        """Analyze returns by period"""
        returns = results['monthly_returns']

        if not returns:
            return {}

        positive_months = sum(1 for r in returns if r > 0)
        negative_months = sum(1 for r in returns if r < 0)
        win_rate = positive_months / len(returns)

        avg_positive = sum(r for r in returns if r > 0) / max(positive_months, 1)
        avg_negative = sum(r for r in returns if r < 0) / max(negative_months, 1)

        return {
            'positive_months': positive_months,
            'negative_months': negative_months,
            'win_rate': win_rate,
            'avg_gain': avg_positive,
            'avg_loss': avg_negative
        }
```

**Step 4: Write E2E integration test**

```python
# tests/integration/trading/test_full_backtest_e2e.py
def test_full_backtest_s_and_p500():
    """End-to-end: full backtest with S&P 500 sample"""
    from trading_backtest.runner import TradingSystemBacktest

    backtest = TradingSystemBacktest(
        start_date="2022-01-01",
        end_date="2024-01-01",
        initial_capital=100000,
        top_k=20
    )

    results = backtest.run()

    # Verify results exist
    assert 'final_value' in results
    assert 'total_return' in results
    assert 'sharpe' in results
    assert 'max_drawdown' in results

    # Verify reasonable values
    assert results['final_value'] > 0
    assert -1 < results['total_return'] < 2
    assert 0 <= results['max_drawdown'] <= 1

def test_backtest_analysis():
    """Generate analysis report"""
    from trading_backtest.analysis import BacktestAnalysis

    results = {
        'final_value': 115000,
        'total_return': 0.15,
        'sharpe': 0.75,
        'max_drawdown': 0.12,
        'monthly_returns': [0.01, 0.02, -0.01, 0.03]
    }

    report = BacktestAnalysis.generate_report(results)

    assert "15.00%" in report
    assert "0.75" in report or "0.750" in report
```

**Step 5: Verify acceptance criteria**

- [ ] Full E2E test passes
- [ ] All components integrated
- [ ] Results generated with metrics
- [ ] Report formatting clean

**Step 6: Commit**

```bash
git add python/trading_backtest/runner.py python/trading_backtest/analysis.py
git add python/trading_backtest/requirements.txt
git add tests/integration/trading/test_full_backtest_e2e.py
git commit -m "feat: add end-to-end backtest integration and analysis"
```

---

**Plan saved. Now dispatching implementer subagent for Task 1...**