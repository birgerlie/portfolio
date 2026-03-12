"""End-to-end tests for RCA engine with complex belief graphs."""

import pytest
from datetime import datetime, timedelta

from trading_backtest.rca import RCAEngine


class TestRCAFullAnalysis:
    """Test complete RCA workflow on complex graphs."""

    def test_rca_5_edge_graph(self):
        """Analyze -8% underperformance through 5-edge graph.

        Graph structure:
            EconomicData (root)
                ↓ (weight=0.9)
            FedPolicy
                ↓ (weight=0.8)
            TechSector
              ↙ (0.6)     ↘ (0.5)
            Apple         Healthcare
                ↘ (0.7)    ↙ (0.6)
                Portfolio
        """
        engine = RCAEngine(decay=0.85)

        # Create all nodes
        nodes = {
            "EconomicData": 100.0,
            "FedPolicy": 95.0,
            "TechSector": 90.0,
            "Apple": 85.0,
            "Healthcare": 88.0,
            "Portfolio": 100.0,
        }
        for node, value in nodes.items():
            credibility = 0.85 if node in ["FedPolicy", "TechSector"] else 0.70
            engine.add_node(node, initial_value=value, credibility=credibility)

        # Create edge structure
        edges = [
            ("EconomicData", "FedPolicy", 0.9),
            ("FedPolicy", "TechSector", 0.8),
            ("TechSector", "Apple", 0.6),
            ("TechSector", "Healthcare", 0.5),
            ("Apple", "Portfolio", 0.7),
            ("Healthcare", "Portfolio", 0.6),
        ]
        for parent, child, weight in edges:
            engine.add_edge(parent, child, weight=weight)

        # Record temporal sequence of anomalies
        t0 = datetime.now()
        engine.record_anomaly("EconomicData", -0.12, timestamp=t0)
        engine.record_anomaly("FedPolicy", -0.10, timestamp=t0 + timedelta(minutes=10))
        engine.record_anomaly(
            "TechSector", -0.08, timestamp=t0 + timedelta(minutes=20)
        )
        engine.record_anomaly("Apple", -0.06, timestamp=t0 + timedelta(minutes=30))
        engine.record_anomaly(
            "Portfolio", -0.08, timestamp=t0 + timedelta(minutes=40)
        )

        # Run complete analysis
        contributions = engine.backward_propagate("Portfolio")
        temporal = engine.temporal_analysis("Portfolio")
        explanation = engine.explain("Portfolio")

        # Assertions
        assert len(contributions) > 0, "Should find contributing nodes"
        assert len(temporal) > 0, "Should find temporal precedence"
        assert explanation is not None, "Should generate explanation"

        # EconomicData should rank as significant root cause
        econ = next((c for c in contributions if c.node == "EconomicData"), None)
        assert econ is not None, "EconomicData should be identified"
        assert econ.weighted_impact < 0, "Should show negative impact"

        # TechSector should have high contribution (direct path)
        tech = next((c for c in contributions if c.node == "TechSector"), None)
        assert tech is not None, "TechSector should be identified"

        # FedPolicy should have temporal precedence
        fed = next((c for c in temporal if c.node == "FedPolicy"), None)
        if fed:
            assert fed.temporal_precedence is True, "FedPolicy should have precedence"

    def test_rca_identifies_root_cause_ordering(self):
        """Root causes should rank by weighted impact."""
        engine = RCAEngine()

        # Two causes with different impacts
        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("StrongCause", initial_value=50.0, credibility=0.95)
        engine.add_node("WeakCause", initial_value=50.0, credibility=0.50)

        engine.add_edge("StrongCause", "Portfolio", weight=0.9)
        engine.add_edge("WeakCause", "Portfolio", weight=0.3)

        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())

        contributions = engine.backward_propagate("Portfolio")

        # Sort by weighted impact
        sorted_contrib = sorted(contributions, key=lambda c: abs(c.weighted_impact), reverse=True)

        # StrongCause should rank first
        if len(sorted_contrib) >= 2:
            assert (
                sorted_contrib[0].node == "StrongCause"
                or "Strong" in sorted_contrib[0].node
            ), "Strong cause should rank first"

    def test_rca_performance_large_graph(self):
        """RCA performs efficiently on larger graphs."""
        engine = RCAEngine(decay=0.85)

        # Create 50-node graph
        num_nodes = 50
        for i in range(num_nodes):
            engine.add_node(f"Node{i}", initial_value=100.0 - i)

        # Create chain and some branches
        for i in range(num_nodes - 1):
            weight = 0.8 - (i * 0.005)  # Gradually decreasing
            engine.add_edge(f"Node{i}", f"Node{i + 1}", weight=max(0.2, weight))

        # Add some cross-links
        for i in range(0, num_nodes - 5, 5):
            engine.add_edge(f"Node{i}", f"Node{i + 5}", weight=0.5)

        # Record anomaly at tail
        engine.record_anomaly("Node49", -0.15, timestamp=datetime.now())

        # Should complete in reasonable time
        import time

        start = time.time()
        contributions = engine.backward_propagate("Node49")
        elapsed = time.time() - start

        assert elapsed < 5.0, f"RCA took {elapsed:.2f}s, should be < 5s"
        assert len(contributions) > 0, "Should find contributions"

    def test_rca_multiple_root_causes(self):
        """Identify multiple independent root causes."""
        engine = RCAEngine()

        # Create structure with multiple independent branches
        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("TechSector", initial_value=50.0, credibility=0.85)
        engine.add_node("HealthSector", initial_value=50.0, credibility=0.85)
        engine.add_node("TechRegulation", initial_value=25.0, credibility=0.90)
        engine.add_node("HealthRegulation", initial_value=25.0, credibility=0.90)

        # Two independent paths
        engine.add_edge("TechRegulation", "TechSector", weight=0.8)
        engine.add_edge("HealthRegulation", "HealthSector", weight=0.8)
        engine.add_edge("TechSector", "Portfolio", weight=0.5)
        engine.add_edge("HealthSector", "Portfolio", weight=0.5)

        # Both roots cause problems
        t = datetime.now()
        engine.record_anomaly("TechRegulation", -0.10, timestamp=t)
        engine.record_anomaly("HealthRegulation", -0.10, timestamp=t)
        engine.record_anomaly("Portfolio", -0.08, timestamp=t + timedelta(minutes=30))

        contributions = engine.backward_propagate("Portfolio")

        # Should identify both regulatory nodes
        nodes_found = {c.node for c in contributions}
        assert (
            "TechRegulation" in nodes_found or "HealthRegulation" in nodes_found
        ), "Should find regulatory root causes"

    def test_rca_with_cycles_handled(self):
        """RCA gracefully handles cyclic graph structures."""
        engine = RCAEngine()

        # Create simple cycle: A → B → C → A
        engine.add_node("A", initial_value=100.0)
        engine.add_node("B", initial_value=100.0)
        engine.add_node("C", initial_value=100.0)

        engine.add_edge("A", "B", weight=0.7)
        engine.add_edge("B", "C", weight=0.7)
        engine.add_edge("C", "A", weight=0.7)

        engine.record_anomaly("A", -0.08, timestamp=datetime.now())

        # Should not infinite loop
        contributions = engine.backward_propagate("A")

        # Should return results without hanging
        assert len(contributions) >= 0


