"""Helpers for resolving scope channel bindings."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import (
    CONNECTION_DOMAIN_SIGNAL,
    CONNECTION_DOMAIN_THERMAL,
    MOTOR_SIGNAL_BUS_CHANNELS,
    THERMAL_PORT_PIN_NAME,
    Component,
    ComponentType,
    is_motor_signal_bus_pin,
    pin_connection_domain,
)
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map
from pulsimgui.utils.signal_utils import format_signal_key

THERMAL_SIGNAL_EXCLUDED_TYPES = {
    ComponentType.GROUND,
    ComponentType.ELECTRICAL_SCOPE,
    ComponentType.THERMAL_SCOPE,
    ComponentType.VOLTAGE_PROBE,
    ComponentType.VOLTAGE_PROBE_GND,
    ComponentType.CURRENT_PROBE,
    ComponentType.POWER_PROBE,
    ComponentType.SIGNAL_MUX,
    ComponentType.SIGNAL_DEMUX,
    ComponentType.GOTO_LABEL,
    ComponentType.FROM_LABEL,
}


@dataclass(slots=True)
class ScopeSignal:
    """Represents a single resolved scalar signal feeding a scope channel."""

    label: str
    signal_key: str | None
    node_id: str | None
    node_label: str | None

    def prepend_label(self, prefix: str) -> None:
        """Prefix the display label for mux/demux routing."""
        if not prefix:
            return
        if not self.label:
            self.label = prefix
            return
        if self.label.startswith(prefix):
            return
        self.label = f"{prefix}/{self.label}"


@dataclass(slots=True)
class ScopeChannelBinding:
    """Resolved information for a single scope input channel."""

    index: int
    pin_index: int
    channel_label: str
    overlay: bool
    node_id: str | None
    node_label: str | None
    signals: list[ScopeSignal] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Human-readable label (channel label + signal/node).

        Prefers the first resolved signal's semantic label (e.g.
        ``I_L`` for a CURRENT_PROBE, ``X1`` for a VOLTAGE_PROBE,
        ``M1 Speed`` for a motor SIG-bus channel) over the raw
        electrical-node name (``N25``). Without this, a scope wired
        to a current probe would still read ``CH2 (N25)`` even
        though the signal *was* correctly resolved to ``IP(I_L)``
        — semantically misleading and the cause of the "I don't
        know if this is the current or some node voltage" bug
        users hit on ex 20. Falls through to the channel-level
        ``node_label`` only when no signal resolved (raw node tap).
        """
        signal_label = ""
        if self.signals:
            primary = self.signals[0]
            signal_label = (primary.node_label or primary.label or "").strip()
        if signal_label:
            return f"{self.channel_label} ({signal_label})"
        if self.node_label:
            return f"{self.channel_label} ({self.node_label})"
        return self.channel_label

    @property
    def is_connected(self) -> bool:
        """Return True when the channel resolves to at least one signal."""
        return any(signal.signal_key for signal in self.signals)


def build_scope_channel_bindings(
    component: Component,
    circuit: Circuit | None,
) -> list[ScopeChannelBinding]:
    """Resolve wiring metadata for every scope channel."""

    if circuit is None:
        return []

    node_map = build_node_map(circuit)
    alias_map = build_node_alias_map(circuit, node_map)
    node_refs: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (comp_id, pin_index), node_id in node_map.items():
        if node_id is not None:
            node_refs[node_id].append((comp_id, pin_index))

    component_lookup = {str(comp.id): comp for comp in circuit.components.values()}
    channels = component.parameters.get("channels", [])
    channel_count = component.parameters.get("channel_count", len(component.pins))

    bindings: list[ScopeChannelBinding] = []
    for index in range(channel_count):
        params = channels[index] if index < len(channels) else {}
        label = params.get("label") or _default_channel_label(component.type, index)
        overlay = bool(params.get("overlay", False))
        pin_index = index if index < len(component.pins) else max(0, len(component.pins) - 1)
        node_id = node_map.get((str(component.id), pin_index))
        node_label = _derive_node_label(node_id, alias_map)

        signals = _resolve_node_signals(
            component,
            node_id,
            alias_map,
            node_refs,
            component_lookup,
            node_map,
        )

        if not signals and node_id and component.type not in (
            ComponentType.ELECTRICAL_SCOPE,
            ComponentType.THERMAL_SCOPE,
        ):
            signals = [
                _make_scope_signal(component.type, node_id, node_label, preferred_label=label)
            ]

        bindings.append(
            ScopeChannelBinding(
                index=index,
                pin_index=pin_index,
                channel_label=label,
                overlay=overlay,
                node_id=node_id,
                node_label=node_label,
                signals=signals,
            )
        )
    return bindings


