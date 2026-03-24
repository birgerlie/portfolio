"""Decision engine — free energy as the priority queue.

Every belief has a goal. Free energy = how far reality is from that goal.
The decision is: fix the biggest gaps first.

energy_field() → ranked list of what needs attention
  → instrument with high FE from neutral goal → position opportunity
  → instrument with high FE from exhaustion goal → exit signal
  → portfolio with high FE from drawdown goal → reduce all
  → strategy with high FE from performing goal → switch strategy

No separate signal function, no Kelly formula, no regime detector.
Free energy IS the signal. The goal gap IS the sizing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class EnergyGap:
    """One belief that's far from its goal."""
    symbol: str
    belief_name: str
    current: float
    goal: float
    free_energy: float
    velocity: float
    phase: str
    direction: str        # "above_goal" or "below_goal"
    action: str           # what to do about it


@dataclass
class SystemState:
    temperature: float = 0.0
    entropy: float = 0.0
    criticality: float = 0.0
    criticality_tier: str = "normal"


@dataclass
class Decision:
    """Portfolio decision driven by energy gaps."""
    gaps: List[EnergyGap]           # ranked by free energy (biggest first)
    system: SystemState
    temperature_scalar: float = 1.0
    warmup: bool = False

    @property
    def top_action(self) -> Optional[EnergyGap]:
        return self.gaps[0] if self.gaps else None

    @property
    def longs(self) -> List[EnergyGap]:
        return [g for g in self.gaps if g.action in ("buy", "add")]

    @property
    def shorts(self) -> List[EnergyGap]:
        return [g for g in self.gaps if g.action in ("sell", "reduce", "exit")]


# ── Native handle resolution ────────────────────────────────────────────────

def _get_native(engine: Any) -> Any:
    """Get the low-level handle that has thermo methods."""
    if hasattr(engine, "init_thermo"):
        return engine
    if hasattr(engine, "_db") and hasattr(engine._db, "init_thermo"):
        return engine._db
    return None


# ── Core: read energy landscape ──────────────────────────────────────────────

# Belief goals — what "normal" or "good" looks like.
# These match the goals defined in entities.py.
BELIEF_GOALS = {
    "price_trend_fast": 0.5,      # neutral
    "price_trend_slow": 0.5,      # neutral
    "spread_tight": 0.8,          # liquid
    "volume_normal": 0.6,         # normal
    "relative_strength": 0.5,     # average
    "exhaustion": 0.2,            # fresh
    "pressure": 0.5,              # no pressure
    "retail_sentiment": 0.5,      # balanced
    "crowded": 0.2,               # uncrowded
    "entry_ready": 0.7,           # we want this high
    "exit_ready": 0.2,            # we want this low
}

# What action resolves each gap
GAP_ACTIONS = {
    # Price trending above goal (bullish) → buy opportunity
    ("price_trend_fast", "above_goal"): "buy",
    ("price_trend_slow", "above_goal"): "buy",
    # Price trending below goal (bearish) → sell signal
    ("price_trend_fast", "below_goal"): "sell",
    ("price_trend_slow", "below_goal"): "sell",
    # Exhaustion above goal → exit (move overdone)
    ("exhaustion", "above_goal"): "exit",
    # Crowded above goal → reduce (too many in the trade)
    ("crowded", "above_goal"): "reduce",
    # Pressure above goal → hedge or reduce
    ("pressure", "above_goal"): "reduce",
    # Relative strength above goal → add (outperforming)
    ("relative_strength", "above_goal"): "add",
    # Relative strength below goal → reduce (underperforming)
    ("relative_strength", "below_goal"): "reduce",
    # Entry ready above goal → buy
    ("entry_ready", "above_goal"): "buy",
    # Exit ready above goal → exit
    ("exit_ready", "above_goal"): "exit",
}


def read_system_state(engine: Any) -> SystemState:
    """Read system-level thermo."""
    state = SystemState()
    native = _get_native(engine) or engine
    try:
        native.run_thermo_pass()
    except Exception:
        pass
    try:
        thermo = native.thermo_state()
        if thermo:
            if isinstance(thermo, dict):
                state.temperature = thermo.get("temperature", 0.0)
                state.entropy = thermo.get("entropy_production", 0.0)
                state.criticality = thermo.get("criticality", 0.0)
                state.criticality_tier = thermo.get("criticality_tier", "normal")
            else:
                state.temperature = getattr(thermo, "temperature", 0.0)
                state.entropy = getattr(thermo, "entropy_production", 0.0)
                state.criticality = getattr(thermo, "criticality", 0.0)
                tier = getattr(thermo, "criticality_tier", None)
                state.criticality_tier = tier.value if hasattr(tier, "value") else str(tier or "normal")
    except Exception:
        pass
    return state


