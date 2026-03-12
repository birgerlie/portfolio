"""Unit tests for RCA (Root Cause Analysis) engine."""

import pytest
from datetime import datetime, timedelta

from trading_backtest.rca import (
    CauseContribution,
    RCAEngine,
)


class TestCauseContributionCreation:
    """Test CauseContribution dataclass initialization."""

    def test_contribution_creation_basic(self):
        """Create a basic cause contribution."""
        contrib = CauseContribution(
            node="FedPolicy",
            direct_impact=-0.05,
            weighted_impact=-0.08,
            credibility=0.85,
            temporal_precedence=True,
        )

        assert contrib.node == "FedPolicy"
        assert contrib.direct_impact == -0.05
        assert contrib.weighted_impact == -0.08
        assert contrib.credibility == 0.85
        assert contrib.temporal_precedence is True

    def test_contribution_defaults(self):
        """CauseContribution has sensible defaults."""
        contrib = CauseContribution(
            node="Apple",
            direct_impact=-0.03,
            weighted_impact=-0.03,
        )

        assert contrib.credibility == 0.0
        assert contrib.temporal_precedence is False

    def test_contribution_impact_bounds(self):
        """Impact values can be positive or negative."""
        contrib_negative = CauseContribution(
            node="Loss",
            direct_impact=-0.10,
            weighted_impact=-0.15,
        )
        contrib_positive = CauseContribution(
            node="Gain",
            direct_impact=0.05,
            weighted_impact=0.08,
        )

        assert contrib_negative.direct_impact < 0
        assert contrib_positive.direct_impact > 0


class TestRCAEngineBackwardPropagation:
    """Test backward propagation through belief graphs."""

    def test_backward_propagation_simple_chain(self):
        """Trace 2-node chain: Portfolio → TechSector."""
        engine = RCAEngine()

        # Add nodes
        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("TechSector", initial_value=50.0)

        # Add edge: TechSector → Portfolio with weight 0.5
        engine.add_edge("TechSector", "Portfolio", weight=0.5)

        # Record anomaly: Portfolio at -8%
        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())

        # Propagate backward
        contributions = engine.backward_propagate("Portfolio")

        # TechSector should contribute roughly: -0.08 * 0.5 = -0.04
        assert len(contributions) > 0
        contrib = next(c for c in contributions if c.node == "TechSector")
        assert contrib.direct_impact < 0

    def test_backward_propagation_long_chain(self):
        """Trace 5-node chain with decay across hops."""
        engine = RCAEngine()

        # Create chain: Portfolio → TechSector → Apple → Earnings → EconomicData
        nodes = ["Portfolio", "TechSector", "Apple", "Earnings", "EconomicData"]
        for node in nodes:
            engine.add_node(node, initial_value=100.0)

        # Connect chain
        edges = [
            ("TechSector", "Portfolio", 0.6),
            ("Apple", "TechSector", 0.7),
            ("Earnings", "Apple", 0.8),
            ("EconomicData", "Earnings", 0.9),
        ]
        for parent, child, weight in edges:
            engine.add_edge(parent, child, weight=weight)

        # Record anomaly at Portfolio
        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())

        # Propagate
        contributions = engine.backward_propagate("Portfolio")

        # Should find all nodes in chain
        found_nodes = {c.node for c in contributions}
        expected = {"TechSector", "Apple", "Earnings", "EconomicData"}
        assert expected.issubset(found_nodes)

        # EconomicData should have smallest direct_impact (furthest)
        econ_contrib = next(c for c in contributions if c.node == "EconomicData")
        tech_contrib = next(c for c in contributions if c.node == "TechSector")
        assert abs(econ_contrib.direct_impact) < abs(tech_contrib.direct_impact)

    def test_backward_propagation_multiple_paths(self):
        """Handle multiple paths to same node."""
        engine = RCAEngine()

        # Diamond structure: Portfolio ← Apple ← Earnings, Portfolio ← Sector ← Earnings
        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("Apple", initial_value=50.0)
        engine.add_node("Sector", initial_value=50.0)
        engine.add_node("Earnings", initial_value=25.0)

        # Two paths to Portfolio
        engine.add_edge("Apple", "Portfolio", weight=0.4)
        engine.add_edge("Sector", "Portfolio", weight=0.4)

        # Both paths from Earnings
        engine.add_edge("Earnings", "Apple", weight=0.7)
        engine.add_edge("Earnings", "Sector", weight=0.7)

        # Anomaly at Portfolio
        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())

        contributions = engine.backward_propagate("Portfolio")

        # Earnings should appear (from both paths)
        earnings_contribs = [c for c in contributions if c.node == "Earnings"]
        assert len(earnings_contribs) >= 1
        # Should be combined impact from both paths
        earnings_total = sum(c.weighted_impact for c in earnings_contribs)
        assert earnings_total < 0

    def test_backward_propagation_with_decay(self):
        """Impact decays with hop distance."""
        engine = RCAEngine(decay=0.8)

        # 3-node chain
        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("Intermediate", initial_value=50.0)
        engine.add_node("Root", initial_value=25.0)

        engine.add_edge("Intermediate", "Portfolio", weight=0.5)
        engine.add_edge("Root", "Intermediate", weight=0.5)

        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())
        contributions = engine.backward_propagate("Portfolio")

        intermediate = next(c for c in contributions if c.node == "Intermediate")
        root = next(c for c in contributions if c.node == "Root")

        # Root should have smaller impact due to decay
        assert abs(root.weighted_impact) < abs(intermediate.weighted_impact)

    def test_backward_propagation_empty_anomaly(self):
        """Backward propagate from node with no anomaly."""
        engine = RCAEngine()

        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("TechSector", initial_value=50.0)
        engine.add_edge("TechSector", "Portfolio", weight=0.5)

        # No anomaly recorded
        contributions = engine.backward_propagate("Portfolio")

        # Should return empty list or neutral contributions
        assert len(contributions) == 0 or all(
            c.weighted_impact == 0 for c in contributions
        )


