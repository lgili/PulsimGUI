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

    # Field-Oriented Control (FOC) drive controller for a 3-phase PMSM +
    # native VSI. Two visible signal-domain inputs (SP = speed-setpoint
    # reference, FB = motor feedback bus), with all the loop tuning knobs
    # (cascaded speed / d-q current PI gains, id reference, q-axis current
    # limit, voltage clamp, speed ramp) exposed as editable parameters.
    # The converter auto-detects the controlled VSI + observed PMSM by
    # tracing wires; the backend ``_build_foc_loops`` then closes the loops
    # over the PMSM observer bundle and drives the VSI switches via inverse
    # Park/Clarke, replacing the open-loop SPWM.
    FOC_CONTROLLER = auto()

    # Closed-loop PFC boost controller — cascaded outer voltage / inner
    # current PI loops with sine-modulated inner setpoint (CCM operation,
    # 240–1000 W range). Three signal-domain inputs:
    #   VBUS  — wire to a voltage probe on the bus capacitor (V_bus)
    #   IL    — wire to a current probe on the boost inductor (i_L)
    #   VAC   — wire to a voltage probe on the rectified AC line (|V_rect|)
    # Tunable parameters: voltage/current PI gains, V_bus target, V_rect
    # peak normalization, line and switching frequencies, duty clamp. The
    # converter auto-detects the boost MOSFET by topology, and the backend
    # ``_build_pfc_loops`` closes the loops via pulsim's ``bind_pi_to_switch``
    # (inner current loop) plus a step-observer (outer voltage loop).
    PFC_BOOST_CONTROLLER = auto()

    # Closed-loop 6-step (trapezoidal / 120°) BLDC drive. Two signal-
    # domain inputs (same shape as FOC_CONTROLLER) so the user can drop
    # this in place of the FOC block on the same PMSM + VSI topology and
    # see the difference in current shape / torque ripple / acoustic
    # noise that 6-step produces vs. FOC:
    #   SP — speed setpoint in rpm (typically wired to a CONSTANT)
    #   FB — feedback from the PMSM signal bus (auto-detects the
    #        observer/VSI pair via the SIG net trace)
    # The backend ``_build_sixstep_loops`` runs an outer rpm PI to
    # produce a duty cycle, sectorises the rotor electrical angle into
    # 6 commutation states, and drives the matching pair of VSI
    # switches via a complementary mask — modulating only the high-side
    # of the active phase pair with the PI's duty. Sensorless emulation
    # is approximated from the observer-bundle's electrical angle (full
    # BEMF-zero-crossing ZCD with a Kalman observer is a follow-up).
    SIXSTEP_CONTROLLER = auto()

    # Coupled-thermal model (pulsim 1.7): a single heatsink shared by N
    # devices. Each device's TH (thermal port) pin wires to one of this
    # component's device slots; the converter emits a descriptor that
    # the backend hands to ``pulsim.thermal.add_shared_heatsink`` +
    # ``make_heatsink_observer``. Per-device junction temperature
    # ``T_j(t)`` then reflects the COUPLED steady state — adding a
    # hotter device next to a cooler one raises both, exactly as in a
    # real assembly. Without this, each device's thermal port goes to
    # its own isolated ambient and the steady state under-predicts by
    # the missing ``Σ Pᵢ · R_th_sa`` term.
    HEATSINK = auto()

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

    # Hierarchical schematic port marker.
    # Placed inside a SubcircuitDefinition's body to declare a named
    # input/output that surfaces on the outer SubcircuitInstance pin.
    # Not a real device — flattening bridges its connected net to the
    # external net of the matching port name.
    SUBCIRCUIT_PORT = auto()

    # Magnetic
    SATURABLE_INDUCTOR = auto()
    COUPLED_INDUCTOR = auto()
    # Jiles-Atherton hysteretic inductor (pulsim 1.5+:
    # pulsim.add_hysteretic_inductor + a step-observer that modulates
    # an internal dummy source to encode N·A·µ₀·dM/dt).
    HYSTERETIC_INDUCTOR = auto()

    # Three-phase / vector control (Pulsim Phase 28)
    CLARKE_TRANSFORM = auto()
    INVERSE_CLARKE_TRANSFORM = auto()
    PARK_TRANSFORM = auto()
    INVERSE_PARK_TRANSFORM = auto()
    PLL = auto()
    SVM = auto()

    # Three-phase grid source (Pulsim 0.10.0a1+: Circuit::add_three_phase_source)
    THREE_PHASE_SOURCE = auto()

    # Three-phase 2-level VSI helper (Pulsim 0.10.0a5+: 6 MOSFETs + 6 SPWM
    # gates packaged into a single drop-in inverter component).
    THREE_PHASE_VSI = auto()

    # Motors (Pulsim 0.10.0a2+: full device-variant integration)
    DC_MOTOR = auto()

    # 3-phase RL load (Pulsim 0.10.0a3+: Y/Δ topology, balanced/unbalanced)
    THREE_PHASE_RL_LOAD = auto()

    # PMSM at fixed rotor speed (Pulsim 0.10.0a3+: R_s + L_s + back-EMF per phase)
    PMSM_STEADY_STATE = auto()

    # PMSM dynamic device-variant (Pulsim 0.10.0a4+: 4 internal states —
    # i_d, i_q, ω_m, θ_m — with mechanical inertia and torque feedback).
    PMSM = auto()

    # 3-phase squirrel-cage induction motor (pulsim 1.5+:
    # pulsim.add_induction_motor — 5-state Krause αβ model + a
    # step-observer driving per-phase back-EMF sources).
    INDUCTION_MOTOR = auto()

    # Pre-configured networks
    SNUBBER_RC = auto()

    # Diode bridges — composite rectifiers that the circuit_converter
    # expands into individual ``add_diode`` calls. The kernel has no
    # native ``add_diode_bridge``; we package them GUI-side so users
    # don't have to wire 4-6 diodes by hand.
    SINGLE_PHASE_DIODE_BRIDGE = auto()  # 4 diodes, AC+/AC- → DC+/DC-
    THREE_PHASE_DIODE_BRIDGE = auto()   # 6 diodes, A/B/C → DC+/DC-

    # MMC (Modular Multilevel Converter) submodule cell.
    # A single ComponentType handles both half-bridge (2 switches, 4 pins)
    # and full-bridge (4 switches, 6 pins) topologies — selected via the
    # ``cell_topology`` parameter. The circuit_converter expands the cell
    # into MOSFETs (with body diodes) + 1 capacitor.
    MMC_CELL = auto()

    # MMC arm — a chain of N sub-module cells modeled at a selectable
    # fidelity level (L0 average / L1 multilevel / L2 SM-equivalent /
    # L3 detailed). Maps to pulsim's native ``add_mmc_arm_*`` family.
    # Represents a WHOLE arm (TOP → BOT) — for a 3-phase MMC you'd
    # instantiate 6 arms (upper + lower per phase).
    MMC_ARM = auto()
    # Dedicated 3-phase MMC modulation controller. Computes six arm
    # modulation references (m_a/m_b/m_c, 120° apart, upper + lower per
    # phase) and drives the six MMC_ARM ``M_REF`` pins. Open-loop
    # sinusoidal today; closed-loop (output-current dq + circulating-
    # current suppression) layers onto the same block later.
    MMC_CONTROLLER = auto()

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
    for index, pin in enumerate(_generate_stacked_pins(input_count, -40, "IN", start_index=0)):
        pin.index = index
        pin.name = f"IN{index}"
        pins.append(pin)

    if output_count == 1:
        pins.append(Pin(len(pins), "OUT", 40, 0))
    else:
        out_pins = _generate_stacked_pins(output_count, 40, "OUT", start_index=len(pins))
        for out_index, pin in enumerate(out_pins):
            pin.name = f"OUT{out_index}"
            pins.append(pin)

    return pins


def _default_unary_block_pins() -> list[Pin]:
    """Create IN/OUT pin pair for unary signal blocks."""
    return [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)]


def _default_sum_pins(input_count: int) -> list[Pin]:
    """Create stacked input pins plus single output pin for sum/sub blocks."""
    pins = _generate_stacked_pins(input_count, -40, "IN")
    pins.append(Pin(len(pins), "OUT", 40, 0))
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

