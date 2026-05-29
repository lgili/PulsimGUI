"""Tests for cascaded PI detection in CircuitConverter.

The closed-loop detector at
``CircuitConverter._infer_native_buck_control_overrides`` is responsible
for recognizing PI → PWM → MOSFET control chains and emitting a
``closed_loop_descriptor`` the backend uses to call
``pulsim.bind_pi_to_switch``. Originally it only recognized a SINGLE
PI in the chain (CONSTANT setpoint + VOLTAGE_PROBE feedback); this
test suite locks in the cascaded-PI extension:

    CONSTANT(V_ref) ── SUB_V ── PI_V ──┐
    VOLTAGE_PROBE  ────────────────────┤
                                        │
                                        └── (inner setpoint)
                            CURRENT_PROBE ──── SUB_I ── PI_I ── PWM ── MOSFET
"""
from __future__ import annotations

from typing import Any

import pytest

from pulsimgui.services.circuit_converter import CircuitConverter


# ---------------------------------------------------------------------------
# Fake backend (just enough surface for the converter)
# ---------------------------------------------------------------------------
class _FakeCircuit:
    @staticmethod
    def ground() -> int:
        return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def add_virtual_component(self, *args, **kwargs) -> None:
        # Detector probes ``hasattr(Circuit(), "add_virtual_component")``
        # to decide whether to run. Existence is enough — no behavior.
        pass


class _FakeBackend:
    Circuit = _FakeCircuit


# ---------------------------------------------------------------------------
# Schematic-shape helpers
# ---------------------------------------------------------------------------
def _comp(comp_id: str, name: str, ctype: str, pin_nodes: list[str],
          parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": comp_id, "name": name, "type": ctype,
        "parameters": parameters or {},
        "pin_nodes": pin_nodes,
    }


def _build_cascaded_circuit() -> dict[str, Any]:
    """Cascaded boost: V_REF → SUB_V → PI_V → SUB_I → PI_I → PWM → MOSFET,
    with V_DC feedback on outer SUB and I_L feedback on inner SUB."""
    components = [
        # Power path (just the MOSFET — the rest is irrelevant for detection)
        _comp("mos", "M_boost", "MOSFET_N", ["nmid", "ngate", "0"]),

        # Voltage probe (DC bus) → output channel "nvdc_meas"
        _comp("vp", "V_DC", "VOLTAGE_PROBE_GND",
              ["nvbus", "nvdc_meas"]),

        # Current probe (boost inductor) → output channel "nil_meas"
        _comp("ip", "I_L", "CURRENT_PROBE",
              ["nrect", "nmid_pre", "nil_meas"],
              parameters={"series_resistance": 1e-4}),

        # Outer chain
        _comp("vref", "V_REF", "CONSTANT", ["nvref_out"],
              parameters={"value": 400.0}),
        _comp("subv", "SUB_V", "SUBTRACTOR",
              ["nvref_out", "nvdc_meas", "nverr"],
              parameters={"input_count": 2, "signs": ["+", "-"]}),
        _comp("piv", "PI_V", "PI_CONTROLLER",
              ["nverr", "niref"],
              parameters={"kp": 0.015, "ki": 1.5,
                          "output_min": 0.0, "output_max": 3.0}),

        # Inner chain
        _comp("subi", "SUB_I", "SUBTRACTOR",
              ["niref", "nil_meas", "nierr"],
              parameters={"input_count": 2, "signs": ["+", "-"]}),
        _comp("pii", "PI_I", "PI_CONTROLLER",
              ["nierr", "nduty"],
              parameters={"kp": 0.10, "ki": 500.0,
                          "output_min": 0.0, "output_max": 0.45}),

        # PWM (DUTY_IN at "nduty", OUT at "ngate" = MOSFET gate)
        _comp("pwm", "PWM_BOOST", "PWM_GENERATOR",
              ["ngate", "nduty"],
              parameters={"frequency": 50000.0, "duty_cycle": 0.5}),
    ]

    node_map = {c["id"]: c["pin_nodes"] for c in components}
    return {"components": components, "node_map": node_map,
            "node_aliases": {}}