def _resolve_node_signals(
    scope_component: Component,
    node_id: str | None,
    alias_map: dict[str, str],
    node_refs: dict[str, list[tuple[str, int]]],
    component_lookup: dict[str, Component],
    node_map: dict[tuple[str, int], str],
    visited_nodes: set[str] | None = None,
    ignore_components: set[str] | None = None,
) -> list[ScopeSignal]:
    if not node_id:
        return []

    if scope_component.type == ComponentType.THERMAL_SCOPE:
        return _resolve_thermal_node_signals(
            scope_component=scope_component,
            node_id=node_id,
            node_refs=node_refs,
            component_lookup=component_lookup,
        )

    visited_nodes = visited_nodes or set()
    if node_id in visited_nodes:
        return []
    visited_nodes.add(node_id)

    ignored = set(ignore_components) if ignore_components else set()

    signals: list[ScopeSignal] = []
    deferred_control_signals: list[ScopeSignal] = []
    expanded = False

    for comp_id, pin_index in node_refs.get(node_id, []):
        if comp_id in ignored:
            continue
        component = component_lookup.get(comp_id)
        if component is None:
            continue
        if comp_id == str(scope_component.id):
            continue
        if pin_index >= len(component.pins):
            continue
        pin_name = component.pins[pin_index].name.upper()

        if component.type == ComponentType.SIGNAL_MUX and pin_name.startswith("OUT"):
            expanded = True
            signals.extend(
                _expand_mux_inputs(
                    scope_component,
                    component,
                    alias_map,
                    node_refs,
                    component_lookup,
                    node_map,
                    visited_nodes,
                    ignored,
                )
            )
        elif component.type == ComponentType.SIGNAL_DEMUX and pin_name == "IN":
            expanded = True
            signals.extend(
                _expand_demux_outputs(
                    scope_component,
                    component,
                    alias_map,
                    node_refs,
                    component_lookup,
                    node_map,
                    visited_nodes,
                    ignored,
                )
            )
        elif component.type == ComponentType.SIGNAL_DEMUX and pin_name.startswith("OUT"):
            expanded = True
            signals.extend(
                _resolve_demux_output(
                    scope_component,
                    component,
                    pin_index,
                    alias_map,
                    node_refs,
                    component_lookup,
                    node_map,
                    visited_nodes,
                    ignored,
                )
            )
        elif component.type in (
            ComponentType.VOLTAGE_PROBE,
            ComponentType.VOLTAGE_PROBE_GND,
        ):
            # Same UX rule as CURRENT_PROBE: a scope channel touching
            # *any* pin of a voltage probe resolves to the canonical
            # ``VP(<probe_name>)`` signal so the user doesn't have to
            # remember which terminal is the "output" pin. Without
            # this, wiring the scope to the probe's electrical ``+`` /
            # ``IN`` side would silently fall through to a raw node-
            # voltage that scaled like the switching node — never what
            # was intended.
            expanded = True
            probe_name = component.name or "Voltage Probe"
            signals.append(
                ScopeSignal(
                    label=probe_name,
                    signal_key=format_signal_key("VP", probe_name),
                    node_id=node_id,
                    node_label=probe_name,
                )
            )
        elif component.type == ComponentType.CURRENT_PROBE:
            # A scope channel wired to ANY pin of a current probe should
            # plot the current. The MEAS pin (signal-domain output) is
            # the canonical one, but users very often wire to the
            # electrical IN/OUT side by mistake (the side that looks
            # like a regular two-port component in the schematic) — and
            # in that case the scope would otherwise resolve to a node-
            # voltage on the switching net, which is confusing and
            # almost never what the user wanted. So expand any pin
            # touching the probe to the same ``IP(<probe_name>)``
            # signal key the kernel emits for that probe.
            expanded = True
            probe_name = component.name or "Current Probe"
            signals.append(
                ScopeSignal(
                    label=probe_name,
                    signal_key=format_signal_key("IP", probe_name),
                    node_id=node_id,
                    node_label=probe_name,
                )
            )
        elif component.type == ComponentType.MMC_ARM and pin_name in ("V_C", "V_C_SPRD"):
            # MMC arm telemetry outputs: V_C (aggregate cap voltage, all levels)
            # and V_C_SPRD (L3 submodule-cap spread). Keys match the backend's
            # ``<arm>.v_C`` / ``<arm>.v_C_spread`` observer signals.
            expanded = True
            arm_name = component.name or "ARM"
            suffix = "v_C" if pin_name == "V_C" else "v_C_spread"
            signals.append(
                ScopeSignal(
                    label=f"{arm_name} {suffix}",
                    signal_key=f"{arm_name}.{suffix}",
                    node_id=node_id,
                    node_label=arm_name,
                )
            )
        elif is_motor_signal_bus_pin(component, pin_index):
            # Dynamic-machine signal bus (PMSM ``SIG``): expand to the ordered
            # list of observable channels. Wired straight to a scope channel
            # the first lane (speed) shows; via a SIGNAL_DEMUX each output
            # lane k selects channel k (i_a, i_b, …). Keys match the backend's
            # ``<motor>.<suffix>`` signals.
            expanded = True
            motor_name = component.name or "M1"
            for suffix, channel_label in MOTOR_SIGNAL_BUS_CHANNELS:
                signals.append(
                    ScopeSignal(
                        label=f"{motor_name} {channel_label}",
                        signal_key=f"{motor_name}.{suffix}",
                        node_id=node_id,
                        node_label=motor_name,
                    )
                )
        else:
            control_signal = _resolve_control_signal(component, pin_index, node_id)
            if control_signal is not None:
                expanded = True
                # DUTY_IN is a convenient alias for PWM command telemetry, but when
                # the same net also exposes an upstream control output (e.g. PI OUT)
                # showing both channels duplicates the same control signal in scope UI.
                if component.type == ComponentType.PWM_GENERATOR and pin_name == "DUTY_IN":
                    deferred_control_signals.append(control_signal)
                else:
                    signals.append(control_signal)

    if not signals and deferred_control_signals:
        signals.extend(deferred_control_signals)

    visited_nodes.discard(node_id)

    if not expanded:
        if scope_component.type == ComponentType.ELECTRICAL_SCOPE:
            return []
        node_label = _derive_node_label(node_id, alias_map)
        return [_make_scope_signal(scope_component.type, node_id, node_label)]

    return _dedupe_signals(signals)


