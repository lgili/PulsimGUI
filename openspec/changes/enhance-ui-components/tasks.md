# Tasks: Enhance UI and Add New Components

## Phase 1: Visual Enhancements

### Rulers
- [x] Create `RulerWidget` class in `views/schematic/ruler.py`
- [x] Implement horizontal ruler with tick marks and labels
- [x] Implement vertical ruler with tick marks and labels
- [x] Connect rulers to schematic view scroll/zoom signals
- [x] Add ruler toggle in View menu
- [x] Theme support for ruler colors
- [ ] Unit tests for ruler coordinate calculations

### Component Labels
- [x] Add `show_value_labels` setting to preferences
- [x] Modify `ComponentItem._update_labels()` to include value
- [x] Implement `format_component_value()` helper function
- [x] Add semi-transparent background to labels
- [x] Handle multi-parameter components (show primary only)
- [x] Add View menu toggle for value labels (shortcut V)
- [ ] Test label positioning with rotation/mirror

### Wire Junctions
- [x] Increase junction radius to 6px in `WireItem`
- [x] Add filled circle rendering for junctions
- [x] Add subtle shadow effect to junctions
- [x] Ensure junction color follows wire color
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
- [x] Reorganize context menu with submenus
- [x] Add Edit submenu (Cut, Copy, Paste, Delete, Duplicate)
- [x] Add Transform submenu (Rotate, Flip)
- [x] Implement Copy/Paste with full component configuration (Ctrl+C/V/X)
- [ ] Add Align submenu (when multiple selected)
- [x] Add icons to all menu items
- [x] Test all menu actions work correctly

## Phase 2: Power Semiconductor Components

### BJT Transistors
- [x] Add BJT_NPN to ComponentType enum
- [x] Add BJT_PNP to ComponentType enum
- [x] Define pins: C (collector), B (base), E (emitter)
- [x] Define parameters: beta, vbe_sat, vce_sat, is_
- [x] Draw NPN symbol (arrow out from emitter)
- [x] Draw PNP symbol (arrow into emitter)
- [x] Add to Semiconductors category

### Thyristors
- [x] Add THYRISTOR (SCR) to ComponentType enum
- [x] Add TRIAC to ComponentType enum
- [x] Define SCR pins: A (anode), K (cathode), G (gate)
- [x] Define TRIAC pins: MT1, MT2, G (gate)
- [x] Define parameters: vgt, igt, holding_current
- [x] Draw SCR symbol
- [x] Draw TRIAC symbol
- [x] Add to Semiconductors category

### Special Diodes
- [x] Add ZENER_DIODE to ComponentType enum
- [x] Add LED to ComponentType enum
- [x] Define Zener parameters: vz, iz_test, zz
- [x] Define LED parameters: vf, color, wavelength
- [x] Draw Zener symbol (bent cathode)
- [x] Draw LED symbol (diode with arrows)
- [x] Add to Semiconductors category

## Phase 3: Analog Components

### Operational Amplifier
- [x] Add OP_AMP to ComponentType enum
- [x] Define pins: IN+ (non-inverting), IN- (inverting), OUT, V+, V-
- [x] Define parameters: gain, gbw, slew_rate, vos
- [x] Draw op-amp triangle symbol
- [ ] Support rail-to-rail option
- [x] Add to Analog category

### Comparator
- [x] Add COMPARATOR to ComponentType enum
- [x] Define pins: IN+, IN-, OUT, V+, V-
- [x] Define parameters: vos, hysteresis, response_time
- [x] Draw comparator symbol (similar to op-amp with output indicator)
- [x] Add to Analog category

## Phase 4: Protection Components

### Relay
- [x] Add RELAY to ComponentType enum
- [x] Define coil pins: COIL+, COIL-
- [x] Define contact pins: COM, NO, NC
- [x] Define parameters: coil_voltage, coil_resistance, contact_rating
- [x] Draw relay symbol (coil + switch)
- [x] Add to Protection category

### Fuse
- [x] Add FUSE to ComponentType enum
- [x] Define pins: 1, 2
- [x] Define parameters: rating, blow_time_curve
- [x] Draw fuse symbol (rectangle with wire)
- [x] Add to Protection category

### Circuit Breaker
- [x] Add CIRCUIT_BREAKER to ComponentType enum
- [x] Define pins: LINE, LOAD
- [x] Define parameters: trip_current, trip_time
- [x] Draw breaker symbol
- [x] Add to Protection category

## Phase 5: Control Blocks

### Math/Signal Blocks
- [x] Add INTEGRATOR to ComponentType enum
- [x] Add DIFFERENTIATOR to ComponentType enum
- [x] Add LIMITER to ComponentType enum
- [x] Add RATE_LIMITER to ComponentType enum
- [x] Add HYSTERESIS to ComponentType enum
- [x] Define parameters for each block
- [x] Draw block symbols with function labels
- [x] Add to Control category

### Advanced Control
- [x] Add LOOKUP_TABLE to ComponentType enum
- [x] Add TRANSFER_FUNCTION to ComponentType enum
- [x] Add DELAY_BLOCK to ComponentType enum
- [x] Add SAMPLE_HOLD to ComponentType enum
- [x] Add STATE_MACHINE to ComponentType enum
- [ ] Implement table editor for lookup table
- [ ] Implement transfer function editor (numerator/denominator)
- [x] Draw symbols for each block
- [x] Add to Control category

## Phase 6: Measurement & Magnetic

### Probes
- [x] Add VOLTAGE_PROBE to ComponentType enum
- [x] Add CURRENT_PROBE to ComponentType enum
- [x] Add POWER_PROBE to ComponentType enum
- [x] Define probe parameters and display options
- [x] Draw probe symbols (voltmeter, ammeter style)
- [ ] Connect probes to waveform viewer
- [x] Add to Measurement category

### Magnetic Components
- [x] Add SATURABLE_INDUCTOR to ComponentType enum
- [x] Add COUPLED_INDUCTOR to ComponentType enum
- [x] Define saturation curve parameters
- [x] Define coupling coefficient for coupled inductor
- [x] Draw symbols with saturation indicator
- [x] Add to Magnetic category

### Pre-configured Networks
- [x] Add SNUBBER_RC to ComponentType enum
- [x] Define parameters: resistance, capacitance
- [x] Draw snubber symbol (R and C combined)
- [x] Add to Networks category

## Phase 7: Integration & Testing

### Library Panel Updates
- [x] Add new categories: Analog, Protection, Magnetic, Networks
- [x] Update category colors and icons
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
