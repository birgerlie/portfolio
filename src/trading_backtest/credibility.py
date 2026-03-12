"""Source credibility tracking for analyst predictions."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict


@dataclass
class SourceCredibility:
    """Track credibility metrics for a data source."""

    source_name: str
    trust: float = 0.5
    recency: float = 1.0
    consistency: float = 0.5

    def __post_init__(self):
        """Validate credibility components are between 0 and 1."""
        for value, name in [
            (self.trust, "trust"),
            (self.recency, "recency"),
            (self.consistency, "consistency"),
        ]:
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1, got {value}")

    @property
    def credibility(self) -> float:
        """Compute credibility: trust^0.6 * recency^0.2 * consistency^0.2."""
        if self.trust == 0:
            return 0.0
        return (self.trust ** 0.6) * (self.recency ** 0.2) * (self.consistency ** 0.2)


@dataclass
class PredictionRecord:
    """Record of a single prediction and its outcome."""

    source: str
    prediction: float
    actual: float
    date: datetime

    def error_percent(self) -> float:
        """Calculate absolute percentage error."""
        if self.prediction == 0:
            return 0.0
        return abs(self.actual - self.prediction) / self.prediction


class CredibilityTracker:
    """Manage source credibility and prediction records."""

    def __init__(self):
        """Initialize empty tracker."""
        self._sources: Dict[str, SourceCredibility] = {}
        self._predictions: Dict[str, List[PredictionRecord]] = {}

    def add_source(self, source: SourceCredibility) -> None:
        """Register a new source."""
        self._sources[source.source_name] = source
        if source.source_name not in self._predictions:
            self._predictions[source.source_name] = []

    def update_source(self, source: SourceCredibility) -> None:
        """Update an existing source."""
        self._sources[source.source_name] = source

    def get_source(self, source_name: str) -> Optional[SourceCredibility]:
        """Get source credibility by name."""
        return self._sources.get(source_name)

    def get_predictions(self, source_name: str) -> List[PredictionRecord]:
        """Get all predictions for a source."""
        return self._predictions.get(source_name, [])

    def add_prediction(self, record: PredictionRecord) -> None:
        """Add prediction and update source credibility."""
        if record.source not in self._sources:
            raise ValueError(f"Unknown source: {record.source}")

        self._predictions[record.source].append(record)
        self._update_credibility_from_prediction(record)

    def _update_credibility_from_prediction(self, record: PredictionRecord) -> None:
        """Update source trust and consistency based on prediction accuracy."""
        source = self._sources[record.source]
        error_percent = record.error_percent()

        # Update trust based on accuracy
        new_trust = self._compute_new_trust(source.trust, error_percent)

        # Update recency based on prediction date
        new_recency = self._compute_recency(record.date)

        # Update consistency based on prediction history
        new_consistency = self._compute_consistency(record.source)

        # Update source
        source.trust = new_trust
        source.recency = new_recency
        source.consistency = new_consistency

    def _compute_new_trust(self, current_trust: float, error_percent: float) -> float:
        """Update trust based on prediction error."""
        if error_percent < 0.02:  # < 2% error
            adjustment = 0.05
        elif error_percent < 0.05:  # < 5% error
            adjustment = 0.01
        else:  # >= 5% error
            adjustment = -0.10

        new_trust = current_trust + adjustment
        return max(0.0, min(1.0, new_trust))

    def _compute_recency(self, prediction_date: datetime) -> float:
        """Compute recency decay based on time since prediction."""
        days_old = (datetime.now() - prediction_date).days
        # Exponential decay: e^(-days_old / 90)
        recency = pow(2.71828, -days_old / 90.0)
        return max(0.0, min(1.0, recency))

    def _compute_consistency(self, source_name: str) -> float:
        """Compute consistency from prediction history."""
        predictions = self._predictions.get(source_name, [])
        if not predictions:
            return 0.5

        if len(predictions) < 2:
            return 0.5

        # Calculate consistency as ratio of accurate predictions
        accurate_count = sum(
            1 for p in predictions if p.error_percent() < 0.03
        )
        return accurate_count / len(predictions)