def _resolve_thermal_node_signals(
    scope_component: Component,
    node_id: str,
    node_refs: dict[str, list[tuple[str, int]]],
    component_lookup: dict[str, Component],
) -> list[ScopeSignal]:
    """Resolve thermal scope node to connected component temperature signals."""
    scope_id = str(scope_component.id)
    signals: list[ScopeSignal] = []

    for comp_id, _pin_index in node_refs.get(node_id, []):
        if comp_id == scope_id:
            continue
        component = component_lookup.get(comp_id)
        if component is None:
            continue
        if _pin_index >= len(component.pins):
            continue
        pin_name = component.pins[_pin_index].name
        pin_is_thermal = (
            pin_name == THERMAL_PORT_PIN_NAME
            or pin_connection_domain(component, _pin_index) == CONNECTION_DOMAIN_THERMAL
        )
        if not pin_is_thermal:
            continue
        if component.type in THERMAL_SIGNAL_EXCLUDED_TYPES:
            continue

        label = component.name or component.type.name.replace("_", " ").title()
        signals.append(
            ScopeSignal(
                label=label,
                signal_key=format_signal_key("T", label),
                node_id=node_id,
                node_label=label,
            )
        )

    return _dedupe_signals(signals)


def _resolve_control_signal(
    component: Component,
    pin_index: int,
    node_id: str,
) -> ScopeSignal | None:
    """Resolve control-domain outputs so scopes can bind directly without probes."""
    if pin_index < 0 or pin_index >= len(component.pins):
        return None
    if component.type in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE):
        return None
    if pin_connection_domain(component, pin_index) != CONNECTION_DOMAIN_SIGNAL:
        return None

    pin_name = component.pins[pin_index].name.upper()
    component_name = component.name or component.type.name.replace("_", " ").title()
    if not component_name:
        return None

    if component.type == ComponentType.PWM_GENERATOR:
        if pin_name == "OUT":
            key = component_name
            return ScopeSignal(label=key, signal_key=key, node_id=node_id, node_label=component_name)
        if pin_name == "DUTY_IN":
            key = f"{component_name}.duty"
            return ScopeSignal(label=key, signal_key=key, node_id=node_id, node_label=component_name)
        return None

    if component.type == ComponentType.C_BLOCK:
        if pin_name in {"OUT", "OUT0"}:
            key = component_name
            return ScopeSignal(label=key, signal_key=key, node_id=node_id, node_label=component_name)
        if not pin_name.startswith("OUT"):
            return None
        try:
            output_index = int(pin_name[3:])
        except (TypeError, ValueError):
            return None
        key = f"{component_name}.out{output_index}"
        return ScopeSignal(label=key, signal_key=key, node_id=node_id, node_label=component_name)

    if not pin_name.startswith("OUT"):
        return None

    return ScopeSignal(
        label=component_name,
        signal_key=component_name,
        node_id=node_id,
        node_label=component_name,
    )


