"""Pin the V_AC symmetry of a floating single-phase Graetz bridge built
via the GUI converter — mirror of the pulsim kernel regression test
(PR #85 upstream).

Backstory
---------

Earlier in the pulsim-1.7 thermal session the user reported an
"asymmetric V_AC, mean ≈ −205 V" on ex 20 (PFC drive) when the AC
input was floating (no GROUND on V1.−). The pulsim agent investigated
upstream and concluded:

  1. **The kernel bug does NOT reproduce on pulsim ≥ 1.6.6.** The
     auto-LM (Levenberg-Marquardt) regularisation added in 1.6.5
     handles exactly the rank-deficient switch-mask Jacobian the old
     bug pivoted on. All variants — bare bridge, realistic g_off
     (1e-12), forward drops, cold start, ghost 1 GΩ resistor,
     current-probe in series — produce ``V_AC = [-311, +311], mean ≈
     0`` on an integer-cycle window.

  2. **The "mean −205 V" was a measurement-window artifact.** The
     user's window (0.04 → 0.08 s) is 2.4 cycles at 60 Hz, not an
     integer number of cycles, so the mean of even a perfectly
     symmetric sine ≠ 0. Repro confirmed: a bare 311 V sine over the
     same window shows the same −23 V "offset", proving the bridge is
     innocent.

  3. **V(ac_p) and V(ac_n) individually ARE one-sided.** Each
     terminal is clamped near 0 V in the opposite half-cycle by the
     bottom-side diodes; the common-mode floats at +Vpeak/2 ≈ +155 V.
     That's correct bridge physics — only the *differential*
     ``V(ac_p) − V(ac_n)`` must be symmetric, and it is.

These tests pin the GOOD behaviour from the GUI side so any future
regression in:

  * the converter's diode-orientation / pin-naming for
    ``SINGLE_PHASE_DIODE_BRIDGE``;
  * the ``_inject_floating_node_helpers`` ghost-resistor pass (the
    suspect the kernel agent flagged as the chip-of-task);
  * the v0-compat shim's sine waveform translation;
  * any future "auto-add GROUND when V1.− is dangling" heuristic;

surfaces here BEFORE users hit it on ex 20.

The kernel side already has its own pin (8 tests upstream); this file
covers the GUI-converter pipeline specifically.
"""
from __future__ import annotations

import math

import numpy as np
import pulsim as ps
import pytest

from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _floating_bridge_components(
    *,
    add_ground: bool = True,
    v_amplitude: float = 311.0,
    f_grid: float = 60.0,
    cbus_uf: float = 470e-6,
    rload_ohm: float = 700.0,
    g_on: float = 1e3,
    g_off: float = 1e-9,
    v_forward: float = 0.0,
) -> tuple[list[dict], dict[str, list[str]]]:
    """Build a single-phase floating-bridge schematic, parametrised
    for the variants the kernel agent's bisection covered.

    Topology::

        V1(sine) AC ── ac_p ──┬──── BR1.AC1
                              │
                      ac_n ──┴──── BR1.AC2
                                    BR1.DC+ ── dc_p ── Cbus, Rload
                                    BR1.DC- ── GND (0)
    """
    components: list[dict] = [
        {
            "id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
            "parameters": {
                "waveform": {
                    "type": "sine",
                    "amplitude": v_amplitude,
                    "frequency": f_grid,
                    "phase": 0.0,
                    "offset": 0.0,
                },
            },
            "pins": [
                {"index": 0, "name": "+"},
                {"index": 1, "name": "-"},
            ],
        },
        {
            "id": "br1", "type": "SINGLE_PHASE_DIODE_BRIDGE", "name": "BR1",
            "parameters": {
                "g_on": g_on, "g_off": g_off, "v_forward": v_forward,
            },
            "pins": [
                {"index": 0, "name": "AC1"},
                {"index": 1, "name": "AC2"},
                {"index": 2, "name": "DC+"},
                {"index": 3, "name": "DC-"},
            ],
        },
        {
            "id": "c1", "type": "CAPACITOR", "name": "Cbus",
            "parameters": {
                "capacitance": cbus_uf, "initial_voltage": 310.0,
            },
            "pins": [
                {"index": 0, "name": "+"}, {"index": 1, "name": "-"},
            ],
        },
        {
            "id": "r1", "type": "RESISTOR", "name": "Rload",
            "parameters": {"resistance": rload_ohm},
            "pins": [
                {"index": 0, "name": "1"}, {"index": 1, "name": "2"},
            ],
        },
    ]
    node_map: dict[str, list[str]] = {
        "v1": ["ac_p", "ac_n"],
        "br1": ["ac_p", "ac_n", "dc_p", "0"],
        "c1":  ["dc_p", "0"],
        "r1":  ["dc_p", "0"],
    }
    if add_ground:
        components.append({
            "id": "g", "type": "GROUND", "name": "GND",
            "parameters": {},
            "pins": [{"index": 0, "name": "gnd"}],
        })
        node_map["g"] = ["0"]
    return components, node_map


