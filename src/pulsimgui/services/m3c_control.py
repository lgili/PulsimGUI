"""Closed-loop controller for the Modular Multilevel Matrix Converter (M3C).

Drives the nine 3×3-matrix arms (``M_<X><y>``, X∈ABC input phase, y∈abc output
phase) of an average-model M3C. Mirrors the ``MmcClosedLoopController``
interface (``update(t, currents, v_cap)`` + ``m_ref(name)``) so the existing
backend control observer drives it unchanged.

Control structure (average model, from L. C. Gili's thesis, Chapter 5):

* **Per-branch current loop** — each branch current ``i_Xy`` is regulated to the
  balanced reference ``i_ref_Xy = (I_in_X* + I_out_y*)/3`` (the minimal-
  circulating distribution) by a PI acting on the branch modulation, on top of
  the grid-voltage + L·di/dt + R·i feed-forward. Tracking every branch current
  regulates the input phase currents (row sums) and output phase currents
  (column sums).
* **Output current command** — ``(id_out, iq_out)`` set the output dq current
  (the converter's job: deliver controlled current/power to Sistema 2).
* **Total-energy loop** — a slow PI on the mean capacitor voltage sets the input
  active-current reference ``id_in`` so input power tracks output power and the
  mean cap voltage holds at ``v_c_ref``.
* **Per-branch capacitor balancing** (optional, ``balance=True``) — a doubly-
  centred proportional law injects an input-frequency circulating current that
  charges the low branches and discharges the high ones without disturbing the
  input/output phase currents (row/column sums stay zero).

Plain Python (no pulsim import) so it unit-tests in isolation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from pulsimgui.services.m3c_svm import CostSelector, tree_module_currents

_TWO_PI = 2.0 * math.pi
_PHASE_OFFSETS = (0.0, -_TWO_PI / 3.0, +_TWO_PI / 3.0)  # A/a, B/b, C/c


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


@dataclass
class M3CClosedLoopController:
    """Closed-loop current + energy (+ optional balancing) controller for one
    average-model M3C. ``branches`` is the nine ``M_<X><y>`` names in (X,y)
    order: M_Aa, M_Ab, M_Ac, M_Ba, ... M_Cc."""

    branches: list[str]
    f_in: float                          # input (Sistema 1) frequency [Hz]
    f_out: float                         # output (Sistema 2) frequency [Hz]
    v_in_pk: float                       # input phase-voltage peak [V]
    v_out_pk: float                      # output phase-voltage peak [V]
    v_c_ref: float                       # target aggregate branch-cap voltage [V]
    l_branch: float = 25.0e-3            # per-branch inductance [H]
    r_branch: float = 0.5               # per-branch resistance [Ω]

    # Output current command (dq, amplitude-invariant; d aligned with v_out).
    id_out: float = 0.0
    iq_out: float = 0.0
    iq_in: float = 0.0                   # input reactive current (0 ⇒ unity PF)

    control_dt: float = 1.0e-5
    soft_start_time: float = 1.0e-2      # ramp the commands 0→full over this [s]

    balance: bool = True                 # per-branch capacitor balancing
    k_balance: float = 0.04              # balancing proportional gain [A/V]
    ki_balance: float = 0.6              # balancing integral gain [A/(V·s)] —
                                         # drives the steady-state branch-cap
                                         # spread toward zero (a P-only law
                                         # leaves a residual the switching
                                         # disturbance keeps re-opening). Tuned
                                         # so the switched-model drift nearly
                                         # stops (≈1.8 kV spread, +0.06 kV/5 s
                                         # vs +0.44 kV/5 s for the original
                                         # input-frequency P-only law)
    k_row: float = 0.04                  # input-phase (row) energy-mode gain [A/V]
    k_col: float = 0.04                  # output-phase (col) energy-mode gain [A/V]
    i_circ_max: float = 60.0             # per-branch circulating-current clamp [A]
    i_in_max: float = 400.0              # input active-current ref clamp [A]

    # Loop bandwidths → default PI gains (Hz).
    f_bw_curr: float = 300.0
    f_bw_energy: float = 5.0
    kp_curr: float | None = None
    ki_curr: float | None = None
    kp_energy: float | None = None
    ki_energy: float | None = None

    # ---- resolved gains / state (not user inputs) ----
    _kp_i: float = field(default=0.0, init=False)
    _ki_i: float = field(default=0.0, init=False)
    _kp_w: float = field(default=0.0, init=False)
    _ki_w: float = field(default=0.0, init=False)
    _int_i: list[float] = field(default_factory=lambda: [0.0] * 9, init=False)
    _int_w: float = field(default=0.0, init=False)
    _int_bal: list[float] = field(default_factory=lambda: [0.0] * 9, init=False)
    _iref_prev: list[float] = field(default_factory=lambda: [0.0] * 9, init=False)
    _m_ref: dict[str, float] = field(default_factory=dict, init=False)
    _next_t: float = field(default=0.0, init=False)
    _started: bool = field(default=False, init=False)
    # diagnostics
    last_id_in: float = field(default=0.0, init=False)
    last_vc_mean: float = field(default=0.0, init=False)
    last_i_circ: list[float] = field(default_factory=lambda: [0.0] * 9, init=False)
    debug: bool = False
    debug_history: list = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        w_i = _TWO_PI * self.f_bw_curr
        w_w = _TWO_PI * self.f_bw_energy
        self._kp_i = self.kp_curr if self.kp_curr is not None else w_i * self.l_branch
        self._ki_i = self.ki_curr if self.ki_curr is not None else w_i * max(self.r_branch, 1e-3)
        # Energy loop: mean-cap error [V] → input active current [A]. Gentle.
        self._kp_w = self.kp_energy if self.kp_energy is not None else 0.05
        self._ki_w = self.ki_energy if self.ki_energy is not None else self._kp_w * w_w
        for name in self.branches:
            self._m_ref[name] = 0.0

    # ------------------------------------------------------------------
    def m_ref(self, name: str) -> float:
        """Latest modulation index held for branch ``name`` (0 until first tick)."""
        return self._m_ref.get(name, 0.0)

    def update(self, t: float, currents: dict, v_cap: dict) -> None:
        """Run the control law at most once per ``control_dt`` (sample & hold).
        ``currents[name]`` is the branch current [A]; ``v_cap[name]`` the
        aggregate branch capacitor voltage [V]."""
        if t + 1e-15 < self._next_t:
            return
        self._next_t = t + self.control_dt
        self._step(t, currents, v_cap)

    # ------------------------------------------------------------------
    def _step(self, t: float, currents: dict, v_cap: dict) -> None:
        dt = self.control_dt
        th_in = _TWO_PI * self.f_in * t
        th_out = _TWO_PI * self.f_out * t
        ramp = 1.0 if self.soft_start_time <= 0.0 else min(1.0, t / self.soft_start_time)

        vc = [v_cap.get(n, self.v_c_ref) for n in self.branches]
        self.last_vc_mean = vc_mean = sum(vc) / 9.0

        # --- total-energy loop: mean-cap error → input active-current ref ---
        e_w = self.v_c_ref - vc_mean
        id_in = self._kp_w * e_w + self._ki_w * self._int_w
        id_in_c = _clamp(id_in, -self.i_in_max, self.i_in_max)
        if id_in == id_in_c or (e_w * id_in) < 0.0:   # conditional anti-windup
            self._int_w += e_w * dt
        self.last_id_in = id_in_c

        # --- per-branch capacitor balancing → circulating current pattern ---
        # The branch-cap imbalance splits into three controllable mode groups
        # (besides the total, handled by the energy loop):
        #   • interaction (4 DOF) — the doubly-centred error, injected in phase
        #     with v_arm = v_in_X − v_out_y (both input and output frequency);
        #   • row modes (input-phase energy, 2 DOF) — transferred between input
        #     phases by a circulating current along the OUTPUT voltage pattern;
        #   • column modes (output-phase energy, 2 DOF) — transferred between
        #     output phases along the INPUT voltage pattern.
        # Each injection keeps zero input-phase (row) and output-phase (column)
        # current sums, so none disturbs the regulated phase currents. WITHOUT
        # the row/column terms the input/output-phase energy modes are
        # uncontrolled and slowly diverge (the long-run "caps lose themselves").
        i_circ = ([0.0] * 9 if not self.balance
                  else self._balancing_law(t, th_in, th_out, vc, vc_mean, dt,
                                           currents))
        self.last_i_circ = list(i_circ)

        # --- per-branch current loop on m (with grid + L·di/dt + R·i FF) ---
        for i in range(3):
            v_in = self.v_in_pk * math.sin(th_in + _PHASE_OFFSETS[i])
            i_in_ref = (self.id_in_abc(id_in_c, self.iq_in, th_in, i))
            for j in range(3):
                k = 3 * i + j
                name = self.branches[k]
                v_out = self.v_out_pk * math.sin(th_out + _PHASE_OFFSETS[j])
                i_out_ref = self.id_in_abc(self.id_out * ramp, self.iq_out * ramp,
                                           th_out, j)
                i_ref = (i_in_ref + i_out_ref) / 3.0 + i_circ[k]
                di_ref = (i_ref - self._iref_prev[k]) / dt
                self._iref_prev[k] = i_ref

                e = i_ref - currents.get(name, 0.0)
                self._int_i[k] += e * dt
                pi = self._kp_i * e + self._ki_i * self._int_i[k]
                v_arm = (v_in - v_out - self.r_branch * i_ref
                         - self.l_branch * di_ref - pi)
                self._m_ref[name] = _clamp(v_arm / max(vc[k], 1.0), -1.0, 1.0)

        if self.debug:
            self.debug_history.append(
                (t, vc_mean, id_in_c, dict(self._m_ref)))

    # ------------------------------------------------------------------
    def _balancing_law(self, t: float, th_in: float, th_out: float,
                       vc: list[float], vc_mean: float, dt: float,
                       currents: dict) -> list[float]:
        """Per-branch balancing → circulating-current pattern (default law).

        The branch-cap imbalance splits into three controllable mode groups
        (besides the total, handled by the energy loop):

        * interaction (4 DOF) — the doubly-centred error, injected in phase with
          ``v_arm = v_in_X − v_out_y`` (both input and output frequency);
        * row modes (input-phase energy, 2 DOF) — transferred between input
          phases by a circulating current along the OUTPUT voltage pattern;
        * column modes (output-phase energy, 2 DOF) — transferred between output
          phases along the INPUT voltage pattern.

        Each injection keeps zero input-phase (row) and output-phase (column)
        current sums, so none disturbs the regulated phase currents. WITHOUT the
        row/column terms the input/output-phase energy modes are uncontrolled
        and slowly diverge (the long-run "caps lose themselves").

        Subclasses (e.g. the thesis Fast-SVM controller) override this hook to
        substitute a different selection of the same constraint-clean injection.
        """
        i_circ = [0.0] * 9
        sin_in = [math.sin(th_in + _PHASE_OFFSETS[i]) for i in range(3)]
        sin_out = [math.sin(th_out + _PHASE_OFFSETS[j]) for j in range(3)]
        err = [vc_mean - vc[k] for k in range(9)]          # +ve ⇒ low ⇒ charge
        row = [sum(err[3 * i + j] for j in range(3)) / 3.0 for i in range(3)]
        col = [sum(err[3 * i + j] for i in range(3)) / 3.0 for j in range(3)]
        tot = sum(err) / 9.0
        for i in range(3):
            for j in range(3):
                k = 3 * i + j
                ec = err[k] - row[i] - col[j] + tot        # interaction
                cmd = self.k_balance * ec + self.ki_balance * self._int_bal[k]
                inj = (cmd * (sin_in[i] - sin_out[j])       # interaction
                       - self.k_row * row[i] * sin_out[j]   # row (input) mode
                       + self.k_col * col[j] * sin_in[i])   # column (output) mode
                inj_c = _clamp(inj, -self.i_circ_max, self.i_circ_max)
                # Conditional anti-windup: stop integrating into saturation.
                if inj == inj_c:
                    self._int_bal[k] += ec * dt
                i_circ[k] = inj_c
        return i_circ

    # ------------------------------------------------------------------
    @staticmethod
    def id_in_abc(d: float, q: float, theta: float, idx: int) -> float:
        """One phase of the inverse Park current (d aligned with the sin grid
        voltage): I_x(t) = d·sin(θ+φ) − q·cos(θ+φ)."""
        ang = theta + _PHASE_OFFSETS[idx]
        return d * math.sin(ang) - q * math.cos(ang)


@dataclass
class M3CSvmController(M3CClosedLoopController):
    """M3C controller whose capacitor balancing is the **thesis Fast-SVM cost
    function** (Etapas 3-4) instead of the default heuristic modal law.

    Everything else is inherited unchanged — the dq energy loop (Etapa 1), the
    per-branch input/output current loops (Etapa 2) and the grid + L·di/dt + R·i
    feed-forward. Only :meth:`_balancing_law` is overridden.

    Each switching period ``Ts = 1/f_switch`` it runs the thesis selection on
    the live state:

    1. lg-transform the reference input/output phase voltages and apply the
       Etapa-3 reduction (tie the smallest input phase to the smallest output
       phase), leaving 45 candidate connections.
    2. For each candidate (a spanning tree of K₃,₃) predict the per-module
       cap-voltage change ``ΔV_xy = Sn·I_xy·Ts/C`` from the live terminal
       currents routed through that tree, and evaluate the cost
       ``J = Σ_xy (ε_xy + ΔV_xy)²``.
    3. Apply the argmin connection for the whole ``Ts``.

    The chosen connection routes the terminal currents through five branches; in
    the GUI's always-connected modular-M3C mesh this is realised as the
    circulating-current pattern ``i_circ = k_svm·(I_tree − I_balanced)`` (zero
    input/output-phase sums, so it never disturbs the regulated phase currents).
    ``k_svm`` scales the discrete matrix-converter routing into a continuous
    circulating injection for the behavioural arms; the *selection* (which caps
    to charge/discharge) is the thesis's predictive cost function verbatim.
    """

    f_switch: float = 2000.0             # switching frequency [Hz] → Ts
    svm_capacitance: float = 680.0e-6    # submodule capacitance C [F]
    svm_sn: float = 6.0                  # active submodules per branch Sn
    k_svm: float = 0.25                  # discrete-routing → circulating gain

    _cost: CostSelector = field(default=None, init=False)  # type: ignore[assignment]
    _next_sel_t: float = field(default=0.0, init=False)
    _svm_conn: tuple = field(default=(), init=False)
    last_connection: tuple = field(default=(), init=False)
    last_short: tuple = field(default=(), init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        ts = 1.0 / max(self.f_switch, 1.0)
        self._cost = CostSelector(sn=self.svm_sn,
                                  capacitance=self.svm_capacitance, ts=ts)

    def _balancing_law(self, t: float, th_in: float, th_out: float,
                       vc: list[float], vc_mean: float, dt: float,
                       currents: dict) -> list[float]:
        # Live terminal currents from the nine branch currents: input phase
        # current = row sum, output phase current = column sum.
        ib = [currents.get(self.branches[k], 0.0) for k in range(9)]
        i_in = tuple(sum(ib[3 * i + j] for j in range(3)) for i in range(3))
        i_out = tuple(sum(ib[3 * i + j] for i in range(3)) for j in range(3))
        # Reference phase voltages (for the Etapa-3 smallest-in/out reduction).
        v_in = tuple(self.v_in_pk * math.sin(th_in + _PHASE_OFFSETS[i])
                     for i in range(3))
        v_out = tuple(self.v_out_pk * math.sin(th_out + _PHASE_OFFSETS[j])
                      for j in range(3))

        # Re-select the connection once per switching period (held over Ts, as
        # in the thesis); re-evaluate the injection magnitude every control tick.
        if not self._svm_conn or t + 1e-15 >= self._next_sel_t:
            self._next_sel_t = t + self._cost.ts
            conn, short = self._cost.select(v_in, v_out, i_in, i_out, vc)
            self._svm_conn = conn
            self.last_connection = conn
            self.last_short = short

        tree_i = tree_module_currents(self._svm_conn, i_in, i_out)
        balanced = [(i_in[i] + i_out[j]) / 3.0
                    for i in range(3) for j in range(3)]
        i_circ = [0.0] * 9
        for i in range(3):
            for j in range(3):
                k = 3 * i + j
                target = tree_i.get((i, j), 0.0)
                inj = self.k_svm * (target - balanced[k])
                i_circ[k] = _clamp(inj, -self.i_circ_max, self.i_circ_max)
        return i_circ