def _expand_mux_inputs(
    scope_component: Component,
    mux_component: Component,
    alias_map: dict[str, str],
    node_refs: dict[str, list[tuple[str, int]]],
    component_lookup: dict[str, Component],
    node_map: dict[tuple[str, int], str],
    visited_nodes: set[str],
    ignore_components: set[str],
) -> list[ScopeSignal]:
    input_count = mux_component.parameters.get("input_count", len(mux_component.pins) - 1)
    ordering = mux_component.parameters.get("ordering") or list(range(input_count))
    labels = mux_component.parameters.get("channel_labels", [])

    signals: list[ScopeSignal] = []
    for entry in ordering:
        try:
            input_idx = int(entry)
        except (TypeError, ValueError):
            continue
        if input_idx < 0 or input_idx >= input_count:
            continue
        pin_index = input_idx
        if pin_index >= len(mux_component.pins):
            continue
        node_id = node_map.get((str(mux_component.id), pin_index))
        preferred = labels[input_idx] if input_idx < len(labels) else mux_component.pins[pin_index].name
        next_ignored = set(ignore_components)
        next_ignored.add(str(mux_component.id))
        child_signals = _resolve_node_signals(
            scope_component,
            node_id,
            alias_map,
            node_refs,
            component_lookup,
            node_map,
            visited_nodes,
            next_ignored,
        )
        if (
            not child_signals
            and node_id
            and scope_component.type not in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE)
        ):
            child_signals = [
                _make_scope_signal(scope_component.type, node_id, _derive_node_label(node_id, alias_map), preferred)
            ]
        for signal in child_signals:
            signal.prepend_label(preferred)
        signals.extend(child_signals)
    return signals


def _expand_demux_outputs(
    scope_component: Component,
    demux_component: Component,
    alias_map: dict[str, str],
    node_refs: dict[str, list[tuple[str, int]]],
    component_lookup: dict[str, Component],
    node_map: dict[tuple[str, int], str],
    visited_nodes: set[str],
    ignore_components: set[str],
) -> list[ScopeSignal]:
    output_count = demux_component.parameters.get("output_count", len(demux_component.pins) - 1)
    ordering = demux_component.parameters.get("ordering") or list(range(output_count))
    labels = demux_component.parameters.get("channel_labels", [])

    signals: list[ScopeSignal] = []
    for entry in ordering:
        try:
            output_idx = int(entry)
        except (TypeError, ValueError):
            continue
        if output_idx < 0 or output_idx >= output_count:
            continue
        pin_index = output_idx + 1  # demux outputs start at pin 1
        if pin_index >= len(demux_component.pins):
            continue
        node_id = node_map.get((str(demux_component.id), pin_index))
        preferred = labels[output_idx] if output_idx < len(labels) else demux_component.pins[pin_index].name
        next_ignored = set(ignore_components)
        next_ignored.add(str(demux_component.id))
        child_signals = _resolve_node_signals(
            scope_component,
            node_id,
            alias_map,
            node_refs,
            component_lookup,
            node_map,
            visited_nodes,
            next_ignored,
        )
        if (
            not child_signals
            and node_id
            and scope_component.type not in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE)
        ):
            child_signals = [
                _make_scope_signal(scope_component.type, node_id, _derive_node_label(node_id, alias_map), preferred)
            ]
        for signal in child_signals:
            signal.prepend_label(preferred)
        signals.extend(child_signals)
    return signals


