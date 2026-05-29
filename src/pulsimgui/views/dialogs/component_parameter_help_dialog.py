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

from pulsimgui.models.component import Component, ComponentType, DEFAULT_PARAMETERS, HIDDEN_PARAMS


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


def render_component_help_html(component: Component, *, is_dark: bool = False) -> str:
    """Render parameter-help content as compact HTML."""
    rows = build_component_help_rows(component)
    component_name = component.type.name.replace("_", " ").title()
    title = html.escape(f"{component_name} Parameter Help")
    styles = _help_html_styles(is_dark)

    if not rows:
        return (
            "<html><body>"
            f"{styles}"
            f"<h3>{title}</h3>"
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
