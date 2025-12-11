# Design: Enhance UI and Add New Components

## Architecture Overview

### Visual Enhancements

#### 1. Rulers Widget
- Create `RulerWidget` class that extends `QWidget`
- Position along top and left edges of schematic view
- Synchronize with view scroll/zoom via signals
- Support both pixel and grid unit display modes
- Theme-aware colors

```
+--[Ruler H]------------------+
|R|                           |
|u|     Schematic View        |
|l|                           |
|e|                           |
|r|                           |
| |                           |
|V|                           |
+-----------------------------+
```

#### 2. Enhanced Component Labels
- Modify `ComponentItem.paint()` to render combined label
- Format: "{name} = {formatted_value}" for components with single main parameter
- Use `format_si_value()` utility for proper SI prefix display
- Semi-transparent background for readability
- Configurable via settings (show/hide value)

#### 3. Wire Junction Enhancement
- Increase junction dot radius from 4.5px to 6px
- Add subtle shadow/glow effect
- Filled circle instead of outline
- Color matches wire color

#### 4. Simulation Visualization
- Add `SimulationOverlay` class for voltage/current display
- Color gradient: blue (negative) -> white (zero) -> red (positive)
- Current flow arrows on wires (optional, toggleable)
- Power dissipation heat map on components
- Update frequency: 10Hz during simulation

#### 5. Context Menu Reorganization
- Group actions into submenus:
  - Edit (Cut, Copy, Paste, Delete, Duplicate)
  - Transform (Rotate CW, Rotate CCW, Flip H, Flip V)
  - Align (Left, Right, Top, Bottom, Center H, Center V)
  - Simulation (Run, Probe, Show Values)
- Add icons to all menu items

### New Components Architecture

#### Component Registration Pattern
Each new component requires:
1. Entry in `ComponentType` enum
2. Default pins in `DEFAULT_PINS` dict
3. Default parameters in `DEFAULT_PARAMETERS` dict
4. Symbol drawing in `ComponentItem._draw_symbol()`
5. Library category assignment in `library_panel.py`

#### New Categories
- **Semiconductors**: BJT_NPN, BJT_PNP, THYRISTOR, TRIAC, ZENER_DIODE, LED
- **Analog**: OP_AMP, COMPARATOR
- **Protection**: RELAY, FUSE, CIRCUIT_BREAKER
- **Control**: LOOKUP_TABLE, TRANSFER_FUNCTION, DELAY_BLOCK, SAMPLE_HOLD, STATE_MACHINE, INTEGRATOR, DIFFERENTIATOR, LIMITER, RATE_LIMITER, HYSTERESIS
- **Measurement**: VOLTAGE_PROBE, CURRENT_PROBE, POWER_PROBE
- **Magnetic**: SATURABLE_INDUCTOR, COUPLED_INDUCTOR
- **Networks**: SNUBBER_RC

#### Component Symbol Design Guidelines
- Size: 60x40 px standard, up to 80x60 for complex
- Pin positions: multiples of grid (20px)
- Colors: use theme colors, gradients for modern look
- Style: similar to existing components (PLECS-inspired)

### Data Model Changes

#### New ComponentType Entries
```python
class ComponentType(Enum):
    # Existing...
    BJT_NPN = auto()
    BJT_PNP = auto()
    THYRISTOR = auto()
    TRIAC = auto()
    ZENER_DIODE = auto()
    LED = auto()
    OP_AMP = auto()
    COMPARATOR = auto()
    RELAY = auto()
    FUSE = auto()
    CIRCUIT_BREAKER = auto()
    LOOKUP_TABLE = auto()
    TRANSFER_FUNCTION = auto()
    DELAY_BLOCK = auto()
    SAMPLE_HOLD = auto()
    STATE_MACHINE = auto()
    INTEGRATOR = auto()
    DIFFERENTIATOR = auto()
    LIMITER = auto()
    RATE_LIMITER = auto()
    HYSTERESIS = auto()
    VOLTAGE_PROBE = auto()
    CURRENT_PROBE = auto()
    POWER_PROBE = auto()
    SATURABLE_INDUCTOR = auto()
    COUPLED_INDUCTOR = auto()
    SNUBBER_RC = auto()
```

### Performance Considerations

1. **Simulation Overlay**: Use dirty-rect updating, not full redraw
2. **Rulers**: Cache tick positions, only recalculate on zoom change
3. **Component Labels**: Pre-render formatted text, cache results
4. **New Components**: Lazy-load symbols, use QPainterPath caching

### Theme Integration

All new visual elements must:
- Use `ThemeService` for colors
- Support light/dark mode
- Respond to theme change signals
- Follow existing color naming conventions

## Trade-offs

| Decision | Alternative | Rationale |
|----------|-------------|-----------|
| Rulers as separate widget | Draw in scene | Better performance, independent scrolling |
| 10Hz overlay update | Real-time | Balance between responsiveness and CPU |
| Filled junction dots | Outlined | Better visibility at all zoom levels |
| Submenus in context | Flat menu | Cleaner organization, less clutter |

## Migration

No migration needed - all changes are additive.
