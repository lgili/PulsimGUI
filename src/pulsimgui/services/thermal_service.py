"""Thermal analysis service with strict backend-only execution."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any

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
    is_synthetic: bool = False
    error_message: str = ""

    def device_names(self) -> list[str]:
        """Return ordered list of component names."""
        return [device.component_name for device in self.devices]

    def total_losses(self) -> float:
        """Total power loss for every device."""
        return sum(device.total_loss for device in self.devices)


class ThermalAnalysisService(QObject):
    """Thermal analysis with strict backend-only execution."""

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
        # Legacy arg kept only for API compatibility; synthetic fallback is disabled.
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
        """Build thermal result strictly from backend thermal capability."""
        _ = max_devices  # Kept for backward API compatibility.
        if circuit is None or not circuit.components:
            result = self._error_result(
                electrical_result,
                "Circuit has no components for thermal analysis.",
            )
            self.result_generated.emit(result)
            return result

        if self._backend is None:
            result = self._error_result(
                electrical_result,
                "Thermal backend is not configured.",
            )
            self.result_generated.emit(result)
            return result

        if not self._is_backend_ready():
            result = self._error_result(
                electrical_result,
                "Thermal backend is unavailable. Install/select a real backend runtime.",
            )
            self.result_generated.emit(result)
            return result

        if not self._backend.has_capability("thermal"):
            result = self._error_result(
                electrical_result,
                "Thermal simulation is not supported by the active backend.",
            )
            self.result_generated.emit(result)
            return result

        result = self._try_backend_thermal(circuit, electrical_result, circuit_data)
        self.result_generated.emit(result)
        return result

    def _try_backend_thermal(
        self,
        circuit: "Circuit",
        electrical_result: SimulationResult | None,
        circuit_data: dict | None,
    ) -> ThermalResult:
        """Attempt to run thermal analysis via the backend."""
        if circuit_data is None:
            circuit_data = self._circuit_to_data(circuit)
            if circuit_data is None:
                return self._error_result(
                    electrical_result,
                    "Failed to serialize circuit for backend thermal analysis.",
                )

        try:
            from pulsimgui.services.backend_types import ThermalSettings, TransientResult

            settings = ThermalSettings(
                ambient_temperature=self._ambient_temperature,
                include_switching_losses=self._include_switching_losses,
                include_conduction_losses=self._include_conduction_losses,
                thermal_network=self._thermal_network,
            )

            transient_result = self._simulation_to_transient(electrical_result)

            backend_result = self._backend.run_thermal(circuit_data, transient_result, settings)

            if backend_result.error_message:
                logger.warning(f"Backend thermal error: {backend_result.error_message}")
                return self._error_result(electrical_result, backend_result.error_message)

            converted = self._convert_backend_result(backend_result, circuit_data)
            self._normalize_thermal_timelines(converted, electrical_result)
            if not converted.devices:
                return self._error_result(
                    electrical_result,
                    "Thermal backend returned no device traces.",
                )
            return converted

        except Exception as exc:
            logger.warning(f"Backend thermal analysis failed: {exc}")
            return self._error_result(
                electrical_result,
                f"Backend thermal analysis failed: {exc}",
            )

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
        self,
        backend_result: "BackendThermalResult",
        circuit_data: dict | None = None,
    ) -> ThermalResult:
        """Convert backend ThermalResult to service ThermalResult."""
        identity = self._build_component_identity_lookup(circuit_data)
        devices = []
        for dev in backend_result.devices:
            raw_name = str(getattr(dev, "name", "unknown") or "unknown")
            component_id, component_name = self._resolve_component_identity(raw_name, identity)

            # Convert FosterStage to ThermalStage
            stages = []
            for i, stage in enumerate(dev.foster_stages):
                stages.append(
                    ThermalStage(
                        name=f"{component_name} RC{i + 1}",
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
                    component_id=component_id,
                    component_name=component_name,
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

    def _normalize_thermal_timelines(
        self,
        result: ThermalResult,
        electrical_result: SimulationResult | None,
    ) -> None:
        """Ensure thermal traces have same length as the thermal time axis."""
        if not result.devices:
            return

        if not result.time and electrical_result and electrical_result.time:
            result.time = list(electrical_result.time)

        target_len = len(result.time)
        if target_len <= 0:
            return

        for device in result.devices:
            trace = list(device.temperature_trace)
            if not trace:
                continue
            needs_resample = len(trace) != target_len
            device.temperature_trace = self._resample_trace(trace, target_len)
            if needs_resample and device.temperature_trace:
                device.steady_state_temperature = float(device.temperature_trace[-1])

    @staticmethod
    def _resample_trace(values: list[float], target_len: int) -> list[float]:
        if target_len <= 0:
            return []
        if not values:
            return []
        source_len = len(values)
        if source_len == target_len:
            return list(values)
        if source_len == 1:
            return [float(values[0])] * target_len
        if target_len == 1:
            return [float(values[-1])]

        resampled: list[float] = []
        scale = (source_len - 1) / (target_len - 1)
        for index in range(target_len):
            position = index * scale
            left = int(position)
            right = min(left + 1, source_len - 1)
            fraction = position - left
            sample = float(values[left]) * (1.0 - fraction) + float(values[right]) * fraction
            resampled.append(sample)
        return resampled

    def _resolve_time_axis(self, electrical_result: SimulationResult | None) -> list[float]:
        if electrical_result and electrical_result.time:
            return list(electrical_result.time)
        # Default 0 .. 10 ms timeline
        samples = 200
        duration = 10e-3
        return [i * (duration / samples) for i in range(samples + 1)]

    def _error_result(self, electrical_result: SimulationResult | None, message: str) -> ThermalResult:
        return ThermalResult(
            time=self._resolve_time_axis(electrical_result),
            devices=[],
            ambient_temperature=self._ambient_temperature,
            is_synthetic=False,
            error_message=str(message),
        )

    def _is_backend_ready(self) -> bool:
        """Best-effort readiness check; rejects known placeholder backends."""
        info = getattr(self._backend, "info", None)
        if info is None:
            return True

        identifier = getattr(info, "identifier", "")
        status = getattr(info, "status", "")

        identifier_text = identifier.strip().lower() if isinstance(identifier, str) else ""
        status_text = status.strip().lower() if isinstance(status, str) else ""

        if identifier_text == "placeholder":
            return False
        if status_text in {"placeholder", "error", "unavailable"}:
            return False
        return True

    @staticmethod
    def _build_component_identity_lookup(
        circuit_data: dict | None,
    ) -> dict[str, dict[str, tuple[str, str]]]:
        components = circuit_data.get("components", []) if isinstance(circuit_data, dict) else []
        by_id: dict[str, tuple[str, str]] = {}
        by_name: dict[str, tuple[str, str]] = {}
        by_backend_default_name: dict[str, tuple[str, str]] = {}
        by_canonical: dict[str, tuple[str, str]] = {}
        for component in components:
            raw_id = str(component.get("id") or "").strip()
            display_name = ThermalAnalysisService._component_display_name(component)
            comp_type = str(component.get("type") or "").strip()
            pair = (
                raw_id or display_name or "unknown",
                display_name or raw_id or "unknown",
            )
            if raw_id:
                by_id[raw_id.lower()] = pair
                canonical_id = ThermalAnalysisService._canonical_identity_token(raw_id)
                if canonical_id and canonical_id not in by_canonical:
                    by_canonical[canonical_id] = pair

            if display_name:
                by_name[display_name.lower()] = pair
                canonical_name = ThermalAnalysisService._canonical_identity_token(display_name)
                if canonical_name and canonical_name not in by_canonical:
                    by_canonical[canonical_name] = pair

            if raw_id and comp_type:
                backend_default = f"{comp_type}_{raw_id[:6]}".lower()
                by_backend_default_name[backend_default] = pair
                canonical_backend = ThermalAnalysisService._canonical_identity_token(backend_default)
                if canonical_backend and canonical_backend not in by_canonical:
                    by_canonical[canonical_backend] = pair

        return {
            "by_id": by_id,
            "by_name": by_name,
            "by_backend_default_name": by_backend_default_name,
            "by_canonical": by_canonical,
        }

    @staticmethod
    def _resolve_component_identity(
        raw_name: str,
        identity: dict[str, dict[str, tuple[str, str]]],
    ) -> tuple[str, str]:
        token = str(raw_name or "").strip()
        if not token:
            return "unknown", "unknown"

        by_id = identity.get("by_id", {})
        by_name = identity.get("by_name", {})
        by_backend_default_name = identity.get("by_backend_default_name", {})
        by_canonical = identity.get("by_canonical", {})

        candidates = [token]
        for separator in ("::", ":", "/", "."):
            if separator in token:
                candidates.extend(part for part in token.split(separator) if part)

        for candidate in candidates:
            lowered = candidate.strip().lower()
            if not lowered:
                continue
            if lowered in by_id:
                mapped_id, mapped_name = by_id[lowered]
                return mapped_id, mapped_name
            if lowered in by_name:
                mapped_id, mapped_name = by_name[lowered]
                return mapped_id, mapped_name
            if lowered in by_backend_default_name:
                mapped_id, mapped_name = by_backend_default_name[lowered]
                return mapped_id, mapped_name
            canonical = ThermalAnalysisService._canonical_identity_token(lowered)
            if canonical and canonical in by_canonical:
                mapped_id, mapped_name = by_canonical[canonical]
                return mapped_id, mapped_name

        return token, token

    @staticmethod
    def _component_display_name(component: dict[str, Any]) -> str:
        raw_name = str(component.get("name") or "").strip()
        if raw_name:
            return raw_name
        comp_type = str(component.get("type") or "").strip()
        if comp_type:
            return comp_type.replace("_", " ").title()
        raw_id = str(component.get("id") or "").strip()
        return raw_id or "unknown"

    @staticmethod
    def _canonical_identity_token(value: str | None) -> str:
        token = str(value or "").strip().lower()
        if not token:
            return ""
        return "".join(ch for ch in token if ch.isalnum())

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
