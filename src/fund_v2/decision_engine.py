"""Unified decision engine — beliefs + thermodynamics in one pass.

Reads SiliconDB beliefs (what things are) and thermodynamic state (how the
system is behaving) together. No separate layers — one coherent read.

The engine computes: temperature, free energy, velocity, phase state.
We read these alongside beliefs and use them for:
  - Position sizing (temperature scales size)
  - Stock selection (energy hotspots only)
  - Timing (velocity and phase)
  - Risk (criticality gates everything)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class InstrumentState:
    """Complete state of one instrument — beliefs + thermo in one read."""
    symbol: str

    # Beliefs (from belief nodes)
    price_trend_fast: float = 0.5
    price_trend_slow: float = 0.5
    relative_strength: float = 0.5
    exhaustion: float = 0.2
    pressure: float = 0.5
    retail_sentiment: float = 0.5
    crowded: float = 0.3

    # Thermo (from engine.node_thermo)
    free_energy: float = 0.0      # surprise — how far from expected
    velocity: float = 0.0         # rate of belief change
    phase: str = "stable"         # stable / transition_up / transition_down

    # Derived
    is_hotspot: bool = False      # high free energy = something happening


@dataclass
class SystemState:
    """Complete state of the market system — thermo + regime."""
    temperature: float = 0.0      # how fast everything is changing
    entropy: float = 0.0          # rate of disorder creation
    criticality: float = 0.0      # proximity to phase transition
    criticality_tier: str = "normal"  # normal / elevated / critical


@dataclass
class Signal:
    """One trading signal with full context."""
    symbol: str
    direction: str                # long / short / neutral
    conviction: float             # 0-1 how sure
    size: float                   # 0-0.30 position weight
    edge: float                   # expected return after costs

    # Why — what drove this signal
    momentum_component: float = 0.0
    thermo_component: float = 0.0
    exhaustion_component: float = 0.0
    pressure_component: float = 0.0

    # Thermo context
    free_energy: float = 0.0
    velocity: float = 0.0
    phase: str = "stable"


@dataclass
class Decision:
    """Complete portfolio decision."""
    signals: List[Signal]
    system: SystemState
    temperature_scalar: float = 1.0   # position size multiplier from temperature
    criticality_discount: float = 1.0  # risk reduction from criticality
    focus_count: int = 0              # how many instruments are hotspots


def _get_native_handle(engine: Any) -> Any:
    """Get the low-level SiliconDBNative handle that has thermo methods.

    The ORM engine chain: App.engine → SiliconDBNativeEngine → _db (SiliconDBNative)
    Thermo methods live on SiliconDBNative, not on the ORM adapter.
    """
    # Direct native handle
    if hasattr(engine, "init_thermo"):
        return engine
    # ORM NativeEngine wraps _db
    if hasattr(engine, "_db") and hasattr(engine._db, "init_thermo"):
        return engine._db
    # High-level SiliconDB wraps _db
    db = getattr(engine, "_db", None)
    if db and hasattr(db, "init_thermo"):
        return db
    return None


def read_system_state(engine: Any) -> SystemState:
    """Read system-level thermodynamic state."""
    state = SystemState()
    native = _get_native_handle(engine)
    if native is None:
        # Try engine directly (might have thermo_state from mixin)
        native = engine
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


def read_instrument_state(engine: Any, symbol: str, ext_id: str) -> InstrumentState:
    """Read one instrument's beliefs + thermo state in a single pass."""
    state = InstrumentState(symbol=symbol)

    # Read beliefs
    for attr in ["price_trend_fast", "price_trend_slow", "relative_strength",
                 "exhaustion", "pressure", "retail_sentiment", "crowded"]:
        try:
            setattr(state, attr, engine.belief(f"{ext_id}:{attr}"))
        except Exception:
            pass

    # Read thermo — need native handle and internal doc_id
    try:
        native = _get_native_handle(engine) or engine
        if native and hasattr(native, "node_thermo"):
            # node_thermo takes an integer doc_id
            # Try multiple ways to get the internal ID
            doc = engine.get(ext_id)
            doc_id = None
            if isinstance(doc, dict) and doc:
                doc_id = doc.get("doc_id") or doc.get("id") or doc.get("internal_id")
            if doc_id:
                nt = native.node_thermo(int(doc_id))
                if nt:
                    if isinstance(nt, dict):
                        state.free_energy = nt.get("free_energy", 0.0)
                        state.velocity = nt.get("velocity", 0.0)
                        state.phase = nt.get("phase_state", "stable")
                    else:
                        state.free_energy = getattr(nt, "free_energy", 0.0)
                        state.velocity = getattr(nt, "velocity", 0.0)
                        phase = getattr(nt, "phase_state", None)
                        state.phase = phase.value if hasattr(phase, "value") else str(phase or "stable")
    except Exception:
        pass

    # Hotspot: high free energy means this instrument is diverging from expected
    state.is_hotspot = abs(state.free_energy) > 0.1

    return state


