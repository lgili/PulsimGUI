"""Template service for creating circuits from predefined templates."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireSegment


class TemplateCategory(Enum):
    """Categories of circuit templates."""

    DC_DC_CONVERTERS = auto()
    INVERTERS = auto()
    POWER_SUPPLIES = auto()
    MOTOR_DRIVES = auto()


@dataclass
class TemplateInfo:
    """Information about a circuit template."""

    id: str
    name: str
    category: TemplateCategory
    description: str
    preview_image: str = ""  # Path to preview image
    tags: list[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


def _create_buck_converter() -> Circuit:
    """Create a basic synchronous buck converter circuit."""
    circuit = Circuit(name="Buck Converter")

    # Grid spacing for layout
    grid = 60

    # Input voltage source (left side)
    vin = Component(
        type=ComponentType.VOLTAGE_SOURCE,
        name="Vin",
        x=-3 * grid,
        y=0,
        parameters={"waveform": {"type": "dc", "value": 12.0}},
    )

    # High-side MOSFET (top switch)
    q_high = Component(
        type=ComponentType.MOSFET_N,
        name="Q_H",
        x=0,
        y=-2 * grid,
        rotation=0,
        parameters={"rds_on": 0.01, "vth": 2.0},
    )

    # Low-side MOSFET (synchronous rectifier)
    q_low = Component(
        type=ComponentType.MOSFET_N,
        name="Q_L",
        x=0,
        y=2 * grid,
        rotation=0,
        parameters={"rds_on": 0.01, "vth": 2.0},
    )

    # Output inductor
    inductor = Component(
        type=ComponentType.INDUCTOR,
        name="L",
        x=2 * grid,
        y=0,
        parameters={"inductance": 10e-6, "initial_current": 0.0},
    )

    # Output capacitor
    cout = Component(
        type=ComponentType.CAPACITOR,
        name="Cout",
        x=4 * grid,
        y=grid,
        rotation=90,
        parameters={"capacitance": 100e-6, "initial_voltage": 0.0},
    )

    # Load resistor
    rload = Component(
        type=ComponentType.RESISTOR,
        name="Rload",
        x=5 * grid,
        y=grid,
        rotation=90,
        parameters={"resistance": 5.0},
    )

    # Input capacitor
    cin = Component(
        type=ComponentType.CAPACITOR,
        name="Cin",
        x=-2 * grid,
        y=grid,
        rotation=90,
        parameters={"capacitance": 10e-6, "initial_voltage": 12.0},
    )

    # Ground references
    gnd1 = Component(type=ComponentType.GROUND, name="GND1", x=-3 * grid, y=3 * grid)
    gnd2 = Component(type=ComponentType.GROUND, name="GND2", x=4 * grid, y=3 * grid)

    # Add components
    for comp in [vin, q_high, q_low, inductor, cout, rload, cin, gnd1, gnd2]:
        circuit.add_component(comp)

    return circuit


def _create_boost_converter() -> Circuit:
    """Create a basic boost converter circuit."""
    circuit = Circuit(name="Boost Converter")

    grid = 60

    # Input voltage source
    vin = Component(
        type=ComponentType.VOLTAGE_SOURCE,
        name="Vin",
        x=-3 * grid,
        y=0,
        parameters={"waveform": {"type": "dc", "value": 5.0}},
    )

    # Input inductor
    inductor = Component(
        type=ComponentType.INDUCTOR,
        name="L",
        x=-grid,
        y=-2 * grid,
        parameters={"inductance": 100e-6, "initial_current": 0.0},
    )

    # Main switch (MOSFET)
    q_main = Component(
        type=ComponentType.MOSFET_N,
        name="Q",
        x=grid,
        y=0,
        rotation=0,
        parameters={"rds_on": 0.02, "vth": 2.0},
    )

    # Boost diode
    diode = Component(
        type=ComponentType.DIODE,
        name="D",
        x=2 * grid,
        y=-2 * grid,
        parameters={"is_": 1e-14, "n": 1.0},
    )

    # Output capacitor
    cout = Component(
        type=ComponentType.CAPACITOR,
        name="Cout",
        x=4 * grid,
        y=0,
        rotation=90,
        parameters={"capacitance": 47e-6, "initial_voltage": 0.0},
    )

    # Load resistor
    rload = Component(
        type=ComponentType.RESISTOR,
        name="Rload",
        x=5 * grid,
        y=0,
        rotation=90,
        parameters={"resistance": 100.0},
    )

    # Input capacitor
    cin = Component(
        type=ComponentType.CAPACITOR,
        name="Cin",
        x=-2 * grid,
        y=0,
        rotation=90,
        parameters={"capacitance": 10e-6, "initial_voltage": 5.0},
    )

    # Ground references
    gnd1 = Component(type=ComponentType.GROUND, name="GND1", x=-3 * grid, y=2 * grid)
    gnd2 = Component(type=ComponentType.GROUND, name="GND2", x=4 * grid, y=2 * grid)

    # Add components
    for comp in [vin, inductor, q_main, diode, cout, rload, cin, gnd1, gnd2]:
        circuit.add_component(comp)

    return circuit


def _create_full_bridge() -> Circuit:
    """Create a full-bridge (H-bridge) inverter circuit."""
    circuit = Circuit(name="Full-Bridge Inverter")

    grid = 60

    # DC bus voltage source
    vdc = Component(
        type=ComponentType.VOLTAGE_SOURCE,
        name="Vdc",
        x=-4 * grid,
        y=0,
        parameters={"waveform": {"type": "dc", "value": 48.0}},
    )

    # DC bus capacitor
    cdc = Component(
        type=ComponentType.CAPACITOR,
        name="Cdc",
        x=-2 * grid,
        y=0,
        rotation=90,
        parameters={"capacitance": 1000e-6, "initial_voltage": 48.0},
    )

    # High-side left MOSFET (Q1)
    q1 = Component(
        type=ComponentType.MOSFET_N,
        name="Q1",
        x=-grid,
        y=-2 * grid,
        rotation=0,
        parameters={"rds_on": 0.01, "vth": 2.0},
    )

    # Low-side left MOSFET (Q2)
    q2 = Component(
        type=ComponentType.MOSFET_N,
        name="Q2",
        x=-grid,
        y=2 * grid,
        rotation=0,
        parameters={"rds_on": 0.01, "vth": 2.0},
    )

    # High-side right MOSFET (Q3)
    q3 = Component(
        type=ComponentType.MOSFET_N,
        name="Q3",
        x=3 * grid,
        y=-2 * grid,
        rotation=0,
        parameters={"rds_on": 0.01, "vth": 2.0},
    )

    # Low-side right MOSFET (Q4)
    q4 = Component(
        type=ComponentType.MOSFET_N,
        name="Q4",
        x=3 * grid,
        y=2 * grid,
        rotation=0,
        parameters={"rds_on": 0.01, "vth": 2.0},
    )

    # Load inductor (represents motor or inductive load)
    l_load = Component(
        type=ComponentType.INDUCTOR,
        name="Lload",
        x=grid,
        y=0,
        parameters={"inductance": 1e-3, "initial_current": 0.0},
    )

    # Load resistor
    r_load = Component(
        type=ComponentType.RESISTOR,
        name="Rload",
        x=2 * grid,
        y=0,
        parameters={"resistance": 1.0},
    )

    # Ground reference
    gnd = Component(type=ComponentType.GROUND, name="GND", x=-4 * grid, y=3 * grid)

    # Add components
    for comp in [vdc, cdc, q1, q2, q3, q4, l_load, r_load, gnd]:
        circuit.add_component(comp)

    return circuit


# Template registry
TEMPLATES: dict[str, tuple[TemplateInfo, Callable[[], Circuit]]] = {
    "buck_converter": (
        TemplateInfo(
            id="buck_converter",
            name="Buck Converter",
            category=TemplateCategory.DC_DC_CONVERTERS,
            description="A synchronous step-down DC-DC converter with high-side and low-side MOSFETs. "
                       "Ideal for voltage regulation from higher to lower voltage levels.",
            tags=["dc-dc", "step-down", "synchronous", "switching"],
        ),
        _create_buck_converter,
    ),
    "boost_converter": (
        TemplateInfo(
            id="boost_converter",
            name="Boost Converter",
            category=TemplateCategory.DC_DC_CONVERTERS,
            description="A step-up DC-DC converter that boosts input voltage to a higher output. "
                       "Commonly used in battery-powered applications.",
            tags=["dc-dc", "step-up", "boost", "switching"],
        ),
        _create_boost_converter,
    ),
    "full_bridge": (
        TemplateInfo(
            id="full_bridge",
            name="Full-Bridge Inverter",
            category=TemplateCategory.INVERTERS,
            description="An H-bridge inverter with 4 MOSFETs for DC-to-AC conversion. "
                       "Used for motor drives, inverters, and bidirectional power transfer.",
            tags=["inverter", "h-bridge", "motor-drive", "dc-ac"],
        ),
        _create_full_bridge,
    ),
}


class TemplateService:
    """Service for managing and creating circuit templates."""

    @staticmethod
    def get_all_templates() -> list[TemplateInfo]:
        """Get all available templates."""
        return [info for info, _ in TEMPLATES.values()]

    @staticmethod
    def get_templates_by_category(category: TemplateCategory) -> list[TemplateInfo]:
        """Get templates filtered by category."""
        return [
            info for info, _ in TEMPLATES.values()
            if info.category == category
        ]

    @staticmethod
    def get_template_info(template_id: str) -> TemplateInfo | None:
        """Get information about a specific template."""
        if template_id in TEMPLATES:
            return TEMPLATES[template_id][0]
        return None

    @staticmethod
    def create_circuit_from_template(template_id: str) -> Circuit | None:
        """Create a new circuit from a template."""
        if template_id in TEMPLATES:
            _, factory = TEMPLATES[template_id]
            return factory()
        return None

    @staticmethod
    def get_categories() -> list[tuple[TemplateCategory, str]]:
        """Get all categories with their display names."""
        return [
            (TemplateCategory.DC_DC_CONVERTERS, "DC-DC Converters"),
            (TemplateCategory.INVERTERS, "Inverters"),
            (TemplateCategory.POWER_SUPPLIES, "Power Supplies"),
            (TemplateCategory.MOTOR_DRIVES, "Motor Drives"),
        ]
