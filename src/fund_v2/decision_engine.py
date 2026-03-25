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
    size: float = 0.0     # position size (0.0 - max_position)
    hedged_by: str = ""   # if part of a pair trade


@dataclass
class SystemState:
    temperature: float = 0.0
    entropy: float = 0.0
    criticality: float = 0.0
    criticality_tier: str = "normal"


@dataclass
class Decision:
    """Portfolio decision driven by energy gaps."""
    gaps: List[EnergyGap]           # one per symbol (deduped, sized)
    all_gaps: List[EnergyGap] = field(default_factory=list)  # all gaps for logging
    system: SystemState = field(default_factory=SystemState)
    temperature_scalar: float = 1.0
    warmup: bool = False
    sector_exposure: Dict[str, float] = field(default_factory=dict)
    directional_crowding: float = 0.0  # 0=balanced, 1=all same direction
    crowd_scalar: float = 1.0          # reduction factor from crowding

    @property
    def top_action(self) -> Optional[EnergyGap]:
        return self.gaps[0] if self.gaps else None

    @property
    def longs(self) -> List[EnergyGap]:
        return [g for g in self.gaps if g.action in ("buy", "add") and g.size > 0]

    @property
    def shorts(self) -> List[EnergyGap]:
        return [g for g in self.gaps if g.action in ("sell", "reduce", "exit") and g.size > 0]


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


# State tracking across cycles
_prev_fe: Dict[str, Dict[str, float]] = {}     # symbol → {belief_name: prev_fe}
_prev_beliefs: Dict[str, Dict[str, float]] = {} # symbol → {belief_name: prev_value}
_prev_actions: Dict[str, dict] = {}              # symbol → {action, count}


def compute_energy_gaps(
    engine: Any,
    symbols: List[str],
    doc_ids: Dict[str, int] = None,
    cost_per_symbol: Dict[str, float] = None,
    min_free_energy: float = 0.05,
) -> List[EnergyGap]:
    """Compute free energy gap for every belief on every instrument.

    Includes reversal detection: when free energy was high and is now
    falling (gap shrinking), that's a mean-reversion signal → buy.
    """
    global _prev_fe
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

        prev_symbol_fe = _prev_fe.get(symbol, {})
        prev_symbol_beliefs = _prev_beliefs.get(symbol, {})
        curr_symbol_fe = {}
        curr_symbol_beliefs = {}

        for belief_name, goal in BELIEF_GOALS.items():
            try:
                current = engine.belief(f"{ext_id}:{belief_name}")
            except Exception:
                continue

            curr_symbol_beliefs[belief_name] = current
            gap = current - goal
            fe = abs(gap)
            curr_symbol_fe[belief_name] = fe

            # Belief momentum: is the belief moving toward or away from goal?
            prev_belief = prev_symbol_beliefs.get(belief_name)
            if prev_belief is not None:
                prev_gap = abs(prev_belief - goal)
                belief_improving = fe < prev_gap  # gap shrinking = improving
                # Boost FE for worsening beliefs (urgent), reduce for improving (less urgent)
                if not belief_improving and fe > 0.1:
                    fe *= 1.2  # worsening → more urgent
                elif belief_improving and fe > 0.1:
                    fe *= 0.8  # improving → less urgent

            if fe < min_free_energy:
                # Reversal detection: FE was high, now shrinking back toward goal
                prev = prev_symbol_fe.get(belief_name, 0)
                if prev > 0.10 and fe < prev * 0.8:  # FE dropped 20%+ from previous
                    reversal_action = "buy" if gap < 0 else "sell"
                    reversal_fe = prev - fe + node_fe * 0.1
                    if reversal_fe > min_free_energy:
                        gaps.append(EnergyGap(
                            symbol=symbol,
                            belief_name=belief_name,
                            current=round(current, 4),
                            goal=goal,
                            free_energy=round(reversal_fe, 4),
                            velocity=round(node_vel, 4),
                            phase=node_phase,
                            direction="reversal",
                            action=reversal_action,
                        ))
                continue

            # Also detect reversals ABOVE min_free_energy when FE is dropping fast
            prev = prev_symbol_fe.get(belief_name, 0)
            if prev > fe * 1.15 and prev > 0.15:  # FE shrinking while still above threshold
                reversal_action = "buy" if gap < 0 else "sell"
                gaps.append(EnergyGap(
                    symbol=symbol,
                    belief_name=belief_name,
                    current=round(current, 4),
                    goal=goal,
                    free_energy=round((prev - fe) * 0.5, 4),  # half the delta as reversal strength
                    velocity=round(node_vel, 4),
                    phase=node_phase,
                    direction="reversal",
                    action=reversal_action,
                ))

            direction = "above_goal" if gap > 0 else "below_goal"
            action = GAP_ACTIONS.get((belief_name, direction), "watch")

            if action == "watch":
                continue

            # Cost filter
            if action in ("buy", "sell", "add"):
                cost_bps = cost_per_symbol.get(symbol, 10)
                if fe < cost_bps / 10000 * 2:
                    continue

            gaps.append(EnergyGap(
                symbol=symbol,
                belief_name=belief_name,
                current=round(current, 4),
                goal=goal,
                free_energy=round(fe + node_fe * 0.1, 4),
                velocity=round(node_vel, 4),
                phase=node_phase,
                direction=direction,
                action=action,
            ))

        _prev_fe[symbol] = curr_symbol_fe
        _prev_beliefs[symbol] = curr_symbol_beliefs

    # ── Accumulator-based signals (fast timing layer) ──────────────
    _add_accumulator_signals(engine, symbols, gaps, doc_ids or {})

    gaps.sort(key=lambda g: g.free_energy, reverse=True)
    return gaps