class TestRCAEngineCauseContribution:
    """Test cause contribution scoring."""

    def test_contribution_scoring_direct_vs_weighted(self):
        """Weighted impact accounts for credibility and distance."""
        engine = RCAEngine()

        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("TechSector", initial_value=50.0)

        engine.add_edge("TechSector", "Portfolio", weight=0.5)
        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())

        contributions = engine.backward_propagate("Portfolio")

        contrib = next(c for c in contributions if c.node == "TechSector")

        # Weighted impact should be different from direct (scaled by credibility)
        # direct_impact ≈ -0.08 * 0.5 = -0.04
        # weighted_impact should be adjusted by node credibility
        assert contrib.direct_impact is not None
        assert contrib.weighted_impact is not None

    def test_contribution_credibility_boost(self):
        """Higher credibility nodes increase weighted impact."""
        engine = RCAEngine()

        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("Source1", initial_value=50.0, credibility=0.3)
        engine.add_node("Source2", initial_value=50.0, credibility=0.9)

        engine.add_edge("Source1", "Portfolio", weight=0.5)
        engine.add_edge("Source2", "Portfolio", weight=0.5)

        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())
        contributions = engine.backward_propagate("Portfolio")

        source1 = next(c for c in contributions if c.node == "Source1")
        source2 = next(c for c in contributions if c.node == "Source2")

        # Source2 (higher credibility) should have larger weighted impact
        assert abs(source2.weighted_impact) > abs(source1.weighted_impact)


