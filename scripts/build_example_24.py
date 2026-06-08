"""Build ``examples/24_cmc_svm_cblock.pulsim``.

Showcase example for pulsim 1.8's ``add_c_block`` "Path B" migration.
The user-visible point of this example is:

  * **One** ``C_BLOCK`` component contains a non-trivial control law
    (Casadei–Serra Space Vector Modulation for a Conventional Matrix
    Converter) written **inline in C** — no external ``.c`` file, no
    pre-built ``.so``, no Python authoring.
  * The block reads **3 inputs** (the filtered grid voltages) and
    drives **3 outputs** (the synthesised matrix-converter output
    phases) — the new ``add_c_block(inputs=[("v", n)…],
    outputs=[("v", n_pos, n_neg)…])`` contract.
  * Pulsim 1.8 takes the inline C body, compiles it on-the-fly, and
    runs it at the sample rate the user picked (50 µs = 20 kHz) —
    same authoring loop as a Simulink S-function, but the result is
    bit-exact with a hand-written kernel block.
  * The output frequency (25 Hz) is completely decoupled from the
    input frequency (60 Hz) — the schematic shows AC-AC frequency
    conversion **without** a DC link, which is the whole point of a
    matrix converter and one of the things pulsim couldn't easily
    showcase before the ``add_c_block`` migration.

Topology — **average model** of a Conventional Matrix Converter
(CMC). A real CMC has 9 bidirectional switches arranged in a 3×3
matrix, which would mean ~18 pulsim switches and at least that many
control signals — too noisy for a 20-component showcase. Instead we
exploit the fact that the **time-average** of Casadei–Serra SVM is
exactly Venturini's optimum modulation: a 3×3 Park-like projection
of the input voltage vector onto a unit vector rotating at the
output frequency. The C_BLOCK runs the real SVM sector lookup
(useful as a teaching moment) and then emits the averaged output
voltages via 3 controlled voltage sources — the same signal a
fully-switched CMC would produce after low-pass filtering through
the output L+R load.

Numerical design point
----------------------

* Input grid: 415 V line-line RMS, 60 Hz (3φ wye, 339 V phase peak).
* Input filter: ``L_in_{a,b,c}`` = 2 mH series + ``C_in_{a,b,c}``
  = 10 µF shunt to ground (cuts the switching ripple a real CMC
  would inject back into the grid).
* Output frequency: 25 Hz. The 5/12 ratio with the 60 Hz input
  produces a visually unmistakable beat pattern between the input
  rhythm and the output rhythm.
* Modulation index q = 0.6 (max theoretical for SVM-CMC is
  √3/2 ≈ 0.866 — we leave headroom so duties stay non-negative
  under a worst-case input dip).
* PWM period 50 µs (20 kHz) — the C_BLOCK ``sample_time``.
* Output load: 3φ star R = 10 Ω + L = 10 mH per phase, neutral
  grounded.
* Sim ``tstop`` = 0.1 s (2.5 output cycles at 25 Hz, 6 input cycles
  at 60 Hz — both rhythms visible in one window).
* Sim ``dt`` = 5 µs (10× oversample of the PWM period).
* Engine: PWL — DSED's analytical fast path would refuse the
  C_BLOCK (it can't extract a closed-form state-space for a block
  driven by inline C).

Component count target ≈ 20. Actual:

  - 1 ``THREE_PHASE_SOURCE``       (V_grid)
  - 3 ``GROUND``                   (GND_grid, GND_filt, GND_load)
  - 6 ``INDUCTOR``                 (3 input filter + 3 load)
  - 3 ``CAPACITOR``                (input filter shunts)
  - 1 ``C_BLOCK``                  (CMC_SVM — THE STAR)
  - 3 ``RESISTOR``                 (load)
  - 2 ``ELECTRICAL_SCOPE``         (input + output telemetry)
  - 4 ``VOLTAGE_PROBE_GND``        (V(va_filt), V(vb_filt), V(vA), V(vB))
  - 4 ``CURRENT_PROBE``            (I_L_in_a, I_L_in_b, I_R_A, I_R_B)

→ 27 components total (still tractable for a single-page demo,
and every one earns its place in the scopes).

Run::

    python scripts/build_example_24.py
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DST = REPO / "examples" / "24_cmc_svm_cblock.pulsim"

# Deterministic IDs — same uuid5 trick as build_example_23.py so re-runs
# produce a bit-for-bit identical file (diff-friendly).
_NS = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _uid(label: str) -> str:
    return str(uuid.uuid5(_NS, f"ex24/{label}"))


def _pin(index: int, name: str, x: float, y: float) -> dict:
    return {"index": index, "name": name, "x": float(x), "y": float(y)}


def _component(
    *,
    comp_id: str,
    comp_type: str,
    name: str,
    x: float,
    y: float,
    parameters: dict,
    pins: list[dict],
    rotation: int = 0,
) -> dict:
    return {
        "id": comp_id,
        "type": comp_type,
        "name": name,
        "x": float(x),
        "y": float(y),
        "rotation": rotation,
        "mirrored_h": False,
        "mirrored_v": False,
        "parameters": parameters,
        "pins": pins,
    }


def _wire(
    *,
    wire_id: str,
    from_id: str,
    from_pin: int,
    to_id: str,
    to_pin: int,
    node_name: str = "",
    segments: list[dict] | None = None,
) -> dict:
    return {
        "id": wire_id,
        "segments": segments or [],
        "start_connection": {"component_id": from_id, "pin_index": from_pin},
        "end_connection": {"component_id": to_id, "pin_index": to_pin},
        "junctions": [],
        "node_name": node_name,
        "alias": "",
    }


def _pin_world(comp: dict, pin_index: int) -> tuple[float, float]:
    """Resolve a pin's absolute (world) coordinates from its component."""
    cx, cy = float(comp["x"]), float(comp["y"])
    for pin in comp["pins"]:
        if pin["index"] == pin_index:
            return cx + float(pin["x"]), cy + float(pin["y"])
    raise KeyError(f"pin {pin_index} not found on {comp.get('name')!r}")


