"""Component model for circuit elements."""

import math
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from uuid import UUID, uuid4


class ComponentType(Enum):
    """Types of circuit components."""

    # Basic passive components
    RESISTOR = auto()
    CAPACITOR = auto()
    INDUCTOR = auto()

    # Sources
    VOLTAGE_SOURCE = auto()
    CURRENT_SOURCE = auto()
    GROUND = auto()

    # Semiconductors - diodes
    DIODE = auto()
    ZENER_DIODE = auto()
    LED = auto()

    # Semiconductors - transistors
    MOSFET_N = auto()
    MOSFET_P = auto()
    IGBT = auto()
    BJT_NPN = auto()
    BJT_PNP = auto()
    THYRISTOR = auto()
    TRIAC = auto()

    # Switching
    SWITCH = auto()

    # Transformers
    TRANSFORMER = auto()

    # Analog
    OP_AMP = auto()
    COMPARATOR = auto()

    # Protection
    RELAY = auto()
    FUSE = auto()
    CIRCUIT_BREAKER = auto()

    # Control blocks - basic
    PI_CONTROLLER = auto()
    PID_CONTROLLER = auto()
    MATH_BLOCK = auto()
    PWM_GENERATOR = auto()
    GAIN = auto()
    SUM = auto()
    SUBTRACTOR = auto()
    CONSTANT = auto()

    # Control blocks - signal processing
    INTEGRATOR = auto()
    DIFFERENTIATOR = auto()
    LIMITER = auto()
    RATE_LIMITER = auto()
    HYSTERESIS = auto()

    # Control blocks - advanced
    LOOKUP_TABLE = auto()
    TRANSFER_FUNCTION = auto()
    DELAY_BLOCK = auto()
    SAMPLE_HOLD = auto()
    STATE_MACHINE = auto()
    C_BLOCK = auto()

    # Measurement
    VOLTAGE_PROBE = auto()
    VOLTAGE_PROBE_GND = auto()
    CURRENT_PROBE = auto()
    POWER_PROBE = auto()

    # Scopes
    ELECTRICAL_SCOPE = auto()
    THERMAL_SCOPE = auto()

    # Signal routing
    SIGNAL_MUX = auto()
    SIGNAL_DEMUX = auto()
    GOTO_LABEL = auto()
    FROM_LABEL = auto()

    # Magnetic
    SATURABLE_INDUCTOR = auto()
    COUPLED_INDUCTOR = auto()

    # Three-phase / vector control (Pulsim Phase 28)
    CLARKE_TRANSFORM = auto()
    INVERSE_CLARKE_TRANSFORM = auto()
    PARK_TRANSFORM = auto()
    INVERSE_PARK_TRANSFORM = auto()
    PLL = auto()
    SVM = auto()

    # Three-phase grid source (Pulsim 0.10.0a1+: Circuit::add_three_phase_source)
    THREE_PHASE_SOURCE = auto()

    # Motors (Pulsim 0.10.0a2+: full device-variant integration)
    DC_MOTOR = auto()

    # 3-phase RL load (Pulsim 0.10.0a3+: Y/Δ topology, balanced/unbalanced)
    THREE_PHASE_RL_LOAD = auto()

    # PMSM at fixed rotor speed (Pulsim 0.10.0a3+: R_s + L_s + back-EMF per phase)
    PMSM_STEADY_STATE = auto()

    # Pre-configured networks
    SNUBBER_RC = auto()

    # Hierarchical
    SUBCIRCUIT = auto()


