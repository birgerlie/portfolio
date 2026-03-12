"""Unit tests for decision engine and expected utility maximization."""

import pytest

from trading_backtest.decision import (
    StockAction,
    ActionType,
    DecisionEngine,
)


class TestExpectedUtilityComputation:
    """Tests for expected utility formula calculation."""

    def test_expected_utility_formula(self):
        """Verify E[U] = return - 0.5*risk - cost - tax with weights."""
        action = StockAction(
            symbol="AAPL",
            action_type=ActionType.BUY,
            expected_return=0.15,      # 15% return
            volatility=0.20,            # 20% volatility
            transaction_cost=0.002,     # 0.2% transaction cost
            tax_cost=0.01,              # 1% tax cost
            liquidity_cost=0.0,         # No liquidity cost
        )

        engine = DecisionEngine()
        utility = engine.compute_utility(action)

        # Expected: 0.15 - 0.5*0.20 - 0.002 - 0.01
        # = 0.15 - 0.10 - 0.002 - 0.01
        # = 0.038
        expected = 0.15 - 0.5 * 0.20 - 0.002 - 0.01
        assert abs(utility - expected) < 1e-6

    def test_utility_with_all_costs(self):
        """Test utility calculation with all cost components."""
        action = StockAction(
            symbol="TSLA",
            action_type=ActionType.SELL,
            expected_return=0.10,
            volatility=0.30,
            transaction_cost=0.005,
            tax_cost=0.02,
            liquidity_cost=0.01,
        )

        engine = DecisionEngine()
        utility = engine.compute_utility(action)

        # Expected: 0.10 - 0.5*0.30 - 0.005 - 0.02 - 0.01
        # = 0.10 - 0.15 - 0.005 - 0.02 - 0.01
        # = -0.085
        expected = 0.10 - 0.5 * 0.30 - 0.005 - 0.02 - 0.01
        assert abs(utility - expected) < 1e-6

    def test_utility_negative_when_costs_exceed_return(self):
        """Utility is negative when costs and risk exceed expected return."""
        action = StockAction(
            symbol="POOR",
            action_type=ActionType.BUY,
            expected_return=0.02,
            volatility=0.40,
            transaction_cost=0.01,
            tax_cost=0.02,
            liquidity_cost=0.005,
        )

        engine = DecisionEngine()
        utility = engine.compute_utility(action)

        # Expected: 0.02 - 0.5*0.40 - 0.01 - 0.02 - 0.005
        # = 0.02 - 0.20 - 0.01 - 0.02 - 0.005
        # = -0.235
        assert utility < 0
        expected = 0.02 - 0.5 * 0.40 - 0.01 - 0.02 - 0.005
        assert abs(utility - expected) < 1e-6

    def test_utility_zero_costs(self):
        """Test utility when only return and risk matter."""
        action = StockAction(
            symbol="ZERO_COST",
            action_type=ActionType.BUY,
            expected_return=0.20,
            volatility=0.10,
            transaction_cost=0.0,
            tax_cost=0.0,
            liquidity_cost=0.0,
        )

        engine = DecisionEngine()
        utility = engine.compute_utility(action)

        # Expected: 0.20 - 0.5*0.10 = 0.15
        expected = 0.20 - 0.5 * 0.10
        assert abs(utility - expected) < 1e-6


