"""The canonical SVG icon set for PulsimGUI.

One family, one grid, one stroke. Every glyph is authored on a 24x24
viewBox with ``stroke-width: 2``, round caps and round joins — the
Lucide drawing convention — so the whole UI reads as a single icon
family. Generic glyphs are Lucide-faithful (ISC license); the
EDA-domain glyphs (probes, wire, net label, FFT, engine, auto-layout,
oscilloscope cursors) are drawn in-house on the same grid so they are
indistinguishable in weight and style from the stock set.

Why this exists (redesign slice 2). Icon rendering previously went
through QtAwesome and mixed TWO icon fonts — Phosphor (``ph.*``) and
Material Design (``mdi6.*``) — with different stroke weights and
metaphors side by side in the same toolbar. Worse, without qtawesome
installed the whole app silently rendered EMPTY icons, and unknown
names silently fell back to a filled circle. This dict is now the
primary source (see ``IconService`` in ``__init__.py``): it is
self-contained, versioned with the app, recolorable at render time,
and renders crisply at any DPI through QSvgRenderer.

Authoring rules — keep the set coherent:

* 24x24 viewBox, ``stroke-width="2"``, round caps/joins (the template
  in ``svg_for`` applies these; bodies carry ONLY geometry).
* Keep 1.5px of padding to the viewBox edge (draw inside 2..22).
* Filled accents use ``fill="currentColor"`` — the renderer recolors
  both stroke and fill.
* Metaphors must survive 16px: no detail thinner than one grid unit.

Each entry is the INNER body of the SVG (one or more elements);
:func:`svg_for` wraps it in the shared template.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Glyph bodies — geometry only. Grouped by domain.
# --------------------------------------------------------------------------

ICONS: dict[str, str] = {
    # ── File ──────────────────────────────────────────────────────────
    "file": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/>',
    "file-plus": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>',
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "folder-open": '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',

    # ── Edit ──────────────────────────────────────────────────────────
    "undo": '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
    "redo": '<path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3l3 2.7"/>',
    "cut": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>',
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "copy-filled": '<rect x="9" y="9" width="13" height="13" rx="2" fill="currentColor"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "paste": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
    "clipboard": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
    "trash": '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
    "delete": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "edit": '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>',
    "rename": '<path d="M4 20h16"/><path d="m6 16 6-12 6 12"/><path d="M8 12h8"/>',

    # ── Zoom / view ───────────────────────────────────────────────────
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "zoom": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "zoom-in": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>',
    "zoom-out": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/>',
    "maximize": '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "minimize": '<path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/>',
    "fit-view": '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/><rect x="9" y="9" width="6" height="6" rx="1"/>',

    # ── Transport / simulation ────────────────────────────────────────
    "play": '<polygon points="6 3 20 12 6 21 6 3" fill="currentColor" stroke="none"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" stroke="none"/>',
    "square": '<rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" stroke="none"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/>',
    "step-forward": '<line x1="19" y1="5" x2="19" y2="19"/><polygon points="5 5 15 12 5 19 5 5"/>',
    "step-forward-filled": '<line x1="19" y1="5" x2="19" y2="19"/><polygon points="5 5 15 12 5 19 5 5" fill="currentColor" stroke="none"/>',
    "engine": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3"/><path d="M12 18.5v3"/><path d="M2.5 12h3"/><path d="M18.5 12h3"/><path d="m5.3 5.3 2.1 2.1"/><path d="m16.6 16.6 2.1 2.1"/><path d="m18.7 5.3-2.1 2.1"/><path d="m7.4 16.6-2.1 2.1"/>',
    "sim-ready": '<circle cx="12" cy="12" r="8"/>',
    "sim-running": '<path d="M21 12a9 9 0 1 1-6.2-8.56"/>',
    "sim-done": '<polyline points="20 6 9 17 4 12"/>',
    "sim-error": '<path d="M12 3 2.8 19a1.2 1.2 0 0 0 1 1.8h16.4a1.2 1.2 0 0 0 1-1.8L12 3z"/><line x1="12" y1="9" x2="12" y2="14"/><circle cx="12" cy="17.2" r="0.5" fill="currentColor"/>',

    # ── Navigation / chrome ───────────────────────────────────────────
    "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
    "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
    "chevron-up": '<polyline points="6 15 12 9 18 15"/>',
    "chevron-left": '<polyline points="15 18 9 12 15 6"/>',
    "menu": '<line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>',
    "sidebar": '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>',
    "sidebar-filled": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M4 4h5v16H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" fill="currentColor" stroke="none"/>',
    "panel-left": '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/><path d="M4 4h5v16H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" fill="currentColor" stroke="none"/>',
    "panel-right": '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="15" y1="3" x2="15" y2="21"/><path d="M15 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5V4z" fill="currentColor" stroke="none"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "minus": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "external-link": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',

    # ── Status / feedback ─────────────────────────────────────────────
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><circle cx="12" cy="8" r="0.5" fill="currentColor"/>',
    "about": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><circle cx="12" cy="8" r="0.5" fill="currentColor"/>',
    "warning": '<path d="M12 3 2.8 19a1.2 1.2 0 0 0 1 1.8h16.4a1.2 1.2 0 0 0 1-1.8L12 3z"/><line x1="12" y1="9" x2="12" y2="14"/><circle cx="12" cy="17.2" r="0.5" fill="currentColor"/>',
    "error": '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r="0.5" fill="currentColor"/>',
    "help-circle": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r="0.5" fill="currentColor"/>',
    "modified": '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
    "saved": '<circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "unlock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.7-1.5"/>',
    "eye": '<path d="M1.5 12C3.8 7.6 7.6 5 12 5s8.2 2.6 10.5 7c-2.3 4.4-6.1 7-10.5 7s-8.2-2.6-10.5-7Z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="M10.6 5.2A10 10 0 0 1 12 5c4.4 0 8.2 2.6 10.5 7a13.4 13.4 0 0 1-3.2 4.2"/><path d="M6.6 6.6A13.3 13.3 0 0 0 1.5 12c2.3 4.4 6.1 7 10.5 7a10 10 0 0 0 5.4-1.6"/><line x1="3" y1="3" x2="21" y2="21"/>',

    # ── Settings / tools ──────────────────────────────────────────────
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3"/><path d="M12 18.5v3"/><path d="M2.5 12h3"/><path d="M18.5 12h3"/><path d="m5.3 5.3 2.1 2.1"/><path d="m16.6 16.6 2.1 2.1"/><path d="m18.7 5.3-2.1 2.1"/><path d="m7.4 16.6-2.1 2.1"/>',
    "sliders": '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    "sliders-horizontal": '<line x1="21" y1="4" x2="14" y2="4"/><line x1="10" y1="4" x2="3" y2="4"/><line x1="21" y1="12" x2="12" y2="12"/><line x1="8" y1="12" x2="3" y2="12"/><line x1="21" y1="20" x2="16" y2="20"/><line x1="12" y1="20" x2="3" y2="20"/><line x1="14" y1="1" x2="14" y2="7"/><line x1="8" y1="9" x2="8" y2="15"/><line x1="16" y1="17" x2="16" y2="23"/>',
    "style-tune": '<line x1="21" y1="6" x2="10" y2="6"/><line x1="6" y1="6" x2="3" y2="6"/><line x1="21" y1="12" x2="16" y2="12"/><line x1="12" y1="12" x2="3" y2="12"/><line x1="21" y1="18" x2="10" y2="18"/><line x1="6" y1="18" x2="3" y2="18"/><circle cx="8" cy="6" r="2"/><circle cx="14" cy="12" r="2"/><circle cx="8" cy="18" r="2"/>',
    "tool": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "keyboard": '<rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="6" cy="8" r="0.5" fill="currentColor"/><circle cx="10" cy="8" r="0.5" fill="currentColor"/><circle cx="14" cy="8" r="0.5" fill="currentColor"/><circle cx="18" cy="8" r="0.5" fill="currentColor"/><circle cx="8" cy="12" r="0.5" fill="currentColor"/><circle cx="12" cy="12" r="0.5" fill="currentColor"/><circle cx="16" cy="12" r="0.5" fill="currentColor"/><path d="M7 16h10"/>',
    "command": '<path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3z"/>',
    "refresh": '<path d="M21 2v6h-6"/><path d="M21 13a9 9 0 1 1-3-7.7L21 8"/>',

    # ── Schematic tools ───────────────────────────────────────────────
    "cursor": '<path d="M4 3 11.07 19.97 13.58 12.58 20.97 10.07 4 3z"/>',
    "mouse-pointer": '<path d="M4 3 11.07 19.97 13.58 12.58 20.97 10.07 4 3z"/><path d="m14 14 6 6"/>',
    "selection": '<path d="M5 3a2 2 0 0 0-2 2"/><path d="M19 3a2 2 0 0 1 2 2"/><path d="M21 19a2 2 0 0 1-2 2"/><path d="M5 21a2 2 0 0 1-2-2"/><line x1="9" y1="3" x2="11" y2="3"/><line x1="13" y1="3" x2="15" y2="3"/><line x1="9" y1="21" x2="11" y2="21"/><line x1="13" y1="21" x2="15" y2="21"/><line x1="3" y1="9" x2="3" y2="11"/><line x1="3" y1="13" x2="3" y2="15"/><line x1="21" y1="9" x2="21" y2="11"/><line x1="21" y1="13" x2="21" y2="15"/>',
    "hand": '<path d="M8 11V5.5a1.5 1.5 0 0 1 3 0V10"/><path d="M11 10V4a1.5 1.5 0 0 1 3 0v6"/><path d="M14 10V5a1.5 1.5 0 0 1 3 0v9a6 6 0 0 1-6 6h-.6a6 6 0 0 1-5-2.7L4 14.5A1.7 1.7 0 0 1 6.7 12.6L8 14"/>',
    "wire": '<path d="M3 20v-7h8V6h10"/><circle cx="11" cy="13" r="1.6" fill="currentColor" stroke="none"/>',
    "net-label": '<path d="M3.5 9.5 9 4h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5.5-5.5a1.4 1.4 0 0 1 0-2z" transform="rotate(45 12 12)"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>',
    "probe-voltage": '<circle cx="10" cy="9" r="6"/><path d="M8 6.5 10 11.5 12 6.5"/><path d="m14.5 13.5 5.5 5.5"/>',
    "probe-current": '<circle cx="10" cy="9" r="6"/><path d="M8 11.5 10 6.5 12 11.5"/><path d="M8.7 10 h2.6"/><path d="m14.5 13.5 5.5 5.5"/>',
    "ground": '<path d="M12 3v8"/><path d="M5 11h14"/><path d="M7.5 15h9"/><path d="M10 19h4"/>',
    "rotate-cw": '<path d="M21 2v6h-6"/><path d="M21 13a9 9 0 1 1-3-7.7L21 8"/>',
    "rotate-ccw": '<path d="M3 2v6h6"/><path d="M3 13a9 9 0 1 0 3-7.7L3 8"/>',
    "flip-horizontal": '<path d="M8 3H5a2 2 0 0 0-2 2v14c0 1.1.9 2 2 2h3"/><path d="M16 3h3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-3"/><path d="M12 20v2"/><path d="M12 14v2"/><path d="M12 8v2"/><path d="M12 2v2"/>',
    "flip-vertical": '<path d="M21 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v3"/><path d="M21 16v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3"/><path d="M4 12H2"/><path d="M10 12H8"/><path d="M16 12h-2"/><path d="M22 12h-2"/>',
    "move": '<polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/><polyline points="15 19 12 22 9 19"/><polyline points="19 9 22 12 19 15"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/>',
    "grid": '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>',
    "grid-filled": '<rect x="3" y="3" width="8" height="8" rx="1" fill="currentColor" stroke="none"/><rect x="13" y="3" width="8" height="8" rx="1" fill="currentColor" stroke="none"/><rect x="3" y="13" width="8" height="8" rx="1" fill="currentColor" stroke="none"/><rect x="13" y="13" width="8" height="8" rx="1" fill="currentColor" stroke="none"/>',
    "auto-layout": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="m14 17.5 3.5 3.5 3.5-3.5"/><path d="M17.5 21v-7"/>',
    "crosshairs": '<circle cx="12" cy="12" r="8"/><path d="M12 2v4"/><path d="M12 18v4"/><path d="M2 12h4"/><path d="M18 12h4"/>',
    "crosshair-simple": '<path d="M12 3v18"/><path d="M3 12h18"/>',

    # ── Scope / analysis ──────────────────────────────────────────────
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "wave": '<path d="M2 12c1.7-4.5 3.6-6.7 5.5-6.7 3.3 0 5.7 13.4 9 13.4 1.9 0 3.8-2.2 5.5-6.7"/>',
    "brand-wave": '<path d="M2 12c1.7-4.5 3.6-6.7 5.5-6.7 3.3 0 5.7 13.4 9 13.4 1.9 0 3.8-2.2 5.5-6.7"/>',
    "waveform": '<path d="M2 12h3l2.5-7 4 14 3-10 1.5 3H22"/>',
    "fft-chart": '<path d="M3 21V3"/><path d="M3 21h18"/><path d="M7 21v-11"/><path d="M11 21v-15"/><path d="M15 21v-8"/><path d="M19 21v-5"/>',
    "math": '<path d="M6 5h12"/><path d="M12 5c-3 0-3 4-3 7s0 7-3 7"/><path d="M7 12h7"/>',
    "math-function": '<path d="M6 5h12"/><path d="M12 5c-3 0-3 4-3 7s0 7-3 7"/><path d="M7 12h7"/><path d="m15 15 5 5"/><path d="m20 15-5 5"/>',
    "measurements": '<path d="M3 15.5 15.5 3l5.5 5.5L8.5 21 3 15.5z"/><path d="m7 12 2 2"/><path d="m10 9 2 2"/><path d="m13 6 2 2"/>',
    "measurements-filled": '<path d="M3 15.5 15.5 3l5.5 5.5L8.5 21 3 15.5z" fill="currentColor"/><path d="m7 12 2 2" stroke="#00000055"/><path d="m10 9 2 2" stroke="#00000055"/><path d="m13 6 2 2" stroke="#00000055"/>',
    "table": '<rect x="3" y="4" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="10" y1="10" x2="10" y2="20"/>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    "code": '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "terminal": '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',

    # ── Library categories ────────────────────────────────────────────
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    "box": '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "heart": '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
    "thermometer": '<path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/>',
    "layout-template": '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/>',
    "square-function": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 17c2 0 2.8-1 2.8-2.8V10c0-2 1-3.3 3.2-3"/><path d="M9 11.2h5"/>',
    "toggle-left": '<rect x="1" y="5" width="22" height="14" rx="7"/><circle cx="8" cy="12" r="3"/>',
    "git-branch": '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
}


# --------------------------------------------------------------------------
# Rendering template
# --------------------------------------------------------------------------

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
    'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)


def svg_for(name: str, color: str = "#9aa0a8", size: int = 24) -> str | None:
    """Return the full recolored SVG document for ``name``.

    ``None`` when the name isn't in the set — callers decide the
    fallback policy (``IconService`` logs and substitutes
    ``help-circle``). ``fill="currentColor"`` accents inside bodies
    are recolored along with the stroke.
    """
    body = ICONS.get(name)
    if body is None:
        return None
    body = body.replace('fill="currentColor"', f'fill="{color}"')
    return _SVG_TEMPLATE.format(size=size, color=color, body=body)


def get_icon_svg(name: str, color: str = "#000000", size: int = 24) -> str:
    """Legacy-compatible accessor — always returns a document (falls
    back to ``help-circle`` for unknown names)."""
    return svg_for(name, color, size) or svg_for("help-circle", color, size)  # type: ignore[return-value]


def get_available_icons() -> list[str]:
    """All icon names in the canonical set."""
    return list(ICONS.keys())
