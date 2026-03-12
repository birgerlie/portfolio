"""End-to-end tests for credibility tracking across full prediction lifecycle."""

from datetime import datetime, timedelta

from trading_backtest.credibility import (
    SourceCredibility,
    PredictionRecord,
    CredibilityTracker,
)


class TestCredibilityTrackingFullCycle:
    """Test full credibility tracking over 10 predictions."""

    def test_credibility_tracking_full_cycle(self):
        """Track analyst credibility over 10 predictions with mixed outcomes."""
        tracker = CredibilityTracker()
        source_name = "analyst_a"

        # Setup initial source
        source = SourceCredibility(
            source_name=source_name,
            trust=0.6,
            recency=1.0,
            consistency=0.75,
        )
        tracker.add_source(source)

        # Track 10 predictions with mixed outcomes
        predictions_data = [
            (100.0, 101.5, 0),    # Accurate (+1.5%)
            (102.0, 104.0, 1),    # Accurate (+2%)
            (105.0, 108.5, 2),    # Inaccurate (+3.3%, acceptable)
            (110.0, 125.0, 3),    # Very inaccurate (+13.6%, bad)
            (125.0, 126.5, 4),    # Accurate (+1.2%)
            (128.0, 142.0, 5),    # Very inaccurate (+10.9%, bad)
            (142.0, 143.0, 6),    # Accurate (+0.7%)
            (144.0, 146.0, 7),    # Accurate (+1.4%)
            (147.0, 160.0, 8),    # Very inaccurate (+8.8%, bad)
            (160.0, 161.0, 9),    # Accurate (+0.6%)
        ]

        predictions = []
        for prediction, actual, day_offset in predictions_data:
            date = datetime.now() - timedelta(days=9 - day_offset)
            record = PredictionRecord(
                source=source_name,
                prediction=prediction,
                actual=actual,
                date=date,
            )
            tracker.add_prediction(record)
            predictions.append(record)

        # Verify source was updated
        final_source = tracker.get_source(source_name)
        assert final_source is not None
        assert len(tracker.get_predictions(source_name)) == 10

        # Check that prediction counts are reasonable
        accurate_count = sum(
            1 for p in predictions if abs(p.actual - p.prediction) / p.prediction < 0.03
        )
        inaccurate_count = 10 - accurate_count

        assert accurate_count >= 4  # At least 4 accurate
        assert inaccurate_count >= 3  # At least 3 inaccurate

        # Trust should have adjusted based on predictions
        # With 4 accurate and 3 very inaccurate, trust should be moderate
        assert 0.3 <= final_source.trust <= 0.8

        # Recency should be high for most recent predictions
        assert final_source.recency >= 0.9

        # Consistency should reflect the balance of accurate vs inaccurate
        assert 0.4 <= final_source.consistency <= 0.9

        # Final credibility should be reasonable
        assert 0.0 <= final_source.credibility <= 1.0

    def test_multiple_sources_tracking(self):
        """Track credibility for multiple analysts simultaneously."""
        tracker = CredibilityTracker()

        # Create two analysts with different profiles
        reliable_analyst = SourceCredibility(
            source_name="reliable_analyst",
            trust=0.85,
            recency=1.0,
            consistency=0.9,
        )
        unreliable_analyst = SourceCredibility(
            source_name="unreliable_analyst",
            trust=0.4,
            recency=1.0,
            consistency=0.5,
        )

        tracker.add_source(reliable_analyst)
        tracker.add_source(unreliable_analyst)

        # Add accurate predictions for reliable analyst
        for i in range(5):
            date = datetime.now() - timedelta(days=4 - i)
            record = PredictionRecord(
                source="reliable_analyst",
                prediction=100.0 + i * 10,
                actual=100.0 + i * 10 + 0.5,  # Accurate (+0.5%)
                date=date,
            )
            tracker.add_prediction(record)

        # Add inaccurate predictions for unreliable analyst
        for i in range(5):
            date = datetime.now() - timedelta(days=4 - i)
            record = PredictionRecord(
                source="unreliable_analyst",
                prediction=100.0 + i * 10,
                actual=100.0 + i * 10 + 20.0,  # Very inaccurate (+20%)
                date=date,
            )
            tracker.add_prediction(record)

        # Reliable analyst should have higher credibility
        reliable = tracker.get_source("reliable_analyst")
        unreliable = tracker.get_source("unreliable_analyst")

        assert reliable.credibility > unreliable.credibility
        assert reliable.trust > unreliable.trust

    def test_source_credibility_improves_with_consistency(self):
        """Credibility increases when analyst becomes consistently accurate."""
        tracker = CredibilityTracker()
        source_name = "improving_analyst"

        source = SourceCredibility(
            source_name=source_name,
            trust=0.5,
            recency=1.0,
            consistency=0.5,
        )
        tracker.add_source(source)

        # Add 5 accurate predictions
        for i in range(5):
            date = datetime.now() - timedelta(days=4 - i)
            record = PredictionRecord(
                source=source_name,
                prediction=100.0,
                actual=100.5,  # Accurate
                date=date,
            )
            tracker.add_prediction(record)

        mid_source = tracker.get_source(source_name)
        mid_credibility = mid_source.credibility

        # Add 5 more accurate predictions
        for i in range(5, 10):
            date = datetime.now() - timedelta(days=9 - i)
            record = PredictionRecord(
                source=source_name,
                prediction=100.0,
                actual=100.5,  # Accurate
                date=date,
            )
            tracker.add_prediction(record)

        final_source = tracker.get_source(source_name)
        final_credibility = final_source.credibility

        # Credibility should increase with more consistent predictions
        assert final_credibility >= mid_credibility
        assert final_source.consistency > 0.7  # High consistency

    def test_empty_tracker_and_missing_source(self):
        """Handle empty tracker and missing sources gracefully."""
        tracker = CredibilityTracker()

        # Getting non-existent source should return None
        missing = tracker.get_source("non_existent")
        assert missing is None

        # Getting predictions for non-existent source should return empty list
        predictions = tracker.get_predictions("non_existent")
        assert predictions == []