class TestRecommendTopKActions:
    """Tests for recommending top K actions by utility."""

    def test_recommend_top_20_actions(self):
        """Select top 20 from 30 candidates, verify correct ordering."""
        engine = DecisionEngine()
        actions = []

        # Create 30 actions with varying utility
        for i in range(30):
            action = StockAction(
                symbol=f"STOCK_{i:02d}",
                action_type=ActionType.BUY if i % 2 == 0 else ActionType.SELL,
                expected_return=0.05 + i * 0.005,      # Increasing return
                volatility=0.15 + (i % 10) * 0.02,     # Varying volatility
                transaction_cost=0.001 + i * 0.0001,   # Increasing cost
                tax_cost=0.005,
                liquidity_cost=0.0,
            )
            actions.append(action)

        # Get top 20
        top_actions = engine.recommend_actions(actions, k=20)

        # Verify count
        assert len(top_actions) == 20

        # Verify ordering (descending utility)
        utilities = [engine.compute_utility(a) for a in top_actions]
        assert utilities == sorted(utilities, reverse=True)

    def test_recommend_with_k_greater_than_candidates(self):
        """When k > candidates, return all candidates sorted."""
        engine = DecisionEngine()
        actions = [
            StockAction(
                symbol=f"STOCK_{i}",
                action_type=ActionType.BUY,
                expected_return=0.10 + i * 0.01,
                volatility=0.15,
                transaction_cost=0.001,
                tax_cost=0.005,
                liquidity_cost=0.0,
            )
            for i in range(5)
        ]

        # Request top 10, but only 5 candidates
        top_actions = engine.recommend_actions(actions, k=10)

        # Should return all 5
        assert len(top_actions) == 5

        # Verify ordering
        utilities = [engine.compute_utility(a) for a in top_actions]
        assert utilities == sorted(utilities, reverse=True)

    def test_recommend_with_k_equal_one(self):
        """When k=1, return the single best action."""
        engine = DecisionEngine()
        actions = [
            StockAction(
                symbol="GOOD",
                action_type=ActionType.BUY,
                expected_return=0.20,
                volatility=0.10,
                transaction_cost=0.001,
                tax_cost=0.005,
                liquidity_cost=0.0,
            ),
            StockAction(
                symbol="MEDIUM",
                action_type=ActionType.BUY,
                expected_return=0.10,
                volatility=0.15,
                transaction_cost=0.001,
                tax_cost=0.005,
                liquidity_cost=0.0,
            ),
            StockAction(
                symbol="POOR",
                action_type=ActionType.BUY,
                expected_return=0.05,
                volatility=0.25,
                transaction_cost=0.001,
                tax_cost=0.005,
                liquidity_cost=0.0,
            ),
        ]

        top_action = engine.recommend_actions(actions, k=1)

        assert len(top_action) == 1
        assert top_action[0].symbol == "GOOD"

    def test_recommend_empty_list(self):
        """Empty candidate list returns empty recommendation."""
        engine = DecisionEngine()
        top_actions = engine.recommend_actions([], k=20)
        assert len(top_actions) == 0


class TestPredictionAccuracy:
    """Tests for tracking and computing prediction accuracy."""

    def test_record_and_retrieve_prediction(self):
        """Record prediction and retrieve it by symbol."""
        engine = DecisionEngine()

        engine.record_prediction(
            symbol="AAPL",
            predicted_action=ActionType.BUY,
            actual_action=ActionType.BUY,
        )

        predictions = engine.get_predictions("AAPL")
        assert len(predictions) == 1
        assert predictions[0]["symbol"] == "AAPL"
        assert predictions[0]["predicted"] == ActionType.BUY
        assert predictions[0]["actual"] == ActionType.BUY

    def test_prediction_accuracy_all_correct(self):
        """When all predictions are correct, accuracy is 100%."""
        engine = DecisionEngine()

        # Record 5 correct predictions
        for i in range(5):
            engine.record_prediction(
                symbol=f"STOCK_{i}",
                predicted_action=ActionType.BUY,
                actual_action=ActionType.BUY,
            )

        accuracy = engine.get_prediction_accuracy()
        assert accuracy == 1.0

    def test_prediction_accuracy_all_incorrect(self):
        """When all predictions are incorrect, accuracy is 0%."""
        engine = DecisionEngine()

        # Record 5 incorrect predictions
        for i in range(5):
            engine.record_prediction(
                symbol=f"STOCK_{i}",
                predicted_action=ActionType.BUY,
                actual_action=ActionType.SELL,
            )

        accuracy = engine.get_prediction_accuracy()
        assert accuracy == 0.0

    def test_prediction_accuracy_mixed(self):
        """Mixed predictions compute average accuracy."""
        engine = DecisionEngine()

        # 4 correct, 1 incorrect
        engine.record_prediction("STOCK_0", ActionType.BUY, ActionType.BUY)
        engine.record_prediction("STOCK_1", ActionType.SELL, ActionType.SELL)
        engine.record_prediction("STOCK_2", ActionType.BUY, ActionType.BUY)
        engine.record_prediction("STOCK_3", ActionType.HOLD, ActionType.HOLD)
        engine.record_prediction("STOCK_4", ActionType.BUY, ActionType.SELL)

        accuracy = engine.get_prediction_accuracy()
        assert accuracy == 0.8  # 4/5

    def test_no_predictions_accuracy(self):
        """Empty prediction history returns 0.0 accuracy."""
        engine = DecisionEngine()
        accuracy = engine.get_prediction_accuracy()
        assert accuracy == 0.0

    def test_prediction_symbols_with_multiple_records(self):
        """Each symbol can have multiple prediction records."""
        engine = DecisionEngine()

        # Multiple predictions for same symbol
        engine.record_prediction("AAPL", ActionType.BUY, ActionType.BUY)
        engine.record_prediction("AAPL", ActionType.SELL, ActionType.SELL)
        engine.record_prediction("AAPL", ActionType.BUY, ActionType.HOLD)

        predictions = engine.get_predictions("AAPL")
        assert len(predictions) == 3

        accuracy = engine.get_prediction_accuracy()
        # 2 correct (BUY->BUY, SELL->SELL), 1 incorrect (BUY->HOLD)
        assert accuracy == 2.0 / 3.0
