"""Tests for thermal scope fallback behavior with backend-native traces."""

from __future__ import annotations

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.scope.scope_window import ScopeWindow


def test_thermal_scope_falls_back_to_backend_thermal_traces_without_bindings(qapp) -> None:
    """Unconnected thermal scopes should still render backend T(...) channels."""
    window = ScopeWindow(
        component_id="scope-th-1",
        component_name="ThermalScope",
        scope_type=ComponentType.THERMAL_SCOPE,
    )
    window.set_bindings([])

    result = SimulationResult(
        time=[0.0, 1e-6, 2e-6],
        signals={
            "T(M1)": [25.0, 25.4, 25.9],
            "V(out)": [0.0, 1.0, 2.0],
        },
        statistics={
            "virtual_channel_metadata": {
                "T(M1)": {
                    "domain": "thermal",
                    "component_type": "thermal_trace",
                }
            }
        },
    )

    window.apply_simulation_result(result)

    assert window._current_result is not None
    assert "T(M1)" in window._current_result.signals
    assert "V(out)" not in window._current_result.signals
    assert window._message_label.text() == "Loaded 1 signal(s)."
    window.close()


def test_thermal_scope_fallback_accepts_metadata_mapped_noncanonical_name(qapp) -> None:
    """Metadata thermal domain should enable fallback even for non T(...) keys."""
    window = ScopeWindow(
        component_id="scope-th-2",
        component_name="ThermalScope",
        scope_type=ComponentType.THERMAL_SCOPE,
    )
    window.set_bindings([])

    result = SimulationResult(
        time=[0.0, 1e-6, 2e-6],
        signals={"device_temp_m1": [25.0, 25.3, 25.6]},
        statistics={
            "virtual_channel_metadata": {
                "device_temp_m1": {
                    "domain": "thermal",
                    "component_type": "thermal_trace",
                    "source_component": "M1",
                }
            }
        },
    )

    window.apply_simulation_result(result)

    assert window._current_result is not None
    assert "device_temp_m1" in window._current_result.signals
    assert window._message_label.text() == "Loaded 1 signal(s)."
    window.close()