def _add_accumulator_signals(
    engine: Any,
    symbols: List[str],
    gaps: List[EnergyGap],
    doc_ids: Dict[str, int],
):
    """Read directional pressure accumulators and generate timing signals.

    Accumulators respond in seconds (not minutes like beliefs).
    Cross-speed divergence = the alpha:
      buy_fast > sell_fast BUT buy_slow < sell_slow → fade the bounce (sell)
      sell_fast > buy_fast BUT buy_slow > sell_slow → buy the dip
    """
    native = _get_native(engine)

    for symbol in symbols:
        did = doc_ids.get(symbol, -1)

        # Read accumulator temperatures
        buy_fast = buy_slow = sell_fast = sell_slow = 0.0
        try:
            if hasattr(engine, "accumulator_temperature"):
                bf = engine.accumulator_temperature("Instrument.buy_pressure_fast", symbol)
                sf = engine.accumulator_temperature("Instrument.sell_pressure_fast", symbol)
                bs = engine.accumulator_temperature("Instrument.buy_pressure_slow", symbol)
                ss = engine.accumulator_temperature("Instrument.sell_pressure_slow", symbol)
                buy_fast = bf.get("temperature", 0) if isinstance(bf, dict) and bf else 0
                sell_fast = sf.get("temperature", 0) if isinstance(sf, dict) and sf else 0
                buy_slow = bs.get("temperature", 0) if isinstance(bs, dict) and bs else 0
                sell_slow = ss.get("temperature", 0) if isinstance(ss, dict) and ss else 0
        except Exception:
            continue

        total_fast = buy_fast + sell_fast
        total_slow = buy_slow + sell_slow

        if total_fast < 0.01 and total_slow < 0.01:
            continue  # no pressure data yet

        # Compute ratios (0=all sell, 0.5=balanced, 1=all buy)
        ratio_fast = buy_fast / total_fast if total_fast > 0.01 else 0.5
        ratio_slow = buy_slow / total_slow if total_slow > 0.01 else 0.5

        # Read node thermo for velocity/phase
        node_vel = 0.0
        node_phase = "stable"
        if native and did >= 0:
            try:
                nt = native.node_thermo(did)
                if nt:
                    node_vel = getattr(nt, "velocity", 0) if not isinstance(nt, dict) else nt.get("velocity", 0)
                    phase = getattr(nt, "phase_state", "stable") if not isinstance(nt, dict) else nt.get("phase_state", "stable")
                    node_phase = phase.value if hasattr(phase, "value") else str(phase)
            except Exception:
                pass

        # Cross-speed divergence signals
        # Fast bounce in slow downtrend → fade it (sell)
        if ratio_fast > 0.6 and ratio_slow < 0.4:
            fe = (ratio_fast - 0.5) * (0.5 - ratio_slow) * 2  # divergence strength
            if fe > 0.02:
                gaps.append(EnergyGap(
                    symbol=symbol, belief_name="pressure_divergence",
                    current=round(ratio_fast, 4), goal=round(ratio_slow, 4),
                    free_energy=round(fe, 4), velocity=round(node_vel, 4),
                    phase=node_phase, direction="fade_bounce", action="sell",
                ))

        # Fast dip in slow uptrend → buy the dip
        elif ratio_fast < 0.4 and ratio_slow > 0.6:
            fe = (0.5 - ratio_fast) * (ratio_slow - 0.5) * 2
            if fe > 0.02:
                gaps.append(EnergyGap(
                    symbol=symbol, belief_name="pressure_divergence",
                    current=round(ratio_fast, 4), goal=round(ratio_slow, 4),
                    free_energy=round(fe, 4), velocity=round(node_vel, 4),
                    phase=node_phase, direction="buy_dip", action="buy",
                ))

        # Strong agreement: both fast and slow same direction
        elif ratio_fast > 0.65 and ratio_slow > 0.6:
            fe = (ratio_fast - 0.5) * (ratio_slow - 0.5) * 2
            if fe > 0.02:
                gaps.append(EnergyGap(
                    symbol=symbol, belief_name="pressure_agreement",
                    current=round(ratio_fast, 4), goal=0.5,
                    free_energy=round(fe, 4), velocity=round(node_vel, 4),
                    phase=node_phase, direction="momentum_buy", action="buy",
                ))

        elif ratio_fast < 0.35 and ratio_slow < 0.4:
            fe = (0.5 - ratio_fast) * (0.5 - ratio_slow) * 2
            if fe > 0.02:
                gaps.append(EnergyGap(
                    symbol=symbol, belief_name="pressure_agreement",
                    current=round(ratio_fast, 4), goal=0.5,
                    free_energy=round(fe, 4), velocity=round(node_vel, 4),
                    phase=node_phase, direction="momentum_sell", action="sell",
                ))