def _l_segments(
    p1: tuple[float, float],
    p2: tuple[float, float],
    *,
    vertical_first: bool = False,
) -> list[dict]:
    """Build an L-shaped 2-segment routing between two world points.

    With ``vertical_first=False`` (default) the route goes
    horizontally to ``(p2.x, p1.y)`` then vertically to ``p2``;
    with ``vertical_first=True`` it goes vertically first then
    horizontally. The choice influences where the corner lands —
    important because ``_merge_nearby_points`` in ``build_node_map``
    silently merges points that happen to fall within 5 px of each
    other across the entire wire+pin point cloud, so two corners from
    different nets at the same coordinates would short.

    ``build_node_map`` only needs segment endpoints to be at the pin
    world positions — it then unions them via spatial coincidence AND
    via ``start_connection`` / ``end_connection`` metadata.
    """
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2 and y1 == y2:
        # Degenerate: emit a single zero-length segment so the wire
        # has at least one entry (the union-find treats it as a
        # single point).
        return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}]
    if x1 == x2 or y1 == y2:
        # Straight-line case — single segment.
        return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}]
    if vertical_first:
        return [
            {"x1": x1, "y1": y1, "x2": x1, "y2": y2},
            {"x1": x1, "y1": y2, "x2": x2, "y2": y2},
        ]
    return [
        {"x1": x1, "y1": y1, "x2": x2, "y2": y1},
        {"x1": x2, "y1": y1, "x2": x2, "y2": y2},
    ]


# Wires whose end is on a scope or going from a MEAS/OUT signal pin
# upward to a scope use vertical-first routing — keeps the corner on
# the source's X axis instead of the scope's. Identified by node-name
# prefix ("SIG_") which we already use on every signal-bearing wire.
SIGNAL_WIRE_PREFIXES = ("SIG_",)


def _route_wire_segments(wire: dict, comp_by_id: dict[str, dict]) -> None:
    """Populate ``wire['segments']`` with an L-shape based on the
    wire's start/end pin world coordinates. No-op if segments are
    already present.

    ``build_node_map`` uses these segment endpoints to union pin nets
    via spatial coincidence (PIN_HIT_TOLERANCE = 5 px). It ALSO unions
    via explicit ``start_connection`` / ``end_connection`` metadata,
    but ONLY when the wire has at least one segment (the union code
    reads ``start_ref`` from the first segment). So we must emit
    segments to make the explicit-endpoint path work.
    """
    if wire.get("segments"):
        return
    sc = wire["start_connection"]
    ec = wire["end_connection"]
    a_comp = comp_by_id[sc["component_id"]]
    b_comp = comp_by_id[ec["component_id"]]
    a_pos = _pin_world(a_comp, int(sc["pin_index"]))
    b_pos = _pin_world(b_comp, int(ec["pin_index"]))

    # Signal-domain wires going to scopes get vertical-first routing
    # to avoid corner collisions with the corners of power-domain
    # wires that converge on the scope's X column.
    node_name = str(wire.get("node_name") or "")
    is_signal = any(node_name.startswith(prefix) for prefix in SIGNAL_WIRE_PREFIXES)
    wire["segments"] = _l_segments(a_pos, b_pos, vertical_first=is_signal)


