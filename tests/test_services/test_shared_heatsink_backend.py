"""Tests for the backend ``_compute_shared_heatsink_steady_state`` helper.

The helper takes the per-device average powers we already computed in
``_compute_per_device_electrothermal`` and runs the coupled
shared-heatsink steady-state through ``pulsim.thermal.shared_heatsink_steady_state``.

What we pin here:

  1. **Coupling math.** For 2 devices with known R_jc, R_cs, R_sa, and
     powers, the analytic answer is::

         T_sink   = T_amb + R_sa · ΣP
         T_case_i = T_sink + R_cs_i · P_i
         T_j_i    = T_case_i + R_jc_i · P_i

     The whole point of using a shared-heatsink model is that the
     ``Σ P`` term couples every device to every other — adding a
     hotter device next to a cooler one raises *both*. This test
     parameterises a few combinations and checks numbers to 0.1 °C.

  2. **Fallback when no HEATSINK was placed.** Empty descriptor list →
     empty result list → the legacy per-device-isolated thermal path
     continues to apply.

  3. **Missing-power devices are excluded.** A device whose name isn't
     in ``electrothermal_rows`` (e.g. a passive component without a
     loss model) is dropped from the descriptor with no error so the
     remaining devices still get coupled results.

  4. **CSV → FosterStage helper.** Empty CSVs return []; matched
     R/C lengths produce stages; negative / zero values reject the
     whole CSV (the caller falls back to single-RC).
"""
from __future__ import annotations

import pulsim as p
import pytest

from pulsimgui.services.backend_adapter import PulsimBackend


def _backend() -> PulsimBackend:
    """A bare PulsimBackend instance — we only call pure helpers, no
    constructor work is required."""
    backend = PulsimBackend.__new__(PulsimBackend)
    backend._module = p  # type: ignore[attr-defined]
    return backend


class _StubCircuit:
    """Drop-in for the GUI Circuit shim that just carries the
    ``shared_heatsink_descriptors`` attribute."""

    def __init__(self, descriptors: list[dict]) -> None:
        self.shared_heatsink_descriptors = descriptors


# ---------------------------------------------------------------------------
# Coupling math (the headline test)
# ---------------------------------------------------------------------------


def test_two_devices_share_R_th_sa_via_sum_of_powers() -> None:
    """Closed-form check of the SharedHeatsink steady-state network.

    Setup: Q1 dissipates 5 W, Q2 dissipates 10 W. Both share a
    R_sa = 3 K/W heatsink with 0.5 K/W TIM each. Q1 has R_jc = 1.5 K/W,
    Q2 has R_jc = 1.0 K/W. T_amb = 40 °C.

    Analytic:
        ΣP       = 15 W
        T_sink   = 40 + 3 · 15        = 85 °C
        T_case_1 = 85 + 0.5 · 5       = 87.5 °C
        T_j_1    = 87.5 + 1.5 · 5     = 95 °C
        T_case_2 = 85 + 0.5 · 10      = 90 °C
        T_j_2    = 90 + 1.0 · 10      = 100 °C
    """
    desc = {
        "name": "HS",
        "R_th_sink_to_amb_K_per_W": 3.0,
        "C_th_sink_J_per_K": 0.0,
        "T_amb_C": 40.0,
        "devices": [
            {
                "device_name": "Q1", "device_type": "MOSFET_N",
                "R_th_case_to_sink_K_per_W": 0.5,
                "thermal_rth_stages": "",  # use single-RC fallback
                "thermal_cth_stages": "",
                "thermal_rth_K_per_W": 1.5,
                "thermal_cth_J_per_K": 0.075,
            },
            {
                "device_name": "Q2", "device_type": "MOSFET_N",
                "R_th_case_to_sink_K_per_W": 0.5,
                "thermal_rth_stages": "", "thermal_cth_stages": "",
                "thermal_rth_K_per_W": 1.0,
                "thermal_cth_J_per_K": 0.05,
            },
        ],
    }
    rows = [
        {"component_name": "Q1", "conduction": {"P_avg_W": 5.0}},
        {"component_name": "Q2", "conduction": {"P_avg_W": 10.0}},
    ]
    out = _backend()._compute_shared_heatsink_steady_state(
        circuit=_StubCircuit([desc]),
        electrothermal_rows=rows,
    )
    assert len(out) == 1
    assert out[0]["name"] == "HS"
    assert out[0]["T_sink_C"] == pytest.approx(85.0, abs=0.1)
    assert out[0]["devices"]["Q1"] == pytest.approx(95.0, abs=0.1)
    assert out[0]["devices"]["Q2"] == pytest.approx(100.0, abs=0.1)
    # Powers echoed back unchanged (lets the GUI display them too).
    assert out[0]["powers_W"] == {"Q1": 5.0, "Q2": 10.0}


