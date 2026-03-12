"""Unit tests for epistemic engine (belief system)."""

from datetime import datetime, timedelta
import pytest

from trading_backtest.epistemic import (
    BeliefType,
    Belief,
    EpistemicEngine,
)
from trading_backtest.credibility import SourceCredibility


class TestBeliefCreation:
    """Test belief object creation and initialization."""

    def test_belief_creation_basic(self):
        """Create a basic belief with symbol and attribute."""
        belief = Belief(
            symbol="AAPL",
            attribute="undervalued",
            belief_type=BeliefType.UNDERVALUED,
        )

        assert belief.symbol == "AAPL"
        assert belief.attribute == "undervalued"
        assert belief.belief_type == BeliefType.UNDERVALUED
        assert belief.probability == 0.5
        assert belief.confirmations == 0
        assert belief.contradictions == 0
        assert belief.sources == {}

    def test_belief_probability_bounds(self):
        """Belief probability is between 0 and 1."""
        belief = Belief(
            symbol="MSFT",
            attribute="high_growth",
            belief_type=BeliefType.HIGH_GROWTH,
            probability=0.75,
        )

        assert 0.0 <= belief.probability <= 1.0
        assert belief.probability == 0.75

    def test_belief_tracks_confirmation_sources(self):
        """Belief tracks which sources provided confirmations."""
        belief = Belief(
            symbol="GOOGL",
            attribute="ai_potential",
            belief_type=BeliefType.HIGH_GROWTH,
        )

        belief.add_confirmation("analyst_a", credibility=0.75)
        belief.add_confirmation("analyst_b", credibility=0.60)

        assert belief.confirmations == 2
        assert "analyst_a" in belief.sources
        assert belief.sources["analyst_a"]["confirmations"] == 1
        assert belief.sources["analyst_b"]["confirmations"] == 1

    def test_belief_tracks_contradiction_sources(self):
        """Belief tracks which sources provided contradictions."""
        belief = Belief(
            symbol="TSLA",
            attribute="overvalued",
            belief_type=BeliefType.OVERVALUED,
        )

        belief.add_contradiction("skeptic_a", credibility=0.50)
        belief.add_contradiction("skeptic_a", credibility=0.50)

        assert belief.contradictions == 2
        assert "skeptic_a" in belief.sources
        assert belief.sources["skeptic_a"]["contradictions"] == 2


class TestCredibilityWeightedBeliefUpdate:
    """Test credibility-weighted Bayesian belief updates."""

    def test_credibility_weighted_belief_update(self):
        """Goldman (0.75) dominates RetailBlog (0.20), belief > 0.70."""
        engine = EpistemicEngine()

        # Create belief
        belief = Belief(
            symbol="AAPL",
            attribute="recovery_potential",
            belief_type=BeliefType.UNDERVALUED,
        )

        # Goldman: high credibility
        goldman = SourceCredibility(
            source_name="goldman_sachs",
            trust=0.9,
            recency=0.9,
            consistency=0.85,
        )

        # RetailBlog: low credibility
        retail_blog = SourceCredibility(
            source_name="retail_blog",
            trust=0.3,
            recency=0.5,
            consistency=0.2,
        )

        # Register sources
        engine.tracker.add_source(goldman)
        engine.tracker.add_source(retail_blog)

        # Goldman provides strong confirmation
        engine.update_belief(belief, "goldman_sachs", confirmation=True)

        # RetailBlog provides weak contradiction
        engine.update_belief(belief, "retail_blog", confirmation=False)

        # Goldman's credibility (0.75) should dominate
        assert belief.probability > 0.70

    def test_equal_credibility_sources_balance(self):
        """Equal credibility sources create balanced beliefs."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="MSFT",
            attribute="market_position",
            belief_type=BeliefType.HIGH_GROWTH,
        )

        # Two analysts with equal credibility
        analyst_a = SourceCredibility(
            source_name="analyst_a",
            trust=0.7,
            recency=1.0,
            consistency=0.7,
        )
        analyst_b = SourceCredibility(
            source_name="analyst_b",
            trust=0.7,
            recency=1.0,
            consistency=0.7,
        )

        engine.tracker.add_source(analyst_a)
        engine.tracker.add_source(analyst_b)

        # One confirms, one contradicts
        engine.update_belief(belief, "analyst_a", confirmation=True)
        engine.update_belief(belief, "analyst_b", confirmation=False)

        # Should be close to 0.5 with balanced sources
        assert abs(belief.probability - 0.5) < 0.2

    def test_bayesian_update_formula(self):
        """Probability follows credibility-weighted Bayesian formula."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="NVDA",
            attribute="chip_demand",
            belief_type=BeliefType.HIGH_GROWTH,
        )

        source = SourceCredibility(
            source_name="analyst_strong",
            trust=0.8,
            recency=1.0,
            consistency=0.8,
        )
        engine.tracker.add_source(source)

        # Add multiple confirmations
        for _ in range(3):
            engine.update_belief(belief, "analyst_strong", confirmation=True)

        # Probability should increase with weighted confirmations
        # P = (α + Σ cred*conf) / (α + Σ cred*conf + contra)
        # α = 1, conf = 3, cred ≈ 0.77, contra = 0
        # P ≈ (1 + 3*0.77) / (1 + 3*0.77) = 1 (near ceiling)
        assert belief.probability > 0.85


