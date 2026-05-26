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

from pulsimgui.models.component import Component
from pulsimgui.models.circuit import Circuit
from pulsimgui.views.scope.bindings import build_scope_channel_bindings

from ._auto_palette import next_palette_color
from .capabilities.live_stream import LiveSignalSpec
from .capabilities.post_sim import PostSimSignalSpec


_LOG = logging.getLogger(__name__)


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
    """
    bindings = build_scope_channel_bindings(scope_component, circuit)
    builder = _circuit_builder(simulation_service, project)

    live: list[LiveSignalSpec] = []
    post: list[PostSimSignalSpec] = []
    for i, binding in enumerate(bindings):
        # ``signals[0].signal_key`` is the canonical key the kernel emits
        # into ``SimulationResult.signals``. Without a key there's nothing
        # to plot.
        signal_key: str | None = None
        for sig in binding.signals:
            if sig.signal_key:
                signal_key = sig.signal_key
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

        live.append(LiveSignalSpec(
            name=display,
            state_idx=state_idx,
            color=color,
            unit="V" if scope_component.type.name == "ELECTRICAL_SCOPE" else "°C",
            panel="Main",
        ))
        post.append(PostSimSignalSpec(name=display, signal_key=signal_key))

    return live, post


__all__ = ["resolve_scope_signal_specs"]
