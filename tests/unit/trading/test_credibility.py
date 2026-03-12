"""Unit tests for source credibility tracking."""

from datetime import datetime, timedelta
import pytest

from trading_backtest.credibility import (
    SourceCredibility,
    PredictionRecord,
    CredibilityTracker,
)


class TestCredibilityComputation:
    """Tests for credibility score calculation."""

    def test_credibility_formula(self):
        """Verify credibility = trust^0.6 * recency^0.2 * consistency^0.2."""
        source = SourceCredibility(
            source_name="analyst_a",
            trust=0.8,
            recency=0.9,
            consistency=0.7,
        )

        # Expected: 0.8^0.6 * 0.9^0.2 * 0.7^0.2
        # 0.8^0.6 ≈ 0.8614
        # 0.9^0.2 ≈ 0.9795
        # 0.7^0.2 ≈ 0.9145
        # Product ≈ 0.7700
        expected = (0.8 ** 0.6) * (0.9 ** 0.2) * (0.7 ** 0.2)
        assert abs(source.credibility - expected) < 1e-4

    def test_credibility_min_bounds(self):
        """Credibility is 0 when any component is 0."""
        source = SourceCredibility(
            source_name="bad_source",
            trust=0.0,
            recency=0.9,
            consistency=0.7,
        )
        assert source.credibility == 0.0

    def test_credibility_max_bounds(self):
        """Credibility is 1 when all components are 1."""
        source = SourceCredibility(
            source_name="perfect_source",
            trust=1.0,
            recency=1.0,
            consistency=1.0,
        )
        assert abs(source.credibility - 1.0) < 1e-4

    def test_credibility_property_read_only(self):
        """Credibility is computed property, not settable."""
        source = SourceCredibility(
            source_name="test",
            trust=0.5,
            recency=0.5,
            consistency=0.5,
        )
        with pytest.raises(AttributeError):
            source.credibility = 0.8


class TestPredictionRecord:
    """Tests for prediction record structure."""

    def test_prediction_record_creation(self):
        """Create a prediction record with all fields."""
        now = datetime.now()
        record = PredictionRecord(
            source="analyst_a",
            prediction=150.5,
            actual=152.3,
            date=now,
        )

        assert record.source == "analyst_a"
        assert record.prediction == 150.5
        assert record.actual == 152.3
        assert record.date == now

    def test_prediction_record_error_calculation(self):
        """Compute absolute error between prediction and actual."""
        now = datetime.now()
        record = PredictionRecord(
            source="analyst_a",
            prediction=100.0,
            actual=110.0,
            date=now,
        )

        error = abs(record.prediction - record.actual)
        assert error == 10.0


class TestUpdateTrustFromPredictions:
    """Tests for trust updates based on prediction accuracy."""

    def test_accurate_prediction_increases_trust(self):
        """Trust increases when prediction is accurate (error < 2%)."""
        tracker = CredibilityTracker()
        source_name = "analyst_a"

        # Initial setup
        source = SourceCredibility(source_name, trust=0.5, recency=1.0, consistency=0.8)
        tracker.add_source(source)

        # Add accurate prediction (1% error)
        record = PredictionRecord(
            source=source_name,
            prediction=100.0,
            actual=101.0,
            date=datetime.now(),
        )

        initial_trust = tracker.get_source(source_name).trust
        tracker.add_prediction(record)
        updated_source = tracker.get_source(source_name)

        # Trust should increase
        assert updated_source.trust > initial_trust

    def test_inaccurate_prediction_decreases_trust(self):
        """Trust decreases when prediction is inaccurate (error > 5%)."""
        tracker = CredibilityTracker()
        source_name = "analyst_a"

        source = SourceCredibility(source_name, trust=0.8, recency=1.0, consistency=0.8)
        tracker.add_source(source)

        # Add inaccurate prediction (10% error)
        record = PredictionRecord(
            source=source_name,
            prediction=100.0,
            actual=111.0,
            date=datetime.now(),
        )

        initial_trust = tracker.get_source(source_name).trust
        tracker.add_prediction(record)
        updated_source = tracker.get_source(source_name)

        # Trust should decrease
        assert updated_source.trust < initial_trust

    def test_trust_bounds_at_zero_and_one(self):
        """Trust stays between 0 and 1."""
        tracker = CredibilityTracker()
        source_name = "analyst_a"

        source = SourceCredibility(source_name, trust=0.95, recency=1.0, consistency=0.8)
        tracker.add_source(source)

        # Add predictions to push trust toward bounds
        for i in range(5):
            record = PredictionRecord(
                source=source_name,
                prediction=100.0 + i,
                actual=100.0 + i + 15.0,  # Large error
                date=datetime.now(),
            )
            tracker.add_prediction(record)

        updated_source = tracker.get_source(source_name)
        assert 0.0 <= updated_source.trust <= 1.0


class TestCredibilityDecaysWithAge:
    """Tests for recency-based credibility decay."""

    def test_recent_prediction_high_recency(self):
        """Recent predictions have high recency score."""
        tracker = CredibilityTracker()
        source_name = "analyst_a"

        source = SourceCredibility(source_name, trust=0.8, recency=1.0, consistency=0.8)
        tracker.add_source(source)

        # Add recent prediction (today)
        record = PredictionRecord(
            source=source_name,
            prediction=100.0,
            actual=101.0,
            date=datetime.now(),
        )
        tracker.add_prediction(record)

        updated_source = tracker.get_source(source_name)
        assert updated_source.recency >= 0.95  # Very recent

    def test_old_prediction_low_recency(self):
        """Old predictions have low recency score."""
        tracker = CredibilityTracker()
        source_name = "analyst_a"

        source = SourceCredibility(source_name, trust=0.8, recency=1.0, consistency=0.8)
        tracker.add_source(source)

        # Add old prediction (90 days ago)
        old_date = datetime.now() - timedelta(days=90)
        record = PredictionRecord(
            source=source_name,
            prediction=100.0,
            actual=101.0,
            date=old_date,
        )
        tracker.add_prediction(record)

        updated_source = tracker.get_source(source_name)
        assert updated_source.recency < 0.5  # Old enough to decay significantly

    def test_recency_decay_function(self):
        """Recency decays exponentially with age."""
        tracker = CredibilityTracker()
        source_name = "analyst_a"

        source = SourceCredibility(source_name, trust=0.8, recency=1.0, consistency=0.8)
        tracker.add_source(source)

        # Add prediction from 30 days ago
        thirty_days_ago = datetime.now() - timedelta(days=30)
        record = PredictionRecord(
            source=source_name,
            prediction=100.0,
            actual=101.0,
            date=thirty_days_ago,
        )
        tracker.add_prediction(record)

        recency_30 = tracker.get_source(source_name).recency

        # Add prediction from 60 days ago to reset recency
        source = SourceCredibility(source_name, trust=0.8, recency=1.0, consistency=0.8)
        tracker.update_source(source)

        sixty_days_ago = datetime.now() - timedelta(days=60)
        record = PredictionRecord(
            source=source_name,
            prediction=100.0,
            actual=101.0,
            date=sixty_days_ago,
        )
        tracker.add_prediction(record)

        recency_60 = tracker.get_source(source_name).recency

        # Recency at 60 days should be lower than at 30 days
        assert recency_60 < recency_30
