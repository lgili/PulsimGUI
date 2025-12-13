# Tasks: Enhance UI and Add New Components

## Phase 1: Visual Enhancements

### Rulers
- [ ] Create `RulerWidget` class in `views/schematic/ruler.py`
- [ ] Implement horizontal ruler with tick marks and labels
- [ ] Implement vertical ruler with tick marks and labels
- [ ] Connect rulers to schematic view scroll/zoom signals
- [ ] Add ruler toggle in View menu
- [ ] Theme support for ruler colors
- [ ] Unit tests for ruler coordinate calculations

### Component Labels
- [ ] Add `show_value_labels` setting to preferences
- [ ] Modify `ComponentItem._update_labels()` to include value
- [ ] Implement `format_component_value()` helper function
- [ ] Add semi-transparent background to labels
- [ ] Handle multi-parameter components (show primary only)
- [ ] Test label positioning with rotation/mirror

### Wire Junctions
- [ ] Increase junction radius to 6px in `WireItem`
- [ ] Add filled circle rendering for junctions
- [ ] Add subtle shadow effect to junctions
- [ ] Ensure junction color follows wire color
- [ ] Test junction visibility at various zoom levels

### Simulation Visualization
- [ ] Create `SimulationOverlay` class
- [ ] Implement voltage color gradient (blue-white-red)
- [ ] Add node voltage display during simulation
- [ ] Add current flow arrows (optional)
- [ ] Add power dissipation heat indicator
- [ ] Add toggle in Simulation menu
- [ ] Optimize with 10Hz update rate
- [ ] Test performance with 100+ components

### Context Menu Enhancement
- [ ] Reorganize context menu with submenus
- [ ] Add Edit submenu (Cut, Copy, Paste, Delete, Duplicate)
- [ ] Add Transform submenu (Rotate, Flip)
- [ ] Add Align submenu (when multiple selected)
- [ ] Add icons to all menu items
- [ ] Test all menu actions work correctly

## Phase 2: Power Semiconductor Components

### BJT Transistors
- [ ] Add BJT_NPN to ComponentType enum
- [ ] Add BJT_PNP to ComponentType enum
- [ ] Define pins: C (collector), B (base), E (emitter)
- [ ] Define parameters: beta, vbe_sat, vce_sat, is_
- [ ] Draw NPN symbol (arrow out from emitter)
- [ ] Draw PNP symbol (arrow into emitter)
- [ ] Add to Semiconductors category

### Thyristors
- [ ] Add THYRISTOR (SCR) to ComponentType enum
- [ ] Add TRIAC to ComponentType enum
- [ ] Define SCR pins: A (anode), K (cathode), G (gate)
- [ ] Define TRIAC pins: MT1, MT2, G (gate)
- [ ] Define parameters: vgt, igt, holding_current
- [ ] Draw SCR symbol
- [ ] Draw TRIAC symbol
- [ ] Add to Semiconductors category

### Special Diodes
- [ ] Add ZENER_DIODE to ComponentType enum
- [ ] Add LED to ComponentType enum
- [ ] Define Zener parameters: vz, iz_test, zz
- [ ] Define LED parameters: vf, color, wavelength
- [ ] Draw Zener symbol (bent cathode)
- [ ] Draw LED symbol (diode with arrows)
- [ ] Add to Semiconductors category

## Phase 3: Analog Components

### Operational Amplifier
- [ ] Add OP_AMP to ComponentType enum
- [ ] Define pins: IN+ (non-inverting), IN- (inverting), OUT, V+, V-
- [ ] Define parameters: gain, gbw, slew_rate, vos
- [ ] Draw op-amp triangle symbol
- [ ] Support rail-to-rail option
- [ ] Add to Analog category

### Comparator
- [ ] Add COMPARATOR to ComponentType enum
- [ ] Define pins: IN+, IN-, OUT, V+, V-
- [ ] Define parameters: vos, hysteresis, response_time
- [ ] Draw comparator symbol (similar to op-amp with output indicator)
- [ ] Add to Analog category

## Phase 4: Protection Components

### Relay
- [ ] Add RELAY to ComponentType enum
- [ ] Define coil pins: COIL+, COIL-
- [ ] Define contact pins: COM, NO, NC
- [ ] Define parameters: coil_voltage, coil_resistance, contact_rating
- [ ] Draw relay symbol (coil + switch)
- [ ] Add to Protection category

### Fuse
- [ ] Add FUSE to ComponentType enum
- [ ] Define pins: 1, 2
- [ ] Define parameters: rating, blow_time_curve
- [ ] Draw fuse symbol (rectangle with wire)
- [ ] Add to Protection category

### Circuit Breaker
- [ ] Add CIRCUIT_BREAKER to ComponentType enum
- [ ] Define pins: LINE, LOAD
- [ ] Define parameters: trip_current, trip_time
- [ ] Draw breaker symbol
- [ ] Add to Protection category

## Phase 5: Control Blocks

### Math/Signal Blocks
- [ ] Add INTEGRATOR to ComponentType enum
- [ ] Add DIFFERENTIATOR to ComponentType enum
- [ ] Add LIMITER to ComponentType enum
- [ ] Add RATE_LIMITER to ComponentType enum
- [ ] Add HYSTERESIS to ComponentType enum
- [ ] Define parameters for each block
- [ ] Draw block symbols with function labels
- [ ] Add to Control category

### Advanced Control
- [ ] Add LOOKUP_TABLE to ComponentType enum
- [ ] Add TRANSFER_FUNCTION to ComponentType enum
- [ ] Add DELAY_BLOCK to ComponentType enum
- [ ] Add SAMPLE_HOLD to ComponentType enum
- [ ] Add STATE_MACHINE to ComponentType enum
- [ ] Implement table editor for lookup table
- [ ] Implement transfer function editor (numerator/denominator)
- [ ] Draw symbols for each block
- [ ] Add to Control category

## Phase 6: Measurement & Magnetic

### Probes
- [ ] Add VOLTAGE_PROBE to ComponentType enum
- [ ] Add CURRENT_PROBE to ComponentType enum
- [ ] Add POWER_PROBE to ComponentType enum
- [ ] Define probe parameters and display options
- [ ] Draw probe symbols (voltmeter, ammeter style)
- [ ] Connect probes to waveform viewer
- [ ] Add to Measurement category

### Magnetic Components
- [ ] Add SATURABLE_INDUCTOR to ComponentType enum
- [ ] Add COUPLED_INDUCTOR to ComponentType enum
- [ ] Define saturation curve parameters
- [ ] Define coupling coefficient for coupled inductor
- [ ] Draw symbols with saturation indicator
- [ ] Add to Magnetic category

### Pre-configured Networks
- [ ] Add SNUBBER_RC to ComponentType enum
- [ ] Define parameters: resistance, capacitance
- [ ] Draw snubber symbol (R and C combined)
- [ ] Add to Networks category

## Phase 7: Integration & Testing

### Library Panel Updates
- [ ] Add new categories: Analog, Protection, Magnetic, Networks
- [ ] Update category colors and icons
- [ ] Verify drag-and-drop for all new components
- [ ] Test search functionality with new components

### Documentation
- [ ] Update component reference documentation
- [ ] Add parameter descriptions for new components
- [ ] Screenshot new component symbols

### Testing
- [ ] Unit tests for all new component types
- [ ] Integration tests for component placement
- [ ] Visual regression tests for new symbols
- [ ] Performance testing with many new components
- [ ] Test save/load with new component types
