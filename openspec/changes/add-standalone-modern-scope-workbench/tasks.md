## 1. Architecture and Contracts

- [x] 1.1 Create standalone scope module boundary with zero imports from PulsimGui shell internals
- [x] 1.2 Define and implement host adapter interface for signal catalog, sample streaming, and UI event callbacks
- [x] 1.3 Add compatibility adapter so existing PulsimGui workflows can open the new scope workbench
- [x] 1.4 Define host-agnostic workspace serialization schema (scopes, traces, cursors, measurement columns, panel states)

## 2. Workspace and Multi-Scope UX

- [x] 2.1 Implement scope workspace model (multiple scopes per workspace)
- [x] 2.2 Add `+ Scope`, duplicate scope, rename scope, remove scope interactions
- [x] 2.3 Support multiple signals per scope with drag/drop mapping and overlay/separate pane behavior
- [x] 2.4 Persist and restore per-scope independent state

## 3. Sidebar (Collapsible)

- [x] 3.1 Implement left sidebar sections (scopes, signal catalog, trace manager, quick actions)
- [x] 3.2 Implement collapse-to-rail behavior with `Ctrl+B` shortcut and animated transition
- [x] 3.3 Persist sidebar collapsed/expanded state per workspace
- [x] 3.4 Ensure full keyboard navigation and accessible tooltips in collapsed mode

## 4. Cursor and Contextual Bottom Panel

- [x] 4.1 Implement cursor state machine (`NoCursor`, `SingleCursor`, `DualCursor`)
- [x] 4.2 Show bottom panel only when cursors are enabled; hide when disabled
- [x] 4.3 Add `+ Add Measurement` flow to let users choose visible measurement columns
- [x] 4.4 Implement interval selection targets (visible window, A, B, A→B)
- [x] 4.5 Ensure measurement values update in real time during cursor drag

## 5. PLECS-Inspired Analysis Features

- [x] 5.1 Implement saved views list for named zoom/time ranges
- [x] 5.2 Implement trace manager with visibility toggle, active trace selection, and color editing
- [x] 5.3 Implement zoom overview mini-panel synced to the active plot window
- [x] 5.4 Ensure UI behavior follows PLECS analysis flow while using modernized visual styling

## 6. Visual System and Theming

- [x] 6.1 Define scope-specific design tokens (spacing, radius, color, typography)
- [x] 6.2 Implement modern high-contrast style for charts, grid, cursor labels, and data table
- [x] 6.3 Add subtle transitions for panel open/collapse and cursor panel reveal (< 180 ms)
- [x] 6.4 Validate readability in light/dark themes and HiDPI scaling

## 7. Testing and Documentation

- [x] 7.1 Add deterministic unit tests for measurement engine and cursor math
- [x] 7.2 Add headless GUI tests for sidebar collapse and contextual bottom panel behavior
- [x] 7.3 Add integration tests using a placeholder/fake backend publisher
- [x] 7.4 Update user docs with multi-scope and measurement-column workflows
- [x] 7.5 Run validation locally: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen pytest tests/`
