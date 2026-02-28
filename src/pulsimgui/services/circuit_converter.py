"""Helpers for converting GUI schematics into Pulsim circuit objects."""

from __future__ import annotations

import json
from typing import Any

from pulsimgui.models.component import ComponentType


class CircuitConversionError(RuntimeError):
    """Raised when a GUI circuit cannot be converted for backend use."""


class CircuitConverter:
    """Build Pulsim circuit objects from serialized GUI data.

    Builds circuits directly using the Pulsim runtime Circuit API.
    """

    def __init__(self, pulsim_module: Any) -> None:
        self._sl = pulsim_module

    _INSTRUMENTATION_COMPONENTS = {
        # Measurement / visualization – GUI-only, no backend counterpart
        ComponentType.VOLTAGE_PROBE,
        ComponentType.CURRENT_PROBE,
        ComponentType.POWER_PROBE,
        ComponentType.ELECTRICAL_SCOPE,
        ComponentType.THERMAL_SCOPE,
        ComponentType.SIGNAL_MUX,
        ComponentType.SIGNAL_DEMUX,
        # Signal-domain control blocks – evaluated by SignalEvaluator in Python;
        # they do not map to any C++ circuit element.
        ComponentType.CONSTANT,
        ComponentType.GAIN,
        ComponentType.SUM,
        ComponentType.SUBTRACTOR,
        ComponentType.LIMITER,
        ComponentType.RATE_LIMITER,
        ComponentType.PI_CONTROLLER,
        ComponentType.PID_CONTROLLER,
        ComponentType.INTEGRATOR,
        ComponentType.DIFFERENTIATOR,
        ComponentType.HYSTERESIS,
        ComponentType.SAMPLE_HOLD,
        ComponentType.MATH_BLOCK,
    }

    # Map GUI ComponentType enum names to the lowercase backend type strings.
    # Most types follow the simple .name.lower() convention; exceptions are listed here.
    _BACKEND_TYPE_MAP: dict[ComponentType, str] = {
        ComponentType.SUBTRACTOR: "subtraction",
    }

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
        resolved_components: list[tuple[dict, ComponentType, str, list[str]]] = []

        for component in components:
            comp_type = self._component_type(component.get("type"))
            if self._should_skip_component(comp_type):
                continue
            nodes = self._resolve_nodes(component, node_map, alias_map)
            name = self._component_name(component, comp_type)
            resolved_components.append((component, comp_type, name, nodes))

        # Some Pulsim versions expect all non-ground nodes to exist before devices are added.
        self._predeclare_nodes(circuit, resolved_components, node_cache)

        for component, comp_type, name, nodes in resolved_components:
            if comp_type == ComponentType.GROUND:
                continue

            self._add_component(circuit, comp_type, name, component, nodes, node_cache)

            if name and (component.get("x") is not None or component.get("y") is not None):
                positions_to_apply.append((name, component))

        self._apply_positions_from_list(circuit, positions_to_apply)
        return circuit

    def _should_skip_component(self, comp_type: ComponentType) -> bool:
        """Return True for GUI-only instrumentation components.

        These blocks are used for measurement/visualization and should not
        become physical devices in the backend netlist.
        """
        return comp_type in self._INSTRUMENTATION_COMPONENTS

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

    def _declare_node(self, circuit: Any, normalized: str) -> int:
        if hasattr(circuit, "add_node"):
            return circuit.add_node(normalized)
        if hasattr(circuit, "get_node"):
            idx = circuit.get_node(normalized)
            if idx in (-1, None):
                raise CircuitConversionError(
                    "Backend Circuit API does not support creating new nodes dynamically."
                )
            return idx
        raise CircuitConversionError(
            "Backend Circuit API is missing both 'add_node' and 'get_node'."
        )

    def _predeclare_nodes(
        self,
        circuit: Any,
        components: list[tuple[dict, ComponentType, str, list[str]]],
        cache: dict[str, int],
    ) -> None:
        for _component, comp_type, _name, nodes in components:
            if comp_type == ComponentType.GROUND:
                continue
            for node in self._nodes_to_predeclare(comp_type, nodes):
                normalized = self._node_name(node)
                if normalized == "0" or normalized in cache:
                    continue
                cache[normalized] = self._declare_node(circuit, normalized)

    def _nodes_to_predeclare(self, comp_type: ComponentType, nodes: list[str]) -> list[str]:
        """Return only electrical terminals that the backend will stamp.

        Some GUI components expose auxiliary pins (for example thermal ports).
        Predeclaring those unused nodes can create isolated nodes and degrade
        backend convergence on otherwise simple circuits.
        """
        if comp_type in {
            ComponentType.RESISTOR,
            ComponentType.CAPACITOR,
            ComponentType.INDUCTOR,
            ComponentType.VOLTAGE_SOURCE,
            ComponentType.CURRENT_SOURCE,
            ComponentType.DIODE,
            ComponentType.ZENER_DIODE,
            ComponentType.LED,
            ComponentType.SNUBBER_RC,
        }:
            return nodes[:2]

        if comp_type in {ComponentType.MOSFET_N, ComponentType.MOSFET_P, ComponentType.IGBT}:
            return nodes[:3]

        if comp_type == ComponentType.TRANSFORMER:
            return nodes[:4]

        if comp_type == ComponentType.SWITCH:
            return nodes[:3] if len(nodes) >= 3 else nodes[:2]

        # Virtual/unknown components keep their full terminal list.
        return nodes

    def _node_index(self, circuit: Any, name: str, cache: dict[str, int]) -> int:
        """Resolve a node name into a Circuit node index, caching as needed."""
        normalized = self._node_name(name)
        if normalized == "0":
            ground = getattr(circuit, "ground", None)
            if callable(ground):
                return int(ground())
            if isinstance(ground, int):
                return int(ground)
            raise CircuitConversionError("Backend Circuit API does not expose a ground node.")
        if normalized in cache:
            return cache[normalized]
        idx = self._declare_node(circuit, normalized)
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
            anode = self._node_index(circuit, n_anode, node_cache)
            cathode = self._node_index(circuit, n_cathode, node_cache)
            g_on, g_off = self._switch_conductances(params)
            try:
                circuit.add_diode(name, anode, cathode, g_on, g_off)
            except TypeError:
                # Backward compatibility with older backends that accept only 2 terminals.
                circuit.add_diode(name, anode, cathode)
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

        if comp_type == ComponentType.SWITCH:
            g_on, g_off = self._switch_conductances(params)
            if len(nodes) >= 3:
                if not hasattr(circuit, "add_vcswitch"):
                    raise CircuitConversionError(
                        f"Component '{name}' uses a controlled switch but backend lacks 'add_vcswitch'"
                    )
                # Pin layout: 0="CTL" (control), 1="1" (terminal), 2="2" (terminal)
                ctrl, t1, t2 = self._require_nodes(name, nodes, 3)
                circuit.add_vcswitch(
                    name,
                    self._node_index(circuit, ctrl, node_cache),
                    self._node_index(circuit, t1, node_cache),
                    self._node_index(circuit, t2, node_cache),
                    self._as_float(params.get("v_threshold"), default=2.5),
                    g_on,
                    g_off,
                )
                return

            if hasattr(circuit, "add_switch"):
                n1, n2 = self._require_nodes(name, nodes, 2)
                circuit.add_switch(
                    name,
                    self._node_index(circuit, n1, node_cache),
                    self._node_index(circuit, n2, node_cache),
                    self._switch_closed(params),
                    g_on,
                    g_off,
                )
                return

        if comp_type == ComponentType.SNUBBER_RC and hasattr(circuit, "add_snubber_rc"):
            n1, n2 = self._require_nodes(name, nodes, 2)
            circuit.add_snubber_rc(
                name,
                self._node_index(circuit, n1, node_cache),
                self._node_index(circuit, n2, node_cache),
                self._as_float(params.get("resistance"), default=100.0),
                self._as_float(params.get("capacitance"), default=100e-9),
                self._as_float(params.get("initial_voltage"), default=0.0),
            )
            return

        if comp_type == ComponentType.PWM_GENERATOR:
            # Convert the PWM block into a real PWM voltage source.
            # The single OUT pin drives the connected node (e.g. a gate) relative to GND.
            if nodes:
                npos = self._node_index(circuit, nodes[0], node_cache)
                nneg = self._node_index(circuit, "0", node_cache)
                waveform = {
                    "type": "pwm",
                    "frequency": params.get("frequency", 10000.0),
                    "duty_cycle": params.get("duty_cycle", 0.5),
                    "v_high": params.get("amplitude", params.get("v_high", 10.0)),
                    "v_low": params.get("v_low", 0.0),
                    "phase": params.get("phase", 0.0),
                    "rise_time": params.get("rise_time", 0.0),
                    "fall_time": params.get("fall_time", 0.0),
                    "dead_time": params.get("dead_time", 0.0),
                }
                self._add_voltage_source(circuit, name, npos, nneg, waveform)
            return

        if hasattr(circuit, "add_virtual_component"):
            self._add_virtual_component(
                circuit,
                comp_type,
                name,
                nodes,
                params,
                node_cache,
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
            params.offset = self._waveform_float(waveform, ("offset", "vo"), default=0.0)
            params.amplitude = self._waveform_float(waveform, ("amplitude", "va"), default=1.0)
            params.frequency = self._waveform_float(waveform, ("frequency", "freq"), default=60.0)
            params.phase = self._waveform_float(waveform, ("phase",), default=0.0)
            circuit.add_sine_voltage_source(name, npos, nneg, params)
            return

        if kind == "pulse":
            params = self._sl.PulseParams()
            params.v_initial = self._waveform_float(waveform, ("v1", "v_initial"), default=0.0)
            params.v_pulse = self._waveform_float(waveform, ("v2", "v_pulse"), default=5.0)
            params.t_delay = self._waveform_float(
                waveform,
                ("delay", "td", "t_delay"),
                default=0.0,
            )
            params.t_rise = self._waveform_float(
                waveform,
                ("rise_time", "tr", "t_rise"),
                default=1e-9,
            )
            params.t_fall = self._waveform_float(
                waveform,
                ("fall_time", "tf", "t_fall"),
                default=1e-9,
            )
            params.t_width = self._waveform_float(
                waveform,
                ("pulse_width", "pw", "t_width"),
                default=1e-6,
            )
            params.period = self._waveform_float(
                waveform,
                ("period", "per"),
                default=2e-6,
            )
            circuit.add_pulse_voltage_source(name, npos, nneg, params)
            return

        if kind == "pwm":
            params = self._sl.PWMParams()
            params.v_low = self._waveform_float(waveform, ("v_off", "vlow", "v_low"), default=0.0)
            params.v_high = self._waveform_float(waveform, ("v_on", "vhigh", "v_high"), default=5.0)
            params.frequency = self._waveform_float(waveform, ("frequency", "freq"), default=1000.0)
            duty = self._waveform_float(waveform, ("duty_cycle", "duty"), default=0.5)
            if duty > 1.0:
                duty /= 100.0
            params.duty = max(0.0, min(1.0, duty))
            params.dead_time = self._waveform_float(waveform, ("dead_time",), default=0.0)
            params.phase = self._waveform_float(waveform, ("phase",), default=0.0)
            params.rise_time = self._waveform_float(
                waveform,
                ("rise_time", "tr"),
                default=0.0,
            )
            params.fall_time = self._waveform_float(
                waveform,
                ("fall_time", "tf"),
                default=0.0,
            )
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

    def _add_virtual_component(
        self,
        circuit: Any,
        comp_type: ComponentType,
        name: str,
        nodes: list[str],
        params: dict[str, Any],
        node_cache: dict[str, int],
    ) -> None:
        node_indices = [self._node_index(circuit, node_name, node_cache) for node_name in nodes]
        numeric_params: dict[str, float] = {}
        metadata: dict[str, str] = {"component_type": comp_type.name}

        for key, value in params.items():
            param_name = str(key)
            if isinstance(value, bool):
                numeric_params[param_name] = 1.0 if value else 0.0
                continue
            if isinstance(value, (int, float)):
                numeric_params[param_name] = float(value)
                continue

            if isinstance(value, str):
                metadata[param_name] = value
                continue

            try:
                metadata[param_name] = json.dumps(value)
            except TypeError:
                metadata[param_name] = str(value)

        backend_type = self._BACKEND_TYPE_MAP.get(comp_type, comp_type.name.lower())
        try:
            circuit.add_virtual_component(
                backend_type,
                name,
                node_indices,
                numeric_params,
                metadata,
            )
        except Exception as exc:
            raise CircuitConversionError(
                f"Backend converter failed to add virtual component '{comp_type.name}': {exc}"
            ) from exc

    def _as_float(self, value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _waveform_float(
        self,
        waveform: dict[str, Any],
        keys: tuple[str, ...],
        *,
        default: float,
    ) -> float:
        for key in keys:
            if key in waveform:
                return self._as_float(waveform.get(key), default=default)
        return float(default)

    def _switch_closed(self, params: dict[str, Any]) -> bool:
        if "closed" in params:
            return bool(params.get("closed"))
        return bool(params.get("initial_state", False))

    def _switch_conductances(self, params: dict[str, Any]) -> tuple[float, float]:
        g_on_value = params.get("g_on")
        if g_on_value is None:
            ron = self._as_float(params.get("ron"), default=1e-3)
            g_on = 1.0 / max(abs(ron), 1e-15)
        else:
            g_on = self._as_float(g_on_value, default=1e3)

        g_off_value = params.get("g_off")
        if g_off_value is None:
            roff = self._as_float(params.get("roff"), default=1e9)
            g_off = 1.0 / max(abs(roff), 1e-30)
        else:
            g_off = self._as_float(g_off_value, default=1e-9)

        return g_on, g_off


__all__ = ["CircuitConverter", "CircuitConversionError"]
