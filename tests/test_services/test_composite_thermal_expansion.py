"""Pin the composite-device thermal expansion for SINGLE_PHASE_DIODE_BRIDGE
and THREE_PHASE_VSI in the shared-heatsink converter.

Composite components hide multiple physical switches under a single
schematic block. The pulsim 1.7 kernel's ``device_loss_summary`` reports
each internal switch under its own name:

  * ``SINGLE_PHASE_DIODE_BRIDGE`` named ``BR1`` → ``BR1_D1`` … ``BR1_D4``
    (four rectifier diodes).
  * ``THREE_PHASE_VSI`` named ``VSI`` → ``VSI__HSa`` … ``VSI__LSc``
    (six IGBTs / MOSFETs — high-side a/b/c, low-side a/b/c).

The shared-heatsink descriptor must enumerate these sub-devices
INDIVIDUALLY (one row per physical switch) so the kernel's heatsink
solver can match each sub-device's dissipation back to its junction
node. A single "BR1" row would silently swallow 3/4 of the bridge's
loss; a single "VSI" row would do the same for 5/6 of the inverter.

These tests pin:

  1. **A wired bridge expands to 4 sub-device rows.** Same thermal
     params (the four diodes are the same part), distinct device_name
     suffixes ``_D1..D4``.
  2. **A wired VSI expands to 6 sub-device rows** with the kernel's
     exact name convention (``__HSa``/``__HSb``/``__HSc``/``__LSa``/
     ``__LSb``/``__LSc``).
  3. **Sub-rows are independent dicts.** Mutating one row's
     ``conduction`` post-fact (the backend does this) MUST NOT
     pollute the sibling rows. The expansion path uses ``{**shared}``
     specifically to avoid this aliasing trap.
  4. **Single-device components keep their old 1-row behaviour.** A
     plain MOSFET still emits one row named after the component —
     no regression on the existing path.
  5. **Mixed sink wiring works.** A heatsink shared by a bridge + a
     plain MOSFET emits 4 + 1 = 5 rows, with the per-slot
     ``R_th_case_to_sink`` correctly assigned to the FIRST sub-device
     of the bridge and to the MOSFET — the bridge's other 3 diodes
     share the bridge's TH pin and therefore the bridge's case-to-sink.
"""
from __future__ import annotations

import pulsim as p

from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def _converter() -> CircuitConverter:
    return CircuitConverter(make_compat_module(p))


def _mosfet(comp_id: str, name: str = "Q1") -> dict:
    return {
        "id": comp_id, "type": "MOSFET_N", "name": name,
        "parameters": {
            "is_nmos": True, "R_on": 0.05, "v_th": 3.0,
            "enable_thermal_port": True,
            "thermal_rth": 1.5, "thermal_cth": 0.075,
            "thermal_rth_stages": "",
            "thermal_cth_stages": "",
        },
        "pins": [
            {"index": 0, "name": "D"},
            {"index": 1, "name": "G"},
            {"index": 2, "name": "S"},
            {"index": 3, "name": "TH"},
        ],
    }


def _bridge(comp_id: str, name: str = "BR1") -> dict:
    return {
        "id": comp_id, "type": "SINGLE_PHASE_DIODE_BRIDGE", "name": name,
        "parameters": {
            "v_forward": 1.0, "g_on": 1000.0, "g_off": 1e-9,
            "enable_thermal_port": True,
            "thermal_rth": 1.8, "thermal_cth": 0.10,
            "thermal_rth_stages": "0.6, 0.8, 0.4",
            "thermal_cth_stages": "0.01, 0.04, 0.10",
        },
        "pins": [
            {"index": 0, "name": "AC+"},
            {"index": 1, "name": "AC-"},
            {"index": 2, "name": "DC+"},
            {"index": 3, "name": "DC-"},
            {"index": 4, "name": "TH"},
        ],
    }