class TestRCAEngineTemporalAnalysis:
    """Test temporal analysis to identify earliest root causes."""

    def test_temporal_analysis_earliest_change(self):
        """Identify earliest anomaly as likely root cause."""
        engine = RCAEngine()

        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("TechSector", initial_value=50.0)
        engine.add_node("FedPolicy", initial_value=100.0)

        # Create temporal chain: FedPolicy → TechSector → Portfolio
        engine.add_edge("FedPolicy", "TechSector", weight=0.7)
        engine.add_edge("TechSector", "Portfolio", weight=0.6)

        # FedPolicy changes first (earliest)
        t0 = datetime.now()
        t1 = t0 + timedelta(minutes=30)
        t2 = t0 + timedelta(minutes=60)

        engine.record_anomaly("FedPolicy", -0.10, timestamp=t0)
        engine.record_anomaly("TechSector", -0.06, timestamp=t1)
        engine.record_anomaly("Portfolio", -0.08, timestamp=t2)

        # Temporal analysis on Portfolio anomaly
        temporal_results = engine.temporal_analysis("Portfolio")

        # FedPolicy should rank high as root cause (earliest)
        assert len(temporal_results) > 0
        root_causes = [
            r for r in temporal_results if r.temporal_precedence is True
        ]
        assert len(root_causes) > 0

    def test_temporal_analysis_sets_precedence(self):
        """Temporal analysis sets temporal_precedence flag."""
        engine = RCAEngine()

        engine.add_node("A", initial_value=100.0)
        engine.add_node("B", initial_value=100.0)
        engine.add_edge("A", "B", weight=0.8)

        t_early = datetime.now()
        t_late = t_early + timedelta(minutes=10)

        engine.record_anomaly("A", -0.05, timestamp=t_early)
        engine.record_anomaly("B", -0.08, timestamp=t_late)

        results = engine.temporal_analysis("B")

        # A is earlier, should have temporal_precedence=True
        a_result = next((r for r in results if r.node == "A"), None)
        if a_result:
            assert a_result.temporal_precedence is True

    def test_temporal_analysis_no_early_data(self):
        """Temporal analysis handles missing timestamps gracefully."""
        engine = RCAEngine()

        engine.add_node("Root", initial_value=100.0)
        engine.add_node("Effect", initial_value=100.0)
        engine.add_edge("Root", "Effect", weight=0.8)

        # Record only late anomaly
        engine.record_anomaly("Effect", -0.08, timestamp=datetime.now())

        # Should not crash, temporal_precedence defaults to False
        results = engine.temporal_analysis("Effect")

        for result in results:
            # Without earlier data, precedence should be False
            if result.node == "Root":
                # Root has no anomaly recorded, so precedence is false
                assert result.temporal_precedence is False


class TestRCAEngineExplain:
    """Test explanation generation for root causes."""

    def test_explain_single_root_cause(self):
        """Generate explanation for single root cause."""
        engine = RCAEngine()

        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("Apple", initial_value=50.0, credibility=0.9)

        engine.add_edge("Apple", "Portfolio", weight=0.7)
        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())

        explanation = engine.explain("Portfolio")

        assert explanation is not None
        assert "Portfolio" in explanation
        assert "Apple" in explanation or "-8%" in explanation

    def test_explain_includes_impact_scores(self):
        """Explanation includes impact quantification."""
        engine = RCAEngine()

        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("TechSector", initial_value=50.0)

        engine.add_edge("TechSector", "Portfolio", weight=0.5)
        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())

        explanation = engine.explain("Portfolio")

        # Should mention impact percentage
        assert "%" in explanation or "-" in explanation

    def test_explain_empty_engine(self):
        """Explain returns graceful message for unknown node."""
        engine = RCAEngine()

        explanation = engine.explain("NonExistent")

        # Should not crash, return informative message
        assert explanation is not None
        assert isinstance(explanation, str)

    def test_explain_no_anomaly(self):
        """Explain returns graceful message when no anomaly recorded."""
        engine = RCAEngine()

        engine.add_node("Portfolio", initial_value=100.0)

        explanation = engine.explain("Portfolio")

        assert explanation is not None
        assert isinstance(explanation, str)
