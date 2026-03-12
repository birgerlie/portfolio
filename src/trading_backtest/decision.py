"""Decision engine for expected utility maximization and portfolio actions."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional


class ActionType(Enum):
    """Action types for stock trading decisions."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class StockAction:
    """Portfolio action with expected utility components."""

    symbol: str
    action_type: ActionType
    expected_return: float         # Expected return as decimal (0.15 = 15%)
    volatility: float              # Risk/volatility as decimal (0.20 = 20%)
    transaction_cost: float        # Transaction cost as decimal
    tax_cost: float                # Tax cost as decimal
    liquidity_cost: float          # Liquidity cost as decimal


class DecisionEngine:
    """Compute expected utility and recommend top K actions."""

    def __init__(self):
        """Initialize decision engine with empty prediction history."""
        self._predictions: Dict[str, List[Dict]] = {}

    def compute_utility(self, action: StockAction) -> float:
        """Compute expected utility for an action.

        E[U] = expected_return - 0.5*volatility - transaction_cost
               - tax_cost - liquidity_cost

        Args:
            action: StockAction with return, risk, and cost components.

        Returns:
            Expected utility as float.
        """
        return (
            action.expected_return
            - 0.5 * action.volatility
            - action.transaction_cost
            - action.tax_cost
            - action.liquidity_cost
        )

    def recommend_actions(
        self, candidates: List[StockAction], k: int = 20
    ) -> List[StockAction]:
        """Select top K actions by expected utility.

        Args:
            candidates: List of StockAction candidates.
            k: Number of top actions to recommend.

        Returns:
            List of top K actions sorted by utility (descending).
        """
        if not candidates:
            return []

        # Compute utility for each candidate
        utilities = [
            (self.compute_utility(action), action)
            for action in candidates
        ]

        # Sort by utility descending
        utilities.sort(key=lambda x: x[0], reverse=True)

        # Return top K
        return [action for _, action in utilities[:k]]

    def record_prediction(
        self,
        symbol: str,
        predicted_action: ActionType,
        actual_action: ActionType,
    ) -> None:
        """Record a prediction and its actual outcome.

        Args:
            symbol: Stock symbol.
            predicted_action: Predicted ActionType.
            actual_action: Actual ActionType outcome.
        """
        if symbol not in self._predictions:
            self._predictions[symbol] = []

        self._predictions[symbol].append({
            "symbol": symbol,
            "predicted": predicted_action,
            "actual": actual_action,
        })

    def get_predictions(self, symbol: str) -> List[Dict]:
        """Get all predictions for a symbol.

        Args:
            symbol: Stock symbol.

        Returns:
            List of prediction records for the symbol.
        """
        return self._predictions.get(symbol, [])

    def get_prediction_accuracy(self) -> float:
        """Compute directional accuracy across all predictions.

        Returns:
            Accuracy as float (0.0 to 1.0). Returns 0.0 if no predictions.
        """
        all_predictions = []
        for predictions in self._predictions.values():
            all_predictions.extend(predictions)

        if not all_predictions:
            return 0.0

        correct = sum(
            1 for p in all_predictions
            if p["predicted"] == p["actual"]
        )

        return correct / len(all_predictions)
