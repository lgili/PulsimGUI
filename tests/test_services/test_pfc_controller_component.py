"""Tests for the dedicated PFC_BOOST_CONTROLLER component.

Covers the model layer (pin/domain/defaults) and the converter's
descriptor inference (`_infer_pfc_loops`): MOSFET auto-detect, wire
tracing for V_bus / V_rect / i_L, and the parameter recipe.
"""
from __future__ import annotations

import pulsim as p
import pytest

from pulsimgui.models.component import (
    CONNECTION_DOMAIN_SIGNAL,
    DEFAULT_PARAMETERS,
    Component,
    ComponentType,
    pin_connection_domain,
)
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def _converter() -> CircuitConverter:
    return CircuitConverter(make_compat_module(p))


def _pfc_comp(comp_id: str = "pfc", params: dict | None = None,
              pin_nodes: list | None = None) -> dict:
    base = dict(DEFAULT_PARAMETERS[ComponentType.PFC_BOOST_CONTROLLER])
    if params:
        base.update(params)
    out: dict = {"id": comp_id, "type": "PFC_BOOST_CONTROLLER",
                 "name": "PFC1", "parameters": base}
    if pin_nodes is not None:
        out["pin_nodes"] = pin_nodes
    return out


def test_pfc_controller_has_four_signal_pins() -> None:
    # VBUS / IL / VAC are inputs (feedback). PWM is the output that drives
    # the boost MOSFET's gate — making the controller's role visible in
    # the schematic (instead of the converter inferring it silently).
    pfc = Component(type=ComponentType.PFC_BOOST_CONTROLLER, name="PFC1")
    assert [p.name for p in pfc.pins] == ["VBUS", "IL", "VAC", "PWM"]
    for i in range(4):
        assert pin_connection_domain(pfc, i) == CONNECTION_DOMAIN_SIGNAL


def test_pfc_controller_defaults_target_ccm_240_to_1000w() -> None:
    defaults = DEFAULT_PARAMETERS[ComponentType.PFC_BOOST_CONTROLLER]
    # CCM is the recommended operating mode for this power range.
    assert defaults["mode"] == "CCM"
    # Universal-input PFC standard target: 400 V.
    assert defaults["v_bus_ref"] == pytest.approx(400.0)
    # Outer loop tuned below 2·f_line so 120 Hz ripple is not amplified.
    assert defaults["voltage_kp"] == pytest.approx(0.30)
    assert defaults["voltage_ki"] == pytest.approx(6.0)
    # Inner loop targets ~5 kHz crossover. The PI output is the DUTY
    # cycle, so the plant gain ``ΔI/Δduty = V_bus / (s·L)`` divides
    # the "Kp ≈ L·ω_c" formula by V_bus → Kp ≈ ω_c·L/V_bus. For the
    # example recipe (L=5 mH, V_bus=400 V): Kp ≈ 0.39, Ki ≈ 1200.
    assert defaults["current_kp"] == pytest.approx(0.4)
    assert defaults["current_ki"] == pytest.approx(1200.0)
    # 65 kHz is the modern high-power PFC carrier default.
    assert defaults["f_sw"] == pytest.approx(65_000.0)


def test_infer_pfc_loops_emits_descriptor_via_pwm_wire() -> None:
    """The PWM pin (index 3) must wire to the boost MOSFET's gate to bind
    that switch. No PWM wire ⇒ no descriptor (the user's visual cue
    that the loop isn't fully specified)."""
    conv = _converter()
    comps = [
        {"id": "q", "type": "MOSFET_N", "name": "Q_boost",
         # MOSFET pins are [D, G, S] — only the gate's net matters here.
         "pin_nodes": ["drain", "gate_net", "source"]},
        _pfc_comp(pin_nodes=["", "", "", "gate_net"]),
    ]
    descs = conv._infer_pfc_loops(comps, {}, {})
    assert len(descs) == 1
    assert descs[0]["mosfet_name"] == "Q_boost"
    assert descs[0]["mode"] == "CCM"
    assert descs[0]["v_bus_ref"] == pytest.approx(400.0)
    assert descs[0]["f_sw"] == pytest.approx(65_000.0)


def test_infer_pfc_loops_traces_v_bus_node_via_voltage_probe() -> None:
    """When VBUS pin is wired to a voltage probe's OUTPUT, the descriptor
    receives the probe's INPUT node alias — that's the node the backend
    must read for V_bus feedback."""
    conv = _converter()
    comps = [
        {"id": "q", "type": "MOSFET_N", "name": "Q_boost",
         "pin_nodes": ["drain", "gate_net", "source"]},
        {"id": "vbus_probe", "type": "VOLTAGE_PROBE_GND", "name": "V_bus",
         "pin_nodes": ["bus_net", "vbus_out_net"]},
        _pfc_comp(pin_nodes=["vbus_out_net", "", "", "gate_net"]),
    ]
    descs = conv._infer_pfc_loops(comps, {}, {})
    assert len(descs) == 1
    # Should resolve to the probe's INPUT net, not the output.
    assert "bus_net" in descs[0]["v_bus_node"].lower() or descs[0]["v_bus_node"] == "Nbus_net"


def test_infer_pfc_loops_captures_current_probe_name() -> None:
    """IL pin wired to a current probe's MEAS output captures the probe's
    component name (the backend uses it via builder.branch_index_of)."""
    conv = _converter()
    comps = [
        {"id": "q", "type": "MOSFET_N", "name": "Q_boost",
         "pin_nodes": ["drain", "gate_net", "source"]},
        {"id": "il_probe", "type": "CURRENT_PROBE", "name": "I_L",
         "pin_nodes": ["a", "b", "il_meas_net"]},
        _pfc_comp(pin_nodes=["", "il_meas_net", "", "gate_net"]),
    ]
    descs = conv._infer_pfc_loops(comps, {}, {})
    assert len(descs) == 1
    assert descs[0]["i_l_branch_name"] == "I_L"


def test_no_descriptor_without_mosfet() -> None:
    """No MOSFET in the schematic ⇒ no PWM wire can land ⇒ no descriptor."""
    conv = _converter()
    descs = conv._infer_pfc_loops([_pfc_comp()], {}, {})
    assert descs == []


def test_no_descriptor_without_pfc_controller() -> None:
    conv = _converter()
    descs = conv._infer_pfc_loops([
        {"id": "q", "type": "MOSFET_N", "name": "Q_boost"},
    ], {}, {})
    assert descs == []


def test_no_descriptor_when_pwm_pin_unwired() -> None:
    """Mandatory contract: a PFC controller with an unwired PWM pin
    cannot identify its MOSFET — no descriptor emitted even if a
    MOSFET exists in the circuit. The single-MOSFET auto-detect
    fallback was removed in v1.1.3."""
    conv = _converter()
    comps = [
        {"id": "q", "type": "MOSFET_N", "name": "Q_boost",
         "pin_nodes": ["drain", "gate_net", "source"]},
        # PFC PWM pin (index 3) is empty — no wire.
        _pfc_comp(pin_nodes=["", "", "", ""]),
    ]
    descs = conv._infer_pfc_loops(comps, {}, {})
    assert descs == []