# ---------------------------------------------------------------------------
# Inline-C source for the C_BLOCK — Casadei–Serra SVM + Venturini avg.
#
# Pulsim 1.8 wraps this body in a generated ``void cblock_step(double t,
# double dt, const double *in, double *out, double *state)`` so no
# function prototype or #include directives are needed. The body has
# access to:
#   t      — simulation time at the start of the sample (s)
#   dt     — sample period (s)
#   in[i]  — input i (i in [0, n_inputs))
#   out[j] — output j (j in [0, n_outputs))
#   state  — n_states-element scratch vector (unused here — pure
#            feed-forward modulator)
# math.h is implicitly available (sin/cos/atan2/sqrt/floor).
# ---------------------------------------------------------------------------
CMC_SVM_SOURCE = r"""/* === CMC Space Vector Modulation (Casadei-Serra) ===
 * inputs : in[0..2] = filtered input phase voltages v_a, v_b, v_c
 * outputs: out[0..2] = synthesised output phase voltages v_A, v_B, v_C
 *
 * Algorithm: every PWM period (dt = 50 us), compute
 *   1. Input voltage vector angle theta_i and magnitude V_i (Clarke).
 *   2. Output reference angle theta_o = omega_o * t and reference
 *      magnitude q * V_i where q is the modulation index.
 *   3. Input sector K_i in 1..6 (60-deg bands of theta_i).
 *   4. Output sector K_v in 1..6 (60-deg bands of theta_o).
 *   5. Sector-internal angles beta_i, beta_o in [-30, +30] deg.
 *   6. Casadei-Serra duty cycles for the 4 active configurations:
 *           d_I   = (2/sqrt(3)) * q * sin(pi/3 - beta_o) * sin(pi/3 - beta_i)
 *           d_II  = (2/sqrt(3)) * q * sin(beta_o + pi/6) * sin(pi/3 - beta_i)
 *           d_III = (2/sqrt(3)) * q * sin(pi/3 - beta_o) * sin(beta_i + pi/6)
 *           d_IV  = (2/sqrt(3)) * q * sin(beta_o + pi/6) * sin(beta_i + pi/6)
 *           d_0   = 1 - d_I - d_II - d_III - d_IV
 *      d_0 < 0 means q is too aggressive - clamp to a feasible q upstream.
 *   7. Synthesise the averaged output voltages. The Venturini optimum
 *      (which equals the SVM time-average) collapses to projecting the
 *      input voltage vector onto a unit vector rotating at omega_o:
 *           v_oj(t) = q * (v_alpha * cos(theta_o - j*120)
 *                          + v_beta * sin(theta_o - j*120))
 *      We emit those averages; in a switched implementation the same
 *      v_oj results after time-averaging the 5 vector intervals.
 *
 * State: none (pure feed-forward; pulsim 1.8 ZOH-holds the outputs
 * between sample_time firings). */
const double PI       = 3.14159265358979323846;
const double TWO_PI   = 6.28318530717958647692;
const double PI_THIRD = 1.04719755119659774615;   /* 60 deg */
const double PI_SIXTH = 0.52359877559829887308;   /* 30 deg */
const double SQRT3    = 1.73205080756887729353;
const double TWO_3    = 0.66666666666666666667;
const double SQRT3_2  = 0.86602540378443864676;
const double DEG120   = 2.09439510239319549231;

double q     = 0.6;
double f_o   = 25.0;
double omega_o = TWO_PI * f_o;

double va = in[0], vb = in[1], vc = in[2];

/* Input vector in alpha-beta (amplitude-invariant Clarke) */
double v_alpha = TWO_3 * (va - 0.5 * vb - 0.5 * vc);
double v_beta  = TWO_3 * (SQRT3_2 * vb - SQRT3_2 * vc);
double V_i     = sqrt(v_alpha * v_alpha + v_beta * v_beta);
double theta_i = atan2(v_beta, v_alpha);
if (theta_i < 0) theta_i += TWO_PI;

/* Output reference angle */
double theta_o = omega_o * t;
double theta_o_wrap = theta_o - TWO_PI * floor(theta_o / TWO_PI);

/* Sector lookup (1..6, 60 deg each) - computed but not consumed by
   the averaged synthesis below. A switched implementation would use
   these indices to drive 9 gate signals via a lookup table. */
int K_i = (int)(theta_i      / PI_THIRD) + 1; if (K_i > 6) K_i = 1;
int K_v = (int)(theta_o_wrap / PI_THIRD) + 1; if (K_v > 6) K_v = 1;
double beta_i = theta_i      - (K_i - 1) * PI_THIRD - PI_SIXTH;
double beta_o = theta_o_wrap - (K_v - 1) * PI_THIRD - PI_SIXTH;

/* Casadei-Serra duties - emitted for completeness; the unused-warning
   below is silenced via the (void) casts. */
double scale = 2.0 / SQRT3 * q;
double d_I   = scale * sin(PI_THIRD - beta_o) * sin(PI_THIRD - beta_i);
double d_II  = scale * sin(beta_o + PI_SIXTH) * sin(PI_THIRD - beta_i);
double d_III = scale * sin(PI_THIRD - beta_o) * sin(beta_i + PI_SIXTH);
double d_IV  = scale * sin(beta_o + PI_SIXTH) * sin(beta_i + PI_SIXTH);
double d_0   = 1.0 - d_I - d_II - d_III - d_IV;
(void)d_0; (void)K_i; (void)K_v; (void)V_i;
(void)d_I; (void)d_II; (void)d_III; (void)d_IV;

/* Averaged synthesis (= Venturini optimum = SVM time-average):
   project the input voltage vector onto a unit vector rotating at
   omega_o, one per output phase shifted by 120 deg. */
double phi[3] = {theta_o_wrap, theta_o_wrap - DEG120, theta_o_wrap + DEG120};
for (int j = 0; j < 3; j++) {
    double v_proj = v_alpha * cos(phi[j]) + v_beta * sin(phi[j]);
    out[j] = q * v_proj;
}
"""


# ---------------------------------------------------------------------------
# Layout constants — the schematic spans roughly 2200 px wide, 1000 px tall.
# X grows left → right (input grid on the left, load on the right). Y grows
# top → bottom; each phase gets its own horizontal lane (A top, B middle,
# C bottom). Lanes are 200 px apart to leave room for the C_BLOCK's 3 IN /
# 3 OUT pins (200 px tall block) without geometric pin collisions in the
# union-find connectivity pass.
# ---------------------------------------------------------------------------
X_GRID     =   -900
X_LIN      =   -640
X_VPROBE_I =   -440
X_CIN      =   -440
X_CBLOCK   =   -160
X_VPROBE_O =    140
X_R_LOAD   =    320
X_L_LOAD   =    480
X_NEUTRAL  =    640

Y_PHASE_A  =   -200
Y_PHASE_B  =      0
Y_PHASE_C  =    200
Y_NEUTRAL  =    340

