"""Resolve a scope component's wired probes into ``scope_v2`` signal specs.

The resolver is the single seam between scope_v2 and the rest of the
GUI — it knows about ``ScopeChannelBinding`` (from the old scope
package) and the simulation service's circuit builder, and produces
the variant-agnostic specs that ``LiveStreamCapability`` and
``PostSimCapability`` consume.

Keeping the seam narrow lets us delete the old scope package later
without touching scope_v2 — only this file imports the legacy helper.
"""

from __future__ import annotations

import logging
from typing import Any

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

from ._auto_palette import next_palette_color
from .bindings import build_scope_channel_bindings
from .capabilities.live_stream import LiveSignalSpec
from .capabilities.post_sim import PostSimSignalSpec

_LOG = logging.getLogger(__name__)


def _live_node_keys(node_id: str | None, node_label: str | None) -> tuple[str, ...]:
    """Candidate live-stream channel names (``V(...)``) for a circuit node.

    The kernel names live state-vector columns ``V(<wire-alias>)`` or
    ``V(N<netid>)`` and exposes them via ``stream.state_index_for(name)``.
    We try the alias form first, then the numeric forms — mirroring
    ``MainWindow._probe_backend_series`` so post-sim and live agree.
    """
    keys: list[str] = []
    if node_label:
        keys.append(f"V({node_label})")
    if node_id:
        keys.append(f"V(N{node_id})")
        keys.append(f"V({node_id})")
    return tuple(dict.fromkeys(keys))


def _channel_sense_nodes(
    circuit: Circuit,
    node_map: dict[tuple[str, int], str],
    alias_map: dict[str, str],
    binding: Any,
    first_signal: Any,
) -> tuple[tuple[str | None, str | None], tuple[str | None, str | None]]:
    """Resolve a channel's ``"+"`` / ``"-"`` sense nodes as ``(id, label)`` pairs.

    For a voltage-probe channel the terminals are the probe's sense pins
    (pin 0 = ``"+"``, pin 1 = ``"-"``); a ``VOLTAGE_PROBE_GND`` or a
    ground-referenced ``"-"`` has no second terminal. For a scope wired
    straight to a node, ``"+"`` is that node and there is no ``"-"``.
    """
    key = (first_signal.signal_key or "") if first_signal is not None else ""
    if key.startswith("VP(") and first_signal is not None:
        probe = next(
            (
                c
                for c in circuit.components.values()
                if c.name == first_signal.label
                and c.type in (ComponentType.VOLTAGE_PROBE, ComponentType.VOLTAGE_PROBE_GND)
            ),
            None,
        )
        if probe is not None:
            pid = str(probe.id)
            pos_id = node_map.get((pid, 0))
            pos_label = alias_map.get(pos_id) if pos_id else None
            neg_id = neg_label = None
            if probe.type == ComponentType.VOLTAGE_PROBE:
                cand = node_map.get((pid, 1))
                if cand is not None and str(cand).strip() not in ("0", ""):
                    neg_id = cand
                    neg_label = alias_map.get(cand)
            return (pos_id, pos_label or pos_id), (neg_id, neg_label or neg_id)
    return (binding.node_id, binding.node_label), (None, None)


def _circuit_builder(simulation_service: Any, project: Any) -> Any | None:
    """Pull the kernel circuit builder out of the simulation service.

    Mirrors the dance ``main_window._on_live_stream_ready`` already does
    so we share one resolution path. Returns ``None`` when the builder
    isn't reachable (kernel not loaded, project incomplete, …) — the
    caller falls back to ``state_idx=channel_index`` in that case so the
    live capability still has something to plot during a smoke test.
    """
    converter = getattr(simulation_service, "_circuit_converter", None)
    if converter is None or project is None:
        return None
    try:
        circuit_data = converter.project_to_dict(project)
    except Exception:  # noqa: BLE001 - defensive against backend errors
        return None
    builder = circuit_data.get("circuit") if isinstance(circuit_data, dict) else None
    if builder is None:
        return None
    return getattr(builder, "builder", builder)


def _state_idx_for_node(builder: Any | None, node_id: str | int | None) -> int | None:
    """Resolve a kernel state-vector index for ``node_id``.

    The kernel exposes ``builder.node_id_of(name)`` — the name is the
    same node identifier the schematic uses (``"7"``, ``"N7"``, …). We
    try both forms because different backends normalise differently.
    """
    if builder is None or node_id is None:
        return None
    nameset = []
    s = str(node_id)
    nameset.append(s)
    if not s.startswith("N"):
        nameset.append(f"N{s}")
    else:
        nameset.append(s[1:])
    fn = getattr(builder, "node_id_of", None)
    if not callable(fn):
        return None
    for name in nameset:
        try:
            idx = int(fn(name))
        except Exception:  # noqa: BLE001
            continue
        return idx
    return None