def _build_single_loop_circuit() -> dict[str, Any]:
    """Single voltage loop (regression test — existing detection path)."""
    components = [
        _comp("mos", "M_buck", "MOSFET_N", ["nmid", "ngate", "0"]),
        _comp("vp", "V_OUT", "VOLTAGE_PROBE_GND",
              ["nvout", "nvout_meas"]),
        _comp("vref", "V_REF", "CONSTANT", ["nvref_out"],
              parameters={"value": 5.0}),
        _comp("subv", "SUB_V", "SUBTRACTOR",
              ["nvref_out", "nvout_meas", "nverr"],
              parameters={"input_count": 2, "signs": ["+", "-"]}),
        _comp("piv", "PI_V", "PI_CONTROLLER",
              ["nverr", "nduty"],
              parameters={"kp": 0.08, "ki": 40.0,
                          "output_min": 0.05, "output_max": 0.95}),
        _comp("pwm", "PWM_BUCK", "PWM_GENERATOR",
              ["ngate", "nduty"],
              parameters={"frequency": 100000.0, "duty_cycle": 0.5}),
    ]
    node_map = {c["id"]: c["pin_nodes"] for c in components}
    return {"components": components, "node_map": node_map,
            "node_aliases": {}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_single_loop_descriptor_still_emitted() -> None:
    """Regression: the original single-loop pattern still produces a
    valid descriptor without an ``outer_pi`` block."""
    converter = CircuitConverter(_FakeBackend)
    data = _build_single_loop_circuit()
    overrides = converter._infer_native_buck_control_overrides(
        data["components"], data["node_map"], data["node_aliases"],
    )
    descriptors = overrides[-1]
    assert len(descriptors) == 1
    d = descriptors[0]
    assert d["pi_name"] == "PI_V"
    assert d["switch_device"] == "M_buck"
    assert d["kp"] == pytest.approx(0.08)
    assert d["ki"] == pytest.approx(40.0)
    assert d["setpoint_value"] == pytest.approx(5.0)
    assert d["feedback_kind"] == "voltage"
    assert "outer_pi" not in d


def test_cascaded_descriptor_includes_outer_pi_block() -> None:
    """The cascaded chain emits ONE descriptor with the INNER PI's
    gains as top-level and the OUTER PI nested under ``outer_pi``."""
    converter = CircuitConverter(_FakeBackend)
    data = _build_cascaded_circuit()
    overrides = converter._infer_native_buck_control_overrides(
        data["components"], data["node_map"], data["node_aliases"],
    )
    descriptors = overrides[-1]
    # Only the INNER chain (PI_I → PWM → MOSFET) produces a descriptor.
    # The outer PI (PI_V) doesn't feed a PWM directly so it's absorbed
    # into the inner's ``outer_pi`` block.
    assert len(descriptors) == 1
    d = descriptors[0]
    assert d["pi_name"] == "PI_I"
    assert d["switch_device"] == "M_boost"
    assert d["kp"] == pytest.approx(0.10)
    assert d["ki"] == pytest.approx(500.0)
    assert d["output_max"] == pytest.approx(0.45)

    outer = d.get("outer_pi")
    assert outer is not None, "Cascaded descriptor must include outer_pi"
    assert outer["pi_name"] == "PI_V"
    assert outer["kp"] == pytest.approx(0.015)
    assert outer["ki"] == pytest.approx(1.5)
    assert outer["output_max"] == pytest.approx(3.0)
    assert outer["setpoint_value"] == pytest.approx(400.0)


def test_cascaded_inner_feedback_is_current_mode() -> None:
    """The inner SUB reads from a CURRENT_PROBE, so the descriptor
    flags ``feedback_kind == "current"`` and carries the bypass-R
    needed to recover I = (V_in − V_out) / R_bypass at sim time."""
    converter = CircuitConverter(_FakeBackend)
    data = _build_cascaded_circuit()
    overrides = converter._infer_native_buck_control_overrides(
        data["components"], data["node_map"], data["node_aliases"],
    )
    d = overrides[-1][0]
    assert d["feedback_kind"] == "current"
    assert "feedback_node_in" in d
    assert "feedback_node_out" in d
    assert d["feedback_bypass_r"] == pytest.approx(1e-4)


def test_cascaded_outer_pi_references_dc_bus_voltage() -> None:
    """The outer loop's feedback should resolve to the DC-bus
    VOLTAGE_PROBE_GND (not the inner current probe)."""
    converter = CircuitConverter(_FakeBackend)
    data = _build_cascaded_circuit()
    overrides = converter._infer_native_buck_control_overrides(
        data["components"], data["node_map"], data["node_aliases"],
    )
    outer = overrides[-1][0].get("outer_pi") or {}
    # The outer feedback positive side is the bus rail (raw node
    # "nvbus"), which the converter prefixes with "N" → "Nnvbus"
    # because the converter normalizes user-given node names. The
    # negative side is ground.
    assert outer.get("feedback_node", "").endswith("nvbus")
    assert outer.get("feedback_node_neg") in {"0", "Ngnd", ""}
