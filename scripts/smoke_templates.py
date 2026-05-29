#!/usr/bin/env python3
"""Pre-release smoke tests for built-in template projects.

This script validates that default app templates:
1. convert to canonical runtime data,
2. pass front-end contract prevalidation, and
3. complete transient simulation without backend errors.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import BackendCallbacks
from pulsimgui.services.simulation_service import SimulationService

TEMPLATE_EXPECTED_SIGNALS: dict[str, set[str]] = {
    "buck_converter.pulsim": {"Xsw", "Xout"},
    "boost_converter.pulsim": {"X1", "X2"},
    "flyback_converter.pulsim": {"Xsw", "Xout"},
    "buck_converter_closed_loop.pulsim": {"PI1", "PWM1.duty", "Xsw", "Xout"},
}


def _copy_project_settings(service: SimulationService, project: Project) -> None:
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
    ss.enable_voltage_limiting = bool(ps.enable_voltage_limiting)
    ss.max_voltage_step = float(ps.max_voltage_step)
    ss.solver = str(ps.solver)
    ss.step_mode = str(ps.step_mode)
    ss.dc_strategy = str(ps.dc_strategy)
    ss.gmin_initial = float(ps.gmin_initial)
    ss.gmin_final = float(ps.gmin_final)
    ss.dc_source_steps = int(ps.dc_source_steps)
    ss.transient_robust_mode = bool(ps.transient_robust_mode)
    ss.transient_auto_regularize = bool(ps.transient_auto_regularize)
    ss.thermal_ambient = float(ps.thermal_ambient)
    ss.thermal_include_switching_losses = bool(ps.thermal_include_switching_losses)
    ss.thermal_include_conduction_losses = bool(ps.thermal_include_conduction_losses)
    ss.thermal_network = str(ps.thermal_network)
    ss.thermal_policy = str(ps.thermal_policy)
    ss.thermal_default_rth = float(ps.thermal_default_rth)
    ss.thermal_default_cth = float(ps.thermal_default_cth)
    ss.formulation_mode = str(ps.formulation_mode)
    ss.direct_formulation_fallback = bool(ps.direct_formulation_fallback)
    ss.control_mode = str(ps.control_mode)
    ss.control_sample_time = float(ps.control_sample_time)
    service.settings = ss


def _run_template(path: Path) -> tuple[bool, str]:
    """Run one template smoke test."""
    if not path.exists():
        return False, f"missing template file: {path}"

    project = Project.load(path)
    service = SimulationService()
    _copy_project_settings(service, project)

    circuit_data = service.convert_gui_circuit(project)
    contract_error = service._prevalidate_runtime_contract(circuit_data)
    if contract_error:
        return False, f"prevalidation failed: {contract_error}"

    backend = service.backend
    if backend is None:
        return False, "backend is unavailable"

    callbacks = BackendCallbacks(
        progress=lambda *_: None,
        data_point=lambda *_: None,
        check_cancelled=lambda: False,
        wait_if_paused=lambda: None,
    )
    result = backend.run_transient(circuit_data, service.settings, callbacks)
    if result.error_message:
        return False, result.error_message

    if not result.time:
        return False, "simulation returned no time samples"

    tstop = float(service.settings.t_stop)
    tend = float(result.time[-1])
    if not math.isfinite(tend) or tend < (tstop * 0.999):
        return False, f"simulation ended early (t_end={tend:.9g}, t_stop={tstop:.9g})"

    expected = TEMPLATE_EXPECTED_SIGNALS.get(path.name, set())
    if expected:
        available = set(result.signals.keys())
        missing = sorted(expected - available)
        if missing:
            return False, f"missing expected signals: {', '.join(missing)}"

    return True, f"ok (samples={len(result.time)}, t_end={tend:.9g})"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test built-in PulsimGui templates")
    parser.add_argument(
        "--templates-dir",
        type=Path,
        default=Path("src/pulsimgui/resources/templates"),
        help="Directory containing .pulsim templates",
    )
    parser.add_argument(
        "--templates",
        nargs="*",
        default=sorted(TEMPLATE_EXPECTED_SIGNALS.keys()),
        help="Template file names to validate",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    templates_dir = args.templates_dir

    failures: list[str] = []
    for template_name in args.templates:
        template_path = templates_dir / template_name
        ok, details = _run_template(template_path)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {template_name}: {details}")
        if not ok:
            failures.append(template_name)

    if failures:
        print(f"\nTemplate smoke failed for {len(failures)} file(s).")
        return 1

    print("\nAll template smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
