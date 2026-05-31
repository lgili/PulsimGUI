"""Helpers for converting GUI schematics into Pulsim circuit objects."""

from __future__ import annotations

import copy
import json
import time
import uuid
from typing import Any

from pulsimgui.models.component import ComponentType, DUTY_INPUT_PARAMETER


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
        # Subcircuit instances are GUI-only containers — the backend has no
        # native concept of a hierarchical sub-block. We expand each
        # SUBCIRCUIT in ``circuit_data["components"]`` into its internal
        # primitives BEFORE any other processing so the downstream code
        # only ever sees a flat netlist. The pre-pass mutates the
        # ``circuit_data`` dict in place: it appends translated copies of
        # the internal components (with synthesized per-instance net
        # names to avoid sibling-instance collisions) and removes each
        # SUBCIRCUIT entry from both ``components`` and ``node_map``.
        self._flatten_subcircuits(circuit_data)

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
            closed_loop_descriptors,
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
            # FOC-controller markers (C_BLOCK ``control_kind="foc"``) carry
            # no electrical connectivity — they are descriptor-only and are
            # consumed later by ``_infer_foc_loops``. Skip node resolution
            # so an unwired marker doesn't trip the connectivity check.
            if comp_type == ComponentType.C_BLOCK and self._is_foc_marker(
                component.get("parameters")
            ):
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

        # Attach detected closed-loop descriptors to the shim circuit so
        # the backend's transient runner can wire ``bind_pi_to_switch``.
        # Empty list ⇒ open-loop circuit, backend falls back to the
        # legacy static PWM ``switch_fn`` path.
        try:
            setattr(circuit, "closed_loop_descriptors", list(closed_loop_descriptors))
        except Exception:  # noqa: BLE001 - some shims may be slot-restricted
            pass

        # Detect python_numba C_BLOCKs regulating a PWM-driven switch
        # and attach their loop descriptors. This is a standalone pass
        # (it does NOT touch the PI-detection logic above) — the
        # backend compiles each via FastBlockService and runs it as a
        # ClosedLoop. Empty list ⇒ no fast_block controllers.
        try:
            cblock_loops = self._infer_cblock_control_loops(
                components, node_map, alias_map,
            )
            setattr(circuit, "cblock_loop_descriptors", cblock_loops)
        except Exception:  # noqa: BLE001 - detection must never break a build
            pass

        # Detect a Field-Oriented-Control marker (a C_BLOCK carrying
        # ``control_kind="foc"``) co-resident with a native 3φ VSI + a
        # dynamic PMSM, and attach a ``foc_loop_descriptors`` entry. The
        # backend (``_build_foc_loops``) closes the FOC loop at simulate
        # time over the PMSM observer bundle (d-q currents / rotor angle)
        # and drives the VSI via inverse Park/Clarke. Additive: empty
        # unless the FOC marker is present, so it never perturbs the
        # open-loop VSI / averaged-VSI / cblock paths above.
        try:
            foc_loops = self._infer_foc_loops(components)
            setattr(circuit, "foc_loop_descriptors", foc_loops)
        except Exception:  # noqa: BLE001 - detection must never break a build
            pass

        return circuit

    # ------------------------------------------------------------------
    # Subcircuit flattening
    # ------------------------------------------------------------------
    def _flatten_subcircuits(self, circuit_data: dict) -> None:
        """Expand SUBCIRCUIT instances into their internal primitives.

        Mutates ``circuit_data`` in place. After this call:
          - ``circuit_data["components"]`` no longer contains any entry
            with ``type == "SUBCIRCUIT"``. Each instance has been replaced
            with a fresh translated copy of every component from its
            definition's internal ``Circuit``.
          - ``circuit_data["node_map"]`` carries pin assignments for the
            new flattened components. The original SUBCIRCUIT entry's
            ``node_map`` row is dropped.

        Translation rules for an instance ``I`` of definition ``D``:
          - Each port of ``D`` maps an internal net to the external net
            that ``I``'s corresponding instance pin is wired to.
          - All non-port internal nets are rewritten to a unique synthetic
            name ``__sub_{instance_id_short}__{internal_net}`` so two
            instances of the same definition cannot accidentally short
            their internals through a shared net name.

        Recursion: a definition may itself contain SUBCIRCUIT instances.
        We track an in-progress set of definition IDs as we descend and
        raise ``CircuitConversionError`` on a cycle (A→A, A→B→A, etc.).
        Nested instances are expanded depth-first — by the time we
        translate ``I``'s pins, ``D``'s internal circuit is guaranteed to
        be fully flat.

        Missing definitions are treated as conversion errors so the GUI
        surfaces a clear "subcircuit not found" message rather than
        silently dropping the instance.
        """
        components_list = circuit_data.get("components")
        if not isinstance(components_list, list) or not components_list:
            return

        defs_raw = circuit_data.get("subcircuits") or {}
        # ``defs_raw`` is keyed by str(definition_id). Coerce to a
        # consistent shape so look-ups by either string or UUID succeed.
        defs_by_id: dict[str, dict] = {
            str(key): value for key, value in defs_raw.items() if isinstance(value, dict)
        }

        node_map: dict[str, list[str]] = circuit_data.get("node_map") or {}
        if not isinstance(node_map, dict):
            node_map = {}
            circuit_data["node_map"] = node_map

        # Iterate until no SUBCIRCUIT entries remain. Each pass expands
        # one outermost layer; nested SUBCIRCUITs surfaced by the
        # expansion get caught on the next pass. Cycle detection lives
        # inside ``_expand_single_instance`` via the ``in_progress`` set.
        guard = 0
        max_iterations = 1024
        while True:
            guard += 1
            if guard > max_iterations:
                raise CircuitConversionError(
                    "Subcircuit flattening exceeded recursion guard "
                    f"({max_iterations} iterations); aborting."
                )

            # Snapshot indices of SUBCIRCUIT entries so we can drop them
            # after expansion without mutating the list mid-iteration.
            instance_indices: list[int] = []
            for index, component in enumerate(components_list):
                if not isinstance(component, dict):
                    continue
                raw_type = component.get("type")
                if isinstance(raw_type, str) and raw_type.strip().upper() == "SUBCIRCUIT":
                    instance_indices.append(index)

            if not instance_indices:
                return

            # Expand in reverse order so list.pop(index) doesn't shift
            # later indices we still need.
            for index in reversed(instance_indices):
                instance = components_list[index]
                expanded = self._expand_single_instance(
                    instance,
                    defs_by_id,
                    node_map,
                    in_progress=set(),
                )
                # Drop the SUBCIRCUIT entry from the netlist + node_map
                # before appending the expanded primitives.
                instance_id = str(instance.get("id") or "")
                components_list.pop(index)
                if instance_id:
                    node_map.pop(instance_id, None)
                for new_component in expanded:
                    components_list.append(new_component)
                    new_comp_id = str(new_component.get("id") or "")
                    if new_comp_id and "pin_nodes" in new_component:
                        node_map[new_comp_id] = list(
                            new_component["pin_nodes"]
                        )

    def _expand_single_instance(
        self,
        instance: dict,
        defs_by_id: dict[str, dict],
        node_map: dict[str, list[str]],
        *,
        in_progress: set[str],
    ) -> list[dict]:
        """Translate one SUBCIRCUIT instance into a list of flat component dicts.

        Recurses into nested SUBCIRCUITs by pre-expanding them on a fresh
        copy of the internal circuit data BEFORE translating ``instance``'s
        own pins. ``in_progress`` carries the call stack of definition IDs
        currently being expanded — if the definition we're about to enter
        is already in the set, that's a cycle and we abort.
        """
        from pulsimgui.models.circuit import Circuit
        from pulsimgui.models.subcircuit import SubcircuitDefinition
        from pulsimgui.utils.net_utils import build_node_map

        instance_id = str(instance.get("id") or "")
        instance_name = str(instance.get("name") or "") or instance_id or "subckt"

        # Find the definition ID. ``SubcircuitInstance.to_dict`` writes
        # it at top level; older payloads may carry it inside
        # ``parameters`` — check both for backward compatibility.
        def_id_raw = instance.get("subcircuit_id")
        if not def_id_raw:
            params = instance.get("parameters") if isinstance(instance.get("parameters"), dict) else {}
            def_id_raw = params.get("subcircuit_id") if isinstance(params, dict) else None
        def_id = str(def_id_raw) if def_id_raw else ""

        if not def_id or def_id not in defs_by_id:
            raise CircuitConversionError(
                f"Subcircuit instance '{instance_name}' references unknown "
                f"definition '{def_id or '<missing>'}'"
            )

        if def_id in in_progress:
            defn_name = str(defs_by_id[def_id].get("name") or def_id)
            raise CircuitConversionError(
                f"Recursive subcircuit reference detected: {defn_name}"
            )

        definition_dict = defs_by_id[def_id]

        # Rehydrate the definition's internal Circuit. We work on a
        # deepcopy of the dict so the cached project-level definition
        # stays untouched.
        definition = SubcircuitDefinition.from_dict(copy.deepcopy(definition_dict))
        internal_circuit: Circuit = definition.circuit

        # If the user placed SUBCIRCUIT_PORT markers inside the body,
        # rebuild ``definition.ports`` from them as a safety net.
        # (The GUI already auto-syncs on every edit, but the converter
        # owns the contract here — if any path skipped the live sync,
        # we fix it before reading port.internal_node below.)
        from pulsimgui.models.subcircuit import sync_definition_ports_from_markers
        sync_definition_ports_from_markers(definition)

        # Build the canonical pin→net map for the internal circuit.
        # Keys are ``(component_id_str, pin_index) → net_name``.
        internal_node_map = build_node_map(internal_circuit)

        # Build the external translation table for the instance ports:
        # internal_net → external_net.
        port_translation: dict[str, str] = {}
        external_pin_nodes = list(instance.get("pin_nodes") or node_map.get(instance_id) or [])
        for port in definition.ports:
            internal_net = str(port.internal_node or "").strip()
            if not internal_net:
                continue
            pin_idx = int(port.pin_index)
            if pin_idx < 0 or pin_idx >= len(external_pin_nodes):
                # Port not connected externally — synthesize an isolated
                # external net so the internal components keep a valid
                # netlist (matches "floating port" semantics).
                external_net = (
                    f"__sub_{instance_id[:8]}__port_{pin_idx}_open"
                )
            else:
                external_net = str(external_pin_nodes[pin_idx] or "").strip()
                if not external_net:
                    external_net = (
                        f"__sub_{instance_id[:8]}__port_{pin_idx}_open"
                    )
            port_translation[internal_net] = external_net

        # Synthesized prefix for non-port internal nets. Includes a slice
        # of the instance UUID so two instances of the same definition
        # do not collide on internal nets.
        synth_prefix = f"__sub_{instance_id[:8]}__"

        def translate_net(internal_net: str) -> str:
            net = str(internal_net or "").strip()
            if not net:
                return ""
            # Ground stays ground regardless of nesting depth.
            if net == "0":
                return "0"
            if net in port_translation:
                return port_translation[net]
            return f"{synth_prefix}{net}"

        # Recurse first: expand any SUBCIRCUIT instances inside the
        # definition. We do this by routing the internal circuit through
        # the same flattening pass on a temporary ``circuit_data`` dict.
        nested_data: dict[str, Any] = {
            "components": [],
            "node_map": {},
            "subcircuits": defs_by_id,
        }
        from pulsimgui.models.component import ComponentType as _CT
        for internal_component in internal_circuit.components.values():
            # SUBCIRCUIT_PORT markers are not devices — they're a
            # bridging hint for the outer instance. Their effect on
            # the netlist is already captured by port.internal_node
            # (which sync_definition_ports_from_markers refreshed
            # above), so we drop them from the flattened output.
            if internal_component.type == _CT.SUBCIRCUIT_PORT:
                continue
            comp_dict = internal_component.to_dict()
            comp_id = str(internal_component.id)
            pin_count = len(internal_component.pins)
            pin_nodes = [
                internal_node_map.get((comp_id, pin_idx), "") or ""
                for pin_idx in range(pin_count)
            ]
            comp_dict["pin_nodes"] = pin_nodes
            nested_data["components"].append(comp_dict)
            nested_data["node_map"][comp_id] = list(pin_nodes)

        # Recursive expansion — push this definition onto the
        # in-progress set so any descendant referencing it bombs out.
        in_progress_next = set(in_progress)
        in_progress_next.add(def_id)
        self._expand_nested_instances(
            nested_data,
            defs_by_id,
            in_progress=in_progress_next,
        )

        flattened_internals = nested_data["components"]

        # Now translate each flattened internal component's nets to the
        # parent scope (external port net OR synthesized prefixed net).
        emitted: list[dict] = []
        for internal_component in flattened_internals:
            new_component = copy.deepcopy(internal_component)
            # Fresh UUID — required because the same definition may be
            # instantiated multiple times in the parent circuit and the
            # backend identifies components by ID.
            new_component["id"] = str(uuid.uuid4())

            # Prefix the user-facing name with the parent instance name
            # so the flattened netlist is debuggable.
            internal_name = str(internal_component.get("name") or "").strip() or "C"
            new_component["name"] = f"{instance_name}__{internal_name}"

            # Translate every pin net. Skip components with no pin info.
            internal_pins = internal_component.get("pin_nodes") or []
            translated_pins = [translate_net(net) for net in internal_pins]
            new_component["pin_nodes"] = translated_pins

            emitted.append(new_component)

        return emitted

    def _expand_nested_instances(
        self,
        nested_data: dict,
        defs_by_id: dict[str, dict],
        *,
        in_progress: set[str],
    ) -> None:
        """Inner driver for recursive SUBCIRCUIT expansion.

        Mirrors the top-level ``_flatten_subcircuits`` loop but threads
        the ``in_progress`` set so cycles are detected.
        """
        components_list = nested_data["components"]
        node_map = nested_data["node_map"]

        guard = 0
        max_iterations = 1024
        while True:
            guard += 1
            if guard > max_iterations:
                raise CircuitConversionError(
                    "Nested subcircuit flattening exceeded recursion guard "
                    f"({max_iterations} iterations); aborting."
                )

            instance_indices: list[int] = []
            for index, component in enumerate(components_list):
                if not isinstance(component, dict):
                    continue
                raw_type = component.get("type")
                if isinstance(raw_type, str) and raw_type.strip().upper() == "SUBCIRCUIT":
                    instance_indices.append(index)

            if not instance_indices:
                return

            for index in reversed(instance_indices):
                instance = components_list[index]
                expanded = self._expand_single_instance(
                    instance,
                    defs_by_id,
                    node_map,
                    in_progress=in_progress,
                )
                instance_id = str(instance.get("id") or "")
                components_list.pop(index)
                if instance_id:
                    node_map.pop(instance_id, None)
                for new_component in expanded:
                    components_list.append(new_component)
                    new_comp_id = str(new_component.get("id") or "")
                    if new_comp_id and "pin_nodes" in new_component:
                        node_map[new_comp_id] = list(
                            new_component["pin_nodes"]
                        )

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

        # FOC-controller marker: a C_BLOCK carrying ``control_kind="foc"``
        # is NOT a fast_block — it is a pure descriptor the backend reads
        # from ``circuit.foc_loop_descriptors`` (see ``_infer_foc_loops``)
        # to close the motor's current/speed loops. It is never wired into
        # the power stage, so it has no builder presence: skip translation
        # entirely (otherwise the generic virtual-component path would try
        # to compile a non-existent control law / demand input channels).
        if comp_type == ComponentType.C_BLOCK and self._is_foc_marker(params):
            return

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

        if comp_type == ComponentType.DC_MOTOR:
            # Pulsim 0.10.0a2+: Circuit::add_dc_motor with full device-variant
            # integration. Pins: A+ (pin 0), A- (pin 1). The runtime reserves
            # one MNA branch row for the armature current and advances ω, θ
            # internally each timestep. Backend-version gating: if the
            # capability isn't available, raise CircuitConversionError so the
            # GUI surfaces a clear "upgrade Pulsim" message rather than a
            # cryptic AttributeError.
            n_a_plus, n_a_minus = self._require_nodes(name, nodes, 2)
            n_plus_idx = self._node_index(circuit, n_a_plus, node_cache)
            n_minus_idx = self._node_index(circuit, n_a_minus, node_cache)

            params_cls = getattr(self._sl, "DcMotorParams", None)
            add_motor = getattr(circuit, "add_dc_motor", None)
            if params_cls is None or add_motor is None:
                raise CircuitConversionError(
                    "This Pulsim runtime does not support the DC Motor device "
                    "(need pulsim>=0.10.0a2). Upgrade with `pip install -U pulsim`."
                )

            motor_params = params_cls()
            motor_params.name = name
            motor_params.R_a = self._as_float(params.get("R_a"), default=0.5)
            motor_params.L_a = self._as_float(params.get("L_a"), default=10e-3)
            motor_params.K_e = self._as_float(params.get("K_e"), default=0.05)
            motor_params.K_t = self._as_float(params.get("K_t"), default=0.05)
            motor_params.J   = self._as_float(params.get("J"),   default=1e-4)
            motor_params.b   = self._as_float(params.get("b"),   default=1e-5)
            # Quadratic load (Pulsim>=0.10.0a3) — gracefully ignored on older
            # runtimes via hasattr check, so older pulsim still loads files
            # authored against the newer GUI.
            if hasattr(motor_params, "tau_load_quad_coeff"):
                motor_params.tau_load_quad_coeff = self._as_float(
                    params.get("tau_load_quad_coeff"), default=0.0
                )
            motor_params.i_a_init   = self._as_float(params.get("i_a_init"), default=0.0)
            motor_params.omega_init = self._as_float(params.get("omega_init"), default=0.0)
            motor_params.theta_init = self._as_float(params.get("theta_init"), default=0.0)
            add_motor(name, n_plus_idx, n_minus_idx, motor_params)

            # Apply optional load torque (constant, set once at simulation start).
            tau_load = self._as_float(params.get("tau_load"), default=0.0)
            if tau_load != 0.0:
                set_tau = getattr(circuit, "set_motor_tau_load", None)
                if set_tau is not None:
                    set_tau(name, tau_load)
            return

        if comp_type == ComponentType.THREE_PHASE_RL_LOAD:
            # 4-pin (A, B, C, N). Pulsim>=0.10.0a3 decomposes into 3 R+L
            # series branches (Star or Delta).
            n_a, n_b, n_c, n_neutral = self._require_nodes(name, nodes, 4)
            n_a_idx = self._node_index(circuit, n_a, node_cache)
            n_b_idx = self._node_index(circuit, n_b, node_cache)
            n_c_idx = self._node_index(circuit, n_c, node_cache)
            n_n_idx = self._node_index(circuit, n_neutral, node_cache)

            add_load = getattr(circuit, "add_three_phase_rl_load", None)
            params_cls = getattr(self._sl, "ThreePhaseRLLoadParams", None)
            topology_enum = getattr(self._sl, "ThreePhaseLoadTopology", None)
            if add_load is None or params_cls is None or topology_enum is None:
                raise CircuitConversionError(
                    "This Pulsim runtime does not support the 3-Phase RL Load "
                    "component (need pulsim>=0.10.0a3). Upgrade with "
                    "`pip install -U pulsim`."
                )

            ld_p = params_cls()
            ld_p.resistance_per_phase = self._as_float(
                params.get("resistance_per_phase"), default=30.0
            )
            ld_p.inductance_per_phase = self._as_float(
                params.get("inductance_per_phase"), default=50e-3
            )
            topology_str = str(params.get("topology") or "Star").strip().lower()
            ld_p.topology = (
                topology_enum.Delta if topology_str.startswith("delta")
                else topology_enum.Star
            )
            ld_p.unbalance_factor = self._as_float(
                params.get("unbalance_factor"), default=0.0
            )
            add_load(name, n_a_idx, n_b_idx, n_c_idx, n_n_idx, ld_p)
            return

        if comp_type == ComponentType.PMSM_STEADY_STATE:
            # 4-pin (A, B, C, N). Pulsim>=0.10.0a3 decomposes into 3 phases
            # of R_s + L_s + sinusoidal back-EMF.
            n_a, n_b, n_c, n_neutral = self._require_nodes(name, nodes, 4)
            n_a_idx = self._node_index(circuit, n_a, node_cache)
            n_b_idx = self._node_index(circuit, n_b, node_cache)
            n_c_idx = self._node_index(circuit, n_c, node_cache)
            n_n_idx = self._node_index(circuit, n_neutral, node_cache)

            add_pmsm = getattr(circuit, "add_pmsm_steady_state", None)
            params_cls = getattr(self._sl, "PmsmSteadyStateParams", None)
            if add_pmsm is None or params_cls is None:
                raise CircuitConversionError(
                    "This Pulsim runtime does not support the PMSM "
                    "(steady-state) component (need pulsim>=0.10.0a3). "
                    "Upgrade with `pip install -U pulsim`."
                )

            pmsm_p = params_cls()
            pmsm_p.R_s = self._as_float(params.get("R_s"), default=0.5)
            pmsm_p.L_s = self._as_float(params.get("L_s"), default=2e-3)
            pmsm_p.lambda_pm = self._as_float(params.get("lambda_pm"), default=0.1)
            pmsm_p.omega_electrical = self._as_float(
                params.get("omega_electrical"), default=314.159265
            )
            pmsm_p.phase_a_offset_deg = self._as_float(
                params.get("phase_a_offset_deg"), default=0.0
            )
            pmsm_p.positive_sequence = bool(params.get("positive_sequence", True))
            add_pmsm(name, n_a_idx, n_b_idx, n_c_idx, n_n_idx, pmsm_p)
            return

        if comp_type == ComponentType.PMSM:
            # 4-pin (A, B, C, N). Pulsim>=0.10.0a4 dynamic device-variant
            # with 4 internal states (i_d, i_q, ω_m, θ_m), Park-frame torque,
            # forward-Euler mechanical step. Capability-gated against
            # older runtimes.
            n_a, n_b, n_c, n_neutral = self._require_nodes(name, nodes, 4)
            n_a_idx = self._node_index(circuit, n_a, node_cache)
            n_b_idx = self._node_index(circuit, n_b, node_cache)
            n_c_idx = self._node_index(circuit, n_c, node_cache)
            n_n_idx = self._node_index(circuit, n_neutral, node_cache)

            add_pmsm_dyn = getattr(circuit, "add_pmsm", None)
            params_cls = getattr(self._sl, "PmsmParams", None)
            if add_pmsm_dyn is None or params_cls is None:
                raise CircuitConversionError(
                    "This Pulsim runtime does not support the PMSM "
                    "(dynamic) component (need pulsim>=0.10.0a4). "
                    "Upgrade with `pip install -U pulsim`."
                )

            pmsm_p = params_cls()
            pmsm_p.name = name
            pmsm_p.Rs = self._as_float(params.get("Rs"), default=0.5)
            pmsm_p.Ld = self._as_float(params.get("Ld"), default=2e-3)
            pmsm_p.Lq = self._as_float(params.get("Lq"), default=2e-3)
            pmsm_p.psi_pm = self._as_float(params.get("psi_pm"), default=0.1)
            pmsm_p.pole_pairs = int(self._as_float(
                params.get("pole_pairs"), default=2
            ))
            pmsm_p.J = self._as_float(params.get("J"), default=1e-3)
            pmsm_p.b_friction = self._as_float(
                params.get("b_friction"), default=1e-4
            )
            pmsm_p.friction_coulomb = self._as_float(
                params.get("friction_coulomb"), default=0.0
            )
            pmsm_p.i_d_init = self._as_float(
                params.get("i_d_init"), default=0.0
            )
            pmsm_p.i_q_init = self._as_float(
                params.get("i_q_init"), default=0.0
            )
            pmsm_p.omega_init = self._as_float(
                params.get("omega_init"), default=0.0
            )
            pmsm_p.theta_init = self._as_float(
                params.get("theta_init"), default=0.0
            )
            add_pmsm_dyn(name, n_a_idx, n_b_idx, n_c_idx, n_n_idx, pmsm_p)

            # External load torque is set via a separate runtime call,
            # mirroring the DC motor flow. Only forward if the user gave
            # a non-zero value.
            tau_load = self._as_float(params.get("tau_load"), default=0.0)
            if tau_load != 0.0:
                set_tau = getattr(circuit, "set_pmsm_tau_load", None)
                if set_tau is not None:
                    set_tau(name, tau_load)
            return

        if comp_type == ComponentType.INDUCTION_MOTOR:
            # 4-pin (A, B, C, N). pulsim 1.5+ add_induction_motor —
            # adds Rs + leakage-L + back-EMF source per phase and needs
            # make_induction_motor_observer wired at simulate time. The
            # shim records the handle in ``nonlinear_observer_specs``;
            # the backend reads it to compose the observer.
            n_a, n_b, n_c, n_neutral = self._require_nodes(name, nodes, 4)
            n_a_idx = self._node_index(circuit, n_a, node_cache)
            n_b_idx = self._node_index(circuit, n_b, node_cache)
            n_c_idx = self._node_index(circuit, n_c, node_cache)
            n_n_idx = self._node_index(circuit, n_neutral, node_cache)

            add_im = getattr(circuit, "add_induction_motor", None)
            if add_im is None:
                raise CircuitConversionError(
                    "This Pulsim runtime does not support the induction "
                    "motor component (need pulsim>=1.5). Upgrade with "
                    "`pip install -U pulsim`."
                )
            im_params = {
                "R_s": self._as_float(params.get("R_s"), default=0.5),
                "L_s": self._as_float(params.get("L_s"), default=0.05),
                "R_r": self._as_float(params.get("R_r"), default=0.4),
                "L_r": self._as_float(params.get("L_r"), default=0.05),
                "L_m": self._as_float(params.get("L_m"), default=0.045),
                "pole_pairs": int(self._as_float(params.get("pole_pairs"), default=2)),
                "J": self._as_float(params.get("J"), default=1e-3),
                "B": self._as_float(params.get("B"), default=0.0),
                "T_load": self._as_float(params.get("T_load"), default=0.0),
            }
            try:
                add_im(name, n_a_idx, n_b_idx, n_c_idx, n_n_idx, im_params)
            except (ValueError, AttributeError) as exc:
                raise CircuitConversionError(
                    f"Induction motor '{name}': {exc}"
                ) from exc
            return

        if comp_type == ComponentType.HYSTERETIC_INDUCTOR:
            # 2-pin Jiles-Atherton hysteretic inductor (pulsim 1.5+).
            # add_hysteretic_inductor adds L0 + dummy V_M source;
            # make_hysteretic_inductor_observer drives V_M each step.
            n1, n2 = self._require_nodes(name, nodes, 2)
            n1_idx = self._node_index(circuit, n1, node_cache)
            n2_idx = self._node_index(circuit, n2, node_cache)

            add_hl = getattr(circuit, "add_hysteretic_inductor", None)
            if add_hl is None:
                raise CircuitConversionError(
                    "This Pulsim runtime does not support the hysteretic "
                    "inductor component (need pulsim>=1.5). Upgrade with "
                    "`pip install -U pulsim`."
                )
            hl_params = {
                "material": str(params.get("material", "si_steel_m19")),
                "N_turns": int(self._as_float(params.get("N_turns"), default=100)),
                "l_m": self._as_float(params.get("l_m"), default=0.1),
                "A_core": self._as_float(params.get("A_core"), default=1e-4),
            }
            try:
                add_hl(name, n1_idx, n2_idx, hl_params)
            except (ValueError, AttributeError) as exc:
                raise CircuitConversionError(
                    f"Hysteretic inductor '{name}': {exc}"
                ) from exc
            return

        if comp_type == ComponentType.THREE_PHASE_SOURCE:
            # Pins: A, B, C, N (4-terminal). Calls Circuit::add_three_phase_source
            # which internally decomposes into 3 SineVoltageSource branches.
            # Requires pulsim>=0.10.0a1; older runtimes degrade to 3 manual
            # sine sources so older saved projects still load.
            n_a, n_b, n_c, n_neutral = self._require_nodes(name, nodes, 4)
            n_a_idx = self._node_index(circuit, n_a, node_cache)
            n_b_idx = self._node_index(circuit, n_b, node_cache)
            n_c_idx = self._node_index(circuit, n_c, node_cache)
            n_n_idx = self._node_index(circuit, n_neutral, node_cache)

            three_phase_helper = getattr(circuit, "add_three_phase_source", None)
            params_cls = getattr(self._sl, "ThreePhaseSourceParams", None)
            if three_phase_helper is not None and params_cls is not None:
                tp_params = params_cls()
                tp_params.line_to_line_voltage_rms = self._as_float(
                    params.get("line_to_line_voltage_rms"), default=400.0
                )
                tp_params.frequency_hz = self._as_float(
                    params.get("frequency_hz"), default=50.0
                )
                tp_params.phase_a_deg = self._as_float(
                    params.get("phase_a_deg"), default=0.0
                )
                tp_params.positive_sequence = bool(
                    params.get("positive_sequence", True)
                )
                tp_params.unbalance_factor = self._as_float(
                    params.get("unbalance_factor"), default=0.0
                )
                three_phase_helper(name, n_a_idx, n_b_idx, n_c_idx, n_n_idx, tp_params)
            else:
                # Fallback for pulsim < 0.10.0a1: emit 3 manual sine sources.
                self._add_three_phase_fallback(
                    circuit, name, n_a_idx, n_b_idx, n_c_idx, n_n_idx, params
                )
            return

        if comp_type == ComponentType.THREE_PHASE_VSI:
            # 5-pin (VDC+, VDC-, A, B, C). Pulsim>=0.10.0a5 builds a
            # complete 3-leg 6-switch SPWM inverter internally. Capability-
            # gated against older runtimes that lack ``add_three_phase_vsi``.
            n_vdc_pos, n_vdc_neg, n_a, n_b, n_c = self._require_nodes(name, nodes, 5)
            n_vdc_pos_idx = self._node_index(circuit, n_vdc_pos, node_cache)
            n_vdc_neg_idx = self._node_index(circuit, n_vdc_neg, node_cache)
            n_a_idx = self._node_index(circuit, n_a, node_cache)
            n_b_idx = self._node_index(circuit, n_b, node_cache)
            n_c_idx = self._node_index(circuit, n_c, node_cache)

            add_vsi = getattr(circuit, "add_three_phase_vsi", None)
            params_cls = getattr(self._sl, "ThreePhaseVsiParams", None)
            if add_vsi is not None and params_cls is not None:
                vsi_p = params_cls()
                vsi_p.switching_frequency_hz = self._as_float(
                    params.get("switching_frequency_hz"), default=10e3
                )
                vsi_p.modulation_index = self._as_float(
                    params.get("modulation_index"), default=0.8
                )
                vsi_p.modulation_frequency_hz = self._as_float(
                    params.get("modulation_frequency_hz"), default=50.0
                )
                vsi_p.phase_a_deg = self._as_float(
                    params.get("phase_a_deg"), default=0.0
                )
                vsi_p.positive_sequence = bool(
                    params.get("positive_sequence", True)
                )
                vsi_p.v_gate_on = self._as_float(
                    params.get("v_gate_on"), default=12.0
                )
                vsi_p.v_gate_off = self._as_float(
                    params.get("v_gate_off"), default=0.0
                )
                vsi_p.mosfet_r_on_ohm = self._as_float(
                    params.get("mosfet_r_on_ohm"), default=0.01
                )
                vsi_p.mosfet_vth = self._as_float(
                    params.get("mosfet_vth"), default=1.0
                )
                # pulsim 1.6.4 native switched VSI extras. dead_time_s
                # feeds make_three_phase_spwm_fn's symmetric dead-time;
                # mosfet_r_off_ohm sizes the switch OFF resistance. Both
                # default sanely when the GUI/template omits them.
                vsi_p.dead_time_s = self._as_float(
                    params.get("dead_time_s"), default=0.0
                )
                vsi_p.mosfet_r_off_ohm = self._as_float(
                    params.get("mosfet_r_off_ohm"), default=1e9
                )
                # NATIVE switched path (pulsim 1.6.4): the shim's
                # ``add_three_phase_vsi`` builds the 6-switch topology and
                # records the SPWM drive params on ``circuit.vsi_specs``;
                # the backend assembles the real ``make_three_phase_spwm_fn``
                # switch_fn at simulate time (true per-cycle switching, not
                # an averaged fundamental). A genuinely old kernel whose
                # shim re-raises ``AttributeError`` (no ``add_three_phase_vsi``
                # free function) drops through to the averaged fallback
                # below so legacy projects still load.
                try:
                    add_vsi(name, n_vdc_pos_idx, n_vdc_neg_idx,
                            n_a_idx, n_b_idx, n_c_idx, vsi_p)
                    return
                except AttributeError:
                    pass

            # Pulsim 1.5+ retired the native VSI builder. Fall back to a
            # BEHAVIORAL averaged model: three ideal sine voltage sources
            # from each phase to ``VDC-``, at ``modulation_frequency_hz``
            # with 120° phase shifts. Amplitude = (modulation_index ×
            # V_dc_nominal) / 2 — a half-bus reference common to averaged
            # VSI models. Does NOT model switching ripple or per-cycle PWM
            # — adequate for V/f open-loop motor demos where the user
            # cares about the fundamental.
            import math
            f_mod = self._as_float(
                params.get("modulation_frequency_hz"), default=50.0
            )
            m_index = self._as_float(
                params.get("modulation_index"), default=0.8
            )
            phase_a_deg = self._as_float(
                params.get("phase_a_deg"), default=0.0
            )
            positive_seq = bool(params.get("positive_sequence", True))
            v_dc_nominal = self._as_float(
                params.get("v_dc_nominal"), default=400.0
            )
            v_phase_peak = m_index * v_dc_nominal / 2.0
            sign = 1.0 if positive_seq else -1.0
            phase_a_rad = math.radians(phase_a_deg)
            phase_b_rad = phase_a_rad - sign * (2.0 * math.pi / 3.0)
            phase_c_rad = phase_a_rad - sign * (4.0 * math.pi / 3.0)

            vdc_neg_name = circuit._name_of(n_vdc_neg_idx)
            phase_a_name = circuit._name_of(n_a_idx)
            phase_b_name = circuit._name_of(n_b_idx)
            phase_c_name = circuit._name_of(n_c_idx)

            for phase_name, node_name, phase_rad in (
                ("A", phase_a_name, phase_a_rad),
                ("B", phase_b_name, phase_b_rad),
                ("C", phase_c_name, phase_c_rad),
            ):
                circuit._builder.add_sine_voltage_source(
                    f"{name}_V{phase_name}",
                    node_name, vdc_neg_name,
                    v_dc_nominal / 2.0, v_phase_peak,
                    f_mod, phase_rad,
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

        if comp_type == ComponentType.SINGLE_PHASE_DIODE_BRIDGE:
            # Pin layout: 0=AC+, 1=AC-, 2=DC+, 3=DC-
            # Topology (Graetz): 4 diodes, current always flows DC+ → load → DC-.
            #   D1: AC+ → DC+   (anode=AC+, cathode=DC+)
            #   D2: AC- → DC+   (anode=AC-, cathode=DC+)
            #   D3: DC- → AC+   (anode=DC-, cathode=AC+)
            #   D4: DC- → AC-   (anode=DC-, cathode=AC-)
            n_acp, n_acn, n_dcp, n_dcn = self._require_nodes(name, nodes, 4)
            acp = self._node_index(circuit, n_acp, node_cache)
            acn = self._node_index(circuit, n_acn, node_cache)
            dcp = self._node_index(circuit, n_dcp, node_cache)
            dcn = self._node_index(circuit, n_dcn, node_cache)
            g_on, g_off = self._switch_conductances(params)
            for diode_name, anode, cathode in (
                (f"{name}_D1", acp, dcp),
                (f"{name}_D2", acn, dcp),
                (f"{name}_D3", dcn, acp),
                (f"{name}_D4", dcn, acn),
            ):
                try:
                    circuit.add_diode(diode_name, anode, cathode, g_on, g_off)
                except TypeError:
                    circuit.add_diode(diode_name, anode, cathode)
            return

        if comp_type == ComponentType.THREE_PHASE_DIODE_BRIDGE:
            # Pin layout: 0=A, 1=B, 2=C, 3=DC+, 4=DC-
            # Topology: 6-pulse bridge (3 upper diodes A/B/C → DC+, 3 lower
            # DC- → A/B/C). Industry-standard 6-diode rectifier.
            n_a, n_b, n_c, n_dcp, n_dcn = self._require_nodes(name, nodes, 5)
            a = self._node_index(circuit, n_a, node_cache)
            b = self._node_index(circuit, n_b, node_cache)
            c = self._node_index(circuit, n_c, node_cache)
            dcp = self._node_index(circuit, n_dcp, node_cache)
            dcn = self._node_index(circuit, n_dcn, node_cache)
            g_on, g_off = self._switch_conductances(params)
            for diode_name, anode, cathode in (
                (f"{name}_D1", a,   dcp),  # upper A
                (f"{name}_D2", b,   dcp),  # upper B
                (f"{name}_D3", c,   dcp),  # upper C
                (f"{name}_D4", dcn, a),    # lower A
                (f"{name}_D5", dcn, b),    # lower B
                (f"{name}_D6", dcn, c),    # lower C
            ):
                try:
                    circuit.add_diode(diode_name, anode, cathode, g_on, g_off)
                except TypeError:
                    circuit.add_diode(diode_name, anode, cathode)
            return

        if comp_type == ComponentType.MMC_CELL:
            # Single MMC sub-module cell. ``cell_topology`` picks between
            # half-bridge (2 switches, 4 pins) and full-bridge (4 switches,
            # 6 pins). Switch on the parameter and expand into the right
            # primitive set.
            topology = str(params.get("cell_topology") or "Half-Bridge")

            mosfet_params = self._sl.MOSFETParams()
            mosfet_params.is_nmos = True
            mosfet_params.R_on = self._as_float(params.get("r_ds_on"), default=25e-3)
            mosfet_params.R_off = 1.0 / max(
                self._as_float(params.get("g_off"), default=1e-9), 1e-30
            )
            c_cell = self._as_float(params.get("c_cell"), default=4.7e-3)
            v_cell_init = self._as_float(params.get("v_cell_init"), default=0.0)

            if topology == "Full-Bridge":
                # Pin layout: 0=TOP, 1=BOT, 2=S1_G, 3=S2_G, 4=S3_G, 5=S4_G
                # H-bridge with cap across CAP_TOP ↔ CAP_BOT internal nodes:
                #   S1: CAP_TOP → TOP   (gate=S1_G)  upper-left
                #   S2: TOP     → CAP_BOT (gate=S2_G)  lower-left
                #   S3: CAP_TOP → BOT   (gate=S3_G)  upper-right
                #   S4: BOT     → CAP_BOT (gate=S4_G)  lower-right
                n_top, n_bot, n_g1, n_g2, n_g3, n_g4 = self._require_nodes(name, nodes, 6)
                top = self._node_index(circuit, n_top, node_cache)
                bot = self._node_index(circuit, n_bot, node_cache)
                g1 = self._node_index(circuit, n_g1, node_cache)
                g2 = self._node_index(circuit, n_g2, node_cache)
                g3 = self._node_index(circuit, n_g3, node_cache)
                g4 = self._node_index(circuit, n_g4, node_cache)
                cap_top = self._node_index(circuit, f"__{name}_captop", node_cache)
                cap_bot = self._node_index(circuit, f"__{name}_capbot", node_cache)

                circuit.add_mosfet(f"{name}_S1", g1, cap_top, top, mosfet_params)
                circuit.add_mosfet(f"{name}_S2", g2, top, cap_bot, mosfet_params)
                circuit.add_mosfet(f"{name}_S3", g3, cap_top, bot, mosfet_params)
                circuit.add_mosfet(f"{name}_S4", g4, bot, cap_bot, mosfet_params)
                circuit.add_capacitor(f"{name}_C", cap_top, cap_bot, c_cell, v_cell_init)
            else:
                # Half-bridge — pin layout: 0=TOP, 1=BOT, 2=S1_G, 3=S2_G
                #   S1 (upper): CAP_TOP → TOP   (gate=S1_G)
                #   S2 (lower): TOP     → BOT   (gate=S2_G)
                #   C: CAP_TOP → BOT
                n_top, n_bot, n_g1, n_g2 = self._require_nodes(name, nodes, 4)
                top = self._node_index(circuit, n_top, node_cache)
                bot = self._node_index(circuit, n_bot, node_cache)
                g1 = self._node_index(circuit, n_g1, node_cache)
                g2 = self._node_index(circuit, n_g2, node_cache)
                cap_top = self._node_index(circuit, f"__{name}_captop", node_cache)

                circuit.add_mosfet(f"{name}_S1", g1, cap_top, top, mosfet_params)
                circuit.add_mosfet(f"{name}_S2", g2, top, bot, mosfet_params)
                circuit.add_capacitor(f"{name}_C", cap_top, bot, c_cell, v_cell_init)
            return

        if comp_type == ComponentType.MMC_ARM:
            # Pin layout: 0=TOP, 1=BOT, 2=M_REF (signal — ignored in
            # this initial mapping; pulsim's add_mmc_arm_* takes m_ref
            # as a float constant unless wired to a callable).
            n_top, n_bot, _n_mref = self._require_nodes(name, nodes, 3)
            top = self._node_index(circuit, n_top, node_cache)
            bot = self._node_index(circuit, n_bot, node_cache)
            top_name = circuit._name_of(top)
            bot_name = circuit._name_of(bot)

            fidelity = str(params.get("model_fidelity") or "L3 Detailed")
            level = fidelity.split(" ", 1)[0].upper()  # "L0".."L3"

            # Resolve pulsim.mmc module on the backend (pulsim 1.5+
            # exposes it as ``pulsim.mmc``). Older runtimes that lack
            # it raise a clear error instead of failing silently.
            ps_module = getattr(self._sl, "_wrapped", None) or self._sl
            mmc_mod = getattr(ps_module, "mmc", None)
            if mmc_mod is None:
                raise CircuitConversionError(
                    f"MMC_ARM component '{name}' requires pulsim>=1.5 "
                    "with the ``pulsim.mmc`` module. Upgrade pulsim."
                )

            n_sm = max(1, int(self._as_float(
                params.get("n_submodules"), default=4)))
            c_sm = self._as_float(params.get("c_sm"), default=4.7e-3)
            v_c0 = self._as_float(params.get("v_c0"), default=0.0)
            r_arm = self._as_float(params.get("r_arm"), default=0.01)
            f_carrier = self._as_float(params.get("f_carrier"), default=1e3)
            m_ref_const = self._as_float(
                params.get("m_ref_constant"), default=0.5)

            # Submodule type — pulsim.mmc.SubmoduleType is Literal
            # ['half_bridge', 'full_bridge'] (a typing.Literal type,
            # not an enum). Map the GUI label to the literal string.
            sm_type_str = str(params.get("submodule_type") or "Half-Bridge")
            sm_type_value = ("full_bridge" if "Full" in sm_type_str
                              else "half_bridge")

            # Modulation scheme — Literal ['ps_pwm', 'ipd']. Map the
            # GUI's PSC/PD/POD/APOD labels to pulsim's 2 supported
            # variants: PSC → ps_pwm (phase-shifted PWM), anything
            # else falls back to 'ipd' (in-phase disposition).
            mod_scheme_str = str(params.get("modulation_scheme") or "PSC")
            mod_scheme_value = (
                "ps_pwm" if mod_scheme_str.upper().startswith("PS")
                else "ipd"
            )

            # Pick the helper + params class per fidelity level
            level_table = {
                "L0": ("add_mmc_arm_average",    "MmcArmAverageParams"),
                "L1": ("add_mmc_arm_multilevel", "MmcArmMultilevelParams"),
                "L2": ("add_mmc_arm_equivalent", "MmcArmEquivalentParams"),
                "L3": ("add_mmc_arm_detailed",   "MmcArmDetailedParams"),
            }
            if level not in level_table:
                raise CircuitConversionError(
                    f"MMC_ARM '{name}': unknown model_fidelity={fidelity!r}; "
                    f"expected one of {list(level_table.keys())}."
                )
            helper_name, params_cls_name = level_table[level]
            helper = getattr(mmc_mod, helper_name, None)
            params_cls = getattr(mmc_mod, params_cls_name, None)
            if helper is None or params_cls is None:
                raise CircuitConversionError(
                    f"MMC_ARM '{name}': pulsim.mmc lacks {helper_name} / "
                    f"{params_cls_name}. Upgrade pulsim."
                )

            # Build the params instance. n_sm + c_sm are required;
            # everything else is optional with sensible defaults.
            mmc_kwargs: dict[str, Any] = {
                "n_sm": n_sm,
                "c_sm": c_sm,
                "sm_type": sm_type_value,
                "v_c0": v_c0,
                "r_p": r_arm,
            }
            # L1/L2/L3 take a carrier frequency and modulation scheme
            if level in {"L1", "L2", "L3"}:
                mmc_kwargs["f_carrier"] = f_carrier
                mmc_kwargs["modulation_scheme"] = mod_scheme_value
            # L2 also takes dead-time + minimum-on-time
            if level == "L2":
                mmc_kwargs["t_dead"] = self._as_float(
                    params.get("t_dead"), default=1.0e-6)
                mmc_kwargs["t_min"] = self._as_float(
                    params.get("t_min"), default=1.0e-7)
            # L3 takes a balancing strategy (Literal, not bool)
            if level == "L3":
                balancing_val = params.get("balancing", True)
                # GUI used to expose a bool; pulsim wants a literal.
                if isinstance(balancing_val, bool):
                    mmc_kwargs["balancing"] = (
                        "sort_and_select" if balancing_val else "none"
                    )
                else:
                    mmc_kwargs["balancing"] = str(balancing_val)

            mmc_p = params_cls(**mmc_kwargs)

            # Call the helper. Modulation reference is a constant
            # for now — callable references (signal-driven
            # modulation) need backend observer wiring, which is a
            # separate task. The kwarg name differs between L0
            # (``m_b``, branch modulation) and L1/L2/L3 (``m_ref``).
            mod_kw = {"m_b" if level == "L0" else "m_ref": m_ref_const}
            helper(
                circuit._builder,
                name=name,
                node_a=top_name,
                node_b=bot_name,
                params=mmc_p,
                **mod_kw,
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

    def _add_three_phase_fallback(
        self,
        circuit: Any,
        name: str,
        n_a: int,
        n_b: int,
        n_c: int,
        n_neutral: int,
        params: dict[str, Any],
    ) -> None:
        """Manual decomposition for runtimes older than pulsim 0.10.0a1.

        Mirrors the helper that lives in ``runtime_circuit.hpp`` so saved
        projects authored against newer Pulsim still load on older
        runtimes — they just won't see the optimized helper path.
        """
        import math

        v_ll_rms = self._as_float(params.get("line_to_line_voltage_rms"), default=400.0)
        frequency = self._as_float(params.get("frequency_hz"), default=50.0)
        phase_a_deg = self._as_float(params.get("phase_a_deg"), default=0.0)
        positive_sequence = bool(params.get("positive_sequence", True))
        unbalance = self._as_float(params.get("unbalance_factor"), default=0.0)

        # V_ph_peak = V_LL_RMS * sqrt(2) / sqrt(3)
        v_peak = v_ll_rms * math.sqrt(2.0) / math.sqrt(3.0)
        phase_a_rad = math.radians(phase_a_deg)
        two_pi_third = 2.0 * math.pi / 3.0
        shift_b = -two_pi_third if positive_sequence else two_pi_third
        shift_c = -2.0 * two_pi_third if positive_sequence else 2.0 * two_pi_third

        sine_params_cls = getattr(self._sl, "SineParams", None)
        if sine_params_cls is None:
            raise CircuitConversionError(
                "Backend does not expose SineParams; install pulsim>=0.7.0."
            )

        def _emit_leg(suffix: str, node: int, amplitude: float, phase_rad: float) -> None:
            leg = sine_params_cls()
            leg.amplitude = amplitude
            leg.frequency = frequency
            leg.offset = 0.0
            leg.phase = phase_rad
            circuit.add_sine_voltage_source(f"{name}__{suffix}", node, n_neutral, leg)

        _emit_leg("A", n_a, v_peak, phase_a_rad)
        _emit_leg("B", n_b, v_peak * (1.0 - unbalance), phase_a_rad + shift_b)
        _emit_leg("C", n_c, v_peak * (1.0 + unbalance), phase_a_rad + shift_c)

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
        list[dict[str, Any]],
    ]:
        """Infer canonical PI/PWM control overrides for buck-style closed loops.

        This keeps GUI templates compatible with backend-native control:
        - PI nodes => [vref, vout, 0]
        - PWM nodes => [0]
        - PWM metadata => duty_from_channel + target_component
        - C_BLOCK/PID duty wiring to PWM DUTY_IN => duty_from_channel

        Returns
        -------
        tuple
            The legacy six overrides plus a seventh ``closed_loop_descriptors``
            list — one structured dict per detected ``PI_CONTROLLER →
            PWM_GENERATOR → MOSFET`` chain. The backend uses these to
            wire ``pulsim.bind_pi_to_switch`` since pulsim ≥ 1.4 retired
            the in-kernel ``pi_controller`` / ``pwm_generator`` virtual
            blocks the converter still emits for legacy reasons.

            Each descriptor carries everything ``bind_pi_to_switch``
            needs: PI gains + clamps, setpoint value, the kernel-known
            node name to read feedback from, the MOSFET device name, and
            the PWM carrier frequency.
        """
        try:
            supports_virtual = hasattr(self._sl.Circuit(), "add_virtual_component")
        except Exception:
            supports_virtual = False
        if not supports_virtual:
            return {}, {}, {}, {}, [], set(), []

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

        # Voltage-probe outputs: maps "signal node" → (positive node,
        # negative node). The backend computes V = state[pos] - state[neg].
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

        # Current-probe outputs: maps "signal node" → (in_node, out_node,
        # bypass_resistance). The probe is implemented as a tiny series
        # resistor; the backend computes I = (V_in - V_out) / R_bypass.
        # This enables cascaded controllers where the inner loop is
        # current-mode (PI sees inductor current via a CURRENT_PROBE).
        current_probe_outputs: dict[str, tuple[str, str, float]] = {}
        for component in by_type.get(ComponentType.CURRENT_PROBE, []):
            nodes = _raw_nodes(component)
            if len(nodes) < 3:
                continue
            sig_node = nodes[2]
            if not sig_node:
                continue
            params = component.get("parameters") if isinstance(
                component.get("parameters"), dict
            ) else {}
            try:
                bypass_r = float(
                    params.get("series_resistance",
                                self._CURRENT_PROBE_BYPASS_RESISTANCE_OHMS)
                )
            except (TypeError, ValueError):
                bypass_r = self._CURRENT_PROBE_BYPASS_RESISTANCE_OHMS
            if bypass_r <= 0.0:
                bypass_r = self._CURRENT_PROBE_BYPASS_RESISTANCE_OHMS
            current_probe_outputs[sig_node] = (nodes[0], nodes[1], bypass_r)

        # PI-output map: maps each PI's OUT node → the PI component dict.
        # Used by cascaded detection — the inner loop's SUBTRACTOR
        # setpoint pin reads from an OUTER PI's OUT node rather than
        # from a CONSTANT.
        pi_output_to_component: dict[str, dict[str, Any]] = {}
        for pi_comp in by_type.get(ComponentType.PI_CONTROLLER, []):
            pi_nodes_local = _raw_nodes(pi_comp)
            if len(pi_nodes_local) >= 2 and pi_nodes_local[1]:
                pi_output_to_component[pi_nodes_local[1]] = pi_comp

        pi_node_overrides: dict[str, list[str]] = {}
        pwm_node_overrides: dict[str, list[str]] = {}
        pwm_param_overrides: dict[str, dict[str, Any]] = {}
        controlled_target_node_overrides: dict[str, list[str]] = {}
        synthetic_sources: list[dict[str, Any]] = []
        suppressed_component_ids: set[str] = set()
        closed_loop_descriptors: list[dict[str, Any]] = []

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

            # Inner-loop SUB inputs can be:
            #   - feedback: VOLTAGE_PROBE (voltage mode) or CURRENT_PROBE
            #     (current mode, for cascaded inner loop)
            #   - setpoint: CONSTANT (single-loop) or another PI's OUT
            #     (cascaded — outer voltage loop feeds inner current ref)
            feedback_pair: tuple[str, str] | None = None
            current_feedback: tuple[str, str, float] | None = None
            setpoint_constant: float | None = None
            setpoint_constant_id: str | None = None
            outer_pi_component: dict[str, Any] | None = None
            for node in sub_nodes[:2]:
                if node in probe_outputs and feedback_pair is None \
                        and current_feedback is None:
                    feedback_pair = probe_outputs[node]
                    continue
                if node in current_probe_outputs and current_feedback is None \
                        and feedback_pair is None:
                    current_feedback = current_probe_outputs[node]
                    continue
                if node in constant_outputs and setpoint_constant is None \
                        and outer_pi_component is None:
                    setpoint_constant, setpoint_constant_id = constant_outputs[node]
                    continue
                # Cascaded: setpoint comes from another PI's OUT
                if node in pi_output_to_component and outer_pi_component is None \
                        and setpoint_constant is None:
                    candidate_outer = pi_output_to_component[node]
                    # Don't treat the inner PI itself as its own outer
                    if str(candidate_outer.get("id") or "") != pi_id:
                        outer_pi_component = candidate_outer

            # Need at least one feedback source AND one setpoint source
            has_feedback = feedback_pair is not None or current_feedback is not None
            has_setpoint = setpoint_constant is not None or outer_pi_component is not None
            if not has_feedback or not has_setpoint:
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

            # Resolve setpoint info. For single-loop we tie it to a
            # specific CONSTANT voltage source node; for cascaded the
            # inner setpoint is dynamic (driven by outer PI output),
            # so we just synthesize a placeholder.
            if setpoint_constant is not None:
                setpoint_raw_node = self._find_reference_voltage_node(
                    components, node_map, setpoint_constant,
                )
                if setpoint_raw_node:
                    setpoint_node = self._node_label(setpoint_raw_node, alias_map)
                else:
                    setpoint_node = f"{pi_name}_REF".replace(" ", "_")
                    synthetic_sources.append({
                        "name": setpoint_node,
                        "node": setpoint_node,
                        "value": float(setpoint_constant),
                    })
            else:
                # Cascaded inner: setpoint comes from outer PI at sim time.
                setpoint_node = f"{pi_name}_INNER_REF".replace(" ", "_")

            # Resolve feedback nodes (voltage or current). The legacy
            # virtual-block path only uses voltage feedback so we wire
            # ``feedback_plus``/``feedback_minus`` from EITHER source —
            # for current mode we use the probe's IN/OUT pair (the
            # backend then computes I = (V_in - V_out) / R_bypass).
            if current_feedback is not None:
                feedback_plus = self._node_label(current_feedback[0], alias_map)
                feedback_minus = self._node_label(current_feedback[1], alias_map)
            else:
                assert feedback_pair is not None
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

            # Structured descriptor — handed to the backend so it can
            # call ``pulsim.bind_pi_to_switch`` at simulate time. The
            # legacy ``pwm_param_overrides`` above still go in because
            # other code paths depend on them, but the backend now
            # prefers this descriptor for actually driving the loop.
            pi_params = pi_component.get("parameters") if isinstance(
                pi_component.get("parameters"), dict
            ) else {}
            pwm_params = pwm_component.get("parameters") if isinstance(
                pwm_component.get("parameters"), dict
            ) else {}

            def _float(d: dict[str, Any], key: str, default: float) -> float:
                # Tolerate either case — canonical is lowercase
                # (matches DEFAULT_PARAMETERS / the properties panel),
                # but older project files and some hand-edited examples
                # used CamelCase. Try lowercase first, then capitalized.
                for candidate in (key, key.capitalize(), key.lower()):
                    val = d.get(candidate)
                    if val is None:
                        continue
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        continue
                return default

            descriptor: dict[str, Any] = {
                "pi_name": pi_name,
                "pwm_name": self._component_name(
                    pwm_component, ComponentType.PWM_GENERATOR,
                ),
                "switch_device": target_name,
                "kp": _float(pi_params, "kp", 0.1),
                "ki": _float(pi_params, "ki", 100.0),
                "output_min": _float(pi_params, "output_min", 0.0),
                "output_max": _float(pi_params, "output_max", 1.0),
                "pwm_frequency": _float(pwm_params, "frequency", 100_000.0),
                # Kernel-known feedback node name (alias if available,
                # else the ``N{node_id}`` fallback). The backend uses
                # this with ``builder.node_id_of(...)`` to build the
                # ``measured`` callable.
                "feedback_node": feedback_plus,
                # Setpoint side. For single-loop the backend uses
                # ``setpoint_value``; for cascaded it consults
                # ``outer_pi`` and ignores ``setpoint_value``.
                "setpoint_value": (
                    float(setpoint_constant)
                    if setpoint_constant is not None else 0.0
                ),
            }

            # Current-mode inner feedback (cascaded current loop): the
            # backend reads I = (V(in) - V(out)) / R_bypass instead of
            # a single node voltage.
            if current_feedback is not None:
                descriptor["feedback_kind"] = "current"
                descriptor["feedback_node_in"] = self._node_label(
                    current_feedback[0], alias_map,
                )
                descriptor["feedback_node_out"] = self._node_label(
                    current_feedback[1], alias_map,
                )
                descriptor["feedback_bypass_r"] = float(current_feedback[2])
            else:
                descriptor["feedback_kind"] = "voltage"

            # Cascaded: emit a nested ``outer_pi`` block when the inner
            # SUB's setpoint pin reads from another PI's OUT.
            if outer_pi_component is not None:
                outer_id = str(outer_pi_component.get("id") or "").strip()
                outer_name = self._component_name(
                    outer_pi_component, ComponentType.PI_CONTROLLER,
                )
                outer_nodes_loc = _raw_nodes(outer_pi_component)
                outer_input_node = outer_nodes_loc[0] if outer_nodes_loc else ""

                # Find the outer SUBTRACTOR (its OUT feeds outer PI.IN)
                outer_sub: dict[str, Any] | None = None
                for cand in by_type.get(ComponentType.SUBTRACTOR, []):
                    cand_nodes = _raw_nodes(cand)
                    if (len(cand_nodes) >= 3
                            and cand_nodes[2] == outer_input_node
                            and str(cand.get("id") or "") != subtractor_id):
                        outer_sub = cand
                        break

                if outer_sub is not None:
                    outer_sub_nodes = _raw_nodes(outer_sub)
                    outer_feedback_pair: tuple[str, str] | None = None
                    outer_setpoint_val: float | None = None
                    outer_setpoint_const_id: str | None = None
                    for node in outer_sub_nodes[:2]:
                        if node in probe_outputs and outer_feedback_pair is None:
                            outer_feedback_pair = probe_outputs[node]
                            continue
                        if node in constant_outputs and outer_setpoint_val is None:
                            outer_setpoint_val, outer_setpoint_const_id = constant_outputs[node]

                    if outer_feedback_pair is not None and outer_setpoint_val is not None:
                        outer_params = outer_pi_component.get("parameters")
                        outer_params = outer_params if isinstance(outer_params, dict) else {}
                        descriptor["outer_pi"] = {
                            "pi_name": outer_name,
                            "kp": _float(outer_params, "kp", 0.1),
                            "ki": _float(outer_params, "ki", 100.0),
                            "output_min": _float(outer_params, "output_min", 0.0),
                            "output_max": _float(outer_params, "output_max", 1.0),
                            "setpoint_value": float(outer_setpoint_val),
                            "feedback_node": self._node_label(
                                outer_feedback_pair[0], alias_map,
                            ),
                            "feedback_node_neg": self._node_label(
                                outer_feedback_pair[1], alias_map,
                            ),
                            # Outer-loop sample period — the backend
                            # uses this to throttle outer PI updates
                            # to a slower rate than the inner PWM
                            # tick (typical: 1 ms vs 20 µs).
                            "sample_time": _float(outer_params, "sample_time", 1.0e-3),
                        }
                        # Suppress the outer sub + outer setpoint constant
                        # so they don't get emitted as virtual blocks too.
                        outer_sub_id = str(outer_sub.get("id") or "")
                        if outer_sub_id:
                            suppressed_component_ids.add(outer_sub_id)
                        if outer_setpoint_const_id:
                            suppressed_component_ids.add(outer_setpoint_const_id)
                        if outer_id:
                            suppressed_component_ids.add(outer_id)

            closed_loop_descriptors.append(descriptor)

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
            duty_input_enabled = bool(params.get(DUTY_INPUT_PARAMETER, False))

            if len(pwm_nodes) < 2:
                if duty_input_enabled:
                    pwm_name = str(pwm_component.get("name") or pwm_id)
                    raise CircuitConversionError(
                        f"PWM '{pwm_name}': porta DUTY_IN está habilitada mas não está conectada a nenhum sinal de controle."
                    )
                continue
            duty_input_node = str(pwm_nodes[1] or "").strip()
            if not duty_input_node:
                if duty_input_enabled:
                    pwm_name = str(pwm_component.get("name") or pwm_id)
                    raise CircuitConversionError(
                        f"PWM '{pwm_name}': porta DUTY_IN está habilitada mas não está conectada a nenhum sinal de controle."
                    )
                continue

            driver_name = signal_driver_by_node.get(duty_input_node)
            if not driver_name:
                if duty_input_enabled:
                    pwm_name = str(pwm_component.get("name") or pwm_id)
                    raise CircuitConversionError(
                        f"PWM '{pwm_name}': porta DUTY_IN está habilitada mas nenhum bloco de controle reconhecido está conectado a ela."
                    )
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
            closed_loop_descriptors,
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

        def _router_label(component: dict[str, Any]) -> str:
            params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            label = str(params.get("net_label", "") or "").strip()
            if label:
                return label
            return str(component.get("name") or "").strip()

        signal_driver_by_node: dict[str, str] = {}
        goto_nodes_by_label: dict[str, list[str]] = {}
        from_nodes_by_label: dict[str, list[str]] = {}

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

            if comp_type in {ComponentType.GOTO_LABEL, ComponentType.FROM_LABEL}:
                label = _router_label(component)
                pin_node = str(pin_nodes[0] or "").strip() if pin_nodes else ""
                if label and pin_node and pin_node != "0":
                    buckets = (
                        goto_nodes_by_label
                        if comp_type == ComponentType.GOTO_LABEL
                        else from_nodes_by_label
                    )
                    nodes = buckets.setdefault(label, [])
                    if pin_node not in nodes:
                        nodes.append(pin_node)
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

        # Flatten Goto/From routers into direct node->channel bindings for control mapping.
        for label, routed_from_nodes in from_nodes_by_label.items():
            source_nodes = goto_nodes_by_label.get(label, [])
            if not source_nodes or not routed_from_nodes:
                continue

            channel_name = ""
            for source_node in source_nodes:
                candidate = str(signal_driver_by_node.get(source_node, "") or "").strip()
                if candidate:
                    channel_name = candidate
                    break
            if not channel_name:
                continue

            for routed_node in routed_from_nodes:
                signal_driver_by_node.setdefault(routed_node, channel_name)

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

            # FOC-controller markers are descriptor-only (read by the
            # backend's FOC loop), not real C_BLOCK control laws — they
            # need no input-channel mapping, so skip validation for them.
            marker_params = component.get("parameters")
            if self._is_foc_marker(marker_params):
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

    def _infer_cblock_control_loops(
        self,
        components: list[dict[str, Any]],
        node_map: dict[str, list[str]],
        alias_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Detect ``python_numba`` C_BLOCKs that regulate a PWM-driven
        switch, and emit one ``cblock_loop_descriptor`` each.

        Topology matched (the SISO controller case):

            <feedback node> ──(probe)──▶ C_BLOCK.in0
            C_BLOCK.out0 ───────────────▶ PWM.duty_in ──▶ switch

        For each python_numba C_BLOCK we resolve:
          * the PWM whose duty-input node equals the C_BLOCK's first
            output node (same wiring rule the PI detector uses), then
            that PWM's target switch via
            :meth:`_infer_pwm_target_component_name`;
          * the feedback electrical node from the C_BLOCK's first
            input — through a voltage probe when one drives that input,
            else the input node directly.

        Standalone + defensive: this pass does NOT share state with
        ``_infer_native_buck_control_overrides`` (the PI detector), so
        it cannot perturb existing closed-loop detection. A C_BLOCK
        that doesn't match the topology is simply skipped.

        Returns the descriptor list (empty when no fast_block
        controller is present). The backend
        (``_build_cblock_closed_loops``) compiles + runs each.
        """
        def _raw_nodes(component: dict[str, Any]) -> list[str]:
            comp_id = str(component.get("id") or "")
            pin_nodes = component.get("pin_nodes")
            if isinstance(pin_nodes, list) and pin_nodes:
                return [str(node or "").strip() for node in pin_nodes]
            return [str(node or "").strip() for node in node_map.get(comp_id, [])]

        # Group by type (only the few we care about).
        by_type: dict[ComponentType, list[dict[str, Any]]] = {}
        for component in components:
            try:
                ct = self._component_type(component.get("type"))
            except CircuitConversionError:
                continue
            by_type.setdefault(ct, []).append(component)

        cblocks = by_type.get(ComponentType.C_BLOCK, [])
        if not cblocks:
            return []

        pwms = by_type.get(ComponentType.PWM_GENERATOR, [])

        # signal node → measured electrical node (positive side). Same
        # construction as the PI detector's ``probe_outputs``.
        probe_outputs: dict[str, str] = {}
        for probe in by_type.get(ComponentType.VOLTAGE_PROBE, []):
            nodes = _raw_nodes(probe)
            if len(nodes) >= 3 and nodes[2]:
                probe_outputs[nodes[2]] = nodes[0]
        for probe in by_type.get(ComponentType.VOLTAGE_PROBE_GND, []):
            nodes = _raw_nodes(probe)
            if len(nodes) >= 2 and nodes[1]:
                probe_outputs[nodes[1]] = nodes[0]

        def _float(d: dict[str, Any], key: str, default: float) -> float:
            for candidate in (key, key.capitalize(), key.lower()):
                val = d.get(candidate)
                if val is None:
                    continue
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
            return default

        descriptors: list[dict[str, Any]] = []
        for cblock in cblocks:
            params = cblock.get("parameters") if isinstance(
                cblock.get("parameters"), dict
            ) else {}
            impl = str(params.get("implementation", "") or "").strip().lower()
            if impl not in {"python_numba", "python", "fast_block"}:
                continue
            source = str(params.get("python_source", "") or "").strip()
            if not source:
                continue

            try:
                n_inputs = max(1, int(params.get("n_inputs", 1) or 1))
            except (TypeError, ValueError):
                n_inputs = 1
            nodes = _raw_nodes(cblock)
            # Need at least one input pin + the first output pin.
            if len(nodes) <= n_inputs:
                continue
            input_node = nodes[0]
            output_node = nodes[n_inputs]
            if not output_node:
                continue

            # Find the PWM whose duty-input node == the C_BLOCK output.
            pwm_component: dict[str, Any] | None = None
            for candidate in pwms:
                cn = _raw_nodes(candidate)
                if len(cn) >= 2 and cn[1] == output_node:
                    pwm_component = candidate
                    break
            if pwm_component is None:
                continue

            pwm_nodes = _raw_nodes(pwm_component)
            pwm_out_node = pwm_nodes[0] if pwm_nodes else ""
            switch_name = self._infer_pwm_target_component_name(
                components, node_map, pwm_out_node,
            )
            if not switch_name:
                continue

            # Feedback electrical node: via a probe driving the C_BLOCK
            # input, else the input node directly.
            measured_raw = probe_outputs.get(input_node, input_node)
            feedback_node = self._node_label(measured_raw, alias_map)

            pwm_params = pwm_component.get("parameters") if isinstance(
                pwm_component.get("parameters"), dict
            ) else {}
            try:
                n_states = max(0, int(params.get("n_states", 1) or 1))
            except (TypeError, ValueError):
                n_states = 1

            descriptors.append({
                "cblock_name": self._component_name(cblock, ComponentType.C_BLOCK),
                "source": source,
                "n_states": n_states,
                "feedback_node": feedback_node,
                "switch_device": switch_name,
                "pwm_frequency": _float(pwm_params, "frequency", 100_000.0),
                "sample_time": _float(params, "sample_time", 0.0),
                "setpoint_value": _float(params, "setpoint", 0.0),
                "output_min": _float(params, "output_min", 0.0),
                "output_max": _float(params, "output_max", 1.0),
            })

        return descriptors

    @staticmethod
    def _is_foc_marker(params: Any) -> bool:
        """True when a C_BLOCK's parameters mark it as a FOC controller
        (``control_kind="foc"``). Such a C_BLOCK is a descriptor-only
        marker — not a fast_block — and is exempt from C_BLOCK
        translation + input-channel validation."""
        if not isinstance(params, dict):
            return False
        return str(params.get("control_kind", "") or "").strip().lower() == "foc"

    def _infer_foc_loops(
        self,
        components: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Detect a Field-Oriented-Control marker and emit one
        ``foc_loop_descriptor`` binding it to a native 3φ VSI + a dynamic
        PMSM.

        The FOC controller is represented (option-b, lowest friction) as a
        ``C_BLOCK`` whose ``parameters`` carry ``control_kind="foc"`` plus
        the loop gains / speed-reference ramp / limits. The C_BLOCK is a
        pure *marker* — it is NOT electrically wired into the power stage,
        so it never perturbs the MNA. Open-loop V/f makes a PMSM pole-slip;
        closing i_d/i_q + speed PI loops (this descriptor, executed by the
        backend's ``_build_foc_loops``) is what lets the motor track a
        speed reference with rated current.

        Matched topology (by presence, not wiring):

            C_BLOCK[control_kind="foc"]  +  THREE_PHASE_VSI  +  PMSM

        The descriptor carries the controlled VSI name (the FOC drives its
        six switches via inverse Park/Clarke, *replacing* the VSI's open-
        loop SPWM) and the PMSM name (the FOC reads its observer bundle's
        live d-q currents + rotor angle). Gains / ramp / limits default to
        the validated VLT403U recipe when the marker omits them.

        Standalone + defensive: returns ``[]`` unless a FOC marker is
        present, so the open-loop VSI, averaged-VSI fallback, and cblock
        paths are untouched.
        """
        by_type: dict[ComponentType, list[dict[str, Any]]] = {}
        for component in components:
            try:
                ct = self._component_type(component.get("type"))
            except CircuitConversionError:
                continue
            by_type.setdefault(ct, []).append(component)

        cblocks = by_type.get(ComponentType.C_BLOCK, [])
        vsis = by_type.get(ComponentType.THREE_PHASE_VSI, [])
        pmsms = by_type.get(ComponentType.PMSM, [])

        # FOC needs a switched VSI to command and a dynamic PMSM to
        # observe. No marker / no VSI / no PMSM ⇒ nothing to do.
        if not cblocks or not vsis or not pmsms:
            return []

        def _float(d: dict[str, Any], key: str, default: float) -> float:
            val = d.get(key)
            if val is None:
                return default
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        descriptors: list[dict[str, Any]] = []
        for cblock in cblocks:
            params = cblock.get("parameters") if isinstance(
                cblock.get("parameters"), dict
            ) else {}
            kind = str(params.get("control_kind", "") or "").strip().lower()
            if kind != "foc":
                continue

            # Bind to a named VSI / PMSM if the marker calls one out;
            # otherwise default to the first of each (the common single-
            # drive case). The backend resolves names → specs.
            vsi_name = str(params.get("vsi_name", "") or "").strip()
            if not vsi_name:
                vsi_name = self._component_name(
                    vsis[0], ComponentType.THREE_PHASE_VSI
                )
            pmsm_name = str(params.get("pmsm_name", "") or "").strip()
            if not pmsm_name:
                pmsm_name = self._component_name(
                    pmsms[0], ComponentType.PMSM
                )

            descriptors.append({
                "name": self._component_name(cblock, ComponentType.C_BLOCK),
                "vsi_name": vsi_name,
                "pmsm_name": pmsm_name,
                # DC-bus magnitude the backend uses to normalise the
                # modulation + clamp v_d/v_q (Vbus/2). The kernel can't
                # infer the live, rippling bus, so the marker carries the
                # NOMINAL bus of its front-end (e.g. ~360 V doubler,
                # ~400 V PFC). Defaults to the VLT403U 360 V reference.
                "v_bus": _float(params, "v_bus", 360.0),
                # --- speed (outer) PI -> iq_ref ---
                "speed_kp": _float(params, "speed_kp", 0.17),
                "speed_ki": _float(params, "speed_ki", 6.0),
                # --- current (inner) PIs (shared id/iq gains) ---
                "current_kp": _float(params, "current_kp", 45.0),
                "current_ki": _float(params, "current_ki", 24000.0),
                # --- references / limits ---
                "id_ref": _float(params, "id_ref", 0.0),
                "iq_limit": _float(params, "iq_limit", 3.0),
                # voltage clamp as a fraction of the half-bus (Vbus/2).
                "v_limit_frac": _float(params, "v_limit_frac", 0.92),
                # Speed-reference ramp: 0 → ``speed_ref_rpm`` linearly over
                # ``speed_ramp_s`` (mechanical rpm), then hold.
                "speed_ref_rpm": _float(params, "speed_ref_rpm", 1800.0),
                "speed_ramp_s": _float(params, "speed_ramp_s", 0.10),
                # Carrier (switching) frequency for the inverse-Park PWM.
                "switching_frequency_hz": _float(
                    params, "switching_frequency_hz", 20000.0
                ),
            })

        return descriptors

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

        if comp_type == ComponentType.SATURABLE_INDUCTOR:
            if "i_equiv_init" in normalized and "magnetic_i_equiv_init" not in normalized:
                normalized["magnetic_i_equiv_init"] = normalized.pop("i_equiv_init")

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
