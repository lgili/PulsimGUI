"""External gate modulator for gate-driven M3C arms — the thesis, fully outside.

This is the "control is external, the model only represents" companion to
:mod:`pulsimgui.services.gate_driven_arm`. It implements the thesis's complete
six-stage scheme OUTSIDE the arm and emits per-submodule **gate / insertion
signals**, which a :class:`~pulsimgui.services.gate_driven_arm.GateDrivenArm`
applies verbatim:

* **Etapas 1-4** — delegated to an :class:`M3CSvmController` (dq energy + per-
  branch current loops + the Fast-SVM cost-function inter-module balancing).
  These produce the per-branch modulation index ``m_ref_Xy ∈ [−1, 1]``.
* **Etapa 3/6 — level quantisation + PWM.** The continuous ``m_ref`` is turned
  into a number of inserted submodules ``n = round-ish(|m|·N)`` with sign; the
  fractional level is realised by a per-arm carrier dither (uniformly-sampled
  PWM), giving the multilevel staircase.
* **Etapa 5 — intra-module sort-and-select**, done EXTERNALLY here (not by the
  arm): of the arm's ``N`` submodules, insert the ``n`` whose capacitors most
  need the resulting charge — the lowest when the insertion will charge them,
  the highest when it will discharge them, read from the arm's live per-SM cap
  voltages. This is the balancing the L3 arm normally hides internally; here the
  controller owns it, exactly like a HIL/Simulink external modulator.

So the full hierarchy runs outside the model: inter-module balancing (cost
function, Etapa 4) + intra-module balancing (sort-and-select, Etapa 5), and the
gate-driven arm is a passive multilevel cap network.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def insertion_vector(m: float, t: float, arm: Any, *, f_carrier: float = 2000.0,
                     phase: float = 0.0, pwm: bool = True):
    """Convert a modulation index ``m ∈ [−1, 1]`` into a per-submodule insertion
    vector for ``arm`` (Etapas 3/5/6, reusable by any modulator).

    Level quantisation ``|m|·N`` + per-arm carrier PWM realises the staircase;
    an external sort-and-select on the arm's live ``v_C_per_sm`` (insert the
    lowest caps when the insertion will charge them, the highest when it will
    discharge them — judged from ``arm.i_b``) does the intra-module balancing.
    Returns ``(s, n_insert)`` with ``s ∈ {−1,0,+1}^N`` (the arm clips to its
    half-/full-bridge range).
    """
    n = arm.params.n_sm
    m = _clamp(m, -1.0, 1.0)
    if abs(m) < 1e-12:
        return [0.0] * n, 0
    level = abs(m) * n
    n_insert = int(math.floor(level))
    frac = level - n_insert
    if pwm and frac > 1e-9:
        carrier = ((t * f_carrier) + phase) % 1.0
        if carrier < frac:
            n_insert += 1
    n_insert = min(n_insert, n)
    if n_insert == 0:
        return [0.0] * n, 0
    sign = 1.0 if m > 0.0 else -1.0
    charging = (sign * float(getattr(arm, "i_b", 0.0))) > 0.0
    v = arm.v_C_per_sm
    order = sorted(range(n), key=lambda k: v[k])
    picks = order[:n_insert] if charging else order[n - n_insert:]
    s = [0.0] * n
    for k in picks:
        s[k] = sign
    return s, n_insert


@dataclass
class M3CSvmGateModulator:
    """Wraps an Etapas-1-4 controller and emits per-submodule gates (Etapa 5-6).

    ``controller`` is any object with the ``update(t, currents, vcap)`` /
    ``m_ref(name)`` interface (an :class:`M3CSvmController` for the thesis cost
    function, or an :class:`M3CClosedLoopController`). ``branches`` are the nine
    ``M_<X><y>`` names. ``f_carrier`` sets the PWM dither rate that realises the
    fractional modulation level.
    """

    controller: Any
    branches: list[str]
    f_carrier: float = 2000.0
    pwm: bool = True

    _m_ref: dict[str, float] = field(default_factory=dict, init=False)
    _phase: dict[str, float] = field(default_factory=dict, init=False)
    # diagnostics: last emitted insertion count per branch
    last_n_insert: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for k, name in enumerate(self.branches):
            self._m_ref[name] = 0.0
            # phase-shifted carriers (PSC-PWM flavour) so the nine arms don't
            # all dither in lock-step.
            self._phase[name] = (k % max(len(self.branches), 1)) / max(
                len(self.branches), 1)

    # ------------------------------------------------------------------
    def update(self, t: float, currents: dict, v_cap: dict) -> None:
        """Run the Etapas-1-4 controller (sample-held internally) and cache the
        per-branch modulation indices for the gate conversion."""
        self.controller.update(t, currents, v_cap)
        for name in self.branches:
            self._m_ref[name] = float(self.controller.m_ref(name))

    # ------------------------------------------------------------------
    def gates_for(self, t: float, arm: Any) -> list[float]:
        """Etapa 5-6: convert the held ``m_ref`` for ``arm`` into a per-SM
        insertion vector ``s ∈ {−1, 0, +1}^N`` via level quantisation, carrier
        PWM and an external sort-and-select on the arm's live per-SM caps."""
        m = self._m_ref.get(arm.name, 0.0)
        s, n_insert = insertion_vector(
            m, t, arm, f_carrier=self.f_carrier,
            phase=self._phase.get(arm.name, 0.0), pwm=self.pwm)
        self.last_n_insert[arm.name] = n_insert
        return s

    # ------------------------------------------------------------------
    def gate_source(self):
        """Return a generic ``gate_source(t, arm)`` closure bound to this
        modulator — pass to ``add_gate_driven_arm(..., gate_source=...)``. The
        arm is matched by ``arm.name``, so one closure serves all nine arms."""
        def _src(t: float, arm: Any) -> list[float]:
            return self.gates_for(t, arm)
        return _src
