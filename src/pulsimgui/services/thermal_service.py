"""Synthetic thermal analysis utilities.

This module offers a lightweight placeholder implementation that generates
thermal network information, temperature traces, and loss summaries derived
from the current schematic. The data is entirely synthetic but deterministic,
which makes it useful for UI development and testing until the thermal solver
is wired in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import TYPE_CHECKING, Sequence

from PySide6.QtCore import QObject, Signal

from pulsimgui.services.simulation_service import SimulationResult

if TYPE_CHECKING:  # pragma: no cover - imported only for typing
    from pulsimgui.models.circuit import Circuit
    from pulsimgui.models.component import Component


@dataclass
class ThermalStage:
    """Single RC stage inside a device thermal network."""

    name: str
    resistance: float
    capacitance: float
    temperature: float


@dataclass
class ThermalDeviceResult:
    """Synthetic thermal metrics for a single component."""

    component_id: str
    component_name: str
    stages: list[ThermalStage] = field(default_factory=list)
    temperature_trace: list[float] = field(default_factory=list)
    conduction_loss: float = 0.0
    switching_loss: float = 0.0

    @property
    def total_loss(self) -> float:
        """Total power loss in watts."""
        return self.conduction_loss + self.switching_loss

    @property
    def peak_temperature(self) -> float:
        """Maximum junction temperature sample."""
        return max(self.temperature_trace, default=0.0)


@dataclass
class ThermalResult:
    """Collection of thermal results for the active circuit."""

    time: list[float] = field(default_factory=list)
    devices: list[ThermalDeviceResult] = field(default_factory=list)
    ambient_temperature: float = 25.0

    def device_names(self) -> list[str]:
        """Return ordered list of component names."""
        return [device.component_name for device in self.devices]

    def total_losses(self) -> float:
        """Total power loss for every device."""
        return sum(device.total_loss for device in self.devices)


class ThermalAnalysisService(QObject):
    """Generate deterministic placeholder thermal data."""

    result_generated = Signal(ThermalResult)

    def __init__(self, ambient_temperature: float = 25.0, parent: QObject | None = None):
        super().__init__(parent)
        self._ambient_temperature = ambient_temperature

    @property
    def ambient_temperature(self) -> float:
        """Return ambient temperature used for generation."""
        return self._ambient_temperature

    @ambient_temperature.setter
    def ambient_temperature(self, value: float) -> None:
        self._ambient_temperature = value

    def build_result(
        self,
        circuit: Circuit | None,
        electrical_result: SimulationResult | None = None,
        max_devices: int = 6,
    ) -> ThermalResult:
        """Generate a synthetic thermal data set from the provided circuit."""
        if circuit is None or not circuit.components:
            return self._empty_result(electrical_result)

        ordered_components = self._select_components(circuit, max_devices)
        timeline = self._resolve_time_axis(electrical_result)
        normalized_time = self._normalize_time(timeline)
        devices = [
            self._build_device_result(comp, index, normalized_time, timeline)
            for index, comp in enumerate(ordered_components)
        ]

        result = ThermalResult(
            time=timeline,
            devices=devices,
            ambient_temperature=self._ambient_temperature,
        )
        self.result_generated.emit(result)
        return result

    def _select_components(self, circuit: Circuit, max_devices: int) -> Sequence[Component]:
        components = list(circuit.components.values())
        if not components:
            return []
        components.sort(key=lambda comp: comp.name or comp.type.name)
        return components[:max_devices]

    def _resolve_time_axis(self, electrical_result: SimulationResult | None) -> list[float]:
        if electrical_result and electrical_result.time:
            return list(electrical_result.time)
        # Default 0 .. 10 ms timeline
        samples = 200
        duration = 10e-3
        return [i * (duration / samples) for i in range(samples + 1)]

    def _normalize_time(self, time_axis: Sequence[float]) -> list[float]:
        if not time_axis:
            return []
        start = time_axis[0]
        end = time_axis[-1]
        span = end - start
        if span <= 0:
            return [0.0 for _ in time_axis]
        return [(t - start) / span for t in time_axis]

    def _build_device_result(
        self,
        component: Component,
        position_index: int,
        normalized_time: Sequence[float],
        timeline: Sequence[float],
    ) -> ThermalDeviceResult:
        base_rise = 20.0 + position_index * 8.0
        time_constant = 2.5 + position_index * 0.3
        temps = [
            self._ambient_temperature
            + base_rise * (1 - math.exp(-t * time_constant))
            for t in normalized_time
        ] or [self._ambient_temperature]

        conduction_loss = 3.0 + position_index * 0.8
        switching_loss = 1.5 + position_index * 0.6

        stages = self._build_stages(component, temps)

        return ThermalDeviceResult(
            component_id=str(component.id),
            component_name=component.name or component.type.name,
            stages=stages,
            temperature_trace=list(temps),
            conduction_loss=conduction_loss,
            switching_loss=switching_loss,
        )

    def _build_stages(
        self,
        component: Component,
        temps: Sequence[float],
    ) -> list[ThermalStage]:
        if not temps:
            sample_temp = self._ambient_temperature
        else:
            sample_temp = temps[-1]

        stages: list[ThermalStage] = []
        for index in range(3):
            resistance = 0.3 + index * 0.15
            capacitance = 0.02 + index * 0.01
            temp_index = int(len(temps) * ((index + 1) / 3.0)) - 1
            temp_index = max(0, min(temp_index, len(temps) - 1))
            stage_temp = temps[temp_index] if temps else sample_temp
            stages.append(
                ThermalStage(
                    name=f"{component.name or component.type.name} RC{index + 1}",
                    resistance=round(resistance, 3),
                    capacitance=round(capacitance, 3),
                    temperature=stage_temp,
                )
            )
        return stages

    def _empty_result(self, electrical_result: SimulationResult | None) -> ThermalResult:
        return ThermalResult(time=self._resolve_time_axis(electrical_result), devices=[])