def generate_decision(
    engine: Any,
    symbols: List[str],
    macro_proxies: set[str] = None,
    cost_per_symbol: Dict[str, float] = None,
) -> Decision:
    """Generate a complete portfolio decision from beliefs + thermodynamics.

    This is the unified signal function. One pass reads:
    - System thermo (temperature, criticality) → sizing and risk
    - Per-instrument beliefs (momentum, exhaustion, pressure) → direction
    - Per-instrument thermo (free energy, velocity, phase) → timing and selection
    - Costs → net edge

    Returns signals only for instruments worth trading.
    """
    macro_proxies = macro_proxies or set()
    cost_per_symbol = cost_per_symbol or {}

    # ── Run thermo pass before reading state ────────────────────────
    try:
        native = _get_native_handle(engine)
        if native and hasattr(native, 'run_thermo_pass'):
            native.run_thermo_pass()
    except Exception:
        pass

    # ── System state ─────────────────────────────────────────────────
    system = read_system_state(engine)

    # Temperature → position size scaling
    # High temperature = volatile, scale down. Low = calm, full size.
    if system.temperature > 0.7:
        temperature_scalar = 0.3     # crisis mode — 30% of normal size
    elif system.temperature > 0.4:
        temperature_scalar = 0.6     # elevated — 60%
    else:
        temperature_scalar = 1.0     # calm — full size

    # Criticality → risk discount
    # During warmup (entropy > 10 = system still converging from cold start),
    # ignore criticality — it's an artifact of beliefs moving from 0.5 to their
    # initial values, not a real regime shift.
    warmup = system.entropy > 10.0
    if warmup:
        criticality_discount = 1.0   # ignore during warmup
    elif system.criticality > 0.7:
        criticality_discount = 0.5   # about to flip — 50% (was 30%, too aggressive)
    elif system.criticality > 0.4:
        criticality_discount = 0.7   # elevated — 70%
    else:
        criticality_discount = 1.0   # normal — no discount

    # ── Per-instrument state ─────────────────────────────────────────
    instruments = []
    for symbol in symbols:
        if symbol in macro_proxies:
            continue
        ext_id = f"instrument:{symbol}"
        state = read_instrument_state(engine, symbol, ext_id)
        instruments.append(state)

    # ── Energy hotspots — focus on what matters ──────────────────────
    # Also try engine.energy_field for global hotspot ranking
    try:
        hotspots = engine.energy_field(budget=20, namespace="default")
        if hotspots:
            hotspot_ids = {h.get("external_id", h.get("node_id", "")) for h in hotspots}
            for inst in instruments:
                if f"instrument:{inst.symbol}" in hotspot_ids:
                    inst.is_hotspot = True
    except Exception:
        pass  # fall back to per-node free_energy check

    focus_count = sum(1 for i in instruments if i.is_hotspot)

    # ── Score each instrument ────────────────────────────────────────
    signals = []
    for inst in instruments:

        # Momentum: price trend direction
        momentum = (inst.price_trend_fast - 0.5) * 0.4 + (inst.price_trend_slow - 0.5) * 0.3

        # Thermo signal: free energy direction + velocity
        # High free energy + positive velocity = diverging upward = momentum
        # High free energy + negative velocity = diverging downward = bearish
        # Low free energy = expected behavior = no thermo signal
        thermo_signal = inst.free_energy * inst.velocity * 2.0

        # Phase signal
        phase_boost = 0.0
        if inst.phase == "transition_up":
            phase_boost = 0.05    # breakout bonus
        elif inst.phase == "transition_down":
            phase_boost = -0.05   # breakdown penalty

        # Exhaustion: contrarian — high exhaustion suggests reversal
        exhaustion_signal = (0.5 - inst.exhaustion) * 0.2

        # Pressure: graph-propagated macro/sector pressure
        pressure_signal = (inst.pressure - 0.5) * 0.15

        # Crowd: penalty for crowded trades
        crowd_penalty = (inst.crowded - 0.3) * 0.1

        # Raw edge
        edge = momentum + thermo_signal + phase_boost + exhaustion_signal + pressure_signal - crowd_penalty
        edge = max(-1.0, min(1.0, edge))

        # Direction
        if abs(edge) < 0.01:
            direction = "neutral"
        else:
            direction = "long" if edge > 0 else "short"

        # Conviction: how confident across all signals
        # Agreement between momentum, thermo, and pressure strengthens conviction
        signals_agree = (
            (1 if (momentum > 0) == (edge > 0) else 0) +
            (1 if (thermo_signal > 0) == (edge > 0) else 0) +
            (1 if (pressure_signal > 0) == (edge > 0) else 0)
        )
        conviction = min(1.0, abs(edge) * (0.5 + signals_agree * 0.15))

        # Hotspot boost: higher conviction for energy hotspots
        if inst.is_hotspot:
            conviction = min(1.0, conviction * 1.3)

        # Kelly sizing: f = 2p - 1, capped at 30%
        kelly = max(0.0, 2 * conviction - 1)
        raw_size = min(0.30, kelly)

        # Apply system-level scaling
        size = raw_size * temperature_scalar * criticality_discount

        # Subtract costs
        cost_bps = cost_per_symbol.get(inst.symbol, 5)  # default 5 bps
        net_edge = abs(edge) - (cost_bps / 10000)

        # Only signal if net edge positive and conviction meaningful
        if net_edge <= 0 or conviction < 0.1:
            direction = "neutral"
            size = 0.0

        signals.append(Signal(
            symbol=inst.symbol,
            direction=direction,
            conviction=round(conviction, 4),
            size=round(size, 4),
            edge=round(net_edge if direction != "neutral" else 0.0, 4),
            momentum_component=round(momentum, 4),
            thermo_component=round(thermo_signal, 4),
            exhaustion_component=round(exhaustion_signal, 4),
            pressure_component=round(pressure_signal, 4),
            free_energy=round(inst.free_energy, 4),
            velocity=round(inst.velocity, 4),
            phase=inst.phase,
        ))

    # Sort by conviction * size descending (best opportunities first)
    signals.sort(key=lambda s: s.conviction * s.size, reverse=True)

    return Decision(
        signals=signals,
        system=system,
        temperature_scalar=temperature_scalar,
        criticality_discount=criticality_discount,
        focus_count=focus_count,
    )


