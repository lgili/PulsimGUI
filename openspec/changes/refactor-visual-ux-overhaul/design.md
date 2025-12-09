## Context

PulsimGui aims to be a professional-grade circuit simulation tool comparable to PLECS and Simulink. The current visual design is functional but lacks the polish expected of such tools. Users working with circuit simulation tools spend many hours in the interface, so visual quality and usability directly impact productivity and user satisfaction.

Key stakeholders:
- Power electronics engineers who use PLECS/Simulink daily
- Students learning circuit simulation
- Open-source community contributors

## Goals / Non-Goals

### Goals
- Achieve visual parity with PLECS and Simulink in terms of professional appearance
- Improve discoverability of features through better visual hierarchy
- Reduce friction in common workflows (component placement, wire routing)
- Maintain 60 FPS performance even with visual enhancements
- Support both light and dark themes with consistent quality

### Non-Goals
- Complete UI redesign (preserving existing layout and workflow)
- Adding new functional features (focus on polish, not features)
- Custom icon design (will use existing high-quality icon sets)
- Platform-specific native styling (consistent cross-platform look)

## Decisions

### Decision: Use Lucide Icons for consistency
- **What**: Replace text-based toolbar with Lucide icon set
- **Why**: Lucide is open-source (MIT), has 1000+ icons, consistent style, available in SVG
- **Alternatives considered**:
  - Feather Icons: Fewer icons available
  - Material Icons: Too "Google" looking, not ideal for engineering tools
  - Custom icons: Time-consuming, inconsistent quality

### Decision: CSS-based animations over QPropertyAnimation
- **What**: Use CSS transitions for most UI animations
- **Why**: Simpler to maintain, consistent with Qt stylesheet approach, good performance
- **When to use QPropertyAnimation**: Complex sequences, graphics scene animations
- **Alternatives considered**:
  - QML: Would require significant architecture change
  - Pure QPropertyAnimation: More code, harder to maintain

### Decision: Subtle visual feedback over prominent effects
- **What**: Use subtle glows, shadows, and color shifts rather than heavy borders or animations
- **Why**: Professional tools feel "quiet" - users should focus on their work, not the UI
- **Reference**: VS Code, PLECS, modern CAD tools
- **Alternatives considered**:
  - Prominent selection borders: Too distracting
  - No visual feedback: Poor usability

### Decision: Keep existing dock layout system
- **What**: Enhance visual styling without changing dock mechanics
- **Why**: Users are familiar with Qt dock behavior, changing would confuse existing users
- **Alternatives considered**:
  - Custom panel system: High development cost
  - Tab-based interface: Doesn't fit multi-panel workflow

### Decision: Command palette inspired by VS Code
- **What**: Implement Cmd/Ctrl+K command palette with fuzzy search
- **Why**: Proven UX pattern, allows keyboard-centric workflow, scales with feature count
- **Alternatives considered**:
  - Search dialog: Less discoverable
  - Context menus only: Requires mouse, slow

## Risks / Trade-offs

### Risk: Performance degradation from visual effects
- **Mitigation**: All effects use GPU-accelerated CSS where possible
- **Mitigation**: Disable heavy effects (shadows, blur) at low zoom levels
- **Mitigation**: Benchmark with 500+ component schematics

### Risk: Theme inconsistency across platforms
- **Mitigation**: Test on macOS, Windows, Linux
- **Mitigation**: Use only cross-platform CSS properties
- **Mitigation**: Avoid platform-specific font assumptions

### Risk: Scope creep into feature work
- **Mitigation**: Strictly limit to visual/UX improvements
- **Mitigation**: Any new features require separate proposal
- **Mitigation**: Track feature requests for future proposals

## Migration Plan

### Phase 1: Foundation (Low risk)
1. Add icon assets to resources
2. Update theme color palettes
3. Add animation utilities

### Phase 2: Toolbar & Status Bar
1. Replace toolbar buttons with icons
2. Enhance status bar design
3. Test all toolbar functionality

### Phase 3: Canvas Polish
1. Update grid rendering
2. Add selection effects
3. Improve wire visuals

### Phase 4: Panels & Dialogs
1. Enhance dock panel headers
2. Standardize dialog layouts
3. Add command palette

### Phase 5: Polish & Testing
1. Fix any visual glitches
2. Performance optimization
3. Cross-platform testing

### Rollback
- Each phase can be reverted independently
- Feature flags for major changes (command palette)
- No database/schema changes required

## Open Questions

1. **Icon sizing**: Should we support multiple icon sizes (16/20/24) or pick one?
   - Leaning toward 20px as primary with 24px optional

2. **Minimap**: Is minimap essential or can it be Phase 2?
   - Likely Phase 2, depends on user feedback on large schematic navigation

3. **Animation duration**: What's the right balance of snappy vs smooth?
   - Propose 150ms for most transitions, 200ms for panel collapse

4. **Accessibility**: What's our accessibility target?
   - Minimum WCAG AA contrast ratios
   - Keyboard navigation for all primary actions
