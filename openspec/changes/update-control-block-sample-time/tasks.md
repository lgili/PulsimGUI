## 1. Implementation
- [ ] 1.1 Add `sample_time` default parameter (`0.0`) to eligible control blocks in `component.py` (excluding scopes/probes).
- [ ] 1.2 Add/centralize helper(s) that identify eligible control blocks and normalize `sample_time`/`sample_period` aliases.
- [ ] 1.3 Remove global control scheduling widgets from `simulation_settings_dialog.py` and related settings wiring.
- [ ] 1.4 Update project/settings load path to migrate legacy global control schedule into per-block `sample_time` when needed.
- [ ] 1.5 Update backend adapter and circuit data builder to derive any required global compatibility options from per-block values.
- [ ] 1.6 Ensure project/template serialization keeps per-block `sample_time` and no longer depends on global control scheduling.

## 2. Tests
- [ ] 2.1 Update solver dialog tests to remove expectations around global control mode/sample time controls.
- [ ] 2.2 Add/adjust model tests asserting default `sample_time=0` for eligible control blocks and no `sample_time` for scopes/probes.
- [ ] 2.3 Add migration tests for legacy project files with `control_mode/control_sample_time`.
- [ ] 2.4 Add backend adapter tests for mixed per-block sample times and derived compatibility options.

## 3. Documentation
- [ ] 3.1 Update docs/user guide section for control blocks to explain `Ts` semantics (`0` auto/continuous, `>0` discrete).
- [ ] 3.2 Remove obsolete references to global control-mode scheduling in simulation settings docs.