def format_decision(d: Decision) -> str:
    """Human-readable decision summary."""
    lines = []
    lines.append(f"System: temp={d.system.temperature:.3f} entropy={d.system.entropy:.3f} "
                 f"criticality={d.system.criticality:.3f} ({d.system.criticality_tier})")
    lines.append(f"Scaling: temp={d.temperature_scalar:.0%} crit={d.criticality_discount:.0%} "
                 f"hotspots={d.focus_count}")
    lines.append("")

    for s in d.signals:
        if s.direction == "neutral":
            continue
        arrow = "▲" if s.direction == "long" else "▼"
        hot = "🔥" if s.free_energy > 0.1 else "  "
        phase_str = f" [{s.phase}]" if s.phase != "stable" else ""
        lines.append(
            f"  {arrow} {s.symbol:>8} {s.direction:>5} "
            f"size={s.size:.1%} conv={s.conviction:.0%} edge={s.edge:.4f} "
            f"mom={s.momentum_component:+.3f} thermo={s.thermo_component:+.3f} "
            f"FE={s.free_energy:.3f} v={s.velocity:+.3f}{phase_str} {hot}"
        )

    active = [s for s in d.signals if s.direction != "neutral"]
    if not active:
        lines.append("  No actionable signals")

    return "\n".join(lines)
