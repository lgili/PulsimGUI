# Frontend Architecture and Performance

This page describes the main frontend runtime paths in `PulsimGui` and the conventions used to keep the app fast, lightweight, and contributor-friendly.

## Architecture at a Glance

```text
views (Qt UI)
  -> services (state orchestration and backend adapters)
    -> models (project/circuit/component/wire data)
      -> utils (connectivity and helper algorithms)
```

Core modules:

- `views/`: UI widgets, dialogs, and user interaction flow.
- `services/simulation_service.py`: simulation orchestration, worker lifecycle, runtime contracts.
- `services/circuit_data_builder.py`: GUI -> canonical `pulsim-v1` payload conversion with cache.
- `services/backend_adapter.py`: backend capability detection and execution paths.
- `utils/net_utils.py`: circuit connectivity (`node_map`, aliases, domain-safe net merges).

## Performance-Critical Path

The most latency-sensitive operation before any simulation is:

1. project/circuit read,
2. connectivity build (`build_node_map`),
3. runtime payload generation.

To keep this path fast:

- Conversion logic is isolated in `CircuitDataBuilder`.
- Conversion results are cache-backed using a project/settings signature.
- Worker-thread conversion can reuse cached payload without deep copy.
- Public conversion still returns detached copies to avoid shared-state mutation bugs.

## Cache Behavior

`CircuitDataBuilder` invalidates cache when any of these change:

- active circuit identity,
- project `modified` timestamp,
- component/wire counts,
- runtime simulation contract fields (`tstop`, `dt`, control/thermal/formulation settings).

This gives fast repeated runs while preserving correctness when topology/settings change.

## Contributor Rules (Frontend)

When adding or changing frontend code:

1. Keep UI code out of backend conversion logic.
2. Keep conversion/data logic out of widget classes.
3. Add tests for behavior changes, especially around runtime contracts and conversion.
4. For performance work, prefer algorithm/dataflow improvements over micro-optimizations.
5. Avoid hidden mutable shared state between UI thread and worker thread.

## Recommended Validation Before PR

```bash
PYTHONPATH=src python3 scripts/smoke_templates.py
PYTHONPATH=src QT_QPA_PLATFORM=offscreen pytest tests/test_services/test_simulation_service_runtime.py
PYTHONPATH=src QT_QPA_PLATFORM=offscreen pytest tests/test_services/test_template_service.py
```

If a change impacts release stability, also validate:

```bash
PYTHONPATH=src python3 scripts/sim_buck_closed_loop.py --t-stop 0.01 --dt 1e-6
```

## Where to Start as a New Contributor

- Runtime contracts and safety checks: `SimulationWorker._append_runtime_contract_checks`.
- Circuit conversion and cache: `services/circuit_data_builder.py`.
- Template loading and consistency: `services/template_service.py` and `scripts/smoke_templates.py`.
- Connectivity rules and net domains: `utils/net_utils.py`.