# Dynamic-machine signal bus. A single signal-domain output pin that carries
# all of the motor's observable traces (rotor speed, per-phase + d/q currents,
# torque). The user wires it to a SIGNAL_DEMUX to split the bus into the
# individual channels and connect those to a scope. The CHANNEL ORDER below is
# the demux lane order, and each suffix matches the key the backend publishes
# in ``_merge_motor_observer_signals`` (``<motor>.speed_rpm`` etc.).
MOTOR_SIGNAL_BUS_PIN_NAME = "SIG"
MOTOR_SIGNAL_BUS_CHANNELS: tuple[tuple[str, str], ...] = (
    ("speed_rpm", "Speed (rpm)"),
    ("i_a", "i_a"),
    ("i_b", "i_b"),
    ("i_c", "i_c"),
    ("i_d", "i_d"),
    ("i_q", "i_q"),
    ("torque", "Torque (N·m)"),
)
MOTOR_SIGNAL_BUS_SUPPORTED_TYPES: set[ComponentType] = {
    ComponentType.PMSM,
}


def supports_motor_signal_bus(component_type: ComponentType) -> bool:
    """Return True when a component exposes a dynamic-machine signal bus pin."""
    return component_type in MOTOR_SIGNAL_BUS_SUPPORTED_TYPES


# Inverter PWM bus — a single signal-domain pin carrying the 6 PWM gate
# signals (3 high-side + 3 low-side) for a native 3φ VSI. The wire from
# the controller (FOC_CONTROLLER / SIXSTEP_CONTROLLER) to the VSI's
# ``PWM`` input pin is the SOLE binding between them — the converter
# uses the wire to identify which inverter the controller drives. No
# parameter-based ``vsi_name`` fallback: a missing wire is a converter
# error so the user always sees the binding on the schematic.
INVERTER_PWM_BUS_PIN_NAME = "PWM"
INVERTER_PWM_BUS_CHANNELS: tuple[tuple[str, str], ...] = (
    ("ha", "A high-side"),
    ("la", "A low-side"),
    ("hb", "B high-side"),
    ("lb", "B low-side"),
    ("hc", "C high-side"),
    ("lc", "C low-side"),
)
INVERTER_PWM_BUS_INPUT_SUPPORTED_TYPES: set[ComponentType] = {
    ComponentType.THREE_PHASE_VSI,
}
INVERTER_PWM_BUS_OUTPUT_SUPPORTED_TYPES: set[ComponentType] = {
    ComponentType.FOC_CONTROLLER,
    ComponentType.SIXSTEP_CONTROLLER,
}


def supports_inverter_pwm_bus(component_type: ComponentType) -> bool:
    """Return True when a component has a 6-PWM inverter bus pin (input or output)."""
    return (
        component_type in INVERTER_PWM_BUS_INPUT_SUPPORTED_TYPES
        or component_type in INVERTER_PWM_BUS_OUTPUT_SUPPORTED_TYPES
    )


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
    ComponentType.MMC_ARM:   {2},   # M_REF (signal-driven modulation ref)
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
    ComponentType.FOC_CONTROLLER,
    ComponentType.PFC_BOOST_CONTROLLER,
    ComponentType.SIXSTEP_CONTROLLER,
    ComponentType.MMC_CONTROLLER,
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
    # SharedHeatsink — every pin (AMB + DEV1..N) is thermal-domain so
    # the connectivity rules allow ``TH`` ↔ ``DEV_i`` wires and reject
    # accidental electrical wires onto the heatsink.
    ComponentType.HEATSINK,
}

