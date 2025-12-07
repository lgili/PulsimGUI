"""Component model for circuit elements."""

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
            self.parameters = DEFAULT_PARAMETERS[self.type].copy()

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
        return cls(
            id=UUID(data["id"]),
            type=ComponentType[data["type"]],
            name=data["name"],
            x=data["x"],
            y=data["y"],
            rotation=data.get("rotation", 0),
            mirrored_h=data.get("mirrored_h", False),
            mirrored_v=data.get("mirrored_v", False),
            parameters=data.get("parameters", {}),
            pins=[Pin.from_dict(p) for p in data.get("pins", [])],
        )
