"""Closed-loop controller for the average-value (L0) three-phase MMC.

The open-loop MMC (fixed sinusoidal insertion indices) is only marginally
stable: with no control of the internal energy the arm capacitor voltages run
away within a few ms. This module adds the three loops that make the converter
usable:

1. **Arm-energy balancing** — a slow PI loop drives the mean arm capacitor
   voltage to ``vc_ref`` by commanding a DC circulating-current reference. A
   positive DC circulating current pulls power from the DC bus into the arm
   caps, so a sagging average charges them back up.

2. **Circulating-current suppression (CCSC)** — a fast per-phase PI loop forces
   the phase circulating current ``i_z = (i_up + i_lo)/2`` to track that DC
   reference, which simultaneously kills the 2nd-harmonic circulating current
   that otherwise unbalances the arms. Its output ``v_z`` is the common-mode
   arm-voltage adjustment.

3. **Output voltage / current** — either an open-loop sinusoidal voltage
   reference (``current_control=False``) or a dq output-current loop
   (``current_control=True``) that regulates the load current to ``id_ref`` /
   ``iq_ref`` (Park frame aligned to the modulation angle).

The insertion indices are then ``m = v_arm_desired / v_C`` using the *measured*
capacitor voltage, so the commanded arm voltage stays correct as ``v_C`` moves.

The class is plain Python (no pulsim import) so it unit-tests in isolation. The
backend feeds it measured arm currents + capacitor voltages each control tick
via :meth:`update`; the per-arm insertion index is read back with
:meth:`m_ref`. Both the arm modulation callables and the backend control
observer share one instance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

_TWO_PI = 2.0 * math.pi
# Phase angle offsets A/B/C (balanced positive sequence): A=0, B=-120, C=+120.
_PHASE_OFFSETS_DEG = (0.0, -120.0, 120.0)

# Debug-only registry so a test/diagnostic can reach the controller instance
# the converter built inside a run. Cheap (holds references); cleared on demand.
_DEBUG_REGISTRY: list = []


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


@dataclass
class MmcClosedLoopController:
    """Energy + CCSC (+ optional dq current) controller for one 3φ MMC.

    ``phase_arms`` is the per-phase ``(upper_arm_name, lower_arm_name)`` map in
    A, B, C order; the names match the MMC_ARM component names so the backend
    can key measurements + insertion indices by them. Gains left at ``None``
    are filled from the circuit parameters with sensible bandwidths.
    """

    phase_arms: list[tuple[str, str]]
    vdc_half: float                      # half DC-bus voltage (rail to midpoint)
    vc_ref: float                        # target mean arm capacitor voltage
    freq: float                          # output fundamental frequency (Hz)
    mod_index: float                     # open-loop voltage modulation index
    phase_deg: float = 0.0               # global output phase shift
    arm_l: float = 5.0e-3                # per-arm inductance (H)
    arm_r: float = 0.1                   # per-arm resistance (Ω)
    control_dt: float = 1.0e-5           # controller sample period (s)
    soft_start_time: float = 5.0e-3      # ramp the output 0→full over this (s)

    # Per-phase arm-energy balancing. Off (total energy) by default: it's the
    # right call for a balanced load and keeps the full output (a per-phase
    # loop injects a fundamental circulating current that trims the AC swing).
    # Turn it on for asymmetric loads / per-leg drift.
    per_phase_energy: bool = False

    # Output-current (dq) loop — off by default (open-loop voltage).
    current_control: bool = False
    id_ref: float = 0.0
    iq_ref: float = 0.0
    load_l: float = 0.0
    load_r: float = 0.0

    # Gains (None → computed from bandwidths below).
    kp_ccsc: float | None = None
    ki_ccsc: float | None = None
    kp_energy: float | None = None
    ki_energy: float | None = None
    kp_curr: float | None = None
    ki_curr: float | None = None

    # Closed-loop bandwidths used to size the default gains (Hz).
    f_bw_ccsc: float = 500.0
    f_bw_energy: float = 15.0
    f_bw_curr: float = 300.0
    i_circ_max: float = 40.0             # DC circulating-current ref clamp (A)

    # ---- resolved gains (filled in __post_init__) ----
    _kp_ccsc: float = field(default=0.0, init=False)
    _ki_ccsc: float = field(default=0.0, init=False)
    _kp_energy: float = field(default=0.0, init=False)
    _ki_energy: float = field(default=0.0, init=False)
    _kp_curr: float = field(default=0.0, init=False)
    _ki_curr: float = field(default=0.0, init=False)

    # ---- internal state (not user inputs) ----
    _m_ref: dict[str, float] = field(default_factory=dict, init=False)
    _int_energy: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0], init=False)
    _int_ccsc: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0], init=False)
    _int_d: float = field(default=0.0, init=False)
    _int_q: float = field(default=0.0, init=False)
    _next_t: float = field(default=0.0, init=False)
    _phi: tuple[float, float, float] = field(default=(0.0, 0.0, 0.0), init=False)
    # last computed diagnostics (handy for tests / introspection)
    last_i_circ_ref: float = field(default=0.0, init=False)
    last_vc_avg: float = field(default=0.0, init=False)
    # optional per-tick trace (t, vc_avg, i_circ_ref, i_zA, i_oA, m_uA) — only
    # filled when ``debug`` is set, for sign/gain diagnostics.
    debug: bool = False
    debug_history: list = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        w_ccsc = _TWO_PI * self.f_bw_ccsc
        w_energy = _TWO_PI * self.f_bw_energy
        w_curr = _TWO_PI * self.f_bw_curr
        # Circulating loop sees both arm inductors/resistors in series.
        l_circ = 2.0 * self.arm_l
        r_circ = 2.0 * self.arm_r
        self._kp_ccsc = self.kp_ccsc if self.kp_ccsc is not None else w_ccsc * l_circ
        self._ki_ccsc = self.ki_ccsc if self.ki_ccsc is not None else w_ccsc * max(r_circ, 1e-3)
        # Energy loop: dW/dt ≈ Vdc · i_circ. Keep it gentle.
        self._kp_energy = (
            self.kp_energy if self.kp_energy is not None
            else w_energy * 2.0 * self.arm_l / max(self.vdc_half, 1.0) * 50.0
        )
        self._ki_energy = (
            self.ki_energy if self.ki_energy is not None
            else self._kp_energy * w_energy
        )
        self._kp_curr = self.kp_curr if self.kp_curr is not None else w_curr * max(self.load_l, self.arm_l)
        self._ki_curr = self.ki_curr if self.ki_curr is not None else w_curr * max(self.load_r, 1e-3)
        self._phi = tuple(
            math.radians(self.phase_deg + off) for off in _PHASE_OFFSETS_DEG
        )  # type: ignore[assignment]
        for upper, lower in self.phase_arms:
            self._m_ref[upper] = 0.5
            self._m_ref[lower] = 0.5
        if self.debug:
            _DEBUG_REGISTRY.append(self)

    # ------------------------------------------------------------------
    def m_ref(self, arm_name: str) -> float:
        """Latest insertion index held for ``arm_name`` (0.5 until first tick)."""
        return self._m_ref.get(arm_name, 0.5)

    def update(
        self,
        t: float,
        currents: dict[str, float],
        v_cap: dict[str, float],
    ) -> None:
        """Run the control law at most once per ``control_dt`` (sample & hold).

        ``currents`` / ``v_cap`` are keyed by arm name; ``currents[name]`` is the
        arm branch current (A) and ``v_cap[name]`` the total submodule-cap
        voltage (V).
        """
        if t + 1e-15 < self._next_t:
            return
        self._next_t = t + self.control_dt
        self._step(t, currents, v_cap)

    # ------------------------------------------------------------------
    def _step(
        self,
        t: float,
        currents: dict[str, float],
        v_cap: dict[str, float],
    ) -> None:
        dt = self.control_dt
        theta = _TWO_PI * self.freq * t

        # --- 1. per-phase arm-energy balancing → per-phase DC circulating ref ---
        # Each phase regulates its OWN mean cap voltage, so an asymmetric load
        # (or arm drift) can't pull the legs apart the way a single total-energy
        # loop allows. pulsim's average arm charges its caps with +m·i_b, so a
        # positive DC circulating current pulls bus energy in; a sagging phase
        # (e_w>0) therefore commands a positive i_circ_ref to recharge it.
        vc_vals = [v_cap.get(n, self.vc_ref) for ph in self.phase_arms for n in ph]
        self.last_vc_avg = sum(vc_vals) / len(vc_vals)
        i_circ_ref = [0.0, 0.0, 0.0]
        if self.per_phase_energy:
            for j, (up, lo) in enumerate(self.phase_arms):
                w_j = 0.5 * (v_cap.get(up, self.vc_ref) + v_cap.get(lo, self.vc_ref))
                e_w = self.vc_ref - w_j
                icr = self._kp_energy * e_w + self._ki_energy * self._int_energy[j]
                icr_c = _clamp(icr, -self.i_circ_max, self.i_circ_max)
                if icr == icr_c or (e_w * icr) < 0.0:  # conditional anti-windup
                    self._int_energy[j] += e_w * dt
                i_circ_ref[j] = icr_c
        else:
            e_w = self.vc_ref - self.last_vc_avg
            icr = self._kp_energy * e_w + self._ki_energy * self._int_energy[0]
            icr_c = _clamp(icr, -self.i_circ_max, self.i_circ_max)
            if icr == icr_c or (e_w * icr) < 0.0:
                self._int_energy[0] += e_w * dt
            i_circ_ref = [icr_c, icr_c, icr_c]
        self.last_i_circ_ref = i_circ_ref[0]

        # Soft-start: ramp the commanded output 0→full so the arms aren't
        # slammed at t=0 (energy + CCSC stay active to hold v_C during the ramp).
        ramp = 1.0 if self.soft_start_time <= 0.0 else min(1.0, t / self.soft_start_time)

        # --- 3. output voltage reference (open-loop or dq current loop) ---
        if self.current_control:
            i_out = [
                currents.get(up, 0.0) - currents.get(lo, 0.0)
                for (up, lo) in self.phase_arms
            ]
            i_d, i_q = self._park(i_out, theta)
            e_d = self.id_ref * ramp - i_d
            e_q = self.iq_ref * ramp - i_q
            self._int_d += e_d * dt
            self._int_q += e_q * dt
            w = _TWO_PI * self.freq
            v_d = self._kp_curr * e_d + self._ki_curr * self._int_d - w * self.load_l * i_q
            v_q = self._kp_curr * e_q + self._ki_curr * self._int_q + w * self.load_l * i_d
            v_out = self._inv_park(v_d, v_q, theta)
        else:
            amp = self.mod_index * self.vdc_half * ramp
            v_out = [amp * math.sin(theta + self._phi[j]) for j in range(3)]

        # --- 2. per-phase CCSC + insertion indices ---
        for j, (up, lo) in enumerate(self.phase_arms):
            i_z = 0.5 * (currents.get(up, 0.0) + currents.get(lo, 0.0))
            e_z = i_circ_ref[j] - i_z
            self._int_ccsc[j] += e_z * dt
            v_z = self._kp_ccsc * e_z + self._ki_ccsc * self._int_ccsc[j]

            v_upper = self.vdc_half - v_out[j] - v_z
            v_lower = self.vdc_half + v_out[j] - v_z
            self._m_ref[up] = _clamp(v_upper / max(v_cap.get(up, 1.0), 1.0), 0.0, 1.0)
            self._m_ref[lo] = _clamp(v_lower / max(v_cap.get(lo, 1.0), 1.0), 0.0, 1.0)

        if self.debug:
            self.debug_history.append((
                t, self.last_vc_avg, list(i_circ_ref),
                dict(currents), dict(v_cap), dict(self._m_ref),
            ))

    # ------------------------------------------------------------------
    @staticmethod
    def _park(abc: list[float], theta: float) -> tuple[float, float]:
        """Amplitude-invariant Park: (a,b,c) → (d,q) at angle ``theta``."""
        a, b, c = abc
        cos, sin = math.cos, math.sin
        d = (2.0 / 3.0) * (
            a * cos(theta)
            + b * cos(theta - _TWO_PI / 3.0)
            + c * cos(theta + _TWO_PI / 3.0)
        )
        q = -(2.0 / 3.0) * (
            a * sin(theta)
            + b * sin(theta - _TWO_PI / 3.0)
            + c * sin(theta + _TWO_PI / 3.0)
        )
        return d, q

    @staticmethod
    def _inv_park(d: float, q: float, theta: float) -> list[float]:
        """Inverse amplitude-invariant Park: (d,q) → (a,b,c)."""
        cos, sin = math.cos, math.sin
        return [
            d * cos(theta) - q * sin(theta),
            d * cos(theta - _TWO_PI / 3.0) - q * sin(theta - _TWO_PI / 3.0),
            d * cos(theta + _TWO_PI / 3.0) - q * sin(theta + _TWO_PI / 3.0),
        ]
