# Autonomous Portfolio & Strategy Selection System

A fully autonomous trading system that analyzes market conditions, selects optimal strategies from 7 proven options, composes portfolio weights based on epistemic beliefs using Kelly Criterion sizing, and generates actionable execution instructions.

## Architecture

```
Market Analysis → Regime Detection → Strategy Selection → Portfolio Composition → Execution Planning
```

## Key Components

- **Regime Detector** (`src/trading_backtest/regime.py`) - Classifies market conditions (BULL/BEAR/TRANSITION/CONSOLIDATION)
- **Strategy Selector** (`src/trading_backtest/strategy_selector.py`) - Scores 7 strategies based on historical performance and regime fit
- **Portfolio Composer** (`src/trading_backtest/portfolio_composer.py`) - Allocates positions using Kelly Criterion with epistemic beliefs
- **Execution Generator** (`src/trading_backtest/execution_generator.py`) - Generates buy/sell orders with execution sequencing
- **Automation Controller** (`src/trading_backtest/automation_controller.py`) - Orchestrates full pipeline end-to-end

## Usage

### Command-Line Interface

```bash
python src/run_backtest.py analyze \
  --market '{"avg_return": 0.15, "volatility": 0.18, "positive_pct": 0.65, "momentum": 0.2}' \
  --beliefs '{"NVDA": ["bullish", 0.75], "AAPL": ["bearish", 0.6]}'
```

### Python API

```python
from trading_backtest.automation_controller import AutonomousController

controller = AutonomousController()
result = controller.analyze(market_metrics, beliefs_dict)

print(f"Regime: {result.regime}")
print(f"Selected Strategy: {result.selected_strategy.name}")
print(f"Portfolio: {result.portfolio}")
```

## Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# All tests
pytest tests/
```

## Documentation

- `docs/STOCK-TRADING-SIMULATOR-COMPLETE-GUIDE.md` - Complete user guide and API reference
- `docs/TRADING-SYSTEM-SCIENCE.md` - Scientific foundations and theory
- `docs/RESEARCH-REPORT-AUTONOMOUS-TRADING.md` - Research report for institutional investors
- `docs/2026-03-12-autonomous-portfolio-strategy-selection.md` - Implementation plan
