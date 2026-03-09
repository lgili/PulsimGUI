"""Helpers for converting GUI schematics into Pulsim circuit objects."""

from __future__ import annotations

import json
import time
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
        # Label routers are GUI-only wiring helpers and are resolved before conversion.
        ComponentType.GOTO_LABEL,
        ComponentType.FROM_LABEL,
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

    _PWM_SWITCH_TARGET_PIN: dict[ComponentType, int] = {
        ComponentType.MOSFET_N: 1,
        ComponentType.MOSFET_P: 1,
        ComponentType.IGBT: 1,
        ComponentType.SWITCH: 2,
    }

    # Map GUI ComponentType enum names to the lowercase backend type strings.
    # Most types follow the simple .name.lower() convention; exceptions are listed here.
    _BACKEND_TYPE_MAP: dict[ComponentType, str] = {
        ComponentType.SUBTRACTOR: "subtraction",
        ComponentType.VOLTAGE_PROBE_GND: "voltage_probe",
    }
    _CURRENT_PROBE_BYPASS_RESISTANCE_OHMS = 1e-4

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

        (
            pi_node_overrides,
            pwm_node_overrides,
            pwm_param_overrides,
            controlled_target_node_overrides,
            synthetic_setpoint_sources,
            suppressed_control_component_ids,
        ) = self._infer_native_buck_control_overrides(components, node_map, alias_map)
        cblock_param_overrides = self._infer_cblock_input_channel_overrides(
            components,
            node_map,
        )
        cblock_input_channel_names = self._constant_names_used_as_cblock_inputs(
            components,
            cblock_param_overrides,
        )
        control_override_ids = set(pi_node_overrides) | set(pwm_param_overrides)

        circuit = self._sl.Circuit()
        node_cache: dict[str, int] = {}
        positions_to_apply = []
        resolved_components: list[tuple[dict, ComponentType, str, list[str]]] = []

        for component_index, component in enumerate(components):
            if component_index and component_index % 128 == 0:
                time.sleep(0)
            comp_type = self._component_type(component.get("type"))
            comp_id = str(component.get("id") or "")
            if comp_id in suppressed_control_component_ids:
                continue
            if self._should_skip_component(comp_type) and comp_id not in control_override_ids:
                continue
            nodes = self._resolve_nodes(component, comp_type, node_map, alias_map)
            if comp_id in controlled_target_node_overrides:
                nodes = list(controlled_target_node_overrides[comp_id])
            elif comp_id in pi_node_overrides:
                nodes = list(pi_node_overrides[comp_id])
            elif comp_id in pwm_node_overrides:
                nodes = list(pwm_node_overrides[comp_id])
            name = self._component_name(component, comp_type)
            resolved_components.append((component, comp_type, name, nodes))

        for source_index, source in enumerate(synthetic_setpoint_sources):
            if source_index and source_index % 128 == 0:
                time.sleep(0)
            source_name = str(source["name"])
            source_node = str(source["node"])
            source_value = float(source["value"])
            pseudo_component = {
                "id": f"__synth_ref_{source_name}",
                "type": "VOLTAGE_SOURCE",
                "name": source_name,
                "parameters": {
                    "waveform": {
                        "type": "dc",
                        "value": source_value,
                    }
                },
            }
            resolved_components.append(
                (
                    pseudo_component,
                    ComponentType.VOLTAGE_SOURCE,
                    source_name,
                    [source_node, "0"],
                )
            )

        # Some Pulsim versions expect all non-ground nodes to exist before devices are added.
        self._predeclare_nodes(circuit, resolved_components, node_cache)
        probe_target_overrides = self._infer_probe_target_overrides(resolved_components)

        for resolved_index, (component, comp_type, name, nodes) in enumerate(resolved_components):
            if resolved_index and resolved_index % 128 == 0:
                time.sleep(0)
            if comp_type == ComponentType.GROUND:
                continue

            params_override: dict[str, Any] | None = None
            comp_id = str(component.get("id") or "")
            inferred_target = probe_target_overrides.get(comp_id)
            if inferred_target:
                params_override = dict(component.get("parameters", {}) or {})
                params_override.setdefault("target_component", inferred_target)
            pwm_override = pwm_param_overrides.get(comp_id)
            if pwm_override:
                params_override = dict(params_override or component.get("parameters", {}) or {})
                params_override.update(pwm_override)
            cblock_override = cblock_param_overrides.get(comp_id)
            if cblock_override:
                params_override = dict(params_override or component.get("parameters", {}) or {})
                params_override.update(cblock_override)

            self._add_component(
                circuit,
                comp_type,
                name,
                component,
                nodes,
                node_cache,
                params_override=params_override,
                cblock_input_channel_names=cblock_input_channel_names,
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
        if comp_type == ComponentType.C_BLOCK:
            return True
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
        for component_index, (_component, comp_type, _name, nodes) in enumerate(components):
            if component_index and component_index % 128 == 0:
                time.sleep(0)
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

        if comp_type == ComponentType.C_BLOCK:
            # C-Block inputs are control-channel bindings and should not stamp
            # electrical nodes in the MNA graph.
            return []

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
        cblock_input_channel_names: set[str] | None = None,
    ) -> None:
        params = params_override if params_override is not None else (component.get("parameters", {}) or {})

        if (
            comp_type == ComponentType.CONSTANT
            and name
            and cblock_input_channel_names
            and name in cblock_input_channel_names
            and hasattr(circuit, "add_virtual_component")
            and hasattr(circuit, "add_voltage_source")
        ):
            self._add_constant_as_probe_channel(
                circuit,
                name,
                nodes,
                params,
                node_cache,
            )
            return

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
            use_virtual_pwm = bool(hasattr(circuit, "add_virtual_component")) and (
                bool(str(params.get("duty_from_channel") or "").strip())
                or bool(str(params.get("target_component") or "").strip())
            )
            if use_virtual_pwm:
                virtual_params = dict(params)
                self._sanitize_virtual_pwm_timing(virtual_params)
                self._add_virtual_component(
                    circuit,
                    comp_type,
                    name,
                    nodes,
                    virtual_params,
                    node_cache,
                )
                return

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

        if comp_type == ComponentType.CURRENT_PROBE:
            # Keep IN/OUT electrically continuous; the probe must not open the branch.
            n_in, n_out = self._require_nodes(name, nodes, 2)
            try:
                bypass_r = float(
                    params.get("series_resistance", self._CURRENT_PROBE_BYPASS_RESISTANCE_OHMS)
                )
            except (TypeError, ValueError):
                bypass_r = self._CURRENT_PROBE_BYPASS_RESISTANCE_OHMS
            if bypass_r <= 0.0:
                bypass_r = self._CURRENT_PROBE_BYPASS_RESISTANCE_OHMS

            circuit.add_resistor(
                f"__IP_BYPASS_{name}",
                self._node_index(circuit, n_in, node_cache),
                self._node_index(circuit, n_out, node_cache),
                bypass_r,
            )

            if hasattr(circuit, "add_virtual_component"):
                virtual_params = dict(params)
                virtual_params.setdefault("series_resistance", bypass_r)
                self._add_virtual_component(
                    circuit,
                    comp_type,
                    name,
                    nodes,
                    virtual_params,
                    node_cache,
                )
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

    def _add_constant_as_probe_channel(
        self,
        circuit: Any,
        name: str,
        nodes: list[str],
        params: dict[str, Any],
        node_cache: dict[str, int],
    ) -> None:
        """Emit CONSTANT as a backend-compatible control channel for C-Block inputs.

        Some backend builds do not expose CONSTANT outputs as resolvable C-Block
        control channels. For those cases, synthesize an isolated DC source plus
        a voltage_probe channel with the same component name.
        """
        try:
            value = float(params.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0

        node_name = str(nodes[0] or "").strip() if nodes else ""
        if not node_name or node_name == "0":
            node_name = f"__CONST_CH_{name}"

        source_name = f"__CONST_SRC_{name}"
        npos = self._node_index(circuit, node_name, node_cache)
        nneg = self._node_index(circuit, "0", node_cache)
        circuit.add_voltage_source(source_name, npos, nneg, value)

        self._add_virtual_component(
            circuit,
            ComponentType.VOLTAGE_PROBE_GND,
            name,
            [node_name, "0"],
            {"display_name": name, "scale": 1.0},
            node_cache,
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
                    target.g_on = g_on
                    continue
            if key in {"roff"} and not has_explicit_g_off and hasattr(target, "g_off"):
                g_off = self._conductance_from_resistance(value)
                if g_off is not None:
                    target.g_off = g_off
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
        if comp_type == ComponentType.C_BLOCK:
            # C-Block wiring is resolved via metadata inputs; keep one benign
            # placeholder node for broad backend compatibility.
            return ["0"]
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

    def _infer_native_buck_control_overrides(
        self,
        components: list[dict[str, Any]],
        node_map: dict[str, list[str]],
        alias_map: dict[str, str],
    ) -> tuple[
        dict[str, list[str]],
        dict[str, list[str]],
        dict[str, dict[str, Any]],
        dict[str, list[str]],
        list[dict[str, Any]],
        set[str],
    ]:
        """Infer canonical PI/PWM control overrides for buck-style closed loops.

        This keeps GUI templates compatible with backend-native control:
        - PI nodes => [vref, vout, 0]
        - PWM nodes => [0]
        - PWM metadata => duty_from_channel + target_component
        - C_BLOCK/PID duty wiring to PWM DUTY_IN => duty_from_channel
        """
        try:
            supports_virtual = hasattr(self._sl.Circuit(), "add_virtual_component")
        except Exception:
            supports_virtual = False
        if not supports_virtual:
            return {}, {}, {}, {}, [], set()

        by_id: dict[str, dict[str, Any]] = {}
        by_type: dict[ComponentType, list[dict[str, Any]]] = {}
        for component in components:
            comp_id = str(component.get("id") or "").strip()
            if not comp_id:
                continue
            by_id[comp_id] = component
            comp_type = self._component_type(component.get("type"))
            by_type.setdefault(comp_type, []).append(component)

        def _raw_nodes(component: dict[str, Any]) -> list[str]:
            comp_id = str(component.get("id") or "")
            pin_nodes = component.get("pin_nodes")
            if isinstance(pin_nodes, list) and pin_nodes:
                return [str(node or "").strip() for node in pin_nodes]
            fallback = node_map.get(comp_id, [])
            return [str(node or "").strip() for node in fallback]

        constant_outputs: dict[str, tuple[float, str]] = {}
        for component in by_type.get(ComponentType.CONSTANT, []):
            constant_id = str(component.get("id") or "").strip()
            if not constant_id:
                continue
            nodes = _raw_nodes(component)
            if not nodes:
                continue
            out_node = nodes[0]
            if not out_node:
                continue
            params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            try:
                constant_outputs[out_node] = (float(params.get("value", 0.0)), constant_id)
            except (TypeError, ValueError):
                continue

        probe_outputs: dict[str, tuple[str, str]] = {}
        for component in by_type.get(ComponentType.VOLTAGE_PROBE, []):
            nodes = _raw_nodes(component)
            if len(nodes) < 3:
                continue
            out_node = nodes[2]
            if out_node:
                probe_outputs[out_node] = (nodes[0], nodes[1] or "0")
        for component in by_type.get(ComponentType.VOLTAGE_PROBE_GND, []):
            nodes = _raw_nodes(component)
            if len(nodes) < 2:
                continue
            out_node = nodes[1]
            if out_node:
                probe_outputs[out_node] = (nodes[0], "0")

        pi_node_overrides: dict[str, list[str]] = {}
        pwm_node_overrides: dict[str, list[str]] = {}
        pwm_param_overrides: dict[str, dict[str, Any]] = {}
        controlled_target_node_overrides: dict[str, list[str]] = {}
        synthetic_sources: list[dict[str, Any]] = []
        suppressed_component_ids: set[str] = set()

        for pi_component in by_type.get(ComponentType.PI_CONTROLLER, []):
            pi_id = str(pi_component.get("id") or "").strip()
            pi_name = self._component_name(pi_component, ComponentType.PI_CONTROLLER)
            pi_nodes = _raw_nodes(pi_component)
            if len(pi_nodes) < 2:
                continue
            pi_input_node = pi_nodes[0]
            pi_output_node = pi_nodes[1]

            pwm_component: dict[str, Any] | None = None
            for candidate in by_type.get(ComponentType.PWM_GENERATOR, []):
                candidate_nodes = _raw_nodes(candidate)
                if len(candidate_nodes) >= 2 and candidate_nodes[1] == pi_output_node:
                    pwm_component = candidate
                    break
            if pwm_component is None:
                continue

            subtractor_component: dict[str, Any] | None = None
            for candidate in by_type.get(ComponentType.SUBTRACTOR, []):
                candidate_nodes = _raw_nodes(candidate)
                if len(candidate_nodes) >= 3 and candidate_nodes[2] == pi_input_node:
                    subtractor_component = candidate
                    break
            if subtractor_component is None:
                continue

            sub_nodes = _raw_nodes(subtractor_component)
            if len(sub_nodes) < 2:
                continue

            feedback_pair: tuple[str, str] | None = None
            setpoint_constant: float | None = None
            setpoint_constant_id: str | None = None
            for node in sub_nodes[:2]:
                if node in probe_outputs and feedback_pair is None:
                    feedback_pair = probe_outputs[node]
                    continue
                if node in constant_outputs and setpoint_constant is None:
                    setpoint_constant, setpoint_constant_id = constant_outputs[node]

            if feedback_pair is None or setpoint_constant is None:
                continue

            pwm_id = str(pwm_component.get("id") or "").strip()
            pwm_nodes = _raw_nodes(pwm_component)
            pwm_out_node = pwm_nodes[0] if pwm_nodes else ""
            target_name = self._infer_pwm_target_component_name(
                components,
                node_map,
                pwm_out_node,
            )
            if not target_name:
                continue

            target_component_id = ""
            target_component_type: ComponentType | None = None
            target_component_nodes: list[str] = []
            for candidate in components:
                try:
                    candidate_type = self._component_type(candidate.get("type"))
                except CircuitConversionError:
                    continue
                if candidate_type not in self._PWM_SWITCH_TARGET_PIN:
                    continue
                if self._component_name(candidate, candidate_type) != target_name:
                    continue
                candidate_id = str(candidate.get("id") or "").strip()
                if not candidate_id:
                    continue
                target_component_id = candidate_id
                target_component_type = candidate_type
                target_component_nodes = _raw_nodes(candidate)
                break

            setpoint_raw_node = self._find_reference_voltage_node(components, node_map, setpoint_constant)
            if setpoint_raw_node:
                setpoint_node = self._node_label(setpoint_raw_node, alias_map)
            else:
                setpoint_node = f"{pi_name}_REF".replace(" ", "_")
                synthetic_sources.append(
                    {
                        "name": setpoint_node,
                        "node": setpoint_node,
                        "value": float(setpoint_constant),
                    }
                )
            feedback_plus = self._node_label(feedback_pair[0], alias_map)
            feedback_minus = self._node_label(feedback_pair[1], alias_map)
            pi_node_overrides[pi_id] = [setpoint_node, feedback_plus, feedback_minus]
            pwm_node_overrides[pwm_id] = ["0"]
            pwm_param_overrides[pwm_id] = {
                "duty_from_channel": pi_name,
                "target_component": target_name,
                "duty": float(
                    (
                        pwm_component.get("parameters", {})
                        if isinstance(pwm_component.get("parameters"), dict)
                        else {}
                    ).get("duty_cycle", 0.5)
                ),
            }
            if target_component_type is not None and target_component_id:
                control_pin = self._PWM_SWITCH_TARGET_PIN.get(target_component_type)
                if control_pin is not None and len(target_component_nodes) > control_pin:
                    grounded_target_nodes = list(target_component_nodes)
                    grounded_target_nodes[control_pin] = "0"
                    controlled_target_node_overrides[target_component_id] = [
                        self._node_label(node, alias_map) if node else node
                        for node in grounded_target_nodes
                    ]
            subtractor_id = str(subtractor_component.get("id") or "").strip()
            if subtractor_id:
                suppressed_component_ids.add(subtractor_id)
            if setpoint_constant_id:
                suppressed_component_ids.add(setpoint_constant_id)

        # Generic wiring-based duty inference:
        # If PWM DUTY_IN is driven by a known virtual control block output, convert PWM
        # to backend-native channel-driven mode even without explicit GUI metadata.
        signal_driver_by_node: dict[str, str] = {}
        cblock_channel_aliases: dict[str, str] = {}

        def _register_driver(component: dict[str, Any], output_indices: list[int]) -> None:
            nodes = _raw_nodes(component)
            if not nodes:
                return
            try:
                comp_type = self._component_type(component.get("type"))
            except CircuitConversionError:
                return
            driver_name = self._component_name(component, comp_type)
            if not driver_name:
                return
            for index in output_indices:
                if index < 0 or index >= len(nodes):
                    continue
                node = str(nodes[index] or "").strip()
                if node and node not in signal_driver_by_node:
                    signal_driver_by_node[node] = driver_name

        for cblock in by_type.get(ComponentType.C_BLOCK, []):
            params = cblock.get("parameters") if isinstance(cblock.get("parameters"), dict) else {}
            try:
                n_inputs = max(1, int(params.get("n_inputs", 1) or 1))
            except (TypeError, ValueError):
                n_inputs = 1
            try:
                n_outputs = max(1, int(params.get("n_outputs", 1) or 1))
            except (TypeError, ValueError):
                n_outputs = 1
            nodes = _raw_nodes(cblock)
            if not nodes:
                continue
            cblock_name = self._component_name(cblock, ComponentType.C_BLOCK)
            if not cblock_name:
                continue
            for output_index in range(n_outputs):
                pin_index = n_inputs + output_index
                if pin_index < 0 or pin_index >= len(nodes):
                    continue
                node = str(nodes[pin_index] or "").strip()
                if not node:
                    continue
                # Runtime canonical names:
                # - first output: "<name>"
                # - extra outputs: "<name>.outN"
                output_channel = (
                    cblock_name if output_index == 0 else f"{cblock_name}.out{output_index}"
                )
                if node not in signal_driver_by_node:
                    signal_driver_by_node[node] = output_channel
                # Accept common frontend aliases from older projects.
                alias_tokens = {
                    cblock_name if output_index == 0 else "",
                    f"{cblock_name}.OUT{output_index}",
                    f"{cblock_name}.out{output_index}",
                }
                if output_index == 0:
                    alias_tokens.add(f"{cblock_name}.OUT")
                    alias_tokens.add(f"{cblock_name}.out")
                for alias in alias_tokens:
                    if alias:
                        cblock_channel_aliases[alias] = output_channel
                        cblock_channel_aliases[alias.lower()] = output_channel

        for pi in by_type.get(ComponentType.PI_CONTROLLER, []):
            _register_driver(pi, [1])
        for pid in by_type.get(ComponentType.PID_CONTROLLER, []):
            _register_driver(pid, [1])

        for pwm_component in by_type.get(ComponentType.PWM_GENERATOR, []):
            pwm_id = str(pwm_component.get("id") or "").strip()
            if not pwm_id or pwm_id in pwm_param_overrides:
                continue

            params = (
                pwm_component.get("parameters")
                if isinstance(pwm_component.get("parameters"), dict)
                else {}
            )
            explicit_duty_channel = str(params.get("duty_from_channel") or "").strip()
            if explicit_duty_channel:
                normalized_channel = cblock_channel_aliases.get(
                    explicit_duty_channel
                    if explicit_duty_channel in cblock_channel_aliases
                    else explicit_duty_channel.lower(),
                    explicit_duty_channel,
                )
                if normalized_channel != explicit_duty_channel:
                    pwm_param_overrides[pwm_id] = {"duty_from_channel": normalized_channel}
                continue

            pwm_nodes = _raw_nodes(pwm_component)
            if len(pwm_nodes) < 2:
                continue
            duty_input_node = str(pwm_nodes[1] or "").strip()
            if not duty_input_node:
                continue

            driver_name = signal_driver_by_node.get(duty_input_node)
            if not driver_name:
                continue

            pwm_out_node = str(pwm_nodes[0] or "").strip()
            target_name = str(params.get("target_component") or "").strip()
            if not target_name:
                target_name = self._infer_pwm_target_component_name(
                    components,
                    node_map,
                    pwm_out_node,
                ) or ""

            try:
                duty_default = float(params.get("duty", params.get("duty_cycle", 0.5)))
            except (TypeError, ValueError):
                duty_default = 0.5

            override: dict[str, Any] = {
                "duty_from_channel": driver_name,
                "duty": duty_default,
            }
            if target_name:
                override["target_component"] = target_name
            pwm_param_overrides[pwm_id] = override

            if target_name:
                target_component_id = ""
                target_component_type: ComponentType | None = None
                target_component_nodes: list[str] = []
                for candidate in components:
                    try:
                        candidate_type = self._component_type(candidate.get("type"))
                    except CircuitConversionError:
                        continue
                    if candidate_type not in self._PWM_SWITCH_TARGET_PIN:
                        continue
                    if self._component_name(candidate, candidate_type) != target_name:
                        continue
                    candidate_id = str(candidate.get("id") or "").strip()
                    if not candidate_id:
                        continue
                    target_component_id = candidate_id
                    target_component_type = candidate_type
                    target_component_nodes = _raw_nodes(candidate)
                    break

                if target_component_type is not None and target_component_id:
                    control_pin = self._PWM_SWITCH_TARGET_PIN.get(target_component_type)
                    if control_pin is not None and len(target_component_nodes) > control_pin:
                        grounded_target_nodes = list(target_component_nodes)
                        grounded_target_nodes[control_pin] = "0"
                        controlled_target_node_overrides[target_component_id] = [
                            self._node_label(node, alias_map) if node else node
                            for node in grounded_target_nodes
                        ]

        return (
            pi_node_overrides,
            pwm_node_overrides,
            pwm_param_overrides,
            controlled_target_node_overrides,
            synthetic_sources,
            suppressed_component_ids,
        )

    def _infer_cblock_input_channel_overrides(
        self,
        components: list[dict[str, Any]],
        node_map: dict[str, list[str]],
    ) -> dict[str, dict[str, Any]]:
        """Infer C-Block control-channel input mapping from signal-domain wiring."""

        def _raw_nodes(component: dict[str, Any]) -> list[str]:
            comp_id = str(component.get("id") or "")
            pin_nodes = component.get("pin_nodes")
            if isinstance(pin_nodes, list) and pin_nodes:
                return [str(node or "").strip() for node in pin_nodes]
            fallback = node_map.get(comp_id, [])
            return [str(node or "").strip() for node in fallback]

        signal_driver_by_node: dict[str, str] = {}

        for component in components:
            comp_id = str(component.get("id") or "").strip()
            if not comp_id:
                continue
            try:
                comp_type = self._component_type(component.get("type"))
            except CircuitConversionError:
                continue
            component_name = self._component_name(component, comp_type)
            if not component_name:
                continue

            pin_nodes = _raw_nodes(component)
            if not pin_nodes:
                continue

            pins = component.get("pins")
            if not isinstance(pins, list) or not pins:
                for pin_index, channel_name in self._fallback_signal_output_channels(
                    comp_type,
                    component_name,
                    params=(
                        component.get("parameters")
                        if isinstance(component.get("parameters"), dict)
                        else {}
                    ),
                    node_count=len(pin_nodes),
                ):
                    if pin_index < 0 or pin_index >= len(pin_nodes):
                        continue
                    node_name = str(pin_nodes[pin_index] or "").strip()
                    if not node_name or node_name == "0":
                        continue
                    signal_driver_by_node.setdefault(node_name, channel_name)
                continue

            for pin in pins:
                if not isinstance(pin, dict):
                    continue
                try:
                    pin_index = int(pin.get("index", -1))
                except (TypeError, ValueError):
                    continue
                if pin_index < 0 or pin_index >= len(pin_nodes):
                    continue

                pin_name = str(pin.get("name") or "").strip().upper()
                if not pin_name:
                    continue

                channel_name = ""
                if comp_type == ComponentType.C_BLOCK:
                    if pin_name in {"OUT", "OUT0"}:
                        channel_name = component_name
                    elif pin_name.startswith("OUT"):
                        try:
                            output_index = int(pin_name[3:])
                        except (TypeError, ValueError):
                            continue
                        channel_name = (
                            component_name
                            if output_index == 0
                            else f"{component_name}.out{output_index}"
                        )
                elif comp_type == ComponentType.PWM_GENERATOR:
                    if pin_name == "OUT":
                        channel_name = component_name
                elif comp_type in (
                    ComponentType.VOLTAGE_PROBE,
                    ComponentType.VOLTAGE_PROBE_GND,
                    ComponentType.CURRENT_PROBE,
                ):
                    if pin_name in {"OUT", "MEAS"}:
                        channel_name = component_name
                else:
                    if pin_name == "OUT":
                        channel_name = component_name

                if not channel_name:
                    continue
                node_name = str(pin_nodes[pin_index] or "").strip()
                if not node_name or node_name == "0":
                    continue
                signal_driver_by_node.setdefault(node_name, channel_name)

        known_control_channels = {
            str(channel_name).strip()
            for channel_name in signal_driver_by_node.values()
            if str(channel_name or "").strip()
        }
        known_control_channels_lut = {
            channel_name.lower(): channel_name for channel_name in known_control_channels
        }

        def _map_cblock_inputs_from_wiring(
            *,
            component_name: str,
            pin_nodes: list[str],
            n_inputs: int,
        ) -> list[str]:
            mapped: list[str] = []
            for input_index in range(n_inputs):
                node_name = (
                    str(pin_nodes[input_index] or "").strip()
                    if input_index < len(pin_nodes)
                    else ""
                )
                if not node_name:
                    raise CircuitConversionError(
                        "C-Block "
                        f"'{component_name}' input IN{input_index} is unconnected. "
                        "Connect it to a control signal source "
                        "(for example probe OUT, PI/PID OUT, SUM/SUB OUT, CONSTANT OUT) "
                        "or set metadata 'inputs'."
                    )
                channel_name = signal_driver_by_node.get(node_name, "")
                if not channel_name:
                    raise CircuitConversionError(
                        "C-Block "
                        f"'{component_name}' input IN{input_index} must be driven by a "
                        "control signal output. "
                        f"No channel mapping was found for node '{node_name}'."
                    )
                mapped.append(channel_name)
            return mapped

        overrides: dict[str, dict[str, Any]] = {}
        for component in components:
            comp_id = str(component.get("id") or "").strip()
            if not comp_id:
                continue
            try:
                comp_type = self._component_type(component.get("type"))
            except CircuitConversionError:
                continue
            if comp_type != ComponentType.C_BLOCK:
                continue

            component_name = self._component_name(component, comp_type)
            pins = component.get("pins")
            if not isinstance(pins, list) or not pins:
                # Legacy/minimal payload without pin schema: keep compatibility.
                continue
            params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            pin_nodes = _raw_nodes(component)
            try:
                n_inputs = max(1, int(params.get("n_inputs", 1) or 1))
            except (TypeError, ValueError):
                n_inputs = 1

            explicit_inputs = self._parse_cblock_input_channel_list(
                params.get("inputs", params.get("input_channels"))
            )
            mapped_inputs: list[str] | None = None
            if explicit_inputs:
                if len(explicit_inputs) != n_inputs:
                    raise CircuitConversionError(
                        "C-Block "
                        f"'{component_name}' expects n_inputs={n_inputs}, "
                        f"but metadata declares {len(explicit_inputs)} channels."
                    )

                normalized_explicit: list[str] = []
                unresolved_explicit: list[str] = []
                for channel_name in explicit_inputs:
                    raw_name = str(channel_name or "").strip()
                    if not raw_name:
                        continue
                    canonical_name = known_control_channels_lut.get(raw_name.lower(), raw_name)
                    normalized_explicit.append(canonical_name)
                    if canonical_name not in known_control_channels:
                        unresolved_explicit.append(raw_name)

                if not unresolved_explicit:
                    mapped_inputs = normalized_explicit
                else:
                    # Stale metadata can survive project edits even when GUI no longer
                    # exposes the raw input-channel list. If wiring is available, prefer
                    # deriving channels from IN pins to self-heal these projects.
                    try:
                        mapped_inputs = _map_cblock_inputs_from_wiring(
                            component_name=component_name,
                            pin_nodes=pin_nodes,
                            n_inputs=n_inputs,
                        )
                    except CircuitConversionError:
                        # Preserve legacy behavior when no wiring exists (library mode).
                        mapped_inputs = normalized_explicit
            else:
                mapped_inputs = _map_cblock_inputs_from_wiring(
                    component_name=component_name,
                    pin_nodes=pin_nodes,
                    n_inputs=n_inputs,
                )

            cblock_override: dict[str, Any] = {
                "inputs": list(mapped_inputs),
            }
            overrides[comp_id] = cblock_override

        return overrides

    def _constant_names_used_as_cblock_inputs(
        self,
        components: list[dict[str, Any]],
        cblock_param_overrides: dict[str, dict[str, Any]],
    ) -> set[str]:
        """Return CONSTANT component names referenced by C-Block input channels."""
        constant_names: set[str] = set()
        for component in components:
            try:
                comp_type = self._component_type(component.get("type"))
            except CircuitConversionError:
                continue
            if comp_type != ComponentType.CONSTANT:
                continue
            name = self._component_name(component, comp_type)
            if name:
                constant_names.add(name)

        if not constant_names:
            return set()

        referenced: set[str] = set()
        for override in cblock_param_overrides.values():
            inputs = override.get("inputs")
            if not isinstance(inputs, list):
                continue
            for channel in inputs:
                channel_name = str(channel or "").strip()
                if channel_name and channel_name in constant_names:
                    referenced.add(channel_name)
        return referenced

    @staticmethod
    def _parse_cblock_input_channel_list(raw_value: Any) -> list[str]:
        """Parse C-Block input-channel metadata from list/scalar forms."""
        if raw_value is None:
            return []

        if isinstance(raw_value, list):
            channels = [str(item or "").strip() for item in raw_value]
            return [channel for channel in channels if channel]

        if isinstance(raw_value, tuple):
            channels = [str(item or "").strip() for item in raw_value]
            return [channel for channel in channels if channel]

        text = str(raw_value).strip()
        if not text:
            return []

        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            channels = [str(item or "").strip() for item in parsed]
            return [channel for channel in channels if channel]

        if "," in text:
            channels = [token.strip() for token in text.split(",")]
            return [channel for channel in channels if channel]

        return [text]

    @staticmethod
    def _fallback_signal_output_channels(
        comp_type: ComponentType,
        component_name: str,
        *,
        params: dict[str, Any],
        node_count: int,
    ) -> list[tuple[int, str]]:
        """Best-effort output channel mapping when serialized pin metadata is missing."""
        if node_count <= 0:
            return []

        if comp_type == ComponentType.C_BLOCK:
            try:
                n_inputs = max(1, int(params.get("n_inputs", 1) or 1))
            except (TypeError, ValueError):
                n_inputs = 1
            try:
                n_outputs = max(1, int(params.get("n_outputs", 1) or 1))
            except (TypeError, ValueError):
                n_outputs = 1
            outputs: list[tuple[int, str]] = []
            for output_index in range(n_outputs):
                pin_index = n_inputs + output_index
                if pin_index >= node_count:
                    break
                channel_name = (
                    component_name
                    if output_index == 0
                    else f"{component_name}.out{output_index}"
                )
                outputs.append((pin_index, channel_name))
            return outputs

        if comp_type == ComponentType.PWM_GENERATOR:
            return [(0, component_name)] if node_count >= 1 else []
        if comp_type in (ComponentType.VOLTAGE_PROBE,):
            return [(2, component_name)] if node_count >= 3 else []
        if comp_type == ComponentType.VOLTAGE_PROBE_GND:
            return [(1, component_name)] if node_count >= 2 else []
        if comp_type == ComponentType.CURRENT_PROBE:
            return [(2, component_name)] if node_count >= 3 else []
        if comp_type == ComponentType.CONSTANT:
            return [(0, component_name)] if node_count >= 1 else []
        if comp_type == ComponentType.PI_CONTROLLER:
            return [(1, component_name)] if node_count >= 2 else []
        if comp_type == ComponentType.PID_CONTROLLER:
            return [(2, component_name)] if node_count >= 3 else []
        if comp_type in {
            ComponentType.GAIN,
            ComponentType.INTEGRATOR,
            ComponentType.DIFFERENTIATOR,
            ComponentType.LIMITER,
            ComponentType.RATE_LIMITER,
            ComponentType.HYSTERESIS,
            ComponentType.LOOKUP_TABLE,
            ComponentType.TRANSFER_FUNCTION,
            ComponentType.DELAY_BLOCK,
        }:
            return [(1, component_name)] if node_count >= 2 else []
        if comp_type in {ComponentType.SUM, ComponentType.SUBTRACTOR}:
            try:
                output_pin = int(params.get("input_count", 2) or 2)
            except (TypeError, ValueError):
                output_pin = 2
            output_pin = max(0, min(node_count - 1, output_pin))
            return [(output_pin, component_name)]
        if comp_type in {ComponentType.MATH_BLOCK, ComponentType.SAMPLE_HOLD, ComponentType.STATE_MACHINE}:
            output_pin = min(node_count - 1, 2)
            return [(output_pin, component_name)]

        return []

    def _find_reference_voltage_node(
        self,
        components: list[dict[str, Any]],
        node_map: dict[str, list[str]],
        target_value: float,
    ) -> str | None:
        """Find a voltage-source positive node suitable as PI reference."""
        preferred: str | None = None
        fallback: str | None = None

        for component in components:
            if str(component.get("type", "")).strip().upper() != "VOLTAGE_SOURCE":
                continue
            comp_id = str(component.get("id") or "").strip()
            params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            waveform = params.get("waveform") if isinstance(params.get("waveform"), dict) else {}
            if str(waveform.get("type", "dc")).strip().lower() != "dc":
                continue
            try:
                value = float(waveform.get("value", 0.0))
            except (TypeError, ValueError):
                continue

            nodes = component.get("pin_nodes")
            if not isinstance(nodes, list) or len(nodes) < 1:
                nodes = node_map.get(comp_id, [])
            if not nodes:
                continue
            pos_node = str(nodes[0] or "").strip()
            if not pos_node:
                continue

            if abs(value - target_value) <= max(1e-6, abs(target_value) * 1e-6):
                name = str(component.get("name") or "").strip().lower()
                if name == "vref":
                    preferred = pos_node
                    break
                if fallback is None:
                    fallback = pos_node

        return preferred or fallback

    def _infer_pwm_target_component_name(
        self,
        components: list[dict[str, Any]],
        node_map: dict[str, list[str]],
        pwm_out_node: str,
    ) -> str | None:
        """Infer switchable target component connected to PWM output net."""
        out_node = str(pwm_out_node or "").strip()
        if not out_node:
            return None

        for component in components:
            try:
                comp_type = self._component_type(component.get("type"))
            except CircuitConversionError:
                continue
            control_pin = self._PWM_SWITCH_TARGET_PIN.get(comp_type)
            if control_pin is None:
                continue
            comp_id = str(component.get("id") or "").strip()
            nodes = component.get("pin_nodes")
            if not isinstance(nodes, list) or len(nodes) <= control_pin:
                nodes = node_map.get(comp_id, [])
            if len(nodes) <= control_pin:
                continue
            ctrl_node = str(nodes[control_pin] or "").strip()
            if ctrl_node != out_node:
                continue
            return self._component_name(component, comp_type)

        return None

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

        if comp_type == ComponentType.C_BLOCK:
            normalized.pop("compiler", None)
            implementation = str(normalized.get("implementation", "") or "").strip().lower()
            source = str(normalized.get("source", "") or "").strip()
            lib_path = str(normalized.get("lib_path", "") or "").strip()
            if implementation == "library":
                source = ""
            elif implementation == "source":
                lib_path = ""
            elif source and lib_path:
                lib_path = ""

            try:
                normalized["n_inputs"] = max(1, int(normalized.get("n_inputs", 1) or 1))
            except (TypeError, ValueError):
                normalized["n_inputs"] = 1
            try:
                normalized["n_outputs"] = max(1, int(normalized.get("n_outputs", 1) or 1))
            except (TypeError, ValueError):
                normalized["n_outputs"] = 1

            flags = normalized.get("extra_cflags", [])
            if isinstance(flags, list):
                normalized["extra_cflags"] = [str(item).strip() for item in flags if str(item).strip()]
            elif isinstance(flags, str):
                text = flags.strip()
                tokens = [part.strip() for part in text.split(",")] if "," in text else text.split()
                normalized["extra_cflags"] = [token for token in tokens if token]
            else:
                normalized["extra_cflags"] = []

            normalized["source"] = source.replace("\\", "/")
            normalized["lib_path"] = lib_path.replace("\\", "/")
            normalized.pop("implementation", None)
            normalized.pop("source_code", None)

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

        if comp_type == ComponentType.PWM_GENERATOR:
            if "duty_cycle" in normalized and "duty" not in normalized:
                normalized["duty"] = normalized["duty_cycle"]
            if "amplitude" in normalized and "v_high" not in normalized:
                normalized["v_high"] = normalized["amplitude"]
            normalized.setdefault("v_low", 0.0)

        return normalized

    def _sanitize_virtual_pwm_timing(self, params: dict[str, Any]) -> None:
        """Prevent virtual PWM carrier lock when sample interval matches switching period.

        Some backend builds evaluate virtual PWM carrier only at control sampling
        instants. If ``sample_time`` is equal to ``1/frequency``, the carrier is
        repeatedly sampled at the reset phase and can appear frozen at 0.
        """
        try:
            frequency = float(params.get("frequency", 0.0))
        except (TypeError, ValueError):
            return
        if frequency <= 0.0:
            return

        sample_time: float | None = None
        for key in ("sample_time", "sample_period"):
            if key not in params:
                continue
            try:
                candidate = float(params.get(key))
            except (TypeError, ValueError):
                continue
            if candidate > 0.0:
                sample_time = candidate
                break
        if sample_time is None:
            return

        switching_period = 1.0 / frequency
        if sample_time >= switching_period * (1.0 - 1e-12):
            params["sample_time"] = 0.0
            params["sample_period"] = 0.0

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