def _simulate(components: list[dict], node_map: dict[str, list[str]]):
    """Build via the GUI converter, simulate at 5 µs / 100 ms, return
    ``(times, v_acp, v_acn, v_ac_diff)`` as NumPy arrays."""
    conv = CircuitConverter(make_compat_module(ps))
    circuit = conv.build({"components": components, "node_map": node_map})
    builder = getattr(circuit, "builder", circuit)
    res = ps.simulate(builder, 0.1, dt=5e-6, engine="pwl")
    t = np.asarray(res.times)
    v_acp = np.asarray(res.v("Nac_p"))
    v_acn = np.asarray(res.v("Nac_n"))
    return t, v_acp, v_acn, v_acp - v_acn


def _integer_cycle_mask(t: np.ndarray, f_grid: float = 60.0, n_cycles: int = 4) -> np.ndarray:
    """The window subtlety that confused the original report.

    A 60 Hz sine over a NON-integer number of cycles has a non-zero
    mean by construction. Tests that compute mean/PF over the wrong
    window will flag a perfectly correct sim as broken. Use this
    helper for every mean / PF / DC-offset assertion — last
    ``n_cycles`` full periods of the steady-state portion.
    """
    return t >= t[-1] - n_cycles / f_grid


# ---------------------------------------------------------------------------
# 1. Differential V_AC is the contract — must be symmetric ±Vpeak
# ---------------------------------------------------------------------------


def test_floating_bridge_v_ac_differential_is_symmetric_on_integer_window() -> None:
    """The headline assertion. Floating bridge + 311 V sine → the
    differential ``V(ac_p) − V(ac_n)`` must track the source within
    diode drops, mean ≈ 0 V on any integer-cycle window, peaks at
    ±311 V."""
    components, node_map = _floating_bridge_components()
    t, _, _, v_ac = _simulate(components, node_map)
    mask = _integer_cycle_mask(t)
    v_window = v_ac[mask]

    # Peak-to-peak ≈ 2 × 311 V (diode drops are 0 V in this variant).
    assert v_window.max() == pytest.approx(311.0, abs=1.0)
    assert v_window.min() == pytest.approx(-311.0, abs=1.0)
    # Mean of a symmetric sine over integer cycles is ~0; tolerance
    # 1 V swallows the finite-dt sampling noise.
    assert abs(v_window.mean()) < 1.0, (
        f"V_AC mean {v_window.mean():+.3f} V — bridge introduces an "
        f"offset. The kernel bug the agent investigated was a >100 V "
        f"asymmetry; any value > 1 V here is a regression."
    )
    # RMS ≈ Vpeak / √2 = 219.91 V (analytic).
    rms = float(np.sqrt(np.mean(v_window**2)))
    assert rms == pytest.approx(219.91, rel=2e-3)


def test_v_ac_tracks_source_sine_within_diode_drop_band() -> None:
    """Stronger pin: the differential V_AC tracks the source sine
    analytically (within the diode forward-drop band) at every
    sample, not just the windowed statistics."""
    components, node_map = _floating_bridge_components()
    t, _, _, v_ac = _simulate(components, node_map)
    # Analytic source: V_source(t) = 311 · sin(2π·60·t)
    v_source = 311.0 * np.sin(2.0 * math.pi * 60.0 * t)
    # Integer-cycle window so transient initialisation is excluded.
    mask = _integer_cycle_mask(t)
    deviation = np.abs(v_ac[mask] - v_source[mask])
    # Drops from g_on=1e3 + bus charging dynamics — 2 V envelope is
    # comfortable for a v_forward=0 bridge. The kernel agent's pin
    # uses the same envelope.
    assert float(deviation.max()) < 2.0, (
        f"max |V_AC − V_source| = {deviation.max():.3f} V — the "
        f"bridge is introducing more than a diode drop's worth of "
        f"deviation from the source."
    )


# ---------------------------------------------------------------------------
# 2. Individual node voltages ARE one-sided — that's correct physics
# ---------------------------------------------------------------------------


