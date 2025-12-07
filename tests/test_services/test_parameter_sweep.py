"""Tests for parameter sweep helpers."""

from pulsimgui.services.simulation_service import (
    ParameterSweepResult,
    ParameterSweepRun,
    ParameterSweepSettings,
    SimulationResult,
)


def test_parameter_sweep_settings_linear_values():
    settings = ParameterSweepSettings(
        component_id="1",
        component_name="R1",
        parameter_name="resistance",
        start_value=10,
        end_value=50,
        points=5,
        scale="linear",
        output_signal="V(out)",
        parallel_workers=1,
        baseline_value=10,
    )

    assert settings.generate_values() == [10.0, 20.0, 30.0, 40.0, 50.0]
    assert settings.compute_scale_factor(20.0) == 2.0


def test_parameter_sweep_result_combines_signals():
    settings = ParameterSweepSettings(
        component_id="1",
        component_name="R1",
        parameter_name="resistance",
        start_value=1,
        end_value=2,
        points=2,
        scale="linear",
        output_signal="V(out)",
        parallel_workers=1,
        baseline_value=1,
    )

    run_a = SimulationResult(time=[0, 1], signals={"V(out)": [0.0, 1.0]})
    run_b = SimulationResult(time=[0, 1], signals={"V(out)": [0.0, 2.0]})
    sweep_result = ParameterSweepResult(
        settings=settings,
        runs=[
            ParameterSweepRun(order=1, parameter_value=2.0, result=run_b),
            ParameterSweepRun(order=0, parameter_value=1.0, result=run_a),
        ],
    )

    combined = sweep_result.to_waveform_result()
    assert combined.time == [0, 1]
    assert list(combined.signals.keys()) == [
        "V(out) [resistance=1]",
        "V(out) [resistance=2]",
    ]
    assert combined.statistics["sweep_points"] == 2

    xs, ys = sweep_result.xy_dataset()
    assert xs == [1.0, 2.0]
    assert ys == [1.0, 2.0]
