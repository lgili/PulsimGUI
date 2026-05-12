# PulsimGui — Professional UI/UX Audit (May 2026)

> **Wave-1 release shipped as PulsimGui v0.8.1** — see the
> `polish-pro-uiux-wave-1` OpenSpec change for the per-task status
> table. The P0 regression fixes + Run Bar (P1.2) + Solver pill
> (P1.3) are in v0.8.1. P1.7, P1.10, P1.11 (stale-dot), and all of
> wave-2 below are deferred to a future release.
>
> **Baseline:** PulsimGui v0.8.0 (released against Pulsim 0.9.0).
> Captured on macOS 14 against `examples/09_buck_closed_loop_loss_thermal_validation.pulsim`.
> Comparative benchmarks: PSIM 2025, PLECS 4.x, LTspice XVII, Altium 24, KiCad 8, Simulink 2024b, VS Code, Figma, Linear.

## Executive summary

PulsimGui has already absorbed **a lot** of polish: the
`refactor-visual-ux-overhaul` change (12 sections, 90+ tasks) plus
`update-professional-ui-consistency` are both archived as completed.
Card-based palette, animated docks, quick-add palette (Ctrl+K), context
menus, status banners, minimap, zoom slider, smooth wire rendering,
StatusBanner widget — all shipped.

What separates "polished" from "professional-tool-grade" today is **not
more features** — it's the second wave: **information architecture,
state visibility, and signature workflows**. The schematic editor still
feels like a generic tool with a pretty skin; PLECS / PSIM feel like
power-electronics tools the moment you open them.

This document catalogs the remaining gaps and proposes a **3-wave
roadmap** (P0 / P1 / P2) to close them. P0 items are <1 week each and
fix observable bugs / regressions. P1 = the high-leverage architecture
changes. P2 = the brand-defining moments.

## Section 1 — Observed regressions and bugs (P0, ship within a week)

### 1.1 Status bar shows stale Pulsim version

The status bar reads **"Pulsim 0.5.1"** even after we shipped v0.9.0
today. The badge is hardcoded somewhere, not derived from
`pulsim.__version__`. **User-visible mistake** — first thing a returning
user notices is "the version didn't move."

> **Fix:** read `pulsim.__version__` at import time, fall back to
> "unknown" gracefully. Render in the status bar's "backend" segment.

### 1.2 Open-project does not auto-fit the schematic

Opening `09_buck_closed_loop_loss_thermal_validation.pulsim` drops the
circuit into the bottom-right corner of the viewport, half clipped. The
user has to manually press F-to-fit before they can see what they
opened. **Highest-friction first-impression bug.**

> **Fix:** call `view.fit_to_content()` (or equivalent) at the end of
> `_open_project_file`. Optional: animate from the current view to the
> fit view (250 ms ease-out) so the user *sees* the schematic land.

### 1.3 Toolbar undo/redo appears twice

The top toolbar has the cluster `[new][open][save] [undo][redo]
[zoom-in][zoom-out][fit] [add][route][pan] [undo][redo] …`. Undo/redo
shows up in two clusters. Either duplicate or one is meant to be
"history forward/backward" in a different sense — either way it reads
as a bug.

> **Fix:** keep one undo/redo cluster. If history nav is intentional,
> rename the second pair (e.g. "step back / forward in history" with
> different glyphs).

### 1.4 Component card titles truncate

The "Transformer" card shows **"ransforme"** (clipped left + missing
final r) and "Sat. Inductor" wraps to two lines while neighbors are
single-line. The width budget is too tight for the longer labels.

> **Fix:** auto-shrink font 1pt below threshold OR widen the card by
> 8 px OR truncate with an ellipsis + show full name in tooltip. Match
> Linear's component-row pattern: name on hover/focus shows full text.

### 1.5 Shortcut hint inconsistency

The palette cards show shortcuts as `"R"`, `"C"`, `"L"`, `""` (empty),
`"M"`, `"Shift+M"`. Three issues:
- Empty strings leave dead vertical space — collapse them.
- Single letters render bold but compound shortcuts render plain;
  inconsistent typography.
