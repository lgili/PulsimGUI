"""Tests for the dedicated FOC_CONTROLLER component (wireable replacement
for the legacy C_BLOCK ``control_kind="foc"`` marker).

Three behaviors matter:
  1. Model: FOC_CONTROLLER has SP (signal-domain input) + FB (signal-domain
     input) pins, with all FOC tuning knobs exposed as editable parameters.
  2. Converter: _infer_foc_loops emits a descriptor for BOTH the legacy
     C_BLOCK marker AND the new FOC_CONTROLLER, with the wire-traced PMSM
     binding (FB → motor.SIG) when available.
  3. Prevalidation: the new component is exempt from the C_BLOCK runtime
     contract (it isn't a fast_block).
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
from pulsimgui.services.simulation_service import SimulationService


def _converter() -> CircuitConverter:
    return CircuitConverter(make_compat_module(p))


def _foc_comp(comp_id: str, params: dict | None = None, pin_nodes: list | None = None) -> dict:
    base = dict(DEFAULT_PARAMETERS[ComponentType.FOC_CONTROLLER])
    if params:
        base.update(params)
    out: dict = {"id": comp_id, "type": "FOC_CONTROLLER", "name": "FOC1", "parameters": base}
    if pin_nodes is not None:
        out["pin_nodes"] = pin_nodes
    return out


def test_foc_controller_has_two_signal_input_pins_and_pwm_output_bus() -> None:
    foc = Component(type=ComponentType.FOC_CONTROLLER, name="FOC1")
    names = [p.name for p in foc.pins]
    # SP/FB stay as signal-domain inputs; the new PWM pin is the
    # signal-bus output that wires to the VSI's PWM input.
    assert names == ["SP", "FB", "PWM"]
    assert pin_connection_domain(foc, 0) == CONNECTION_DOMAIN_SIGNAL
    assert pin_connection_domain(foc, 1) == CONNECTION_DOMAIN_SIGNAL
    assert pin_connection_domain(foc, 2) == CONNECTION_DOMAIN_SIGNAL


def test_foc_controller_defaults_match_vlt403u_recipe() -> None:
    defaults = DEFAULT_PARAMETERS[ComponentType.FOC_CONTROLLER]
    assert defaults["speed_kp"] == pytest.approx(0.17)
    assert defaults["speed_ki"] == pytest.approx(6.0)
    assert defaults["current_kp"] == pytest.approx(45.0)
    assert defaults["current_ki"] == pytest.approx(24000.0)
    assert defaults["id_ref"] == pytest.approx(0.0)
    assert defaults["iq_limit"] == pytest.approx(3.0)
    assert defaults["v_limit_frac"] == pytest.approx(0.92)
    assert defaults["speed_ramp_s"] == pytest.approx(0.1)
    assert defaults["speed_ref_rpm"] == pytest.approx(1800.0)


def test_infer_emits_descriptor_for_foc_controller() -> None:
    conv = _converter()
    # PWM bus + FB wires are MANDATORY now: ``pwm_net`` shared between
    # VSI.PWM (pin 5) and FOC.PWM (pin 2); ``sig_net`` shared between
    # PMSM.SIG (pin 4) and FOC.FB (pin 1).
    comps = [
        {"id": "v", "type": "THREE_PHASE_VSI", "name": "VSI",
         "pin_nodes": ["busp", "busn", "pha", "phb", "phc", "pwm_net"]},
        {"id": "m", "type": "PMSM", "name": "M1",
         "pin_nodes": ["pha", "phb", "phc", "0", "sig_net"]},
        _foc_comp(
            "f",
            {"speed_kp": 0.30, "speed_ref_rpm": 1500.0},
            pin_nodes=["sp_net", "sig_net", "pwm_net"],
        ),
    ]
    descs = conv._infer_foc_loops(comps)
    assert len(descs) == 1
    assert descs[0]["vsi_name"] == "VSI"
    assert descs[0]["pmsm_name"] == "M1"
    assert descs[0]["speed_kp"] == pytest.approx(0.30)
    assert descs[0]["speed_ref_rpm"] == pytest.approx(1500.0)


def test_infer_traces_pmsm_via_fb_wire_when_multiple_motors() -> None:
    """When two PMSMs exist, the FB wire (FOC pin 1 → motor pin 4) selects
    which motor the descriptor binds to."""
    conv = _converter()
    comps = [
        {"id": "v", "type": "THREE_PHASE_VSI", "name": "VSI",
         "pin_nodes": ["busp", "busn", "pha", "phb", "phc", "pwm_net"]},
        {"id": "m1", "type": "PMSM", "name": "M_first",
         "pin_nodes": ["A1", "B1", "C1", "N1", "bus_net_first"]},
        {"id": "m2", "type": "PMSM", "name": "M_target",
         "pin_nodes": ["A2", "B2", "C2", "N2", "bus_net_target"]},
        # FB wires to motor M_target; PWM wires to VSI.
        _foc_comp("f", pin_nodes=["sp_net", "bus_net_target", "pwm_net"]),
    ]
    descs = conv._infer_foc_loops(comps)
    assert len(descs) == 1
    assert descs[0]["pmsm_name"] == "M_target"


def test_legacy_cblock_marker_still_works() -> None:
    """Backward compatibility: the C_BLOCK control_kind="foc" path still
    produces a descriptor (so old saved files don't break)."""
    conv = _converter()
    comps = [
        {"id": "v", "type": "THREE_PHASE_VSI", "name": "VSI"},
        {"id": "m", "type": "PMSM", "name": "M1"},
        {"id": "c", "type": "C_BLOCK", "name": "FOC_legacy",
         "parameters": {"control_kind": "foc", "speed_kp": 0.25}},
    ]
    descs = conv._infer_foc_loops(comps)
    assert len(descs) == 1
    assert descs[0]["name"] == "FOC_legacy"
    assert descs[0]["speed_kp"] == pytest.approx(0.25)


def test_both_legacy_and_new_components_emit_two_descriptors() -> None:
    """A circuit carrying both kinds (transitional file) emits one
    descriptor per controller. The new FOC_CONTROLLER requires the
    wired PWM + FB bus; the legacy C_BLOCK marker keeps its parameter-
    based / single-VSI binding."""
    conv = _converter()
    comps = [
        {"id": "v", "type": "THREE_PHASE_VSI", "name": "VSI",
         "pin_nodes": ["busp", "busn", "pha", "phb", "phc", "pwm_net"]},
        {"id": "m", "type": "PMSM", "name": "M1",
         "pin_nodes": ["pha", "phb", "phc", "0", "sig_net"]},
        {"id": "c", "type": "C_BLOCK", "name": "FOC_legacy",
         "parameters": {"control_kind": "foc"}},
        _foc_comp("f", pin_nodes=["sp_net", "sig_net", "pwm_net"]),
    ]
    descs = conv._infer_foc_loops(comps)
    assert {d["name"] for d in descs} == {"FOC_legacy", "FOC1"}


def test_no_descriptor_without_vsi_or_pmsm() -> None:
    conv = _converter()
    # No PMSM
    descs = conv._infer_foc_loops([
        {"id": "v", "type": "THREE_PHASE_VSI", "name": "VSI"},
        _foc_comp("f"),
    ])
    assert descs == []
    # No VSI
    descs = conv._infer_foc_loops([
        {"id": "m", "type": "PMSM", "name": "M1"},
        _foc_comp("f"),
    ])
    assert descs == []


def test_prevalidation_does_not_reject_foc_controller(monkeypatch) -> None:
    """The new component is not a C_BLOCK, so the runtime contract that
    rejects source-less C_BLOCKs never applies to it."""
    # Use a bare SimulationService instance — we only need the validator
    # method, which is independent of the backend loader.
    svc = SimulationService.__new__(SimulationService)
    issue = SimulationService._prevalidate_runtime_contract(svc, {
        "components": [
            {"type": "THREE_PHASE_VSI", "name": "VSI", "parameters": {}},
            {"type": "PMSM", "name": "M1", "parameters": {}},
            {"type": "FOC_CONTROLLER", "name": "FOC1",
             "parameters": DEFAULT_PARAMETERS[ComponentType.FOC_CONTROLLER]},
        ],
    })
    assert issue is None