@dataclass
class Pin:
    """A connection point on a component."""

    index: int
    name: str
    x: float  # Relative to component origin
    y: float

    def to_dict(self) -> dict:
        """Serialize pin to dictionary."""
        return {"index": self.index, "name": self.name, "x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict) -> "Pin":
        """Deserialize pin from dictionary."""
        return cls(
            index=data["index"],
            name=data["name"],
            x=data["x"],
            y=data["y"],
        )


PIN_GRID_STEP = 20.0


def _snap_to_pin_grid(value: float) -> float:
    """Snap a coordinate to the pin grid step using half-away-from-zero rounding."""
    step = PIN_GRID_STEP
    value = float(value)
    if value >= 0:
        return math.floor((value + step / 2.0) / step) * step
    return math.ceil((value - step / 2.0) / step) * step


def _snap_pin_layout(pins: list[Pin]) -> list[Pin]:
    """Return a copy of pins with coordinates aligned to the pin grid."""
    return [
        Pin(pin.index, pin.name, _snap_to_pin_grid(pin.x), _snap_to_pin_grid(pin.y))
        for pin in pins
    ]


def _snap_component_pins_to_grid(component: "Component") -> None:
    """Mutate component pin coordinates so every pin lands on the wiring grid."""
    component.pins = _snap_pin_layout(component.pins)


def _generate_stacked_pins(
    count: int,
    x: float,
    name_prefix: str,
    start_index: int = 0,
) -> list[Pin]:
    """Create evenly spaced pins stacked vertically."""

    if count <= 0:
        return []

    spacing = PIN_GRID_STEP
    pins: list[Pin] = []
    for idx in range(count):
        if count % 2 == 1:
            y = (idx - (count // 2)) * spacing
        else:
            lower_half = count // 2
            if idx < lower_half:
                y = (idx - lower_half) * spacing
            else:
                y = (idx - lower_half + 1) * spacing
        pins.append(
            Pin(
                start_index + idx,
                f"{name_prefix}{idx + 1}",
                _snap_to_pin_grid(x),
                y,
            )
        )
    return pins


def _default_scope_pins(channel_count: int) -> list[Pin]:
    """Create default pins for scope components."""

    return _generate_stacked_pins(channel_count, -40, "CH")


def _default_mux_pins(input_count: int) -> list[Pin]:
    """Create default pins for mux blocks."""

    pins = _generate_stacked_pins(input_count, -20, "IN")
    pins.append(Pin(len(pins), "OUT", 20, 0))
    return pins


def _default_demux_pins(output_count: int) -> list[Pin]:
    """Create default pins for demux blocks."""

    pins = [Pin(0, "IN", -20, 0)]
    pins.extend(
        _generate_stacked_pins(output_count, 20, "OUT", start_index=1)
    )
    return pins


def _default_c_block_pins(input_count: int, output_count: int) -> list[Pin]:
    """Create IN/OUT pins for C-Block with canonical ABI naming."""
    pins: list[Pin] = []
    for index, pin in enumerate(_generate_stacked_pins(input_count, -35, "IN", start_index=0)):
        pin.index = index
        pin.name = f"IN{index}"
        pins.append(pin)

    if output_count == 1:
        pins.append(Pin(len(pins), "OUT", 35, 0))
    else:
        out_pins = _generate_stacked_pins(output_count, 35, "OUT", start_index=len(pins))
        for out_index, pin in enumerate(out_pins):
            pin.name = f"OUT{out_index}"
            pins.append(pin)

    return pins


def _default_unary_block_pins() -> list[Pin]:
    """Create IN/OUT pin pair for unary signal blocks."""
    return [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)]


def _default_sum_pins(input_count: int) -> list[Pin]:
    """Create stacked input pins plus single output pin for sum/sub blocks."""
    pins = _generate_stacked_pins(input_count, -35, "IN")
    pins.append(Pin(len(pins), "OUT", 35, 0))
    return pins


def _scope_label_prefix(comp_type: ComponentType) -> str:
    """Get default label prefix for scope channels based on component type."""

    return "CH" if comp_type == ComponentType.ELECTRICAL_SCOPE else "T"


THERMAL_PORT_PARAMETER = "enable_thermal_port"
THERMAL_PORT_PIN_NAME = "TH"
DUTY_INPUT_PARAMETER = "enable_duty_input"
DUTY_INPUT_PIN_NAME = "DUTY_IN"
VOLTAGE_PROBE_OUTPUT_PIN_NAME = "OUT"
CURRENT_PROBE_OUTPUT_PIN_NAME = "MEAS"
MAGNETIC_CORE_SUPPORTED_TYPES: set[ComponentType] = {
    ComponentType.SATURABLE_INDUCTOR,
}
THERMAL_PORT_SUPPORTED_TYPES: set[ComponentType] = {
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
    ComponentType.BJT_NPN,
    ComponentType.BJT_PNP,
    ComponentType.THYRISTOR,
    ComponentType.TRIAC,
    ComponentType.SWITCH,
    ComponentType.TRANSFORMER,
    ComponentType.RELAY,
    ComponentType.FUSE,
    ComponentType.CIRCUIT_BREAKER,
    ComponentType.SATURABLE_INDUCTOR,
    ComponentType.COUPLED_INDUCTOR,
    ComponentType.SNUBBER_RC,
}

THERMAL_PARAMETER_SUPPORTED_TYPES: set[ComponentType] = {
    ComponentType.RESISTOR,
    ComponentType.DIODE,
    ComponentType.MOSFET_N,
    ComponentType.MOSFET_P,
    ComponentType.IGBT,
    ComponentType.BJT_NPN,
    ComponentType.BJT_PNP,
}


def supports_thermal_port(component_type: ComponentType) -> bool:
    """Return True when component type can expose a thermal measurement port."""

    return component_type in THERMAL_PORT_SUPPORTED_TYPES


def supports_electrothermal_parameters(component_type: ComponentType) -> bool:
    """Return True when the component supports electrothermal Rth/Cth parameters."""

    return component_type in THERMAL_PARAMETER_SUPPORTED_TYPES


def _pin_name(component: "Component", pin_index: int) -> str:
    if 0 <= pin_index < len(component.pins):
        return component.pins[pin_index].name
    return ""


def is_scope_input_pin(component: "Component", pin_index: int) -> bool:
    """Return True when pin belongs to an electrical or thermal scope input."""
    if pin_index < 0 or pin_index >= len(component.pins):
        return False
    return component.type in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE)


def is_voltage_probe_output_pin(component: "Component", pin_index: int) -> bool:
    """Return True when pin is the scope-facing output of a voltage probe."""
    if component.type not in (ComponentType.VOLTAGE_PROBE, ComponentType.VOLTAGE_PROBE_GND):
        return False
    return _pin_name(component, pin_index) == VOLTAGE_PROBE_OUTPUT_PIN_NAME


def is_current_probe_output_pin(component: "Component", pin_index: int) -> bool:
    """Return True when pin is the scope-facing output of a current probe."""
    if component.type != ComponentType.CURRENT_PROBE:
        return False
    return _pin_name(component, pin_index) == CURRENT_PROBE_OUTPUT_PIN_NAME


def is_thermal_output_pin(component: "Component", pin_index: int) -> bool:
    """Return True for optional thermal output pins exposed by components."""
    if is_scope_input_pin(component, pin_index):
        return False
    return _pin_name(component, pin_index) == THERMAL_PORT_PIN_NAME


def is_electrical_probe_output_pin(component: "Component", pin_index: int) -> bool:
    """Return True for any electrical probe output that can feed electrical scopes."""
    return is_voltage_probe_output_pin(component, pin_index) or is_current_probe_output_pin(component, pin_index)


def is_restricted_measurement_pin(component: "Component", pin_index: int) -> bool:
    """Return True when a pin has dedicated measurement-routing rules."""
    return (
        is_scope_input_pin(component, pin_index)
        or is_electrical_probe_output_pin(component, pin_index)
        or is_thermal_output_pin(component, pin_index)
    )


def can_connect_measurement_pins(
    left_component: "Component",
    left_pin_index: int,
    right_component: "Component",
    right_pin_index: int,
) -> bool:
    """Validate dedicated scope/probe/thermal routing compatibility."""
    left_is_e_scope = left_component.type == ComponentType.ELECTRICAL_SCOPE
    right_is_e_scope = right_component.type == ComponentType.ELECTRICAL_SCOPE
    left_is_t_scope = left_component.type == ComponentType.THERMAL_SCOPE
    right_is_t_scope = right_component.type == ComponentType.THERMAL_SCOPE

    left_is_e_probe_out = is_electrical_probe_output_pin(left_component, left_pin_index)
    right_is_e_probe_out = is_electrical_probe_output_pin(right_component, right_pin_index)
    left_is_signal_scope_source = is_signal_scope_source_pin(left_component, left_pin_index)
    right_is_signal_scope_source = is_signal_scope_source_pin(right_component, right_pin_index)
    left_is_t_out = is_thermal_output_pin(left_component, left_pin_index)
    right_is_t_out = is_thermal_output_pin(right_component, right_pin_index)

    # Scope routing constraints apply only when an Electrical Scope is involved.
    # Otherwise, direct signal-to-signal links (e.g. CONSTANT -> C_BLOCK,
    # PI -> PWM DUTY_IN, probe OUT -> C_BLOCK) should be accepted.
    if left_is_e_scope or right_is_e_scope:
        return (
            left_is_e_scope
            and (right_is_e_probe_out or right_is_signal_scope_source)
        ) or (
            right_is_e_scope
            and (left_is_e_probe_out or left_is_signal_scope_source)
        )

    thermal_group = left_is_t_scope or right_is_t_scope or left_is_t_out or right_is_t_out
    if thermal_group:
        return (left_is_t_scope and right_is_t_out) or (right_is_t_scope and left_is_t_out)

    return True


CONNECTION_DOMAIN_CIRCUIT = "circuit"
CONNECTION_DOMAIN_SIGNAL = "signal"
CONNECTION_DOMAIN_THERMAL = "thermal"
CONNECTION_DOMAIN_ANY = "any"

# Map switching-device component types to their gate/base/control pin indices.
# These pins accept signal-domain connections (e.g. PWM output).
_CONTROL_PIN_INDICES: dict[ComponentType, set[int]] = {
    ComponentType.MOSFET_N:  {1},   # G
    ComponentType.MOSFET_P:  {1},   # G
    ComponentType.IGBT:      {1},   # G
    ComponentType.BJT_NPN:   {1},   # B
    ComponentType.BJT_PNP:   {1},   # B
    ComponentType.THYRISTOR: {2},   # G
    ComponentType.TRIAC:     {2},   # G
    ComponentType.SWITCH:    {2},   # CTL
}

SIGNAL_DOMAIN_COMPONENT_TYPES: set[ComponentType] = {
    ComponentType.ELECTRICAL_SCOPE,
    ComponentType.VOLTAGE_PROBE,
    ComponentType.VOLTAGE_PROBE_GND,
    ComponentType.CURRENT_PROBE,
    ComponentType.POWER_PROBE,
    ComponentType.SIGNAL_MUX,
    ComponentType.SIGNAL_DEMUX,
    ComponentType.PI_CONTROLLER,
    ComponentType.PID_CONTROLLER,
    ComponentType.MATH_BLOCK,
    ComponentType.PWM_GENERATOR,
    ComponentType.GAIN,
    ComponentType.SUM,
    ComponentType.SUBTRACTOR,
    ComponentType.CONSTANT,
    ComponentType.INTEGRATOR,
    ComponentType.DIFFERENTIATOR,
    ComponentType.LIMITER,
    ComponentType.RATE_LIMITER,
    ComponentType.HYSTERESIS,
    ComponentType.LOOKUP_TABLE,
    ComponentType.TRANSFER_FUNCTION,
    ComponentType.DELAY_BLOCK,
    ComponentType.SAMPLE_HOLD,
    ComponentType.STATE_MACHINE,
    ComponentType.C_BLOCK,
    ComponentType.OP_AMP,
    ComponentType.COMPARATOR,
    # Three-phase / vector control
    ComponentType.CLARKE_TRANSFORM,
    ComponentType.INVERSE_CLARKE_TRANSFORM,
    ComponentType.PARK_TRANSFORM,
    ComponentType.INVERSE_PARK_TRANSFORM,
    ComponentType.PLL,
    ComponentType.SVM,
}

THERMAL_DOMAIN_COMPONENT_TYPES: set[ComponentType] = {
    ComponentType.THERMAL_SCOPE,
}

ANY_DOMAIN_COMPONENT_TYPES: set[ComponentType] = {
    ComponentType.GOTO_LABEL,
    ComponentType.FROM_LABEL,
}

CONTROL_SAMPLE_TIME_PARAM = "sample_time"
LEGACY_CONTROL_SAMPLE_TIME_PARAM = "sample_period"
CONTROL_SAMPLE_TIME_ALIASES: tuple[str, ...] = (
    CONTROL_SAMPLE_TIME_PARAM,
    LEGACY_CONTROL_SAMPLE_TIME_PARAM,
)
_MIN_CONTROL_SAMPLE_TIME = 1e-12

# Components that support Simulink-style per-block sampling (Ts).
# Scopes/probes are intentionally excluded.
CONTROL_SAMPLE_TIME_COMPONENT_TYPES: frozenset[ComponentType] = frozenset(
    {
        ComponentType.SIGNAL_MUX,
        ComponentType.SIGNAL_DEMUX,
        ComponentType.PI_CONTROLLER,
        ComponentType.PID_CONTROLLER,
        ComponentType.MATH_BLOCK,
        ComponentType.PWM_GENERATOR,
        ComponentType.GAIN,
        ComponentType.SUM,
        ComponentType.SUBTRACTOR,
        ComponentType.CONSTANT,
        ComponentType.INTEGRATOR,
        ComponentType.DIFFERENTIATOR,
        ComponentType.LIMITER,
        ComponentType.RATE_LIMITER,
        ComponentType.HYSTERESIS,
        ComponentType.LOOKUP_TABLE,
        ComponentType.TRANSFER_FUNCTION,
        ComponentType.DELAY_BLOCK,
        ComponentType.SAMPLE_HOLD,
        ComponentType.STATE_MACHINE,
        ComponentType.C_BLOCK,
        # Three-phase / vector control
        ComponentType.CLARKE_TRANSFORM,
        ComponentType.INVERSE_CLARKE_TRANSFORM,
        ComponentType.PARK_TRANSFORM,
        ComponentType.INVERSE_PARK_TRANSFORM,
        ComponentType.PLL,
        ComponentType.SVM,
    }
)
CONTROL_SAMPLE_TIME_COMPONENT_TYPE_NAMES: frozenset[str] = frozenset(
    component_type.name for component_type in CONTROL_SAMPLE_TIME_COMPONENT_TYPES
)


def supports_control_sample_time(component_type: ComponentType) -> bool:
    """Return True when a component type supports per-block sample time (Ts)."""
    return component_type in CONTROL_SAMPLE_TIME_COMPONENT_TYPES


def _normalize_control_mode_literal(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "sampled": "discrete",
        "sample": "discrete",
        "continuous_time": "continuous",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in {"auto", "continuous", "discrete"} else "auto"


def _coerce_sample_time(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    if not math.isfinite(parsed) or parsed < 0.0:
        parsed = 0.0
    return parsed


def get_control_sample_time(parameters: dict[str, Any], *, default: float = 0.0) -> float:
    """Read sample time from either canonical or legacy parameter names."""
    if not isinstance(parameters, dict):
        return _coerce_sample_time(default, default=0.0)

    for key in CONTROL_SAMPLE_TIME_ALIASES:
        if key not in parameters:
            continue
        return _coerce_sample_time(parameters.get(key), default=default)

    return _coerce_sample_time(default, default=0.0)


def set_control_sample_time(parameters: dict[str, Any], sample_time: Any) -> float:
    """Store canonical sample time and drop legacy alias keys."""
    normalized = _coerce_sample_time(sample_time, default=0.0)
    parameters[CONTROL_SAMPLE_TIME_PARAM] = normalized
    parameters.pop(LEGACY_CONTROL_SAMPLE_TIME_PARAM, None)
    return normalized


def derive_control_schedule_from_serialized_components(
    components: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    fallback_mode: Any = "auto",
    fallback_sample_time: Any = 0.0,
) -> tuple[str, float | None]:
    """Derive aggregate control scheduling from per-block Ts values.

    If at least one eligible control block exists, per-block Ts is authoritative:
    - any Ts > 0 => aggregate discrete mode using the smallest positive Ts
    - all Ts <= 0 => aggregate auto mode

    Fallback settings are used only when no Ts-capable block exists.
    """
    has_sampled_block = False
    min_positive_sample_time: float | None = None

    for component in components:
        if not isinstance(component, dict):
            continue
        type_name = str(component.get("type") or "").strip().upper().replace("-", "_")
        if type_name not in CONTROL_SAMPLE_TIME_COMPONENT_TYPE_NAMES:
            continue
        has_sampled_block = True
        params = component.get("parameters")
        sample_time = get_control_sample_time(params if isinstance(params, dict) else {}, default=0.0)
        if sample_time > 0.0:
            if min_positive_sample_time is None or sample_time < min_positive_sample_time:
                min_positive_sample_time = sample_time

    if has_sampled_block:
        if min_positive_sample_time is not None:
            return "discrete", max(min_positive_sample_time, _MIN_CONTROL_SAMPLE_TIME)
        return "auto", None

    mode = _normalize_control_mode_literal(fallback_mode)
    sample_time = _coerce_sample_time(fallback_sample_time, default=0.0)
    if mode == "discrete":
        return mode, max(sample_time, _MIN_CONTROL_SAMPLE_TIME)
    if sample_time > 0.0:
        return mode, max(sample_time, _MIN_CONTROL_SAMPLE_TIME)
    return mode, None


def component_connection_domain(component_type: ComponentType) -> str:
    """Return the default wiring domain used by a component family."""
    if component_type in ANY_DOMAIN_COMPONENT_TYPES:
        return CONNECTION_DOMAIN_ANY
    if component_type in THERMAL_DOMAIN_COMPONENT_TYPES:
        return CONNECTION_DOMAIN_THERMAL
    if component_type in SIGNAL_DOMAIN_COMPONENT_TYPES:
        return CONNECTION_DOMAIN_SIGNAL
    return CONNECTION_DOMAIN_CIRCUIT


def is_signal_scope_source_pin(component: "Component", pin_index: int) -> bool:
    """Return True when the pin can feed an electrical scope with control-domain data."""
    if pin_index < 0 or pin_index >= len(component.pins):
        return False
    if component.type in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE):
        return False

    pin_name = _pin_name(component, pin_index).strip().upper()
    if not pin_name:
        return False

    if component.type == ComponentType.PWM_GENERATOR:
        # OUT carries switched gate waveform; DUTY_IN maps to duty telemetry channel.
        return pin_name in {"OUT", "DUTY_IN"}

    if component.type == ComponentType.C_BLOCK:
        # C-Block control outputs follow OUT / OUTn ABI pin naming.
        return pin_name == "OUT" or pin_name.startswith("OUT")

    if component.type not in SIGNAL_DOMAIN_COMPONENT_TYPES:
        return False

    return pin_name.startswith("OUT")


def pin_connection_domain(component: "Component", pin_index: int) -> str:
    """Return the effective connection domain for a specific pin."""
    if component.type in ANY_DOMAIN_COMPONENT_TYPES:
        return CONNECTION_DOMAIN_ANY

    if component.type == ComponentType.C_BLOCK:
        # C-Block is pure control-domain: inputs and outputs must be signal wires.
        return CONNECTION_DOMAIN_SIGNAL

    if component.type == ComponentType.THERMAL_SCOPE:
        return CONNECTION_DOMAIN_THERMAL
    if is_thermal_output_pin(component, pin_index):
        return CONNECTION_DOMAIN_THERMAL

    if component.type == ComponentType.VOLTAGE_PROBE:
        return (
            CONNECTION_DOMAIN_SIGNAL
            if is_voltage_probe_output_pin(component, pin_index)
            else CONNECTION_DOMAIN_CIRCUIT
        )

    if component.type == ComponentType.VOLTAGE_PROBE_GND:
        return (
            CONNECTION_DOMAIN_SIGNAL
            if is_voltage_probe_output_pin(component, pin_index)
            else CONNECTION_DOMAIN_CIRCUIT
        )

    if component.type == ComponentType.CURRENT_PROBE:
        return (
            CONNECTION_DOMAIN_SIGNAL
            if is_current_probe_output_pin(component, pin_index)
            else CONNECTION_DOMAIN_CIRCUIT
        )

    if is_scope_input_pin(component, pin_index):
        return CONNECTION_DOMAIN_SIGNAL
    if is_electrical_probe_output_pin(component, pin_index):
        return CONNECTION_DOMAIN_SIGNAL

    # Gate / base / control pins of switching devices accept signal-domain drives.
    if pin_index in _CONTROL_PIN_INDICES.get(component.type, set()):
        return CONNECTION_DOMAIN_SIGNAL

    return component_connection_domain(component.type)


# Default pin configurations for each component type
DEFAULT_PINS: dict[ComponentType, list[Pin]] = {
    # Basic passive
    ComponentType.RESISTOR: [Pin(0, "1", -30, 0), Pin(1, "2", 30, 0)],
    ComponentType.CAPACITOR: [Pin(0, "+", -20, 0), Pin(1, "-", 20, 0)],
    ComponentType.INDUCTOR: [Pin(0, "1", -30, 0), Pin(1, "2", 30, 0)],

    # Sources
    ComponentType.VOLTAGE_SOURCE: [Pin(0, "+", 0, -25), Pin(1, "-", 0, 25)],
    ComponentType.CURRENT_SOURCE: [Pin(0, "+", 0, -25), Pin(1, "-", 0, 25)],
    ComponentType.GROUND: [Pin(0, "gnd", 0, -10)],

    # Diodes
    ComponentType.DIODE: [Pin(0, "A", -20, 0), Pin(1, "K", 20, 0)],
    ComponentType.ZENER_DIODE: [Pin(0, "A", -20, 0), Pin(1, "K", 20, 0)],
    ComponentType.LED: [Pin(0, "A", -20, 0), Pin(1, "K", 20, 0)],

    # Transistors
    ComponentType.MOSFET_N: [Pin(0, "D", 20, -20), Pin(1, "G", -20, 0), Pin(2, "S", 20, 20)],
    ComponentType.MOSFET_P: [Pin(0, "D", 20, 20), Pin(1, "G", -20, 0), Pin(2, "S", 20, -20)],
    ComponentType.IGBT: [Pin(0, "C", 20, -20), Pin(1, "G", -20, 0), Pin(2, "E", 20, 20)],
    ComponentType.BJT_NPN: [Pin(0, "C", 20, -20), Pin(1, "B", -20, 0), Pin(2, "E", 20, 20)],
    ComponentType.BJT_PNP: [Pin(0, "C", 20, 20), Pin(1, "B", -20, 0), Pin(2, "E", 20, -20)],
    ComponentType.THYRISTOR: [Pin(0, "A", 0, -20), Pin(1, "K", 0, 20), Pin(2, "G", -20, 10)],
    ComponentType.TRIAC: [Pin(0, "MT1", 0, -20), Pin(1, "MT2", 0, 20), Pin(2, "G", -20, 10)],

    # Switching
    ComponentType.SWITCH: [Pin(0, "1", -20, 0), Pin(1, "2", 20, 0), Pin(2, "CTL", 0, -20)],

    # Transformer
    ComponentType.TRANSFORMER: [
        Pin(0, "P1", -30, -15),
        Pin(1, "P2", -30, 15),
        Pin(2, "S1", 30, -15),
        Pin(3, "S2", 30, 15),
    ],

    # Analog
    ComponentType.OP_AMP: [
        Pin(0, "IN+", -35, -12),
        Pin(1, "IN-", -35, 12),
        Pin(2, "OUT", 35, 0),
        Pin(3, "V+", 0, -25),
        Pin(4, "V-", 0, 25),
    ],
    ComponentType.COMPARATOR: [
        Pin(0, "IN+", -35, -12),
        Pin(1, "IN-", -35, 12),
        Pin(2, "OUT", 35, 0),
        Pin(3, "V+", 0, -25),
        Pin(4, "V-", 0, 25),
    ],

    # Protection
    ComponentType.RELAY: [
        Pin(0, "COIL+", -35, -15),
        Pin(1, "COIL-", -35, 15),
        Pin(2, "COM", 35, 0),
        Pin(3, "NO", 35, -15),
        Pin(4, "NC", 35, 15),
    ],
    ComponentType.FUSE: [Pin(0, "1", -20, 0), Pin(1, "2", 20, 0)],
    ComponentType.CIRCUIT_BREAKER: [Pin(0, "LINE", -20, 0), Pin(1, "LOAD", 20, 0)],

    # Control blocks - basic
    ComponentType.PI_CONTROLLER: [
        Pin(0, "IN", -35, 0),
        Pin(1, "OUT", 35, 0),
    ],
    ComponentType.PID_CONTROLLER: [
        Pin(0, "IN", -35, -12),
        Pin(1, "FB", -35, 12),
        Pin(2, "OUT", 35, 0),
    ],
    ComponentType.MATH_BLOCK: [
        Pin(0, "A", -35, -12),
        Pin(1, "B", -35, 12),
        Pin(2, "OUT", 35, 0),
    ],
    ComponentType.PWM_GENERATOR: [
        Pin(0, "OUT", 35, 0),
        Pin(1, "DUTY_IN", -35, 20),
    ],
    ComponentType.GAIN: _default_unary_block_pins(),
    ComponentType.SUM: _default_sum_pins(2),
    ComponentType.SUBTRACTOR: _default_sum_pins(2),
    ComponentType.CONSTANT: [Pin(0, "OUT", 40, 0)],

    # Control blocks - signal processing
    ComponentType.INTEGRATOR: [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)],
    ComponentType.DIFFERENTIATOR: [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)],
    ComponentType.LIMITER: [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)],
    ComponentType.RATE_LIMITER: [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)],
    ComponentType.HYSTERESIS: [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)],

    # Control blocks - advanced
    ComponentType.LOOKUP_TABLE: [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)],
    ComponentType.TRANSFER_FUNCTION: [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)],
    ComponentType.DELAY_BLOCK: [Pin(0, "IN", -35, 0), Pin(1, "OUT", 35, 0)],
    ComponentType.SAMPLE_HOLD: [
        Pin(0, "IN", -35, -10),
        Pin(1, "TRIG", -35, 10),
        Pin(2, "OUT", 35, 0),
    ],
    ComponentType.STATE_MACHINE: [
        Pin(0, "IN1", -35, -12),
        Pin(1, "IN2", -35, 12),
        Pin(2, "OUT", 35, 0),
    ],
    ComponentType.C_BLOCK: _default_c_block_pins(1, 1),

    # Measurement
    ComponentType.VOLTAGE_PROBE: [
        Pin(0, "+", 0, -20),
        Pin(1, "-", 0, 20),
        Pin(2, VOLTAGE_PROBE_OUTPUT_PIN_NAME, 25, 0),
    ],
    ComponentType.VOLTAGE_PROBE_GND: [
        Pin(0, "IN", -25, 0),
        Pin(1, VOLTAGE_PROBE_OUTPUT_PIN_NAME, 25, 0),
    ],
    ComponentType.CURRENT_PROBE: [
        Pin(0, "IN", -20, 0),
        Pin(1, "OUT", 20, 0),
        Pin(2, CURRENT_PROBE_OUTPUT_PIN_NAME, 0, -20),
    ],
    ComponentType.POWER_PROBE: [
        Pin(0, "V+", -25, -15),
        Pin(1, "V-", -25, 15),
        Pin(2, "I+", 25, -15),
        Pin(3, "I-", 25, 15),
    ],

    # Scopes
    ComponentType.ELECTRICAL_SCOPE: _default_scope_pins(2),
    ComponentType.THERMAL_SCOPE: _default_scope_pins(2),

    # Signal routing
    ComponentType.SIGNAL_MUX: _default_mux_pins(4),
    ComponentType.SIGNAL_DEMUX: _default_demux_pins(4),
    ComponentType.GOTO_LABEL: [Pin(0, "NET", -40, 0)],
    ComponentType.FROM_LABEL: [Pin(0, "NET", 40, 0)],

    # Magnetic
    ComponentType.SATURABLE_INDUCTOR: [Pin(0, "1", -30, 0), Pin(1, "2", 30, 0)],
    ComponentType.COUPLED_INDUCTOR: [
        Pin(0, "L1_1", -30, -15),
        Pin(1, "L1_2", -30, 15),
        Pin(2, "L2_1", 30, -15),
        Pin(3, "L2_2", 30, 15),
    ],

    # Pre-configured networks
    ComponentType.SNUBBER_RC: [Pin(0, "1", -25, 0), Pin(1, "2", 25, 0)],

    # Three-phase / vector control (Pulsim Phase 28)
    # Clarke (abc → αβγ): 3 inputs + 3 channel outputs (channels via metadata)
    ComponentType.CLARKE_TRANSFORM: [
        Pin(0, "A", -35, -20),
        Pin(1, "B", -35, 0),
        Pin(2, "C", -35, 20),
        Pin(3, "ALPHA", 35, -20),
        Pin(4, "BETA", 35, 0),
        Pin(5, "GAMMA", 35, 20),
    ],
    ComponentType.INVERSE_CLARKE_TRANSFORM: [
        Pin(0, "ALPHA", -35, -20),
        Pin(1, "BETA", -35, 0),
        Pin(2, "GAMMA", -35, 20),
        Pin(3, "A", 35, -20),
        Pin(4, "B", 35, 0),
        Pin(5, "C", 35, 20),
    ],
    # Park (αβ + θ → dq): nodes [alpha, beta], θ via metadata
    ComponentType.PARK_TRANSFORM: [
        Pin(0, "ALPHA", -35, -15),
        Pin(1, "BETA", -35, 15),
        Pin(2, "D", 35, -15),
        Pin(3, "Q", 35, 15),
    ],
    ComponentType.INVERSE_PARK_TRANSFORM: [
        Pin(0, "D", -35, -15),
        Pin(1, "Q", -35, 15),
        Pin(2, "ALPHA", 35, -15),
        Pin(3, "BETA", 35, 15),
    ],
    # Single-phase PLL: 1 input → θ, ω, lock_error channels
    ComponentType.PLL: [
        Pin(0, "IN", -35, 0),
        Pin(1, "THETA", 35, -15),
        Pin(2, "OMEGA", 35, 0),
        Pin(3, "ERR", 35, 15),
    ],
    # SVM (αβ → 3 duties)
    ComponentType.SVM: [
        Pin(0, "ALPHA", -35, -15),
        Pin(1, "BETA", -35, 15),
        Pin(2, "DA", 35, -20),
        Pin(3, "DB", 35, 0),
        Pin(4, "DC", 35, 20),
    ],

    # Three-phase grid source (pulsim>=0.10.0a1).
    # 4 pins: A, B, C, Neutral. The runtime decomposes this into 3 internal
    # SineVoltageSource branches sharing the neutral.
    ComponentType.THREE_PHASE_SOURCE: [
        Pin(0, "A", 30, -25),
        Pin(1, "B", 30, 0),
        Pin(2, "C", 30, 25),
        Pin(3, "N", -30, 0),
    ],

    # DC Motor (pulsim>=0.10.0a2). 2-terminal armature device with internal
    # mechanical state (ω, θ). Pulsim's runtime reserves one branch row for
    # the armature current and advances ω, θ each accepted timestep.
    ComponentType.DC_MOTOR: [
        Pin(0, "A+", -30, 0),
        Pin(1, "A-", 30, 0),
    ],

    # 3-phase RL load (pulsim>=0.10.0a3). 4 pins: A, B, C, Neutral.
    # The runtime decomposes into R+L series branches (Y or Δ topology).
    ComponentType.THREE_PHASE_RL_LOAD: [
        Pin(0, "A", -30, -25),
        Pin(1, "B", -30, 0),
        Pin(2, "C", -30, 25),
        Pin(3, "N", 30, 0),
    ],

    # PMSM (pulsim>=0.10.0a3). 4 pins: A, B, C, Neutral. Decomposes into
    # 3 phases of R_s + L_s + sinusoidal back-EMF source.
    ComponentType.PMSM_STEADY_STATE: [
        Pin(0, "A", -30, -25),
        Pin(1, "B", -30, 0),
        Pin(2, "C", -30, 25),
        Pin(3, "N", 30, 0),
    ],
}


