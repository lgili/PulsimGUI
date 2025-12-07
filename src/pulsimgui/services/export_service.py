"""Export service for exporting circuits and waveforms to various formats."""

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgGenerator

from pulsimgui.models.component import ComponentType

if TYPE_CHECKING:
    from pulsimgui.models.circuit import Circuit
    from pulsimgui.models.project import Project
    from pulsimgui.services.simulation_service import SimulationResult
    from pulsimgui.views.schematic import SchematicScene


# SPICE component mappings
SPICE_COMPONENT_MAP = {
    ComponentType.RESISTOR: "R",
    ComponentType.CAPACITOR: "C",
    ComponentType.INDUCTOR: "L",
    ComponentType.VOLTAGE_SOURCE: "V",
    ComponentType.CURRENT_SOURCE: "I",
    ComponentType.DIODE: "D",
    ComponentType.MOSFET_N: "M",
    ComponentType.MOSFET_P: "M",
    ComponentType.IGBT: "Q",
    ComponentType.SWITCH: "S",
    ComponentType.TRANSFORMER: "X",
}


class ExportService:
    """Service for exporting circuits and simulation results."""

    @staticmethod
    def export_spice_netlist(circuit: "Circuit", filepath: str) -> None:
        """Export circuit to SPICE netlist format.

        Args:
            circuit: The circuit to export
            filepath: Path to save the netlist
        """
        lines = [
            f"* SPICE Netlist exported from PulsimGui",
            f"* Circuit: {circuit.name}",
            "",
        ]

        # Build node map from wire connections
        node_map = ExportService._build_node_map(circuit)

        # Export components
        for comp in circuit.components.values():
            if comp.type == ComponentType.GROUND:
                continue  # Ground is implicit in SPICE (node 0)

            spice_prefix = SPICE_COMPONENT_MAP.get(comp.type, "X")
            spice_line = ExportService._component_to_spice(comp, node_map)
            if spice_line:
                lines.append(spice_line)

        lines.append("")
        lines.append(".end")

        Path(filepath).write_text("\n".join(lines))

    @staticmethod
    def _build_node_map(circuit: "Circuit") -> dict[tuple[str, int], str]:
        """Build a map of (component_id, pin_index) -> node_name."""
        node_map: dict[tuple[str, int], str] = {}
        node_counter = 1

        # First, find ground connections - they should be node 0
        for comp in circuit.components.values():
            if comp.type == ComponentType.GROUND:
                # Find what's connected to this ground
                gnd_pos = comp.get_pin_position(0)
                for other_comp in circuit.components.values():
                    if other_comp.id == comp.id:
                        continue
                    for pin_idx in range(len(other_comp.pins)):
                        pin_pos = other_comp.get_pin_position(pin_idx)
                        if abs(pin_pos[0] - gnd_pos[0]) < 5 and abs(pin_pos[1] - gnd_pos[1]) < 5:
                            node_map[(str(other_comp.id), pin_idx)] = "0"

        # Then, assign node names to remaining pins based on wire connections
        for wire in circuit.wires.values():
            if not wire.segments:
                continue

            # Get connected pins for this wire
            connected_pins = []
            for seg in wire.segments:
                # Check start and end of each segment
                for pos in [(seg.x1, seg.y1), (seg.x2, seg.y2)]:
                    for comp in circuit.components.values():
                        for pin_idx in range(len(comp.pins)):
                            pin_pos = comp.get_pin_position(pin_idx)
                            if abs(pin_pos[0] - pos[0]) < 5 and abs(pin_pos[1] - pos[1]) < 5:
                                connected_pins.append((str(comp.id), pin_idx))

            if not connected_pins:
                continue

            # Check if any pin already has a node assigned
            existing_node = None
            for pin_key in connected_pins:
                if pin_key in node_map:
                    existing_node = node_map[pin_key]
                    break

            # Assign the same node to all connected pins
            if existing_node is None:
                existing_node = str(node_counter)
                node_counter += 1

            for pin_key in connected_pins:
                node_map[pin_key] = existing_node

        # Assign unique nodes to any unconnected pins
        for comp in circuit.components.values():
            for pin_idx in range(len(comp.pins)):
                key = (str(comp.id), pin_idx)
                if key not in node_map:
                    node_map[key] = str(node_counter)
                    node_counter += 1

        return node_map

    @staticmethod
    def _component_to_spice(comp, node_map: dict[tuple[str, int], str]) -> str:
        """Convert a component to SPICE netlist line."""
        comp_id = str(comp.id)
        params = comp.parameters

        def get_node(pin_idx: int) -> str:
            return node_map.get((comp_id, pin_idx), "0")

        if comp.type == ComponentType.RESISTOR:
            return f"{comp.name} {get_node(0)} {get_node(1)} {params.get('resistance', 1000)}"

        elif comp.type == ComponentType.CAPACITOR:
            line = f"{comp.name} {get_node(0)} {get_node(1)} {params.get('capacitance', 1e-6)}"
            if params.get('initial_voltage', 0) != 0:
                line += f" IC={params['initial_voltage']}"
            return line

        elif comp.type == ComponentType.INDUCTOR:
            line = f"{comp.name} {get_node(0)} {get_node(1)} {params.get('inductance', 1e-3)}"
            if params.get('initial_current', 0) != 0:
                line += f" IC={params['initial_current']}"
            return line

        elif comp.type == ComponentType.VOLTAGE_SOURCE:
            waveform = params.get('waveform', {'type': 'dc', 'value': 5.0})
            wave_type = waveform.get('type', 'dc')
            if wave_type == 'dc':
                return f"{comp.name} {get_node(0)} {get_node(1)} DC {waveform.get('value', 0)}"
            elif wave_type == 'sine':
                offset = waveform.get('offset', 0)
                amplitude = waveform.get('amplitude', 1)
                frequency = waveform.get('frequency', 1000)
                return f"{comp.name} {get_node(0)} {get_node(1)} SIN({offset} {amplitude} {frequency})"
            elif wave_type == 'pulse':
                v1 = waveform.get('v1', 0)
                v2 = waveform.get('v2', 5)
                td = waveform.get('delay', 0)
                tr = waveform.get('rise_time', 1e-9)
                tf = waveform.get('fall_time', 1e-9)
                pw = waveform.get('pulse_width', 0.5e-3)
                per = waveform.get('period', 1e-3)
                return f"{comp.name} {get_node(0)} {get_node(1)} PULSE({v1} {v2} {td} {tr} {tf} {pw} {per})"
            else:
                return f"{comp.name} {get_node(0)} {get_node(1)} DC {waveform.get('value', 0)}"

        elif comp.type == ComponentType.CURRENT_SOURCE:
            waveform = params.get('waveform', {'type': 'dc', 'value': 1.0})
            return f"{comp.name} {get_node(0)} {get_node(1)} DC {waveform.get('value', 0)}"

        elif comp.type == ComponentType.DIODE:
            return f"{comp.name} {get_node(0)} {get_node(1)} D1"

        elif comp.type in (ComponentType.MOSFET_N, ComponentType.MOSFET_P):
            # D G S for MOSFET
            model = "NMOS" if comp.type == ComponentType.MOSFET_N else "PMOS"
            return f"{comp.name} {get_node(0)} {get_node(1)} {get_node(2)} {get_node(2)} {model}"

        elif comp.type == ComponentType.IGBT:
            # C G E for IGBT - modeled as subcircuit
            return f"X{comp.name} {get_node(0)} {get_node(1)} {get_node(2)} IGBT"

        elif comp.type == ComponentType.SWITCH:
            ron = params.get('ron', 0.001)
            return f"{comp.name} {get_node(0)} {get_node(1)} ctrl_node 0 SW RON={ron}"

        elif comp.type == ComponentType.TRANSFORMER:
            # Transformers need coupled inductors in SPICE
            ratio = params.get('turns_ratio', 1.0)
            lm = params.get('lm', 1e-3)
            lines = [
                f"L{comp.name}_P {get_node(0)} {get_node(1)} {lm}",
                f"L{comp.name}_S {get_node(2)} {get_node(3)} {lm * ratio * ratio}",
                f"K{comp.name} L{comp.name}_P L{comp.name}_S 0.999",
            ]
            return "\n".join(lines)

        return f"* Unknown component: {comp.name}"

    @staticmethod
    def export_json_netlist(project: "Project", filepath: str) -> None:
        """Export circuit to JSON netlist format (Pulsim format).

        Args:
            project: The project to export
            filepath: Path to save the netlist
        """
        circuit = project.get_active_circuit()

        netlist = {
            "version": "1.0",
            "name": circuit.name,
            "components": [],
            "wires": [],
        }

        # Export components
        for comp in circuit.components.values():
            comp_data = {
                "id": str(comp.id),
                "type": comp.type.name,
                "name": comp.name,
                "parameters": comp.parameters,
                "pins": [
                    {
                        "index": pin.index,
                        "name": pin.name,
                        "position": comp.get_pin_position(pin.index),
                    }
                    for pin in comp.pins
                ],
            }
            netlist["components"].append(comp_data)

        # Export wires (connectivity)
        for wire in circuit.wires.values():
            wire_data = {
                "id": str(wire.id),
                "segments": [
                    {"x1": seg.x1, "y1": seg.y1, "x2": seg.x2, "y2": seg.y2}
                    for seg in wire.segments
                ],
            }
            netlist["wires"].append(wire_data)

        Path(filepath).write_text(json.dumps(netlist, indent=2))

    @staticmethod
    def export_schematic_png(scene: "SchematicScene", filepath: str, scale: float = 2.0) -> None:
        """Export schematic scene to PNG image.

        Args:
            scene: The schematic scene to export
            filepath: Path to save the image
            scale: Scale factor for higher resolution (default 2.0 for 2x resolution)
        """
        # Get scene bounds with some padding
        bounds = scene.itemsBoundingRect()
        padding = 50
        bounds = bounds.adjusted(-padding, -padding, padding, padding)

        # Create image with scaled dimensions
        width = int(bounds.width() * scale)
        height = int(bounds.height() * scale)

        if width <= 0 or height <= 0:
            # Empty scene - create minimal image
            width = 100
            height = 100

        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(scene.background_color)

        # Render scene to image
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        painter.translate(-bounds.topLeft())
        scene.render(painter, QRectF(), bounds)
        painter.end()

        image.save(filepath)

    @staticmethod
    def export_schematic_svg(scene: "SchematicScene", filepath: str) -> None:
        """Export schematic scene to SVG vector image.

        Args:
            scene: The schematic scene to export
            filepath: Path to save the SVG
        """
        # Get scene bounds with some padding
        bounds = scene.itemsBoundingRect()
        padding = 50
        bounds = bounds.adjusted(-padding, -padding, padding, padding)

        width = int(bounds.width())
        height = int(bounds.height())

        if width <= 0 or height <= 0:
            width = 100
            height = 100

        # Create SVG generator
        generator = QSvgGenerator()
        generator.setFileName(filepath)
        generator.setSize(bounds.size().toSize())
        generator.setViewBox(QRectF(0, 0, width, height))
        generator.setTitle("PulsimGui Schematic")
        generator.setDescription("Exported from PulsimGui")

        # Render scene to SVG
        painter = QPainter(generator)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(-bounds.topLeft())
        scene.render(painter, QRectF(), bounds)
        painter.end()

    @staticmethod
    def export_waveforms_csv(result: "SimulationResult", filepath: str) -> None:
        """Export simulation waveforms to CSV file.

        Args:
            result: Simulation result containing time and signal data
            filepath: Path to save the CSV
        """
        if not result.is_valid:
            raise ValueError("Cannot export invalid simulation result")

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header row: Time, Signal1, Signal2, ...
            headers = ["Time (s)"] + list(result.signals.keys())
            writer.writerow(headers)

            # Data rows
            for i, t in enumerate(result.time):
                row = [t]
                for signal_name in result.signals.keys():
                    values = result.signals[signal_name]
                    if i < len(values):
                        row.append(values[i])
                    else:
                        row.append("")
                writer.writerow(row)
