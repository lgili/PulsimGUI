"""Regression test: the current-probe ``result.i()`` path is GENERIC.

Any user-placed CURRENT_PROBE — at any position in the schematic,
with any user-chosen name — must land its branch current in
``result.signals[<probe_name>]`` after a transient run, without
hard-coding any particular probe name.

This test was added after a user concern that the PFC ex 20 fix
might have been specific to the ``I_L`` probe. It builds a tiny
synthetic AC circuit with TWO probes carrying arbitrary names at
DIFFERENT positions (one on the line side, one on the resistor's
return path) and verifies both currents come through.
"""
from __future__ import annotations

import uuid

import numpy as np
import pulsim as ps

from pulsimgui.services.backend_adapter import (
    BackendCallbacks,
    BackendInfo,
    PulsimBackend,
)
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.services.simulation_service import SimulationSettings


def _cid() -> str:
    return str(uuid.uuid4())


def test_two_user_named_current_probes_both_publish_via_result_i() -> None:
    """Two probes at different schematic positions, both must show up
    in ``result.signals`` keyed by their user-chosen names, with peaks
    matching the analytic AC RMS = V_pk/R/√2."""
    V1, R1, IP_AC, IP_R, GND = (_cid() for _ in range(5))
    comps = [
        {"id": V1, "type": "VOLTAGE_SOURCE", "name": "Vsource",
         "parameters": {
             "waveform": {"type": "sine", "amplitude": 100.0, "frequency": 100.0}
         },
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        # Probe #1: between V1.+ and R1.1 — uses a user-invented name.
        {"id": IP_AC, "type": "CURRENT_PROBE", "name": "I_line_user",
         "parameters": {},
         "pins": [{"index": 0, "name": "IN"},
                  {"index": 1, "name": "OUT"},
                  {"index": 2, "name": "MEAS"}]},
        {"id": R1, "type": "RESISTOR", "name": "R1",
         "parameters": {"resistance": 10.0},
         "pins": [{"index": 0, "name": "1"}, {"index": 1, "name": "2"}]},
        # Probe #2: between R1.2 and GND — different position, different
        # user-invented name. Must ALSO be picked up.
        {"id": IP_R, "type": "CURRENT_PROBE", "name": "I_R_other_probe",
         "parameters": {},
         "pins": [{"index": 0, "name": "IN"},
                  {"index": 1, "name": "OUT"},
                  {"index": 2, "name": "MEAS"}]},
        {"id": GND, "type": "GROUND", "name": "GND",
         "parameters": {}, "pins": [{"index": 0, "name": "gnd"}]},
    ]
    node_map = {
        V1:    ["Vplus", "0"],
        IP_AC: ["Vplus", "Rin", ""],
        R1:    ["Rin", "Rout"],
        IP_R:  ["Rout", "0", ""],
        GND:   ["0"],
    }

    settings = SimulationSettings(t_start=0.0, t_stop=0.020)
    settings.dt = 5e-6
    settings.max_step = 5e-6
    settings.step_mode = "fixed"

    backend = PulsimBackend(
        module=make_compat_module(ps),
        info=BackendInfo(
            identifier="pulsim",
            name="pulsim",
            version="1.6.5",
            status="available",
            capabilities={"transient"},
        ),
    )
    cbs = BackendCallbacks(
        progress=lambda p, m: None,
        data_point=lambda t, s: None,
        check_cancelled=lambda: False,
        wait_if_paused=lambda: None,
    )
    result = backend.run_transient(
        {"components": comps, "node_map": node_map}, settings, cbs,
    )

    assert result.error_message == ""

    # Both user-chosen names land in result.signals.
    assert "I_line_user" in result.signals, (
        "user-named current probe missing from result.signals — the "
        "result.i() path is no longer generic"
    )
    assert "I_R_other_probe" in result.signals, (
        "second user-named probe missing — only one probe published"
    )

    i_line = np.asarray(result.signals["I_line_user"])
    i_r = np.asarray(result.signals["I_R_other_probe"])

    # Analytic AC RMS for V_pk=100, R=10 (single resistor in series with
    # two 0 V sense sources): I_rms = 100/(10·√2) ≈ 7.07 A.
    # Skip the first 100 samples to drop the initial-condition transient.
    rms_line = float(np.sqrt(np.mean(i_line[100:] ** 2)))
    rms_r = float(np.sqrt(np.mean(i_r[100:] ** 2)))
    assert 6.5 < rms_line < 7.5, f"I_line_user RMS = {rms_line:.3g} A"
    assert 6.5 < rms_r < 7.5, f"I_R_other_probe RMS = {rms_r:.3g} A"
    # Same series branch → same current.
    assert np.allclose(i_line, i_r, atol=1e-6), (
        "two probes on the same series branch should report the same "
        "current — backend or converter is mis-routing one of them"
    )

    # Telemetry confirms the modern ``result.i()`` path served BOTH.
    repaired = result.statistics.get("virtual_probe_repaired_channels") or []
    assert "I_line_user:result.i" in repaired
    assert "I_R_other_probe:result.i" in repaired