def test_individual_ac_nodes_are_one_sided_by_bridge_clamping() -> None:
    """V(ac_p) and V(ac_n) individually swing between ≈ 0 V and ≈
    +Vpeak. Each AC terminal is clamped to ground potential by the
    bottom-side diode in the opposite half-cycle while the top-side
    diode drives the bus during its own half-cycle.

    This LOOKS like the bug but isn't — the user originally measured
    V(ac_p) alone and saw [0, 311] / mean +155 instead of the
    expected [-311, +311] / mean 0. The fix is to measure the
    differential, NOT to "fix" the simulator.
    """
    components, node_map = _floating_bridge_components()
    t, v_acp, v_acn, _ = _simulate(components, node_map)
    mask = _integer_cycle_mask(t)

    # Each terminal swings from "clamped near 0 V" to "near +Vpeak".
    # Lower bound floor is set by the diode g_off leakage (negligible)
    # plus the diode forward drop; we leave a 5 V envelope.
    assert -5.0 < v_acp[mask].min() < 5.0
    assert v_acp[mask].max() == pytest.approx(311.0, abs=2.0)
    assert -5.0 < v_acn[mask].min() < 5.0
    assert v_acn[mask].max() == pytest.approx(311.0, abs=2.0)

    # Common-mode (the average of the two terminals) rides up at
    # +Vpeak / 2 ≈ +155 V — that's where the floating bridge floats.
    common = (v_acp[mask] + v_acn[mask]) / 2.0
    assert common.mean() == pytest.approx(311.0 / 2.0, abs=10.0)


# ---------------------------------------------------------------------------
# 3. Pitfall: non-integer cycle windows make a symmetric sine LOOK offset
# ---------------------------------------------------------------------------


def test_non_integer_cycle_window_makes_symmetric_sine_look_offset() -> None:
    """The single root-cause of the user's confusion in the original
    report. A 2.4-cycle window over a perfectly symmetric 60 Hz sine
    gives mean ≈ −23 V — purely a windowing artefact, NOT a bug.

    This test exists to make sure future contributors don't waste
    time chasing the kernel when they see a non-zero mean in the
    scope. If this test EVER fails because the windowed mean came
    out close to zero, the test data is no longer representative of
    the original bug report — flag it and re-derive the threshold.
    """
    components, node_map = _floating_bridge_components()
    t, _, _, v_ac = _simulate(components, node_map)
    # Mimic the bad window from the original report: 0.04 → 0.08 s
    # is 2.4 cycles at 60 Hz.
    bad_window = (t >= 0.04) & (t < 0.08)
    assert bad_window.any()
    bad_mean = float(v_ac[bad_window].mean())
    # The bad-window mean SHOULD be far from zero — that's the whole
    # point. > 5 V is comfortable above any honest sim noise.
    assert abs(bad_mean) > 5.0, (
        f"bad-window mean = {bad_mean:+.2f} V; the 2.4-cycle artefact "
        f"vanished — the test data no longer reproduces the original "
        f"measurement pitfall, so this test is no longer useful as a "
        f"regression guard. Re-derive the threshold or pick a longer "
        f"non-integer span."
    )


# ---------------------------------------------------------------------------
# 4. Parametric variants the kernel agent walked — all must stay symmetric
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("g_off", [1e-9, 1e-12])
@pytest.mark.parametrize("v_forward", [0.0, 0.7])
@pytest.mark.parametrize("cbus_uf", [220e-6, 470e-6, 1000e-6])
def test_v_ac_symmetric_across_parametric_variants(
    g_off: float, v_forward: float, cbus_uf: float,
) -> None:
    """Sweep the kernel agent's bisection axes — every variant must
    still report a symmetric V_AC under the GUI converter. This catches
    any new regression that's parameter-sensitive (e.g. a switch-mask
    Jacobian rank issue that only fires at certain g_off ranges)."""
    components, node_map = _floating_bridge_components(
        g_off=g_off, v_forward=v_forward, cbus_uf=cbus_uf,
    )
    t, _, _, v_ac = _simulate(components, node_map)
    mask = _integer_cycle_mask(t)
    # Forward drop drags the peak inward by ~v_forward per half cycle.
    # 2 V envelope is comfortable for v_forward up to 0.7.
    peak_target = 311.0 - v_forward
    assert v_ac[mask].max() == pytest.approx(peak_target, abs=2.0)
    assert v_ac[mask].min() == pytest.approx(-peak_target, abs=2.0)
    assert abs(v_ac[mask].mean()) < 1.0


# ---------------------------------------------------------------------------
# 5. Helper sanity: integer-cycle mask gives a coherent window
# ---------------------------------------------------------------------------


def test_integer_cycle_mask_picks_a_coherent_window_size() -> None:
    """Sanity: the helper picks N integer cycles' worth of samples on
    a 5 µs timestep — pin this so a future change to the sim length /
    dt in the test builder doesn't silently shorten or split the
    window."""
    components, node_map = _floating_bridge_components()
    t, *_ = _simulate(components, node_map)
    mask = _integer_cycle_mask(t, f_grid=60.0, n_cycles=4)
    # 4 cycles at 60 Hz = 66.67 ms ≈ 13_333 samples at dt=5 µs.
    expected = round(4.0 / 60.0 / 5e-6)
    actual = int(mask.sum())
    # Tolerance ±1 — the sample at t = t_end - 4/60 may land on
    # either side of the boundary depending on the solver's adaptive
    # step pacing.
    assert abs(actual - expected) <= 1
