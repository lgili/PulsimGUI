#!/usr/bin/env python3
"""Prove the MMC arm model GENUINELY changes when you switch model_fidelity.

The user asked: "tem certeza que muda o modelo quando trocamos? pq a
simulacao do l3 esta muito rapida" — i.e. is L3 actually running the
detailed submodule model, or is the GUI silently reusing the cheap L0
average source?

This script loads each shipped closed-loop example and runs it through
the REAL ``CircuitConverter`` with the four ``pulsim.mmc.add_mmc_arm_*``
constructors wrapped to record which one fires. Different fidelity ⇒
different pulsim constructor ⇒ different math. If L3 were secretly L0,
``add_mmc_arm_average`` would light up for the L3 example — it doesn't.

Run from the repo root::

    PYTHONPATH=src python3 scripts/verify_mmc_fidelity_dispatch.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pulsim as p

from pulsimgui.models.project import Project
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = {
    "L0 Average    (ex24)": "24_mmc_three_phase_controlled.pulsim",
    "L1 Multilevel (ex27)": "27_mmc_three_phase_l1_closed_loop.pulsim",
    "L2 Equivalent (ex28)": "28_mmc_three_phase_l2_closed_loop.pulsim",
    "L3 Detailed   (ex26)": "26_mmc_three_phase_l3_closed_loop.pulsim",
}
ARM_FNS = (
    "add_mmc_arm_average",
    "add_mmc_arm_multilevel",
    "add_mmc_arm_equivalent",
    "add_mmc_arm_detailed",
)


def _circuit_data(path: Path) -> dict:
    project = Project.from_dict(json.loads(path.read_text()), path=path)
    circuit = project.circuits[project.active_circuit]
    node_map_raw = build_node_map(circuit)
    alias_map = build_node_alias_map(circuit, node_map_raw)
    comps: list[dict] = []
    node_map: dict[str, list[str]] = {}
    for c in circuit.components.values():
        cid = str(c.id)
        comps.append({
            "id": cid, "type": c.type.name, "name": c.name,
            "x": c.x, "y": c.y, "rotation": c.rotation,
            "parameters": dict(c.parameters),
            "pins": [{"index": pin.index, "name": pin.name,
                      "x": pin.x, "y": pin.y} for pin in c.pins],
        })
        nodes = []
        for pin_idx in range(len(c.pins)):
            raw = node_map_raw.get((cid, pin_idx), f"pin_{cid}_{pin_idx}")
            nodes.append(alias_map.get(raw, raw))
        node_map[cid] = nodes
    return {"components": comps, "node_map": node_map, "node_aliases": alias_map}


def main() -> None:
    compat = make_compat_module(p)
    mmc_mod = compat.mmc

    # Wrap each constructor to count calls, preserving behaviour.
    counters: dict[str, int] = {}
    originals = {}
    for fn_name in ARM_FNS:
        orig = getattr(mmc_mod, fn_name)
        originals[fn_name] = orig

        def make_wrapper(name, fn):
            def wrapper(*a, **kw):
                counters[name] = counters.get(name, 0) + 1
                return fn(*a, **kw)
            return wrapper

        setattr(mmc_mod, fn_name, make_wrapper(fn_name, orig))

    print(f"pulsim {getattr(p, '__version__', '?')}\n")
    header = f"{'example':<22} | " + " | ".join(f"{n.split('_')[-1]:<11}" for n in ARM_FNS)
    print(header)
    print("-" * len(header))
    all_ok = True
    expected_for = {
        "L0 Average    (ex24)": "add_mmc_arm_average",
        "L1 Multilevel (ex27)": "add_mmc_arm_multilevel",
        "L2 Equivalent (ex28)": "add_mmc_arm_equivalent",
        "L3 Detailed   (ex26)": "add_mmc_arm_detailed",
    }
    for label, fname in EXAMPLES.items():
        path = ROOT / "examples" / fname
        if not path.is_file():
            print(f"{label:<22} | MISSING {fname}")
            all_ok = False
            continue
        counters.clear()
        conv = CircuitConverter(compat)
        conv.build(_circuit_data(path))
        row = f"{label:<22} | " + " | ".join(
            f"{counters.get(n, 0):<11}" for n in ARM_FNS)
        # Verify ONLY the expected constructor fired (6 arms each).
        exp = expected_for[label]
        ok = counters.get(exp, 0) == 6 and all(
            counters.get(n, 0) == 0 for n in ARM_FNS if n != exp)
        row += "   " + ("✓ correct model" if ok else "✗ WRONG")
        all_ok &= ok
        print(row)

    # Restore originals.
    for fn_name, orig in originals.items():
        setattr(mmc_mod, fn_name, orig)

    print()
    if not all_ok:
        raise SystemExit("RESULT: dispatch mismatch — see ✗ rows above.")
    print("RESULT: each fidelity dispatches to its OWN pulsim constructor.")
    print("        L3 runs add_mmc_arm_detailed — NOT the L0 average source.\n")

    # --- Part 2: the WAVEFORMS genuinely differ (not just the call) ----------
    # Drive a single L0 and a single L3 arm with the IDENTICAL modulation m(t)
    # and arm current i(t), then compare the arm-voltage v_b they produce.
    import numpy as np
    from pulsim.mmc import MmcArmAverageParams, MmcArmDetailedParams

    m = lambda t: 0.5 * (1.0 + 0.9 * np.sin(2 * np.pi * 60 * t))
    i = lambda t: 20.0 * np.sin(2 * np.pi * 60 * t)
    n_sm, c_sm, v_c0, dur, dt = 4, 1.2e-3, 640.0, 0.033, 2.0e-6
    level = v_c0 / n_sm          # one submodule voltage step
    thr = level * 0.4            # "big jump" = >40 % of a submodule level

    r0 = p.simulate_mmc_arm_average(
        duration=dur, dt=dt, m_b=m, i_b=i,
        params=MmcArmAverageParams(n_sm=n_sm, c_sm=c_sm, v_c0=v_c0))
    # Seed a deliberate submodule imbalance so L3's sort-and-select balancing
    # is visible converging on v_C_spread.
    seed = v_c0 / n_sm + np.linspace(-30.0, 30.0, n_sm)
    r3 = p.simulate_mmc_arm_detailed(
        duration=dur, dt=dt, m_ref=m, i_b=i, initial_v_C_per_sm=seed,
        params=MmcArmDetailedParams(n_sm=n_sm, c_sm=c_sm, v_c0=v_c0,
                                    f_carrier=2000.0))
    j0 = int(np.sum(np.abs(np.diff(np.asarray(r0.v_b))) > thr))
    j3 = int(np.sum(np.abs(np.diff(np.asarray(r3.v_b))) > thr))
    spread0 = float(np.abs(r3.v_C_spread[0]))
    spreadN = float(np.abs(r3.v_C_spread[-1]))

    print(f"Same m(t) & i(t), one arm each, ~2 cycles "
          f"(submodule step = {level:.0f} V):")
    print(f"  L0 Average  : {j0:>4} switching jumps in v_b   "
          f"→ smooth continuous m·v_C envelope")
    print(f"  L3 Detailed : {j3:>4} switching jumps in v_b   "
          f"→ discrete submodule switching staircase")
    print(f"  L3 v_C_spread (submodule imbalance): "
          f"{spread0:.1f} V → {spreadN:.1f} V  "
          f"(sort-and-select balancing; L0 has no such telemetry)")
    print()
    print("Conclusion: the model truly changes. L3 is fast only because the")
    print("switching is computed INSIDE the arm step (b_extra), so the MNA")
    print("system stays L0-sized — same solve cost, real submodule physics.")
    if not (j0 == 0 and j3 > 50):
        raise SystemExit("Waveform check failed: expected L0 smooth, L3 switching.")


if __name__ == "__main__":
    main()
