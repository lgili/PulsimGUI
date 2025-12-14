"""Helpers for converting GUI schematics into Pulsim circuit objects."""

from __future__ import annotations

from typing import Any, Iterable

from pulsimgui.models.component import ComponentType


class CircuitConversionError(RuntimeError):
    """Raised when a GUI circuit cannot be converted for backend use."""


class CircuitConverter:
    """Build Pulsim circuit objects from serialized GUI data."""

    def __init__(self, pulsim_module: Any) -> None:
        self._sl = pulsim_module
        self._node_indices: dict[str, int] = {}

    def build(self, circuit_data: dict) -> Any:
        """Create a ``pulsim.Circuit`` instance from serialized schematic data."""

        circuit = self._sl.Circuit()
        self._node_indices = {}
        alias_map: dict[str, str] = circuit_data.get("node_aliases", {}) or {}
        components: list[dict] = circuit_data.get("components", []) or []
        node_map: dict[str, list[str]] = circuit_data.get("node_map", {}) or {}

        if not components:
            return circuit

        # First pass: collect all unique nodes and register them
        all_node_names: set[str] = set()
        for component in components:
            nodes = self._resolve_nodes(component, node_map, alias_map)
            all_node_names.update(nodes)

        # Register each non-ground node to get its index
        for node_name in sorted(all_node_names):
            if node_name not in ("0", "gnd", "GND"):
                idx = circuit.add_node(node_name)
                self._node_indices[node_name] = idx
        # Ground is always index -1
        self._node_indices["0"] = circuit.ground()
        self._node_indices["gnd"] = circuit.ground()
        self._node_indices["GND"] = circuit.ground()

        # Second pass: add components using node indices
        for component in components:
            comp_type = self._component_type(component.get("type"))
            nodes = self._resolve_nodes(component, node_map, alias_map)
            self._add_component(circuit, comp_type, component, nodes)

        self._apply_positions(circuit, components)
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

    def _node_index(self, node_name: str) -> int:
        """Get the integer index for a node name."""
        if node_name not in self._node_indices:
            raise CircuitConversionError(f"Unknown node '{node_name}'")
        return self._node_indices[node_name]

    def _add_component(
        self,
        circuit: Any,
        comp_type: ComponentType,
        component: dict,
        nodes: list[str],
    ) -> None:
        name = self._component_name(component, comp_type)
        params = component.get("parameters", {}) or {}

        if comp_type == ComponentType.RESISTOR:
            n1, n2 = self._require_nodes(name, nodes, 2)
            resistance = self._as_float(params.get("resistance"), default=1.0)
            circuit.add_resistor(name, self._node_index(n1), self._node_index(n2), resistance)
            return

        if comp_type == ComponentType.CAPACITOR:
            n1, n2 = self._require_nodes(name, nodes, 2)
            capacitance = self._as_float(params.get("capacitance"), default=1e-6)
            ic = self._as_float(params.get("initial_voltage"), default=0.0)
            circuit.add_capacitor(name, self._node_index(n1), self._node_index(n2), capacitance, ic)
            return

        if comp_type == ComponentType.INDUCTOR:
            n1, n2 = self._require_nodes(name, nodes, 2)
            inductance = self._as_float(params.get("inductance"), default=1e-3)
            ic = self._as_float(params.get("initial_current"), default=0.0)
            circuit.add_inductor(name, self._node_index(n1), self._node_index(n2), inductance, ic)
            return

        if comp_type == ComponentType.VOLTAGE_SOURCE:
            n_pos, n_neg = self._require_nodes(name, nodes, 2)
            npos_idx = self._node_index(n_pos)
            nneg_idx = self._node_index(n_neg)
            self._add_voltage_source(circuit, name, npos_idx, nneg_idx, params.get("waveform"))
            return

        if comp_type == ComponentType.CURRENT_SOURCE:
            n_pos, n_neg = self._require_nodes(name, nodes, 2)
            waveform = self._build_waveform(params.get("waveform"))
            circuit.add_current_source(name, self._node_index(n_pos), self._node_index(n_neg), waveform)
            return

        if comp_type == ComponentType.DIODE:
            n_anode, n_cathode = self._require_nodes(name, nodes, 2)
            circuit.add_diode(name, self._node_index(n_anode), self._node_index(n_cathode))
            return

        if comp_type in (ComponentType.MOSFET_N, ComponentType.MOSFET_P):
            gate, drain, source = self._require_nodes(name, nodes, 3)
            mosfet_params = self._sl.MOSFETParams()
            mosfet_params.is_nmos = comp_type == ComponentType.MOSFET_N
            self._assign_attributes(mosfet_params, params)
            circuit.add_mosfet(name, self._node_index(gate), self._node_index(drain), self._node_index(source), mosfet_params)
            return

        if comp_type == ComponentType.IGBT:
            gate, collector, emitter = self._require_nodes(name, nodes, 3)
            igbt_params = self._sl.IGBTParams()
            self._assign_attributes(igbt_params, params)
            circuit.add_igbt(name, self._node_index(gate), self._node_index(collector), self._node_index(emitter), igbt_params)
            return

        if comp_type == ComponentType.TRANSFORMER:
            p1, p2, s1, s2 = self._require_nodes(name, nodes, 4)
            turns_ratio = self._as_float(params.get("turns_ratio"), default=1.0)
            circuit.add_transformer(name, self._node_index(p1), self._node_index(p2), self._node_index(s1), self._node_index(s2), turns_ratio)
            return

        if comp_type == ComponentType.GROUND:
            # Ground symbols are implicit through node mapping (node "0").
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
        waveform_spec: dict | None,
    ) -> None:
        """Add a voltage source with the appropriate method based on waveform type."""
        if not waveform_spec:
            circuit.add_voltage_source(name, npos, nneg, 0.0)
            return

        kind = (waveform_spec.get("type") or "dc").lower()

        if kind == "dc":
            value = self._as_float(waveform_spec.get("value"), default=0.0)
            circuit.add_voltage_source(name, npos, nneg, value)
            return

        if kind == "pwm":
            params = self._sl.PWMParams()
            params.v_high = self._as_float(waveform_spec.get("v_on"), default=5.0)
            params.v_low = self._as_float(waveform_spec.get("v_off"), default=0.0)
            params.frequency = self._as_float(waveform_spec.get("frequency"), default=1000.0)
            params.duty = self._as_float(waveform_spec.get("duty_cycle"), default=0.5)
            params.dead_time = self._as_float(waveform_spec.get("dead_time"), default=0.0)
            params.phase = self._as_float(waveform_spec.get("phase"), default=0.0)
            circuit.add_pwm_voltage_source(name, npos, nneg, params)
            return

        if kind == "sine":
            params = self._sl.SineParams()
            params.amplitude = self._as_float(waveform_spec.get("amplitude"), default=1.0)
            params.offset = self._as_float(waveform_spec.get("offset"), default=0.0)
            params.frequency = self._as_float(waveform_spec.get("frequency"), default=1000.0)
            params.phase = self._as_float(waveform_spec.get("phase"), default=0.0)
            circuit.add_sine_voltage_source(name, npos, nneg, params)
            return

        if kind == "pulse":
            params = self._sl.PulseParams()
            params.v_initial = self._as_float(waveform_spec.get("v1"), default=0.0)
            params.v_pulse = self._as_float(waveform_spec.get("v2"), default=5.0)
            params.t_delay = self._as_float(waveform_spec.get("delay"), default=0.0)
            params.t_rise = self._as_float(waveform_spec.get("rise_time"), default=1e-9)
            params.t_fall = self._as_float(waveform_spec.get("fall_time"), default=1e-9)
            params.t_width = self._as_float(waveform_spec.get("pulse_width"), default=1e-6)
            params.period = self._as_float(waveform_spec.get("period"), default=2e-6)
            circuit.add_pulse_voltage_source(name, npos, nneg, params)
            return

        raise CircuitConversionError(f"Unsupported waveform type '{kind}' for voltage source")

    def _apply_positions(self, circuit: Any, components: Iterable[dict]) -> None:
        if not hasattr(circuit, "set_position"):
            return
        for component in components:
            name = (component.get("name") or "").strip()
            if not name:
                continue
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

    def _build_waveform(self, spec: dict | None) -> Any:
        if not spec:
            return 0.0
        kind = (spec.get("type") or "dc").lower()
        if kind == "dc":
            return self._as_float(spec.get("value"), default=0.0)
        if kind == "sine":
            wf = self._sl.SineWaveform()
            wf.offset = self._as_float(spec.get("offset"), default=0.0)
            wf.amplitude = self._as_float(spec.get("amplitude"), default=1.0)
            wf.frequency = self._as_float(spec.get("frequency"), default=1000.0)
            wf.phase = self._as_float(spec.get("phase"), default=0.0)
            return wf
        if kind == "pulse":
            wf = self._sl.PulseWaveform()
            wf.v1 = self._as_float(spec.get("v1"), default=0.0)
            wf.v2 = self._as_float(spec.get("v2"), default=5.0)
            wf.td = self._as_float(spec.get("delay"), default=0.0)
            wf.tr = self._as_float(spec.get("rise_time"), default=1e-9)
            wf.tf = self._as_float(spec.get("fall_time"), default=1e-9)
            wf.pw = self._as_float(spec.get("pulse_width"), default=1e-6)
            wf.period = self._as_float(spec.get("period"), default=2e-6)
            return wf
        if kind == "pwl":
            wf = self._sl.PWLWaveform()
            wf.points = [tuple(point) for point in spec.get("points", [])]
            return wf
        if kind == "pwm":
            wf = self._sl.PWMWaveform()
            wf.v_off = self._as_float(spec.get("v_off"), default=0.0)
            wf.v_on = self._as_float(spec.get("v_on"), default=5.0)
            wf.frequency = self._as_float(spec.get("frequency"), default=1000.0)
            wf.duty = self._as_float(spec.get("duty_cycle"), default=0.5)
            wf.dead_time = self._as_float(spec.get("dead_time"), default=0.0)
            wf.phase = self._as_float(spec.get("phase"), default=0.0)
            wf.complementary = bool(spec.get("complementary", False))
            return wf
        raise CircuitConversionError(f"Unsupported waveform type '{kind}'")

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