def _normalize_default_pin_map() -> None:
    """Normalize every default pin layout to the global pin grid."""
    for comp_type, pins in list(DEFAULT_PINS.items()):
        DEFAULT_PINS[comp_type] = _snap_pin_layout(pins)


_normalize_default_pin_map()


DEFAULT_THERMAL_DEVICE_PARAMS: dict[str, Any] = {
    "thermal_enabled": True,
    "thermal_network": "single_rc",
    "thermal_rth": 1.0,
    "thermal_cth": 0.1,
    "thermal_rth_stages": "",
    "thermal_cth_stages": "",
    "thermal_temp_init": 25.0,
    "thermal_temp_ref": 25.0,
    "thermal_alpha": 0.004,
    "thermal_shared_sink_id": "",
    "thermal_shared_sink_rth": 0.0,
    "thermal_shared_sink_cth": 0.0,
}

DEFAULT_SWITCHING_ENERGY_PARAMS: dict[str, Any] = {
    "switching_loss_model": "scalar",
    "switching_eon_j": 0.0,
    "switching_eoff_j": 0.0,
    "switching_err_j": 0.0,
    "switching_loss_axes_current": "",
    "switching_loss_axes_voltage": "",
    "switching_loss_axes_temperature": "",
    "switching_loss_eon_table": "",
    "switching_loss_eoff_table": "",
    "switching_loss_err_table": "",
}


