## Why
Current waveform visualization relies on a single global scope dock and ad-hoc probes. Users building Simulink/Plecs-style control systems expect dedicated scope blocks that capture signals, configurable multi-trace layouts, and mux/demux utilities. We also need to mirror this workflow for upcoming thermal analysis so users can organize electrical and thermal plots per subsystem. Without scope components the schematic cannot describe which signals to persist, how to group them, or how to rename traces.

## What Changes
- Introduce electrical and thermal scope components that let users configure the number of inputs, per-trace grouping, and custom signal naming.
- Add mux and demux control blocks so multiple single-wire signals can be combined/split before entering scopes.
- Allow inline wire naming/override so scope traces show user-friendly names regardless of node labels.
- Launch dedicated floating scope windows (one per scope block) instead of forcing everything into the docked viewer, while still reusing shared waveform/thermal viewer features.
- Ensure scope configuration is saved with the project and restored on load.

## Impact
- Specs impacted: `waveform-viewer`, `thermal-viewer`, `schematic-editor`, `component-library`.
- Code impacted: component metadata/models, schematic items, properties panel, waveform/thermal viewer services, persistence model, simulation signal routing.
