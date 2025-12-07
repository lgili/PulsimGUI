"""Wire model for electrical connections."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class WireSegment:
    """A single segment of a wire (straight line)."""

    x1: float
    y1: float
    x2: float
    y2: float

    def to_dict(self) -> dict:
        """Serialize segment to dictionary."""
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    @classmethod
    def from_dict(cls, data: dict) -> "WireSegment":
        """Deserialize segment from dictionary."""
        return cls(x1=data["x1"], y1=data["y1"], x2=data["x2"], y2=data["y2"])


@dataclass
class WireConnection:
    """Connection point of a wire to a component pin."""

    component_id: UUID
    pin_index: int

    def to_dict(self) -> dict:
        """Serialize connection to dictionary."""
        return {"component_id": str(self.component_id), "pin_index": self.pin_index}

    @classmethod
    def from_dict(cls, data: dict) -> "WireConnection":
        """Deserialize connection from dictionary."""
        return cls(
            component_id=UUID(data["component_id"]),
            pin_index=data["pin_index"],
        )


@dataclass
class Wire:
    """A wire connecting component pins."""

    id: UUID = field(default_factory=uuid4)
    segments: list[WireSegment] = field(default_factory=list)
    start_connection: WireConnection | None = None
    end_connection: WireConnection | None = None
    junctions: list[tuple[float, float]] = field(default_factory=list)
    node_name: str = ""  # Electrical node name for netlist

    @property
    def start_point(self) -> tuple[float, float] | None:
        """Get the starting point of the wire."""
        if self.segments:
            return (self.segments[0].x1, self.segments[0].y1)
        return None

    @property
    def end_point(self) -> tuple[float, float] | None:
        """Get the ending point of the wire."""
        if self.segments:
            return (self.segments[-1].x2, self.segments[-1].y2)
        return None

    def add_segment(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Add a segment to the wire."""
        self.segments.append(WireSegment(x1, y1, x2, y2))

    def get_all_points(self) -> list[tuple[float, float]]:
        """Get all unique points in the wire path."""
        points = []
        for seg in self.segments:
            if not points or points[-1] != (seg.x1, seg.y1):
                points.append((seg.x1, seg.y1))
            points.append((seg.x2, seg.y2))
        return points

    def to_dict(self) -> dict:
        """Serialize wire to dictionary."""
        return {
            "id": str(self.id),
            "segments": [s.to_dict() for s in self.segments],
            "start_connection": self.start_connection.to_dict() if self.start_connection else None,
            "end_connection": self.end_connection.to_dict() if self.end_connection else None,
            "junctions": self.junctions,
            "node_name": self.node_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Wire":
        """Deserialize wire from dictionary."""
        return cls(
            id=UUID(data["id"]),
            segments=[WireSegment.from_dict(s) for s in data.get("segments", [])],
            start_connection=(
                WireConnection.from_dict(data["start_connection"])
                if data.get("start_connection")
                else None
            ),
            end_connection=(
                WireConnection.from_dict(data["end_connection"])
                if data.get("end_connection")
                else None
            ),
            junctions=data.get("junctions", []),
            node_name=data.get("node_name", ""),
        )
