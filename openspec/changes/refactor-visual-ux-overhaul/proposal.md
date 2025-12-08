## Why

PulsimGui currently has a functional but basic visual appearance that lacks the polish and professional feel of industry-standard tools like PLECS and Simulink. The current UI has usability issues with component placement, wire routing, and overall visual hierarchy that make it feel like an early prototype rather than a production-ready tool.

## What Changes

### Visual Design Overhaul
- **Modern toolbar design**: Icon-based toolbar with subtle hover effects, proper spacing, and visual groupings (similar to VS Code/PLECS)
- **Refined component library panel**: Card-based component previews with live symbol thumbnails, better categorization, and smooth animations
- **Professional schematic canvas**: Improved grid styling, shadows on selected components, smooth wire rendering with rounded corners
- **Polished dock panels**: Refined headers with subtle gradients, better resize handles, and consistent padding
- **Modern dialogs**: Consistent dialog styling with proper spacing, button alignment, and visual hierarchy
- **Enhanced status bar**: Segmented status bar with visual indicators for simulation state

### Usability Improvements
- **Quick-add palette (Cmd/Ctrl+K)**: Command palette for fast component insertion without leaving keyboard
- **Improved component drop behavior**: Visual feedback during drag, magnetic snap preview, ghost placement
- **Better wire routing**: Auto-routing suggestions, visual feedback for valid connections, junction highlighting
- **Selection improvements**: Multi-select visual feedback, group selection box with count indicator
- **Zoom improvements**: Smooth animated zoom, zoom slider in corner, minimap for large schematics
- **Keyboard navigation**: Full keyboard control for placing and editing components

### Bug Fixes
- Fix component placement position offset during drag-drop
- Fix wire connection point detection accuracy
- Fix grid alignment issues at different zoom levels
- Fix panel resize persistence across sessions
- Fix theme switching artifacts

## Impact
- Affected specs: application-shell, schematic-editor
- Affected code:
  - `src/pulsimgui/services/theme_service.py` - Enhanced theming with more refined styles
  - `src/pulsimgui/views/main_window.py` - Toolbar and panel refinements
  - `src/pulsimgui/views/library/library_panel.py` - Card-based component display
  - `src/pulsimgui/views/schematic/` - All schematic rendering improvements
  - `src/pulsimgui/views/dialogs/` - Dialog styling consistency
  - `src/pulsimgui/resources/` - New icons and assets
