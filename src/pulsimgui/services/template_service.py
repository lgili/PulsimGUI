"""Template service for creating circuits from predefined templates."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.project import Project


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
    tags: list[str] | None = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []


def _repo_root() -> Path:
    """Return repository root from the service module path."""
    return Path(__file__).resolve().parents[3]


def _candidate_example_paths(example_file: str) -> list[Path]:
    """Return candidate locations for an example project file."""
    return [
        _repo_root() / "examples" / example_file,
        Path.cwd() / "examples" / example_file,
    ]


def _load_example_circuit(example_file: str, *, fallback_name: str) -> Circuit:
    """Load the active circuit from an example .pulsim file.

    Falls back to an empty circuit when the example cannot be loaded.
    """
    for path in _candidate_example_paths(example_file):
        if not path.exists():
            continue
        try:
            project = Project.load(path)
            circuit = project.get_active_circuit()
            # Prefer project/template naming over generic circuit keys.
            if not circuit.name or circuit.name.lower() in {"main", "untitled", "untitled project"}:
                circuit.name = project.name or fallback_name
            return circuit
        except Exception:
            continue

    return Circuit(name=fallback_name)


def _load_example_project(example_file: str, *, fallback_name: str) -> Project | None:
    """Load a complete project from an example file.

    Returns a project with circuits + simulation settings when possible.
    """
    for path in _candidate_example_paths(example_file):
        if not path.exists():
            continue
        try:
            project = Project.load(path)
            if not project.name:
                project.name = fallback_name
            return project
        except Exception:
            continue
    return None


def _example_factory(example_file: str, fallback_name: str) -> Callable[[], Circuit]:
    """Build a factory that creates a circuit from an example project."""

    def _factory() -> Circuit:
        return _load_example_circuit(example_file, fallback_name=fallback_name)

    return _factory


# Template registry backed by full example projects (components + wires + probes + scopes).
TEMPLATES: dict[str, tuple[TemplateInfo, Callable[[], Circuit]]] = {
    "buck_converter": (
        TemplateInfo(
            id="buck_converter",
            name="Buck Converter",
            category=TemplateCategory.DC_DC_CONVERTERS,
            description=(
                "Step-down converter template loaded from examples/buck_converter.pulsim "
                "with complete wiring, probes, and scope channels."
            ),
            tags=["dc-dc", "step-down", "buck", "switching"],
        ),
        _example_factory("buck_converter.pulsim", "Buck Converter"),
    ),
    "boost_converter": (
        TemplateInfo(
            id="boost_converter",
            name="Boost Converter",
            category=TemplateCategory.DC_DC_CONVERTERS,
            description=(
                "Step-up converter template loaded from examples/boost_converter.pulsim "
                "with complete wiring, probes, and scope channels."
            ),
            tags=["dc-dc", "step-up", "boost", "switching"],
        ),
        _example_factory("boost_converter.pulsim", "Boost Converter"),
    ),
    "flyback_converter": (
        TemplateInfo(
            id="flyback_converter",
            name="Flyback Converter",
            category=TemplateCategory.DC_DC_CONVERTERS,
            description=(
                "Flyback converter template loaded from examples/flyback_converter.pulsim "
                "with complete wiring, probes, and scope channels."
            ),
            tags=["dc-dc", "flyback", "isolated", "switching"],
        ),
        _example_factory("flyback_converter.pulsim", "Flyback Converter"),
    ),
    "buck_converter_closed_loop": (
        TemplateInfo(
            id="buck_converter_closed_loop",
            name="Buck Converter (Closed Loop)",
            category=TemplateCategory.DC_DC_CONVERTERS,
            description=(
                "Closed-loop buck template loaded from examples/buck_converter_closed_loop.pulsim "
                "including control blocks and complete wiring."
            ),
            tags=["dc-dc", "buck", "closed-loop", "control"],
        ),
        _example_factory("buck_converter_closed_loop.pulsim", "Buck Converter (Closed Loop)"),
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
            info
            for info, _ in TEMPLATES.values()
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
    def create_project_from_template(template_id: str) -> Project | None:
        """Create a full project from a template example file.

        Includes circuit topology, wires, and persisted simulation settings.
        """
        if template_id not in TEMPLATES:
            return None

        template_info, _ = TEMPLATES[template_id]
        example_map = {
            "buck_converter": "buck_converter.pulsim",
            "boost_converter": "boost_converter.pulsim",
            "flyback_converter": "flyback_converter.pulsim",
            "buck_converter_closed_loop": "buck_converter_closed_loop.pulsim",
        }
        example_file = example_map.get(template_id)
        if not example_file:
            return None
        return _load_example_project(example_file, fallback_name=template_info.name)

    @staticmethod
    def get_categories() -> list[tuple[TemplateCategory, str]]:
        """Get all categories with their display names."""
        return [
            (TemplateCategory.DC_DC_CONVERTERS, "DC-DC Converters"),
            (TemplateCategory.INVERTERS, "Inverters"),
            (TemplateCategory.POWER_SUPPLIES, "Power Supplies"),
            (TemplateCategory.MOTOR_DRIVES, "Motor Drives"),
        ]
