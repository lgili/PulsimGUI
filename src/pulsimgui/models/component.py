"""Component model for circuit elements."""

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from uuid import UUID, uuid4


class ComponentType(Enum):
    """Types of circuit components."""

    RESISTOR = auto()
    CAPACITOR = auto()
    INDUCTOR = auto()
    VOLTAGE_SOURCE = auto()
    CURRENT_SOURCE = auto()
    GROUND = auto()
    DIODE = auto()
    MOSFET_N = auto()
    MOSFET_P = auto()
    IGBT = auto()
    SWITCH = auto()
    TRANSFORMER = auto()
    PI_CONTROLLER = auto()
    PID_CONTROLLER = auto()
    MATH_BLOCK = auto()
    PWM_GENERATOR = auto()
    ELECTRICAL_SCOPE = auto()
    THERMAL_SCOPE = auto()
    SIGNAL_MUX = auto()
    SIGNAL_DEMUX = auto()
    SUBCIRCUIT = auto()  # Hierarchical subcircuit instance


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


def _generate_stacked_pins(
    count: int,
    x: float,
    name_prefix: str,
    start_index: int = 0,
) -> list[Pin]:
    """Create evenly spaced pins stacked vertically."""

    if count <= 0:
        return []

    spacing = 18.0
    offset = (count - 1) * spacing / 2.0
    pins: list[Pin] = []
    for idx in range(count):
        pins.append(
            Pin(
                start_index + idx,
                f"{name_prefix}{idx + 1}",
                x,
                -offset + idx * spacing,
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


def _scope_label_prefix(comp_type: ComponentType) -> str:
    """Get default label prefix for scope channels based on component type."""

    return "CH" if comp_type == ComponentType.ELECTRICAL_SCOPE else "T"


# Default pin configurations for each component type
DEFAULT_PINS: dict[ComponentType, list[Pin]] = {
    ComponentType.RESISTOR: [Pin(0, "1", -30, 0), Pin(1, "2", 30, 0)],
    ComponentType.CAPACITOR: [Pin(0, "+", -20, 0), Pin(1, "-", 20, 0)],
    ComponentType.INDUCTOR: [Pin(0, "1", -30, 0), Pin(1, "2", 30, 0)],
    ComponentType.VOLTAGE_SOURCE: [Pin(0, "+", 0, -25), Pin(1, "-", 0, 25)],
    ComponentType.CURRENT_SOURCE: [Pin(0, "+", 0, -25), Pin(1, "-", 0, 25)],
    ComponentType.GROUND: [Pin(0, "gnd", 0, -10)],
    ComponentType.DIODE: [Pin(0, "A", -20, 0), Pin(1, "K", 20, 0)],
    ComponentType.MOSFET_N: [Pin(0, "D", 20, -20), Pin(1, "G", -20, 0), Pin(2, "S", 20, 20)],
    ComponentType.MOSFET_P: [Pin(0, "D", 20, 20), Pin(1, "G", -20, 0), Pin(2, "S", 20, -20)],
    ComponentType.IGBT: [Pin(0, "C", 20, -20), Pin(1, "G", -20, 0), Pin(2, "E", 20, 20)],
    ComponentType.SWITCH: [Pin(0, "1", -20, 0), Pin(1, "2", 20, 0)],
    ComponentType.TRANSFORMER: [
        Pin(0, "P1", -30, -15),
        Pin(1, "P2", -30, 15),
        Pin(2, "S1", 30, -15),
        Pin(3, "S2", 30, 15),
    ],
    ComponentType.PI_CONTROLLER: [
        Pin(0, "IN", -35, -12),
        Pin(1, "FB", -35, 12),
        Pin(2, "OUT", 35, 0),
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
        Pin(0, "CTRL", -35, -12),
        Pin(1, "CLK", -35, 12),
        Pin(2, "OUT", 35, 0),
    ],
    ComponentType.ELECTRICAL_SCOPE: _default_scope_pins(2),
    ComponentType.THERMAL_SCOPE: _default_scope_pins(2),
    ComponentType.SIGNAL_MUX: _default_mux_pins(4),
    ComponentType.SIGNAL_DEMUX: _default_demux_pins(4),
}

# Default parameter templates for each component type
DEFAULT_PARAMETERS: dict[ComponentType, dict[str, Any]] = {
    ComponentType.RESISTOR: {"resistance": 1000.0},
    ComponentType.CAPACITOR: {"capacitance": 1e-6, "initial_voltage": 0.0},
    ComponentType.INDUCTOR: {"inductance": 1e-3, "initial_current": 0.0},
    ComponentType.VOLTAGE_SOURCE: {"waveform": {"type": "dc", "value": 5.0}},
    ComponentType.CURRENT_SOURCE: {"waveform": {"type": "dc", "value": 1.0}},
    ComponentType.GROUND: {},
    ComponentType.DIODE: {"is_": 1e-14, "n": 1.0, "rs": 0.0},
    ComponentType.MOSFET_N: {"vth": 2.0, "kp": 0.1, "lambda_": 0.0, "rds_on": 0.01},
    ComponentType.MOSFET_P: {"vth": -2.0, "kp": 0.1, "lambda_": 0.0, "rds_on": 0.01},
    ComponentType.IGBT: {"vth": 3.0, "vce_sat": 2.0},
    ComponentType.SWITCH: {"ron": 0.001, "roff": 1e9, "initial_state": False},
    ComponentType.TRANSFORMER: {"turns_ratio": 1.0, "lm": 1e-3},
    ComponentType.PI_CONTROLLER: {
        "kp": 1.0,
        "ki": 100.0,
        "output_min": -1.0,
        "output_max": 1.0,
    },
    ComponentType.PID_CONTROLLER: {
        "kp": 1.0,
        "ki": 100.0,
        "kd": 0.01,
        "output_min": -1.0,
        "output_max": 1.0,
    },
    ComponentType.MATH_BLOCK: {
        "operation": "sum",
        "gain": 1.0,
    },
    ComponentType.PWM_GENERATOR: {
        "frequency": 10000.0,
        "duty_cycle": 0.5,
        "carrier": "sawtooth",
        "amplitude": 1.0,
    },
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
    ComponentType.SIGNAL_MUX: {
        "input_count": 4,
        "channel_labels": ["Ch1", "Ch2", "Ch3", "Ch4"],
        "ordering": [0, 1, 2, 3],
    },
    ComponentType.SIGNAL_DEMUX: {
        "output_count": 4,
        "channel_labels": ["Ch1", "Ch2", "Ch3", "Ch4"],
        "ordering": [0, 1, 2, 3],
    },
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


SCOPE_CHANNEL_LIMITS = (1, 8)
MUX_CHANNEL_LIMITS = (2, 16)


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, value))


def _synchronize_special_component(component: Component) -> None:
    if component.type in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE):
        _synchronize_scope(component)
    elif component.type == ComponentType.SIGNAL_MUX:
        _synchronize_mux(component)
    elif component.type == ComponentType.SIGNAL_DEMUX:
        _synchronize_demux(component)


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

    component.pins = _default_scope_pins(channel_count)


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

    component.pins = _default_mux_pins(input_count)


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

    component.pins = _default_demux_pins(output_count)


def set_scope_channel_count(component: Component, count: int) -> None:
    """Update a scope component to use the provided channel count."""

    _synchronize_scope(component, force_count=count)


def set_mux_input_count(component: Component, count: int) -> None:
    """Update a mux component's input count and pin layout."""

    _synchronize_mux(component, force_count=count)


def set_demux_output_count(component: Component, count: int) -> None:
    """Update a demux component's output count and pin layout."""

    _synchronize_demux(component, force_count=count)