def test_loss_subkeys_are_summed_into_total_power() -> None:
    """``conduction`` + ``turn_on`` + ``turn_off`` each contribute to
    the device's average power. Skipping any one of them would
    under-predict T_j."""
    desc = {
        "name": "HS", "R_th_sink_to_amb_K_per_W": 1.0,
        "C_th_sink_J_per_K": 0.0, "T_amb_C": 25.0,
        "devices": [{
            "device_name": "Q1", "device_type": "MOSFET_N",
            "R_th_case_to_sink_K_per_W": 0.0,
            "thermal_rth_stages": "", "thermal_cth_stages": "",
            "thermal_rth_K_per_W": 1.0, "thermal_cth_J_per_K": 0.1,
        }],
    }
    rows = [{
        "component_name": "Q1",
        "conduction": {"P_avg_W": 3.0},
        "turn_on":    {"P_avg_W": 2.0},
        "turn_off":   {"P_avg_W": 1.0},
    }]
    out = _backend()._compute_shared_heatsink_steady_state(
        circuit=_StubCircuit([desc]),
        electrothermal_rows=rows,
    )
    # ΣP = 6 W → T_sink = 25 + 6 = 31; T_j = 31 + 1·6 = 37 °C.
    assert out[0]["devices"]["Q1"] == pytest.approx(37.0, abs=0.1)
    assert out[0]["powers_W"]["Q1"] == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_no_descriptors_yields_empty_result() -> None:
    """No HEATSINK in the schematic → the legacy per-device-isolated
    thermal pipeline owns the result, helper returns []."""
    out = _backend()._compute_shared_heatsink_steady_state(
        circuit=_StubCircuit([]),
        electrothermal_rows=[
            {"component_name": "Q1", "conduction": {"P_avg_W": 5.0}}
        ],
    )
    assert out == []


def test_devices_without_power_entries_are_silently_dropped() -> None:
    """A device whose name isn't in ``electrothermal_rows`` (no loss
    model recorded — e.g. a passive component that the user wired to
    the heatsink anyway) is excluded from the solve. The remaining
    devices still get coupled results — the absent one doesn't poison
    the sink with a 0 W placeholder."""
    desc = {
        "name": "HS", "R_th_sink_to_amb_K_per_W": 2.0,
        "C_th_sink_J_per_K": 0.0, "T_amb_C": 25.0,
        "devices": [
            {
                "device_name": "Q1", "device_type": "MOSFET_N",
                "R_th_case_to_sink_K_per_W": 0.0,
                "thermal_rth_stages": "", "thermal_cth_stages": "",
                "thermal_rth_K_per_W": 1.0, "thermal_cth_J_per_K": 0.1,
            },
            {
                "device_name": "R_filter", "device_type": "RESISTOR",
                "R_th_case_to_sink_K_per_W": 0.0,
                "thermal_rth_stages": "", "thermal_cth_stages": "",
                "thermal_rth_K_per_W": 1.0, "thermal_cth_J_per_K": 0.1,
            },
        ],
    }
    rows = [{"component_name": "Q1", "conduction": {"P_avg_W": 5.0}}]
    out = _backend()._compute_shared_heatsink_steady_state(
        circuit=_StubCircuit([desc]),
        electrothermal_rows=rows,
    )
    assert out[0]["devices"] == {"Q1": pytest.approx(40.0, abs=0.1)}
    # R_filter is not in the result at all — not as a 0 W placeholder.
    assert "R_filter" not in out[0]["devices"]


# ---------------------------------------------------------------------------
# Foster-CSV helper
# ---------------------------------------------------------------------------


def test_foster_csv_helper_returns_paired_stages() -> None:
    """3-stage CSV pair → 3 ``FosterStage`` with ``tau = R · C``."""
    stages = PulsimBackend._foster_stages_from_csv(
        "0.2, 0.4, 0.3", "0.005, 0.025, 0.167",
    )
    assert len(stages) == 3
    expected_taus = [0.2 * 0.005, 0.4 * 0.025, 0.3 * 0.167]
    for stage, tau_expected in zip(stages, expected_taus):
        assert stage.tau_s == pytest.approx(tau_expected, rel=1e-9)


def test_foster_csv_helper_returns_empty_on_blank_input() -> None:
    """Blank CSV (or only one side blank) → []; caller falls back to
    the single-RC stage."""
    assert PulsimBackend._foster_stages_from_csv("", "0.005, 0.025") == []
    assert PulsimBackend._foster_stages_from_csv("0.2, 0.4", "") == []
    assert PulsimBackend._foster_stages_from_csv("", "") == []


def test_foster_csv_helper_rejects_mismatched_lengths() -> None:
    """A 3-R, 2-C pair is malformed input — fall back rather than
    silently dropping the third stage."""
    assert PulsimBackend._foster_stages_from_csv(
        "0.2, 0.4, 0.3", "0.005, 0.025",
    ) == []


def test_foster_csv_helper_rejects_non_positive_values() -> None:
    """Negative R or C is non-physical (and pulsim would reject it);
    fall back to the single-RC path instead of throwing."""
    assert PulsimBackend._foster_stages_from_csv(
        "0.2, -0.4, 0.3", "0.005, 0.025, 0.167",
    ) == []
    assert PulsimBackend._foster_stages_from_csv(
        "0.2, 0.4, 0.3", "0.005, 0.0, 0.167",
    ) == []
