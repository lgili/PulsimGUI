"""Tests for project-level simulation settings serialization."""

from pulsimgui.models.project import SimulationSettings


def test_project_simulation_settings_roundtrip_control_fields() -> None:
    settings = SimulationSettings(
        control_mode="discrete",
        control_sample_time=2.5e-6,
    )

    payload = settings.to_dict()
    restored = SimulationSettings.from_dict(payload)

    assert payload["control_mode"] == "discrete"
    assert payload["control_sample_time"] == 2.5e-6
    assert restored.control_mode == "discrete"
    assert restored.control_sample_time == 2.5e-6


def test_project_simulation_settings_normalizes_control_mode_and_sample_time() -> None:
    restored = SimulationSettings.from_dict(
        {
            "control_mode": "sampled",
            "control_sample_time": -1.0,
        }
    )

    assert restored.control_mode == "discrete"
    assert restored.control_sample_time == 0.0


def test_project_simulation_settings_thermal_policy_defaults_roundtrip() -> None:
    settings = SimulationSettings(
        thermal_policy="loss_only",
        thermal_default_rth=2.0,
        thermal_default_cth=0.25,
    )

    payload = settings.to_dict()
    restored = SimulationSettings.from_dict(payload)

    assert payload["thermal_policy"] == "loss_only"
    assert payload["thermal_default_rth"] == 2.0
    assert payload["thermal_default_cth"] == 0.25
    assert restored.thermal_policy == "loss_only"
    assert restored.thermal_default_rth == 2.0
    assert restored.thermal_default_cth == 0.25