# ── Graph correlation structure ──────────────────────────────────────────────

# Sector membership (must match ontology in run_crypto_coinbase.py)
SYMBOL_SECTORS = {
    "BTCUSD": "layer1", "ETHUSD": "layer1",
    "SOLUSD": "l1_alt", "AVAXUSD": "l1_alt", "ADAUSD": "l1_alt",
    "DOTUSD": "l1_alt", "NEARUSD": "l1_alt", "SUIUSD": "l1_alt",
    "APTUSD": "l1_alt", "SEIUSD": "l1_alt", "INJUSD": "l1_alt", "TIAUSD": "l1_alt",
    "ARBUSD": "layer2", "OPUSD": "layer2", "MATICUSD": "layer2",
    "AAVEUSD": "defi", "UNIUSD": "defi", "CRVUSD": "defi", "LDOUSD": "defi",
    "LINKUSD": "infra", "GRTUSD": "infra", "FILUSD": "infra",
    "FETUSD": "ai_compute",
    "DOGEUSD": "meme", "SHIBUSD": "meme", "PEPEUSD": "meme", "BONKUSD": "meme",
    "XRPUSD": "payments", "ATOMUSD": "interop",
}

# Competition edges (from ontology)
COMPETITORS = {
    "SOLUSD": [("ETHUSD", 0.8), ("AVAXUSD", 0.7)],
    "AVAXUSD": [("SOLUSD", 0.7)],
    "SUIUSD": [("SOLUSD", 0.6), ("APTUSD", 0.8)],
    "APTUSD": [("SUIUSD", 0.8)],
    "ARBUSD": [("OPUSD", 0.9)],
    "OPUSD": [("ARBUSD", 0.9)],
    "MATICUSD": [("ARBUSD", 0.7)],
    "UNIUSD": [("CRVUSD", 0.6)],
    "DOGEUSD": [("SHIBUSD", 0.8)],
    "PEPEUSD": [("BONKUSD", 0.7)],
    "FETUSD": [("RNDRUSD", 0.7)],
}