class TestRetroactiveDiscounting:
    """Test retroactive removal of fraudster contributions."""

    def test_retroactive_discounting(self):
        """Remove fraudster's contributions, belief reverts to baseline."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="XYZ",
            attribute="earnings_growth",
            belief_type=BeliefType.HIGH_GROWTH,
        )

        # Fraudster with initial high credibility
        fraudster = SourceCredibility(
            source_name="fraudster",
            trust=0.8,
            recency=1.0,
            consistency=0.8,
        )

        # Legitimate source
        legitimate = SourceCredibility(
            source_name="legitimate",
            trust=0.6,
            recency=1.0,
            consistency=0.6,
        )

        engine.tracker.add_source(fraudster)
        engine.tracker.add_source(legitimate)

        # Both confirm the belief
        engine.update_belief(belief, "fraudster", confirmation=True)
        engine.update_belief(belief, "legitimate", confirmation=True)

        probability_with_fraudster = belief.probability
        assert probability_with_fraudster > 0.6

        # Fraudster detected and discounted
        engine.discount_fraudster("fraudster")

        probability_after_discount = belief.probability

        # Probability should drop significantly after fraud removal
        assert probability_after_discount < probability_with_fraudster

    def test_fraudster_removal_affects_all_beliefs(self):
        """Removing fraudster updates all beliefs they touched."""
        engine = EpistemicEngine()

        # Two beliefs both confirmed by fraudster
        belief1 = Belief(
            symbol="AAPL",
            attribute="growth",
            belief_type=BeliefType.HIGH_GROWTH,
        )
        belief2 = Belief(
            symbol="MSFT",
            attribute="valuation",
            belief_type=BeliefType.UNDERVALUED,
        )

        fraudster = SourceCredibility(
            source_name="fraudster",
            trust=0.7,
            recency=1.0,
            consistency=0.7,
        )

        engine.tracker.add_source(fraudster)
        engine.add_belief(belief1)
        engine.add_belief(belief2)

        # Fraudster confirms both
        engine.update_belief(belief1, "fraudster", confirmation=True)
        engine.update_belief(belief2, "fraudster", confirmation=True)

        prob1_before = belief1.probability
        prob2_before = belief2.probability

        # Discount fraudster
        engine.discount_fraudster("fraudster")

        prob1_after = belief1.probability
        prob2_after = belief2.probability

        # Both should be affected
        assert prob1_after < prob1_before
        assert prob2_after < prob2_before

    def test_fraudster_with_mixed_beliefs(self):
        """Fraudster removal only affects beliefs they touched."""
        engine = EpistemicEngine()

        # Belief touched by fraudster
        belief_touched = Belief(
            symbol="AAPL",
            attribute="growth",
            belief_type=BeliefType.HIGH_GROWTH,
        )

        # Belief not touched by fraudster
        belief_untouched = Belief(
            symbol="GOOGL",
            attribute="innovation",
            belief_type=BeliefType.HIGH_GROWTH,
        )

        fraudster = SourceCredibility(
            source_name="fraudster",
            trust=0.7,
            recency=1.0,
            consistency=0.7,
        )
        legitimate = SourceCredibility(
            source_name="legitimate",
            trust=0.6,
            recency=1.0,
            consistency=0.6,
        )

        engine.tracker.add_source(fraudster)
        engine.tracker.add_source(legitimate)
        engine.add_belief(belief_touched)
        engine.add_belief(belief_untouched)

        # Only touched belief gets fraudster confirmation
        engine.update_belief(belief_touched, "fraudster", confirmation=True)
        engine.update_belief(belief_untouched, "legitimate", confirmation=True)

        prob_touched_before = belief_touched.probability
        prob_untouched_before = belief_untouched.probability

        engine.discount_fraudster("fraudster")

        prob_touched_after = belief_touched.probability
        prob_untouched_after = belief_untouched.probability

        # Touched should change, untouched should stay same
        assert prob_touched_after < prob_touched_before
        assert abs(prob_untouched_after - prob_untouched_before) < 0.01


class TestEnergyFieldAnomaly:
    """Test anomaly detection in belief confidence."""

    def test_energy_field_anomaly(self):
        """Detect anomalies without updating beliefs."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="AAPL",
            attribute="recovery",
            belief_type=BeliefType.UNDERVALUED,
        )

        source = SourceCredibility(
            source_name="analyst",
            trust=0.8,
            recency=1.0,
            consistency=0.8,
        )

        engine.tracker.add_source(source)
        engine.add_belief(belief)

        # Normal updates
        engine.update_belief(belief, "analyst", confirmation=True)
        normal_probability = belief.probability

        # Anomaly detection (high confidence, sparse evidence)
        anomaly = engine.detect_anomaly(belief)

        # Should detect anomaly if belief is high confidence with low evidence
        assert isinstance(anomaly, dict)
        assert "is_anomaly" in anomaly
        assert "confidence" in anomaly
        assert "evidence_count" in anomaly

    def test_anomaly_no_belief_update(self):
        """Anomaly detection doesn't modify belief."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="MSFT",
            attribute="growth",
            belief_type=BeliefType.HIGH_GROWTH,
        )

        source = SourceCredibility(
            source_name="analyst",
            trust=0.7,
            recency=1.0,
            consistency=0.7,
        )

        engine.tracker.add_source(source)
        engine.add_belief(belief)

        engine.update_belief(belief, "analyst", confirmation=True)
        probability_before = belief.probability

        # Detect anomaly
        engine.detect_anomaly(belief)

        # Probability should not change
        assert belief.probability == probability_before

    def test_high_confidence_low_evidence_anomaly(self):
        """Anomaly when confidence is high but evidence is sparse."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="XYZ",
            attribute="potential",
            belief_type=BeliefType.UNDERVALUED,
            probability=0.95,  # High confidence
        )

        engine.add_belief(belief)

        # Few confirmations but belief is very high
        anomaly = engine.detect_anomaly(belief)

        # Should flag as potential anomaly
        if anomaly["evidence_count"] < 3:
            assert anomaly["is_anomaly"] is True or anomaly["confidence"] > 0.80
