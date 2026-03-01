## 1. Specification Alignment
- [ ] 1.1 Review waveform, thermal, schematic-editor, and component-library specs to finalize scope block UX details
- [ ] 1.2 Confirm persistence format updates needed for scope component settings and wire aliases

## 2. Component and Editor Updates
- [ ] 2.1 Extend component models/properties to represent electrical scope, thermal scope, mux, and demux blocks with configurable channel counts
- [ ] 2.2 Update library metadata and icons so the new components appear in the Control Blocks category with previews and default parameters
- [ ] 2.3 Implement schematic items, pin layouts, and drag/drop placement flows for the new components, including multiple wires per scope input when overlay is enabled
- [ ] 2.4 Add inline wire alias editing (interaction, rendering, persistence, undo/redo) and ensure aliases propagate to probes and scopes
- [ ] 2.5 Wire up properties panel editors for scope channel settings, overlay toggles, and mux/demux channel labeling

## 3. Viewer and Persistence Work
- [ ] 3.1 Create per-component waveform viewer windows that subscribe to the signals defined by each electrical scope block and store their state in the project
- [ ] 3.2 Create per-component thermal viewer windows with the same behavior for thermal scopes
- [ ] 3.3 Ensure simulation output routing delivers the requested signals (respecting aliases) into each scope window, covering mux/demux paths
- [ ] 3.4 Persist scope window state, channel metadata, and wire aliases in project saves/loads, including backward compatibility defaults

## 4. Validation
- [ ] 4.1 Add unit tests for component models, alias handling, and persistence serialization
- [ ] 4.2 Add GUI/service tests for opening scope windows, overlay plotting, and mux/demux signal ordering
- [ ] 4.3 Update documentation/tutorials with instructions for the new scope workflow
