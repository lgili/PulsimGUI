"""Build and cache canonical runtime circuit payloads for simulation.

This module isolates GUI->runtime payload conversion from SimulationService,
keeping conversion deterministic, testable, and performance-aware.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pulsimgui.models.project import Project


@dataclass(frozen=True)
class CircuitBuildSignature:
    """Fingerprint describing a project circuit + runtime simulation contract."""

    project_id: int
    active_circuit: str
    circuit_id: int
    project_modified: str
    component_count: int
    wire_count: int
    settings_key: tuple[Any, ...]


class CircuitDataBuilder:
    """Convert GUI project circuits to canonical pulsim-v1 payloads.

    The builder caches the latest conversion result to avoid repeated expensive
    node-map reconstruction when users run multiple simulations without changing
    schematic topology or simulation contract settings.
    """

    def __init__(self) -> None:
        self._cache_lock = threading.Lock()
        self._cache_signature: CircuitBuildSignature | None = None
        self._cache_payload: dict[str, Any] | None = None

    def clear(self) -> None:
        """Clear cached conversion payload."""
        with self._cache_lock:
            self._cache_signature = None
            self._cache_payload = None

    def build(
        self,
        project: Project | None,
        *,
        settings: Any,
        normalize_step_mode: Any,
        normalize_formulation_mode: Any,
        normalize_thermal_policy: Any,
        normalize_control_mode: Any,
        build_node_map: Any,
        build_node_alias_map: Any,
        copy_result: bool,
        cooperative_yield: bool,
    ) -> dict[str, Any]:
        """Build a canonical runtime payload from GUI project state.

        Args:
            project: GUI project model or None.
            settings: Runtime simulation settings object.
            normalize_step_mode: Callable normalization helper.
            normalize_formulation_mode: Callable normalization helper.
            normalize_thermal_policy: Callable normalization helper.
            normalize_control_mode: Callable normalization helper.
            build_node_map: Connectivity builder callable.
            build_node_alias_map: Alias map builder callable.
            copy_result: Return deep copy (safe for external mutation).
            cooperative_yield: Yield periodically on large loops.
        """
        if project is None:
            payload = self._base_payload(
                settings,
                normalize_step_mode=normalize_step_mode,
                normalize_formulation_mode=normalize_formulation_mode,
                normalize_thermal_policy=normalize_thermal_policy,
                normalize_control_mode=normalize_control_mode,
            )
            return copy.deepcopy(payload) if copy_result else payload

        signature = self._signature(
            project,
            settings,
            normalize_step_mode=normalize_step_mode,
            normalize_formulation_mode=normalize_formulation_mode,
            normalize_thermal_policy=normalize_thermal_policy,
            normalize_control_mode=normalize_control_mode,
        )

        with self._cache_lock:
            if signature == self._cache_signature and self._cache_payload is not None:
                return copy.deepcopy(self._cache_payload) if copy_result else self._cache_payload

        payload = self._build_uncached(
            project,
            settings,
            normalize_step_mode=normalize_step_mode,
            normalize_formulation_mode=normalize_formulation_mode,
            normalize_thermal_policy=normalize_thermal_policy,
            normalize_control_mode=normalize_control_mode,
            build_node_map=build_node_map,
            build_node_alias_map=build_node_alias_map,
            cooperative_yield=cooperative_yield,
        )

        with self._cache_lock:
            self._cache_signature = signature
            self._cache_payload = payload

        return copy.deepcopy(payload) if copy_result else payload

    def _signature(
        self,
        project: Project,
        settings: Any,
        *,
        normalize_step_mode: Any,
        normalize_formulation_mode: Any,
        normalize_thermal_policy: Any,
        normalize_control_mode: Any,
    ) -> CircuitBuildSignature:
        circuit = project.get_active_circuit()
        modified_raw = getattr(project, "modified", None)
        if isinstance(modified_raw, datetime):
            modified_token = modified_raw.isoformat(timespec="microseconds")
        else:
            modified_token = str(modified_raw)

        return CircuitBuildSignature(
            project_id=id(project),
            active_circuit=str(getattr(project, "active_circuit", "main") or "main"),
            circuit_id=id(circuit),
            project_modified=modified_token,
            component_count=len(circuit.components),
            wire_count=len(circuit.wires),
            settings_key=self._settings_signature(
                settings,
                normalize_step_mode=normalize_step_mode,
                normalize_formulation_mode=normalize_formulation_mode,
                normalize_thermal_policy=normalize_thermal_policy,
                normalize_control_mode=normalize_control_mode,
            ),
        )

    @staticmethod
    def _settings_signature(
        settings: Any,
        *,
        normalize_step_mode: Any,
        normalize_formulation_mode: Any,
        normalize_thermal_policy: Any,
        normalize_control_mode: Any,
    ) -> tuple[Any, ...]:
        control_mode = normalize_control_mode(getattr(settings, "control_mode", "auto"))
        control_sample_time = max(0.0, float(getattr(settings, "control_sample_time", 0.0)))
        if control_mode == "discrete":
            control_sample_time = max(control_sample_time, 1e-12)

        return (
            float(getattr(settings, "t_start", 0.0)),
            float(getattr(settings, "t_stop", 1e-3)),
            float(getattr(settings, "t_step", 1e-6)),
            normalize_step_mode(getattr(settings, "step_mode", "fixed")),
            normalize_formulation_mode(getattr(settings, "formulation_mode", "projected_wrapper")),
            bool(getattr(settings, "direct_formulation_fallback", True)),
            bool(getattr(settings, "enable_events", True)),
            bool(getattr(settings, "enable_losses", True)),
            control_mode,
            control_sample_time,
            float(getattr(settings, "thermal_ambient", 25.0)),
            normalize_thermal_policy(getattr(settings, "thermal_policy", "loss_with_temperature_scaling")),
            max(0.0, float(getattr(settings, "thermal_default_rth", 1.0))),
            max(0.0, float(getattr(settings, "thermal_default_cth", 0.1))),
        )

    def _build_uncached(
        self,
        project: Project,
        settings: Any,
        *,
        normalize_step_mode: Any,
        normalize_formulation_mode: Any,
        normalize_thermal_policy: Any,
        normalize_control_mode: Any,
        build_node_map: Any,
        build_node_alias_map: Any,
        cooperative_yield: bool,
    ) -> dict[str, Any]:
        payload = self._base_payload(
            settings,
            normalize_step_mode=normalize_step_mode,
            normalize_formulation_mode=normalize_formulation_mode,
            normalize_thermal_policy=normalize_thermal_policy,
            normalize_control_mode=normalize_control_mode,
        )

        circuit = project.get_active_circuit()
        if circuit is None:
            return payload

        node_map_raw = build_node_map(circuit)
        alias_map = build_node_alias_map(circuit, node_map_raw)
        payload["node_aliases"] = alias_map
        payload["metadata"] = {"name": circuit.name}

        component_node_map: dict[str, list[str]] = {}
        components_out: list[dict[str, Any]] = payload["components"]

        for comp_index, component in enumerate(circuit.components.values()):
            if cooperative_yield and comp_index and comp_index % 128 == 0:
                time.sleep(0)

            comp_dict = component.to_dict()
            # Keep payload detached from mutable GUI model params.
            comp_dict["parameters"] = copy.deepcopy(component.parameters)
            comp_id = str(component.id)
            pin_count = len(component.pins)
            pin_nodes = [
                node_map_raw.get((comp_id, pin_index), "") or ""
                for pin_index in range(pin_count)
            ]
            comp_dict["pin_nodes"] = pin_nodes
            components_out.append(comp_dict)
            component_node_map[comp_id] = pin_nodes

        payload["node_map"] = component_node_map

        wires_out: list[dict[str, Any]] = payload["wires"]
        for wire_index, wire in enumerate(circuit.wires.values()):
            if cooperative_yield and wire_index and wire_index % 128 == 0:
                time.sleep(0)
            wires_out.append(wire.to_dict())

        return payload

    @staticmethod
    def _base_payload(
        settings: Any,
        *,
        normalize_step_mode: Any,
        normalize_formulation_mode: Any,
        normalize_thermal_policy: Any,
        normalize_control_mode: Any,
    ) -> dict[str, Any]:
        control_mode = normalize_control_mode(getattr(settings, "control_mode", "auto"))
        control_sample_time = max(0.0, float(getattr(settings, "control_sample_time", 0.0)))
        control_cfg: dict[str, Any] = {"mode": control_mode}
        if control_sample_time > 0.0 or control_mode == "discrete":
            control_cfg["sample_time"] = max(control_sample_time, 1e-12)

        return {
            "schema": "pulsim-v1",
            "version": 1,
            "simulation": {
                "tstart": float(getattr(settings, "t_start", 0.0)),
                "tstop": float(getattr(settings, "t_stop", 1e-3)),
                "dt": float(getattr(settings, "t_step", 1e-6)),
                "step_mode": normalize_step_mode(getattr(settings, "step_mode", "fixed")),
                "formulation": normalize_formulation_mode(
                    getattr(settings, "formulation_mode", "projected_wrapper")
                ),
                "direct_formulation_fallback": bool(
                    getattr(settings, "direct_formulation_fallback", True)
                ),
                "enable_events": bool(getattr(settings, "enable_events", True)),
                "enable_losses": bool(getattr(settings, "enable_losses", True)),
                "control": control_cfg,
                "thermal": {
                    "enabled": bool(getattr(settings, "enable_losses", True)),
                    "ambient": float(getattr(settings, "thermal_ambient", 25.0)),
                    "policy": normalize_thermal_policy(
                        getattr(settings, "thermal_policy", "loss_with_temperature_scaling")
                    ),
                    "default_rth": max(0.0, float(getattr(settings, "thermal_default_rth", 1.0))),
                    "default_cth": max(0.0, float(getattr(settings, "thermal_default_cth", 0.1))),
                },
            },
            "components": [],
            "wires": [],
            "nodes": {},
            "node_map": {},
            "node_aliases": {},
            "metadata": {},
        }
