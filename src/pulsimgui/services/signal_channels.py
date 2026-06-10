"""Enumerate the signal channels a circuit exposes for name-based binding.

Several control parameters bind by typing a component name into a free-text
field — ``duty_from_channel`` on PWM_GENERATOR, the C_BLOCK ``inputs`` list…
A typo silently falls back to defaults, which is the classic "why is my duty
stuck at 0.5" failure. This service lists the names that are actually
bindable in the open circuit so the editor can offer a validated picker
(an editable combo — free text still allowed for forward-compat).

What counts as a channel (mirrors what the converter's channel inference
binds by name):

* measurement probes — VOLTAGE_PROBE / VOLTAGE_PROBE_GND / CURRENT_PROBE /
  POWER_PROBE component names;
* signal-domain block outputs — CONSTANT, GAIN, PI/PID, SUM, SUBTRACTOR,
  LIMITER, INTEGRATOR, DIFFERENTIATOR, RATE_LIMITER, HYSTERESIS,
  LOOKUP_TABLE, TRANSFER_FUNCTION, DELAY_BLOCK, SAMPLE_HOLD, STATE_MACHINE,
  C_BLOCK names (their output drives the wire they're connected to);
* PLL / transforms — name-based sub-channels (``<name>.theta`` style) for
  forward compatibility with the dq blocks.

Pure Python (no Qt) so it unit-tests in isolation.
"""
from __future__ import annotations

from pulsimgui.models.component import ComponentType

_PROBE_TYPES = {
    ComponentType.VOLTAGE_PROBE,
    ComponentType.VOLTAGE_PROBE_GND,
    ComponentType.CURRENT_PROBE,
    ComponentType.POWER_PROBE,
}

_SIGNAL_BLOCK_TYPES = {
    ComponentType.CONSTANT,
    ComponentType.GAIN,
    ComponentType.PI_CONTROLLER,
    ComponentType.PID_CONTROLLER,
    ComponentType.SUM,
    ComponentType.SUBTRACTOR,
    ComponentType.LIMITER,
    ComponentType.INTEGRATOR,
    ComponentType.DIFFERENTIATOR,
    ComponentType.RATE_LIMITER,
    ComponentType.HYSTERESIS,
    ComponentType.LOOKUP_TABLE,
    ComponentType.TRANSFER_FUNCTION,
    ComponentType.DELAY_BLOCK,
    ComponentType.SAMPLE_HOLD,
    ComponentType.STATE_MACHINE,
    ComponentType.C_BLOCK,
}

# Name-based sub-channels exposed by dedicated blocks.
_SUBCHANNEL_TYPES: dict[ComponentType, tuple[str, ...]] = {
    ComponentType.PLL: ("theta", "omega"),
    ComponentType.PARK_TRANSFORM: ("d", "q"),
    ComponentType.CLARKE_TRANSFORM: ("alpha", "beta"),
}


def enumerate_channels(circuit) -> list[str]:
    """All bindable channel names in ``circuit``, sorted, probes first.

    ``circuit`` is the GUI :class:`~pulsimgui.models.circuit.Circuit` (only
    ``components.values()`` with ``type``/``name`` is required, so mocks and
    dict-shims work too).
    """
    if circuit is None:
        return []
    components = getattr(circuit, "components", None)
    if components is None:
        return []
    values = components.values() if hasattr(components, "values") else components

    probes: list[str] = []
    blocks: list[str] = []
    subs: list[str] = []
    for comp in values:
        ctype = getattr(comp, "type", None)
        name = str(getattr(comp, "name", "") or "").strip()
        if not name or ctype is None:
            continue
        if ctype in _PROBE_TYPES:
            probes.append(name)
        elif ctype in _SIGNAL_BLOCK_TYPES:
            blocks.append(name)
        if ctype in _SUBCHANNEL_TYPES:
            subs.extend(f"{name}.{sub}" for sub in _SUBCHANNEL_TYPES[ctype])
    return sorted(probes) + sorted(blocks) + sorted(subs)


def is_channel_parameter(param_name: str) -> bool:
    """Should this parameter get the channel picker?"""
    return param_name.endswith("_from_channel")
