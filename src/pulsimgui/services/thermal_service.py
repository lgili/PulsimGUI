"""Thermal analysis service with backend integration.

This module provides thermal analysis with real backend support and synthetic
fallback. When a backend with thermal capability is available, it uses the
real thermal simulator. Otherwise, it generates synthetic data for UI
development and testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
from typing import TYPE_CHECKING, Any, Sequence

from PySide6.QtCore import QObject, Signal

from pulsimgui.services.simulation_service import SimulationResult

if TYPE_CHECKING:  # pragma: no cover - imported only for typing
    from pulsimgui.models.circuit import Circuit
    from pulsimgui.models.component import Component
    from pulsimgui.services.backend_adapter import SimulationBackend
    from pulsimgui.services.backend_types import (
        ThermalResult as BackendThermalResult,
        ThermalSettings,
        TransientResult,
    )

logger = logging.getLogger(__name__)


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
    switching_loss_on: float = 0.0
    switching_loss_off: float = 0.0
    reverse_recovery_loss: float = 0.0
    steady_state_temperature: float = 0.0
    thermal_limit: float | None = None

    def __post_init__(self) -> None:
        detailed_switching = (
            float(self.switching_loss_on)
            + float(self.switching_loss_off)
            + float(self.reverse_recovery_loss)
        )
        if detailed_switching > 0.0:
            self.switching_loss = detailed_switching
        if not self.steady_state_temperature and self.temperature_trace:
            self.steady_state_temperature = float(self.temperature_trace[-1])

    @property
    def total_loss(self) -> float:
        """Total power loss in watts."""
        return self.conduction_loss + self.switching_loss

    @property
    def peak_temperature(self) -> float:
        """Maximum junction temperature sample."""
        return max(self.temperature_trace, default=0.0)

    @property
    def exceeds_limit(self) -> bool:
        """Return True when peak temperature exceeds configured thermal limit."""
        if self.thermal_limit is None:
            return False
        return self.peak_temperature > float(self.thermal_limit)


@dataclass
class ThermalResult:
    """Collection of thermal results for the active circuit."""

    time: list[float] = field(default_factory=list)
    devices: list[ThermalDeviceResult] = field(default_factory=list)
    ambient_temperature: float = 25.0
    is_synthetic: bool = True
    error_message: str = ""

    def device_names(self) -> list[str]:
        """Return ordered list of component names."""
        return [device.component_name for device in self.devices]

    def total_losses(self) -> float:
        """Total power loss for every device."""
        return sum(device.total_loss for device in self.devices)


class ThermalAnalysisService(QObject):
    """Thermal analysis with backend integration and synthetic fallback."""

    result_generated = Signal(ThermalResult)

    def __init__(
        self,
        ambient_temperature: float = 25.0,
        include_switching_losses: bool = True,
        include_conduction_losses: bool = True,
        thermal_network: str = "foster",
        allow_synthetic_fallback: bool = True,
        backend: "SimulationBackend | None" = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._ambient_temperature = ambient_temperature
        self._include_switching_losses = bool(include_switching_losses)
        self._include_conduction_losses = bool(include_conduction_losses)
        self._thermal_network = str(thermal_network or "foster").strip().lower()
        self._allow_synthetic_fallback = bool(allow_synthetic_fallback)
        if self._thermal_network not in {"foster", "cauer"}:
            self._thermal_network = "foster"
        self._backend = backend

    @property
    def ambient_temperature(self) -> float:
        """Return ambient temperature used for generation."""
        return self._ambient_temperature

    @ambient_temperature.setter
    def ambient_temperature(self, value: float) -> None:
        self._ambient_temperature = value

    @property
    def backend(self) -> "SimulationBackend | None":
        """Return the current backend."""
        return self._backend

    @backend.setter
    def backend(self, value: "SimulationBackend | None") -> None:
        """Set the backend for thermal analysis."""
        self._backend = value

    @property
    def include_switching_losses(self) -> bool:
        """Whether switching losses are included when running thermal analysis."""
        return self._include_switching_losses

    @include_switching_losses.setter
    def include_switching_losses(self, value: bool) -> None:
        self._include_switching_losses = bool(value)

    @property
    def include_conduction_losses(self) -> bool:
        """Whether conduction losses are included when running thermal analysis."""
        return self._include_conduction_losses

    @include_conduction_losses.setter
    def include_conduction_losses(self, value: bool) -> None:
        self._include_conduction_losses = bool(value)

    @property
    def thermal_network(self) -> str:
        """Selected thermal network model for backend-capable analysis."""
        return self._thermal_network

    @thermal_network.setter
    def thermal_network(self, value: str) -> None:
        network = str(value or "foster").strip().lower()
        self._thermal_network = network if network in {"foster", "cauer"} else "foster"

    def build_result(
        self,
        circuit: "Circuit | None",
        electrical_result: SimulationResult | None = None,
        max_devices: int = 6,
        circuit_data: dict | None = None,
    ) -> ThermalResult:
        """Build thermal result, trying real backend first then synthetic fallback.

        Args:
            circuit: GUI Circuit model for synthetic generation.
            electrical_result: Electrical simulation result for time base.
            max_devices: Maximum devices for synthetic generation.
            circuit_data: Serialized circuit data for backend (if available).

        Returns:
            ThermalResult with is_synthetic=False if from real backend,
            or is_synthetic=True if synthetic fallback was used.
        """
        if circuit is None or not circuit.components:
            return self._empty_result(electrical_result)

        # Try real backend first if available
        if self._backend is not None and self._backend.has_capability("thermal"):
            result = self._try_backend_thermal(circuit, electrical_result, circuit_data)
            if result is not None:
                self.result_generated.emit(result)
                return result
            if not self._allow_synthetic_fallback:
                result = ThermalResult(
                    time=self._resolve_time_axis(electrical_result),
                    devices=[],
                    ambient_temperature=self._ambient_temperature,
                    is_synthetic=False,
                    error_message=(
                        "Backend thermal analysis failed and synthetic fallback is disabled."
                    ),
                )
                self.result_generated.emit(result)
                return result
            logger.debug("Backend thermal analysis failed, using synthetic fallback")
        elif not self._allow_synthetic_fallback:
            result = ThermalResult(
                time=self._resolve_time_axis(electrical_result),
                devices=[],
                ambient_temperature=self._ambient_temperature,
                is_synthetic=False,
                error_message=(
                    "Thermal backend capability unavailable and synthetic fallback is disabled."
                ),
            )
            self.result_generated.emit(result)
            return result

        # Fall back to synthetic generation
        result = self._build_synthetic_result(circuit, electrical_result, max_devices)
        self.result_generated.emit(result)
        return result

    def _try_backend_thermal(
        self,
        circuit: "Circuit",
        electrical_result: SimulationResult | None,
        circuit_data: dict | None,
    ) -> ThermalResult | None:
        """Attempt to run thermal analysis via the backend."""
        if circuit_data is None:
            # Try to build circuit_data from GUI circuit
            circuit_data = self._circuit_to_data(circuit)
            if circuit_data is None:
                return None

        try:
            from pulsimgui.services.backend_types import ThermalSettings, TransientResult

            # Build settings
            settings = ThermalSettings(
                ambient_temperature=self._ambient_temperature,
                include_switching_losses=self._include_switching_losses,
                include_conduction_losses=self._include_conduction_losses,
                thermal_network=self._thermal_network,
            )

            # Build transient result for backend
            transient_result = self._simulation_to_transient(electrical_result)

            # Run backend thermal analysis
            backend_result = self._backend.run_thermal(circuit_data, transient_result, settings)

            # Check for errors
            if backend_result.error_message:
                logger.warning(f"Backend thermal error: {backend_result.error_message}")
                return None

            # Convert to service format
            return self._convert_backend_result(backend_result)

        except Exception as exc:
            logger.warning(f"Backend thermal analysis failed: {exc}")
            return None

    def _circuit_to_data(self, circuit: "Circuit") -> dict | None:
        """Convert GUI Circuit to serialized data for backend."""
        try:
            # Use the circuit's serialization method if available
            if hasattr(circuit, "to_dict"):
                return circuit.to_dict()
            # Build minimal data structure
            components = []
            for comp_id, comp in circuit.components.items():
                comp_data = {
                    "id": str(comp_id),
                    "type": comp.type.name,
                    "name": comp.name or comp.type.name,
                    "parameters": dict(comp.parameters) if comp.parameters else {},
                }
                # Add pin nodes if available
                if hasattr(comp, "pin_nodes"):
                    comp_data["pin_nodes"] = list(comp.pin_nodes)
                components.append(comp_data)
            return {"components": components}
        except Exception as exc:
            logger.debug(f"Failed to convert circuit to data: {exc}")
            return None

    def _simulation_to_transient(
        self, electrical_result: SimulationResult | None
    ) -> "TransientResult":
        """Convert SimulationResult to TransientResult for backend."""
        from pulsimgui.services.backend_types import TransientResult

        if electrical_result is None:
            return TransientResult()

        return TransientResult(
            time=list(electrical_result.time) if electrical_result.time else [],
            signals=dict(electrical_result.signals) if electrical_result.signals else {},
        )

    def _convert_backend_result(
        self, backend_result: "BackendThermalResult"
    ) -> ThermalResult:
        """Convert backend ThermalResult to service ThermalResult."""
        devices = []
        for dev in backend_result.devices:
            # Convert FosterStage to ThermalStage
            stages = []
            for i, stage in enumerate(dev.foster_stages):
                stages.append(
                    ThermalStage(
                        name=f"{dev.name} RC{i + 1}",
                        resistance=stage.resistance,
                        capacitance=stage.capacitance,
                        temperature=dev.peak_temperature,  # Use peak temp for stage
                    )
                )

            # Build device result
            conduction = float(getattr(dev.losses, "conduction", 0.0))
            switching_on = float(getattr(dev.losses, "switching_on", 0.0))
            switching_off = float(getattr(dev.losses, "switching_off", 0.0))
            reverse_recovery = float(getattr(dev.losses, "reverse_recovery", 0.0))
            switching_total = switching_on + switching_off + reverse_recovery
            if switching_total <= 0.0:
                switching_total = float(getattr(dev.losses, "switching_total", 0.0))

            trace = list(getattr(dev, "junction_temperature", []))
            steady_state = float(
                getattr(
                    dev,
                    "steady_state_temperature",
                    trace[-1] if trace else self._ambient_temperature,
                )
            )
            devices.append(
                ThermalDeviceResult(
                    component_id=str(getattr(dev, "name", "unknown")),
                    component_name=str(getattr(dev, "name", "unknown")),
                    stages=stages,
                    temperature_trace=trace,
                    conduction_loss=conduction,
                    switching_loss=switching_total,
                    switching_loss_on=switching_on,
                    switching_loss_off=switching_off,
                    reverse_recovery_loss=reverse_recovery,
                    steady_state_temperature=steady_state,
                    thermal_limit=getattr(dev, "thermal_limit", None),
                )
            )

        return ThermalResult(
            time=list(backend_result.time),
            devices=devices,
            ambient_temperature=backend_result.ambient_temperature,
            is_synthetic=backend_result.is_synthetic,
            error_message=backend_result.error_message,
        )

    def _build_synthetic_result(
        self,
        circuit: "Circuit",
        electrical_result: SimulationResult | None,
        max_devices: int,
    ) -> ThermalResult:
        """Generate synthetic thermal data from the circuit."""
        ordered_components = self._select_components(circuit, max_devices)
        timeline = self._resolve_time_axis(electrical_result)
        normalized_time = self._normalize_time(timeline)
        devices = [
            self._build_device_result(comp, index, normalized_time, timeline)
            for index, comp in enumerate(ordered_components)
        ]

        return ThermalResult(
            time=timeline,
            devices=devices,
            ambient_temperature=self._ambient_temperature,
            is_synthetic=True,
        )

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
        if not self._include_conduction_losses:
            conduction_loss = 0.0
        if not self._include_switching_losses:
            switching_loss = 0.0
        switching_on = switching_loss * 0.65
        switching_off = switching_loss * 0.35
        thermal_limit = self._resolve_thermal_limit(component)

        stages = self._build_stages(component, temps)

        return ThermalDeviceResult(
            component_id=str(component.id),
            component_name=component.name or component.type.name,
            stages=stages,
            temperature_trace=list(temps),
            conduction_loss=conduction_loss,
            switching_loss=switching_loss,
            switching_loss_on=switching_on,
            switching_loss_off=switching_off,
            reverse_recovery_loss=0.0,
            steady_state_temperature=temps[-1] if temps else self._ambient_temperature,
            thermal_limit=thermal_limit,
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
        return ThermalResult(
            time=self._resolve_time_axis(electrical_result),
            devices=[],
            is_synthetic=True,
        )

    @staticmethod
    def _resolve_thermal_limit(component: "Component") -> float | None:
        """Best-effort extraction of component thermal limit from parameter aliases."""
        params = dict(getattr(component, "parameters", {}) or {})
        for key in ("thermal_limit", "tj_max", "temperature_limit", "temp_max"):
            value = params.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None
