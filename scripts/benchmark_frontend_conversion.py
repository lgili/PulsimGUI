#!/usr/bin/env python3
"""Benchmark frontend circuit conversion latency.

This script helps contributors validate conversion-path performance changes
without opening the GUI.
"""

from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

from pulsimgui.models.project import Project
from pulsimgui.services.simulation_service import SimulationService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark GUI->runtime circuit conversion")
    parser.add_argument(
        "--project",
        type=Path,
        default=Path("examples/09_buck_closed_loop_loss_thermal_validation.pulsim"),
        help="Path to .pulsim project file",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=30,
        help="Number of benchmark runs",
    )
    return parser.parse_args()


def _time_call(fn) -> float:
    start = time.perf_counter()
    fn()
    end = time.perf_counter()
    return (end - start) * 1_000.0


def _stats(samples: list[float]) -> tuple[float, float, float]:
    return min(samples), statistics.mean(samples), max(samples)


def main() -> int:
    args = _parse_args()
    if args.runs <= 0:
        raise ValueError("--runs must be > 0")
    if not args.project.exists():
        raise FileNotFoundError(args.project)

    project = Project.load(args.project)

    # Cold path: new SimulationService every run.
    cold_samples: list[float] = []
    for _ in range(args.runs):
        service = SimulationService()
        cold_samples.append(_time_call(lambda service_instance=service: service_instance.convert_gui_circuit(project)))

    # Warm path: same service instance should hit conversion cache.
    service = SimulationService()
    _ = service.convert_gui_circuit(project)
    warm_samples = [_time_call(lambda: service.convert_gui_circuit_cached(project)) for _ in range(args.runs)]

    cold_min, cold_avg, cold_max = _stats(cold_samples)
    warm_min, warm_avg, warm_max = _stats(warm_samples)

    print(f"Project: {args.project}")
    print(f"Runs: {args.runs}")
    print("\nCold conversion (new service each run):")
    print(f"  min={cold_min:.3f} ms  avg={cold_avg:.3f} ms  max={cold_max:.3f} ms")
    print("Warm conversion (cached worker path):")
    print(f"  min={warm_min:.3f} ms  avg={warm_avg:.3f} ms  max={warm_max:.3f} ms")

    if warm_avg > 0:
        speedup = cold_avg / warm_avg
        print(f"\nEstimated warm-path speedup: {speedup:.2f}x")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