ANY_DOMAIN_COMPONENT_TYPES: set[ComponentType] = {
    ComponentType.GOTO_LABEL,
    ComponentType.FROM_LABEL,
    # Port markers don't have a domain of their own — they inherit
    # whatever the connected net is (electrical or signal).
    ComponentType.SUBCIRCUIT_PORT,
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
        ComponentType.FOC_CONTROLLER,
        ComponentType.PFC_BOOST_CONTROLLER,
        ComponentType.SIXSTEP_CONTROLLER,
        ComponentType.MMC_CONTROLLER,
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


def is_motor_signal_bus_pin(component: "Component", pin_index: int) -> bool:
    """Return True for a dynamic machine's signal-bus output pin (``SIG``).

    The pin carries the motor's full observable bus (speed / currents /
    torque). A SIGNAL_DEMUX wired to it splits the bus into the individual
    channels for scoping.
    """
    if not supports_motor_signal_bus(component.type):
        return False
    return _pin_name(component, pin_index).strip().upper() == MOTOR_SIGNAL_BUS_PIN_NAME


def is_inverter_pwm_bus_pin(component: "Component", pin_index: int) -> bool:
    """Return True for an inverter PWM bus pin (``PWM`` on VSI / FOC / SIXSTEP).

    The pin carries the 6 gate signals between a FOC / SIXSTEP controller's
    PWM output and a THREE_PHASE_VSI's PWM input. Signal-domain (not
    electrical) — the converter must NOT treat the wire as a circuit branch.
    """
    if not supports_inverter_pwm_bus(component.type):
        return False
    return _pin_name(component, pin_index).strip().upper() == INVERTER_PWM_BUS_PIN_NAME


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

    # Dynamic-machine signal bus (PMSM ``SIG``) feeds a demux/scope.
    if is_motor_signal_bus_pin(component, pin_index):
        return True

    # Inverter PWM bus (FOC/SIXSTEP ``PWM`` output, VSI ``PWM`` input)
    # can also be tapped by a demux/scope for individual-gate plotting.
    if is_inverter_pwm_bus_pin(component, pin_index):
        return True

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

    # A dynamic machine's signal-bus output (PMSM ``SIG``) is signal-domain
    # even though the device itself is a circuit component.
    if is_motor_signal_bus_pin(component, pin_index):
        return CONNECTION_DOMAIN_SIGNAL

    # The 6-PWM inverter bus (VSI ``PWM`` input + FOC/SIXSTEP ``PWM``
    # output) is signal-domain. The VSI itself is a circuit component
    # (electrical phases + DC bus pins), but its PWM pin is the
    # controller wire and must NOT feed MNA.
    if is_inverter_pwm_bus_pin(component, pin_index):
        return CONNECTION_DOMAIN_SIGNAL

    return component_connection_domain(component.type)


# Default pin configurations for each component type
DEFAULT_PINS: dict[ComponentType, list[Pin]] = {
    # Basic passive
    ComponentType.RESISTOR: [Pin(0, "1", -40, 0), Pin(1, "2", 40, 0)],
    ComponentType.CAPACITOR: [Pin(0, "+", -20, 0), Pin(1, "-", 20, 0)],
    ComponentType.INDUCTOR: [Pin(0, "1", -40, 0), Pin(1, "2", 40, 0)],

    # Sources
    ComponentType.VOLTAGE_SOURCE: [Pin(0, "+", 0, -20), Pin(1, "-", 0, 20)],
    ComponentType.CURRENT_SOURCE: [Pin(0, "+", 0, -20), Pin(1, "-", 0, 20)],
    ComponentType.GROUND: [Pin(0, "gnd", 0, -20)],

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
    ComponentType.THYRISTOR: [Pin(0, "A", 0, -20), Pin(1, "K", 0, 20), Pin(2, "G", -20, 20)],
    ComponentType.TRIAC: [Pin(0, "MT1", 0, -20), Pin(1, "MT2", 0, 20), Pin(2, "G", -20, 20)],

    # Switching
    ComponentType.SWITCH: [Pin(0, "1", -20, 0), Pin(1, "2", 20, 0), Pin(2, "CTL", 0, -20)],

    # Transformer
    ComponentType.TRANSFORMER: [
        Pin(0, "P1", -40, -20),
        Pin(1, "P2", -40, 20),
        Pin(2, "S1", 40, -20),
        Pin(3, "S2", 40, 20),
    ],

    # Analog
    ComponentType.OP_AMP: [
        Pin(0, "IN+", -40, -20),
        Pin(1, "IN-", -40, 20),
        Pin(2, "OUT", 40, 0),
        Pin(3, "V+", 0, -20),
        Pin(4, "V-", 0, 20),
    ],
    ComponentType.COMPARATOR: [
        Pin(0, "IN+", -40, -20),
        Pin(1, "IN-", -40, 20),
        Pin(2, "OUT", 40, 0),
        Pin(3, "V+", 0, -20),
        Pin(4, "V-", 0, 20),
    ],

    # Protection
    ComponentType.RELAY: [
        Pin(0, "COIL+", -40, -20),
        Pin(1, "COIL-", -40, 20),
        Pin(2, "COM", 40, 0),
        Pin(3, "NO", 40, -20),
        Pin(4, "NC", 40, 20),
    ],
    ComponentType.FUSE: [Pin(0, "1", -20, 0), Pin(1, "2", 20, 0)],
    ComponentType.CIRCUIT_BREAKER: [Pin(0, "LINE", -20, 0), Pin(1, "LOAD", 20, 0)],

    # Control blocks - basic
    ComponentType.PI_CONTROLLER: [
        Pin(0, "IN", -40, 0),
        Pin(1, "OUT", 40, 0),
    ],
    ComponentType.PID_CONTROLLER: [
        Pin(0, "IN", -40, -20),
        Pin(1, "FB", -40, 20),
        Pin(2, "OUT", 40, 0),
    ],
    ComponentType.MATH_BLOCK: [
        Pin(0, "A", -40, -20),
        Pin(1, "B", -40, 20),
        Pin(2, "OUT", 40, 0),
    ],
    ComponentType.PWM_GENERATOR: [
        Pin(0, "OUT", 40, 0),
        Pin(1, "DUTY_IN", -40, 20),
    ],
    ComponentType.GAIN: _default_unary_block_pins(),
    ComponentType.SUM: _default_sum_pins(2),
    ComponentType.SUBTRACTOR: _default_sum_pins(2),
    ComponentType.CONSTANT: [Pin(0, "OUT", 40, 0)],

    # Control blocks - signal processing
    ComponentType.INTEGRATOR: [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)],
    ComponentType.DIFFERENTIATOR: [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)],
    ComponentType.LIMITER: [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)],
    ComponentType.RATE_LIMITER: [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)],
    ComponentType.HYSTERESIS: [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)],

    # Control blocks - advanced
    ComponentType.LOOKUP_TABLE: [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)],
    ComponentType.TRANSFER_FUNCTION: [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)],
    ComponentType.DELAY_BLOCK: [Pin(0, "IN", -40, 0), Pin(1, "OUT", 40, 0)],
    ComponentType.SAMPLE_HOLD: [
        Pin(0, "IN", -40, -20),
        Pin(1, "TRIG", -40, 20),
        Pin(2, "OUT", 40, 0),
    ],
    ComponentType.STATE_MACHINE: [
        Pin(0, "IN1", -40, -20),
        Pin(1, "IN2", -40, 20),
        Pin(2, "OUT", 40, 0),
    ],
    ComponentType.C_BLOCK: _default_c_block_pins(1, 1),

    # FOC controller: 2 signal-domain inputs + 1 signal-bus output.
    # SP  = speed-setpoint reference (rpm, signal). Typically driven by a
    #       CONSTANT carrying the target speed.
    # FB  = motor feedback bus (signal). Wire to the PMSM's SIG pin (or
    #       to a demux of it) so the converter can identify which PMSM
    #       to observe.
    # PWM = inverter PWM bus (signal-bus output). A single pin carrying
    #       all 6 gate signals (3 high-side + 3 low-side) produced by
    #       inverse Park/Clarke. Wire to a THREE_PHASE_VSI's ``PWM``
    #       input pin — that wire is the SOLE binding between the FOC
    #       and the inverter (no parameter-based ``vsi_name`` fallback).
    ComponentType.FOC_CONTROLLER: [
        Pin(0, "SP", -40, -20),
        Pin(1, "FB", -40, 20),
        Pin(2, INVERTER_PWM_BUS_PIN_NAME, 40, 0),
    ],

    # 6-step BLDC controller — same SP / FB / PWM convention as the FOC
    # block so the user can swap one for the other on the same
    # schematic and see the difference. The converter routes through
    # the PMSM ``SIG`` bus the FB pin reaches to bind the PMSM, and
    # through the ``PWM`` output bus wire to bind the VSI.
    ComponentType.SIXSTEP_CONTROLLER: [
        Pin(0, "SP", -40, -20),
        Pin(1, "FB", -40, 20),
        Pin(2, INVERTER_PWM_BUS_PIN_NAME, 40, 0),
    ],

    # Shared heatsink (pulsim 1.7). Default layout has 4 device slots
    # (covers a typical PFC: Q_boost + D_boost + bridge diodes) plus an
    # ambient reference pin. Slot count can grow via ``n_devices`` in
    # the parameters; ``_synchronize_special_component`` rebuilds the
    # pin layout to match.
    #   AMB    = ambient temperature reference (thermal-domain). Wires
    #            to a GROUND-like THERMAL_REFERENCE pin or just floats
    #            (uses ``T_amb_C`` parameter).
    #   DEV1..N = thermal-domain ports. Each wires to ONE device's
    #             ``TH`` pin to enrol that device in the shared sink.
    ComponentType.HEATSINK: [
        Pin(0, "AMB", -40, 0),
        Pin(1, "DEV1", 40, -30),
        Pin(2, "DEV2", 40, -10),
        Pin(3, "DEV3", 40, 10),
        Pin(4, "DEV4", 40, 30),
    ],

    # PFC boost controller: 3 signal-domain inputs.
    # VBUS = bus-voltage feedback (V). Wire to a voltage probe on the bus
    #        capacitor.
    # IL   = inductor-current feedback (A). Wire to a current probe on the
    #        boost inductor.
    # VAC  = rectified-input voltage (V). Wire to a voltage probe on the
    #        diode-bridge DC+ rail (between bridge and L_boost).
    # PWM  = drive signal for the boost MOSFET's gate. Wiring this pin
    #        to a MOSFET tells the converter which switch this controller
    #        drives (preferred over the auto-detect path, which was the
    #        only option before — that was confusing because there was
    #        no visible wire showing which switch the PFC controlled).
    #        Auto-detect still runs as a fallback when the pin is
    #        unwired, so older schematics keep working.
    ComponentType.PFC_BOOST_CONTROLLER: [
        Pin(0, "VBUS", -40, -20),
        Pin(1, "IL",   -40,   0),
        Pin(2, "VAC",  -40,  20),
        Pin(3, "PWM",   40,   0),
    ],

    # Measurement
    ComponentType.VOLTAGE_PROBE: [
        Pin(0, "+", 0, -20),
        Pin(1, "-", 0, 20),
        Pin(2, VOLTAGE_PROBE_OUTPUT_PIN_NAME, 20, 0),
    ],
    ComponentType.VOLTAGE_PROBE_GND: [
        Pin(0, "IN", -20, 0),
        Pin(1, VOLTAGE_PROBE_OUTPUT_PIN_NAME, 20, 0),
    ],
    ComponentType.CURRENT_PROBE: [
        Pin(0, "IN", -20, 0),
        Pin(1, "OUT", 20, 0),
        Pin(2, CURRENT_PROBE_OUTPUT_PIN_NAME, 0, -20),
    ],
    ComponentType.POWER_PROBE: [
        Pin(0, "V+", -20, -20),
        Pin(1, "V-", -20, 20),
        Pin(2, "I+", 20, -20),
        Pin(3, "I-", 20, 20),
    ],

    # Scopes
    ComponentType.ELECTRICAL_SCOPE: _default_scope_pins(2),
    ComponentType.THERMAL_SCOPE: _default_scope_pins(2),

    # Signal routing
    ComponentType.SIGNAL_MUX: _default_mux_pins(4),
    ComponentType.SIGNAL_DEMUX: _default_demux_pins(4),
    ComponentType.GOTO_LABEL: [Pin(0, "NET", -40, 0)],
    ComponentType.FROM_LABEL: [Pin(0, "NET", 40, 0)],
    # SUBCIRCUIT_PORT default sits on the left edge. The pin position
    # is regenerated by _synchronize_subcircuit_port_pin based on the
    # ``side`` parameter (left/right/top/bottom).
    ComponentType.SUBCIRCUIT_PORT: [Pin(0, "P", -40, 0)],

    # Magnetic
    ComponentType.SATURABLE_INDUCTOR: [Pin(0, "1", -40, 0), Pin(1, "2", 40, 0)],
    ComponentType.COUPLED_INDUCTOR: [
        Pin(0, "L1_1", -40, -20),
        Pin(1, "L1_2", -40, 20),
        Pin(2, "L2_1", 40, -20),
        Pin(3, "L2_2", 40, 20),
    ],
    # Jiles-Atherton hysteretic inductor — 2-terminal like an
    # ordinary inductor (the L0 + V_M internal split is invisible).
    ComponentType.HYSTERETIC_INDUCTOR: [Pin(0, "1", -40, 0), Pin(1, "2", 40, 0)],

    # Pre-configured networks
    ComponentType.SNUBBER_RC: [Pin(0, "1", -20, 0), Pin(1, "2", 20, 0)],

    # Single-phase diode bridge (Graetz). 4 external pins: 2 AC, 2 DC.
    # Internal topology when converted:
    #   D1: AC+ → DC+,  D2: AC- → DC+
    #   D3: DC- → AC+,  D4: DC- → AC-
    ComponentType.SINGLE_PHASE_DIODE_BRIDGE: [
        Pin(0, "AC+", -40, -20),
        Pin(1, "AC-", -40, 20),
        Pin(2, "DC+", 40, -20),
        Pin(3, "DC-", 40, 20),
        # pulsim 1.7 — thermal-port pin for SharedHeatsink wiring.
        # Wires the 4 internal diodes (BR_D1..D4) as a single lumped
        # device to a HEATSINK's DEV pin; the converter expands this
        # into 4 sub-device descriptor rows sharing the same Foster
        # stack (so the user only has to enter one device's data).
        Pin(4, "TH", 0, 40),
    ],

    # Three-phase diode bridge (6-pulse rectifier). 5 pins: A, B, C, DC+, DC-.
    # Upper diodes: A/B/C → DC+
    # Lower diodes: DC- → A/B/C
    ComponentType.THREE_PHASE_DIODE_BRIDGE: [
        Pin(0, "A",   -40, -20),
        Pin(1, "B",   -40, 0),
        Pin(2, "C",   -40, 20),
        Pin(3, "DC+",  40, -20),
        Pin(4, "DC-",  40, 20),
    ],

    # MMC sub-module cell. The pin count is dynamic: half-bridge uses
    # 4 pins (TOP, BOT, S1_G, S2_G), full-bridge uses 6 (adds S3_G,
    # S4_G). Default pin layout below is the half-bridge variant — the
    # ``_synchronize_mmc_cell`` hook rewrites the layout when the
    # ``cell_topology`` parameter changes.
    ComponentType.MMC_CELL: [
        Pin(0, "TOP",  -40, -20),
        Pin(1, "BOT",  -40, 20),
        Pin(2, "S1_G",  40, -20),
        Pin(3, "S2_G",  40, 20),
    ],

    # MMC arm. 3 pins:
    #   TOP, BOT — the two arm terminals (chain endpoints)
    #   M_REF   — modulation reference input (constant or driven by a
    #             signal block); pulsim's add_mmc_arm_* takes this
    #             value to drive the per-step arm voltage.
    ComponentType.MMC_ARM: [
        Pin(0, "TOP",  -40, -40),
        Pin(1, "BOT",  -40, 40),
        Pin(2, "M_REF", 40, 0),
    ],
    # 3-phase MMC controller: six modulation-reference outputs, one per
    # arm (phase A/B/C × upper/lower). Wire each to the matching
    # MMC_ARM ``M_REF`` pin; the converter reads the pin role (phase +
    # up/lo) to build that arm's m_ref(t).
    ComponentType.MMC_CONTROLLER: [
        Pin(0, "A_UP", 40, -50),
        Pin(1, "A_LO", 40, -30),
        Pin(2, "B_UP", 40, -10),
        Pin(3, "B_LO", 40,  10),
        Pin(4, "C_UP", 40,  30),
        Pin(5, "C_LO", 40,  50),
    ],

    # Three-phase / vector control (Pulsim Phase 28)
    # Clarke (abc → αβγ): 3 inputs + 3 channel outputs (channels via metadata)
    ComponentType.CLARKE_TRANSFORM: [
        Pin(0, "A", -40, -20),
        Pin(1, "B", -40, 0),
        Pin(2, "C", -40, 20),
        Pin(3, "ALPHA", 40, -20),
        Pin(4, "BETA", 40, 0),
        Pin(5, "GAMMA", 40, 20),
    ],
    ComponentType.INVERSE_CLARKE_TRANSFORM: [
        Pin(0, "ALPHA", -40, -20),
        Pin(1, "BETA", -40, 0),
        Pin(2, "GAMMA", -40, 20),
        Pin(3, "A", 40, -20),
        Pin(4, "B", 40, 0),
        Pin(5, "C", 40, 20),
    ],
    # Park (αβ + θ → dq): nodes [alpha, beta], θ via metadata
    ComponentType.PARK_TRANSFORM: [
        Pin(0, "ALPHA", -40, -20),
        Pin(1, "BETA", -40, 20),
        Pin(2, "D", 40, -20),
        Pin(3, "Q", 40, 20),
    ],
    ComponentType.INVERSE_PARK_TRANSFORM: [
        Pin(0, "D", -40, -20),
        Pin(1, "Q", -40, 20),
        Pin(2, "ALPHA", 40, -20),
        Pin(3, "BETA", 40, 20),
    ],
    # Single-phase PLL: 1 input → θ, ω, lock_error channels
    ComponentType.PLL: [
        Pin(0, "IN", -40, 0),
        Pin(1, "THETA", 40, -20),
        Pin(2, "OMEGA", 40, 0),
        Pin(3, "ERR", 40, 20),
    ],
    # SVM (αβ → 3 duties)
    ComponentType.SVM: [
        Pin(0, "ALPHA", -40, -20),
        Pin(1, "BETA", -40, 20),
        Pin(2, "DA", 40, -20),
        Pin(3, "DB", 40, 0),
        Pin(4, "DC", 40, 20),
    ],
    # Three-phase grid source (pulsim>=0.10.0a1).
    # 4 pins: A, B, C, Neutral. The runtime decomposes this into 3 internal
    # SineVoltageSource branches sharing the neutral.
    ComponentType.THREE_PHASE_SOURCE: [
        Pin(0, "A", 40, -20),
        Pin(1, "B", 40, 0),
        Pin(2, "C", 40, 20),
        Pin(3, "N", -40, 0),
    ],

    # Three-phase 2-level VSI (pulsim>=0.10.0a5).
    # 5 pins: VDC+, VDC-, A, B, C. The runtime decomposes into 6 MOSFETs +
    # 6 PWM gate drivers in 3 half-bridge legs.
    ComponentType.THREE_PHASE_VSI: [
        Pin(0, "VDC+", -40, -20),
        Pin(1, "VDC-", -40, 20),
        Pin(2, "A", 40, -20),
        Pin(3, "B", 40, 0),
        Pin(4, "C", 40, 20),
        # Inverter PWM bus input (signal-domain). A single bus pin
        # carrying all 6 gate signals (3 high-side + 3 low-side). The
        # FOC_CONTROLLER / SIXSTEP_CONTROLLER ``PWM`` output pin wires
        # here — that wire is the SOLE binding between the controller
        # and this inverter (no parameter-based ``vsi_name`` fallback).
        Pin(5, INVERTER_PWM_BUS_PIN_NAME, -40, 40),
        # pulsim 1.7 — thermal-port pin for SharedHeatsink wiring.
        # Wires the 6 internal MOSFETs (VSI__HSa/HSb/HSc/LSa/LSb/LSc)
        # as a single lumped device. Converter expands into 6 sub-
        # device descriptor rows sharing the same Foster stack so
        # users only enter ONE device's thermal data.
        Pin(6, "TH", 40, 40),
    ],

    # DC Motor (pulsim>=0.10.0a2). 2-terminal armature device with internal
    # mechanical state (ω, θ). Pulsim's runtime reserves one branch row for
    # the armature current and advances ω, θ each accepted timestep.
    ComponentType.DC_MOTOR: [
        Pin(0, "A+", -40, 0),
        Pin(1, "A-", 40, 0),
    ],

    # 3-phase RL load (pulsim>=0.10.0a3). 4 pins: A, B, C, Neutral.
    # The runtime decomposes into R+L series branches (Y or Δ topology).
    ComponentType.THREE_PHASE_RL_LOAD: [
        Pin(0, "A", -40, -20),
        Pin(1, "B", -40, 0),
        Pin(2, "C", -40, 20),
        Pin(3, "N", 40, 0),
    ],

    # PMSM (pulsim>=0.10.0a3). 4 pins: A, B, C, Neutral. Decomposes into
    # 3 phases of R_s + L_s + sinusoidal back-EMF source.
    # Stator phase pins land on the 20-px wiring grid directly — keeping
    # the authoring aligned with the runtime snap so wires connect right
    # at the rendered pin bubble (no silent ±5 / ±10 drift).
    ComponentType.PMSM_STEADY_STATE: [
        Pin(0, "A", -40, -20),
        Pin(1, "B", -40, 0),
        Pin(2, "C", -40, 20),
        Pin(3, "N", 40, 0),
    ],

    # PMSM dynamic (pulsim>=0.10.0a4). 4 power pins (A, B, C, Neutral) +
    # a signal-bus output (SIG) carrying the motor's observable traces
    # (speed / currents / torque) for wiring to a SIGNAL_DEMUX → scope.
    # Full device-variant: rotor inertia + electromagnetic torque feedback,
    # 4 internal states tracked by the runtime.
    ComponentType.PMSM: [
        Pin(0, "A", -40, -20),
        Pin(1, "B", -40, 0),
        Pin(2, "C", -40, 20),
        Pin(3, "N", 40, 0),
        Pin(4, MOTOR_SIGNAL_BUS_PIN_NAME, 40, 20),
    ],
    # Induction motor: 3 stator phase terminals + star-point neutral,
    # same terminal layout convention as PMSM.
    ComponentType.INDUCTION_MOTOR: [
        Pin(0, "A", -40, -20),
        Pin(1, "B", -40, 0),
        Pin(2, "C", -40, 20),
        Pin(3, "N", 40, 0),
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
    # Per-device junction-temperature safety limit (pulsim 1.7
    # ``ThermalLimitMonitor``). Disabled when ``T_max_C <= 0``. Hysteresis
    # avoids chatter when T_j hovers right at the limit.
    "thermal_t_max_C": 0.0,
    "thermal_t_max_hysteresis_C": 0.0,
    # Linear temperature-coefficient of loss (pulsim 1.7
    # ``TempCoLoss``). Multipliers on the conduction / switching
    # reference power: ``P(T_j) = P_ref · (1 + α · (T_j − T_ref))``.
    # Defaults to 0 (temperature-independent — behaves like the
    # legacy isolated/coupled paths). Typical values from datasheets:
    #   * MOSFET conduction (Rds_on rises with T): a_cond ≈ +0.006
    #   * Diode conduction  (V_f falls with T):    a_cond ≈ −0.002
    #   * Switching energy:                         a_sw   ≈ +0.001
    # When non-zero, the backend runs the coupled fixed-point solve
    # (``electrothermal_steady_state``) which can detect THERMAL
    # RUNAWAY (ρ(M·K) ≥ 1) before the user blows up a real device.
    "loss_a_cond_per_C": 0.0,
    "loss_a_sw_per_C": 0.0,
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
        # ``implementation`` picks the authoring backend:
        #   "source"        — C source (legacy / PSIM-style, compiled
        #                      by the kernel toolchain).
        #   "lib"           — pre-built shared library path.
        #   "python_numba"  — pulsim 1.5 fast_block: a Python control
        #                      law JIT-compiled via Numba (or run
        #                      pure-Python when numba is absent).
        "implementation": "source",
        "source": "",
        "lib_path": "",
        "source_code": "",
        "extra_cflags": [],
        "sample_time": 0.0,
        # python_numba authoring: the control-law function body + its
        # persistent-state vector length. Empty by default; the
        # properties editor seeds a PI template on first switch.
        "python_source": "",
        "n_states": 1,
    },

    # PFC boost controller — cascaded outer voltage / inner current PI
    # loops with sine-modulated inner setpoint. Defaults target a 240–
    # 1000 W universal-input PFC stage operating in CCM (continuous-
    # conduction mode) — the standard choice in this power range because:
    #   - I_peak is ~2× I_avg vs ~4× in DCM, so MOSFET / inductor stress
    #     is much lower and a smaller EMI filter is sufficient.
    #   - Fixed switching frequency simplifies EMI compliance.
    #   - Loop bandwidth is higher than DCM voltage-mode, giving better
    #     transient response on load steps.
    # DCM may be preferable below ~150 W (single voltage loop, no inner
    # current loop), but for this range CCM wins.
    ComponentType.PFC_BOOST_CONTROLLER: {
        # CCM is the default mode (recommended for 240–1000 W). Switch to
        # "DCM" only for lighter loads where DCM's simpler single-loop
        # control is acceptable.
        "mode": "CCM",
        # --- Target / safety ---
        # Universal-input PFC standard target (400 V) — high enough to
        # accept up to 264 Vrms input without saturating.
        "v_bus_ref": 400.0,
        "v_bus_min": 0.0,
        "v_bus_max": 450.0,
        # --- Outer voltage loop (slow, ~10 Hz BW) ---
        # Set well below 2·f_line so the 120 Hz bus ripple is NOT
        # amplified into the current reference (the classic PFC trap).
        "voltage_kp": 0.30,
        "voltage_ki": 6.0,
        # Output of the voltage loop is the peak input-current amplitude.
        # Clamp to a safe per-unit of the inverter rating.
        "i_pk_limit": 10.0,
        # --- Inner current loop (fast, ~5 kHz BW) ---
        # The PI output is the DUTY cycle (0..duty_max). Tune for the
        # plant ``ΔI_L / Δduty ≈ V_bus / (s·L)`` so the closed loop
        # crosses over at ω_c without saturating duty on every cycle:
        #
        #   Kp ≈ ω_c · L / V_bus
        #   Ki ≈ Kp · ω_zero   (ω_zero typically ω_c / 5..10)
        #
        # Defaults below target L=5 mH, V_bus=400 V, ω_c = 2π·5 kHz —
        # the recipe used by the bundled examples. **Older Pulsim builds
        # shipped Kp=31.4 / Ki=3140 here; those values are 80× too high
        # — a ~30 mA current error saturated duty to ``duty_max`` and
        # the inductor current built giant per-cycle spikes**. Adjust
        # ``current_kp ∝ L`` if your boost choke is different.
        "current_kp": 0.4,
        "current_ki": 1200.0,
        # Duty clamp (0..duty_max). Leave a small margin so the bus
        # capacitor never charges through the body diode.
        "duty_max": 0.95,
        # --- Source / line ---
        # Vac peak normalization (used as the sine-reference scale). For
        # 230 Vrms line: 230·√2 ≈ 325 V. For 110 Vrms low-line: 156 V.
        "vac_pk_nom": 325.0,
        # Mains frequency (Hz). 50 (EU/SA) or 60 (NA).
        "f_line": 60.0,
        # --- Switching ---
        # Standard high-power PFC carrier (65 kHz is the modern default).
        "f_sw": 65000.0,
        # --- Startup ---
        # Soft-start ramp time (seconds). The outer voltage reference is
        # ramped linearly from ``v_bus_initial`` (defaults to the peak
        # rectified AC, ≈ ``vac_pk_nom``) up to ``v_bus_ref`` over this
        # interval, so the outer PI never sees a huge initial error and
        # the integrator does NOT wind up to ``i_pk_limit``. Without the
        # ramp, the current loop saturates immediately and the inductor
        # current shows giant switching transients during the entire
        # bus-cap charge interval — exactly the "noisy/unphysical I_L"
        # symptom users hit when running ex 20 from a cold start.
        # Set to 0 to disable (matches the pre-1.1.2 behaviour).
        "soft_start_time": 0.05,
        # Initial bus-voltage assumption used to seed the soft-start
        # ramp. Defaults to the peak rectified mains (≈ vac_pk_nom);
        # set explicitly when the bus has a different precharge level.
        "v_bus_initial": 310.0,
        # NOTE: as of v1.1.3 there are NO ``*_name`` binding overrides
        # here. The MOSFET (PWM output), the bus-voltage node (VBUS
        # input), the rectified-input node (VAC input), and the
        # inductor current probe (IL input) are ALL identified by
        # wire-tracing the corresponding pin. A missing wire is a hard
        # converter error so the user always sees the binding on the
        # schematic, never a silent ``auto-detect`` magic.
    },

    # FOC drive controller — cascaded speed → d/q current PI loops over a
    # PMSM observer bundle, with inverse Park/Clarke driving a native 3φ
    # VSI. The defaults below are the validated VLT403U recipe; tune them
    # in the properties dialog if your motor has different parameters.
    ComponentType.FOC_CONTROLLER: {
        # Outer speed loop (rpm error → q-axis current reference).
        "speed_kp": 0.17,
        "speed_ki": 6.0,
        # Inner current loops (d/q current error → d/q voltage references).
        "current_kp": 45.0,
        "current_ki": 24000.0,
        # d-axis current reference (0 for non-salient PMSM; flux-weakening
        # uses a negative value at high speed).
        "id_ref": 0.0,
        # q-axis current saturation — clamps torque-producing current to
        # a safe per-unit value.
        "iq_limit": 3.0,
        # Voltage clamp as fraction of Vdc/2 (modulation-index ceiling).
        "v_limit_frac": 0.92,
        # Speed-reference ramp time (s) — softens step changes in SP so the
        # outer PI doesn't saturate or trip the q-current limit.
        "speed_ramp_s": 0.1,
        # Fallback PWM carrier when no VSI is configured upstream.
        "switching_frequency_hz": 20000.0,
        # Fallback speed reference (rpm) when the SP pin is left unwired.
        "speed_ref_rpm": 1800.0,
        # Explicit DC-bus magnitude. Used by the backend to normalise
        # the modulation + clamp v_d/v_q (Vbus/2). Set this to the
        # nominal DC bus of the front-end feeding the VSI (e.g. 360 V
        # for a doubler, 400 V for a PFC). 0 leaves it at the
        # converter-side default (360 V).
        "v_bus": 0.0,
        # NOTE: no ``pmsm_name`` / ``vsi_name`` overrides — the
        # observed PMSM is identified by tracing the FB pin wire back
        # to the motor's SIG bus, and the driven VSI is identified by
        # tracing the PWM output wire to the inverter's PWM bus input.
        # A missing wire is a hard converter error.
    },

    ComponentType.HEATSINK: {
        # Number of device slots (also drives the pin layout —
        # ``_synchronize_special_component`` regenerates pins to match).
        # 2-6 is the practical range; default 4 covers a typical PFC
        # front-end (Q_boost + D_boost + 2 of the 4 bridge diodes).
        "n_devices": 4,
        # Sink-to-ambient thermal resistance [K/W]. The ONE field that
        # dominates the steady-state shared-sink temperature rise — set
        # it to whatever the heatsink datasheet reports (or use the
        # ``convection_resistance`` helper for a first-cut estimate).
        # 5 K/W is a small TO-220 clip-on default.
        "R_th_sink_to_amb_K_per_W": 5.0,
        # Optional sink thermal mass [J/K]. ``0`` = massless (steady-
        # state-only sizing). Non-zero gives the transient response a
        # tau ≈ R_sa · C_sink before the sink temperature catches up to
        # the steady state — important on intermittent / pulsed loads.
        "C_th_sink_J_per_K": 0.0,
        # Ambient temperature [°C]. The whole network is anchored here
        # — every junction temperature reads as
        # T_j_i = T_amb + R_th_sa·Σ_P + R_th_cs_i·P_i + R_th_jc_i·P_i.
        "T_amb_C": 25.0,
        # OPTIONAL per-device case-to-sink resistance [K/W], one CSV
        # entry per attached device. Empty defaults every device to
        # ``0`` (case bonded directly to sink). Use the
        # ``tim_resistance`` helper or the datasheet ``R_th_ch`` to
        # populate. Example: "0.5, 0.5, 0.3, 0.3" for 4 devices on
        # thermal grease + electrical insulator pads.
        "case_to_sink_R_th_csv": "",
    },

    ComponentType.SIXSTEP_CONTROLLER: {
        # Outer speed loop (rpm error → duty). PI tuned for the same
        # Embraco VLT403U recipe the FOC default targets, scaled so the
        # output sits in 0..duty_max.
        "speed_kp": 0.0025,
        "speed_ki": 0.05,
        # Duty clamp (0..duty_max) — modulates only the active high-side
        # of the commutation sector pair.
        "duty_max": 0.95,
        # Speed reference (rpm) used when SP pin is unwired.
        "speed_ref_rpm": 1800.0,
        # Speed-reference ramp time (s) — same purpose as FOC's: keep the
        # outer PI from saturating on a cold-start step.
        "speed_ramp_s": 0.1,
        # PWM carrier frequency for the high-side modulation.
        "switching_frequency_hz": 20000.0,
        # Commutation sector advance (electrical degrees). 0° = classic
        # 120° trapezoidal alignment; +30° / −30° emulates the lead /
        # lag many production drives use to chase BEMF peak.
        "sector_advance_deg": 0.0,
        # NOTE: no ``pmsm_name`` / ``vsi_name`` overrides — both the
        # observed PMSM and the driven VSI are identified by wire-
        # tracing (FB → SIG bus and PWM → inverter PWM bus).
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
    # Hierarchical port marker. ``port_name`` is what appears as the
    # pin label on the outer SubcircuitInstance symbol; ``direction``
    # is cosmetic + governs flattening for control signals; ``side``
    # places the pin on the outer rectangle.
    ComponentType.SUBCIRCUIT_PORT: {
        "port_name": "port",
        "direction": "bidir",
        "side": "left",
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

    # Power rectifier bridges (composite — expanded to primitives at convert time)
    ComponentType.SINGLE_PHASE_DIODE_BRIDGE: {
        # Diode model — applied to all 4 diodes (D1..D4)
        "g_on": 1.0e3,           # conductance when conducting [S]
        "g_off": 1.0e-9,         # conductance when blocking [S]
        "v_forward": 0.7,        # forward drop [V]  (informational; kernel uses g_on/g_off PWL)
        # Optional thermal (per-diode, applied uniformly)
        "r_th_jc": 1.5,          # K/W
        "tau_th": 0.075,         # s
        # pulsim 1.7 — fields used WHEN the TH pin is wired to a
        # HEATSINK. All 4 sub-diodes get the same Foster stack +
        # tempcos. Single-stage fallback if multi-stage CSVs are
        # blank. Mirrors ``DEFAULT_THERMAL_DEVICE_PARAMS`` but uses
        # this composite's own keys (so the inspector renders the
        # full set without colliding with the per-MOSFET fields).
        **DEFAULT_THERMAL_DEVICE_PARAMS,
    },
    ComponentType.THREE_PHASE_DIODE_BRIDGE: {
        # Diode model — applied to all 6 diodes (D1..D6)
        "g_on": 1.0e3,
        "g_off": 1.0e-9,
        "v_forward": 0.7,
        "r_th_jc": 1.5,
        "tau_th": 0.075,
    },

    # Modular Multilevel Converter sub-module cell.
    # ``cell_topology`` picks between half-bridge (2 switches) and
    # full-bridge (4 switches) — the converter and visual item branch
    # on this value, and ``_synchronize_mmc_cell`` rewires the pin
    # layout on change.
    ComponentType.MMC_CELL: {
        "cell_topology": "Half-Bridge",  # "Half-Bridge" | "Full-Bridge"
        # Switch model (shared across all MOSFETs in the cell)
        "r_ds_on": 25e-3,        # MOSFET on-resistance [Ω]
        "g_off": 1.0e-9,         # off-state conductance [S]
        "v_th": 3.0,             # gate threshold [V]
        # Body diode
        "diode_v_forward": 0.7,
        "diode_g_on": 1.0e3,
        "diode_g_off": 1.0e-9,
        # Cell capacitor
        "c_cell": 4.7e-3,        # F  (typical MMC sub-module ≈ mF range)
        "v_cell_init": 0.0,      # initial capacitor voltage [V]
        # Thermal (per-switch)
        "r_th_jc": 1.0,
        "tau_th": 0.060,
    },

    # MMC arm — full chain of N sub-modules with selectable fidelity.
    # ``model_fidelity`` maps to pulsim's native arm helpers:
    #   L0 Average   → add_mmc_arm_average    (single equivalent V src)
    #   L1 Multilevel→ add_mmc_arm_multilevel (per-level voltage steps)
    #   L2 Equivalent→ add_mmc_arm_equivalent (SM-equivalent model)
    #   L3 Detailed  → add_mmc_arm_detailed   (every switch + cap)
    ComponentType.MMC_ARM: {
        "model_fidelity": "L3 Detailed",
        "submodule_type": "Half-Bridge",       # or "Full-Bridge"
        "n_submodules": 4,                      # # SMs in the arm chain
        # Capacitor + arm impedance
        "c_sm": 4.7e-3,                         # per-SM capacitance [F]
        "v_c0": 0.0,                            # initial SM voltage [V]
        "r_arm": 0.01,                          # arm series resistance [Ω]
        # Modulation
        "m_ref_constant": 0.5,                  # used when M_REF pin unwired
        # Switching (used by L1/L2/L3 — not L0)
        "f_carrier": 1000.0,                    # PWM carrier [Hz]
        "modulation_scheme": "PSC",             # "PSC" (ps_pwm) | "IPD"
        # L2-only (dead-time / min on-time)
        "t_dead": 1.0e-6,
        "t_min": 1.0e-7,
        # L3-only (cap-voltage balancing strategy)
        "balancing": "sort_and_select",         # "sort_and_select" | "none"
    },
    ComponentType.MMC_CONTROLLER: {
        # Open-loop sinusoidal modulation (each phase 120° apart; the
        # upper arm gets m, the lower arm the complement). The converter
        # builds m_ref(t) = offset + (index/2)·sin(2π·f·t + phase) per
        # phase and routes it to the wired arm M_REF pins.
        "m_ref_offset": 0.5,        # DC operating point (mid-modulation)
        "modulation_index": 0.8,    # AC modulation depth (0..1, peak)
        "frequency": 60.0,          # output AC frequency [Hz]
        "phase_deg": 0.0,           # phase-A reference angle [deg]
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
    # Three-phase 2-level VSI helper (Pulsim 0.10.0a5). Decomposes into
    # 6 MOSFETs + 6 SPWM gate drivers (forced to Ideal switching mode).
    ComponentType.THREE_PHASE_VSI: {
        "switching_frequency_hz":  10e3,   # Hz — PWM carrier
        "modulation_index":        0.8,    # 0..1 linear SPWM
        "modulation_frequency_hz": 50.0,   # Hz — output fundamental
        "phase_a_deg":             0.0,    # Reference angle for phase A
        "positive_sequence":       True,
        "v_gate_on":               12.0,   # V — gate drive amplitude
        "v_gate_off":              0.0,    # V
        "mosfet_r_on_ohm":         0.01,   # Ω — R_ds(on)
        "mosfet_vth":              1.0,    # V — gate threshold
        # pulsim 1.7 — fields used WHEN the TH pin is wired to a
        # HEATSINK. All 6 sub-MOSFETs (HSa/HSb/HSc/LSa/LSb/LSc) get
        # the same Foster stack + tempcos. See SINGLE_PHASE_DIODE_BRIDGE
        # entry for the rationale.
        **DEFAULT_THERMAL_DEVICE_PARAMS,
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

    # PMSM dynamic device (Pulsim 0.10.0a4). Full device-variant: 4
    # internal states (i_d, i_q, ω_m, θ_m), 3 reserved MNA branch rows,
    # Park-frame torque, forward-Euler mechanical step.
    ComponentType.PMSM: {
        "Rs":            0.5,        # Ω — stator phase resistance
        "Ld":            2e-3,       # H — d-axis inductance
        "Lq":            2e-3,       # H — q-axis inductance (Lq > Ld → IPM)
        "psi_pm":        0.1,        # Wb — magnet flux linkage
        "pole_pairs":    2,          # poles / 2
        "J":             1e-3,       # kg·m² — rotor inertia
        "b_friction":    1e-4,       # N·m·s — linear viscous friction
        "friction_coulomb": 0.0,     # N·m — Coulomb friction
        "i_d_init":      0.0,        # A
        "i_q_init":      0.0,        # A
        "omega_init":    0.0,        # rad/s
        "theta_init":    0.0,        # rad
        "tau_load":      0.0,        # N·m — external shaft load
    },

    # 3-phase squirrel-cage induction motor (pulsim.add_induction_motor).
    # Rotor R/L are REFERRED to the stator side (IEEE equivalent-
    # circuit convention). Hard constraint enforced by pulsim:
    # L_m² < L_s·L_r so the leakage factor σ = 1 − Lm²/(Ls·Lr) ∈ (0, 1).
    # These defaults give σ = 0.19 (typical small machine).
    ComponentType.INDUCTION_MOTOR: {
        "R_s":          0.5,    # Ω — stator phase resistance
        "L_s":          0.05,   # H — stator self-inductance
        "R_r":          0.4,    # Ω — rotor resistance (referred)
        "L_r":          0.05,   # H — rotor self-inductance (referred)
        "L_m":          0.045,  # H — mutual inductance (referred)
        "pole_pairs":   2,      # poles / 2
        "J":            1e-3,   # kg·m² — rotor + load inertia
        "B":            0.0,    # N·m·s — viscous friction
        "T_load":       0.0,    # N·m — constant shaft load torque
    },

    # Jiles-Atherton hysteretic inductor (pulsim.add_hysteretic_inductor).
    # ``material`` selects a built-in J-A parameter set (see
    # PARAM_OPTIONS); the converter resolves it via
    # pulsim.reference_material(). Geometry (N_turns / l_m / A_core)
    # sets the linear air-core inductance L0 = N²·A·µ₀/l_m and scales
    # the hysteresis contribution. All three must be positive (pulsim
    # raises otherwise).
    ComponentType.HYSTERETIC_INDUCTOR: {
        "material":     "si_steel_m19",  # J-A catalog key
        "N_turns":      100,             # turns on the coil
        "l_m":          0.1,             # m — mean magnetic path length
        "A_core":       1e-4,            # m² — effective core area
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
    # MMC sub-module cell topology (drives pin count + converter
    # expansion + visual symbol).
    "cell_topology": ["Half-Bridge", "Full-Bridge"],
    # MMC arm fidelity level (drives which pulsim native helper
    # the converter calls — see DEFAULT_PARAMETERS for the mapping).
    "model_fidelity": [
        "L0 Average",
        "L1 Multilevel",
        "L2 Equivalent",
        "L3 Detailed",
    ],
    # MMC arm sub-module flavor (passed to pulsim's SubmoduleType
    # Literal[..]). Maps to 'half_bridge' / 'full_bridge'.
    "submodule_type": ["Half-Bridge", "Full-Bridge"],
    # MMC arm modulation scheme (passed to pulsim's ModulationScheme
    # Literal[..]). pulsim 1.5 supports two: PSC (= ps_pwm,
    # phase-shifted PWM) and IPD (= ipd, in-phase disposition).
    "modulation_scheme": ["PSC", "IPD"],
    # MMC L3 cap-voltage balancing strategy.
    "balancing": ["sort_and_select", "none"],
    # Jiles-Atherton soft-magnetic material catalog for the
    # HYSTERETIC_INDUCTOR. Each maps to a built-in 5-parameter J-A
    # set via pulsim.reference_material(). Order = widest→narrowest
    # loss loop is roughly annealed_iron > si_steel > permalloy >
    # ferrite, but the user picks by material name, not loss.
    "material": [
        "si_steel_m19",
        "annealed_iron",
        "ferrite_n87",
        "permalloy",
    ],
    # SUBCIRCUIT_PORT direction: cosmetic (arrow head) + signals to
    # the converter how to treat the bridge for control signals.
    # ``bidir`` is the default for electrical nets.
    "direction": ["input", "output", "bidir"],
    # Which edge of the outer SubcircuitInstance symbol the pin
    # lands on.
    "side": ["left", "right", "top", "bottom"],
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
        """Initialize default pins/parameters and normalize the layout.

        Pins supplied explicitly — e.g. by :meth:`from_dict` when opening a
        saved circuit — are authoritative: their exact positions are
        preserved so saved wire endpoints stay attached and the symbol does
        not visually stretch. Parameter normalization and structural pin
        synchronization still run; only the grid-snap / default-respacing
        *nudge* is reverted, and only when synchronization left the pin set
        (names + order) unchanged. A genuine structural change (e.g. a
        probe-schema rename, or a param-driven channel-count change) keeps
        the freshly synchronized layout. Components created from scratch (no
        pins provided) get the full default layout plus grid snapping.
        """
        pins_were_loaded = bool(self.pins)
        if not self.pins and self.type in DEFAULT_PINS:
            self.pins = [
                Pin(p.index, p.name, p.x, p.y) for p in DEFAULT_PINS[self.type]
            ]
        # Parameter backfill: a saved file may be missing keys that were
        # added in a later release (e.g. ``soft_start_time`` /
        # ``v_bus_initial`` on PFC_BOOST_CONTROLLER). Without this pass
        # the new properties dialog wouldn't list them, the backend
        # converter would fall back to its hard-coded defaults, and the
        # behaviour would silently drift from a freshly-placed component
        # of the same type. ``setdefault`` keeps every user-customised
        # value intact and only fills the gaps.
        if self.type in DEFAULT_PARAMETERS:
            defaults = DEFAULT_PARAMETERS[self.type]
            if not self.parameters:
                self.parameters = deepcopy(defaults)
            else:
                for key, value in defaults.items():
                    self.parameters.setdefault(key, deepcopy(value))

        saved_geometry: dict[str, tuple[float, float]] | None = None
        if pins_were_loaded:
            saved_geometry = {pin.name: (pin.x, pin.y) for pin in self.pins}

        _synchronize_special_component(self)

        if saved_geometry is not None:
            # Loaded from a file: restore the saved position of every pin
            # that survives synchronization by name, **snapped to the
            # current wiring grid**. The snap is a no-op for files saved
            # since the grid-alignment pass and migrates older files
            # where pins were authored at off-grid values like
            # ``(-30, ±25)`` or ``(-35, ±15)`` — those land at
            # ``(-40, ±20)`` after snapping, which is exactly where the
            # body art now draws the pin bubble. Wire endpoints attached
            # to the saved coordinates get the same snap in
            # ``SchematicScene._normalize_circuit_geometry`` so the wire
            # still meets the migrated pin.
            for pin in self.pins:
                saved = saved_geometry.get(pin.name)
                if saved is not None:
                    pin.x = _snap_to_pin_grid(saved[0])
                    pin.y = _snap_to_pin_grid(saved[1])
        else:
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
    elif component.type == ComponentType.MMC_CELL:
        _synchronize_mmc_cell(component)
    elif component.type in (ComponentType.SUM, ComponentType.SUBTRACTOR):
        _synchronize_sum_like_block(component)
    elif component.type == ComponentType.C_BLOCK:
        _synchronize_c_block(component)
    elif component.type == ComponentType.PWM_GENERATOR:
        _synchronize_pwm_duty_pin(component)
    elif component.type == ComponentType.HEATSINK:
        _synchronize_heatsink(component)
    elif component.type in (
        ComponentType.PI_CONTROLLER,
        ComponentType.GAIN,
        ComponentType.GOTO_LABEL,
        ComponentType.FROM_LABEL,
        # PFC / FOC / SIXSTEP controllers + the THREE_PHASE_VSI all
        # ship pin layouts that evolved (the PFC ``PWM`` output pin
        # landed in 1.1.2; the FOC / SIXSTEP ``PWM`` output pins + the
        # VSI's matching ``PWM`` input bus pin landed in 1.1.3 when
        # the wireless name-binding overrides were removed in favour
        # of explicit-wire-only binding). Running the default-layout
        # sync ensures saved files migrate forward: if the saved pin
        # set differs from the current template, it's replaced. The
        # ``__post_init__`` step that follows then snaps every
        # retained coord back to the user's saved geometry.
        ComponentType.PFC_BOOST_CONTROLLER,
        ComponentType.FOC_CONTROLLER,
        ComponentType.SIXSTEP_CONTROLLER,
        ComponentType.MMC_CONTROLLER,
        ComponentType.THREE_PHASE_VSI,
    ):
        _synchronize_default_pin_layout(component)
    elif component.type == ComponentType.SUBCIRCUIT_PORT:
        _synchronize_subcircuit_port_pin(component)
    elif component.type in (
        ComponentType.VOLTAGE_PROBE,
        ComponentType.VOLTAGE_PROBE_GND,
        ComponentType.CURRENT_PROBE,
    ):
        _synchronize_measurement_probe_pins(component)
    elif supports_motor_signal_bus(component.type):
        _synchronize_motor_signal_pin(component)
    else:
        _synchronize_thermal_port(component)

    _synchronize_control_sample_time(component)


def _synchronize_motor_signal_pin(component: Component) -> None:
    """Ensure a dynamic machine exposes its ``SIG`` signal-bus output pin.

    Motors saved before this feature carry only the electrical terminals;
    append the signal-bus pin (at its default template position) so the
    motor's observable traces can be wired to a demux + scope. Idempotent.
    """
    if not supports_motor_signal_bus(component.type):
        return
    if any(pin.name == MOTOR_SIGNAL_BUS_PIN_NAME for pin in component.pins):
        return
    template = DEFAULT_PINS.get(component.type, [])
    sig = next((p for p in template if p.name == MOTOR_SIGNAL_BUS_PIN_NAME), None)
    if sig is None:
        return
    component.pins.append(
        Pin(len(component.pins), MOTOR_SIGNAL_BUS_PIN_NAME, sig.x, sig.y)
    )


def _synchronize_subcircuit_port_pin(component: Component) -> None:
    """Place the SUBCIRCUIT_PORT marker's single pin based on its
    ``side`` parameter (left/right/top/bottom).

    The pin always faces *into* the subcircuit body (so wires from
    inner components attach naturally). The marker badge is drawn on
    the opposite side, pointing outward to suggest the direction the
    signal travels relative to the parent symbol.

    side=left  → pin at ( +40,   0)  (badge on the left side)
    side=right → pin at ( -40,   0)
    side=top   → pin at (   0, +25)
    side=bottom→ pin at (   0, -25)

    The pin's name mirrors the ``port_name`` parameter so the inner
    schematic shows the port label right at the connection point.
    """
    params = component.parameters or {}
    side = str(params.get("side", "left")).lower().strip()
    port_name = str(params.get("port_name", "port")).strip() or "port"

    PIN_OFFSETS = {
        "left":   ( 40.0,   0.0),
        "right":  (-40.0,   0.0),
        "top":    (  0.0,  25.0),
        "bottom": (  0.0, -25.0),
    }
    px, py = PIN_OFFSETS.get(side, PIN_OFFSETS["left"])

    new_pins = _snap_pin_layout([Pin(0, port_name, px, py)])

    # Don't rewrite pin list if it already matches — avoids spurious
    # change notifications on every property edit.
    if (
        len(component.pins) == 1
        and component.pins[0].name == new_pins[0].name
        and abs(component.pins[0].x - new_pins[0].x) < 0.1
        and abs(component.pins[0].y - new_pins[0].y) < 0.1
    ):
        return
    component.pins = new_pins


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


def _synchronize_heatsink(component: Component) -> None:
    """Rebuild the HEATSINK pin layout based on the ``n_devices`` param.

    Default layout has 4 device slots (DEV1..DEV4) plus the ambient
    reference (AMB). The user can bump ``n_devices`` up to 8 (covers a
    3-phase VSI: 6 switches + body diodes) or down to 1 (single device
    on a clip-on TO-220 sink). Pins are regenerated as
    ``[AMB, DEV1, DEV2, ..., DEVn]`` with the device pins evenly
    distributed along the right edge so they stay clickable. Idempotent:
    re-syncing without a parameter change leaves the layout untouched.

    Old pin geometry (user-customised positions) is dropped because the
    spacing rule applies once n_devices changes; if the user manually
    re-spaces pins after the sync, that survives the next save/load.
    """
    if component.type != ComponentType.HEATSINK:
        return
    raw = component.parameters.get("n_devices", 4)
    # ``raw or 4`` doesn't work — 0 is a legitimate int the user might
    # type while editing and we want to clamp it to 1, not jump up to
    # the default 4. So treat only None / non-coercible inputs as
    # "missing → default".
    if raw is None:
        n = 4
    else:
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = 4
    n = max(1, min(8, n))
    component.parameters["n_devices"] = n

    pins: list[Pin] = [Pin(0, "AMB", -40, 0)]
    # Device pins span the right edge in grid-aligned steps of 20 (the
    # snap grid) so distinct slots never collide after the post-init
    # snap pass — picking a continuous span would round adjacent pins
    # onto the same coordinate at higher n.
    step = 20.0
    # Symmetric layout around y=0. For even n, pins land at
    # ±step/2 ± step·k (so 4 pins → [-30, -10, +10, +30] → snap to
    # [-40, -20, +20, +40]). For odd n, the middle pin sits at y=0.
    offset = (n - 1) * step / 2.0
    ys = [-offset + i * step for i in range(n)]
    for idx, y in enumerate(ys, start=1):
        pins.append(Pin(idx, f"DEV{idx}", 40, int(round(y))))

    template = _snap_pin_layout(pins)
    component.pins = template


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


# ---------------------------------------------------------------------------
# MMC sub-module cell (dynamic pin layout)
# ---------------------------------------------------------------------------
# Pin layouts indexed by ``cell_topology``. Half-bridge has 4 pins
# (TOP, BOT, S1_G, S2_G), full-bridge has 6 (adds S3_G, S4_G for the
# right H-bridge leg). Pin indices stay stable for the shared TOP/BOT/
# S1_G/S2_G prefix so wires connecting to those pins survive a topology
# change.
_MMC_CELL_PIN_LAYOUTS: dict[str, list[Pin]] = {
    "Half-Bridge": [
        Pin(0, "TOP",  -30, -25),
        Pin(1, "BOT",  -30, 25),
        Pin(2, "S1_G",  30, -15),
        Pin(3, "S2_G",  30, 15),
    ],
    "Full-Bridge": [
        Pin(0, "TOP",  -30, -30),
        Pin(1, "BOT",  -30, 30),
        Pin(2, "S1_G",  30, -25),
        Pin(3, "S2_G",  30, -10),
        Pin(4, "S3_G",  30, 10),
        Pin(5, "S4_G",  30, 25),
    ],
}


def _synchronize_mmc_cell(component: Component) -> None:
    """Rewrite ``MMC_CELL`` pin layout to match the ``cell_topology``."""
    params = component.parameters
    topology = str(params.get("cell_topology") or "Half-Bridge")
    if topology not in _MMC_CELL_PIN_LAYOUTS:
        topology = "Half-Bridge"
    params["cell_topology"] = topology
    component.pins = _snap_pin_layout([
        Pin(p.index, p.name, p.x, p.y)
        for p in _MMC_CELL_PIN_LAYOUTS[topology]
    ])


def set_mmc_cell_topology(component: Component, topology: str) -> None:
    """Switch an ``MMC_CELL`` between half-bridge and full-bridge.

    Trims/extends pins to match the new layout. Wires connected to
    shared pins (TOP/BOT/S1_G/S2_G) keep their indices so they survive
    the topology change; wires on full-bridge-only pins (S3_G/S4_G)
    will dangle if you switch back to half-bridge.
    """
    component.parameters["cell_topology"] = topology
    _synchronize_mmc_cell(component)


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
