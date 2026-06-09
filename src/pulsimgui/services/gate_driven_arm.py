"""Gate-driven (externally-commanded) behavioural MMC/M3C arm.

The L0-L3 pulsim arms take a *modulation index* ``m_ref`` and decide internally
which submodules to insert (and, at L3, run their own sort-and-select capacitor
balancing). This module is the opposite paradigm — the one used in HIL /
Simulink workflows where **the controller is fully external and the model only
represents the circuit**:

* the user supplies, per arm and per step, the **per-submodule insertion / gate
  signal** ``s = [s_0 … s_{N-1}]`` (the output of *their* modulation +
  balancing + sort-and-select, computed outside);
* the arm just integrates each submodule capacitor and sums the inserted
  voltages — **no internal balancing, no internal PWM**.

It is built entirely on pulsim's public behavioural-source mechanism (one
controlled voltage source per arm, advanced by a ``(step_observer, b_extra_fn)``
pair — the same machinery the native L0-L3 arms use), so it keeps the L0-sized
MNA matrix and runs at behavioural speed (no gate-level MNA switches).

Per-submodule capacitor dynamics (forward Euler), matching the L3 kernel
(``dv_C_n/dt = (s_n·i_b − v_C_n/r_p)/C``):

    v_C_n ← v_C_n + (s_n·i_b − v_C_n/r_p)·dt/C        (s_n ∈ {−1,0,+1})
    v_b   = Σ_n s_n·v_C_n          (inserted arm voltage)

``s_n ∈ {0,+1}`` for a half-bridge SM (unipolar) or ``{−1,0,+1}`` for a
full-bridge SM (bipolar, ±v_C). Whatever the external controller commands is
applied verbatim — if it seeds an imbalance and never corrects it, the arm
preserves it (there is no sort-and-select to hide a buggy external balancer).

Pure Python; the only pulsim coupling is ``builder.add_voltage_source`` and the
``pool``/``graph`` index helpers (identical to ``pulsim.mmc``).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Callable

# A gate source maps (time, arm) → per-submodule insertion states. The observer
# stashes the live arm current on ``arm.i_b`` and the per-SM cap voltages on
# ``arm.v_C_per_sm`` before each call, so an external controller can run the
# full thesis algorithm (cost function + sort-and-select) from the live state.
GateSource = Callable[[float, "GateDrivenArm"], Sequence[float]]


@dataclass
class GateDrivenArmParams:
    """Static configuration of a gate-driven arm."""

    n_sm: int = 6                      # submodules per arm
    c_sm: float = 680.0e-6             # per-submodule capacitance [F]
    v_c0: float = 4000.0              # initial per-submodule cap voltage [V]
    r_p_per_sm: float = 0.0           # parallel discharge resistance [Ω]; 0 ⇒ none
    sm_type: str = "full_bridge"      # "full_bridge" (±) | "half_bridge" (0/+)


@dataclass
class GateDrivenArm:
    """Live state + handle for one gate-driven arm."""

    params: GateDrivenArmParams
    gate_source: GateSource
    name: str
    v_C_per_sm: list[float] = field(default_factory=list)
    v_b: float = 0.0
    v_b_baseline: float = 0.0
    i_b: float = 0.0                  # last branch current (set by the observer)
    source_branch_id: int = -1

    @property
    def v_C(self) -> float:
        """Aggregate arm capacitor voltage Σ v_C_per_sm [V] (what the M3C
        controller reads — e.g. 6×4 kV = 24 kV)."""
        return float(sum(self.v_C_per_sm))

    @property
    def v_C_spread(self) -> float:
        """Submodule capacitor spread max−min [V] (balance telemetry). With no
        internal balancing this only shrinks if the *external* gates balance."""
        if not self.v_C_per_sm:
            return 0.0
        return float(max(self.v_C_per_sm) - min(self.v_C_per_sm))


def _clip_insertion(s: float, sm_type: str) -> float:
    lo = -1.0 if sm_type == "full_bridge" else 0.0
    return lo if s < lo else 1.0 if s > 1.0 else float(s)


def add_gate_driven_arm(
    builder,
    *,
    name: str,
    node_a: str,
    node_b: str,
    params: GateDrivenArmParams,
    gate_source: GateSource,
    v_c0_per_sm: Sequence[float] | None = None,
) -> GateDrivenArm:
    """Add a gate-driven arm (single controlled voltage source ``node_a→node_b``).

    ``gate_source(t, arm)`` must return ``params.n_sm`` insertion states. An
    optional ``v_c0_per_sm`` seeds a non-uniform initial submodule imbalance
    (e.g. to show the *external* balancer removing it). The user adds any series
    arm inductor and the rest of the topology, exactly as for the L0-L3 arms.
    """
    n = params.n_sm
    if v_c0_per_sm is None:
        v_c = [float(params.v_c0)] * n
    else:
        v_c = [float(v) for v in v_c0_per_sm]
        if len(v_c) != n:
            raise ValueError(f"v_c0_per_sm length {len(v_c)} != n_sm {n}")

    arm = GateDrivenArm(params=params, gate_source=gate_source, name=name,
                        v_C_per_sm=v_c)

    # DC-operating-point baseline: the inserted voltage at t=0 from the initial
    # gates, so multi-arm topologies solve their DC-OP correctly (the b_extra_fn
    # then injects the delta from this baseline every step).
    s0 = [_clip_insertion(s, params.sm_type)
          for s in gate_source(0.0, arm)]
    if len(s0) != n:
        raise ValueError(f"gate_source returned {len(s0)} states != n_sm {n}")
    v_b0 = sum(s0[k] * v_c[k] for k in range(n))
    arm.v_b = v_b0
    arm.v_b_baseline = v_b0

    src_id = builder.graph.num_branches
    builder.add_voltage_source(f"{name}_Varm", node_a, node_b, v_b0)
    arm.source_branch_id = src_id
    return arm


def make_gate_driven_arm_observers(
    builder,
    arms: "list[GateDrivenArm]",
    *,
    dt: float,
):
    """Build the ``(step_observer, b_extra_fn)`` pair for one or more
    gate-driven arms sharing the simulation step (plug into ``pulsim.simulate``).

    Mirrors ``pulsim.mmc.make_mmc_arms_observer``: ``i_b = x[src_idx]`` is the
    arm current (positive ``node_a→node_b``), the caps integrate forward-Euler
    under the externally-commanded insertion, and ``b_extra_fn`` injects
    ``baseline − v_b`` so the source presents the live inserted voltage.
    """
    if dt <= 0:
        raise ValueError(f"dt must be > 0 (got {dt})")
    if not arms:
        raise ValueError("arms must contain at least one element")

    state_size = builder.pool.state_size(builder.graph)
    src_indices = [
        builder.pool.branch_var_id_for_source(a.source_branch_id, builder.graph)
        for a in arms
    ]

    def _apply(arm: GateDrivenArm, s: Sequence[float], i_b: float) -> None:
        p = arm.params
        inv_c = dt / p.c_sm
        leak = (dt / (p.r_p_per_sm * p.c_sm)) if p.r_p_per_sm > 0.0 else 0.0
        v = arm.v_C_per_sm
        for nidx in range(p.n_sm):
            sn = _clip_insertion(s[nidx], p.sm_type)
            v[nidx] += sn * i_b * inv_c - v[nidx] * leak

    def step_observer(t, x):
        for k, arm in enumerate(arms):
            i_b = float(x[src_indices[k]])
            arm.i_b = i_b
            s = arm.gate_source(t, arm)              # external gates over [t,t+dt]
            _apply(arm, s, i_b)                       # integrate per-SM caps
            # Stash v_b for the NEXT sample (b_extra reads it one step later),
            # using the gates active at t+dt and the just-updated caps.
            s_next = arm.gate_source(t + dt, arm)
            p = arm.params
            arm.v_b = sum(_clip_insertion(s_next[nidx], p.sm_type)
                          * arm.v_C_per_sm[nidx] for nidx in range(p.n_sm))

    def b_extra_fn(_t):
        out = [0.0] * state_size
        for k, arm in enumerate(arms):
            out[src_indices[k]] = arm.v_b_baseline - arm.v_b
        return out

    return step_observer, b_extra_fn
