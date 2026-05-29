"""Tests for project-level simulation settings serialization."""

from pulsimgui.models.component import ComponentType
from pulsimgui.models.project import Project, SimulationSettings


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


def test_project_simulation_settings_roundtrip_enable_newton_lm() -> None:
    """``enable_newton_lm`` must round-trip through the file schema so a
    project can persist the Levenberg-Marquardt Newton damping that some
    ill-conditioned multi-switch drives (e.g. a boost PFC stage composed
    with a switched VSI) need to converge — instead of relying on app
    preferences that a fresh GUI Run wouldn't carry."""
    settings = SimulationSettings(enable_newton_lm=True)

    payload = settings.to_dict()
    restored = SimulationSettings.from_dict(payload)

    assert payload["enable_newton_lm"] is True
    assert restored.enable_newton_lm is True


def test_project_simulation_settings_enable_newton_lm_defaults_false() -> None:
    """A legacy file (no ``enable_newton_lm`` key) defaults to False so
    pre-existing projects keep their bit-identical Newton behavior."""
    assert SimulationSettings().enable_newton_lm is False
    assert SimulationSettings.from_dict({"tstop": 1e-3}).enable_newton_lm is False


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


def test_project_load_migrates_legacy_global_control_sample_time_to_control_blocks() -> None:
    payload = {
        "name": "LegacyControl",
        "active_circuit": "main",
        "simulation_settings": {
            "control_mode": "discrete",
            "control_sample_time": 12e-6,
        },
        "circuits": {
            "main": {
                "name": "main",
                "components": [
                    {
                        "id": "3d9518e1-c7b2-4d73-ae2a-adfbf601e4bb",
                        "type": "PI_CONTROLLER",
                        "name": "PI1",
                        "x": 0.0,
                        "y": 0.0,
                        "rotation": 0,
                        "mirrored_h": False,
                        "mirrored_v": False,
                        "parameters": {"kp": 0.2, "ki": 10.0},
                        "pins": [],
                    }
                ],
                "wires": [],
            }
        },
    }

    project = Project.from_dict(payload)
    component = next(iter(project.get_active_circuit().components.values()))

    assert component.type == ComponentType.PI_CONTROLLER
    assert component.parameters["sample_time"] == 12e-6


def test_project_load_keeps_explicit_component_sample_time() -> None:
    payload = {
        "name": "ExplicitTs",
        "active_circuit": "main",
        "simulation_settings": {
            "control_mode": "discrete",
            "control_sample_time": 20e-6,
        },
        "circuits": {
            "main": {
                "name": "main",
                "components": [
                    {
                        "id": "12d6d8ff-2eab-41ea-ab31-3c1da9f7dd96",
                        "type": "PI_CONTROLLER",
                        "name": "PI1",
                        "x": 0.0,
                        "y": 0.0,
                        "rotation": 0,
                        "mirrored_h": False,
                        "mirrored_v": False,
                        "parameters": {"kp": 0.2, "ki": 10.0, "sample_time": 7e-6},
                        "pins": [],
                    }
                ],
                "wires": [],
            }
        },
    }

    project = Project.from_dict(payload)
    component = next(iter(project.get_active_circuit().components.values()))

    assert component.parameters["sample_time"] == 7e-6