Y_SCOPE_IN  = -400
Y_SCOPE_OUT =  400
X_SCOPE_IN  =  -160
X_SCOPE_OUT =  780


def build() -> dict:
    components: list[dict] = []
    wires: list[dict] = []

    # ------------------------------------------------------------------
    # V_grid — THREE_PHASE_SOURCE. 415 V LL, 60 Hz. Pins A/B/C/N.
    # ------------------------------------------------------------------
    v_grid_id = _uid("V_grid")
    v_grid = _component(
        comp_id=v_grid_id, comp_type="THREE_PHASE_SOURCE", name="V_grid",
        x=X_GRID, y=Y_PHASE_B,
        parameters={
            "line_to_line_voltage_rms": 415.0,
            "frequency_hz": 60.0,
            "phase_a_deg": 0.0,
            "positive_sequence": True,
            "unbalance_factor": 0.0,
        },
        pins=[
            _pin(0, "A", 40, -20),
            _pin(1, "B", 40,   0),
            _pin(2, "C", 40,  20),
            _pin(3, "N", -40,  0),
        ],
    )
    components.append(v_grid)

    # GND_grid on the neutral
    gnd_grid_id = _uid("GND_grid")
    gnd_grid = _component(
        comp_id=gnd_grid_id, comp_type="GROUND", name="GND_grid",
        x=X_GRID - 100, y=Y_PHASE_B + 80,
        parameters={},
        pins=[_pin(0, "gnd", 0, -20)],
    )
    components.append(gnd_grid)

    # Wire V_grid.N → GND_grid.gnd
    wires.append(_wire(
        wire_id=_uid("w-vgrid-n-gnd"),
        from_id=v_grid_id, from_pin=3,
        to_id=gnd_grid_id, to_pin=0,
        node_name="GND",
    ))

    # ------------------------------------------------------------------
    # Input filter inductors — L_in_{a,b,c} in series with each phase.
    # Pin layout: 1 (in) on the left, 2 (out) on the right.
    # ------------------------------------------------------------------
    L_in_ids: list[str] = []
    for phase, y_phase in (("a", Y_PHASE_A), ("b", Y_PHASE_B), ("c", Y_PHASE_C)):
        lid = _uid(f"L_in_{phase}")
        L_in_ids.append(lid)
        components.append(_component(
            comp_id=lid, comp_type="INDUCTOR", name=f"L_in_{phase}",
            x=X_LIN, y=y_phase,
            parameters={
                "inductance": 2.0e-3,
                "initial_current": 0.0,
                "enable_thermal_port": False,
            },
            pins=[_pin(0, "1", -40, 0), _pin(1, "2", 40, 0)],
        ))

    # Wire V_grid → L_in_{a,b,c}.1 — A=pin0, B=pin1, C=pin2.
    for phase_idx, lid in enumerate(L_in_ids):
        wires.append(_wire(
            wire_id=_uid(f"w-vgrid-lin-{phase_idx}"),
            from_id=v_grid_id, from_pin=phase_idx,
            to_id=lid, to_pin=0,
            node_name=f"GRID_{('a','b','c')[phase_idx].upper()}",
        ))

    # ------------------------------------------------------------------
    # Input filter caps — C_in_{a,b,c} from each filtered node to GND.
    # Pin layout: + on the left (to the phase node), - on the right
    # (towards GND). We collect the cap '-' pins onto a single shared
    # GND_filt node.
    # ------------------------------------------------------------------
    gnd_filt_id = _uid("GND_filt")
    gnd_filt = _component(
        comp_id=gnd_filt_id, comp_type="GROUND", name="GND_filt",
        x=X_CIN, y=Y_PHASE_C + 200,
        parameters={},
        pins=[_pin(0, "gnd", 0, -20)],
    )
    components.append(gnd_filt)

    C_in_ids: list[str] = []
    for phase, y_phase in (("a", Y_PHASE_A), ("b", Y_PHASE_B), ("c", Y_PHASE_C)):
        cid = _uid(f"C_in_{phase}")
        C_in_ids.append(cid)
        components.append(_component(
            comp_id=cid, comp_type="CAPACITOR", name=f"C_in_{phase}",
            x=X_CIN, y=y_phase + 60,
            parameters={
                "capacitance": 10.0e-6,
                "initial_voltage": 0.0,
                "enable_thermal_port": False,
            },
            pins=[_pin(0, "+", 0, -20), _pin(1, "-", 0, 20)],
        ))

    # Wire L_in_c.2 → C_in_c.+ — the direct L → C connection on phase c.
    # For phase a and b the connection is broken into two wires going
    # through a CURRENT_PROBE (added later) so the probe measures the
    # actual line current; emitting the direct wire here would short-
    # circuit the probe.
    wires.append(_wire(
        wire_id=_uid("w-lin-cin-c"),
        from_id=L_in_ids[2], from_pin=1,
        to_id=C_in_ids[2], to_pin=0,
        node_name="Vc_FILT",
    ))

    # Wire C_in_{a,b,c}.- → GND_filt — chained so the cap minus pins
    # all share one node (a single ground rail).
    wires.append(_wire(
        wire_id=_uid("w-cin-a-gnd"),
        from_id=C_in_ids[0], from_pin=1,
        to_id=gnd_filt_id, to_pin=0,
        node_name="GND",
    ))
    wires.append(_wire(
        wire_id=_uid("w-cin-b-gnd"),
        from_id=C_in_ids[1], from_pin=1,
        to_id=gnd_filt_id, to_pin=0,
        node_name="GND",
    ))
    wires.append(_wire(
        wire_id=_uid("w-cin-c-gnd"),
        from_id=C_in_ids[2], from_pin=1,
        to_id=gnd_filt_id, to_pin=0,
        node_name="GND",
    ))

    # ------------------------------------------------------------------
    # Voltage probes on the filtered nodes — these are the C_BLOCK's
    # in[0..2]. VOLTAGE_PROBE_GND is ground-referenced — IN is the
    # measured node, OUT is the signal output.
    # ------------------------------------------------------------------
    vprobe_in_ids: list[str] = []
    # CMC C_BLOCK input pins are at relative Y = -200, 0, 200 (200 px
    # apart) so the IN voltage probes sit at the corresponding world Y
    # to keep the L-shape wire routing horizontal-only between probe
    # OUT and C_BLOCK IN — avoids accidental geometric coincidence
    # between routing corners and other pins.
    vp_in_y = (Y_PHASE_A, Y_PHASE_B, Y_PHASE_C)
    for phase_idx, phase in enumerate(("a", "b", "c")):
        pid = _uid(f"VP_in_{phase}")
        vprobe_in_ids.append(pid)
        components.append(_component(
            comp_id=pid, comp_type="VOLTAGE_PROBE_GND", name=f"VP_in_{phase}",
            x=X_VPROBE_I + 100, y=vp_in_y[phase_idx] - 60,
            parameters={"display_name": f"V{phase}_FILT", "scale": 1.0},
            pins=[_pin(0, "IN", -20, 0), _pin(1, "OUT", 20, 0)],
        ))
        # Wire VP_in.IN to the corresponding filtered phase node.
        # We tap C_in.+ (rather than L_in.2) because the input current
        # probe (CP_in_X) inserts a 0V voltage source between
        # L_in.2 and C_in.+, splitting that line into TWO electrical
        # nodes. The C_in.+ side is the one that holds the
        # ``V{phase}_FILT`` alias the C_BLOCK reads via this probe.
        wires.append(_wire(
            wire_id=_uid(f"w-vp-in-{phase}"),
            from_id=C_in_ids[phase_idx], from_pin=0,
            to_id=pid, to_pin=0,
            node_name=f"V{phase}_FILT",
        ))

    # ------------------------------------------------------------------
    # THE STAR — CMC_SVM C_BLOCK.
    #
    # 3 inputs (signal-domain, from the voltage probes), 3 outputs
    # (electrical voltage sources driving the load phase nodes). Inline-C
    # implementation; sample_time = 50 µs (20 kHz controller); no
    # persistent state.
    # ------------------------------------------------------------------
    cblock_id = _uid("CMC_SVM")
    cblock = _component(
        comp_id=cblock_id, comp_type="C_BLOCK", name="CMC_SVM",
        x=X_CBLOCK, y=Y_PHASE_B,
        parameters={
            "n_inputs": 3,
            "n_outputs": 3,
            "implementation": "source",
            "source": "",
            "lib_path": "",
            "source_code": CMC_SVM_SOURCE,
            "extra_cflags": [],
            "sample_time": 5.0e-5,
            "n_states": 0,
            # Optional metadata that's purely cosmetic in the GUI's
            # block-properties panel; helps the user identify what each
            # input is wired to.
            "inputs": ["VP_in_a", "VP_in_b", "VP_in_c"],
        },
        pins=[
            # IN0..IN2 stacked on the left — aligned with the 3 voltage
            # probe Y positions (200 px apart) so the L-shape wire
            # routing doesn't generate intermediate corner points that
            # would accidentally land on another pin (PIN_HIT_TOLERANCE
            # is 5 px, but the union-find merges by spatial coincidence
            # across the entire wire net).
            _pin(0, "IN0", -40, -200),
            _pin(1, "IN1", -40,    0),
            _pin(2, "IN2", -40,  200),
            # OUT0..OUT2 stacked on the right at the same spacing.
            _pin(3, "OUT0",  40, -200),
            _pin(4, "OUT1",  40,    0),
            _pin(5, "OUT2",  40,  200),
        ],
    )
    components.append(cblock)

    # Wire C_BLOCK inputs from voltage probes.
    for phase_idx in range(3):
        wires.append(_wire(
            wire_id=_uid(f"w-vp-cb-{phase_idx}"),
            from_id=vprobe_in_ids[phase_idx], from_pin=1,
            to_id=cblock_id, to_pin=phase_idx,
            node_name=f"SIG_V{('a','b','c')[phase_idx]}_FILT",
        ))

    # ------------------------------------------------------------------
    # Output stage — 3 voltage probes (OUT side), 3 R, 3 L, common GND.
    # The C_BLOCK's OUT0..OUT2 are electrical nodes vA, vB, vC. Each
    # drives R_X → L_X → load neutral.
    # ------------------------------------------------------------------
    R_load_ids: list[str] = []
    L_load_ids: list[str] = []
    vprobe_out_ids: list[str] = []
    for phase_idx, phase in enumerate(("A", "B", "C")):
        y_phase = (Y_PHASE_A, Y_PHASE_B, Y_PHASE_C)[phase_idx]

        # VP_out_X — voltage probe at the C_BLOCK output (vX node).
        vp_id = _uid(f"VP_out_{phase}")
        vprobe_out_ids.append(vp_id)
        components.append(_component(
            comp_id=vp_id, comp_type="VOLTAGE_PROBE_GND", name=f"VP_out_{phase}",
            x=X_VPROBE_O, y=y_phase - 40,
            parameters={"display_name": f"v{phase}", "scale": 1.0},
            pins=[_pin(0, "IN", -20, 0), _pin(1, "OUT", 20, 0)],
        ))
        # Probe IN attaches to the C_BLOCK output node directly.
        wires.append(_wire(
            wire_id=_uid(f"w-cb-vp-{phase}"),
            from_id=cblock_id, from_pin=3 + phase_idx,
            to_id=vp_id, to_pin=0,
            node_name=f"v{phase}",
        ))

        # R_X
        rid = _uid(f"R_{phase}")
        R_load_ids.append(rid)
        components.append(_component(
            comp_id=rid, comp_type="RESISTOR", name=f"R_{phase}",
            x=X_R_LOAD, y=y_phase,
            parameters={
                "resistance": 10.0,
                "enable_thermal_port": False,
            },
            pins=[_pin(0, "1", -40, 0), _pin(1, "2", 40, 0)],
        ))
        # Wire R_X.1 to the v{phase} node (via the probe net)
        wires.append(_wire(
            wire_id=_uid(f"w-vp-r-{phase}"),
            from_id=vp_id, from_pin=0,
            to_id=rid, to_pin=0,
            node_name=f"v{phase}",
        ))

        # L_X
        lid = _uid(f"L_{phase}")
        L_load_ids.append(lid)
        components.append(_component(
            comp_id=lid, comp_type="INDUCTOR", name=f"L_{phase}",
            x=X_L_LOAD, y=y_phase,
            parameters={
                "inductance": 10.0e-3,
                "initial_current": 0.0,
                "enable_thermal_port": False,
            },
            pins=[_pin(0, "1", -40, 0), _pin(1, "2", 40, 0)],
        ))
        # R_X.2 → L_X.1: ONLY for phase C (the unprobed phase).
        # Phases A and B route through a CURRENT_PROBE added later —
        # emitting a direct wire here would short-circuit the probe.
        if phase == "C":
            wires.append(_wire(
                wire_id=_uid(f"w-r-l-{phase}"),
                from_id=rid, from_pin=1,
                to_id=lid, to_pin=0,
                node_name=f"LMID_{phase}",
            ))

    # GND_load — common return for all 3 L_X.2 pins (star load).
    gnd_load_id = _uid("GND_load")
    components.append(_component(
        comp_id=gnd_load_id, comp_type="GROUND", name="GND_load",
        x=X_NEUTRAL, y=Y_NEUTRAL,
        parameters={},
        pins=[_pin(0, "gnd", 0, -20)],
    ))
    for phase_idx, lid in enumerate(L_load_ids):
        wires.append(_wire(
            wire_id=_uid(f"w-l-neutral-{phase_idx}"),
            from_id=lid, from_pin=1,
            to_id=gnd_load_id, to_pin=0,
            node_name="GND",
        ))

    # ------------------------------------------------------------------
    # Current probes — 2 on the input filter (I through L_in_a, L_in_b)
    # and 2 on the output (I through R_A, R_B). We splice them into the
    # existing wire chains: each probe sits in series at the spot it
    # measures. CURRENT_PROBE pins: 0 = IN, 1 = OUT, 2 = MEAS (signal).
    #
    # To keep wire count low, we re-route the existing series wires:
    # instead of L_in_a.2 → C_in_a.+, we now have L_in_a.2 → CP.IN →
    # CP.OUT → C_in_a.+. The CURRENT_PROBE is wired by 2 wires (in +
    # out) plus 1 signal-domain wire to the scope.
    # ------------------------------------------------------------------

    # First, drop the wires we're going to replace.
    # (We collected wires in order; we know which ids by node name pattern.)
    # Easier approach: rebuild only the wires we care about. We never
    # added the I_L_in_a / I_L_in_b probe segments — do so now.

    # I_L_in_a / I_L_in_b : current probes on input phases a and b.
    cprobe_in_ids: list[str] = []
    for phase, y_phase in (("a", Y_PHASE_A), ("b", Y_PHASE_B)):
        cpid = _uid(f"CP_in_{phase}")
        cprobe_in_ids.append(cpid)
        components.append(_component(
            comp_id=cpid, comp_type="CURRENT_PROBE", name=f"CP_in_{phase}",
            x=X_LIN + 80, y=y_phase - 40,
            parameters={"display_name": f"I_L_in_{phase}", "scale": 1.0},
            pins=[
                _pin(0, "IN",   -20, 0),
                _pin(1, "OUT",   20, 0),
                _pin(2, "MEAS",   0, -20),
            ],
        ))
        # Splice: existing L_in.2 → C_in.+ stays valid (same electrical
        # node). The CURRENT_PROBE simply taps that wire — i.e. we wire
        # CP.IN to the L_in.2 node and CP.OUT to the C_in.+ node, leaving
        # the existing wire in place. The converter treats these as
        # parallel paths on the same node, which is mathematically
        # correct (the probe is a thru-wire in PWL) and avoids the need
        # to re-thread the original wire through the probe.
        # → Cleaner: emit two short wires that put the probe on the node.

    # Wires: each input current probe SITS IN SERIES on the
    # L_in.2 → C_in.+ path. The OUTPUT side of the probe (CP.OUT to
    # C_in.+) keeps the ``V{phase}_FILT`` alias — that's the node the
    # C_BLOCK reads. The INPUT side (L_in.2 → CP.IN) gets a different
    # alias (``L_in.2``-style) so the converter does NOT collapse the
    # two probe terminals into the same electrical node. (When two
    # wires share the same ``node_name``/``alias`` label, the
    # ``build_node_alias_map`` post-pass forces them onto the same
    # alias-keyed entry in the lowered ``Circuit``; the current-probe
    # voltage-source stamp at IN→OUT then degenerates to a 0V source
    # on the SAME node, the matrix loses a rank, and the PWL state-
    # space cache reports ``mask 0b0 N=0``.)
    for idx, (phase, cpid) in enumerate(zip(("a", "b"), cprobe_in_ids)):
        wires.append(_wire(
            wire_id=_uid(f"w-lin-cp-in-{phase}"),
            from_id=L_in_ids[idx], from_pin=1,
            to_id=cpid, to_pin=0,
            node_name=f"L_in_{phase}_OUT",
        ))
        wires.append(_wire(
            wire_id=_uid(f"w-cp-in-cin-{phase}"),
            from_id=cpid, from_pin=1,
            to_id=C_in_ids[idx], to_pin=0,
            node_name=f"V{phase}_FILT",
        ))

    # I_R_A / I_R_B : current probes on output phases A and B (in
    # series with R_A, R_B).
    cprobe_out_ids: list[str] = []
    for phase, y_phase in (("A", Y_PHASE_A), ("B", Y_PHASE_B)):
        cpid = _uid(f"CP_out_{phase}")
        cprobe_out_ids.append(cpid)
        components.append(_component(
            comp_id=cpid, comp_type="CURRENT_PROBE", name=f"CP_out_{phase}",
            x=X_R_LOAD + 80, y=y_phase - 40,
            parameters={"display_name": f"I_R_{phase}", "scale": 1.0},
            pins=[
                _pin(0, "IN",   -20, 0),
                _pin(1, "OUT",   20, 0),
                _pin(2, "MEAS",   0, -20),
            ],
        ))
        # In-series probe on the R_X.2 → L_X.1 path. Same rule as the
        # input current probes: keep the OUT side labelled ``LMID_X``
        # so the load inductor still sees the labelled net, but give
        # the IN side a distinct alias so the converter does NOT
        # short-circuit the probe to a single node.
        idx = ("A", "B").index(phase)
        wires.append(_wire(
            wire_id=_uid(f"w-r-cp-out-{phase}"),
            from_id=R_load_ids[idx], from_pin=1,
            to_id=cpid, to_pin=0,
            node_name=f"R_{phase}_OUT",
        ))
        wires.append(_wire(
            wire_id=_uid(f"w-cp-out-l-{phase}"),
            from_id=cpid, from_pin=1,
            to_id=L_load_ids[idx], to_pin=0,
            node_name=f"LMID_{phase}",
        ))

    # ------------------------------------------------------------------
    # Scopes — 2 of them, 4 channels each.
    #   Scope_input  : V(va_filt), V(vb_filt), I(L_in_a), I(L_in_b)
    #   Scope_output : V(vA),       V(vB),       I(R_A),    I(R_B)
    # ------------------------------------------------------------------
    scope_in_id = _uid("Scope_input")
    components.append(_component(
        comp_id=scope_in_id, comp_type="ELECTRICAL_SCOPE", name="Scope_input",
        x=X_SCOPE_IN, y=Y_SCOPE_IN,
        parameters={
            "channel_count": 4,
            "channels": [
                {"label": "V(va_filt)", "overlay": False},
                {"label": "V(vb_filt)", "overlay": False},
                {"label": "I(L_in_a)",  "overlay": False},
                {"label": "I(L_in_b)",  "overlay": False},
            ],
        },
        pins=[
            _pin(0, "CH1", -40, -30),
            _pin(1, "CH2", -40, -10),
            _pin(2, "CH3", -40,  10),
            _pin(3, "CH4", -40,  30),
        ],
    ))

    # Scope_input wires
    wires.append(_wire(
        wire_id=_uid("w-sc-in-vpa"),
        from_id=vprobe_in_ids[0], from_pin=1,
        to_id=scope_in_id, to_pin=0,
        node_name="SIG_Va_FILT",
    ))
    wires.append(_wire(
        wire_id=_uid("w-sc-in-vpb"),
        from_id=vprobe_in_ids[1], from_pin=1,
        to_id=scope_in_id, to_pin=1,
        node_name="SIG_Vb_FILT",
    ))
    wires.append(_wire(
        wire_id=_uid("w-sc-in-cpa"),
        from_id=cprobe_in_ids[0], from_pin=2,
        to_id=scope_in_id, to_pin=2,
        node_name="SIG_I_L_in_a",
    ))
    wires.append(_wire(
        wire_id=_uid("w-sc-in-cpb"),
        from_id=cprobe_in_ids[1], from_pin=2,
        to_id=scope_in_id, to_pin=3,
        node_name="SIG_I_L_in_b",
    ))

    scope_out_id = _uid("Scope_output")
    components.append(_component(
        comp_id=scope_out_id, comp_type="ELECTRICAL_SCOPE", name="Scope_output",
        x=X_SCOPE_OUT, y=Y_SCOPE_OUT,
        parameters={
            "channel_count": 4,
            "channels": [
                {"label": "V(vA)",   "overlay": False},
                {"label": "V(vB)",   "overlay": False},
                {"label": "I(R_A)",  "overlay": False},
                {"label": "I(R_B)",  "overlay": False},
            ],
        },
        pins=[
            _pin(0, "CH1", -40, -30),
            _pin(1, "CH2", -40, -10),
            _pin(2, "CH3", -40,  10),
            _pin(3, "CH4", -40,  30),
        ],
    ))

    # Scope_output wires
    wires.append(_wire(
        wire_id=_uid("w-sc-out-vpA"),
        from_id=vprobe_out_ids[0], from_pin=1,
        to_id=scope_out_id, to_pin=0,
        node_name="SIG_vA",
    ))
    wires.append(_wire(
        wire_id=_uid("w-sc-out-vpB"),
        from_id=vprobe_out_ids[1], from_pin=1,
        to_id=scope_out_id, to_pin=1,
        node_name="SIG_vB",
    ))
    wires.append(_wire(
        wire_id=_uid("w-sc-out-cpA"),
        from_id=cprobe_out_ids[0], from_pin=2,
        to_id=scope_out_id, to_pin=2,
        node_name="SIG_I_R_A",
    ))
    wires.append(_wire(
        wire_id=_uid("w-sc-out-cpB"),
        from_id=cprobe_out_ids[1], from_pin=2,
        to_id=scope_out_id, to_pin=3,
        node_name="SIG_I_R_B",
    ))

    # ------------------------------------------------------------------
    # Simulation settings — pulsim 1.8 schema. Engine forced to PWL
    # because the C_BLOCK refuses DSED's analytical fast-path.
    # ------------------------------------------------------------------
    sim = {
        "tstop": 0.1,
        "dt": 5.0e-6,
        "max_step": 5.0e-6,
        "tstart": 0.0,
        "abstol": 1.0e-6,
        "reltol": 1.0e-3,
        "solver": "auto",
        "step_mode": "fixed",
        "output_points": 20000,
        "enable_events": True,
        "max_step_retries": 16,
        "enable_losses": False,
        "max_iterations": 100,
        "enable_voltage_limiting": False,
        "max_voltage_step": 5.0,
        "enable_newton_lm": True,
        "dc_strategy": "auto",
        "gmin_initial": 1.0e-3,
        "gmin_final": 1.0e-12,
        "dc_source_steps": 10,
        "transient_robust_mode": True,
        "transient_auto_regularize": True,
        "thermal_ambient": 25.0,
        "thermal_include_switching_losses": True,
        "thermal_include_conduction_losses": True,
        "thermal_network": "foster",
        "thermal_policy": "loss_with_temperature_scaling",
        "thermal_default_rth": 1.0,
        "thermal_default_cth": 0.1,
        "formulation_mode": "projected_wrapper",
        "direct_formulation_fallback": True,
        # The C_BLOCK is a discrete-time controller running at 20 kHz;
        # ``control_sample_time`` must match its ``sample_time``.
        "control_mode": "discrete",
        "control_sample_time": 5.0e-5,
        "ac_f_start": 1.0,
        "ac_f_stop": 1.0e6,
        "ac_points_per_decade": 10,
        "ac_anchor_mode": "auto",
        "ac_sweep_scale": "decade",
        "ac_injection_node": "",
        "ac_measurement_node": "",
        "averaged_options": None,
        # pulsim 1.6+ engine selector — PWL only (DSED can't extract LTI
        # state-space for an inline-C C_BLOCK).
        "engine": "pwl",
        "dsed_rtol": 1.0e-6,
        "dsed_atol": 1.0e-9,
        "dsed_dt_init": 1.0e-9,
        "dsed_integrator": "auto",
        "dsed_stiffness_threshold": 10.0,
        "dsed_h_bdf2": 1.0e-6,
        "start_from_dc_op": False,
    }

    # ------------------------------------------------------------------
    # Route every wire's segments. ``build_node_map`` needs each wire
    # to have at least one segment whose endpoints touch the connected
    # pins — without that, the union-find loses the connection between
    # the pins on each end and each component ends up on its own
    # singleton net. We L-shape every wire from start pin → end pin.
    # ------------------------------------------------------------------
    comp_by_id = {c["id"]: c for c in components}
    for wire in wires:
        _route_wire_segments(wire, comp_by_id)

    now = datetime.now().isoformat(timespec="seconds")
    project = {
        "version": "1.0",
        "name": (
            "24 CMC + Casadei-Serra SVM (inline-C C_BLOCK) — 415 V/60 Hz "
            "→ 25 Hz AC-AC, q=0.6, 20 kHz controller, pulsim 1.8 path B"
        ),
        "created": now,
        "modified": now,
        "active_circuit": "main",
        "simulation_settings": sim,
        "circuits": {
            "main": {
                "name": "main",
                "components": components,
                "wires": wires,
            },
        },
        "subcircuits": {},
        "scope_windows": {},
        "scope_workspace_state": {},
    }
    return project


def main() -> None:
    project = build()
    DST.write_text(json.dumps(project, indent=2))
    circ = project["circuits"]["main"]
    print(f"Wrote {DST.relative_to(REPO)}")
    print(f"  components:  {len(circ['components'])}")
    print(f"  wires:       {len(circ['wires'])}")
    types: dict[str, int] = {}
    for c in circ["components"]:
        types[c["type"]] = types.get(c["type"], 0) + 1
    for t, n in sorted(types.items()):
        print(f"    {t}: {n}")


if __name__ == "__main__":
    main()
