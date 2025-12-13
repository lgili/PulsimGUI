# Proposal: Enhance UI and Add New Components

## Summary
Enhance the visual appearance of PulsimGui to be more professional like PLECS, and expand the component library with additional power electronics and control components.

## Motivation
- Current UI lacks some professional features found in PLECS (rulers, better labels, simulation visualization)
- Component library is missing common power electronics components (BJT, thyristors, op-amps, etc.)
- Better visual feedback during simulation would improve user experience

## Scope

### Visual Enhancements
1. **Rulers** - Add measurement rulers along schematic edges (pixels/grid units)
2. **Component Labels** - Show name and value together (e.g., "R1 = 1kΩ")
3. **Wire Junctions** - Larger, more visible junction dots
4. **Simulation Visualization** - Color-coded voltage/current during simulation
5. **Context Menus** - Better organized with submenus and icons

### New Components

#### Power Semiconductors
- BJT_NPN, BJT_PNP (Bipolar transistors)
- THYRISTOR (SCR)
- TRIAC
- ZENER_DIODE
- LED

#### Analog Components
- OP_AMP (Operational amplifier)
- COMPARATOR

#### Protection & Switching
- RELAY
- FUSE
- CIRCUIT_BREAKER

#### Control Blocks
- LOOKUP_TABLE (1D interpolation)
- TRANSFER_FUNCTION (s-domain)
- DELAY_BLOCK (time delay)
- SAMPLE_HOLD
- STATE_MACHINE
- INTEGRATOR
- DIFFERENTIATOR
- LIMITER
- RATE_LIMITER
- HYSTERESIS

#### Measurement
- VOLTAGE_PROBE
- CURRENT_PROBE
- POWER_PROBE

#### Magnetic
- SATURABLE_INDUCTOR
- COUPLED_INDUCTOR

#### Passive Networks
- SNUBBER_RC (pre-configured RC snubber)

## Out of Scope
- Grid style changes (keeping dots as requested)
- 3D visualization
- Animation during editing

## Dependencies
- Existing schematic-editor spec
- Existing component-library spec

## Risks
- Large number of new components may require extensive testing
- Simulation visualization may impact performance

## Success Criteria
- All visual enhancements implemented and working
- At least 15 new components added with proper symbols
- No regression in existing functionality
