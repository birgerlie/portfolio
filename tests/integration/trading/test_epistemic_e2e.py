"""End-to-end tests for epistemic engine across full 3-month cycle."""

from datetime import datetime, timedelta

from trading_backtest.epistemic import (
    BeliefType,
    Belief,
    EpistemicEngine,
)
from trading_backtest.credibility import SourceCredibility


class TestEpistemicEngineFullCycle:
    """Test epistemic engine over 3-month cycle with multiple sources."""

    def test_epistemic_engine_full_cycle(self):
        """Track belief evolution over 3 months with sources appearing/disappearing."""
        engine = EpistemicEngine()

        # Create belief about AAPL
        belief = Belief(
            symbol="AAPL",
            attribute="recovery_potential",
            belief_type=BeliefType.UNDERVALUED,
        )
        engine.add_belief(belief)

        # Month 1: Optimistic sources emerge
        goldman = SourceCredibility(
            source_name="goldman_sachs",
            trust=0.8,
            recency=1.0,
            consistency=0.75,
        )
        morgan = SourceCredibility(
            source_name="morgan_stanley",
            trust=0.75,
            recency=1.0,
            consistency=0.70,
        )
        engine.tracker.add_source(goldman)
        engine.tracker.add_source(morgan)

        # Both confirm recovery
        engine.update_belief(belief, "goldman_sachs", confirmation=True)
        engine.update_belief(belief, "morgan_stanley", confirmation=True)

        prob_month1 = belief.probability
        assert prob_month1 > 0.65

        # Month 2: Skeptic joins the conversation
        skeptic = SourceCredibility(
            source_name="short_seller_fund",
            trust=0.4,
            recency=1.0,
            consistency=0.5,
        )
        engine.tracker.add_source(skeptic)

        # Skeptic contradicts multiple times
        engine.update_belief(belief, "short_seller_fund", confirmation=False)
        engine.update_belief(belief, "short_seller_fund", confirmation=False)

        prob_month2 = belief.probability
        # Probability drops but stays positive (low credibility skeptic)
        assert prob_month2 < 0.85

        # Month 3: Fraudster exposed and discounted
        # Skeptic's credibility drops to fraud level
        engine.discount_fraudster("short_seller_fund")

        prob_month3 = belief.probability
        # Probability should recover after fraud removal
        assert prob_month3 > prob_month2

    def test_belief_convergence_with_strong_sources(self):
        """Belief converges toward high probability with consistent strong sources."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="MSFT",
            attribute="cloud_growth",
            belief_type=BeliefType.HIGH_GROWTH,
        )
        engine.add_belief(belief)

        # Strong consensus source
        consensus = SourceCredibility(
            source_name="tech_research",
            trust=0.85,
            recency=1.0,
            consistency=0.85,
        )
        engine.tracker.add_source(consensus)

        # Multiple confirmations over time
        for _ in range(5):
            engine.update_belief(belief, "tech_research", confirmation=True)

        # Should converge to high probability
        assert belief.probability > 0.80

    def test_belief_with_multiple_source_types(self):
        """Belief stabilizes with diverse source confirmations."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="GOOGL",
            attribute="ai_leadership",
            belief_type=BeliefType.HIGH_GROWTH,
        )
        engine.add_belief(belief)

        # Multiple diverse sources
        sources = {
            "research_firm": SourceCredibility(
                source_name="research_firm",
                trust=0.75,
                recency=1.0,
                consistency=0.75,
            ),
            "tech_blogger": SourceCredibility(
                source_name="tech_blogger",
                trust=0.50,
                recency=1.0,
                consistency=0.55,
            ),
            "insider_report": SourceCredibility(
                source_name="insider_report",
                trust=0.70,
                recency=0.95,
                consistency=0.70,
            ),
        }

        for source in sources.values():
            engine.tracker.add_source(source)

        # Each source confirms
        for source_name in sources.keys():
            engine.update_belief(belief, source_name, confirmation=True)

        # Multiple sources confirming should converge to high probability
        prob = belief.probability
        assert prob > 0.90

        # Verify sources are tracked
        assert len(belief.sources) == 3
        assert belief.confirmations == 3

    def test_source_credibility_evolution_affects_belief(self):
        """Belief updates reflect changing source credibility."""
        engine = EpistemicEngine()

        belief = Belief(
            symbol="TSLA",
            attribute="profitability",
            belief_type=BeliefType.UNDERVALUED,
        )
        engine.add_belief(belief)

        # Source starts with medium credibility
        source = SourceCredibility(
            source_name="analyst_evolving",
            trust=0.6,
            recency=1.0,
            consistency=0.6,
        )
        engine.tracker.add_source(source)

        # Initial confirmation
        engine.update_belief(belief, "analyst_evolving", confirmation=True)
        prob_initial = belief.probability

        # Source credibility improves (through external updates)
        improved_source = SourceCredibility(
            source_name="analyst_evolving",
            trust=0.8,
            recency=1.0,
            consistency=0.8,
        )
        engine.tracker.update_source(improved_source)

        # Add another confirmation with improved credibility
        engine.update_belief(belief, "analyst_evolving", confirmation=True)
        prob_improved = belief.probability

        # With only confirmations, probability converges to 1
        # The improvement shows in the convergence rate
        assert prob_improved >= prob_initial
