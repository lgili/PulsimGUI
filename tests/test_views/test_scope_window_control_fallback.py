"""Tests for control-channel fallback resolution in ScopeWindow."""

from __future__ import annotations

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.scope.bindings import ScopeChannelBinding, ScopeSignal
from pulsimgui.views.scope.scope_window import ScopeWindow


def _single_binding(signal_key: str, label: str | None = None) -> ScopeChannelBinding:
    """Build a one-channel scope binding for a specific signal key."""
    return ScopeChannelBinding(
        index=0,
        pin_index=0,
        channel_label="CH1",
        overlay=False,
        node_id="1",
        node_label="1",
        signals=[
            ScopeSignal(
                label=label or signal_key,
                signal_key=signal_key,
                node_id="1",
                node_label="1",
            )
        ],
    )


def test_control_scope_uses_virtual_metadata_when_key_differs(qapp) -> None:
    """Scope should map control channels by metadata source_component when names diverge."""
    window = ScopeWindow("scope-1", "Scope1", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.set_bindings([_single_binding("CB_PI.OUT0")])
        result = SimulationResult(
            time=[0.0, 1e-6],
            signals={"CB_PI": [0.1, 0.2]},
            statistics={
                "virtual_channel_metadata": {
                    "CB_PI": {
                        "component_type": "c_block",
                        "source_component": "CB_PI",
                        "domain": "control",
                        "unit": "",
                    }
                }
            },
        )

        window.apply_simulation_result(result)
        assert window._current_result is not None
        assert len(window._current_result.signals) == 1
        assert next(iter(window._current_result.signals.values())) == [0.1, 0.2]
    finally:
        window.close()


def test_control_scope_prefers_matching_qualifier_for_pwm_duty(qapp) -> None:
    """Duty bindings should choose the duty-like channel when metadata has multiple outputs."""
    window = ScopeWindow("scope-2", "Scope2", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.set_bindings([_single_binding("PWM1.duty")])
        result = SimulationResult(
            time=[0.0, 1e-6],
            signals={
                "PWM1": [0.15, 0.2],
                "PWM1.OUT0": [0.3, 0.35],
                "PWM1.DUTY_COMMAND": [0.45, 0.5],
            },
            statistics={
                "virtual_channel_metadata": {
                    "PWM1": {
                        "component_type": "pwm_generator",
                        "source_component": "PWM1",
                        "domain": "control",
                        "unit": "",
                    },
                    "PWM1.OUT0": {
                        "component_type": "pwm_generator",
                        "source_component": "PWM1",
                        "domain": "control",
                        "unit": "",
                    },
                    "PWM1.DUTY_COMMAND": {
                        "component_type": "pwm_generator",
                        "source_component": "PWM1",
                        "domain": "control",
                        "unit": "",
                    },
                }
            },
        )

        window.apply_simulation_result(result)
        assert window._current_result is not None
        assert len(window._current_result.signals) == 1
        assert next(iter(window._current_result.signals.values())) == [0.45, 0.5]
    finally:
        window.close()


def test_control_scope_resolves_case_insensitive_signal_keys(qapp) -> None:
    """Case-only differences between binding and backend signal names should still match."""
    window = ScopeWindow("scope-3", "Scope3", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.set_bindings([_single_binding("PI1")])
        result = SimulationResult(
            time=[0.0, 1e-6],
            signals={"pi1": [0.9, 1.1]},
            statistics={},
        )

        window.apply_simulation_result(result)
        assert window._current_result is not None
        assert len(window._current_result.signals) == 1
        assert next(iter(window._current_result.signals.values())) == [0.9, 1.1]
    finally:
        window.close()


def test_control_scope_fuzzy_matches_when_metadata_is_missing(qapp) -> None:
    """Scope should still map control channels by source-like names without metadata."""
    window = ScopeWindow("scope-4", "Scope4", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.set_bindings([_single_binding("CB_PI.OUT0")])
        result = SimulationResult(
            time=[0.0, 1e-6],
            signals={
                "V(OUT)": [5.8, 5.9],
                "CB_PI": [0.35, 0.4],
            },
            statistics={},
        )

        window.apply_simulation_result(result)
        assert window._current_result is not None
        assert len(window._current_result.signals) == 1
        assert next(iter(window._current_result.signals.values())) == [0.35, 0.4]
    finally:
        window.close()


def test_control_scope_falls_back_to_node_voltage_when_control_channel_absent(qapp) -> None:
    """Control scope should use V(node) fallback when backend lacks virtual control channels."""
    window = ScopeWindow("scope-5", "Scope5", ComponentType.ELECTRICAL_SCOPE)
    try:
        binding = _single_binding("CB_PI.OUT0")
        binding.node_id = "14"
        binding.node_label = "N14"
        window.set_bindings([binding])
        result = SimulationResult(
            time=[0.0, 1e-6],
            signals={
                "V(N14)": [0.2, 0.22],
                "V(OUT)": [5.9, 6.0],
            },
            statistics={},
        )

        window.apply_simulation_result(result)
        assert window._current_result is not None
        assert len(window._current_result.signals) == 1
        label, values = next(iter(window._current_result.signals.items()))
        assert "V(N14)" in label
        assert values == [0.2, 0.22]
    finally:
        window.close()
