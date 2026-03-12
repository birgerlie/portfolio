"""End-to-end tests for decision engine portfolio selection."""

from trading_backtest.decision import (
    StockAction,
    ActionType,
    DecisionEngine,
)


class TestDecisionEnginePortfolioSelection:
    """Test decision engine portfolio selection with realistic data."""

    def test_decision_engine_portfolio_selection(self):
        """Select top 20 from 30 candidates with verification."""
        engine = DecisionEngine()

        # Create 30 realistic stock candidates
        candidates = []
        for i in range(30):
            # Create diverse utility profiles
            expected_return = 0.08 + (i / 30) * 0.12  # 8% to 20% return range
            volatility = 0.10 + (i % 10) * 0.03      # 10% to 40% volatility
            transaction_cost = 0.001 + (i % 5) * 0.0005
            tax_cost = 0.005 + (i % 3) * 0.002
            liquidity_cost = (i % 7) * 0.001

            action = StockAction(
                symbol=f"STOCK_{i:02d}",
                action_type=ActionType.BUY if i % 2 == 0 else ActionType.SELL,
                expected_return=expected_return,
                volatility=volatility,
                transaction_cost=transaction_cost,
                tax_cost=tax_cost,
                liquidity_cost=liquidity_cost,
            )
            candidates.append(action)

        # Select top 20
        selected = engine.recommend_actions(candidates, k=20)

        # Verify count
        assert len(selected) == 20

        # Verify ordering is descending by utility
        utilities = [engine.compute_utility(action) for action in selected]
        for i in range(len(utilities) - 1):
            assert utilities[i] >= utilities[i + 1], \
                f"Utilities not sorted: {utilities[i]} < {utilities[i + 1]}"

        # Verify all selected have positive utility (if available)
        max_utility = max(
            engine.compute_utility(action) for action in candidates
        )
        if max_utility > 0:
            selected_utilities = [
                engine.compute_utility(action) for action in selected
            ]
            # Top selections should have reasonable positive utility
            assert selected_utilities[0] > 0 or all(u <= 0 for u in utilities)

        # Verify top 20 are actually the best 20
        all_utilities = [
            (engine.compute_utility(action), action.symbol)
            for action in candidates
        ]
        all_utilities.sort(reverse=True, key=lambda x: x[0])
        top_20_symbols = set(symbol for _, symbol in all_utilities[:20])
        selected_symbols = set(action.symbol for action in selected)

        assert selected_symbols == top_20_symbols, \
            f"Selected {selected_symbols} != expected {top_20_symbols}"

    def test_portfolio_with_varied_risk_profiles(self):
        """Test portfolio selection with varied risk and return profiles."""
        engine = DecisionEngine()

        candidates = []

        # High return, high risk
        for i in range(10):
            action = StockAction(
                symbol=f"AGGRESSIVE_{i}",
                action_type=ActionType.BUY,
                expected_return=0.25,
                volatility=0.40,
                transaction_cost=0.002,
                tax_cost=0.01,
                liquidity_cost=0.005,
            )
            candidates.append(action)

        # Medium return, medium risk
        for i in range(10):
            action = StockAction(
                symbol=f"BALANCED_{i}",
                action_type=ActionType.BUY,
                expected_return=0.15,
                volatility=0.20,
                transaction_cost=0.001,
                tax_cost=0.005,
                liquidity_cost=0.002,
            )
            candidates.append(action)

        # Low return, low risk
        for i in range(10):
            action = StockAction(
                symbol=f"CONSERVATIVE_{i}",
                action_type=ActionType.BUY,
                expected_return=0.05,
                volatility=0.08,
                transaction_cost=0.001,
                tax_cost=0.003,
                liquidity_cost=0.0,
            )
            candidates.append(action)

        # Select top 20
        selected = engine.recommend_actions(candidates, k=20)

        assert len(selected) == 20

        # Should favor higher utility (which needs good return-to-risk ratio)
        selected_symbols = [action.symbol for action in selected]

        # Count by profile
        aggressive_count = sum(
            1 for s in selected_symbols if s.startswith("AGGRESSIVE")
        )
        balanced_count = sum(
            1 for s in selected_symbols if s.startswith("BALANCED")
        )
        conservative_count = sum(
            1 for s in selected_symbols if s.startswith("CONSERVATIVE")
        )

        # Should prefer balanced and aggressive over conservative
        # (balanced has 0.15 - 0.5*0.20 - costs ≈ 0.08 utility)
        # (aggressive has 0.25 - 0.5*0.40 - costs ≈ 0.08 utility)
        # (conservative has 0.05 - 0.5*0.08 - costs ≈ 0.01 utility)
        assert balanced_count + aggressive_count >= 10

    def test_prediction_tracking_during_selection(self):
        """Test prediction tracking while selecting actions."""
        engine = DecisionEngine()

        candidates = [
            StockAction(
                symbol=f"STOCK_{i}",
                action_type=ActionType.BUY if i % 2 == 0 else ActionType.SELL,
                expected_return=0.10,
                volatility=0.15,
                transaction_cost=0.001,
                tax_cost=0.005,
                liquidity_cost=0.0,
            )
            for i in range(10)
        ]

        selected = engine.recommend_actions(candidates, k=5)
        assert len(selected) == 5

        # Record predictions for selected actions
        for action in selected:
            # Predict the action's type, but only half correct
            actual = action.action_type if action.symbol.endswith(("0", "2", "4")) \
                else ActionType.HOLD
            engine.record_prediction(
                action.symbol,
                action.action_type,
                actual,
            )

        # Check accuracy
        accuracy = engine.get_prediction_accuracy()
        assert 0.0 <= accuracy <= 1.0
        # With 5 predictions and some correct/incorrect
        assert accuracy == 0.6  # 3 correct out of 5

    def test_empty_portfolio_selection(self):
        """Test selection from empty candidate list."""
        engine = DecisionEngine()
        selected = engine.recommend_actions([], k=20)
        assert len(selected) == 0
        assert selected == []

    def test_single_candidate_selection(self):
        """Test selection from single candidate."""
        engine = DecisionEngine()
        candidates = [
            StockAction(
                symbol="ONLY_ONE",
                action_type=ActionType.BUY,
                expected_return=0.10,
                volatility=0.15,
                transaction_cost=0.001,
                tax_cost=0.005,
                liquidity_cost=0.0,
            )
        ]

        selected = engine.recommend_actions(candidates, k=20)
        assert len(selected) == 1
        assert selected[0].symbol == "ONLY_ONE"
