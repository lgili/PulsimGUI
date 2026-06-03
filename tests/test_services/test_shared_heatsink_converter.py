"""Converter tests for the HEATSINK → shared_heatsink_descriptor path.

These pin the contract the next slice (the backend's
``_build_shared_heatsink_loops``) reads from
``circuit.shared_heatsink_descriptors``:

  1. **Detection by wiring.** Every HEATSINK whose DEV pins reach a
     device's ``TH`` pin shows up. Heatsinks with no wires are
     silently dropped (descriptor-only sinks are noise that would
     embed a 0-device network in the backend).
  2. **Per-device payload.** Each wired device contributes its name,
     type, Foster CSVs, single-RC fallbacks, and the per-slot
     case-to-sink resistance from the heatsink's CSV.
  3. **Multiple sinks.** Two sinks each with their own device set
     emit two descriptors with the right groupings.
  4. **Descriptor-only path stays clean.** When there's no HEATSINK
     at all, ``shared_heatsink_descriptors`` is an empty list — the
     existing per-device-isolated thermal path is untouched.
"""
from __future__ import annotations

import pulsim as p

from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def _converter() -> CircuitConverter:
    return CircuitConverter(make_compat_module(p))


def _mosfet(comp_id: str, name: str = "Q1") -> dict:
    """A minimal MOSFET with an enabled TH thermal port."""
    return {
        "id": comp_id, "type": "MOSFET_N", "name": name,
        "parameters": {
            "is_nmos": True, "R_on": 0.05, "v_th": 3.0,
            "enable_thermal_port": True,
            "thermal_rth": 1.5, "thermal_cth": 0.075,
            "thermal_rth_stages": "0.2, 0.4, 0.3",
            "thermal_cth_stages": "0.005, 0.025, 0.167",
        },
        "pins": [
            {"index": 0, "name": "D"},
            {"index": 1, "name": "G"},
            {"index": 2, "name": "S"},
            {"index": 3, "name": "TH"},
        ],
    }


def _diode(comp_id: str, name: str = "D1") -> dict:
    return {
        "id": comp_id, "type": "DIODE", "name": name,
        "parameters": {
            "g_on": 1000.0, "g_off": 1e-9, "v_forward": 0.7,
            "enable_thermal_port": True,
            "thermal_rth": 1.0, "thermal_cth": 0.05,
            "thermal_rth_stages": "", "thermal_cth_stages": "",
        },
        "pins": [
            {"index": 0, "name": "A"},
            {"index": 1, "name": "K"},
            {"index": 2, "name": "TH"},
        ],
    }


def _heatsink(
    comp_id: str,
    *,
    name: str = "HS1",
    n_devices: int = 4,
    R_sa: float = 5.0,
    C_sink: float = 0.0,
    T_amb: float = 25.0,
    case_csv: str = "",
) -> dict:
    return {
        "id": comp_id, "type": "HEATSINK", "name": name,
        "parameters": {
            "n_devices": n_devices,
            "R_th_sink_to_amb_K_per_W": R_sa,
            "C_th_sink_J_per_K": C_sink,
            "T_amb_C": T_amb,
            "case_to_sink_R_th_csv": case_csv,
        },
        "pins": (
            [{"index": 0, "name": "AMB"}]
            + [
                {"index": i + 1, "name": f"DEV{i + 1}"}
                for i in range(n_devices)
            ]
        ),
    }


def test_no_heatsink_in_circuit_yields_empty_descriptors() -> None:
    """A circuit with no HEATSINK leaves the legacy per-device-isolated
    thermal path untouched — the descriptor list stays empty."""
    descs = _converter()._infer_shared_heatsink_loops(
        [_mosfet("q")], node_map={"q": ["a", "b", "c", "th_q"]},
    )
    assert descs == []


def test_heatsink_with_no_wired_devices_is_dropped() -> None:
    """A descriptor-only heatsink (none of its DEV pins reach a
    device's TH) emits NO descriptor — the backend would embed a
    0-device network otherwise."""
    descs = _converter()._infer_shared_heatsink_loops(
        [
            _heatsink("h", n_devices=2),
            _mosfet("q"),  # TH not wired to the sink
        ],
        node_map={
            "h": ["amb_net", "dev_slot1", "dev_slot2"],
            "q": ["a", "b", "c", "th_disconnected"],
        },
    )
    assert descs == []


