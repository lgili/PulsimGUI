"""SI prefix parsing and formatting utilities."""

import re
from typing import Tuple

SI_PREFIXES: dict[str, float] = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "m": 1e-3,
    "": 1,
    "k": 1e3,
    "K": 1e3,
    "meg": 1e6,
    "M": 1e6,
    "g": 1e9,
    "G": 1e9,
    "t": 1e12,
    "T": 1e12,
}

PREFIX_ORDER = ["f", "p", "n", "u", "m", "", "k", "meg", "G", "T"]

SI_PATTERN = re.compile(
    r"^\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*(f|p|n|u|µ|m|k|K|meg|M|g|G|t|T)?\s*$"
)


def parse_si_value(value_str: str) -> float:
    """
    Parse a string with SI prefix into a float.

    Examples:
        >>> parse_si_value("10k")
        10000.0
        >>> parse_si_value("4.7u")
        4.7e-6
        >>> parse_si_value("100n")
        1e-7
        >>> parse_si_value("1.5meg")
        1500000.0

    Args:
        value_str: String containing a number with optional SI prefix

    Returns:
        The numeric value as a float

    Raises:
        ValueError: If the string cannot be parsed
    """
    match = SI_PATTERN.match(value_str.strip())
    if not match:
        # Try parsing as plain float
        try:
            return float(value_str)
        except ValueError:
            raise ValueError(f"Cannot parse '{value_str}' as SI value")

    number = float(match.group(1))
    prefix = match.group(2) or ""

    if prefix not in SI_PREFIXES:
        raise ValueError(f"Unknown SI prefix: '{prefix}'")

    return number * SI_PREFIXES[prefix]


def format_si_value(value: float, unit: str = "", precision: int = 3) -> str:
    """
    Format a float value with appropriate SI prefix.

    Examples:
        >>> format_si_value(10000, "ohm")
        "10k ohm"
        >>> format_si_value(4.7e-6, "F")
        "4.7u F"
        >>> format_si_value(0.001)
        "1m"

    Args:
        value: The numeric value to format
        unit: Optional unit string to append
        precision: Number of significant digits

    Returns:
        Formatted string with SI prefix
    """
    if value == 0:
        return f"0{' ' + unit if unit else ''}"

    abs_value = abs(value)
    sign = "" if value >= 0 else "-"

    # Find appropriate prefix
    best_prefix = ""
    best_scaled = abs_value

    for prefix in PREFIX_ORDER:
        multiplier = SI_PREFIXES[prefix]
        scaled = abs_value / multiplier

        if 1 <= scaled < 1000:
            best_prefix = prefix
            best_scaled = scaled
            break
        elif scaled >= 1:
            best_prefix = prefix
            best_scaled = scaled

    # Format with appropriate precision
    if best_scaled >= 100:
        formatted = f"{sign}{best_scaled:.{max(0, precision-3)}f}"
    elif best_scaled >= 10:
        formatted = f"{sign}{best_scaled:.{max(0, precision-2)}f}"
    else:
        formatted = f"{sign}{best_scaled:.{max(0, precision-1)}f}"

    # Remove trailing zeros after decimal point
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")

    result = f"{formatted}{best_prefix}"
    if unit:
        result += f" {unit}"

    return result


def split_si_value(value_str: str) -> Tuple[float, str]:
    """
    Split a string into numeric value and prefix.

    Args:
        value_str: String containing number with optional SI prefix

    Returns:
        Tuple of (numeric_value, prefix)
    """
    match = SI_PATTERN.match(value_str.strip())
    if not match:
        return float(value_str), ""

    return float(match.group(1)), match.group(2) or ""


# Primary parameter and unit mapping for each component type
# Maps ComponentType name -> (parameter_name, unit)
PRIMARY_PARAMETERS: dict[str, tuple[str, str]] = {
    "RESISTOR": ("resistance", "Ω"),
    "CAPACITOR": ("capacitance", "F"),
    "INDUCTOR": ("inductance", "H"),
    "VOLTAGE_SOURCE": ("voltage", "V"),
    "CURRENT_SOURCE": ("current", "A"),
    "DIODE": ("vf", "V"),
    "ZENER_DIODE": ("vz", "V"),
    "LED": ("vf", "V"),
    "MOSFET_N": ("vth", "V"),
    "MOSFET_P": ("vth", "V"),
    "IGBT": ("vce_sat", "V"),
    "BJT_NPN": ("beta", ""),
    "BJT_PNP": ("beta", ""),
    "THYRISTOR": ("vgt", "V"),
    "TRIAC": ("vgt", "V"),
    "TRANSFORMER": ("turns_ratio", ":1"),
    "OP_AMP": ("gain", ""),
    "COMPARATOR": ("vos", "V"),
    "RELAY": ("coil_voltage", "V"),
    "FUSE": ("rating", "A"),
    "CIRCUIT_BREAKER": ("trip_current", "A"),
    "PI_CONTROLLER": ("kp", ""),
    "PID_CONTROLLER": ("kp", ""),
    "PWM_GENERATOR": ("frequency", "Hz"),
    "GAIN": ("gain", ""),
    "SUM": ("input_count", ""),
    "SUBTRACTOR": ("input_count", ""),
    "INTEGRATOR": ("gain", ""),
    "DIFFERENTIATOR": ("gain", ""),
    "LIMITER": ("max_value", ""),
    "RATE_LIMITER": ("max_rate", ""),
    "DELAY_BLOCK": ("delay", "s"),
    "SATURABLE_INDUCTOR": ("inductance", "H"),
    "COUPLED_INDUCTOR": ("coupling_coefficient", ""),
    "SNUBBER_RC": ("resistance", "Ω"),
}


def format_component_value(component_type_name: str, parameters: dict) -> str:
    """
    Format a component's primary parameter value for display.

    Args:
        component_type_name: The component type name (e.g., "RESISTOR")
        parameters: Dictionary of component parameters

    Returns:
        Formatted string with SI prefix and unit, or empty string if no primary parameter
    """
    if component_type_name not in PRIMARY_PARAMETERS:
        return ""

    param_name, unit = PRIMARY_PARAMETERS[component_type_name]
    value = parameters.get(param_name)

    if value is None:
        return ""

    # Special formatting for ratios
    if unit == ":1":
        return f"1:{value}"

    # Special formatting for dimensionless values
    if not unit:
        if isinstance(value, float):
            if value >= 1000 or value < 0.001:
                return f"{value:.2g}"
            return f"{value:g}"
        return str(value)

    # Standard SI formatting
    return format_si_value(value, unit)
