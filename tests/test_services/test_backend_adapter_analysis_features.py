"""Tests for post-processing/frequency integration in backend_adapter."""

from __future__ import annotations

from types import SimpleNamespace

from pulsimgui.services import backend_adapter as backend_adapter_module
from pulsimgui.services.backend_adapter import BackendInfo, PlaceholderBackend, PulsimBackend
from pulsimgui.services.backend_types import ACSettings, TransientResult
from pulsimgui.services.simulation_service import SimulationSettings


class _DummyConverter:
    """Lightweight circuit converter test double."""

    def __init__(self, _module) -> None:
        pass

    def build(self, _data):
        return SimpleNamespace(name="dummy_circuit")


def test_placeholder_backend_post_processing_returns_success() -> None:
    """Placeholder backend should provide deterministic synthetic post-processing output."""
    backend = PlaceholderBackend()
    transient = TransientResult(
        time=[0.0, 1e-6, 2e-6, 3e-6],
        signals={"V(out)": [0.0, 1.0, 0.5, 0.0]},
    )

    result = backend.run_post_processing(
        transient,
        [
            {"job_id": "td", "kind": "time_domain", "signals": ["V(out)"]},
            {"job_id": "sp", "kind": "spectral", "signals": ["V(out)"]},
        ],
    )

    assert result.success
    assert result.jobs
    assert result.jobs[0].success


def test_pulsim_backend_maps_post_processing_results(monkeypatch) -> None:
    """Adapter should map core post-processing structures to GUI dataclasses."""
    monkeypatch.setattr(backend_adapter_module, "CircuitConverter", _DummyConverter)

    class _SimulationResult:
        def __init__(self, **kwargs) -> None:
            self.time = list(kwargs.get("time", []))
            self.virtual_channels = dict(kwargs.get("virtual_channels", {}))
            self.signals = dict(kwargs.get("signals", {}))

    class _PostProcessingJob:
        def __init__(self) -> None:
            self.job_id = ""
            self.kind = ""
            self.signals = []

    class _PostProcessingOptions:
        def __init__(self) -> None:
            self.jobs = []

    def _run_post_processing(sim_result, _options):
        assert "V(out)" in sim_result.virtual_channels
        return {
            "success": True,
            "jobs": [
                {
                    "job_id": "td1",
                    "kind": "time_domain",
                    "success": True,
                    "diagnostic": "ok",
                    "diagnostic_message": "",
                    "scalar_metrics": {
                        "rms": {
                            "name": "rms",
                            "value": 5.0,
                            "unit": "V",
                            "domain": "time",
                            "source_signal": "V(out)",
                        }
                    },
                    "spectrum_bins": [
                        {"frequency_hz": 1000.0, "magnitude": 1.25, "phase_deg": -5.0}
                    ],
                    "harmonics": [
                        {
                            "harmonic_number": 1,
                            "frequency_hz": 1000.0,
                            "magnitude": 1.25,
                            "phase_deg": -5.0,
                            "magnitude_pct_fundamental": 100.0,
                        }
                    ],
                    "undefined_metrics": [
                        {
                            "name": "thd_pct",
                            "reason": "undefined_metric",
                            "reason_message": "fundamental is zero",
                        }
                    ],
                    "sample_count": 64,
                    "runtime_seconds": 0.001,
                    "signal_names": ["V(out)"],
                }
            ],
        }

    module = SimpleNamespace(
        __version__="0.7.2",
        __file__="/tmp/pulsim/__init__.py",
        SimulationResult=_SimulationResult,
        PostProcessingJob=_PostProcessingJob,
        PostProcessingOptions=_PostProcessingOptions,
        run_post_processing=_run_post_processing,
    )
    info = BackendInfo(
        identifier="pulsim",
        name="Pulsim",
        version="0.7.2",
        status="available",
    )
    backend = PulsimBackend(module, info)

    transient = TransientResult(
        time=[0.0, 1e-6, 2e-6],
        signals={"V(out)": [0.0, 1.0, 0.5]},
    )
    result = backend.run_post_processing(transient, [{"job_id": "td1", "kind": "time_domain"}])

    assert result.success
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.scalar_metrics["rms"].value == 5.0
    assert job.spectrum_bins[0].amplitude == 1.25
    assert job.harmonics[0].order == 1
    assert job.undefined_metrics[0].reason == "undefined_metric"
    assert job.sample_count == 64