- macOS users expect `⌘+M`, not `Cmd+M`. The "Shift+M" reads
  Windows-native.

> **Fix:** centralize shortcut rendering in
> `pulsimgui.utils.shortcut_format(QKeySequence)` and respect platform.

## Section 2 — Information architecture (P1)

### 2.1 Title bar wastes vertical space

macOS title bar is empty (system-painted). Industry-standard pro tools
(VS Code, Figma, Linear) **claim the title bar** via a unified-titlebar
window to recover ~28 px of vertical real estate and surface the
project name + breadcrumbs + presence indicators there.

> **Proposal:** unified titlebar
>
> ```
>  ●●●  PulsimGui  ▸  examples  ▸  buck_closed_loop  *unsaved   [⊞ Schematic] [📊 Scope] [⚙ Settings]
> ```
>
> Left: traffic-light + breadcrumb. Center: file + dirty indicator. Right:
> view-switcher (chord tabs) for the major surfaces.

### 2.2 No persistent file/project context

The current title bar (when shown) only displays "PulsimGui -
buck_converter.pulsim". The user has zero answer for:
- "Where on disk is this file?"
- "Am I in a Git-tracked project?"
- "What's the last simulation result attached to this circuit?"
- "Which sub-circuit am I editing?" (when navigating into a
  `subcircuit` block)

> **Proposal:** persistent **left-rail "Project" tab** (collapsible)
> with: project tree, recent files, templates, snippets, current
> simulation telemetry (last run timestamp, dt, integrator, total
> samples). Similar to VS Code's Explorer panel but power-electronics-
> shaped.

### 2.3 Simulation controls feel disconnected

The four small icons at top-right (play / pause / stop / scope) work
but read as toolbar buttons, not as **simulation control**. PLECS and
PSIM both have a prominent control band — a frame around play / pause
/ stop + progress bar + dt readout. Pulsim's controls are easily
overlooked.

> **Proposal:** **Run Bar** floating above the canvas (or pinned to
> top of status bar) when a simulation is configured:
>
> ```
>  [▶ Run]  [⏸]  [■]      ▏  ░░░░░░░░░░░░  ▏  t = 12.4 / 50.0 ms   2.3× realtime   ⊕ Console
> ```
>
> Click `Run` → it morphs into a progress bar with elapsed time, step
> count, current dt, realtime factor. Click console expands a fold-out
> log with the live `pulsim.LogLevel` stream.

### 2.4 No surfacing of current solver / parameters

Right now the user can't see "what integrator am I about to run?" without
opening Simulation → Settings. For a tool whose differentiator is
**numerical fidelity** (TR-BDF2, RosenbrockW, JFNK, KLU), the active
solver should be **glanceable**.

> **Proposal:** **Solver pill** in the status bar:
>
> `🟢 TR-BDF2 · dt=1µs · KLU · adaptive ▾`
>
> Click → opens the Settings dialog focused on solver section. Color =
> health (green = converged last run, amber = retried, red = failed).

## Section 3 — Visual design (P1)

### 3.1 Color system lacks semantic anchoring

Pulsim's GUI uses:
- **Green** for play button, minimap tint, electrical net highlighting,
  and now the new "Three-Phase / Vector Control" palette category.
- **Orange** for thermal/heat overlays.
- **Blue** for selection / control signals.
- **Red** for errors and the LED component.

But the meaning isn't reinforced anywhere. PSIM trains the user to
read its color palette through repeated, **consistent** mapping:
voltage = orange, current = blue, power = green, control = yellow.

