"""Regression: the MMC examples' rotated current probes must load undistorted.

A rotated ``CURRENT_PROBE`` (the arm-current ammeters sitting in the vertical
arm legs) is authored with CANONICAL pins (IN left / OUT right / MEAS top) plus
``rotation = 90`` — the GUI rotates body + pins together on load. Two latent
bugs used to corrupt this on load:

1. **Double rotation.** The builder's wire helper computed wire endpoints from
   the *unrotated* pin coords. ``Circuit._heal_double_rotated_components`` then
   saw the canonical coords as ground truth and un-rotated the pins to meet
   them — silently turning the vertical probe horizontal. Fixed by computing the
   builder's wire endpoints at the *rotated* pin position so the healer leaves
   legitimately-rotated parts alone.
2. **Name-collision corruption.** The probes were authored with non-canonical
   pin names (``"1"``/``"2"``/``"OUT"``); the probe-pin sync renamed them to the
   canonical ``IN``/``OUT``/``MEAS`` and the saved-geometry restore-by-name then
   mapped the old signal ``"OUT"`` onto the new current-terminal ``OUT``,
   misplacing it. Fixed by authoring canonical names.

These tests pin the *loaded* geometry so neither regresses: arm probes stay
vertical, phase probes stay horizontal, every current terminal lands on a wire
endpoint, and the heal pass is an idempotent no-op.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulsimgui.models.circuit import _heal_double_rotated_components
from pulsimgui.models.component import ComponentType
from pulsimgui.models.project import Project

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
MMC_EXAMPLES = [
    "24_mmc_three_phase_controlled.pulsim",
    "25_mmc_three_phase_closed_loop.pulsim",
    "26_mmc_three_phase_l3_closed_loop.pulsim",
    "27_mmc_three_phase_l1_closed_loop.pulsim",
    "28_mmc_three_phase_l2_closed_loop.pulsim",
]


def _load_circuit(filename: str):
    path = EXAMPLES_DIR / filename
    if not path.is_file():
        pytest.skip(f"example {filename} not present")
    project = Project.from_dict(json.loads(path.read_text()), path=path)
    return project.circuits[project.active_circuit]


def _wire_endpoints(circuit) -> set[tuple[int, int]]:
    pts: set[tuple[int, int]] = set()
    for wire in circuit.wires.values():
        for endpoint in (wire.start_point, wire.end_point):
            if endpoint is not None:
                pts.add((round(endpoint[0]), round(endpoint[1])))
    return pts


def _probe_terminals(probe) -> dict[str, tuple[int, int]]:
    return {
        probe.pins[i].name: tuple(round(v) for v in probe.get_pin_position(i))
        for i in range(len(probe.pins))
    }


@pytest.mark.parametrize("filename", MMC_EXAMPLES)
def test_arm_probes_load_vertical(filename: str) -> None:
    """Arm-current probes (rotation=90) keep a vertical IN↔OUT axis on load."""
    circuit = _load_circuit(filename)
    arm_probes = [
        c for c in circuit.components.values()
        if c.type == ComponentType.CURRENT_PROBE and c.name.startswith("I_arm_")
    ]
    assert arm_probes, f"{filename}: expected arm-current probes"
    for probe in arm_probes:
        assert probe.rotation in (90, 270), (
            f"{filename}:{probe.name}: rotation lost ({probe.rotation})"
        )
        term = _probe_terminals(probe)
        dx = abs(term["IN"][0] - term["OUT"][0])
        dy = abs(term["IN"][1] - term["OUT"][1])
        assert dy > dx, (
            f"{filename}:{probe.name}: IN/OUT axis is horizontal {term} — the "
            "double-rotation healer un-rotated a legitimately-rotated probe."
        )


@pytest.mark.parametrize("filename", MMC_EXAMPLES)
def test_phase_probes_load_horizontal(filename: str) -> None:
    """Phase-current probes (rotation=0) keep a horizontal IN↔OUT axis."""
    circuit = _load_circuit(filename)
    phase_probes = [
        c for c in circuit.components.values()
        if c.type == ComponentType.CURRENT_PROBE and c.name.startswith("I_ph")
    ]
    assert phase_probes, f"{filename}: expected phase-current probes"
    for probe in phase_probes:
        term = _probe_terminals(probe)
        dx = abs(term["IN"][0] - term["OUT"][0])
        dy = abs(term["IN"][1] - term["OUT"][1])
        assert dx > dy, f"{filename}:{probe.name}: IN/OUT axis not horizontal {term}"


@pytest.mark.parametrize("filename", MMC_EXAMPLES)
def test_probe_current_terminals_are_wired(filename: str) -> None:
    """Every current terminal (IN/OUT) lands on a wire endpoint — no detachment
    introduced by computing wire endpoints at the rotated pin position."""
    circuit = _load_circuit(filename)
    endpoints = _wire_endpoints(circuit)
    probes = [
        c for c in circuit.components.values()
        if c.type == ComponentType.CURRENT_PROBE
    ]
    for probe in probes:
        term = _probe_terminals(probe)
        for name in ("IN", "OUT"):
            assert term[name] in endpoints, (
                f"{filename}:{probe.name}: terminal {name} at {term[name]} "
                "is not on any wire endpoint"
            )


@pytest.mark.parametrize("filename", MMC_EXAMPLES)
def test_heal_pass_is_idempotent_noop(filename: str) -> None:
    """Re-running the double-rotation healer on the loaded circuit changes
    nothing — the shipped geometry is already correct (no false positives)."""
    circuit = _load_circuit(filename)
    assert _heal_double_rotated_components(circuit) == 0
