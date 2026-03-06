"""Tests for backend-owned virtual probe channels in PulsimBackend."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pulsimgui.services.backend_adapter import BackendCallbacks, BackendInfo, PulsimBackend
from pulsimgui.services.simulation_service import SimulationSettings


class _FakeProbeMetadata:
    def __init__(self, component_type: str) -> None:
        self.component_type = component_type


class _FakeProbeCircuit:
    def __init__(self) -> None:
        self._nodes: dict[str, int] = {}

    @staticmethod
    def ground() -> int:
        return 0

    def add_node(self, name: str) -> int:
        if name not in self._nodes:
            self._nodes[name] = len(self._nodes) + 1
        return self._nodes[name]

    def add_voltage_source(self, *_: Any) -> None: ...

    def add_resistor(self, *_: Any) -> None: ...

    def node_names(self) -> list[str]:
        return list(self._nodes.keys())

    def num_nodes(self) -> int:
        return len(self._nodes)

    def num_branches(self) -> int:
        return 0

    def set_timestep(self, _: float) -> None: ...

    def virtual_channel_metadata(self) -> dict[str, _FakeProbeMetadata]:
        return {
            "VP1": _FakeProbeMetadata("voltage_probe"),
            "IP1": _FakeProbeMetadata("current_probe"),
        }

    def evaluate_virtual_signals(self, state: list[float]) -> dict[str, float]:
        voltage = float(state[0]) if state else 0.0
        return {"VP1": voltage, "IP1": 0.75}


def _build_backend() -> PulsimBackend:
    def run_transient(*_args: Any, **_kwargs: Any) -> tuple[list[float], list[list[float]], bool, str]:
        return [0.0, 1e-3], [[2.0], [3.0]], True, ""

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeProbeCircuit,
        run_transient=run_transient,
    )
    return PulsimBackend(
        fake_module,
        BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="2.0.0",
            status="available",
        ),
    )


def test_run_transient_populates_virtual_probe_channels() -> None:
    backend = _build_backend()
    settings = SimulationSettings(t_start=0.0, t_stop=1e-3, t_step=1e-6)
    callbacks = BackendCallbacks(
        progress=lambda *_: None,
        data_point=lambda *_: None,
        check_cancelled=lambda: False,
        wait_if_paused=lambda: None,
    )
    circuit_data = {
        "components": [
            {
                "id": "v1",
                "type": "VOLTAGE_SOURCE",
                "name": "V1",
                "parameters": {"waveform": {"type": "dc", "value": 5.0}},
                "pin_nodes": ["1", "0"],
            },
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 10.0},
                "pin_nodes": ["1", "0"],
            },
        ],
        "node_map": {"v1": ["1", "0"], "r1": ["1", "0"]},
        "node_aliases": {"1": "OUT", "0": "0"},
    }

    result = backend.run_transient(circuit_data, settings, callbacks)

    assert result.error_message == ""
    assert result.signals["VP1"] == [2.0, 3.0]
    assert result.signals["IP1"] == [0.75, 0.75]
