"""Helpers for converting GUI schematics into Pulsim circuit objects."""

from __future__ import annotations

from typing import Any, Iterable

from pulsimgui.models.component import ComponentType


class CircuitConversionError(RuntimeError):
    """Raised when a GUI circuit cannot be converted for backend use."""


class CircuitConverter:
    """Build Pulsim circuit objects from serialized GUI data.

    Builds circuits directly using the Pulsim runtime Circuit API.
    """

    def __init__(self, pulsim_module: Any) -> None:
        self._sl = pulsim_module

    def build(self, circuit_data: dict) -> Any:
        """Create a ``pulsim.Circuit`` instance from serialized schematic data.

        Converts the GUI circuit data to Pulsim's runtime Circuit API.
        """
        alias_map: dict[str, str] = circuit_data.get("node_aliases", {}) or {}
        components: list[dict] = circuit_data.get("components", []) or []
        node_map: dict[str, list[str]] = circuit_data.get("node_map", {}) or {}

        if not components:
            return self._sl.Circuit()

        circuit = self._sl.Circuit()
        node_cache: dict[str, int] = {}
        positions_to_apply = []

        for component in components:
            comp_type = self._component_type(component.get("type"))
            nodes = self._resolve_nodes(component, node_map, alias_map)
            name = self._component_name(component, comp_type)

            if comp_type == ComponentType.GROUND:
                continue

            self._add_component(circuit, comp_type, name, component, nodes, node_cache)

            if name and (component.get("x") is not None or component.get("y") is not None):
                positions_to_apply.append((name, component))

        self._apply_positions_from_list(circuit, positions_to_apply)
        return circuit

    def _component_type(self, raw_type: str | None) -> ComponentType:
        if not raw_type:
            raise CircuitConversionError("Component missing type identifier")
        try:
            return ComponentType[raw_type]
        except KeyError as exc:  # pragma: no cover - defensive
            raise CircuitConversionError(f"Unsupported component type '{raw_type}'") from exc

    def _resolve_nodes(
        self,
        component: dict,
        node_map: dict[str, list[str]],
        alias_map: dict[str, str],
    ) -> list[str]:
        comp_id = component.get("id")
        pin_nodes = component.get("pin_nodes") or node_map.get(comp_id) or []
        if not pin_nodes:
            raise CircuitConversionError(
                f"Missing connectivity for component '{component.get('name') or comp_id}'"
            )
        resolved: list[str] = []
        for raw in pin_nodes:
            if raw is None or raw == "":
                raise CircuitConversionError(
                    f"Unmapped node for component '{component.get('name') or comp_id}'"
                )
            resolved.append(self._node_label(raw, alias_map))
        return resolved

    def _node_label(self, node_id: str, alias_map: dict[str, str]) -> str:
        if node_id == "0":
            return "0"
        alias = (alias_map.get(node_id) or "").strip()
        if alias:
            return alias.replace(" ", "_")
        return f"N{node_id}"

    def _component_name(self, component: dict, comp_type: ComponentType) -> str:
        name = (component.get("name") or "").strip()
        if name:
            return name
        comp_id = component.get("id", "")
        suffix = comp_id[:6] if comp_id else comp_type.name
        return f"{comp_type.name}_{suffix}"

    def _node_name(self, node: str) -> str:
        """Normalize node name for pulsim (ground is '0')."""
        if node.lower() in ("0", "gnd"):
            return "0"
        return node

    def _node_index(self, circuit: Any, name: str, cache: dict[str, int]) -> int:
        """Resolve a node name into a Circuit node index, caching as needed."""
        normalized = self._node_name(name)
        if normalized == "0":
            return circuit.ground()
        if normalized in cache:
            return cache[normalized]
        idx = circuit.add_node(normalized)
        cache[normalized] = idx
        return idx

    def _add_component(
        self,
        circuit: Any,
        comp_type: ComponentType,
        name: str,
        component: dict,
        nodes: list[str],
        node_cache: dict[str, int],
    ) -> None:
        params = component.get("parameters", {}) or {}

        if comp_type == ComponentType.RESISTOR:
            n1, n2 = self._require_nodes(name, nodes, 2)
            circuit.add_resistor(
                name,
                self._node_index(circuit, n1, node_cache),
                self._node_index(circuit, n2, node_cache),
                self._as_float(params.get("resistance"), default=1.0),
            )
            return

        if comp_type == ComponentType.CAPACITOR:
            n1, n2 = self._require_nodes(name, nodes, 2)
            circuit.add_capacitor(
                name,
                self._node_index(circuit, n1, node_cache),
                self._node_index(circuit, n2, node_cache),
                self._as_float(params.get("capacitance"), default=1e-6),
                self._as_float(params.get("initial_voltage"), default=0.0),
            )
            return

        if comp_type == ComponentType.INDUCTOR:
            n1, n2 = self._require_nodes(name, nodes, 2)
            circuit.add_inductor(
                name,
                self._node_index(circuit, n1, node_cache),
                self._node_index(circuit, n2, node_cache),
                self._as_float(params.get("inductance"), default=1e-3),
                self._as_float(params.get("initial_current"), default=0.0),
            )
            return

        if comp_type == ComponentType.VOLTAGE_SOURCE:
            npos, nneg = self._require_nodes(name, nodes, 2)
            self._add_voltage_source(
                circuit,
                name,
                self._node_index(circuit, npos, node_cache),
                self._node_index(circuit, nneg, node_cache),
                params.get("waveform") or {},
            )
            return

        if comp_type == ComponentType.CURRENT_SOURCE:
            npos, nneg = self._require_nodes(name, nodes, 2)
            self._add_current_source(
                circuit,
                name,
                self._node_index(circuit, npos, node_cache),
                self._node_index(circuit, nneg, node_cache),
                params.get("waveform") or {},
            )
            return

        if comp_type in (ComponentType.DIODE, ComponentType.ZENER_DIODE, ComponentType.LED):
            n_anode, n_cathode = self._require_nodes(name, nodes, 2)
            circuit.add_diode(
                name,
                self._node_index(circuit, n_anode, node_cache),
                self._node_index(circuit, n_cathode, node_cache),
            )
            return

        if comp_type in (ComponentType.MOSFET_N, ComponentType.MOSFET_P):
            drain, gate, source = self._require_nodes(name, nodes, 3)
            mosfet_params = self._sl.MOSFETParams()
            mosfet_params.is_nmos = comp_type == ComponentType.MOSFET_N
            self._assign_attributes(mosfet_params, params)
            circuit.add_mosfet(
                name,
                self._node_index(circuit, gate, node_cache),
                self._node_index(circuit, drain, node_cache),
                self._node_index(circuit, source, node_cache),
                mosfet_params,
            )
            return

        if comp_type == ComponentType.IGBT:
            collector, gate, emitter = self._require_nodes(name, nodes, 3)
            igbt_params = self._sl.IGBTParams()
            self._assign_attributes(igbt_params, params)
            circuit.add_igbt(
                name,
                self._node_index(circuit, gate, node_cache),
                self._node_index(circuit, collector, node_cache),
                self._node_index(circuit, emitter, node_cache),
                igbt_params,
            )
            return

        if comp_type == ComponentType.TRANSFORMER:
            p1, p2, s1, s2 = self._require_nodes(name, nodes, 4)
            circuit.add_transformer(
                name,
                self._node_index(circuit, p1, node_cache),
                self._node_index(circuit, p2, node_cache),
                self._node_index(circuit, s1, node_cache),
                self._node_index(circuit, s2, node_cache),
                self._as_float(params.get("turns_ratio"), default=1.0),
            )
            return

        raise CircuitConversionError(
            f"Backend converter does not yet support component '{comp_type.name}'"
        )

    def _add_voltage_source(
        self,
        circuit: Any,
        name: str,
        npos: int,
        nneg: int,
        waveform: dict,
    ) -> None:
        kind = (waveform.get("type") or "dc").lower()

        if kind == "dc":
            circuit.add_voltage_source(
                name,
                npos,
                nneg,
                self._as_float(waveform.get("value"), default=0.0),
            )
            return

        if kind == "sine":
            params = self._sl.SineParams()
            params.offset = self._as_float(waveform.get("offset"), default=0.0)
            params.amplitude = self._as_float(waveform.get("amplitude"), default=1.0)
            params.frequency = self._as_float(waveform.get("frequency"), default=60.0)
            params.phase = self._as_float(waveform.get("phase"), default=0.0)
            circuit.add_sine_voltage_source(name, npos, nneg, params)
            return

        if kind == "pulse":
            params = self._sl.PulseParams()
            params.v_initial = self._as_float(waveform.get("v1"), default=0.0)
            params.v_pulse = self._as_float(waveform.get("v2"), default=5.0)
            params.t_delay = self._as_float(waveform.get("delay"), default=0.0)
            params.t_rise = self._as_float(waveform.get("rise_time"), default=1e-9)
            params.t_fall = self._as_float(waveform.get("fall_time"), default=1e-9)
            params.t_width = self._as_float(waveform.get("pulse_width"), default=1e-6)
            params.period = self._as_float(waveform.get("period"), default=2e-6)
            circuit.add_pulse_voltage_source(name, npos, nneg, params)
            return

        if kind == "pwm":
            params = self._sl.PWMParams()
            params.v_low = self._as_float(waveform.get("v_off"), default=0.0)
            params.v_high = self._as_float(waveform.get("v_on"), default=5.0)
            params.frequency = self._as_float(waveform.get("frequency"), default=1000.0)
            params.duty = self._as_float(waveform.get("duty_cycle"), default=0.5)
            params.dead_time = self._as_float(waveform.get("dead_time"), default=0.0)
            params.phase = self._as_float(waveform.get("phase"), default=0.0)
            params.rise_time = self._as_float(waveform.get("rise_time"), default=0.0)
            params.fall_time = self._as_float(waveform.get("fall_time"), default=0.0)
            circuit.add_pwm_voltage_source(name, npos, nneg, params)
            return

        raise CircuitConversionError(f"Unsupported voltage waveform '{kind}'")

    def _add_current_source(
        self,
        circuit: Any,
        name: str,
        npos: int,
        nneg: int,
        waveform: dict,
    ) -> None:
        kind = (waveform.get("type") or "dc").lower()
        if kind != "dc":
            raise CircuitConversionError(
                f"Current source waveform '{kind}' is not supported by the backend"
            )
        circuit.add_current_source(
            name,
            npos,
            nneg,
            self._as_float(waveform.get("value"), default=0.0),
        )

    def _apply_positions_from_list(
        self, circuit: Any, positions: list[tuple[str, dict]]
    ) -> None:
        """Apply schematic positions to components."""
        if not hasattr(circuit, "set_position"):
            return
        for name, component in positions:
            mirrored = bool(component.get("mirrored_h")) or bool(component.get("mirrored_v"))
            position = self._sl.SchematicPosition(
                self._as_float(component.get("x"), default=0.0),
                self._as_float(component.get("y"), default=0.0),
                int(component.get("rotation") or 0),
                mirrored,
            )
            circuit.set_position(name, position)

    def _require_nodes(self, name: str, nodes: list[str], count: int) -> list[str]:
        if len(nodes) < count:
            raise CircuitConversionError(
                f"Component '{name}' expects {count} pins but only {len(nodes)} nodes were provided"
            )
        return nodes[:count]

    def _assign_attributes(self, target: Any, values: dict) -> None:
        for key, value in values.items():
            attr = key
            if not hasattr(target, attr) and attr.endswith("_"):
                attr = attr[:-1]
            if not hasattr(target, attr):
                continue
            setattr(target, attr, value)

    def _as_float(self, value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)


__all__ = ["CircuitConverter", "CircuitConversionError"]