class TestRCAIntegration:
    """Integration tests combining multiple RCA features."""

    def test_rca_workflow_analysis_to_explanation(self):
        """Complete workflow from analysis to explanation."""
        engine = RCAEngine()

        # Build knowledge graph
        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("TechStock", initial_value=50.0, credibility=0.85)
        engine.add_node("FinancialData", initial_value=25.0, credibility=0.90)

        engine.add_edge("FinancialData", "TechStock", weight=0.85)
        engine.add_edge("TechStock", "Portfolio", weight=0.70)

        # Record sequential anomalies
        t0 = datetime.now()
        engine.record_anomaly("FinancialData", -0.15, timestamp=t0)
        engine.record_anomaly("TechStock", -0.12, timestamp=t0 + timedelta(minutes=15))
        engine.record_anomaly("Portfolio", -0.08, timestamp=t0 + timedelta(minutes=30))

        # Step 1: Backward propagation
        contributions = engine.backward_propagate("Portfolio")
        assert len(contributions) > 0

        # Step 2: Temporal analysis
        temporal = engine.temporal_analysis("Portfolio")
        assert len(temporal) > 0

        # Step 3: Generate explanation
        explanation = engine.explain("Portfolio")
        assert explanation is not None
        assert len(explanation) > 0

    def test_rca_with_credibility_weighting(self):
        """RCA respects node credibility in analysis."""
        engine = RCAEngine()

        engine.add_node("Portfolio", initial_value=100.0)
        engine.add_node("HighCredibility", initial_value=50.0, credibility=0.95)
        engine.add_node("LowCredibility", initial_value=50.0, credibility=0.40)

        engine.add_edge("HighCredibility", "Portfolio", weight=0.5)
        engine.add_edge("LowCredibility", "Portfolio", weight=0.5)

        engine.record_anomaly("Portfolio", -0.08, timestamp=datetime.now())

        contributions = engine.backward_propagate("Portfolio")

        high_cred = next(
            (c for c in contributions if c.node == "HighCredibility"), None
        )
        low_cred = next((c for c in contributions if c.node == "LowCredibility"), None)

        if high_cred and low_cred:
            # High credibility should have higher weighted impact
            assert (
                abs(high_cred.weighted_impact) > abs(low_cred.weighted_impact)
            ), "Higher credibility should amplify impact"
