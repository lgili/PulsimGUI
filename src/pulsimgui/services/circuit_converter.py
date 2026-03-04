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
        ComponentType.ELECTRICAL_SCOPE,
        ComponentType.THERMAL_SCOPE,
        ComponentType.SIGNAL_MUX,
        ComponentType.SIGNAL_DEMUX,
        ComponentType.GOTO_LABEL,
        ComponentType.FROM_LABEL,
        # Signal-domain control blocks are evaluated by the backend-provided
        # signal evaluator (pulsim.signal_evaluator) and therefore do not map
        # to direct C++ circuit elements in this converter.
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

    _PROBE_TARGET_CANDIDATES = frozenset(
        {
            ComponentType.RESISTOR,
            ComponentType.CAPACITOR,
            ComponentType.INDUCTOR,
            ComponentType.VOLTAGE_SOURCE,
            ComponentType.CURRENT_SOURCE,
            ComponentType.DIODE,
            ComponentType.ZENER_DIODE,
            ComponentType.LED,
            ComponentType.MOSFET_N,
            ComponentType.MOSFET_P,
            ComponentType.IGBT,
            ComponentType.TRANSFORMER,
            ComponentType.SWITCH,
            ComponentType.SNUBBER_RC,
            ComponentType.PWM_GENERATOR,
        }
    )

    # Map GUI ComponentType enum names to the lowercase backend type strings.
    # Most types follow the simple .name.lower() convention; exceptions are listed here.
    _BACKEND_TYPE_MAP: dict[ComponentType, str] = {
        ComponentType.SUBTRACTOR: "subtraction",
        ComponentType.VOLTAGE_PROBE_GND: "voltage_probe",
    }

    _ATTRIBUTE_ALIASES: dict[str, tuple[str, ...]] = {
        "vce_sat": ("v_ce_sat",),
        "v_ce_sat": ("vce_sat",),
        "open_loop_gain": ("gain",),
        "gain": ("open_loop_gain",),
        "offset": ("vos",),
        "vos": ("offset",),
        "output_min": ("min", "rail_low"),
        "output_max": ("max", "rail_high"),
        "lower_limit": ("output_min", "min", "rail_low"),
        "upper_limit": ("output_max", "max", "rail_high"),
        "output_low": ("low",),
        "output_high": ("high",),
        "sample_time": ("sample_period",),
        "sample_period": ("sample_time",),
        "delay_time": ("delay",),
        "delay": ("delay_time",),
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
            nodes = self._resolve_nodes(component, comp_type, node_map, alias_map)
            name = self._component_name(component, comp_type)
            resolved_components.append((component, comp_type, name, nodes))

        # Some Pulsim versions expect all non-ground nodes to exist before devices are added.
        self._predeclare_nodes(circuit, resolved_components, node_cache)
        probe_target_overrides = self._infer_probe_target_overrides(resolved_components)

        for component, comp_type, name, nodes in resolved_components:
            if comp_type == ComponentType.GROUND:
                continue

            params_override: dict[str, Any] | None = None
            comp_id = str(component.get("id") or "")
            inferred_target = probe_target_overrides.get(comp_id)
            if inferred_target:
                params_override = dict(component.get("parameters", {}) or {})
                params_override.setdefault("target_component", inferred_target)

            self._add_component(
                circuit,
                comp_type,
                name,
                component,
                nodes,
                node_cache,
                params_override=params_override,
            )

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
        comp_type: ComponentType,
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
        for pin_index, raw in enumerate(pin_nodes):
            if raw is None or raw == "":
                # Probe output pins may be intentionally unconnected in the GUI.
                if self._allows_unmapped_pin(comp_type, pin_index):
                    resolved.append("0")
                    continue
                raise CircuitConversionError(
                    f"Unmapped node for component '{component.get('name') or comp_id}'"
                )
            resolved.append(self._node_label(raw, alias_map))
        return resolved

    @staticmethod
    def _allows_unmapped_pin(comp_type: ComponentType, pin_index: int) -> bool:
        if comp_type == ComponentType.VOLTAGE_PROBE:
            return pin_index == 2
        if comp_type == ComponentType.VOLTAGE_PROBE_GND:
            return pin_index == 1
        if comp_type == ComponentType.CURRENT_PROBE:
            return pin_index == 2
        return False

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

        if comp_type == ComponentType.VOLTAGE_PROBE:
            return nodes[:2]

        if comp_type == ComponentType.VOLTAGE_PROBE_GND:
            return nodes[:1]

        if comp_type == ComponentType.CURRENT_PROBE:
            return nodes[:2]

        if comp_type == ComponentType.POWER_PROBE:
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
        *,
        params_override: dict[str, Any] | None = None,
    ) -> None:
        params = params_override if params_override is not None else (component.get("parameters", {}) or {})

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
        has_explicit_g_on = "g_on" in values
        has_explicit_g_off = "g_off" in values

        for key, value in values.items():
            if key in {"rds_on", "ron"} and not has_explicit_g_on and hasattr(target, "g_on"):
                g_on = self._conductance_from_resistance(value)
                if g_on is not None:
                    setattr(target, "g_on", g_on)
                    continue
            if key in {"roff"} and not has_explicit_g_off and hasattr(target, "g_off"):
                g_off = self._conductance_from_resistance(value)
                if g_off is not None:
                    setattr(target, "g_off", g_off)
                    continue

            for attr in self._attribute_candidates(str(key)):
                if hasattr(target, attr):
                    setattr(target, attr, value)
                    break

    def _add_virtual_component(
        self,
        circuit: Any,
        comp_type: ComponentType,
        name: str,
        nodes: list[str],
        params: dict[str, Any],
        node_cache: dict[str, int],
    ) -> None:
        virtual_nodes = self._virtual_component_nodes(comp_type, nodes)
        node_indices = [self._node_index(circuit, node_name, node_cache) for node_name in virtual_nodes]
        numeric_params: dict[str, float] = {}
        metadata: dict[str, str] = {"component_type": comp_type.name}
        normalized_params = self._normalize_virtual_component_params(comp_type, params)

        for key, value in normalized_params.items():
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

    def _virtual_component_nodes(self, comp_type: ComponentType, nodes: list[str]) -> list[str]:
        """Return node subset/normalization used for backend virtual components."""
        if comp_type == ComponentType.VOLTAGE_PROBE:
            return nodes[:2]
        if comp_type == ComponentType.VOLTAGE_PROBE_GND:
            in_node = nodes[0] if nodes else "0"
            return [in_node, "0"]
        if comp_type == ComponentType.CURRENT_PROBE:
            if len(nodes) >= 2:
                return nodes[:2]
            if len(nodes) == 1:
                return [nodes[0], "0"]
            return ["0", "0"]
        if comp_type == ComponentType.POWER_PROBE:
            if len(nodes) >= 2:
                return nodes[:2]
            if len(nodes) == 1:
                return [nodes[0], "0"]
            return ["0", "0"]
        return nodes

    def _infer_probe_target_overrides(
        self,
        components: list[tuple[dict, ComponentType, str, list[str]]],
    ) -> dict[str, str]:
        """Infer best-effort target_component metadata for current/power probes."""
        branch_candidates: list[tuple[str, set[str]]] = []
        for _component, comp_type, name, nodes in components:
            if comp_type in self._PROBE_TARGET_CANDIDATES:
                branch_candidates.append((name, set(nodes)))

        if not branch_candidates:
            return {}

        inferred: dict[str, str] = {}
        for component, comp_type, _name, nodes in components:
            comp_id = str(component.get("id") or "")
            if not comp_id:
                continue

            target: str | None = None
            if comp_type == ComponentType.CURRENT_PROBE:
                target = self._infer_probe_target(nodes[:2], branch_candidates, prefer_second_node=True)
            elif comp_type == ComponentType.POWER_PROBE:
                current_nodes = nodes[2:4] if len(nodes) >= 4 else nodes[:2]
                target = self._infer_probe_target(
                    current_nodes,
                    branch_candidates,
                    prefer_second_node=False,
                )

            if target:
                inferred[comp_id] = target

        return inferred

    @staticmethod
    def _infer_probe_target(
        probe_nodes: list[str],
        candidates: list[tuple[str, set[str]]],
        *,
        prefer_second_node: bool,
    ) -> str | None:
        if not probe_nodes:
            return None

        first_node = probe_nodes[0]
        second_node = probe_nodes[1] if len(probe_nodes) > 1 else None
        preferred_node = second_node if (prefer_second_node and second_node is not None) else first_node
        fallback_node = first_node if preferred_node == second_node else second_node

        if second_node is not None:
            same_branch = [
                candidate_name
                for candidate_name, candidate_nodes in candidates
                if first_node in candidate_nodes and second_node in candidate_nodes
            ]
            if same_branch:
                return same_branch[0]

        for node in (preferred_node, fallback_node):
            if node is None:
                continue
            touching = [
                candidate_name
                for candidate_name, candidate_nodes in candidates
                if node in candidate_nodes
            ]
            if touching:
                return touching[0]

        return None

    def _attribute_candidates(self, key: str) -> tuple[str, ...]:
        values: list[str] = [key]
        if key.endswith("_"):
            values.append(key[:-1])
        if "_" in key:
            values.append(key.rstrip("_"))
        values.extend(self._ATTRIBUTE_ALIASES.get(key, ()))

        ordered: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value and value not in seen:
                ordered.append(value)
                seen.add(value)
        return tuple(ordered)

    @staticmethod
    def _conductance_from_resistance(value: Any) -> float | None:
        try:
            resistance = abs(float(value))
        except (TypeError, ValueError):
            return None
        if resistance <= 0.0:
            return None
        return 1.0 / max(resistance, 1e-30)

    def _normalize_virtual_component_params(
        self,
        comp_type: ComponentType,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(params)

        if "lower_limit" in normalized and "output_min" not in normalized:
            normalized["output_min"] = normalized["lower_limit"]
        if "upper_limit" in normalized and "output_max" not in normalized:
            normalized["output_max"] = normalized["upper_limit"]
        if "output_min" in normalized:
            normalized.setdefault("min", normalized["output_min"])
        if "output_max" in normalized:
            normalized.setdefault("max", normalized["output_max"])

        if "output_low" in normalized and "low" not in normalized:
            normalized["low"] = normalized["output_low"]
        if "output_high" in normalized and "high" not in normalized:
            normalized["high"] = normalized["output_high"]

        if "upper_threshold" in normalized or "lower_threshold" in normalized:
            try:
                upper = float(normalized.get("upper_threshold", normalized.get("threshold", 0.5)))
                lower = float(normalized.get("lower_threshold", normalized.get("threshold", -0.5)))
            except (TypeError, ValueError):
                upper = 0.5
                lower = -0.5
            if "threshold" not in normalized:
                normalized["threshold"] = (upper + lower) / 2.0
            if "hysteresis" not in normalized:
                normalized["hysteresis"] = abs(upper - lower)

        if "sample_time" in normalized and "sample_period" not in normalized:
            normalized["sample_period"] = normalized["sample_time"]

        if "delay_time" in normalized and "delay" not in normalized:
            normalized["delay"] = normalized["delay_time"]
        if "delay" in normalized and "delay_time" not in normalized:
            normalized["delay_time"] = normalized["delay"]

        if comp_type in (ComponentType.PI_CONTROLLER, ComponentType.PID_CONTROLLER):
            normalized.setdefault("anti_windup", True)

        if comp_type == ComponentType.OP_AMP:
            if "open_loop_gain" in normalized and "gain" not in normalized:
                normalized["gain"] = normalized["open_loop_gain"]
            if "offset" in normalized and "vos" not in normalized:
                normalized["vos"] = normalized["offset"]
            if "rail_low" in normalized and "output_min" not in normalized:
                normalized["output_min"] = normalized["rail_low"]
            if "rail_high" in normalized and "output_max" not in normalized:
                normalized["output_max"] = normalized["rail_high"]

        if comp_type == ComponentType.COMPARATOR:
            normalized.setdefault("threshold", float(normalized.get("vos", 0.0) or 0.0))
            normalized.setdefault("high", 1.0)
            normalized.setdefault("low", 0.0)

        return normalized

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
