#!/usr/bin/env python3
"""Diagnose the ex25 'PwlStateSpaceCache singular at dt=5e-07' failure.

Run this IN YOUR environment (the one where the GUI fails) and paste the
full output. It prints, for the switched-CMC example:

  * the installed pulsim version + the backend_adapter commit in effect,
  * the converted switch count,
  * a CLEAN headless run at the example's dt (does it work at all?),
  * and — patching the backend to be verbose — the dt + error of EVERY
    retry attempt, so we see exactly which attempt produces the 5e-7
    singular-cache error and whether the FIRST (2 us) attempt fails.

Usage:
    source .venv/bin/activate
    python scripts/diagnose_ex25.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pulsim as ps

from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import BackendCallbacks, PulsimBackend
from pulsimgui.services.simulation_service import SimulationService

REPO = Path(__file__).resolve().parents[1]
EX = REPO / "examples" / "25_cmc_switched_svm_cblock.pulsim"


def main() -> None:
    print("=" * 60)
    print("pulsim version:", getattr(ps, "__version__", "?"))
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        print("repo HEAD:", sha)
    except Exception as exc:  # noqa: BLE001
        print("repo HEAD: <unknown>", exc)
    print("has _is_pwl_cache_singular_error guard:",
          hasattr(PulsimBackend, "_is_pwl_cache_singular_error"))
    print("=" * 60)

    project = Project.from_dict(json.loads(EX.read_text()), path=EX)
    svc = SimulationService()
    svc.apply_project_simulation_settings(project)
    print("configured t_step:", svc.settings.t_step,
          "| max_step:", svc.settings.max_step,
          "| enable_events:", svc.settings.enable_events)

    cd = svc.convert_gui_circuit(project)
    comps = cd.get("components", [])
    n_bidi = sum(1 for c in comps if c.get("type") == "BIDIRECTIONAL_SWITCH")
    n_mos = sum(1 for c in comps if c.get("type") == "MOSFET_N")
    print(f"components: {len(comps)} | BIDIRECTIONAL_SWITCH={n_bidi} MOSFET_N={n_mos}")

    # Patch _run_transient_once to log every attempt's dt + error.
    orig = PulsimBackend._run_transient_once

    def logged(self, circuit, circuit_data, settings, callbacks, dt,
               x0, newton_opts, linear_solver):
        res = orig(self, circuit, circuit_data, settings, callbacks, dt,
                   x0, newton_opts, linear_solver)
        err = (res.error_message or "")[:90]
        print(f"  ATTEMPT dt={dt:.3e} -> {'OK' if not err else 'ERR: ' + err}")
        return res

    PulsimBackend._run_transient_once = logged
    try:
        backend = svc.backend
        NLS = getattr(ps, "NativeLiveStream", None)
        ls = NLS(capacity=200_000, decimate=100) if NLS else None
        cb = BackendCallbacks(
            progress=lambda *a: None, data_point=lambda *a: None,
            check_cancelled=lambda: False, wait_if_paused=lambda: None,
            live_stream=ls,
        )
        print("--- running via backend (with live_stream, like the GUI) ---")
        res = backend.run_transient(cd, svc.settings, cb)
        print("--- FINAL ---")
        print("  error:", repr(res.error_message))
        print("  samples:", len(res.time) if res.time is not None else 0)
    finally:
        PulsimBackend._run_transient_once = orig


if __name__ == "__main__":
    main()
