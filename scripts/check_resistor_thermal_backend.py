"""Check whether backend transient result exports resistor thermal telemetry.

Usage:
    PYTHONPATH=src python scripts/check_resistor_thermal_backend.py
    PYTHONPATH=src python scripts/check_resistor_thermal_backend.py --example examples/10_resistor_thermal_scope_smoke.pulsim
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import BackendCallbacks
from pulsimgui.services.simulation_service import SimulationService


def _sync_project_settings(service: SimulationService, project: Project) -> None:
    """Copy persisted project simulation settings into runtime settings."""
    ps = project.simulation_settings
    ss = service.settings
    ss.t_start = float(ps.tstart)
    ss.t_stop = float(ps.tstop)
    ss.t_step = float(ps.dt)
    ss.max_step = float(ps.max_step)
    ss.enable_events = bool(ps.enable_events)
    ss.max_step_retries = int(ps.max_step_retries)
    ss.enable_losses = bool(ps.enable_losses)
    ss.max_newton_iterations = int(ps.max_iterations)
    ss.thermal_ambient = float(ps.thermal_ambient)
    ss.thermal_include_switching_losses = bool(ps.thermal_include_switching_losses)
    ss.thermal_include_conduction_losses = bool(ps.thermal_include_conduction_losses)
    ss.thermal_network = str(ps.thermal_network)
    ss.thermal_policy = str(ps.thermal_policy)
    ss.thermal_default_rth = float(ps.thermal_default_rth)
    ss.thermal_default_cth = float(ps.thermal_default_cth)
    ss.solver = str(ps.solver)
    ss.step_mode = str(ps.step_mode)
    ss.formulation_mode = str(ps.formulation_mode)
    ss.direct_formulation_fallback = bool(ps.direct_formulation_fallback)
    service.settings = ss


def _parse_semver_triplet(version: str | None) -> tuple[int, int, int] | None:
    """Parse ``major.minor.patch`` prefix from version text."""
    text = str(version or "").strip().lstrip("vV")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _is_modern_thermal_trace_contract(version: str | None) -> bool:
    """Return whether backend is expected to expose sampled T(...) thermal traces."""
    parsed = _parse_semver_triplet(version)
    return parsed is not None and parsed >= (0, 6, 5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check backend thermal telemetry for resistor example")
    parser.add_argument(
        "--example",
        type=Path,
        default=Path("examples/10_resistor_thermal_scope_smoke.pulsim"),
        help="Path to the .pulsim example",
    )
    args = parser.parse_args()

    project = Project.load(args.example)
    service = SimulationService()
    _sync_project_settings(service, project)

    backend = service.backend
    if backend is None:
        print("FAIL: no backend selected")
        return 2

    circuit_data = service.convert_gui_circuit(project)
    issue = service._prevalidate_runtime_contract(circuit_data)
    if issue:
        print(f"FAIL: prevalidation error: {issue}")
        return 2

    callbacks = BackendCallbacks(
        progress=lambda *_: None,
        data_point=lambda *_: None,
        check_cancelled=lambda: False,
        wait_if_paused=lambda: None,
    )
    result = backend.run_transient(circuit_data, service.settings, callbacks)

    print(f"Backend: {backend.info.identifier} {backend.info.version}")
    print(f"Transient error: {result.error_message or '<none>'}")
    print(f"Time points: {len(result.time)}")
    print(f"Signals: {sorted(result.signals.keys())[:12]}")

    stats = result.statistics if isinstance(result.statistics, dict) else {}
    metadata = stats.get("virtual_channel_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    thermal_trace_keys = [
        key
        for key in result.signals.keys()
        if str(key).strip().startswith("T(") and str(key).strip().endswith(")")
    ]
    thermal_meta_keys = [
        name
        for name, entry in metadata.items()
        if isinstance(entry, dict)
        and (
            str(entry.get("domain", "")).strip().lower() == "thermal"
            or str(entry.get("component_type", "")).strip().lower() == "thermal_trace"
        )
    ]

    thermal_summary = stats.get("thermal_summary")
    component_rows = stats.get("component_electrothermal")
    if isinstance(component_rows, list):
        r1_row = next((row for row in component_rows if str(row.get("component_name")) == "R1"), None)
    else:
        r1_row = None

    print(f"Thermal trace keys: {thermal_trace_keys}")
    print(f"Thermal metadata keys: {thermal_meta_keys}")
    print(f"Has thermal_summary: {isinstance(thermal_summary, dict)}")
    print(f"thermal_summary: {thermal_summary}")
    print(f"R1 component_electrothermal: {r1_row}")

    has_summary = isinstance(thermal_summary, dict) and r1_row is not None
    has_sampled_trace = bool(thermal_trace_keys and thermal_meta_keys)
    expects_sampled_trace = _is_modern_thermal_trace_contract(backend.info.version)

    if has_summary and has_sampled_trace:
        print("PASS: backend returned thermal summary + sampled thermal trace contract.")
        return 0

    if has_summary and not expects_sampled_trace:
        print(
            "PASS (legacy thermal contract): backend returned summary telemetry. "
            "Sampled T(...) traces are not mandatory for this backend version."
        )
        return 0

    if has_summary and expects_sampled_trace and not has_sampled_trace:
        print(
            "FAIL: backend returned only summary telemetry. "
            "Expected sampled T(...) traces + thermal metadata for this backend version."
        )
        return 1

    print("FAIL: backend did not return resistor thermal telemetry")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