def _compute_sizes(
    gaps: List[EnergyGap],
    temperature_scalar: float,
    max_position: float = 0.15,
    max_sector_exposure: float = 0.40,
    **kwargs,
) -> tuple[List[EnergyGap], Dict[str, float]]:
    """Size positions from free energy, adjusted for correlation and sector limits.

    Size = FE × scale × temperature_scalar, then:
    1. Reduce if same sector already has exposure (concentration penalty)
    2. Boost if position hedges an existing one (competitor pair)
    3. Cap at max_position per instrument, max_sector_exposure per sector
    4. (#2) Boost size when velocity confirms direction (momentum alignment)
    5. (#3) Reduce size when action hasn't changed since last cycle (stale signal)
    """
    global _prev_actions

    # Deduplicate: take the highest FE gap per symbol (one action per instrument)
    best_per_symbol: Dict[str, EnergyGap] = {}
    for g in gaps:
        if g.symbol not in best_per_symbol or g.free_energy > best_per_symbol[g.symbol].free_energy:
            best_per_symbol[g.symbol] = g

    # Track sector exposure
    sector_exposure: Dict[str, float] = {}
    # Track positions for hedge detection
    positioned: Dict[str, str] = {}  # symbol → action (buy/sell)

    sized_gaps = []

    for g in sorted(best_per_symbol.values(), key=lambda x: x.free_energy, reverse=True):
        sector = SYMBOL_SECTORS.get(g.symbol, "unknown")

        # Base size: FE scaled to position range
        # FE 0.1 → 2% position, FE 0.5 → 10%, FE 1.0 → 15%
        raw_size = min(max_position, g.free_energy * 0.15)

        # Temperature scaling (reduce in volatile markets)
        size = raw_size * temperature_scalar

        # Sector concentration penalty
        current_sector_exp = sector_exposure.get(sector, 0)
        remaining_sector = max(0, max_sector_exposure - current_sector_exp)
        if size > remaining_sector:
            size = remaining_sector  # cap at sector limit

        # Hedge detection: if a competitor has opposite action, boost both
        competitors = COMPETITORS.get(g.symbol, [])
        hedge_sym = ""
        for comp_sym, corr in competitors:
            if comp_sym in positioned:
                comp_action = positioned[comp_sym]
                # Opposite actions on correlated instruments = hedge
                is_hedge = (
                    (g.action in ("buy", "add") and comp_action in ("sell", "reduce", "exit")) or
                    (g.action in ("sell", "reduce", "exit") and comp_action in ("buy", "add"))
                )
                if is_hedge:
                    size = min(max_position, size * (1 + corr * 0.5))  # boost by correlation
                    hedge_sym = comp_sym
                    break
                # Same direction on correlated instruments = concentrated
                elif corr > 0.6:
                    size *= (1 - corr * 0.3)  # reduce by correlation

        # (#2) Velocity alignment boost: if velocity confirms the gap direction, boost
        if g.velocity != 0:
            vel_confirms = (
                (g.action in ("sell", "reduce", "exit") and g.velocity < 0) or
                (g.action in ("buy", "add") and g.velocity > 0)
            )
            if vel_confirms:
                size = min(max_position, size * 1.3)  # 30% boost
            elif abs(g.velocity) > 0.005:
                size *= 0.5  # velocity opposes → reduce 50%

        # Outcome-aware decay: reinforce correct signals, decay incorrect ones
        prev_info = _prev_actions.get(g.symbol, {})
        prev_act = prev_info.get("action")
        prev_count = prev_info.get("count", 0)
        prev_price = prev_info.get("price", 0)
        current_price = kwargs.get("prices", {}).get(g.symbol, 0)

        if prev_act == g.action:
            stale_count = prev_count + 1

            # Check if the signal has been correct since first emitted
            if prev_price > 0 and current_price > 0:
                price_moved_right = (
                    (g.action in ("sell", "reduce", "exit") and current_price < prev_price) or
                    (g.action in ("buy", "add") and current_price > prev_price)
                )
                if price_moved_right:
                    # Signal is correct — reinforce, don't decay
                    size *= min(1.2, 1.0 + stale_count * 0.05)  # slight boost, cap at 20%
                else:
                    # Signal is wrong — decay aggressively
                    size *= 0.6 ** min(stale_count, 5)  # fast decay for wrong signals
            else:
                # No price data — mild decay
                size *= 0.85 ** min(stale_count, 8)
        else:
            stale_count = 0
            prev_price = current_price  # reset price anchor on direction change

        _prev_actions[g.symbol] = {"action": g.action, "count": stale_count, "price": prev_price or current_price}

        if size < 0.005:
            size = 0.0

        g.size = round(size, 4)
        g.hedged_by = hedge_sym

        if size > 0:
            sector_exposure[sector] = current_sector_exp + size
            positioned[g.symbol] = g.action

        sized_gaps.append(g)

    # Also include non-best gaps (for logging) with size=0
    best_symbols = set(best_per_symbol.keys())
    for g in gaps:
        if g.symbol not in best_symbols or g is best_per_symbol[g.symbol]:
            continue
        g.size = 0.0
        sized_gaps.append(g)

    sized_gaps.sort(key=lambda g: g.free_energy, reverse=True)
    return sized_gaps, sector_exposure


