"""Contextual parameter help dialog for component properties."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.models.component import (
    Component,
    ComponentType,
    DEFAULT_PARAMETERS,
    HIDDEN_PARAMS,
    MOTOR_SIGNAL_BUS_CHANNELS,
    MOTOR_SIGNAL_BUS_PIN_NAME,
    supports_motor_signal_bus,
)


@dataclass(frozen=True)
class ParameterHelp:
    """Human-readable help metadata for one model parameter."""

    meaning: str
    where_to_find: str
    note: str = ""


@dataclass(frozen=True)
class ParameterHelpRow:
    """Expanded help row ready to render in the UI."""

    name: str
    default_value: str
    meaning: str
    where_to_find: str
    note: str
    search_url: str


_COMMON_PARAMETER_HELP: dict[str, ParameterHelp] = {
    "resistance": ParameterHelp(
        "Equivalent electrical resistance used by the simulator.",
        "Datasheet nominal value (R) and tolerance, or design target for external loads.",
    ),
    "capacitance": ParameterHelp(
        "Capacitance value of the capacitor model.",
        "Datasheet capacitance at the specified bias/frequency conditions.",
    ),
    "inductance": ParameterHelp(
        "Inductance used in dynamic current equations.",
        "Datasheet inductance measured at a stated current and test frequency.",
    ),
    "initial_voltage": ParameterHelp(
        "Initial capacitor voltage at t=0.",
        "Startup requirement or expected steady-state operating point before transient.",
    ),
    "initial_current": ParameterHelp(
        "Initial inductor current at t=0.",
        "Startup condition from previous operating point, pre-charge, or design expectation.",
    ),
    "waveform": ParameterHelp(
        "Time-domain source definition (DC, sine, pulse, PWL, etc.).",
        "Source specification in system requirements or bench stimulus profile.",
    ),
    "is_": ParameterHelp(
        "Saturation current of the exponential junction model.",
        "Estimate from reverse leakage/current-temperature data in datasheet curves.",
    ),
    "n": ParameterHelp(
        "Ideality (emission) factor of the PN junction equation.",
        "Extract from diode I-V curve slope around the intended operating current range.",
    ),
    "rs": ParameterHelp(
        "Series parasitic resistance in the conduction path.",
        "Estimate from forward I-V slope at high current (delta V / delta I).",
    ),
    "vth": ParameterHelp(
        "Device threshold voltage for gate/base driven turn-on models.",
        "MOSFET/IGBT datasheet threshold key (e.g., VGS(th)).",
    ),
    "lambda_": ParameterHelp(
        "Channel-length modulation/output conductance factor.",
        "Fit from output-characteristic slope in saturation region (ID vs VDS).",
    ),
    "g_on": ParameterHelp(
        "On-state conductance (1 / Ron) for simplified switch models.",
        "Extract from on-state voltage drop vs current (slope around nominal current).",
    ),
    "g_off": ParameterHelp(
        "Off-state leakage conductance.",
        "Estimate from datasheet leakage current at blocking voltage (Ioff / Voff).",
    ),
    "v_ce_sat": ParameterHelp(
        "IGBT saturation voltage drop in conduction.",
        "Datasheet VCE(sat) at the reference current/temperature.",
    ),
    "beta": ParameterHelp(
        "BJT DC current gain (hFE).",
        "Datasheet hFE/β table at operating collector current and temperature.",
    ),
    "vbe_sat": ParameterHelp(
        "BJT base-emitter voltage in saturation.",
        "Datasheet VBE(sat) in the switching/saturation conditions.",
    ),
    "vce_sat": ParameterHelp(
        "BJT collector-emitter saturation voltage.",
        "Datasheet VCE(sat) at target collector/base drive levels.",
    ),
    "ron": ParameterHelp(
        "Closed-switch resistance.",
        "Datasheet on-state resistance/contact resistance in the intended operating region.",
    ),
    "roff": ParameterHelp(
        "Open-switch resistance approximation.",
        "Choose high value to represent leakage while keeping numerical stability.",
    ),
    "initial_state": ParameterHelp(
        "Initial boolean state for controlled switch elements.",
        "Control startup requirement at simulation t=0.",
    ),
    "turns_ratio": ParameterHelp(
        "Transformer turns ratio Np/Ns used by idealized model.",
        "Magnetics design target or datasheet turns specification.",
    ),
    "lm": ParameterHelp(
        "Magnetizing inductance of transformer primary.",
        "Datasheet magnetizing inductance (Lm) or no-load test extraction.",
    ),
    "frequency": ParameterHelp(
        "Operating/switching frequency in Hz.",
        "Control design target (fs) or oscillator specification.",
    ),
    "duty_cycle": ParameterHelp(
        "Normalized duty command (0..1) in PWM generator.",
        "Control law output or nominal duty from converter design equations.",
    ),
    "carrier": ParameterHelp(
        "Carrier waveform type used for PWM comparison.",
        "Control strategy choice (typically sawtooth or triangle).",
    ),
    "gain": ParameterHelp(
        "Static multiplier applied to the input signal.",
        "Control tuning worksheet or transfer-function derivation.",
    ),
    "kp": ParameterHelp(
        "Proportional gain of the controller block.",
        "Controller tuning method (pole placement, Ziegler-Nichols, loop shaping).",
    ),
    "ki": ParameterHelp(
        "Integral gain of the controller block.",
        "Controller tuning from desired low-frequency tracking/error rejection.",
    ),
    "kd": ParameterHelp(
        "Derivative gain of the controller block.",
        "Controller tuning from desired damping/noise trade-off.",
    ),
    "output_min": ParameterHelp(
        "Lower saturation limit for controller output.",
        "Set from actuator or duty-command minimum constraints.",
    ),
    "output_max": ParameterHelp(
        "Upper saturation limit for controller output.",
        "Set from actuator or duty-command maximum constraints.",
    ),
    "anti_windup": ParameterHelp(
        "Enable integral anti-windup logic when output saturates.",
        "Best-practice control setting; usually enabled for bounded actuators.",
    ),
    "sample_time": ParameterHelp(
        "Discrete sample time Ts. 0 means automatic/continuous scheduling.",
        "From controller execution frequency: Ts = 1 / Fcontrol.",
        "Choose Ts at least 10x to 20x faster than loop bandwidth.",
    ),
    "open_loop_gain": ParameterHelp(
        "Open-loop gain of op-amp macromodel.",
        "Datasheet AOL or DC open-loop gain.",
    ),
    "gbw": ParameterHelp(
        "Gain-bandwidth product of op-amp model.",
        "Datasheet GBW (unity-gain bandwidth).",
    ),
    "slew_rate": ParameterHelp(
        "Maximum output slope limitation (V/s).",
        "Datasheet slew rate (SR).",
    ),
    "offset": ParameterHelp(
        "Input-referred offset in op-amp/comparator style blocks.",
        "Datasheet input offset voltage (Vos) or measured trim.",
    ),
    "rail_low": ParameterHelp(
        "Lower output saturation rail.",
        "Supply and output-stage swing limitations from datasheet.",
    ),
    "rail_high": ParameterHelp(
        "Upper output saturation rail.",
        "Supply and output-stage swing limitations from datasheet.",
    ),
    "threshold": ParameterHelp(
        "Comparator switching threshold.",
        "Design setpoint or sensor/comparator reference value.",
    ),
    "hysteresis": ParameterHelp(
        "Comparator hysteresis band around threshold.",
        "Noise immunity requirement and acceptable switching dead-band.",
    ),
    "high": ParameterHelp(
        "Comparator high output level.",
        "Digital/control interface high-level requirement.",
    ),
    "low": ParameterHelp(
        "Comparator low output level.",
        "Digital/control interface low-level requirement.",
    ),
    "source": ParameterHelp(
        "Path to C source file implementing the custom control block.",
        "Project source tree or generated block implementation file.",
    ),
    "n_inputs": ParameterHelp(
        "Number of scalar inputs exposed by C-Block ABI.",
        "From C-Block function signature and control architecture.",
    ),
    "n_outputs": ParameterHelp(
        "Number of scalar outputs exposed by C-Block ABI.",
        "From C-Block function signature and control architecture.",
    ),
    "extra_cflags": ParameterHelp(
        "Additional compiler flags for C-Block build.",
        "Toolchain requirement (include paths, feature flags, optimization options).",
    ),
    "thermal_enabled": ParameterHelp(
        "Enable electrothermal model coupling.",
        "Turn on when thermal behavior/junction temperature must affect results.",
    ),
    "thermal_rth": ParameterHelp(
        "Junction-to-ambient equivalent thermal resistance (K/W).",
        "Datasheet thermal resistance Rth(j-a) or Rth(j-c) plus sink path model.",
    ),
    "thermal_cth": ParameterHelp(
        "Equivalent thermal capacitance (J/K).",
        "Fit from transient thermal impedance Zth curves.",
    ),
    "thermal_temp_init": ParameterHelp(
        "Initial junction/device temperature (degC).",
        "Ambient/startup condition for transient thermal simulation.",
    ),
    "thermal_alpha": ParameterHelp(
        "Temperature coefficient used for electrical parameter scaling.",
        "Datasheet normalized resistance/conduction-vs-temperature curves.",
    ),
    "switching_loss_model": ParameterHelp(
        "Switching loss mode (scalar or table-driven).",
        "Choose based on available datasheet energy curves and required fidelity.",
    ),
    "switching_eon_j": ParameterHelp(
        "Turn-on energy per switching event (J).",
        "Datasheet Eon at matching current, voltage, gate drive, and temperature.",
    ),
    "switching_eoff_j": ParameterHelp(
        "Turn-off energy per switching event (J).",
        "Datasheet Eoff at matching current, voltage, gate drive, and temperature.",
    ),
    "switching_err_j": ParameterHelp(
        "Reverse-recovery related energy per event (J), when applicable.",
        "Datasheet Err/Erec for diode or body-diode recovery behavior.",
    ),
}


_COMPONENT_PARAMETER_OVERRIDES: dict[ComponentType, dict[str, ParameterHelp]] = {
    ComponentType.MOSFET_N: {
        "kp": ParameterHelp(
            "MOSFET transconductance factor of the square-law channel model.",
            "Estimate from transfer curve slope ID vs VGS above threshold.",
        ),
    },
    ComponentType.MOSFET_P: {
        "kp": ParameterHelp(
            "PMOS transconductance factor magnitude in the square-law channel model.",
            "Estimate from |ID| vs VGS transfer curve in conduction region.",
        ),
    },
    ComponentType.PI_CONTROLLER: {
        "kp": ParameterHelp(
            "PI proportional gain acting on instantaneous error.",
            "Controller tuning from crossover target and plant gain.",
        ),
        "ki": ParameterHelp(
            "PI integral gain acting on accumulated error.",
            "Controller tuning from steady-state error and desired low-frequency loop gain.",
        ),
    },
    ComponentType.PID_CONTROLLER: {
        "kp": ParameterHelp(
            "PID proportional gain acting on instantaneous error.",
            "Controller tuning from crossover target and plant gain.",
        ),
        "ki": ParameterHelp(
            "PID integral gain acting on accumulated error.",
            "Controller tuning from low-frequency error rejection goals.",
        ),
        "kd": ParameterHelp(
            "PID derivative gain acting on error slope.",
            "Controller tuning from damping target and noise sensitivity limits.",
        ),
    },
    ComponentType.PFC_BOOST_CONTROLLER: {
        "mode": ParameterHelp(
            "Operating mode. CCM (continuous conduction, recommended for "
            "240–1000 W) keeps i_L > 0 every switching cycle; DCM lets i_L "
            "drop to zero (only worthwhile below ~150 W).",
            "Application power band. CCM for >300 W is standard practice.",
        ),
        "v_bus_ref": ParameterHelp(
            "Target DC-bus voltage (V) regulated by the outer loop. The "
            "universal-input PFC standard is 400 V (high enough for 264 Vrms "
            "input without saturation).",
            "Downstream-converter datasheet (DC-link voltage rating).",
        ),
        "v_bus_max": ParameterHelp(
            "Hard upper bound on V_bus (over-voltage trip / clamp).",
            "Bus capacitor rating minus margin.",
        ),
        "v_bus_min": ParameterHelp(
            "Lower bound used during startup so the outer loop doesn't "
            "saturate before the bridge has charged the bus.",
            "Front-end peak (Vac_pk · √2) — bus can't go below it.",
        ),
        "voltage_kp": ParameterHelp(
            "Outer voltage loop proportional gain (V_bus error → I_pk_ref).",
            "Tune for ~10 Hz crossover — well below 2·f_line so the 120 Hz "
            "bus ripple is NOT amplified into the current reference.",
        ),
        "voltage_ki": ParameterHelp(
            "Outer voltage loop integral gain.",
            "Sets the DC bus regulation accuracy. Ki ≈ Kp · ω_c / 5 is a "
            "safe starting point.",
        ),
        "i_pk_limit": ParameterHelp(
            "Saturation on the outer-loop output (max peak input current). "
            "Prevents inductor saturation and inrush during a load step.",
            "Inductor saturation current and MOSFET pulsed-current rating.",
        ),
        "current_kp": ParameterHelp(
            "Inner current loop proportional gain (i_L error → duty).",
            "Tune from L_boost / R_dcr: Kp ≈ L · ω_c (rad/s). For L = 1 mH "
            "and ω_c = 2π·5 kHz → Kp ≈ 31.4.",
        ),
        "current_ki": ParameterHelp(
            "Inner current loop integral gain.",
            "Cancels the inductor pole: Ki ≈ R_dcr · ω_c. For R_dcr = 0.1 Ω "
            "and ω_c = 2π·5 kHz → Ki ≈ 3140.",
        ),
        "duty_max": ParameterHelp(
            "Upper duty clamp (0..1). Leave a small margin (≤ 0.95) so the "
            "bus capacitor never charges through the body diode.",
            "MOSFET datasheet (gate-drive timing) and dead-time budget.",
        ),
        "vac_pk_nom": ParameterHelp(
            "Nominal Vac peak (V) used as the sine-reference scale. For "
            "230 Vrms line: 230·√2 ≈ 325 V; for 110 Vrms low-line: 156 V.",
            "Worst-case input line voltage at nominal.",
        ),
        "f_line": ParameterHelp(
            "Mains frequency (Hz). 50 Hz (EU/SA) or 60 Hz (NA). Used by the "
            "outer loop's low-pass to track the line cycle.",
            "Local grid standard.",
        ),
        "f_sw": ParameterHelp(
            "Inner-loop PWM carrier frequency (Hz). 65 kHz is the modern "
            "high-power PFC default — high enough for a small inductor, "
            "low enough to keep MOSFET losses manageable.",
            "Inverter MOSFET / driver datasheet (max f_sw, dead-time).",
        ),
        # NOTE: as of v1.1.3 the wireless-binding override parameters
        # (``boost_mosfet_name`` / ``v_bus_node_name`` / ``v_ac_node_name``
        # / ``i_l_branch_name``) have been removed. The MOSFET is
        # identified by wiring the ``PWM`` output pin to its gate; the
        # V_bus / V_rect nodes are identified by wiring the ``VBUS`` /
        # ``VAC`` input pins to voltage probes on those nodes; the i_L
        # branch is identified by wiring the ``IL`` input pin to a
        # current probe on the boost inductor.
    },
    ComponentType.FOC_CONTROLLER: {
        "speed_kp": ParameterHelp(
            "Outer speed loop proportional gain (Δω → iq_ref).",
            "Tune for the desired speed bandwidth. Start small and double until "
            "rise time is acceptable; back off if overshoot exceeds ~10%.",
        ),
        "speed_ki": ParameterHelp(
            "Outer speed loop integral gain (∫Δω → iq_ref).",
            "Sets the steady-state speed error. Set so the integral takes "
            "10×–20× the rise time to wind up the current reference fully.",
        ),
        "current_kp": ParameterHelp(
            "Inner d/q current loops proportional gain (shared across axes).",
            "Tune from R_s and L_s and the desired current-loop bandwidth: "
            "Kp ≈ L_s · ω_c, where ω_c is the target loop crossover (rad/s).",
        ),
        "current_ki": ParameterHelp(
            "Inner d/q current loops integral gain (shared across axes).",
            "Sets the closed-loop pole at the motor stator pole: Ki ≈ R_s · ω_c.",
        ),
        "id_ref": ParameterHelp(
            "d-axis current reference (A). Zero for non-salient PMSM (MTPA at "
            "low speed); use a negative value for field-weakening above base speed.",
            "Motor + drive datasheet (Ld/Lq, base speed, max DC bus).",
        ),
        "iq_limit": ParameterHelp(
            "q-axis current saturation (A) — clamps torque-producing current "
            "to a safe per-unit value of the rated stator current.",
            "Motor datasheet (rated stator current) and inverter rating.",
        ),
        "v_limit_frac": ParameterHelp(
            "Voltage clamp on the inverse-Park outputs, as a fraction of Vdc/2.",
            "Modulation ceiling. 0.92 is a safe linear margin; 1.0 hits over-"
            "modulation (3rd-harmonic injection); >1 enters 6-step territory.",
        ),
        "speed_ramp_s": ParameterHelp(
            "Speed-reference ramp time (s) — softens step changes in SP so the "
            "outer PI doesn't saturate or trip the q-current limit at startup.",
            "Application requirement (e.g. compressor soft-start, traction).",
        ),
        "switching_frequency_hz": ParameterHelp(
            "PWM carrier frequency for the inverse-Park modulator that drives "
            "the VSI switches.",
            "Inverter datasheet (max f_sw) and motor audible-noise / loss budget.",
        ),
        "speed_ref_rpm": ParameterHelp(
            "Fallback speed reference (rpm) used when the SP pin is unwired.",
            "Use as a constant baseline; for runtime control, wire a CONSTANT "
            "(or any signal source) into the SP pin instead.",
        ),
        "v_bus": ParameterHelp(
            "Optional explicit DC-bus magnitude (V). Leave 0 to read from the "
            "VSI's vdc setting at simulate time. Used to normalise modulation.",
            "Front-end nominal DC bus (e.g. 320 V doubler, 400 V PFC).",
        ),
        # NOTE: as of v1.1.3 ``pmsm_name`` / ``vsi_name`` overrides are
        # gone — the observed PMSM is identified by wiring FB to the
        # motor's SIG bus, and the driven VSI by wiring the PWM output
        # to the inverter's PWM bus input.
    },
    ComponentType.SIXSTEP_CONTROLLER: {
        "speed_kp": ParameterHelp(
            "Outer speed-loop proportional gain (Δω → duty).",
            "Tune for the desired speed bandwidth. The 6-step law has no "
            "inner current loop, so Kp couples to duty directly — start "
            "small (~1e-3) and increase until rise time is acceptable.",
        ),
        "speed_ki": ParameterHelp(
            "Outer speed-loop integral gain (∫Δω → duty).",
            "Sets steady-state speed error. Anti-windup is built in: the "
            "integrator is held when the duty clamps at 0 or duty_max.",
        ),
        "duty_max": ParameterHelp(
            "Maximum modulation duty (0..1) applied to the active "
            "high-side switch each sector.",
            "Inverter ratings (deadtime margin) and motor ceiling. 0.95 "
            "leaves headroom for sensorless BEMF observation windows.",
        ),
        "speed_ref_rpm": ParameterHelp(
            "Fallback speed reference (rpm) used when the SP pin is unwired.",
            "Use as a constant baseline; wire a CONSTANT (or any signal "
            "source) into the SP pin for runtime control.",
        ),
        "speed_ramp_s": ParameterHelp(
            "Speed-reference ramp time (s). Softens step changes in SP and "
            "gives the rotor (and any sensorless observer) time to lock.",
            "Application requirement; raise if startup stalls.",
        ),
        "switching_frequency_hz": ParameterHelp(
            "PWM carrier frequency for the active high-side switch of the "
            "current commutation sector.",
            "Inverter datasheet (max f_sw) and motor audible-noise budget.",
        ),
        "sector_advance_deg": ParameterHelp(
            "Electrical-angle offset (deg) added before sector lookup. "
            "Used by production drives to align commutation with the "
            "BEMF peak instead of the zero-crossing.",
            "Empirical; start at 0 and adjust ±15° to peak torque/efficiency.",
        ),
        # NOTE: as of v1.1.3 ``pmsm_name`` / ``vsi_name`` overrides are
        # gone — both bindings are wire-traced (FB → SIG bus, PWM →
        # inverter PWM bus input).
    },
}

_DATASHEET_SEARCH_TERMS: dict[str, str] = {
    "resistance": "resistance tolerance",
    "capacitance": "capacitance tolerance ESR",
    "inductance": "inductance saturation current",
    "initial_voltage": "startup initial condition",
    "initial_current": "startup initial condition",
    "is_": "saturation current Is",
    "n": "ideality factor n",
    "rs": "series resistance",
    "vth": "VGS(th) threshold voltage",
    "lambda_": "output conductance channel length modulation",
    "g_on": "on resistance RDS(on) VCE(sat)",
    "g_off": "off leakage current",
    "v_ce_sat": "VCE(sat)",
    "beta": "hFE DC current gain",
    "vbe_sat": "VBE(sat)",
    "vce_sat": "VCE(sat)",
    "ron": "RDS(on) on resistance",
    "roff": "off leakage current",
    "turns_ratio": "turns ratio magnetics",
    "lm": "magnetizing inductance",
    "frequency": "switching frequency",
    "duty_cycle": "duty cycle",
    "carrier": "carrier waveform",
    "gain": "gain transfer function",
    "kp": "controller Kp",
    "ki": "controller Ki",
    "kd": "controller Kd",
    "output_min": "output saturation limits",
    "output_max": "output saturation limits",
    "anti_windup": "anti windup",
    "sample_time": "discrete sample time Ts",
    "open_loop_gain": "AOL open loop gain",
    "gbw": "gain bandwidth product GBW",
    "slew_rate": "slew rate SR",
    "offset": "input offset voltage Vos",
    "rail_low": "output swing low rail",
    "rail_high": "output swing high rail",
    "threshold": "threshold voltage",
    "hysteresis": "hysteresis band",
    "high": "logic high output level",
    "low": "logic low output level",
    "source": "C block source code ABI",
    "n_inputs": "C block ABI inputs",
    "n_outputs": "C block ABI outputs",
    "extra_cflags": "compiler flags include path",
    "thermal_enabled": "electrothermal modeling",
    "thermal_rth": "thermal resistance Rth",
    "thermal_cth": "thermal capacitance Cth",
    "thermal_temp_init": "initial junction temperature",
    "thermal_alpha": "temperature coefficient alpha",
    "switching_loss_model": "switching loss model Eon Eoff",
    "switching_eon_j": "Eon switching energy",
    "switching_eoff_j": "Eoff switching energy",
    "switching_err_j": "Err recovery energy",
}

_PART_HINT_KEYS: tuple[str, ...] = (
    "part_number",
    "part",
    "mpn",
    "manufacturer_part_number",
    "device",
    "model",
    "model_name",
)


def _format_default_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (int, bool)):
        return str(value)
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    except TypeError:
        return str(value)


def _parameter_help(component_type: ComponentType, parameter_name: str) -> ParameterHelp:
    override = _COMPONENT_PARAMETER_OVERRIDES.get(component_type, {}).get(parameter_name)
    if override is not None:
        return override
    common = _COMMON_PARAMETER_HELP.get(parameter_name)
    if common is not None:
        return common
    return ParameterHelp(
        meaning=f"Model parameter `{parameter_name}`.",
        where_to_find=(
            "Map this parameter to the equivalent field in the component model datasheet "
            "or in your control design worksheet."
        ),
    )


def _component_part_hint(component: Component) -> str:
    for key in _PART_HINT_KEYS:
        value = component.parameters.get(key)
        if isinstance(value, str):
            token = value.strip()
            if token:
                return token
    return ""


def build_datasheet_search_query(component: Component, parameter_name: str) -> str:
    """Build a user-friendly web search query for one component parameter."""
    part_hint = _component_part_hint(component)
    component_hint = component.type.name.replace("_", " ").title()
    parameter_hint = _DATASHEET_SEARCH_TERMS.get(parameter_name, parameter_name.replace("_", " "))

    if part_hint:
        return f"{part_hint} datasheet {parameter_hint} test conditions"
    return f"{component_hint} datasheet {parameter_hint} parameter"


def build_datasheet_search_url(component: Component, parameter_name: str) -> str:
    """Build an external web URL for the parameter-focused datasheet search."""
    query = build_datasheet_search_query(component, parameter_name)
    return f"https://www.google.com/search?q={quote_plus(query)}"


def build_component_help_rows(component: Component) -> list[ParameterHelpRow]:
    """Build ordered help rows for the currently edited component."""
    hidden = HIDDEN_PARAMS.get(component.type, frozenset())
    defaults = DEFAULT_PARAMETERS.get(component.type, {})
    rows: list[ParameterHelpRow] = []

    for name, current_value in component.parameters.items():
        if name in hidden:
            continue
        help_info = _parameter_help(component.type, name)
        default_value = defaults.get(name, current_value)
        rows.append(
            ParameterHelpRow(
                name=name,
                default_value=_format_default_value(default_value),
                meaning=help_info.meaning,
                where_to_find=help_info.where_to_find,
                note=help_info.note,
                search_url=build_datasheet_search_url(component, name),
            )
        )
    return rows


def _dialog_color_tokens(is_dark: bool) -> dict[str, str]:
    if is_dark:
        return {
            "bg": "#0b1220",
            "surface": "#111a2d",
            "surface_alt": "#16223a",
            "border": "#27364f",
            "text": "#e6edf8",
            "muted": "#a9b7cd",
            "accent": "#34a6ff",
            "accent_soft": "#1d3d66",
            "badge_bg": "#173454",
            "badge_text": "#9fd3ff",
        }
    return {
        "bg": "#f4f7fb",
        "surface": "#ffffff",
        "surface_alt": "#f7fafc",
        "border": "#dbe4f0",
        "text": "#1b2a3a",
        "muted": "#54657a",
        "accent": "#1f78d1",
        "accent_soft": "#e8f3ff",
        "badge_bg": "#e8f3ff",
        "badge_text": "#1f5f9c",
    }


def _help_html_styles(is_dark: bool) -> str:
    c = _dialog_color_tokens(is_dark)
    return f"""
    <style>
      body {{
        margin: 0;
        padding: 0;
        font-family: "Segoe UI", "SF Pro Text", "Noto Sans", sans-serif;
        color: {c["text"]};
        background: {c["surface"]};
      }}
      .subtitle {{
        margin: 0 0 14px 0;
        color: {c["muted"]};
        line-height: 1.45;
      }}
      .table-wrap {{
        border: 1px solid {c["border"]};
        border-radius: 12px;
        overflow: hidden;
      }}
      table {{
        border-collapse: collapse;
        width: 100%;
      }}
      thead tr {{
        background: {c["surface_alt"]};
      }}
      th {{
        padding: 10px 12px;
        text-align: left;
        font-size: 12px;
        font-weight: 700;
        color: {c["muted"]};
        border-bottom: 1px solid {c["border"]};
      }}
      td {{
        vertical-align: top;
        padding: 10px 12px;
        border-bottom: 1px solid {c["border"]};
        font-size: 13px;
        line-height: 1.4;
      }}
      tbody tr:last-child td {{
        border-bottom: none;
      }}
      tbody tr:nth-child(even) {{
        background: {c["surface_alt"]};
      }}
      code {{
        font-family: "SF Mono", "Consolas", "Menlo", monospace;
        font-size: 12px;
        color: {c["text"]};
        background: {c["accent_soft"]};
        border: 1px solid {c["border"]};
        padding: 2px 5px;
        border-radius: 5px;
      }}
      .action {{
        display: inline-block;
        text-decoration: none;
        color: #fff;
        background: {c["accent"]};
        border: 1px solid {c["accent"]};
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
        padding: 5px 10px;
      }}
      .action:hover {{
        filter: brightness(1.06);
      }}
      .tip {{
        margin-top: 14px;
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid {c["border"]};
        background: {c["surface_alt"]};
        color: {c["muted"]};
      }}
    </style>
    """


def _motor_signal_bus_section(component: Component) -> str:
    """Render the SIG signal-bus reference table for a dynamic machine.

    Lists every demux output lane → backend signal key in order, so the user
    can wire a SIGNAL_DEMUX → scope without guessing what each output carries.
    Returns empty when the component has no signal bus.
    """
    if not supports_motor_signal_bus(component.type):
        return ""
    motor_name = html.escape(component.name or "M1")
    rows_html = "\n".join(
        "<tr>"
        f"<td><code>OUT{idx + 1}</code></td>"
        f"<td>{html.escape(label)}</td>"
        f"<td><code>{motor_name}.{html.escape(suffix)}</code></td>"
        "</tr>"
        for idx, (suffix, label) in enumerate(MOTOR_SIGNAL_BUS_CHANNELS)
    )
    return (
        "<h4 style='margin:12px 0 4px 0;'>"
        f"{html.escape(MOTOR_SIGNAL_BUS_PIN_NAME)} signal bus"
        "</h4>"
        "<p class='subtitle' style='margin-bottom:6px;'>"
        f"Wire the <code>{html.escape(MOTOR_SIGNAL_BUS_PIN_NAME)}</code> pin to a "
        "<code>SIGNAL_DEMUX</code> and tap each demux output (in order) into a "
        "scope channel. The same backend keys are used by post-sim and probe "
        "lookups, so dropping a curve into a math expression also works."
        "</p>"
        "<div class='table-wrap'>"
        "<table><thead><tr>"
        "<th>Demux output</th>"
        "<th>Channel</th>"
        "<th>Backend signal key</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
        "</div>"
    )


def render_component_help_html(component: Component, *, is_dark: bool = False) -> str:
    """Render parameter-help content as compact HTML."""
    rows = build_component_help_rows(component)
    component_name = component.type.name.replace("_", " ").title()
    title = html.escape(f"{component_name} Parameter Help")
    styles = _help_html_styles(is_dark)
    bus_section = _motor_signal_bus_section(component)

    if not rows:
        return (
            "<html><body>"
            f"{styles}"
            f"<h3>{title}</h3>"
            f"{bus_section}"
            "<p>No editable parameters were found for this component.</p>"
            "</body></html>"
        )

    row_markup: list[str] = []
    for row in rows:
        note_markup = (
            f"<div style='margin-top:4px;color:#666;'><em>{html.escape(row.note)}</em></div>"
            if row.note
            else ""
        )
        row_markup.append(
            "<tr>"
            f"<td><code>{html.escape(row.name)}</code></td>"
            f"<td><code>{html.escape(row.default_value)}</code></td>"
            f"<td>{html.escape(row.meaning)}</td>"
            f"<td>{html.escape(row.where_to_find)}{note_markup}</td>"
            f"<td><a class='action' href='{html.escape(row.search_url, quote=True)}'>Open Datasheet Search</a></td>"
            "</tr>"
        )

    rows_html = "\n".join(row_markup)
    return (
        "<html><body>"
        f"{styles}"
        f"<h3 style='margin:0 0 6px 0;'>{title}</h3>"
        f"{bus_section}"
        "<p class='subtitle'>"
        "Use this table as a practical guide: what each parameter means, "
        "typical datasheet keys/sources, and the model default used by PulsimGui."
        "</p>"
        "<div class='table-wrap'>"
        "<table><thead><tr>"
        "<th>Parameter</th>"
        "<th>Default</th>"
        "<th>Meaning</th>"
        "<th>Where to get it</th>"
        "<th>Action</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
        "</div>"
        "<div class='tip'>"
        "Tip: keep operating point (current, voltage, temperature, and gate drive) "
        "consistent with the datasheet test conditions when copying values."
        "</div>"
        "</body></html>"
    )


class ComponentParameterHelpDialog(QDialog):
    """Dialog that shows contextual component parameter help."""

    def __init__(self, component: Component, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._component = component
        component_name = component.type.name.replace("_", " ").title()
        self.setWindowTitle(f"Help - {component_name}")
        self.resize(980, 620)
        self.setMinimumSize(860, 520)

        is_dark = (
            self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        )
        colors = _dialog_color_tokens(is_dark)
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {colors["bg"]};
            }}
            QFrame#HelpHeader {{
                background: {colors["surface"]};
                border: 1px solid {colors["border"]};
                border-radius: 14px;
            }}
            QLabel#HelpTitle {{
                color: {colors["text"]};
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#HelpSubtitle {{
                color: {colors["muted"]};
                font-size: 12px;
            }}
            QLabel#HelpBadge {{
                color: {colors["badge_text"]};
                background: {colors["badge_bg"]};
                border: 1px solid {colors["border"]};
                border-radius: 9px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QTextBrowser {{
                background: {colors["surface"]};
                border: 1px solid {colors["border"]};
                border-radius: 12px;
                padding: 8px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QFrame(self)
        header.setObjectName("HelpHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(6)

        title = QLabel(f"{component_name} Parameter Guide", header)
        title.setObjectName("HelpTitle")
        header_layout.addWidget(title)

        subtitle = QLabel(
            "Review model defaults, parameter meaning, and practical datasheet lookup hints.",
            header,
        )
        subtitle.setObjectName("HelpSubtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)

        badges_row = QWidget(header)
        badges_layout = QHBoxLayout(badges_row)
        badges_layout.setContentsMargins(0, 0, 0, 0)
        badges_layout.setSpacing(6)

        type_badge = QLabel(f"Type: {component_name}", badges_row)
        type_badge.setObjectName("HelpBadge")
        badges_layout.addWidget(type_badge)

        param_count = len(build_component_help_rows(component))
        count_badge = QLabel(f"Parameters: {param_count}", badges_row)
        count_badge.setObjectName("HelpBadge")
        badges_layout.addWidget(count_badge)

        part_hint = _component_part_hint(component)
        if part_hint:
            part_badge = QLabel(f"Part: {part_hint}", badges_row)
            part_badge.setObjectName("HelpBadge")
            badges_layout.addWidget(part_badge)

        badges_layout.addStretch(1)
        header_layout.addWidget(badges_row)
        layout.addWidget(header)

        self._browser = QTextBrowser(self)
        self._browser.setOpenExternalLinks(True)
        self._browser.setHtml(render_component_help_html(component, is_dark=is_dark))
        layout.addWidget(self._browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)
