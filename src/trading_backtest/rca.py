"""Root Cause Analysis (RCA) engine for belief graphs."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Set, Tuple
from collections import deque, defaultdict


@dataclass
class CauseContribution:
    """Quantified contribution of a cause to an anomaly."""

    node: str
    direct_impact: float
    weighted_impact: float
    credibility: float = 0.0
    temporal_precedence: bool = False


class RCAEngine:
    """Backward propagate through belief graphs to identify root causes."""

    def __init__(self, decay: float = 0.85):
        """Initialize RCA engine.

        Args:
            decay: Impact decay per hop in graph (0.0-1.0)
        """
        self.decay = decay
        self._nodes: Dict[str, Dict[str, float]] = {}
        self._edges: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        self._anomalies: Dict[str, Tuple[float, datetime]] = {}

    def add_node(
        self,
        node_id: str,
        initial_value: float = 100.0,
        credibility: float = 0.70,
    ) -> None:
        """Add a node to the belief graph.

        Args:
            node_id: Unique node identifier
            initial_value: Initial value for scaling
            credibility: Node credibility (0.0-1.0)
        """
        self._nodes[node_id] = {
            "initial_value": initial_value,
            "credibility": credibility,
        }

    def add_edge(self, parent: str, child: str, weight: float) -> None:
        """Add directed edge parent → child with impact weight.

        Args:
            parent: Parent node (cause)
            child: Child node (effect)
            weight: Edge weight (impact magnitude, 0.0-1.0)
        """
        self._edges[parent].append((child, weight))

    def record_anomaly(
        self, node_id: str, magnitude: float, timestamp: datetime
    ) -> None:
        """Record anomaly at a node.

        Args:
            node_id: Node with anomaly
            magnitude: Anomaly magnitude (e.g., -0.08 for -8%)
            timestamp: When anomaly occurred
        """
        self._anomalies[node_id] = (magnitude, timestamp)

    def backward_propagate(self, anomaly_node: str) -> List[CauseContribution]:
        """Trace backward from anomaly to find root causes.

        Uses BFS with exponential decay per hop.

        Args:
            anomaly_node: Node with recorded anomaly

        Returns:
            List of CauseContribution sorted by weighted impact
        """
        if anomaly_node not in self._anomalies:
            return []

        magnitude, _ = self._anomalies[anomaly_node]
        contributions = self._bfs_backward(anomaly_node, magnitude)

        dedup = self._deduplicate_contributions(contributions)
        return self._sort_by_impact(dedup)

    def _bfs_backward(
        self, start_node: str, initial_magnitude: float
    ) -> List[CauseContribution]:
        """BFS backward from start_node to find causes.

        Args:
            start_node: Node to start from
            initial_magnitude: Initial anomaly magnitude

        Returns:
            List of CauseContribution
        """
        contributions = []
        visited: Set[str] = set()
        queue = deque(
            [(start_node, initial_magnitude, 0)]  # (node, impact, hops)
        )

        while queue:
            current, impact, hops = queue.popleft()

            if current in visited:
                continue
            visited.add(current)

            parents = self._find_parents(current)
            for parent, edge_weight in parents:
                contrib = self._create_contribution(
                    parent, impact, edge_weight, hops
                )
                contributions.append(contrib)

                if abs(contrib.direct_impact) > 0.001:
                    queue.append((parent, contrib.direct_impact, hops + 1))

        return contributions

    def _find_parents(self, node: str) -> List[Tuple[str, float]]:
        """Find all parents of a node.

        Args:
            node: Child node

        Returns:
            List of (parent_id, edge_weight) tuples
        """
        parents = []
        for parent, children in self._edges.items():
            for child, weight in children:
                if child == node:
                    parents.append((parent, weight))
        return parents

    def _create_contribution(
        self, parent: str, impact: float, edge_weight: float, hops: int
    ) -> CauseContribution:
        """Create contribution with decay and credibility."""
        new_impact = impact * edge_weight * (self.decay ** hops)
        cred = self._nodes.get(parent, {}).get("credibility", 0.70)
        return CauseContribution(
            node=parent,
            direct_impact=new_impact,
            weighted_impact=new_impact * cred,
            credibility=cred,
            temporal_precedence=False,
        )

    def _deduplicate_contributions(
        self, contributions: List[CauseContribution]
    ) -> Dict[str, CauseContribution]:
        """Keep highest impact contribution per node."""
        dedup = {}
        for contrib in contributions:
            key = contrib.node
            if key not in dedup or abs(contrib.weighted_impact) > abs(
                dedup[key].weighted_impact
            ):
                dedup[key] = contrib
        return dedup

    def _sort_by_impact(
        self, contrib_dict: Dict[str, CauseContribution]
    ) -> List[CauseContribution]:
        """Sort contributions by weighted impact magnitude."""
        return sorted(
            contrib_dict.values(),
            key=lambda c: abs(c.weighted_impact),
            reverse=True,
        )

    def temporal_analysis(
        self, anomaly_node: str
    ) -> List[CauseContribution]:
        """Identify root causes using temporal precedence.

        Earlier anomalies are likely root causes.

        Args:
            anomaly_node: Node to analyze

        Returns:
            List of CauseContribution with temporal_precedence set
        """
        if anomaly_node not in self._anomalies:
            return []

        contributions = self.backward_propagate(anomaly_node)
        anomaly_time = self._anomalies[anomaly_node][1]

        # Mark temporal precedence
        temporal = []
        for contrib in contributions:
            precedence = False
            if contrib.node in self._anomalies:
                parent_time = self._anomalies[contrib.node][1]
                # Parent is root cause if anomaly occurred earlier
                precedence = parent_time < anomaly_time

            temporal.append(
                CauseContribution(
                    node=contrib.node,
                    direct_impact=contrib.direct_impact,
                    weighted_impact=contrib.weighted_impact,
                    credibility=contrib.credibility,
                    temporal_precedence=precedence,
                )
            )

        return temporal

    def explain(self, anomaly_node: str) -> str:
        """Generate natural language explanation of root causes.

        Args:
            anomaly_node: Node with anomaly

        Returns:
            Natural language explanation string
        """
        if anomaly_node not in self._nodes:
            return f"Node '{anomaly_node}' not found in graph."

        if anomaly_node not in self._anomalies:
            return f"No anomaly recorded for '{anomaly_node}'."

        magnitude, timestamp = self._anomalies[anomaly_node]
        contributions = self.temporal_analysis(anomaly_node)

        if not contributions:
            return self._explain_no_causes(anomaly_node, magnitude, timestamp)

        return self._format_explanation(anomaly_node, magnitude, contributions)

    def _explain_no_causes(
        self, node: str, magnitude: float, timestamp: datetime
    ) -> str:
        """Explain when no root causes found."""
        return (
            f"Detected {magnitude:.1%} change at '{node}' "
            f"at {timestamp.isoformat()}, but no upstream root causes found."
        )

    def _format_explanation(
        self,
        anomaly_node: str,
        magnitude: float,
        contributions: List[CauseContribution],
    ) -> str:
        """Format explanation with top root causes."""
        lines = [f"RCA for '{anomaly_node}': {magnitude:.1%} impact"]
        for i, c in enumerate(contributions[:3], 1):
            src = "upstream" if c.temporal_precedence else "potential"
            lines.append(
                f"  {i}. {c.node}: {c.weighted_impact*100:.2f}% ({src}, "
                f"{c.credibility:.0%})"
            )
        return "\n".join(lines)