def generate_decision(
    engine: Any,
    symbols: List[str],
    doc_ids: Dict[str, int] = None,
    cost_per_symbol: Dict[str, float] = None,
    **kwargs,
) -> Decision:
    """Generate a portfolio decision from the energy landscape.

    Full pipeline:
    1. Read system thermo → temperature scalar
    2. Compute energy gaps per instrument per belief
    3. Size positions from free energy
    4. Adjust for sector correlation (reduce concentrated, boost hedged)
    5. Return ranked, sized decision
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
    all_gaps = compute_energy_gaps(
        engine=engine,
        symbols=symbols,
        doc_ids=doc_ids,
        cost_per_symbol=cost_per_symbol,
    )

    # (#1) Directional crowding detection
    # When >80% of gaps point the same way, it's one market bet, not many independent bets
    if all_gaps:
        buys = sum(1 for g in all_gaps if g.action in ("buy", "add"))
        sells = sum(1 for g in all_gaps if g.action in ("sell", "reduce", "exit"))
        total = buys + sells
        if total > 0:
            dominant = max(buys, sells)
            directional_crowding = dominant / total  # 0.5 = balanced, 1.0 = all same
        else:
            directional_crowding = 0.0

        # Scale down when crowded: 100% same direction → 30% of normal size
        if directional_crowding > 0.8:
            crowd_scalar = 0.3
        elif directional_crowding > 0.6:
            crowd_scalar = 0.6
        else:
            crowd_scalar = 1.0
    else:
        directional_crowding = 0.0
        crowd_scalar = 1.0

    # Size positions with graph correlation + hedging + crowd scalar
    sized_gaps, sector_exposure = _compute_sizes(
        all_gaps, temperature_scalar * crowd_scalar,
        prices=kwargs.get("prices", {}),
    )

    return Decision(
        gaps=sized_gaps,
        all_gaps=all_gaps,
        system=system,
        temperature_scalar=temperature_scalar,
        warmup=warmup,
        sector_exposure=sector_exposure,
        directional_crowding=directional_crowding,
        crowd_scalar=crowd_scalar,
    )


def format_decision(d: Decision) -> str:
    """Human-readable decision."""
    lines = []
    lines.append(
        f"System: temp={d.system.temperature:.3f} entropy={d.system.entropy:.3f} "
        f"crit={d.system.criticality:.3f} ({d.system.criticality_tier})"
    )
    lines.append(f"Scaling: temp={d.temperature_scalar:.0%} crowd={d.crowd_scalar:.0%} dir_crowd={d.directional_crowding:.0%} warmup={d.warmup}")

    if not d.gaps:
        lines.append("  No energy gaps above threshold — all beliefs near goals")
        return "\n".join(lines)

    # Show sized positions (size > 0)
    active = [g for g in d.gaps if g.size > 0]
    passive = [g for g in d.gaps if g.size == 0]

    if active:
        lines.append(f"  ACTIVE ({len(active)} positions):")
        for g in active:
            arrow = "▲" if g.action in ("buy", "add") else "▼"
            phase_str = f" [{g.phase}]" if g.phase != "stable" else ""
            hedge_str = f" hedged:{g.hedged_by}" if g.hedged_by else ""
            hot = "🔥" if g.free_energy > 0.2 else ""
            lines.append(
                f"    {arrow} {g.symbol:>8} {g.action:>6} size={g.size:.1%} "
                f"FE={g.free_energy:.3f} v={g.velocity:+.3f}{phase_str}{hedge_str} {hot}"
            )

    # Sector exposure
    if d.sector_exposure:
        lines.append(f"  Sectors: {' | '.join(f'{s}={v:.1%}' for s, v in sorted(d.sector_exposure.items(), key=lambda x: -x[1]) if v > 0)}")

    lines.append(f"  Total: {len(active)} sized, {len(passive)} unsized, {len(d.gaps)} gaps")
    return "\n".join(lines)
