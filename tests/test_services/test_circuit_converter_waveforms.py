"""Waveform mapping regression tests for CircuitConverter voltage sources."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pulsimgui.services.circuit_converter import CircuitConverter


class _PulseParams:
    def __init__(self) -> None:
        self.v_initial = 0.0
        self.v_pulse = 1.0
        self.t_delay = 0.0
        self.t_rise = 1e-9
        self.t_fall = 1e-9
        self.t_width = 1e-6
        self.period = 2e-6


class _SineParams:
    def __init__(self) -> None:
        self.offset = 0.0
        self.amplitude = 1.0
        self.frequency = 50.0
        self.phase = 0.0


class _PWMParams:
    def __init__(self) -> None:
        self.v_low = 0.0
        self.v_high = 1.0
        self.frequency = 10000.0
        self.duty = 0.5
        self.dead_time = 0.0
        self.phase = 0.0
        self.rise_time = 0.0
        self.fall_time = 0.0


class _WaveformCircuit:
    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.pulse_sources: list[tuple[str, int, int, _PulseParams]] = []
        self.pwm_sources: list[tuple[str, int, int, _PWMParams]] = []
        self.sine_sources: list[tuple[str, int, int, _SineParams]] = []

    @staticmethod
    def ground() -> int:
        return 0

    def add_node(self, name: str) -> int:
        idx = self.nodes.get(name)
        if idx is None:
            idx = len(self.nodes) + 1
            self.nodes[name] = idx
        return idx

    def add_voltage_source(self, *_args, **_kwargs) -> None:
        raise AssertionError("Expected pulse/pwm/sine path, not dc source")

    def add_pulse_voltage_source(self, name: str, npos: int, nneg: int, params: _PulseParams) -> None:
        self.pulse_sources.append((name, npos, nneg, params))

    def add_pwm_voltage_source(self, name: str, npos: int, nneg: int, params: _PWMParams) -> None:
        self.pwm_sources.append((name, npos, nneg, params))

    def add_sine_voltage_source(self, name: str, npos: int, nneg: int, params: _SineParams) -> None:
        self.sine_sources.append((name, npos, nneg, params))


def _build_voltage_source_circuit(waveform: dict) -> dict:
    return {
        "components": [
            {
                "id": "vs-1",
                "type": "VOLTAGE_SOURCE",
                "name": "Vgate",
                "parameters": {"waveform": waveform},
                "pin_nodes": ["1", "0"],
            }
        ],
        "node_map": {"vs-1": ["1", "0"]},
        "node_aliases": {"1": "GATE", "0": "0"},
    }


def test_converter_accepts_legacy_pulse_waveform_keys() -> None:
    fake_module = SimpleNamespace(
        Circuit=_WaveformCircuit,
        PulseParams=_PulseParams,
        SineParams=_SineParams,
        PWMParams=_PWMParams,
    )
    converter = CircuitConverter(fake_module)

    converted = converter.build(
        _build_voltage_source_circuit(
            {
                "type": "pulse",
                "v1": 0.0,
                "v2": 12.0,
                "td": 2e-6,
                "tr": 3e-9,
                "tf": 4e-9,
                "pw": 25e-6,
                "per": 50e-6,
            }
        )
    )

    assert len(converted.pulse_sources) == 1
    _name, _npos, _nneg, params = converted.pulse_sources[0]
    assert params.v_initial == pytest.approx(0.0)
    assert params.v_pulse == pytest.approx(12.0)
    assert params.t_delay == pytest.approx(2e-6)
    assert params.t_rise == pytest.approx(3e-9)
    assert params.t_fall == pytest.approx(4e-9)
    assert params.t_width == pytest.approx(25e-6)
    assert params.period == pytest.approx(50e-6)


def test_converter_accepts_legacy_pwm_waveform_keys_and_percent_duty() -> None:
    fake_module = SimpleNamespace(
        Circuit=_WaveformCircuit,
        PulseParams=_PulseParams,
        SineParams=_SineParams,
        PWMParams=_PWMParams,
    )
    converter = CircuitConverter(fake_module)

    converted = converter.build(
        _build_voltage_source_circuit(
            {
                "type": "pwm",
                "vlow": -1.0,
                "vhigh": 9.0,
                "freq": 40_000.0,
                "duty": 35.0,
                "tr": 5e-9,
                "tf": 7e-9,
            }
        )
    )

    assert len(converted.pwm_sources) == 1
    _name, _npos, _nneg, params = converted.pwm_sources[0]
    assert params.v_low == pytest.approx(-1.0)
    assert params.v_high == pytest.approx(9.0)
    assert params.frequency == pytest.approx(40_000.0)
    assert params.duty == pytest.approx(0.35)
    assert params.rise_time == pytest.approx(5e-9)
    assert params.fall_time == pytest.approx(7e-9)