def compute_energy_gaps(
    engine: Any,
    symbols: List[str],
    doc_ids: Dict[str, int] = None,
    cost_per_symbol: Dict[str, float] = None,
    min_free_energy: float = 0.05,
) -> List[EnergyGap]:
    """Compute free energy gap for every belief on every instrument.

    Free energy = |current - goal|. Simple, interpretable, no KL divergence
    needed at this level — the engine computes true KL on the Metal GPU,
    but for the decision we just need the gap magnitude and direction.
    """
    doc_ids = doc_ids or {}
    cost_per_symbol = cost_per_symbol or {}
    native = _get_native(engine)

    gaps = []

    for symbol in symbols:
        ext_id = f"instrument:{symbol}"
        did = doc_ids.get(symbol, -1)

        # Read per-node thermo
        node_fe = 0.0
        node_vel = 0.0
        node_phase = "stable"
        if native and did >= 0:
            try:
                nt = native.node_thermo(did)
                if nt:
                    if isinstance(nt, dict):
                        node_fe = nt.get("free_energy", 0.0)
                        node_vel = nt.get("velocity", 0.0)
                        node_phase = nt.get("phase_state", "stable")
                    else:
                        node_fe = getattr(nt, "free_energy", 0.0)
                        node_vel = getattr(nt, "velocity", 0.0)
                        phase = getattr(nt, "phase_state", None)
                        node_phase = phase.value if hasattr(phase, "value") else str(phase or "stable")
            except Exception:
                pass

        # Read each belief and compute gap from goal
        for belief_name, goal in BELIEF_GOALS.items():
            try:
                current = engine.belief(f"{ext_id}:{belief_name}")
            except Exception:
                continue

            gap = current - goal
            fe = abs(gap)

            if fe < min_free_energy:
                continue  # too close to goal — no action needed

            direction = "above_goal" if gap > 0 else "below_goal"
            action = GAP_ACTIONS.get((belief_name, direction), "watch")

            # Skip "watch" actions — nothing to do
            if action == "watch":
                continue

            # Cost filter: for buy/sell/add, check if the gap exceeds costs
            if action in ("buy", "sell", "add"):
                cost_bps = cost_per_symbol.get(symbol, 10)
                if fe < cost_bps / 10000 * 2:  # gap must exceed 2x costs
                    continue

            gaps.append(EnergyGap(
                symbol=symbol,
                belief_name=belief_name,
                current=round(current, 4),
                goal=goal,
                free_energy=round(fe + node_fe * 0.1, 4),  # boost by engine's FE
                velocity=round(node_vel, 4),
                phase=node_phase,
                direction=direction,
                action=action,
            ))

    # Sort by free energy descending — biggest gap first
    gaps.sort(key=lambda g: g.free_energy, reverse=True)
    return gaps


def generate_decision(
    engine: Any,
    symbols: List[str],
    doc_ids: Dict[str, int] = None,
    cost_per_symbol: Dict[str, float] = None,
    **kwargs,
) -> Decision:
    """Generate a portfolio decision from the energy landscape.

    One call. Reads system thermo + per-instrument belief gaps.
    Returns ranked list of what to do, biggest gap first.
    """
    system = read_system_state(engine)

    # Temperature scaling
    if system.temperature > 0.7:
        temperature_scalar = 0.3
    elif system.temperature > 0.4:
        temperature_scalar = 0.6
    else:
        temperature_scalar = 1.0

    # Warmup detection
    warmup = system.entropy > 10.0

    # Compute all energy gaps
    gaps = compute_energy_gaps(
        engine=engine,
        symbols=symbols,
        doc_ids=doc_ids,
        cost_per_symbol=cost_per_symbol,
    )

    return Decision(
        gaps=gaps,
        system=system,
        temperature_scalar=temperature_scalar,
        warmup=warmup,
    )


def format_decision(d: Decision) -> str:
    """Human-readable decision."""
    lines = []
    lines.append(
        f"System: temp={d.system.temperature:.3f} entropy={d.system.entropy:.3f} "
        f"crit={d.system.criticality:.3f} ({d.system.criticality_tier})"
    )
    lines.append(f"Scaling: temp={d.temperature_scalar:.0%} warmup={d.warmup}")

    if not d.gaps:
        lines.append("  No energy gaps above threshold — all beliefs near goals")
        return "\n".join(lines)

    # Group by action type
    buys = [g for g in d.gaps if g.action in ("buy", "add")]
    sells = [g for g in d.gaps if g.action in ("sell", "reduce", "exit")]

    for g in d.gaps[:10]:  # top 10 gaps
        arrow = "▲" if g.action in ("buy", "add") else "▼" if g.action in ("sell", "reduce", "exit") else "—"
        phase_str = f" [{g.phase}]" if g.phase != "stable" else ""
        hot = "🔥" if g.free_energy > 0.2 else ""
        lines.append(
            f"  {arrow} {g.symbol:>8} {g.action:>6} "
            f"FE={g.free_energy:.3f} {g.belief_name}={g.current:.3f} (goal={g.goal}) "
            f"v={g.velocity:+.3f}{phase_str} {hot}"
        )

    lines.append(f"  Total: {len(buys)} buy/add, {len(sells)} sell/reduce/exit, {len(d.gaps)} total gaps")
    return "\n".join(lines)
