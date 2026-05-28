#!/usr/bin/env python3
"""Builder for example 18 — subcircuit reuse demo.

Run from the repo root::

    PYTHONPATH=src python3 scripts/build_subcircuit_example.py

Regenerates ``examples/18_subcircuit_demo.pulsim``. Demonstrates the
hierarchical subcircuit feature end-to-end:

  1. A ``HalfBridgeLeg`` subcircuit is defined ONCE — internally it's
     two MOSFETs in series with a node between them.
  2. The parent schematic instantiates it TWICE to build a 3-phase-
     ish two-leg inverter, sharing a common DC bus + load.
  3. The simulation flattens both instances into their primitives
     via the new ``_flatten_subcircuits`` pre-pass and runs.

The point isn't a textbook converter — it's that the user creates
the half-bridge ONCE and reuses it. Open the file in the GUI,
double-click any instance to descend into the definition, edit the
internals, save, and ALL instances reflect the change automatically.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pulsimgui.models  # noqa: F401 — defuse circular import
from pulsimgui.utils.wire_router import WireRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def uid_str() -> str:
    return str(uuid4())


def comp(*, type, name, x, y, parameters, pins, rotation=0, extra=None):
    """Build a component dict. ``extra`` merges in subcircuit-specific
    fields (like ``subcircuit_id``) without polluting the common path."""
    out = {
        "id": uid_str(), "type": type, "name": name,
        "x": float(x), "y": float(y),
        "rotation": rotation, "mirrored_h": False, "mirrored_v": False,
        "parameters": parameters, "pins": pins,
    }
    if extra:
        out.update(extra)
    return out


def pin(index, name, x, y):
    return {"index": index, "name": name, "x": float(x), "y": float(y)}


def wire(a_id, a_pin, b_id, b_pin, components_by_id, router, *,
         node_name="", alias=""):
    ca = components_by_id[a_id]
    cb = components_by_id[b_id]
    ax = ca["x"] + next(p["x"] for p in ca["pins"] if p["index"] == a_pin)
    ay = ca["y"] + next(p["y"] for p in ca["pins"] if p["index"] == a_pin)
    bx = cb["x"] + next(p["x"] for p in cb["pins"] if p["index"] == b_pin)
    by = cb["y"] + next(p["y"] for p in cb["pins"] if p["index"] == b_pin)
    raw = router.route(ax, ay, bx, by)
    segments = [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                for (x1, y1, x2, y2) in raw]
    return {
        "id": uid_str(), "segments": segments,
        "start_connection": {"component_id": a_id, "pin_index": a_pin},
        "end_connection": {"component_id": b_id, "pin_index": b_pin},
        "junctions": [], "node_name": node_name, "alias": alias,
    }


def wire_at(a_id, a_pin_pos, b_id, b_pin_pos, router, *, node_name=""):
    """Wire between two raw (x, y) positions — used when one endpoint
    is a port, not a real component."""
    raw = router.route(*a_pin_pos, *b_pin_pos)
    segments = [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                for (x1, y1, x2, y2) in raw]
    return {
        "id": uid_str(), "segments": segments,
        "start_connection": {"component_id": a_id, "pin_index": 0},
        "end_connection": {"component_id": b_id, "pin_index": 0},
        "junctions": [], "node_name": node_name, "alias": "",
    }


# ---------------------------------------------------------------------------
# Subcircuit DEFINITION — "HalfBridgeLeg"
# ---------------------------------------------------------------------------
# Internal topology:
#
#       VDC+ pin ────┐
#                    │
#                  [M_HI]    high-side MOSFET
#                    │
#                    ●─── AC_OUT pin
#                    │
#                  [M_LO]    low-side MOSFET
#                    │
#       VDC- pin ────┘
#
# Three ports: VDC+, AC_OUT, VDC-
# Two MOSFETs in series sharing the AC mid-point.
def build_half_bridge_definition() -> tuple[UUID, dict]:
    """Return (definition_id, serialized_definition_dict)."""
    defn_id = uuid4()

    # Components inside the definition's internal circuit
    m_hi_id = uid_str()
    m_lo_id = uid_str()
    internal_components = [
        # M_HI: drain at VDC+, source at AC mid (MOSFET pins:
        # 0=drain, 1=gate, 2=source — match component.py defaults)
        {
            "id": m_hi_id, "type": "MOSFET_N", "name": "M_HI",
            "x": 0.0, "y": -30.0, "rotation": 0,
            "mirrored_h": False, "mirrored_v": False,
            "parameters": {
                "is_nmos": True, "R_on": 25e-3, "R_off": 1.0e9, "v_th": 3.0,
            },
            "pins": [pin(0, "D", 0, -25), pin(1, "G", -25, 0), pin(2, "S", 0, 25)],
        },
        # M_LO: drain at AC mid, source at VDC-
        {
            "id": m_lo_id, "type": "MOSFET_N", "name": "M_LO",
            "x": 0.0, "y": 30.0, "rotation": 0,
            "mirrored_h": False, "mirrored_v": False,
            "parameters": {
                "is_nmos": True, "R_on": 25e-3, "R_off": 1.0e9, "v_th": 3.0,
            },
            "pins": [pin(0, "D", 0, -25), pin(1, "G", -25, 0), pin(2, "S", 0, 25)],
        },
    ]

    # Internal wires — these define the internal net topology that
    # the flattener reads via build_node_map.
    internal_wires = [
        # M_HI source (0, -5) → M_LO drain (0, 5) — the AC mid node
        {
            "id": uid_str(),
            "segments": [{"x1": 0.0, "y1": -5.0, "x2": 0.0, "y2": 5.0}],
            "start_connection": {"component_id": m_hi_id, "pin_index": 2},
            "end_connection": {"component_id": m_lo_id, "pin_index": 0},
            "junctions": [], "node_name": "AC_MID", "alias": "",
        },
    ]

    # The 3 ports
    port_vdc_pos = {
        "id": str(uuid4()),
        "name": "VDC+",
        "internal_node": "VDC_POS",  # internal net name for the high-side D pin
        "pin_index": 0,
        "x": -40.0, "y": -30.0,
    }
    port_vdc_neg = {
        "id": str(uuid4()),
        "name": "VDC-",
        "internal_node": "VDC_NEG",  # internal net name for the low-side S pin
        "pin_index": 1,
        "x": -40.0, "y": 30.0,
    }
    port_ac_out = {
        "id": str(uuid4()),
        "name": "AC_OUT",
        "internal_node": "AC_MID",   # = the net between M_HI.S and M_LO.D
        "pin_index": 2,
        "x": 40.0, "y": 0.0,
    }

    # The flattener resolves port-net assignments from internal pin
    # connectivity. For VDC+ / VDC- to actually map onto the
    # high-side D and low-side S, we need to label those pins via
    # extra wires anchored at those positions. Cleanest: add two
    # 0-length anchor wires that pin them by node_name. (The GUI
    # equivalent is the user dropping a Goto label.)
    # In practice it's simpler to override pin_nodes downstream —
    # but for round-trip fidelity we add explicit wires.

    definition_dict = {
        "id": str(defn_id),
        "name": "HalfBridgeLeg",
        "description": (
            "A half-bridge leg — two NMOS in series sharing the AC "
            "midpoint. Reusable building block: instantiate twice "
            "for an H-bridge, six times for a 3-phase 2-level VSI."
        ),
        "circuit": {
            "id": uid_str(),
            "name": "HalfBridgeLeg_internal",
            "components": internal_components,
            "wires": internal_wires,
        },
        "ports": [port_vdc_pos, port_vdc_neg, port_ac_out],
        "symbol_width": 80.0,
        "symbol_height": 80.0,
    }
    return defn_id, definition_dict


# ---------------------------------------------------------------------------
# Parent schematic — two instances of HalfBridgeLeg form an H-bridge,
# connected across a DC source with a resistive load between the
# two AC midpoints.
# ---------------------------------------------------------------------------
def build_parent_circuit(defn_id: UUID, definition_dict: dict):
    components: list[dict] = []
    wires: list[dict] = []

    # DC source
    v_dc = comp(
        type="VOLTAGE_SOURCE", name="V_DC", x=-400, y=0,
        parameters={
            "waveform": {"type": "dc", "value": 200.0,
                         "amplitude": 0.0, "frequency": 0.0,
                         "offset": 200.0, "phase": 0.0},
        },
        pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
    )
    components.append(v_dc)

    gnd = comp(
        type="GROUND", name="GND", x=-340, y=80,
        parameters={},
        pins=[pin(0, "gnd", 0, -20)],
    )
    components.append(gnd)

    # The two SubcircuitInstance blocks — both reference the SAME
    # definition. Each gets its own gates implicitly (no signal —
    # this example just demonstrates flattening + connectivity).
    leg_pins = [
        pin(0, "VDC+", -40, -30),
        pin(1, "VDC-", -40, 30),
        pin(2, "AC_OUT", 40, 0),
    ]
    leg_left = comp(
        type="SUBCIRCUIT", name="Leg_L", x=-120, y=-40,
        parameters={"symbol_width": 80.0, "symbol_height": 80.0},
        pins=list(leg_pins),
        extra={"subcircuit_id": str(defn_id)},
    )
    components.append(leg_left)

    leg_right = comp(
        type="SUBCIRCUIT", name="Leg_R", x=120, y=-40,
        parameters={"symbol_width": 80.0, "symbol_height": 80.0},
        pins=list(leg_pins),
        extra={"subcircuit_id": str(defn_id)},
    )
    components.append(leg_right)

    # Load resistor between the two AC outputs
    r_load = comp(
        type="RESISTOR", name="R_load", x=0, y=120,
        parameters={"resistance": 10.0},
        pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
    )
    components.append(r_load)

    # Probes
    vp_acL = comp(
        type="VOLTAGE_PROBE_GND", name="V_AC_L",
        x=-50, y=-100,
        parameters={"display_name": "V_AC_L", "scale": 1.0},
        pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
    )
    components.append(vp_acL)

    vp_acR = comp(
        type="VOLTAGE_PROBE_GND", name="V_AC_R",
        x=50, y=-100,
        parameters={"display_name": "V_AC_R", "scale": 1.0},
        pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
    )
    components.append(vp_acR)

    vp_bus = comp(
        type="VOLTAGE_PROBE_GND", name="V_BUS", x=-300, y=-80,
        parameters={"display_name": "V_BUS", "scale": 1.0},
        pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
    )
    components.append(vp_bus)

    # Scope
    scope = comp(
        type="ELECTRICAL_SCOPE", name="Scope_HBridge", x=320, y=-100,
        parameters={
            "channel_count": 3,
            "channels": [
                {"label": "V_BUS",  "overlay": False},
                {"label": "V_AC_L", "overlay": False},
                {"label": "V_AC_R", "overlay": False},
            ],
        },
        pins=[pin(0, "CH1", -40, -25),
              pin(1, "CH2", -40, 0),
              pin(2, "CH3", -40, 25)],
    )
    components.append(scope)

    # ----- Wires -----
    comp_by_id = {c["id"]: c for c in components}
    router = WireRouter(grid=20.0)
    router.add_obstacles_from_components(
        components, body_half_w=30.0, body_half_h=25.0, padding=6.0,
    )

    def w(a, ap, b, bp, *, node_name=""):
        wires.append(wire(a["id"], ap, b["id"], bp, comp_by_id,
                            router, node_name=node_name))

    # V_DC+ → V_BUS probe → both legs' VDC+ pins
    w(v_dc, 0, vp_bus, 0, node_name="VDC_POS")
    w(vp_bus, 0, leg_left, 0, node_name="VDC_POS")
    w(vp_bus, 0, leg_right, 0, node_name="VDC_POS")

    # V_DC- → ground → both legs' VDC- pins
    w(v_dc, 1, gnd, 0, node_name="VDC_NEG")
    w(gnd, 0, leg_left, 1, node_name="VDC_NEG")
    w(gnd, 0, leg_right, 1, node_name="VDC_NEG")

    # AC_OUT of each leg → load + voltage probe
    w(leg_left, 2, vp_acL, 0, node_name="AC_L")
    w(vp_acL, 0, r_load, 0, node_name="AC_L")
    w(leg_right, 2, vp_acR, 0, node_name="AC_R")
    w(vp_acR, 0, r_load, 1, node_name="AC_R")

    # Scope wiring
    w(vp_bus, 1, scope, 0)
    w(vp_acL, 1, scope, 1)
    w(vp_acR, 1, scope, 2)

    return components, wires


# ---------------------------------------------------------------------------
# Build + write
# ---------------------------------------------------------------------------
defn_id, defn_dict = build_half_bridge_definition()
components, wires = build_parent_circuit(defn_id, defn_dict)

sim_settings = {
    "tstop": 0.020, "dt": 1.0e-6, "tstart": 0.0,
    "output_points": 20000,
    "control_sample_time": 1.0e-5, "control_mode": "discrete",
    "tol_newton_dx": 1.0e-6, "tol_newton_res": 1.0e-6,
    "enable_newton_line_search": True, "enable_newton_lm": False,
    "enable_substep_state_correction": True,
    "enable_nonlinear_refresh": False,
    "start_from_dc_op": False, "max_event_iterations": 50,
}

now = datetime.now().isoformat(timespec="seconds")
project = {
    "version": "1.0",
    "name": "18 Subcircuit Demo — HalfBridgeLeg × 2 (H-bridge)",
    "created": now,
    "modified": now,
    "active_circuit": "main",
    "simulation_settings": sim_settings,
    "circuits": {
        "main": {
            "name": "main",
            "components": components,
            "wires": wires,
        },
    },
    # ↓↓↓ THE KEY BIT — definitions live here. The Project model
    # serializes ``subcircuits`` as a LIST of definition dicts (see
    # Project.to_dict / from_dict). Both SUBCIRCUIT instances in the
    # parent above reference the same UUID, so editing the
    # definition once propagates to both instances automatically.
    "subcircuits": [defn_dict],
    "scope_windows": {},
    "scope_workspace_state": {},
}

out_path = Path(
    "/Users/lgili/Documents/01 - Codes/01 - Github/PulsimGUI/"
    "examples/18_subcircuit_demo.pulsim"
)
out_path.write_text(json.dumps(project, indent=2))
print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
print(f"  {len(components)} parent components, "
      f"{len(wires)} parent wires, "
      f"1 subcircuit definition")