def resolve_scope_signal_specs(
    scope_component: Component,
    circuit: Circuit,
    simulation_service: Any,
    project: Any,
) -> tuple[list[LiveSignalSpec], list[PostSimSignalSpec]]:
    """Return ``(live_specs, post_specs)`` for the scope's wired channels.

    Only channels with a resolved ``signal_key`` (i.e. a probe is wired
    to the scope pin) show up; idle channels are silently skipped so the
    sidebar doesn't list dead inputs.

    The post-sim spec carries a primary ``signal_key`` plus a list of
    ``fallback_keys`` so the lookup tolerates the several ways the same
    signal can show up in ``SimulationResult.signals``:

    * ``VP(probe_name)`` — what ``MainWindow._result_with_probe_signals``
      synthesizes after the run.
    * ``probe_name`` — the raw virtual channel the kernel typically
      emits for a probe component.
    * ``V(node_id)`` / ``V(node_label)`` — what the kernel emits when a
      scope is wired directly to a circuit node without a probe.
    * The binding's display name — covers user-renamed channels.

    Whichever name the backend used wins; the unused fallbacks are
    silently ignored.
    """
    bindings = build_scope_channel_bindings(scope_component, circuit)
    builder = _circuit_builder(simulation_service, project)
    node_map = build_node_map(circuit)
    alias_map = build_node_alias_map(circuit, node_map)
    channels = scope_component.parameters.get("channels", []) or []

    is_thermal = scope_component.type.name == "THERMAL_SCOPE"
    prefix = "T" if is_thermal else "V"
    unit = "°C" if is_thermal else "V"

    live: list[LiveSignalSpec] = []
    post: list[PostSimSignalSpec] = []
    for i, binding in enumerate(bindings):
        # A channel may name a result signal directly (``"signal"`` in its
        # config) instead of being wired to a probe — used to plot device
        # observer traces (e.g. ``M1.speed_rpm`` / ``M1.i_a``) that aren't
        # electrical nodes. Post-sim only: they're not in the live state
        # vector, so they appear when the run finishes.
        channel_cfg = channels[i] if i < len(channels) else {}
        direct_signal = ""
        if isinstance(channel_cfg, dict):
            direct_signal = str(channel_cfg.get("signal") or "").strip()
        if direct_signal:
            display = str(channel_cfg.get("label") or direct_signal)
            post.append(PostSimSignalSpec(
                name=display,
                signal_key=direct_signal,
                fallback_keys=(),
            ))
            continue

        # ``signals[0].signal_key`` is the canonical key the kernel emits
        # into ``SimulationResult.signals``. Without a key there's nothing
        # to plot.
        signal_key: str | None = None
        first_signal = None
        for sig in binding.signals:
            if sig.signal_key:
                signal_key = sig.signal_key
                first_signal = sig
                break
        if not signal_key:
            continue

        display = binding.display_name
        color = next_palette_color(i)

        # Best-effort state-vector index for the live capability. Falls
        # back to the channel index so the capability still draws
        # *something* — the data will look wrong but the wiring is
        # exercised, which catches integration bugs in CI.
        state_idx = _state_idx_for_node(builder, binding.node_id)
        if state_idx is None:
            _LOG.debug(
                "resolve_scope_signal_specs: node %r unresolved, "
                "falling back to channel index %d",
                binding.node_id, i,
            )
            state_idx = i

        # Build candidate keys in priority order. We dedupe at the end
        # so the tuple is short.
        candidates: list[str] = []
        if first_signal is not None:
            label = first_signal.label
            if label:
                candidates.append(label)
                candidates.append(f"{prefix}({label})")
            node_label = first_signal.node_label
            if node_label:
                candidates.append(node_label)
                candidates.append(f"{prefix}({node_label})")
            node_id = first_signal.node_id
            if node_id:
                candidates.append(str(node_id))
                candidates.append(f"{prefix}({node_id})")
        if binding.node_label:
            candidates.append(binding.node_label)
            candidates.append(f"{prefix}({binding.node_label})")
        if binding.channel_label:
            candidates.append(binding.channel_label)
            candidates.append(f"{prefix}({binding.channel_label})")
        candidates.append(display)

        # De-dup while preserving order; drop the primary so we don't
        # try it twice in PostSimCapability.
        seen = {signal_key}
        fallback_keys: list[str] = []
        for key in candidates:
            if key and key not in seen:
                seen.add(key)
                fallback_keys.append(key)

        # Live state-vector columns: the kernel permutes nodes, so the
        # capability resolves these names against the stream's own index
        # at run time. A differential VOLTAGE_PROBE yields a "-" terminal
        # so the live trace plots V(+) − V(−), matching the post-sim path.
        (pos_id, pos_label), (neg_id, neg_label) = _channel_sense_nodes(
            circuit, node_map, alias_map, binding, first_signal,
        )
        live.append(LiveSignalSpec(
            name=display,
            state_idx=state_idx,
            color=color,
            unit=unit,
            panel="Main",
            pos_keys=_live_node_keys(pos_id, pos_label),
            neg_keys=_live_node_keys(neg_id, neg_label),
        ))
        post.append(PostSimSignalSpec(
            name=display,
            signal_key=signal_key,
            fallback_keys=tuple(fallback_keys),
        ))

    return live, post


__all__ = ["resolve_scope_signal_specs"]
