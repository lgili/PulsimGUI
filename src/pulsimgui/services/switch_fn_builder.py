"""Assemble a pulsim 1.3 ``switch_fn`` callback from per-device PWM
configs.

Pulsim 1.0 retired the legacy ``Circuit.add_mosfet(gate, drain, source,
…)`` 3-pin device model. v1.3 treats every controllable switching
branch (MOSFET / IGBT / explicit ``add_switch``) as a 2-terminal
element whose ON/OFF state is decided at simulate-time by a
user-supplied callback::

    switch_fn(t: float) -> SwitchStateMask

The mask has one bit per switching branch, indexed in builder-call
order. PulsimGUI used to drive the gate by wiring a virtual PWM
component directly to the MOSFET's gate node — that path no longer
exists in v1.3 because the gate is not a node anymore.

This module bridges the gap: callers describe each device's PWM in a
:class:`SwitchPwmConfig`, this module produces a ``switch_fn`` that
toggles each ``switch_idx`` according to its config (composed with
``pulsim.make_combined_switch_fn``). The shim's
:class:`pulsim_v0_compat.Circuit` already exposes
``switch_indices`` (``device_name → switch_idx``) and
``num_switches`` — everything else this helper needs.

The expected pipeline is:

1. ``circuit_converter`` builds the circuit through the v0 shim.
2. The shim's ``Circuit.pending_gate_signals`` lists every switch + its
   gate node + its ``switch_idx``.
3. PulsimGUI's PWM-control panel (or a YAML template, or a hand-coded
   test) populates a ``{device_name: SwitchPwmConfig}`` dict.
4. :func:`assemble_switch_fn` produces the callback, which the backend
   passes to ``pulsim.simulate(builder, switch_fn=…)``.

Devices without an explicit config default to **always-OFF** — safer
than leaving them ON, since a MOSFET that's always conducting can
short-circuit a bus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Per-device config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SwitchPwmConfig:
    """PWM drive parameters for one switching branch.

    The defaults produce a 50 % duty cycle at 100 kHz, which is a
    reasonable starting point for the typical SMPS topology but is
    almost certainly not what any specific design wants — callers
    should set the values explicitly.

    Attributes
    ----------
    frequency
        PWM carrier frequency in hertz.
    duty
        ON-time fraction in ``[0, 1]``. Clamped to ``[0, 1]`` so a
        user typo (1.5 → "150 %") doesn't crash the assembler.
    phase
        Phase offset within one PWM period, in radians. Used to
        stagger synchronous-rectifier or interleaved pairs.
    enabled
        When False, the device defaults to OFF for the entire
        simulation regardless of frequency/duty. Useful for
        templating circuits where some MOSFETs are wired but not
        driven (e.g. body-diode-only operation during the dead-time
        characterisation step).
    """

    frequency: float = 100_000.0
    duty: float = 0.5
    phase: float = 0.0
    enabled: bool = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def assemble_switch_fn(
    circuit: Any,
    configs: dict[str, SwitchPwmConfig],
    pulsim_module: Any,
) -> Callable[[float], Any] | None:
    """Build a ``switch_fn(t) -> SwitchStateMask`` callback that
    toggles every switch on ``circuit`` according to ``configs``.

    Parameters
    ----------
    circuit
        A :class:`pulsim_v0_compat.Circuit` — must expose
        ``num_switches`` and ``switch_indices`` (device_name →
        switch_idx).
    configs
        Maps device names to :class:`SwitchPwmConfig`. Devices missing
        from the dict default to OFF.
    pulsim_module
        The real pulsim module — used to source ``make_pwm_switch_fn``,
        ``make_combined_switch_fn``, and ``SwitchStateMask``.

    Returns
    -------
    Callable or None
        ``None`` when ``circuit`` has zero switching branches (no
        ``switch_fn`` needed). Otherwise a callable suitable for
        ``simulate(switch_fn=…)``.
    """
    num_switches = int(getattr(circuit, "num_switches", 0))
    if num_switches <= 0:
        return None

    indices = dict(getattr(circuit, "switch_indices", {}) or {})
    if not indices:
        # We've got switching branches but no device-name map — fall
        # through to an all-OFF mask so the simulator can at least
        # start.
        return _make_constant_off_fn(pulsim_module, num_switches)

    per_switch_fns: list[Callable[[float], Any]] = []
    for device_name, switch_idx in indices.items():
        cfg = configs.get(device_name)
        if cfg is None or not cfg.enabled or cfg.duty <= 0.0:
            # No config / disabled / zero duty → switch stays OFF.
            # We deliberately don't add a ``make_pwm_switch_fn(...,
            # duty=0)`` because that would still allocate a callback;
            # leaving the bit out is cleaner.
            continue
        clamped_duty = min(1.0, max(0.0, float(cfg.duty)))
        per_switch_fns.append(
            pulsim_module.make_pwm_switch_fn(
                float(cfg.frequency),
                clamped_duty,
                int(switch_idx),
                int(num_switches),
                float(cfg.phase),
            )
        )

    if not per_switch_fns:
        return _make_constant_off_fn(pulsim_module, num_switches)

    if len(per_switch_fns) == 1:
        # Skip the composition wrapper when there's only one switch —
        # cheaper and easier to debug.
        return per_switch_fns[0]

    return pulsim_module.make_combined_switch_fn(num_switches, per_switch_fns)


def collect_device_names(circuit: Any) -> list[str]:
    """Return the ordered list of switching-device names a host can
    populate :class:`SwitchPwmConfig` entries for. Convenient for
    surfacing the list in a UI dialog (Run Simulation → PWM table)."""
    return [
        entry["device"]
        for entry in getattr(circuit, "pending_gate_signals", []) or []
    ]


def configs_from_pwm_records(
    circuit: Any,
    fallback_frequency: float = 100_000.0,
    fallback_duty: float = 0.5,
) -> dict[str, SwitchPwmConfig]:
    """Best-effort heuristic: cross-reference the shim's
    ``virtual_component_records`` (PWM generators the GUI emitted) with
    the gate-node assignments and build a :class:`SwitchPwmConfig`
    dict.

    Convention (matches PulsimGUI today): a PWM generator records its
    output as the first entry in ``nodes`` and its params dict carries
    ``frequency`` / ``duty`` / ``phase``. The function looks for a
    virtual component whose first node matches a known ``gate_node``;
    when it finds one, it produces a config for the corresponding
    device.

    Falls back to ``fallback_frequency`` / ``fallback_duty`` for any
    field a record omits. Devices whose gate isn't driven by any PWM
    record stay out of the result (they end up OFF in the assembled
    switch_fn).

    This function is a "default policy", not a contract — once the GUI
    grows a real PWM-config UI, the panel should produce
    ``SwitchPwmConfig`` entries directly and skip this helper.
    """
    gate_to_idx: dict[str, int] = dict(
        getattr(circuit, "gate_node_indices", {}) or {}
    )
    if not gate_to_idx:
        return {}
    # Build switch_idx → device_name reverse map for the final result.
    idx_to_device: dict[int, str] = {
        entry["switch_idx"]: entry["device"]
        for entry in getattr(circuit, "pending_gate_signals", []) or []
        if entry.get("gate_node")
    }

    out: dict[str, SwitchPwmConfig] = {}
    virtual_components: Iterable[dict[str, Any]] = (
        getattr(circuit, "virtual_component_records", []) or []
    )
    for record in virtual_components:
        if not _looks_like_pwm_gen(record):
            continue
        first_node = _first_node(record)
        if first_node is None:
            continue
        switch_idx = gate_to_idx.get(first_node)
        if switch_idx is None:
            continue
        device_name = idx_to_device.get(switch_idx)
        if device_name is None:
            continue
        params = record.get("params") or {}
        out[device_name] = SwitchPwmConfig(
            frequency=float(params.get("frequency", fallback_frequency)),
            duty=float(params.get("duty", fallback_duty)),
            phase=float(params.get("phase", 0.0)),
            enabled=bool(params.get("enabled", True)),
        )
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _make_constant_off_fn(
    pulsim_module: Any,
    num_switches: int,
) -> Callable[[float], Any]:
    """Callback that returns an all-zero ``SwitchStateMask`` regardless
    of ``t``. The simulator will treat every switching branch as OFF
    (g_off) for the entire run — equivalent to leaving a MOSFET's gate
    floating low."""

    mask_cls = pulsim_module.SwitchStateMask

    def _all_off(_t: float) -> Any:
        return mask_cls(int(num_switches))

    return _all_off


def _looks_like_pwm_gen(record: dict[str, Any]) -> bool:
    """Heuristic: a PulsimGUI virtual component is a PWM generator
    when its ``kind`` string contains "pwm" (case-insensitive). The
    GUI uses ``"pwm_generator"`` today; we match more loosely so
    future renames don't silently break the heuristic."""
    kind = str(record.get("kind", "")).lower()
    return "pwm" in kind


def _first_node(record: dict[str, Any]) -> str | None:
    nodes = record.get("nodes") or []
    if not nodes:
        return None
    first = nodes[0]
    if first is None:
        return None
    return str(first)
