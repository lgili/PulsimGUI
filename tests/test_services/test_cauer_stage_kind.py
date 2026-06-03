"""Tests for the per-device Cauer / Foster topology toggle (pulsim 1.7
``CauerStage`` alternative to ``FosterStage``).

What we pin here:

  1. **Helper builds the right class.** ``_foster_stages_from_csv``
     with ``kind="foster"`` produces ``FosterStage`` objects whose
     ``τ_s = R · C``; with ``kind="cauer"`` produces ``CauerStage``
     objects carrying ``R + C`` directly. Both topologies are valid
     inputs to ``HeatsinkDevice``.

  2. **Default is foster.** Omitting ``kind`` (or passing an unknown
     string) falls back to Foster so existing schematics behave
     bit-for-bit as before.

  3. **Single-RC fallback respects the kind too.** A device whose CSV
     pair is blank gets a one-stage build via
     ``_foster_stages_from_single_rc``; that stage must match the
     selected topology.

  4. **Converter forwards the kind from device params into the
     descriptor.** Bench-mark the end-to-end wire so the backend can
     trust ``descriptor["devices"][i]["thermal_stage_kind"]``.

  5. **Coupled steady-state result is numerically equivalent.**
     Foster and Cauer ladders with the same R, C pairs produce the
     SAME steady-state temperatures (only the transient shape differs
     — and ``shared_heatsink_steady_state`` operates at DC where the
     two topologies share the trivial Σ R_i answer). This is a sanity
     check that the kind toggle doesn't accidentally distort the
     thermal stack at steady state.
"""
from __future__ import annotations

import pulsim as p
import pulsim.thermal as pt
import pytest

from pulsimgui.services.backend_adapter import PulsimBackend
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _backend() -> PulsimBackend:
    backend = PulsimBackend.__new__(PulsimBackend)
    backend._module = p  # type: ignore[attr-defined]
    return backend


class _StubCircuit:
    def __init__(self, descriptors: list[dict]) -> None:
        self.shared_heatsink_descriptors = descriptors


# ---------------------------------------------------------------------------
# Helper directly: kind selects the pulsim class
# ---------------------------------------------------------------------------


def test_foster_stages_from_csv_default_kind_is_foster() -> None:
    """No ``kind`` argument → FosterStage with ``tau = R·C``. Keeps
    every existing schematic byte-identical when the new field isn't
    set."""
    stages = PulsimBackend._foster_stages_from_csv(
        "0.5, 1.0", "0.1, 0.2",
    )
    assert len(stages) == 2
    for stage in stages:
        assert isinstance(stage, pt.FosterStage)
    # tau = R · C
    assert stages[0].tau_s == pytest.approx(0.5 * 0.1)
    assert stages[1].tau_s == pytest.approx(1.0 * 0.2)


def test_foster_stages_from_csv_cauer_emits_cauer_stages() -> None:
    """``kind="cauer"`` → CauerStage with R and C carried verbatim,
    NO tau computation."""
    stages = PulsimBackend._foster_stages_from_csv(
        "0.5, 1.0", "0.1, 0.2", kind="cauer",
    )
    assert len(stages) == 2
    for stage in stages:
        assert isinstance(stage, pt.CauerStage)
    assert stages[0].R_th_K_per_W == pytest.approx(0.5)
    assert stages[0].C_th_J_per_K == pytest.approx(0.1)
    assert stages[1].R_th_K_per_W == pytest.approx(1.0)
    assert stages[1].C_th_J_per_K == pytest.approx(0.2)


def test_foster_stages_from_csv_unknown_kind_falls_back_to_foster() -> None:
    """A garbled kind string ("cauer-ish", "", None-as-string) must
    not crash — fall back to Foster so the user sees *some* result
    rather than an empty stack."""
    stages_garbage = PulsimBackend._foster_stages_from_csv(
        "0.5", "0.1", kind="cauer-ish",
    )
    stages_empty = PulsimBackend._foster_stages_from_csv(
        "0.5", "0.1", kind="",
    )
    for stages in (stages_garbage, stages_empty):
        assert len(stages) == 1
        assert isinstance(stages[0], pt.FosterStage)


def test_single_rc_fallback_respects_kind() -> None:
    """When the multi-stage CSVs are blank, the backend builds a
    single stage from the legacy ``thermal_rth`` / ``thermal_cth``
    fields. That fallback must also honour the kind toggle."""
    foster = PulsimBackend._foster_stages_from_single_rc(1.5, 0.075)
    assert len(foster) == 1
    assert isinstance(foster[0], pt.FosterStage)
    assert foster[0].tau_s == pytest.approx(1.5 * 0.075)

    cauer = PulsimBackend._foster_stages_from_single_rc(1.5, 0.075, kind="cauer")
    assert len(cauer) == 1
    assert isinstance(cauer[0], pt.CauerStage)
    assert cauer[0].R_th_K_per_W == pytest.approx(1.5)
    assert cauer[0].C_th_J_per_K == pytest.approx(0.075)


# ---------------------------------------------------------------------------
# Converter forwards the per-device kind into the descriptor
# ---------------------------------------------------------------------------