# Default parameter templates for each component type
DEFAULT_PARAMETERS: dict[ComponentType, dict[str, Any]] = {
    # Basic passive
    ComponentType.RESISTOR: {"resistance": 1000.0},
    ComponentType.CAPACITOR: {"capacitance": 1e-6, "initial_voltage": 0.0},
    ComponentType.INDUCTOR: {"inductance": 1e-3, "initial_current": 0.0},

    # Sources
    ComponentType.VOLTAGE_SOURCE: {"waveform": {"type": "dc", "value": 5.0}},
    ComponentType.CURRENT_SOURCE: {"waveform": {"type": "dc", "value": 1.0}},
    ComponentType.GROUND: {},

    # Diodes
    ComponentType.DIODE: {
        "is_": 1e-14,
        "n": 1.0,
        "rs": 0.0,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.ZENER_DIODE: {
        "vz": 5.1,
        "iz_test": 0.02,
        "zz": 5.0,
        "is_": 1e-14,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.LED: {
        "vf": 2.0,
        "color": "red",
        "wavelength": 620,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },

    # Transistors
    ComponentType.MOSFET_N: {
        "vth": 2.0,
        "kp": 0.1,
        "lambda_": 0.0,
        "g_off": 1e-9,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.MOSFET_P: {
        "vth": -2.0,
        "kp": 0.1,
        "lambda_": 0.0,
        "g_off": 1e-9,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.IGBT: {
        "vth": 3.0,
        "g_on": 1e4,
        "g_off": 1e-9,
        "v_ce_sat": 2.0,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.BJT_NPN: {
        "beta": 100.0,
        "vbe_sat": 0.7,
        "vce_sat": 0.2,
        "is_": 1e-14,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.BJT_PNP: {
        "beta": 100.0,
        "vbe_sat": -0.7,
        "vce_sat": -0.2,
        "is_": 1e-14,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.THYRISTOR: {
        "vgt": 1.0,
        "igt": 0.03,
        "holding_current": 0.05,
        "vf": 1.5,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.TRIAC: {
        "vgt": 1.5,
        "igt": 0.05,
        "holding_current": 0.05,
        "vf": 1.5,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },

    # Switching
    ComponentType.SWITCH: {
        "ron": 0.001,
        "roff": 1e9,
        "initial_state": False,
        **DEFAULT_SWITCHING_ENERGY_PARAMS,
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },

    # Transformer
    ComponentType.TRANSFORMER: {"turns_ratio": 1.0, "lm": 1e-3},

    # Analog
    ComponentType.OP_AMP: {
        "open_loop_gain": 1e5,
        "gbw": 1e6,
        "slew_rate": 1e6,
        "offset": 0.0,
        "rail_low": -15.0,
        "rail_high": 15.0,
        "rail_to_rail": False,
    },
    ComponentType.COMPARATOR: {
        "threshold": 0.0,
        "hysteresis": 0.0,
        "high": 1.0,
        "low": 0.0,
    },

    # Protection
    ComponentType.RELAY: {
        "coil_voltage": 12.0,
        "coil_resistance": 400.0,
        "contact_rating": 10.0,
        "ron": 0.01,
        "roff": 1e9,
    },
    ComponentType.FUSE: {
        "rating": 1.0,
        "blow_i2t": 1.0,
    },
    ComponentType.CIRCUIT_BREAKER: {
        "trip_current": 10.0,
        "trip_time": 0.01,
        "ron": 0.001,
    },

    # Control blocks - basic
    ComponentType.PI_CONTROLLER: {
        "kp": 1.0,
        "ki": 100.0,
        "output_min": -1.0,
        "output_max": 1.0,
        "anti_windup": True,
        "sample_time": 0.0,
    },
    ComponentType.PID_CONTROLLER: {
        "kp": 1.0,
        "ki": 100.0,
        "kd": 0.01,
        "output_min": -1.0,
        "output_max": 1.0,
        "anti_windup": True,
        "sample_time": 0.0,
    },
    ComponentType.MATH_BLOCK: {
        "operation": "sum",
        "gain": 1.0,
        "sample_time": 0.0,
    },
    ComponentType.PWM_GENERATOR: {
        "frequency": 10000.0,
        "duty_cycle": 0.5,
        "carrier": "sawtooth",
        "amplitude": 20.0,
        "sample_time": 0.0,
        DUTY_INPUT_PARAMETER: False,
    },
    ComponentType.GAIN: {
        "gain": 1.0,
        "sample_time": 0.0,
    },
    ComponentType.SUM: {
        "input_count": 2,
        "signs": ["+", "+"],
        "sample_time": 0.0,
    },
    ComponentType.SUBTRACTOR: {
        "input_count": 2,
        "signs": ["+", "-"],
        "sample_time": 0.0,
    },
    ComponentType.CONSTANT: {
        "value": 0.0,
        "sample_time": 0.0,
    },

    # Control blocks - signal processing
    ComponentType.INTEGRATOR: {
        "gain": 1.0,
        "initial_value": 0.0,
        "output_min": -1e6,
        "output_max": 1e6,
        "sample_time": 0.0,
    },
    ComponentType.DIFFERENTIATOR: {
        "gain": 1.0,
        "alpha": 0.0,
        "sample_time": 0.0,
    },
    ComponentType.LIMITER: {
        "output_min": -1.0,
        "output_max": 1.0,
        "sample_time": 0.0,
    },
    ComponentType.RATE_LIMITER: {
        "rising_rate": 1e6,
        "falling_rate": -1e6,
        "sample_time": 0.0,
    },
    ComponentType.HYSTERESIS: {
        "threshold": 0.0,
        "hysteresis": 1.0,
        "high": 1.0,
        "low": 0.0,
        "sample_time": 0.0,
    },

    # Control blocks - advanced
    ComponentType.LOOKUP_TABLE: {
        "table_x": [0.0, 0.5, 1.0],
        "table_y": [0.0, 0.25, 1.0],
        "interpolation": "linear",
        "sample_time": 0.0,
    },
    ComponentType.TRANSFER_FUNCTION: {
        "numerator": [1.0],
        "denominator": [1.0, 1.0],
        "sample_time": 0.0,
    },
    ComponentType.DELAY_BLOCK: {
        "delay_time": 1e-3,
        "sample_time": 0.0,
    },
    ComponentType.SAMPLE_HOLD: {
        "sample_time": 0.0,
    },
    ComponentType.STATE_MACHINE: {
        "states": ["S0", "S1"],
        "initial_state": "S0",
        "transitions": [],
        "sample_time": 0.0,
    },
    ComponentType.C_BLOCK: {
        "n_inputs": 1,
        "n_outputs": 1,
        "implementation": "source",
        "source": "",
        "lib_path": "",
        "source_code": "",
        "extra_cflags": [],
        "sample_time": 0.0,
    },

    # Measurement
    ComponentType.VOLTAGE_PROBE: {
        "display_name": "V",
        "scale": 1.0,
    },
    ComponentType.VOLTAGE_PROBE_GND: {
        "display_name": "Vg",
        "scale": 1.0,
    },
    ComponentType.CURRENT_PROBE: {
        "display_name": "I",
        "scale": 1.0,
    },
    ComponentType.POWER_PROBE: {
        "display_name": "P",
        "scale": 1.0,
    },

    # Scopes
    ComponentType.ELECTRICAL_SCOPE: {
        "channel_count": 2,
        "channels": [
            {"label": "CH1", "overlay": False},
            {"label": "CH2", "overlay": False},
        ],
    },
    ComponentType.THERMAL_SCOPE: {
        "channel_count": 2,
        "channels": [
            {"label": "T1", "overlay": False},
            {"label": "T2", "overlay": False},
        ],
    },

    # Signal routing
    ComponentType.SIGNAL_MUX: {
        "input_count": 4,
        "channel_labels": ["Ch1", "Ch2", "Ch3", "Ch4"],
        "ordering": [0, 1, 2, 3],
        "sample_time": 0.0,
    },
    ComponentType.SIGNAL_DEMUX: {
        "output_count": 4,
        "channel_labels": ["Ch1", "Ch2", "Ch3", "Ch4"],
        "ordering": [0, 1, 2, 3],
        "sample_time": 0.0,
    },
    ComponentType.GOTO_LABEL: {
        "net_label": "NET1",
    },
    ComponentType.FROM_LABEL: {
        "net_label": "NET1",
    },

    # Magnetic
    ComponentType.SATURABLE_INDUCTOR: {
        "inductance": 1e-3,
        # Saturation model
        "saturation_current": 10.0,
        "saturation_inductance": 1e-6,
        "saturation_exponent": 2.0,
        # Magnetic core config (pulsimcore v0.7.9+)
        "magnetic_core_enabled": True,
        "magnetic_core_model": "saturation",
        "magnetic_core_loss_policy": "telemetry_only",
        "core_loss_k": 0.0,
        "core_loss_alpha": 2.0,
        "core_loss_freq_coeff": 0.0,
        "i_equiv_init": 0.0,
        "hysteresis_band": 0.0,
        "hysteresis_strength": 0.15,
        "hysteresis_loss_coeff": 0.2,
        "hysteresis_state_init": 1.0,
    },
    ComponentType.COUPLED_INDUCTOR: {
        "l1": 1e-3,
        "l2": 1e-3,
        "mutual_inductance": 0.9e-3,
        "coupling_coefficient": 0.9,
    },

    # Pre-configured networks
    ComponentType.SNUBBER_RC: {
        "resistance": 100.0,
        "capacitance": 100e-9,
    },

    # Three-phase / vector control (Pulsim Phase 28)
    # Clarke / inverse-Clarke have no numeric parameters.
    ComponentType.CLARKE_TRANSFORM: {
        "sample_time": 0.0,
    },
    ComponentType.INVERSE_CLARKE_TRANSFORM: {
        "sample_time": 0.0,
    },
    # Park reads θ (and optionally α / β) from a channel — set via
    # the parameters panel: "theta_from_channel: PLL.theta", etc.
    ComponentType.PARK_TRANSFORM: {
        "theta_from_channel": "",
        "alpha_from_channel": "",
        "beta_from_channel": "",
        "sample_time": 0.0,
    },
    ComponentType.INVERSE_PARK_TRANSFORM: {
        "theta_from_channel": "",
        "d_from_channel": "",
        "q_from_channel": "",
        "sample_time": 0.0,
    },
    # Single-phase PLL: PI loop on q-axis projection.
    ComponentType.PLL: {
        "kp": 200.0,
        "ki": 2000.0,
        "f_nominal_hz": 60.0,
        "sample_time": 0.0,
    },
    # Space-Vector Modulation: takes (α, β) refs (channel) + V_dc.
    ComponentType.SVM: {
        "v_dc": 200.0,
        "alpha_from_channel": "",
        "beta_from_channel": "",
        "sample_time": 0.0,
    },
    # Three-phase voltage source (Pulsim 0.10.0a1).
    # Decomposes into 3 internal SineVoltageSource branches sharing
    # the neutral pin. ``positive_sequence`` flips B/C; ``unbalance_factor``
    # in [0, 1) scales |V_b|=(1-u) and |V_c|=(1+u) keeping A at nominal.
    ComponentType.THREE_PHASE_SOURCE: {
        "line_to_line_voltage_rms": 400.0,
        "frequency_hz": 50.0,
        "phase_a_deg": 0.0,
        "positive_sequence": True,
        "unbalance_factor": 0.0,
    },
    # DC Motor (Pulsim 0.10.0a2). Full device-variant — runtime advances
    # ω and θ internally; user only needs to wire the armature terminals.
    # Defaults match the analytical small-motor example used in Pulsim's
    # examples/cpp/02_dc_motor_step.cpp.
    ComponentType.DC_MOTOR: {
        "R_a": 0.5,           # Ω — armature resistance
        "L_a": 10e-3,         # H — armature inductance
        "K_e": 0.05,          # V·s/rad — back-EMF constant
        "K_t": 0.05,          # N·m/A — torque constant (= K_e in SI)
        "J":   1e-4,          # kg·m² — rotor inertia
        "b":   1e-5,          # N·m·s — viscous friction (linear in ω)
        "tau_load_quad_coeff": 0.0,  # N·m·s² — quadratic load (fan/pump)
        "i_a_init":   0.0,    # A — initial armature current
        "omega_init": 0.0,    # rad/s — initial speed
        "theta_init": 0.0,    # rad — initial rotor angle
        "tau_load":   0.0,    # N·m — external load torque (constant)
    },

    # 3-phase RL load (Pulsim 0.10.0a3). Decomposes into 3 R+L branches
    # in Star (Y) or Delta (Δ) topology.
    ComponentType.THREE_PHASE_RL_LOAD: {
        "resistance_per_phase": 30.0,    # Ω
        "inductance_per_phase": 50e-3,   # H
        "topology": "Star",              # "Star" or "Delta"
        "unbalance_factor": 0.0,         # [0, 1)
    },

    # PMSM at fixed rotor speed (Pulsim 0.10.0a3). Per-phase R_s + L_s +
    # sinusoidal back-EMF (amplitude = ω_e · λ_pm).
    ComponentType.PMSM_STEADY_STATE: {
        "R_s": 0.5,                      # Ω — stator phase resistance
        "L_s": 2e-3,                     # H — stator phase inductance
        "lambda_pm": 0.1,                # V·s/rad — rotor flux linkage
        "omega_electrical": 314.16,      # rad/s — fixed electrical speed (~50 Hz)
        "phase_a_offset_deg": 0.0,       # rotor angle offset
        "positive_sequence": True,       # False flips B/C
    },
}

# Parameters that are intentionally hidden from the default properties UI.
# They keep their default values unless the user edits the .pulsim file directly.
# RATIONALE - PWM amplitude: all supported switching devices (MOSFET, IGBT,
# VoltageControlledSwitch) operate correctly with the 20 V default. Exposing
# the amplitude invites users to lower it below the device threshold, breaking
# simulation convergence without obvious explanation.
HIDDEN_PARAMS: dict[ComponentType, frozenset[str]] = {
    ComponentType.PWM_GENERATOR: frozenset({"amplitude", "duty_from_channel", "target_component"}),
}

# Maps string parameter names to their allowed values.
# The properties panel renders these as dropdowns instead of free-text fields.
PARAM_OPTIONS: dict[str, list[str]] = {
    # Magnetic core (SATURABLE_INDUCTOR)
    "magnetic_core_model": ["saturation", "hysteresis"],
    "magnetic_core_loss_policy": ["telemetry_only", "loss_summary"],
    # PWM carrier waveform
    "carrier": ["sawtooth", "triangle"],
    # LED body color (drives schematic rendering)
    "color": ["red", "green", "blue", "yellow", "white"],
    # Electrothermal: RC network topology
    "thermal_network": ["single_rc", "foster", "cauer"],
    # Switching loss computation model
    "switching_loss_model": ["scalar", "datasheet"],
}


@dataclass
class Component:
    """A circuit component with position, parameters, and connections."""

    id: UUID = field(default_factory=uuid4)
    type: ComponentType = ComponentType.RESISTOR
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: int = 0  # Degrees, multiples of 90
    mirrored_h: bool = False
    mirrored_v: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)
    pins: list[Pin] = field(default_factory=list)

    def __post_init__(self):
        """Initialize default pins and parameters if not provided."""
        if not self.pins and self.type in DEFAULT_PINS:
            self.pins = [
                Pin(p.index, p.name, p.x, p.y) for p in DEFAULT_PINS[self.type]
            ]
        if not self.parameters and self.type in DEFAULT_PARAMETERS:
            self.parameters = deepcopy(DEFAULT_PARAMETERS[self.type])

        _synchronize_special_component(self)
        _snap_component_pins_to_grid(self)

    def get_pin_position(self, pin_index: int) -> tuple[float, float]:
        """Get absolute position of a pin, accounting for rotation and mirroring."""
        if pin_index >= len(self.pins):
            raise IndexError(f"Pin index {pin_index} out of range")

        pin = self.pins[pin_index]
        px, py = pin.x, pin.y

        # Apply mirroring
        if self.mirrored_h:
            px = -px
        if self.mirrored_v:
            py = -py

        # Apply rotation (in 90-degree increments)
        for _ in range((self.rotation // 90) % 4):
            px, py = -py, px

        return self.x + px, self.y + py

    def to_dict(self) -> dict:
        """Serialize component to dictionary."""
        return {
            "id": str(self.id),
            "type": self.type.name,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "rotation": self.rotation,
            "mirrored_h": self.mirrored_h,
            "mirrored_v": self.mirrored_v,
            "parameters": self.parameters,
            "pins": [p.to_dict() for p in self.pins],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Component":
        """Deserialize component from dictionary."""
        comp_type = ComponentType[data["type"]]
        if comp_type == ComponentType.SUBCIRCUIT:
            from pulsimgui.models.subcircuit import SubcircuitInstance

            return SubcircuitInstance.from_dict(data)

        return cls(
            id=UUID(data["id"]),
            type=comp_type,
            name=data["name"],
            x=data["x"],
            y=data["y"],
            rotation=data.get("rotation", 0),
            mirrored_h=data.get("mirrored_h", False),
            mirrored_v=data.get("mirrored_v", False),
            parameters=data.get("parameters", {}),
            pins=[Pin.from_dict(p) for p in data.get("pins", [])],
        )


SCOPE_CHANNEL_LIMITS = (1, 16)
MUX_CHANNEL_LIMITS = (2, 16)
SUM_INPUT_LIMITS = (2, 16)
C_BLOCK_IO_LIMITS = (1, 32)


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, value))


def _synchronize_control_sample_time(component: "Component") -> None:
    """Normalize Ts fields for components that support per-block sampling."""
    if not supports_control_sample_time(component.type):
        component.parameters.pop(CONTROL_SAMPLE_TIME_PARAM, None)
        component.parameters.pop(LEGACY_CONTROL_SAMPLE_TIME_PARAM, None)
        return

    sample_time = get_control_sample_time(component.parameters, default=0.0)
    set_control_sample_time(component.parameters, sample_time)


def _synchronize_special_component(component: Component) -> None:
    if component.type in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE):
        _synchronize_scope(component)
    elif component.type == ComponentType.SIGNAL_MUX:
        _synchronize_mux(component)
    elif component.type == ComponentType.SIGNAL_DEMUX:
        _synchronize_demux(component)
    elif component.type in (ComponentType.SUM, ComponentType.SUBTRACTOR):
        _synchronize_sum_like_block(component)
    elif component.type == ComponentType.C_BLOCK:
        _synchronize_c_block(component)
    elif component.type == ComponentType.PWM_GENERATOR:
        _synchronize_pwm_duty_pin(component)
    elif component.type in (
        ComponentType.PI_CONTROLLER,
        ComponentType.GAIN,
        ComponentType.GOTO_LABEL,
        ComponentType.FROM_LABEL,
    ):
        _synchronize_default_pin_layout(component)
    elif component.type in (
        ComponentType.VOLTAGE_PROBE,
        ComponentType.VOLTAGE_PROBE_GND,
        ComponentType.CURRENT_PROBE,
    ):
        _synchronize_measurement_probe_pins(component)
    else:
        _synchronize_thermal_port(component)

    _synchronize_control_sample_time(component)


def _synchronize_default_pin_layout(component: Component) -> None:
    """Synchronize components that always follow their default pin map."""
    default_pins = DEFAULT_PINS.get(component.type, [])
    if not default_pins:
        return
    if len(component.pins) == len(default_pins):
        names_match = all(component.pins[idx].name == default_pins[idx].name for idx in range(len(default_pins)))
        coords_match = all(
            abs(component.pins[idx].x - default_pins[idx].x) < 0.1
            and abs(component.pins[idx].y - default_pins[idx].y) < 0.1
            for idx in range(len(default_pins))
        )
        if names_match and coords_match:
            return
    component.pins = _snap_pin_layout([Pin(pin.index, pin.name, pin.x, pin.y) for pin in default_pins])


def _synchronize_measurement_probe_pins(component: Component) -> None:
    """Synchronize probe pin layout after schema changes."""
    default_pins = DEFAULT_PINS.get(component.type, [])
    if not default_pins:
        return
    if len(component.pins) == len(default_pins):
        names_match = all(component.pins[idx].name == default_pins[idx].name for idx in range(len(default_pins)))
        coords_match = all(
            abs(component.pins[idx].x - default_pins[idx].x) < 0.1
            and abs(component.pins[idx].y - default_pins[idx].y) < 0.1
            for idx in range(len(default_pins))
        )
        if names_match and coords_match:
            return
    component.pins = _snap_pin_layout([Pin(pin.index, pin.name, pin.x, pin.y) for pin in default_pins])


def _synchronize_sum_like_block(component: Component, force_count: int | None = None) -> None:
    """Synchronize SUM/SUBTRACTOR pin layout and signs list."""
    params = component.parameters
    requested = force_count or params.get("input_count") or 2
    input_count = _clamp(int(requested), *SUM_INPUT_LIMITS)
    params["input_count"] = input_count

    if component.type == ComponentType.SUBTRACTOR:
        default_signs = ["+"] + ["-"] * max(input_count - 1, 0)
    else:
        default_signs = ["+"] * input_count

    signs = list(params.get("signs") or [])
    if not signs:
        signs = default_signs
    while len(signs) < input_count:
        signs.append(default_signs[len(signs)])
    if len(signs) > input_count:
        del signs[input_count:]
    params["signs"] = signs

    component.pins = _snap_pin_layout(_default_sum_pins(input_count))


def _synchronize_c_block(
    component: Component,
    force_n_inputs: int | None = None,
    force_n_outputs: int | None = None,
) -> None:
    """Synchronize C-Block pin layout and ABI parameter defaults."""
    params = component.parameters
    requested_inputs = force_n_inputs if force_n_inputs is not None else params.get("n_inputs", 1)
    requested_outputs = (
        force_n_outputs if force_n_outputs is not None else params.get("n_outputs", 1)
    )
    try:
        n_inputs = _clamp(int(requested_inputs), *C_BLOCK_IO_LIMITS)
    except (TypeError, ValueError):
        n_inputs = 1
    try:
        n_outputs = _clamp(int(requested_outputs), *C_BLOCK_IO_LIMITS)
    except (TypeError, ValueError):
        n_outputs = 1

    params["n_inputs"] = n_inputs
    params["n_outputs"] = n_outputs
    params.setdefault("implementation", "source")
    params.setdefault("source", "")
    params.setdefault("lib_path", "")
    params.setdefault("source_code", "")

    raw_flags = params.get("extra_cflags", [])
    if isinstance(raw_flags, list):
        params["extra_cflags"] = [str(flag) for flag in raw_flags if str(flag).strip()]
    else:
        params["extra_cflags"] = []

    component.pins = _snap_pin_layout(_default_c_block_pins(n_inputs, n_outputs))


def _synchronize_pwm_duty_pin(component: Component) -> None:
    """Synchronize the optional DUTY_IN pin on PWM_GENERATOR.

    When *enable_duty_input* is False (default) the DUTY_IN pin is hidden and
    the fixed *duty_cycle* parameter is used by the simulator.  When True the
    pin is visible and the converter wires the connected signal as the duty
    source; leaving it unconnected will raise a validation error at simulation
    time.
    """
    if component.type != ComponentType.PWM_GENERATOR:
        return

    # Backward-compat: infer enabled state from serialised pin list when the
    # parameter is absent (e.g. files saved before this feature existed).
    serialized_has_duty_pin = any(pin.name == DUTY_INPUT_PIN_NAME for pin in component.pins)
    raw_enabled = component.parameters.get(DUTY_INPUT_PARAMETER, None)
    if raw_enabled is None and serialized_has_duty_pin:
        enabled = True
    else:
        enabled = bool(raw_enabled)
    component.parameters[DUTY_INPUT_PARAMETER] = enabled

    # Rebuild pin list: always keep OUT, conditionally keep DUTY_IN.
    pins = [Pin(pin.index, pin.name, pin.x, pin.y) for pin in component.pins if pin.name != DUTY_INPUT_PIN_NAME]
    if not pins:
        # Fallback: restore OUT from defaults if lost somehow.
        base = DEFAULT_PINS.get(ComponentType.PWM_GENERATOR, [])
        pins = [Pin(p.index, p.name, p.x, p.y) for p in base if p.name != DUTY_INPUT_PIN_NAME]

    if enabled:
        pins.append(Pin(index=len(pins), name=DUTY_INPUT_PIN_NAME, x=-35.0, y=20.0))

    for index, pin in enumerate(pins):
        pin.index = index
    component.pins = _snap_pin_layout(pins)


def _synchronize_thermal_port(component: Component) -> None:
    """Synchronize optional thermal measurement pin on supported components."""
    if not supports_thermal_port(component.type):
        component.parameters.pop(THERMAL_PORT_PARAMETER, None)
        return

    serialized_has_thermal_pin = any(pin.name == THERMAL_PORT_PIN_NAME for pin in component.pins)
    raw_enabled = component.parameters.get(THERMAL_PORT_PARAMETER, None)
    if raw_enabled is None and serialized_has_thermal_pin:
        enabled = True
    else:
        enabled = bool(raw_enabled)
    component.parameters[THERMAL_PORT_PARAMETER] = enabled

    thermal_active = bool(component.parameters.get("thermal_enabled", False) or enabled)
    if supports_electrothermal_parameters(component.type) and thermal_active:
        for key, default in DEFAULT_THERMAL_DEVICE_PARAMS.items():
            component.parameters.setdefault(key, default)

    base_pins = DEFAULT_PINS.get(component.type, [])
    if not base_pins:
        return

    # Keep the current electrical pin map stable and reserve TH as optional last pin.
    # This preserves extended pin layouts (for example, a controlled switch with 3 pins).
    pins = [Pin(pin.index, pin.name, pin.x, pin.y) for pin in component.pins if pin.name != THERMAL_PORT_PIN_NAME]
    if len(pins) < len(base_pins):
        pins = [Pin(pin.index, pin.name, pin.x, pin.y) for pin in base_pins]

    if enabled:
        pins.append(Pin(index=len(pins), name=THERMAL_PORT_PIN_NAME, x=0.0, y=PIN_GRID_STEP))

    for index, pin in enumerate(pins):
        pin.index = index
    component.pins = _snap_pin_layout(pins)


def _synchronize_scope(component: Component, force_count: int | None = None) -> None:
    params = component.parameters
    requested = force_count or params.get("channel_count") or len(params.get("channels", [])) or 1
    channel_count = _clamp(int(requested), *SCOPE_CHANNEL_LIMITS)
    params["channel_count"] = channel_count

    channels = params.setdefault("channels", [])
    prefix = _scope_label_prefix(component.type)

    while len(channels) < channel_count:
        channels.append({"label": f"{prefix}{len(channels) + 1}", "overlay": False})
    if len(channels) > channel_count:
        del channels[channel_count:]

    for idx, channel in enumerate(channels):
        channel.setdefault("label", f"{prefix}{idx + 1}")
        channel.setdefault("overlay", False)

    component.pins = _snap_pin_layout(_default_scope_pins(channel_count))


def _synchronize_mux(component: Component, force_count: int | None = None) -> None:
    params = component.parameters
    requested = force_count or params.get("input_count") or len(params.get("channel_labels", [])) or 2
    input_count = _clamp(int(requested), *MUX_CHANNEL_LIMITS)
    params["input_count"] = input_count

    labels = params.setdefault("channel_labels", [])
    while len(labels) < input_count:
        labels.append(f"Ch{len(labels) + 1}")
    if len(labels) > input_count:
        del labels[input_count:]

    ordering = params.setdefault("ordering", list(range(input_count)))
    ordering = [int(idx) for idx in ordering[:input_count]]
    while len(ordering) < input_count:
        ordering.append(len(ordering))
    params["ordering"] = [
        max(0, min(input_count - 1, idx)) for idx in ordering
    ]

    component.pins = _snap_pin_layout(_default_mux_pins(input_count))


def _synchronize_demux(component: Component, force_count: int | None = None) -> None:
    params = component.parameters
    requested = force_count or params.get("output_count") or len(params.get("channel_labels", [])) or 2
    output_count = _clamp(int(requested), *MUX_CHANNEL_LIMITS)
    params["output_count"] = output_count

    labels = params.setdefault("channel_labels", [])
    while len(labels) < output_count:
        labels.append(f"Ch{len(labels) + 1}")
    if len(labels) > output_count:
        del labels[output_count:]

    ordering = params.setdefault("ordering", list(range(output_count)))
    ordering = [int(idx) for idx in ordering[:output_count]]
    while len(ordering) < output_count:
        ordering.append(len(ordering))
    params["ordering"] = [
        max(0, min(output_count - 1, idx)) for idx in ordering
    ]

    component.pins = _snap_pin_layout(_default_demux_pins(output_count))


def set_scope_channel_count(component: Component, count: int) -> None:
    """Update a scope component to use the provided channel count."""

    _synchronize_scope(component, force_count=count)


def set_mux_input_count(component: Component, count: int) -> None:
    """Update a mux component's input count and pin layout."""

    _synchronize_mux(component, force_count=count)


def set_demux_output_count(component: Component, count: int) -> None:
    """Update a demux component's output count and pin layout."""

    _synchronize_demux(component, force_count=count)


def set_sum_input_count(component: Component, count: int) -> None:
    """Update SUM/SUBTRACTOR input count and pin layout."""

    if component.type not in (ComponentType.SUM, ComponentType.SUBTRACTOR):
        return
    _synchronize_sum_like_block(component, force_count=count)


def set_cblock_io_counts(
    component: Component,
    *,
    n_inputs: int | None = None,
    n_outputs: int | None = None,
) -> None:
    """Update C-Block input/output counts and pin layout."""
    if component.type != ComponentType.C_BLOCK:
        return
    _synchronize_c_block(component, force_n_inputs=n_inputs, force_n_outputs=n_outputs)


def set_cblock_input_count(component: Component, count: int) -> None:
    """Update only C-Block input count."""
    set_cblock_io_counts(component, n_inputs=count)


def set_cblock_output_count(component: Component, count: int) -> None:
    """Update only C-Block output count."""
    set_cblock_io_counts(component, n_outputs=count)


def set_thermal_port_enabled(component: Component, enabled: bool) -> None:
    """Enable or disable thermal measurement pin for compatible components."""

    component.parameters[THERMAL_PORT_PARAMETER] = bool(enabled)
    _synchronize_special_component(component)


def set_pwm_duty_input_enabled(component: Component, enabled: bool) -> None:
    """Enable or disable the DUTY_IN port on a PWM_GENERATOR component.

    When disabled (default) the block uses the fixed *duty_cycle* parameter.
    When enabled the DUTY_IN pin appears on the schematic and the connected
    signal is used as the duty command; the simulation will reject the circuit
    if the pin is left unconnected.
    """

    component.parameters[DUTY_INPUT_PARAMETER] = bool(enabled)
    _synchronize_special_component(component)
