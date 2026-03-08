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


def test_project_simulation_settings_roundtrip_frequency_and_averaged_fields() -> None:
    settings = SimulationSettings(
        ac_f_start=10.0,
        ac_f_stop=1e5,
        ac_points_per_decade=30,
        ac_anchor_mode="dc",
        ac_sweep_scale="log",
        ac_injection_node="vin,0",
        ac_measurement_node="vout,0",
        averaged_options={"topology": "flyback", "mode": "auto", "envelope": "lenient"},
    )

    payload = settings.to_dict()
    restored = SimulationSettings.from_dict(payload)

    assert payload["ac_f_start"] == 10.0
    assert payload["ac_f_stop"] == 1e5
    assert payload["ac_points_per_decade"] == 30
    assert payload["ac_anchor_mode"] == "dc"
    assert payload["ac_sweep_scale"] == "log"
    assert payload["ac_injection_node"] == "vin,0"
    assert payload["ac_measurement_node"] == "vout,0"
    assert payload["averaged_options"]["topology"] == "flyback"
    assert restored.ac_f_start == 10.0
    assert restored.ac_f_stop == 1e5
    assert restored.ac_points_per_decade == 30
    assert restored.ac_anchor_mode == "dc"
    assert restored.ac_sweep_scale == "log"
    assert restored.ac_injection_node == "vin,0"
    assert restored.ac_measurement_node == "vout,0"
    assert restored.averaged_options == {
        "topology": "flyback",
        "mode": "auto",
        "envelope": "lenient",
    }
