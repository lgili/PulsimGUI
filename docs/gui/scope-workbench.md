# Scope Workbench

The Scope Workbench is a PLECS-inspired signal analysis environment that opens when you
double-click a scope component or select **View → Scope Workbench** from the main menu.
It supports multiple independent scopes per simulation, grouped signal panels, cursor-driven
measurements, saved zoom views, and a collapsible sidebar.

---

## Sidebar

The left sidebar is organised into four tabs.

| Tab | Contents |
|-----|----------|
| **Signals** | All signals available in the current scope, grouped by source block. Toggle visibility with the checkbox; drag a row onto a plot pane to reassign it. |
| **Scopes** | List of open scope tabs. Click to switch; right-click for rename / duplicate / remove. |
| **Traces** | Per-signal trace controls: visibility toggle, color swatch, line width. |
| **Views** | Saved zoom/time ranges (see [Saved Views](#saved-views)). |

### Collapse to rail

Press **Ctrl+B** or click the **◀** button at the top of the sidebar to collapse it to a
narrow icon rail. Click any icon in the rail to jump directly to that tab and expand the
sidebar again. The expanded/collapsed state is stored per workspace.

---

## Multiple Scopes

Each simulation session can have several independent scopes with their own signal sets,
plot layouts, and measurement configurations.

| Action | How |
|--------|-----|
| Add a scope | Click **+ Scope** in the Scopes tab or use the toolbar button. |
| Duplicate | Right-click a scope entry → **Duplicate**. |
| Rename | Double-click the scope name in the tab or the Scopes list. |
| Remove | Right-click → **Remove** (last scope is reset, never deleted). |

Switching scopes restores each scope's independent cursor position, zoom level, and
visible measurement columns.

---

## Signal Pane Layout

Signals can be displayed on **separate stacked panes** (one signal per row) or **overlaid
on the same pane**.

- **Drag** a signal row in the Signals tab onto an existing plot pane to overlay it.
- **Right-click** a signal → **Send to pane** to choose a specific pane by leader signal.
- **Right-click** a signal → **Separate pane** to give it its own row.
- Click **Split all** in the toolbar to restore every signal to its own dedicated pane.

Signal colors are assigned automatically from the palette and kept in sync between the
Signals tab, the trace manager, and the measurement table.

---

## Cursors and Bottom Panel

Enable cursors with the **Cursors** checkbox in the right toolbar or by pressing **C**.
The bottom measurement panel appears automatically when cursors are active and hides when
they are disabled.

### Cursor modes

| Mode | Activation |
|------|-----------|
| Single cursor (A) | Enable cursors — one vertical line appears. |
| Dual cursor (A + B) | Drag a second cursor from the cursor-A handle or press **D**. |

Measurement values update in real time while you drag a cursor.

### Interval target

The **interval selector** (right toolbar drop-down) controls the time window used for
statistical measurements.

| Option | Description |
|--------|-------------|
| **A→B** | Between cursor A and cursor B (default). |
| **Visible Window** | The currently visible horizontal extent of the plot. |
| **Cursor A** | A small window centred on cursor A. |
| **Cursor B** | A small window centred on cursor B. |

### Visible measurement columns

Click **+ Add Measurement** in the bottom panel header to choose which statistics are
shown. Available columns:

| Key | Label | Description |
|-----|-------|-------------|
| `rms` | RMS | Root-mean-square value over the interval. |
| `max` | Peak | Maximum sample value. |
| `min` | Min | Minimum sample value. |
| `pkpk` | Pk-Pk | Peak-to-peak amplitude (`max − min`). |
| `mean` | Mean | Arithmetic mean. |
| `c1` | C1 | Value at cursor A. |
| `c2` | C2 | Value at cursor B. |
| `dv` | ΔV | Difference between cursor B and cursor A values. |

Colored signal dots in the row headers identify each signal at a glance.

---

## Saved Views

A *Saved View* stores a named time range and optional Y-axis bounds so you can return to
an area of interest with a single click.

1. Zoom/pan the plot to the region you want to capture.
2. In the **Views** tab, click **Save view** and enter a name.
3. To restore a view, select it in the list and click **Apply view** (or double-click).
4. To delete, select the view and click **Delete**.

Saved views are serialised with the workspace state and restored across sessions.

---

## Zoom Overview

A compact **overview mini-panel** (80 px tall) appears below the main plots. It shows all
signals at full time scale with a shaded region indicating the currently visible window.
Drag the shaded region to pan, or resize its edges to zoom, without losing the global
context.

---

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Toggle sidebar collapse | `Ctrl+B` |
| Enable / disable cursors | `C` |
| Toggle dual cursor | `D` |
| Zoom in / out (time axis) | Scroll wheel |
| Zoom Y axis | `Shift` + scroll |
| Zoom both axes | `Ctrl` + scroll |
| Copy plot image | toolbar copy button |
| Split all panes | toolbar split button |