def test_one_heatsink_one_device_emits_descriptor() -> None:
    """The simplest happy-path topology: one MOSFET on a heatsink."""
    descs = _converter()._infer_shared_heatsink_loops(
        [
            _heatsink("h", n_devices=2, R_sa=3.5, T_amb=30.0),
            _mosfet("q", name="Q_boost"),
        ],
        node_map={
            "h": ["amb_net", "shared_th", ""],
            "q": ["drain", "gate", "source", "shared_th"],
        },
    )
    assert len(descs) == 1
    d = descs[0]
    assert d["name"] == "HS1"
    assert d["R_th_sink_to_amb_K_per_W"] == 3.5
    assert d["T_amb_C"] == 30.0
    assert d["C_th_sink_J_per_K"] == 0.0
    assert len(d["devices"]) == 1
    dev = d["devices"][0]
    assert dev["device_name"] == "Q_boost"
    assert dev["device_type"] == "MOSFET_N"
    assert dev["thermal_rth_stages"] == "0.2, 0.4, 0.3"
    assert dev["thermal_cth_stages"] == "0.005, 0.025, 0.167"
    assert dev["thermal_rth_K_per_W"] == 1.5
    assert dev["thermal_cth_J_per_K"] == 0.075
    # case_to_sink defaults to 0 when the CSV is empty.
    assert dev["R_th_case_to_sink_K_per_W"] == 0.0


def test_per_slot_case_to_sink_csv_is_aligned_by_slot_position() -> None:
    """``case_to_sink_R_th_csv`` is read positionally: slot k (DEV_k)
    consumes csv[k−1]. Missing entries default to 0."""
    descs = _converter()._infer_shared_heatsink_loops(
        [
            _heatsink(
                "h", n_devices=4, case_csv="0.5; 0.7, 0.3",  # only 3 entries
            ),
            _mosfet("q1", name="Q1"),
            _mosfet("q2", name="Q2"),
            _diode("d1", name="D1"),
            _diode("d2", name="D2"),
        ],
        node_map={
            "h": [
                "amb_net", "th_q1", "th_q2", "th_d1", "th_d2",
            ],
            "q1": ["d1", "g1", "s1", "th_q1"],
            "q2": ["d2", "g2", "s2", "th_q2"],
            "d1": ["a1", "k1", "th_d1"],
            "d2": ["a2", "k2", "th_d2"],
        },
    )
    assert len(descs) == 1
    devices = descs[0]["devices"]
    r_cs = [d["R_th_case_to_sink_K_per_W"] for d in devices]
    # Order follows DEV pin enumeration: Q1, Q2, D1, D2.
    assert r_cs == [0.5, 0.7, 0.3, 0.0]


def test_two_heatsinks_emit_two_descriptors_with_correct_groupings() -> None:
    """A schematic with two sinks (e.g. PFC stage + VSI stage) yields
    two descriptors, each carrying only its own wired devices."""
    descs = _converter()._infer_shared_heatsink_loops(
        [
            _heatsink("hA", name="HS_PFC", n_devices=2, R_sa=4.0),
            _heatsink("hB", name="HS_VSI", n_devices=2, R_sa=2.0),
            _mosfet("q1", name="Q_PFC"),
            _diode("d1", name="D_PFC"),
            _mosfet("q2", name="Q_VSI_H"),
            _mosfet("q3", name="Q_VSI_L"),
        ],
        node_map={
            "hA": ["amb_A", "th_q1", "th_d1"],
            "hB": ["amb_B", "th_q2", "th_q3"],
            "q1": ["x1", "g", "s", "th_q1"],
            "d1": ["x2", "x3", "th_d1"],
            "q2": ["x4", "g", "s", "th_q2"],
            "q3": ["x5", "g", "s", "th_q3"],
        },
    )
    assert {d["name"] for d in descs} == {"HS_PFC", "HS_VSI"}
    by_name = {d["name"]: d for d in descs}
    assert {dev["device_name"] for dev in by_name["HS_PFC"]["devices"]} == {
        "Q_PFC", "D_PFC",
    }
    assert {dev["device_name"] for dev in by_name["HS_VSI"]["devices"]} == {
        "Q_VSI_H", "Q_VSI_L",
    }
    # R_th_sa correctly attached to each sink.
    assert by_name["HS_PFC"]["R_th_sink_to_amb_K_per_W"] == 4.0
    assert by_name["HS_VSI"]["R_th_sink_to_amb_K_per_W"] == 2.0


def test_heatsink_descriptor_attached_to_circuit_after_build() -> None:
    """End-to-end: the full ``conv.build({...})`` call stashes the
    descriptor list on the returned Circuit so the backend can read
    ``circuit.shared_heatsink_descriptors`` next slice."""
    components = [
        _heatsink("h", n_devices=1),
        _mosfet("q", name="Q1"),
        # Need a complete circuit — a source and a load.
        {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
         "parameters": {"waveform": {"type": "dc", "value": 10.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": "r1", "type": "RESISTOR", "name": "R1",
         "parameters": {"resistance": 10.0},
         "pins": [{"index": 0, "name": "1"}, {"index": 1, "name": "2"}]},
        {"id": "g", "type": "GROUND", "name": "G", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
    ]
    node_map = {
        "h": ["amb", "th_q"],
        "q": ["a", "b", "0", "th_q"],
        "v1": ["a", "0"],
        "r1": ["a", "0"],
        "g": ["0"],
    }
    circ = _converter().build({"components": components, "node_map": node_map})
    descs = list(getattr(circ, "shared_heatsink_descriptors", []))
    assert len(descs) == 1
    assert descs[0]["devices"][0]["device_name"] == "Q1"