> **Proposal:** publish a **color semantics document** and enforce
> via `theme_service` tokens:
>
> | Token | Hex (dark) | Hex (light) | Used for |
> |---|---|---|---|
> | `--electrical` | `#22c55e` | `#16a34a` | Live electrical traces |
> | `--control` | `#3b82f6` | `#2563eb` | Control / signal channels |
> | `--thermal` | `#f97316` | `#ea580c` | Thermal sub-network |
> | `--magnetic` | `#a855f7` | `#7c3aed` | Magnetic / flux |
> | `--three-phase` | `#7c3aed` | `#6d28d9` | Vector control (new) |
> | `--error` | `#ef4444` | `#dc2626` | Faults, invalid wiring |
>
> **Risk to manage:** my new "Three-Phase / Vector Control" purple
> category now competes with the "magnetic" purple I'm proposing. Pick
> one before this ships.

### 3.2 Typography is single-weight

Every label in the GUI uses the same font weight + size. The
information hierarchy carries no typographic signal — the user has to
read text content to know if it's a section title, a parameter name, or
a value. Compare to Linear / Figma: 4 weights × 6 sizes form a
disciplined scale.

> **Proposal:** adopt **Inter** (or **Geist**) as the variable font,
> codify a 5-step scale:
>
> | Token | Size / Weight | Use |
> |---|---|---|
> | `display` | 20/600 | Window title segment, breadcrumb root |
> | `heading` | 16/600 | Dialog titles, panel headers |
> | `subheading` | 13/600 | Section labels in properties panel |
> | `body` | 12/400 | Default UI text |
> | `code` | 11/500 mono | Channel names, parameter keys, IDs |
> | `caption` | 10/500 | Help/hint text, shortcut hints |

### 3.3 Minimap floats as a decoration

The minimap is a green-tinted rounded square hovering top-left over the
canvas. It looks **pasted on** — no header, no close handle, no
position lock. It also flicker-resizes during pan.

> **Proposal:** apply the **panel chrome** standard to the minimap:
>
> - 1 px stroked border + soft drop shadow (theme-token)
> - tiny header bar: "Map" + close (×) + position-lock (📌) icons
> - drag-to-reposition only from header
> - corner-snap (top-left/right/bottom-left/right) with 8 px inset
> - 50% opacity when the mouse leaves the canvas

### 3.4 Component icons inconsistent weight

The library glyphs (resistor, capacitor, etc.) use different stroke
weights — diode lines look thinner than MOSFET lines, and the Zener vs
LED indicators have different scales. They were drawn ad-hoc, not on a
grid.

