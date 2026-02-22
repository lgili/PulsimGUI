"""Helpers for resolving scope channel bindings."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import (
    Component,
    ComponentType,
    CURRENT_PROBE_OUTPUT_PIN_NAME,
    THERMAL_PORT_PIN_NAME,
    VOLTAGE_PROBE_OUTPUT_PIN_NAME,
)
from pulsimgui.utils.net_utils import build_node_map, build_node_alias_map
from pulsimgui.utils.signal_utils import format_signal_key

THERMAL_SIGNAL_EXCLUDED_TYPES = {
    ComponentType.GROUND,
    ComponentType.ELECTRICAL_SCOPE,
    ComponentType.THERMAL_SCOPE,
    ComponentType.VOLTAGE_PROBE,
    ComponentType.CURRENT_PROBE,
    ComponentType.POWER_PROBE,
    ComponentType.SIGNAL_MUX,
    ComponentType.SIGNAL_DEMUX,
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
        """Human-readable label (channel label + node)."""
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
    expanded = False

    for comp_id, pin_index in node_refs.get(node_id, []):
        if comp_id in ignored:
            continue
        component = component_lookup.get(comp_id)
        if component is None:
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
        elif component.type == ComponentType.VOLTAGE_PROBE and pin_name == VOLTAGE_PROBE_OUTPUT_PIN_NAME:
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
        elif component.type == ComponentType.CURRENT_PROBE and pin_name == CURRENT_PROBE_OUTPUT_PIN_NAME:
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
        if component.pins[_pin_index].name != THERMAL_PORT_PIN_NAME:
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