def _vsi(comp_id: str, name: str = "VSI") -> dict:
    return {
        "id": comp_id, "type": "THREE_PHASE_VSI", "name": name,
        "parameters": {
            "vce_sat": 1.5, "i_ref": 20.0, "e_on_uj": 150.0, "e_off_uj": 100.0,
            "enable_thermal_port": True,
            "thermal_rth": 0.5, "thermal_cth": 0.05,
            "thermal_rth_stages": "0.1, 0.2, 0.2",
            "thermal_cth_stages": "0.005, 0.015, 0.030",
        },
        "pins": [
            {"index": 0, "name": "DC+"},
            {"index": 1, "name": "DC-"},
            {"index": 2, "name": "A"},
            {"index": 3, "name": "B"},
            {"index": 4, "name": "C"},
            {"index": 5, "name": "GATE_BUS"},
            {"index": 6, "name": "TH"},
        ],
    }


def _heatsink(
    comp_id: str,
    *,
    name: str = "HS1",
    n_devices: int = 4,
    R_sa: float = 3.0,
    T_amb: float = 25.0,
    case_csv: str = "",
) -> dict:
    return {
        "id": comp_id, "type": "HEATSINK", "name": name,
        "parameters": {
            "n_devices": n_devices,
            "R_th_sink_to_amb_K_per_W": R_sa,
            "C_th_sink_J_per_K": 0.0,
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


def test_diode_bridge_expands_to_four_sub_devices() -> None:
    """A single SINGLE_PHASE_DIODE_BRIDGE wired to a heatsink emits four
    rows — one per internal diode — sharing the bridge's thermal stack."""
    descs = _converter()._infer_shared_heatsink_loops(
        [
            _heatsink("h", n_devices=1, R_sa=2.0, T_amb=40.0),
            _bridge("br", name="BR1"),
        ],
        node_map={
            "h": ["amb", "th_br"],
            "br": ["ac_p", "ac_n", "dc_p", "dc_n", "th_br"],
        },
    )
    assert len(descs) == 1
    devs = descs[0]["devices"]
    names = [d["device_name"] for d in devs]
    # All four sub-devices, ordered per the template tuple in
    # ``_COMPOSITE_THERMAL_SUBDEVICES``.
    assert names == ["BR1_D1", "BR1_D2", "BR1_D3", "BR1_D4"]
    # All four carry the same thermal stack — they are physically the
    # same diode part repeated four times in the bridge package.
    for d in devs:
        assert d["device_type"] == "SINGLE_PHASE_DIODE_BRIDGE"
        assert d["thermal_rth_stages"] == "0.6, 0.8, 0.4"
        assert d["thermal_cth_stages"] == "0.01, 0.04, 0.10"
        assert d["thermal_rth_K_per_W"] == 1.8
        assert d["thermal_cth_J_per_K"] == 0.10


def test_three_phase_vsi_expands_to_six_sub_devices_with_kernel_naming() -> None:
    """A THREE_PHASE_VSI emits six rows. The names MUST match the
    kernel's ``device_loss_summary`` keys exactly — the heatsink solver
    looks up dissipation by sub-device name, so a typo here silently
    zeros out 5/6 of the inverter's heat."""
    descs = _converter()._infer_shared_heatsink_loops(
        [
            _heatsink("h", n_devices=1, R_sa=1.5),
            _vsi("inv", name="VSI"),
        ],
        node_map={
            "h": ["amb", "th_vsi"],
            "inv": [
                "dc_p", "dc_n", "phase_a", "phase_b", "phase_c",
                "gate", "th_vsi",
            ],
        },
    )
    assert len(descs) == 1
    names = [d["device_name"] for d in descs[0]["devices"]]
    assert names == [
        "VSI__HSa", "VSI__HSb", "VSI__HSc",
        "VSI__LSa", "VSI__LSb", "VSI__LSc",
    ]


def test_each_sub_device_row_is_an_independent_dict() -> None:
    """The expansion uses ``{**shared}`` per row specifically so the
    backend can mutate one sub-device's ``conduction`` (or any other
    backend-attached metadata) without poisoning the others. If the
    rows aliased the same dict, all six VSI switches would mirror
    each other's post-sim state — a silent correctness bug."""
    descs = _converter()._infer_shared_heatsink_loops(
        [_heatsink("h", n_devices=1), _vsi("inv", name="V")],
        node_map={
            "h": ["amb", "th"],
            "inv": ["dc_p", "dc_n", "a", "b", "c", "g", "th"],
        },
    )
    rows = descs[0]["devices"]
    # All six rows have distinct identity — no aliasing.
    assert len({id(r) for r in rows}) == 6
    # Mutating row 0 doesn't propagate.
    rows[0]["conduction"] = 999.0
    assert "conduction" not in rows[1]
    assert "conduction" not in rows[5]


def test_single_device_components_still_emit_one_row() -> None:
    """A plain MOSFET (NOT a composite) still emits exactly one row
    under its component name — the composite path mustn't accidentally
    change the existing single-device behaviour."""
    descs = _converter()._infer_shared_heatsink_loops(
        [_heatsink("h", n_devices=1), _mosfet("q", name="Q_boost")],
        node_map={
            "h": ["amb", "th_q"],
            "q": ["d", "g", "s", "th_q"],
        },
    )
    rows = descs[0]["devices"]
    assert len(rows) == 1
    assert rows[0]["device_name"] == "Q_boost"
    assert rows[0]["device_type"] == "MOSFET_N"


def test_mixed_sink_bridge_plus_mosfet_emits_five_rows_with_correct_R_cs() -> None:
    """A heatsink shared by a SINGLE_PHASE_DIODE_BRIDGE on slot 1 and a
    MOSFET on slot 2:

      * Five rows total (4 bridge sub-devices + 1 MOSFET).
      * The bridge's four sub-devices all share the SLOT 1
        case-to-sink resistance (the bridge body is bolted to one slot,
        even though it hosts four internal diodes).
      * The MOSFET's row picks up slot 2's case-to-sink.

    This pins the contract that ``case_to_sink_R_th_csv`` is read by
    *slot* (the physical bolt point on the heatsink), not by sub-device.
    """
    descs = _converter()._infer_shared_heatsink_loops(
        [
            _heatsink("h", n_devices=2, case_csv="0.4, 0.6"),
            _bridge("br", name="BR1"),
            _mosfet("q", name="Q_PFC"),
        ],
        node_map={
            "h": ["amb", "th_br", "th_q"],
            "br": ["ac_p", "ac_n", "dc_p", "dc_n", "th_br"],
            "q": ["d", "g", "s", "th_q"],
        },
    )
    assert len(descs) == 1
    rows = descs[0]["devices"]
    names = [r["device_name"] for r in rows]
    # 4 bridge diodes + 1 MOSFET = 5 rows. Bridge first (slot 1),
    # MOSFET after (slot 2), preserving DEV pin enumeration order.
    assert names == ["BR1_D1", "BR1_D2", "BR1_D3", "BR1_D4", "Q_PFC"]
    r_cs = [r["R_th_case_to_sink_K_per_W"] for r in rows]
    # Slot 1's 0.4 applies to all four bridge sub-devices (the bridge
    # body occupies one bolt slot).
    assert r_cs[:4] == [0.4, 0.4, 0.4, 0.4]
    # Slot 2's 0.6 applies to the MOSFET.
    assert r_cs[4] == 0.6


def test_cauer_kind_propagates_to_every_sub_device_row() -> None:
    """The ``thermal_network`` parameter ("cauer" vs "foster") is a
    parent-level choice — when present, EVERY sub-device row inherits
    it. Without this, three of the four bridge diodes would silently
    fall back to Foster while the first one used Cauer, giving
    physically inconsistent steady-state temperatures."""
    bridge = _bridge("br", name="BR_CAUER")
    bridge["parameters"]["thermal_network"] = "cauer"
    descs = _converter()._infer_shared_heatsink_loops(
        [_heatsink("h", n_devices=1), bridge],
        node_map={
            "h": ["amb", "th"],
            "br": ["ac_p", "ac_n", "dc_p", "dc_n", "th"],
        },
    )
    rows = descs[0]["devices"]
    assert len(rows) == 4
    assert all(r["thermal_stage_kind"] == "cauer" for r in rows)