> **Proposal:** redraw the icon set on a **24 × 24 grid, 1.5 px
> stroke, 2 px corner radius**, optimized as SVG. Match
> [Lucide](https://lucide.dev) visual language. Side benefit: makes the
> palette readable at 75 % zoom on low-DPI screens.

## Section 4 — Density and the schematic workspace (P1)

### 4.1 Wire labels collide

In the buck-converter screenshot the labels `Vin`, `Vout`, `Xsw`, `GND`,
`SW`, `220u H` all crowd the same horizontal slice. There's no
collision avoidance: labels rendered at fixed offsets relative to wire
endpoints, ignoring overlap.

> **Proposal:** when two label boxes intersect, automatically:
>
> 1. shift one along the wire by ±20 px (snap to grid)
> 2. if still colliding, switch from "above the wire" to "below the
>    wire"
> 3. if still colliding, swap to leader-line + offset (Altium pattern)

### 4.2 No "what is connected to what" reveal

Selecting a wire highlights it. But selecting a **net** (the equivalence
class of connected wires) doesn't visually reveal the full net. For
debugging "why isn't this circuit converging," users have to trace the
net by hand.

> **Proposal:** hover on a junction or wire highlights the entire net
> with a glow ring. Selecting a junction shows a HUD overlay listing
> every component pin on this net (`R1.1 → Cout.1 → SCOPE1.CH0`).

### 4.3 The "empty canvas" state is a textbox

```
Start your schematic
Drag components here from the library.
Press Ctrl+K to quick-add a component.
Use the mouse wheel to zoom and middle-drag to pan.
```

It's helpful but it's a *paragraph*. Modern empty states are
**action-oriented cards**:

> **Proposal:**
>
> ```
>  ┌─────────────────────┐   ┌─────────────────────┐
>  │ ▭▭ Blank schematic  │   │ ✨ Quick-add (⌘K)    │
>  │  Start from scratch │   │  Component palette  │
>  └─────────────────────┘   └─────────────────────┘
>
>  ┌─────────────────────┐   ┌─────────────────────┐
>  │ 📦 Templates        │   │ 📂 Recent files     │
>  │  Buck, Boost, LLC,  │   │  09_buck_closed...  │
>  │  full-bridge, FOC   │   │  buck_converter...  │
>  └─────────────────────┘   └─────────────────────┘
> ```
>
> Cards have hover lifts and click to act. **Templates** card opens
> the existing template dialog; **Recent files** lists the last 8.

## Section 5 — Motion and feedback (P1)

### 5.1 No "loading" state for circuit open

Loading a moderately-large circuit (the 16-component buck) is
instantaneous on the dev machine, but on Windows with antivirus or on
network drives it can take 1–3 seconds. **There's no visual
acknowledgment** that the click registered.

> **Proposal:** loading scrim with skeleton outline of the schematic,
> identical pattern to Notion / Linear / Figma. The empty-state card
> grid is the fallback once we know the file path is valid but
> contents aren't ready.

### 5.2 Simulation has no spatial progress

When you click Run, the only visible feedback is "Idle → Completed"
in the status bar. The user can't tell if it's **stuck in a Newton
inner loop** or **just slow**. PLECS shows a live timeline cursor
sweeping across the scope window during simulation.

> **Proposal:** during simulation, the scope window's time axis
> displays a **live sweep cursor** updated at 30 fps from the
> simulator's reported `t_current / t_stop` ratio. Same cursor optionally
> on the schematic (small clock icon on the canvas's top-left).

### 5.3 No error feedback at the failing site

When YAML emission fails (unconnected pin, missing parameter, invalid
input), the user gets a modal `QMessageBox` with a stack-style error.
The schematic itself doesn't tell them which component is broken.

> **Proposal:** **inline diagnostics layer**: failing components get
> a small red badge (1) on their corner; hovering the badge shows the
> error tooltip; clicking jumps the properties panel to the offending
> field with a red outline. **VS Code-style diagnostics.**

### 5.4 No optimistic UI on parameter edit

Editing a parameter in the properties panel updates the model
immediately, but there's no signal that the schematic is now "dirtied"
relative to the last saved version vs the last simulated version.

> **Proposal:** **dirty indicators** at three resolutions:
>
> - file dirty: titlebar shows `* unsaved`
> - simulation dirty: every component touched since the last successful
>   run gets a tiny yellow dot
> - waveform stale: scope window header says "stale (rerun)" with a
>   one-click "Re-run" button

## Section 6 — Power-user surfaces (P2)

### 6.1 Command palette is single-purpose

Ctrl+K opens the quick-add palette today (components only). Pro tools
use the **same shortcut** for everything: VS Code, Linear, Notion,
Figma all use Cmd/Ctrl+K as a global command palette.

> **Proposal:** generalize to a **fuzzy-search command palette** with
> typed prefixes:
>
> | Prefix | Scope | Examples |
> |---|---|---|
> | `>` | Commands | `> Run simulation`, `> Open template`, `> Toggle dark mode` |
> | `:` | Files | `:buck`, `:09_buck` |
> | `@` | Components on canvas | `@M1`, `@PWM1`, `@Scope1` |
> | `#` | Add new component | `#R 10k`, `#PI kp=2 ki=100` |
> | `?` | Help / docs lookup | `?theta_from_channel` |
>
> The current "quick add" remains accessible as the `#` mode.

### 6.2 No console / log surface

The runtime emits structured logs (Newton iterations, fallbacks,
linear-solver telemetry). Today these only show up in stdout. A power
user can't introspect during a session.

> **Proposal:** dockable **Console panel** (bottom dock, tabs:
> Output / Problems / Telemetry):
>
> - Output: stdout/stderr stream, color-coded by `LogLevel`.
> - Problems: structured diagnostic list (same as 5.3).
> - Telemetry: Newton iters, dt rejections, fallbacks, factorization
>   cache hits per step — like Chrome DevTools Performance panel.

### 6.3 No live-editing of YAML

For text-first users (PLECS Blockset, ngspice migrants), there's no
way to "see and edit the YAML directly" inside the GUI. Today they have
to open the `.pulsim` file in an external editor and reload.

> **Proposal:** **split-view editor mode** (View → Toggle YAML pane):
>
> - Right half of canvas becomes a Monaco-style editor with the
>   netlist YAML.
> - Edits propagate bidirectionally — moving a component on the
>   schematic updates the YAML position; editing the YAML rebuilds the
>   schematic on save.
> - Catch syntax errors with red squiggles + line numbers in the
>   gutter.

### 6.4 No diff / version history

Pro engineering tools track changes. Today, after editing a circuit
for 30 minutes, there's no "show me what changed since I last saved."

> **Proposal:** **History panel** (right rail tab) with:
>
> - Diff-by-component (added / removed / changed values).
> - Time-travel: scrub a slider and the schematic restores to that
>   state.
> - Named checkpoints (Cmd+Shift+S).
> - Git-aware mode: if the file is in a Git repo, list commits that
>   touched it, click to load any historical version side-by-side.

## Section 7 — Comparative analysis

| Capability | Pulsim today | PSIM | PLECS | LTspice | KiCad 8 | Simulink | Figma |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Schematic editor | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | n/a |
| Component palette w/ search | ✅ | ⚠ | ⚠ | ⚠ | ✅ | ⚠ | ✅ |
| Quick-add palette | ✅ Ctrl+K | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Command palette (general) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Inline diagnostics | ❌ | ⚠ | ⚠ | ❌ | ✅ | ✅ | ✅ |
| Live simulation cursor | ❌ | ⚠ | ✅ | ⚠ | ❌ | ✅ | n/a |
| YAML / netlist split view | ❌ | ❌ | ❌ | ⚠ | ✅ | ❌ | n/a |
| Templates gallery | ✅ | ✅ | ✅ | ⚠ | ✅ | ✅ | ✅ |
| Net highlighting | ❌ | ✅ | ✅ | ✅ | ✅ | n/a | n/a |
| Dirty + stale indicators | ⚠ | ✅ | ✅ | ❌ | ✅ | ⚠ | ✅ |
| Console / logs surface | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| History / version travel | ❌ | ❌ | ❌ | ❌ | ⚠ | ❌ | ✅ |
| Modern color tokens | ⚠ | ❌ | ❌ | ❌ | ✅ | ⚠ | ✅ |
| Modern typography | ⚠ | ❌ | ❌ | ❌ | ✅ | ⚠ | ✅ |
| Dark theme | ✅ | ❌ | ⚠ | ❌ | ✅ | ⚠ | ✅ |

✅ excellent · ⚠ partial · ❌ missing

**Reading the table:** Pulsim is already ahead of every CAE peer on
**dark theme, quick-add palette, modern color tokens** — and behind
*all* of them on **net highlighting, inline diagnostics, console
surface**.

## Section 8 — Proposed roadmap

### Wave P0 — "Fix the regressions" (1 sprint, 1 dev)

| # | Item | Effort |
|---|---|---|
| P0.1 | Status bar reads `pulsim.__version__` (kill the stale 0.5.1) | 0.25d |
| P0.2 | Auto-fit on `_open_project_file` | 0.5d |
| P0.3 | De-duplicate undo/redo toolbar cluster | 0.25d |
| P0.4 | Card-label truncation + tooltip fallback | 0.5d |
| P0.5 | Platform-aware shortcut rendering | 1d |
| P0.6 | Audit `theme_service` tokens — find every remaining hardcoded color | 2d |

**Deliverable:** v0.8.1 release, "polish patch."

### Wave P1 — "Information architecture" (2 sprints, 1–2 devs)

| # | Item | Effort |
|---|---|---|
| P1.1 | Unified titlebar + breadcrumb + view-switcher | 1w |
| P1.2 | **Run Bar** with progress + realtime factor + console flyout | 1w |
| P1.3 | **Solver pill** in status bar | 0.5w |
| P1.4 | **Project tab** in left rail (tree, recent, templates) | 1.5w |
| P1.5 | Color-token system + semantic mapping doc | 1w |
| P1.6 | Typography scale + Inter/Geist adoption | 0.5w |
| P1.7 | Empty-state action cards (replace text-only) | 0.5w |
| P1.8 | Wire-label collision avoidance | 1w |
| P1.9 | Net highlighting on hover/select | 0.5w |
| P1.10 | Inline diagnostics layer (red badges + jump-to-fix) | 1.5w |
| P1.11 | Dirty / stale / unsaved indicator triple | 0.5w |
| P1.12 | Minimap chrome + corner-snap | 0.5w |

**Deliverable:** v0.9.0, "the professional release."

### Wave P2 — "Power-user surfaces" (3+ sprints, 1–3 devs)

| # | Item | Effort |
|---|---|---|
| P2.1 | Generalized command palette (`>`, `:`, `@`, `#`, `?` modes) | 2w |
| P2.2 | Console panel (Output / Problems / Telemetry tabs) | 1.5w |
| P2.3 | Split-view YAML editor (Monaco-style, bidirectional) | 3w |
| P2.4 | History panel + time-travel scrubber | 2.5w |
| P2.5 | Icon set redraw (40+ components on 24 px grid) | 1.5w |
| P2.6 | Live simulation cursor on scope + canvas | 1w |
| P2.7 | Onboarding tour (first-launch overlay) | 1w |

**Deliverable:** v1.0.0, "the brand-defining release."

## Appendix A — Already-shipped UX surface (don't reimplement)

For context, the following UX surfaces are already complete (refer to
archived OpenSpec changes `refactor-visual-ux-overhaul` and
`update-professional-ui-consistency`):

- Card-based component library with hover preview
- Smooth animated zoom, ZoomSlider, ZoomOverlay corner widget
- Animated dock widgets with collapse/expand
- Quick-add palette (`Ctrl+K` — components only)
- Theme service with light/dark/moderndark
- Status bar with segmented sections, coordinate widget,
  simulation-state indicator
- Schematic grid rendering (subtle dots that scale with zoom)
- Drop shadow on selected components, glow on hover
- Wire auto-routing suggestions (Space cycles options)
- Junction dot highlighting, hover effects
- Magnetic snap visual feedback
- Context menus with icons, rounded corners
- Status banners on dialogs
- Modern result tables (alternating rows, styled headers)
- Properties panel section headers with icons
- Saved-views in scope window
- Cursor-driven measurement panel
- VirtuScope dark theme for scope traces
- Grouped signal panel + measurement table polish

## Appendix B — Things to leave alone

These work well today and don't need iteration in waves P0–P2:

- Card-based library categories + per-category color
- Animated docks
- Schematic grid + selection highlights
- Wire rendering quality
- Scope workbench (mature; recent investment)
- Properties-panel parameter editors

---

## Closing thoughts

PulsimGui is one wave away from "looking like a $500/seat commercial
power-electronics tool." The work that's already done covers the
**surface** — what's left is the **structure**: how the user
**reads** the running state of their simulation, how they recover
from errors, how they navigate between schematics, how the tool tells
its own story when they first open it.

P0 fixes the visible regressions in a week.
P1 makes Pulsim *feel* professional.
P2 makes Pulsim *be* professional.

If you only do one section: do **P1.2 (Run Bar) + P1.3 (Solver pill)
+ P1.4 (Project tab) + P1.10 (Inline diagnostics)** as a coherent
release. That's the architecture wave. Everything else is polish on
top.