def _resolve_demux_output(
    scope_component: Component,
    demux_component: Component,
    pin_index: int,
    alias_map: dict[str, str],
    node_refs: dict[str, list[tuple[str, int]]],
    component_lookup: dict[str, Component],
    node_map: dict[tuple[str, int], str],
    visited_nodes: set[str],
    ignore_components: set[str],
) -> list[ScopeSignal]:
    output_idx = max(0, pin_index - 1)
    output_count = demux_component.parameters.get("output_count", len(demux_component.pins) - 1)
    ordering = demux_component.parameters.get("ordering") or list(range(output_count))
    ordering = ordering[:output_count]
    lane_index = _lane_for_output_index(ordering, output_idx)
    input_node = node_map.get((str(demux_component.id), 0))
    if input_node is None:
        return []

    next_ignored = set(ignore_components)
    next_ignored.add(str(demux_component.id))
    upstream_signals = _resolve_node_signals(
        scope_component,
        input_node,
        alias_map,
        node_refs,
        component_lookup,
        node_map,
        visited_nodes,
        next_ignored,
    )

    if not upstream_signals and scope_component.type not in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE):
        node_label = _derive_node_label(input_node, alias_map)
        placeholder = _make_scope_signal(scope_component.type, input_node, node_label)
        upstream_signals = [placeholder]

    selected = []
    if 0 <= lane_index < len(upstream_signals):
        signal = upstream_signals[lane_index]
        label = _demux_output_label(demux_component, output_idx, signal.label)
        selected.append(
            ScopeSignal(
                label=label,
                signal_key=signal.signal_key,
                node_id=signal.node_id,
                node_label=signal.node_label,
            )
        )
    else:
        if scope_component.type in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE):
            return []
        node_label = _derive_node_label(input_node, alias_map)
        label = _demux_output_label(demux_component, output_idx, node_label or "Signal")
        selected.append(
            _make_scope_signal(scope_component.type, input_node, node_label, label)
        )
    return selected


def _make_scope_signal(
    scope_type: ComponentType,
    node_id: str,
    node_label: str | None,
    preferred_label: str | None = None,
) -> ScopeSignal:
    label = preferred_label or node_label or "Signal"
    prefix = "V" if scope_type == ComponentType.ELECTRICAL_SCOPE else "T"
    signal_key = format_signal_key(prefix, node_label or label)
    return ScopeSignal(label=label, signal_key=signal_key, node_id=node_id, node_label=node_label or label)


def _dedupe_signals(signals: list[ScopeSignal]) -> list[ScopeSignal]:
    deduped: dict[str, ScopeSignal] = {}
    for signal in signals:
        key = signal.signal_key or f"{signal.node_id}:{signal.label}"
        if key in deduped:
            continue
        deduped[key] = signal
    return list(deduped.values())


def _lane_for_output_index(ordering: list[int], output_idx: int) -> int:
    for lane, mapped_output in enumerate(ordering):
        if mapped_output == output_idx:
            return lane
    return output_idx


def _demux_output_label(component: Component, output_idx: int, fallback: str | None) -> str:
    labels = component.parameters.get("channel_labels", [])
    if 0 <= output_idx < len(labels):
        label = labels[output_idx]
        if label:
            return label
    pins = component.pins
    if 0 <= output_idx + 1 < len(pins):
        return pins[output_idx + 1].name
    return fallback or "Signal"


def _derive_node_label(node_id: str | None, alias_map: dict[str, str]) -> str | None:
    if not node_id:
        return None
    if node_id in alias_map:
        return alias_map[node_id]
    if node_id == "0":
        return "GND"
    return f"N{node_id}"


def _default_channel_label(component_type: ComponentType, index: int) -> str:
    if component_type == ComponentType.THERMAL_SCOPE:
        return f"T{index + 1}"
    return f"CH{index + 1}"
