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

    def build(self, circuit_data: dict) -> Any:
        """Create a ``pulsim.Circuit`` instance from serialized schematic data."""

        circuit = self._sl.Circuit()
        alias_map: dict[str, str] = circuit_data.get("node_aliases", {}) or {}
        components: list[dict] = circuit_data.get("components", []) or []
        node_map: dict[str, list[str]] = circuit_data.get("node_map", {}) or {}

        if not components:
            return circuit

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
            circuit.add_resistor(name, n1, n2, resistance)
            return

        if comp_type == ComponentType.CAPACITOR:
            n1, n2 = self._require_nodes(name, nodes, 2)
            capacitance = self._as_float(params.get("capacitance"), default=1e-6)
            ic = self._as_float(params.get("initial_voltage"), default=0.0)
            circuit.add_capacitor(name, n1, n2, capacitance, ic=ic)
            return

        if comp_type == ComponentType.INDUCTOR:
            n1, n2 = self._require_nodes(name, nodes, 2)
            inductance = self._as_float(params.get("inductance"), default=1e-3)
            ic = self._as_float(params.get("initial_current"), default=0.0)
            circuit.add_inductor(name, n1, n2, inductance, ic=ic)
            return

        if comp_type == ComponentType.VOLTAGE_SOURCE:
            n_pos, n_neg = self._require_nodes(name, nodes, 2)
            waveform = self._build_waveform(params.get("waveform"))
            circuit.add_voltage_source(name, n_pos, n_neg, waveform)
            return

        if comp_type == ComponentType.CURRENT_SOURCE:
            n_pos, n_neg = self._require_nodes(name, nodes, 2)
            waveform = self._build_waveform(params.get("waveform"))
            circuit.add_current_source(name, n_pos, n_neg, waveform)
            return

        if comp_type == ComponentType.DIODE:
            n_anode, n_cathode = self._require_nodes(name, nodes, 2)
            diode_params = self._sl.DiodeParams()
            self._assign_attributes(diode_params, params)
            circuit.add_diode(name, n_anode, n_cathode, diode_params)
            return

        if comp_type in (ComponentType.MOSFET_N, ComponentType.MOSFET_P):
            drain, gate, source = self._require_nodes(name, nodes, 3)
            mosfet_params = self._sl.MOSFETParams()
            mosfet_params.type = (
                self._sl.MOSFETType.NMOS if comp_type == ComponentType.MOSFET_N else self._sl.MOSFETType.PMOS
            )
            self._assign_attributes(mosfet_params, params)
            circuit.add_mosfet(name, drain, gate, source, mosfet_params)
            return

        if comp_type == ComponentType.IGBT:
            collector, gate, emitter = self._require_nodes(name, nodes, 3)
            igbt_params = self._sl.IGBTParams()
            self._assign_attributes(igbt_params, params)
            circuit.add_igbt(name, collector, gate, emitter, igbt_params)
            return

        if comp_type == ComponentType.TRANSFORMER:
            p1, p2, s1, s2 = self._require_nodes(name, nodes, 4)
            transformer_params = self._sl.TransformerParams()
            self._assign_attributes(transformer_params, params)
            circuit.add_transformer(name, p1, p2, s1, s2, transformer_params)
            return

        if comp_type == ComponentType.GROUND:
            # Ground symbols are implicit through node mapping (node "0").
            return

        raise CircuitConversionError(
            f"Backend converter does not yet support component '{comp_type.name}'"
        )

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