def test_pulsim_backend_frequency_analysis_uses_native_option_fields(monkeypatch) -> None:
    """Frequency adapter should map GUI settings into core option/port fields."""
    monkeypatch.setattr(backend_adapter_module, "CircuitConverter", _DummyConverter)

    class _FrequencyAnalysisPort:
        def __init__(self) -> None:
            self.positive_node = ""
            self.negative_node = ""

    class _FrequencyAnalysisOptions:
        def __init__(self) -> None:
            self.enabled = False
            self.mode = None
            self.anchor_mode = None
            self.sweep_scale = None
            self.f_start_hz = 0.0
            self.f_stop_hz = 0.0
            self.points = 0
            self.injection_current_amplitude = 0.0
            self.perturbation_port = _FrequencyAnalysisPort()
            self.output_port = _FrequencyAnalysisPort()

    class _FrequencyAnalysisMode:
        OpenLoopTransfer = "open_loop_transfer"
        ClosedLoopTransfer = "closed_loop_transfer"
        InputImpedance = "input_impedance"
        OutputImpedance = "output_impedance"

    class _FrequencyAnchorMode:
        Auto = "auto"
        DC = "dc"
        Periodic = "periodic"
        Averaged = "averaged"

    class _FrequencySweepScale:
        Logarithmic = "log"
        Linear = "linear"

    captured: dict[str, object] = {}

    def _run_frequency_analysis(_circuit, options, raise_on_failure=False):
        captured["raise_on_failure"] = raise_on_failure
        captured["options"] = options
        return SimpleNamespace(
            success=True,
            diagnostic=SimpleNamespace(value="ok", name="Ok"),
            message="",
            mode=_FrequencyAnalysisMode.OpenLoopTransfer,
            anchor_mode_selected=_FrequencyAnchorMode.DC,
            failed_point_index=-1,
            failed_frequency_hz=0.0,
            frequency_hz=[10.0, 100.0, 1000.0],
            magnitude_db=[0.0, -3.0, -20.0],
            phase_deg=[0.0, -45.0, -89.0],
            gain_margin_db=10.0,
            phase_margin_deg=60.0,
            gain_crossover_hz=1200.0,
            phase_crossover_hz=9000.0,
            gain_crossover_reason=SimpleNamespace(value="none"),
            phase_crossover_reason=SimpleNamespace(value="none"),
            phase_margin_reason=SimpleNamespace(value="none"),
            gain_margin_reason=SimpleNamespace(value="none"),
        )

    module = SimpleNamespace(
        __version__="0.7.2",
        __file__="/tmp/pulsim/__init__.py",
        FrequencyAnalysisOptions=_FrequencyAnalysisOptions,
        FrequencyAnalysisPort=_FrequencyAnalysisPort,
        FrequencyAnalysisMode=_FrequencyAnalysisMode,
        FrequencyAnchorMode=_FrequencyAnchorMode,
        FrequencySweepScale=_FrequencySweepScale,
        run_frequency_analysis=_run_frequency_analysis,
    )

    info = BackendInfo(
        identifier="pulsim",
        name="Pulsim",
        version="0.7.2",
        status="available",
    )
    backend = PulsimBackend(module, info)
    settings = ACSettings(
        f_start=10.0,
        f_stop=100000.0,
        points_per_decade=20,
        input_source="vin",
        output_nodes=["vout"],
        anchor_mode="dc",
        sweep_scale="log",
        injection_node="vin,0",
        measurement_node="vout",
    )

    result = backend.run_frequency_analysis({}, settings)

    assert result.success
    assert result.is_valid
    assert result.frequencies == [10.0, 100.0, 1000.0]

    options = captured["options"]
    assert isinstance(options, _FrequencyAnalysisOptions)
    assert options.f_start_hz == 10.0
    assert options.f_stop_hz == 100000.0
    assert options.points > 0
    assert options.anchor_mode == _FrequencyAnchorMode.DC
    assert options.sweep_scale == _FrequencySweepScale.Logarithmic
    assert options.perturbation_port.positive_node == "vin"
    assert options.perturbation_port.negative_node == "0"
    assert options.output_port.positive_node == "vout"
    assert options.output_port.negative_node == "0"


def test_pulsim_backend_capabilities_include_new_analysis_features(monkeypatch) -> None:
    """Capability detection should expose post-processing/frequency/averaged flags."""
    monkeypatch.setattr(backend_adapter_module, "CircuitConverter", _DummyConverter)

    module = SimpleNamespace(
        __version__="0.7.2",
        __file__="/tmp/pulsim/__init__.py",
        run_post_processing=lambda *_args, **_kwargs: None,
        run_frequency_analysis=lambda *_args, **_kwargs: None,
        AveragedConverterOptions=object,
    )

    info = BackendInfo(
        identifier="pulsim",
        name="Pulsim",
        version="0.7.2",
        status="available",
    )
    backend = PulsimBackend(module, info)

    assert "post_processing" in backend.capabilities
    assert "frequency_analysis" in backend.capabilities
    assert "averaged" in backend.capabilities


def test_pulsim_backend_builds_averaged_converter_options(monkeypatch) -> None:
    """Transient options should carry averaged converter settings when provided."""
    monkeypatch.setattr(backend_adapter_module, "CircuitConverter", _DummyConverter)

    class _SimulationOptions:
        def __init__(self) -> None:
            self.averaged_converter = None

    class _AveragedConverterOptions:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    module = SimpleNamespace(
        __version__="0.7.2",
        __file__="/tmp/pulsim/__init__.py",
        SimulationOptions=_SimulationOptions,
        AveragedConverterOptions=_AveragedConverterOptions,
        AveragedConverterTopology={"buck": "buck_topology"},
        AveragedOperatingMode={"ccm": "ccm_mode"},
        AveragedEnvelopePolicy={"strict": "strict_policy"},
    )

    info = BackendInfo(
        identifier="pulsim",
        name="Pulsim",
        version="0.7.2",
        status="available",
    )
    backend = PulsimBackend(module, info)
    settings = SimulationSettings(
        averaged_options={
            "topology": "buck",
            "mode": "ccm",
            "envelope": "strict",
        }
    )

    options = backend._build_simulation_options(
        settings,
        dt=1e-6,
        newton_opts=SimpleNamespace(),
        linear_solver=None,
        circuit_data=None,
    )

    assert options.averaged_converter is not None
    assert options.averaged_converter.kwargs["topology"] == "buck_topology"
    assert options.averaged_converter.kwargs["mode"] == "ccm_mode"
    assert options.averaged_converter.kwargs["envelope"] == "strict_policy"