def _mosfet_dict(
    comp_id: str,
    *,
    name: str = "Q1",
    kind: str = "foster",
) -> dict:
    return {
        "id": comp_id, "type": "MOSFET_N", "name": name,
        "parameters": {
            "is_nmos": True, "R_on": 0.05, "v_th": 3.0,
            "enable_thermal_port": True,
            "thermal_rth": 1.5, "thermal_cth": 0.075,
            "thermal_rth_stages": "0.5, 1.0",
            "thermal_cth_stages": "0.1, 0.2",
            "thermal_stage_kind": kind,
        },
        "pins": [
            {"index": 0, "name": "D"}, {"index": 1, "name": "G"},
            {"index": 2, "name": "S"}, {"index": 3, "name": "TH"},
        ],
    }


def _heatsink_dict(comp_id: str, *, n_devices: int = 1) -> dict:
    return {
        "id": comp_id, "type": "HEATSINK", "name": "HS1",
        "parameters": {
            "n_devices": n_devices,
            "R_th_sink_to_amb_K_per_W": 3.0,
            "C_th_sink_J_per_K": 0.0,
            "T_amb_C": 25.0,
            "case_to_sink_R_th_csv": "",
        },
        "pins": (
            [{"index": 0, "name": "AMB"}]
            + [{"index": i + 1, "name": f"DEV{i + 1}"} for i in range(n_devices)]
        ),
    }


def test_converter_forwards_thermal_stage_kind_to_descriptor() -> None:
    """A MOSFET with ``thermal_stage_kind="cauer"`` flows through
    ``_infer_shared_heatsink_loops`` and ends up on the device row in
    the descriptor so the backend can read it."""
    conv = CircuitConverter(make_compat_module(p))
    descriptors = conv._infer_shared_heatsink_loops(
        [_heatsink_dict("h"), _mosfet_dict("q", name="Q_cauer", kind="cauer")],
        node_map={
            "h": ["amb_net", "th"],
            "q": ["a", "g", "s", "th"],
        },
    )
    assert len(descriptors) == 1
    devices = descriptors[0]["devices"]
    assert len(devices) == 1
    assert devices[0]["device_name"] == "Q_cauer"
    assert devices[0]["thermal_stage_kind"] == "cauer"


def test_converter_default_thermal_stage_kind_is_foster_when_absent() -> None:
    """Legacy schematics (saved before this field existed) don't carry
    ``thermal_stage_kind`` in their params. The converter must default
    them to "foster" so the backend keeps its existing behaviour."""
    conv = CircuitConverter(make_compat_module(p))
    legacy_mosfet = _mosfet_dict("q", name="Q_legacy", kind="")
    # Drop the field entirely to simulate "saved before this commit".
    legacy_mosfet["parameters"].pop("thermal_stage_kind", None)
    descriptors = conv._infer_shared_heatsink_loops(
        [_heatsink_dict("h"), legacy_mosfet],
        node_map={
            "h": ["amb_net", "th"],
            "q": ["a", "g", "s", "th"],
        },
    )
    devices = descriptors[0]["devices"]
    assert devices[0]["thermal_stage_kind"] == "foster"


# ---------------------------------------------------------------------------
# End-to-end: Foster and Cauer give the same steady-state numbers.
# (The transient shapes differ; steady-state Σ R_i is identical.)
# ---------------------------------------------------------------------------


def test_foster_and_cauer_give_same_steady_state_temperatures() -> None:
    """At DC the Foster ladder and the Cauer ladder with the same R, C
    pairs both reduce to ``Σ R_i`` — so the coupled steady-state T_j
    must match between the two topologies. If this test ever fails,
    the kind toggle is leaking a numerical bias that doesn't belong."""
    def desc(kind: str) -> dict:
        return {
            "name": "HS",
            "R_th_sink_to_amb_K_per_W": 3.0,
            "C_th_sink_J_per_K": 0.0,
            "T_amb_C": 40.0,
            "devices": [{
                "device_name": "Q1", "device_type": "MOSFET_N",
                "R_th_case_to_sink_K_per_W": 0.5,
                "thermal_rth_stages": "0.5, 1.0",
                "thermal_cth_stages": "0.1, 0.2",
                "thermal_rth_K_per_W": 1.5,
                "thermal_cth_J_per_K": 0.075,
                "thermal_stage_kind": kind,
            }],
        }

    rows = [{"component_name": "Q1", "conduction": {"P_avg_W": 7.0}}]

    foster_out = _backend()._compute_shared_heatsink_steady_state(
        circuit=_StubCircuit([desc("foster")]),
        electrothermal_rows=rows,
    )
    cauer_out = _backend()._compute_shared_heatsink_steady_state(
        circuit=_StubCircuit([desc("cauer")]),
        electrothermal_rows=rows,
    )
    assert len(foster_out) == 1 and len(cauer_out) == 1
    # T_sink and T_j must match between topologies at steady state.
    assert foster_out[0]["T_sink_C"] == pytest.approx(
        cauer_out[0]["T_sink_C"], rel=1e-9,
    )
    assert foster_out[0]["devices"]["Q1"] == pytest.approx(
        cauer_out[0]["devices"]["Q1"], rel=1e-9,
    )
