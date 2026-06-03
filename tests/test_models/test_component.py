"""Tests for Component model."""

from pulsimgui.models.component import (
    CONNECTION_DOMAIN_ANY,
    CONNECTION_DOMAIN_SIGNAL,
    CURRENT_PROBE_OUTPUT_PIN_NAME,
    THERMAL_PORT_PARAMETER,
    THERMAL_PORT_PIN_NAME,
    VOLTAGE_PROBE_OUTPUT_PIN_NAME,
    Component,
    ComponentType,
    Pin,
    can_connect_measurement_pins,
    pin_connection_domain,
    set_cblock_io_counts,
    set_scope_channel_count,
    set_thermal_port_enabled,
)


class TestPin:
    def test_create_pin(self):
        pin = Pin(index=0, name="A", x=10.0, y=20.0)
        assert pin.index == 0
        assert pin.name == "A"
        assert pin.x == 10.0
        assert pin.y == 20.0

    def test_pin_serialization(self):
        pin = Pin(index=1, name="B", x=-5.0, y=15.0)
        data = pin.to_dict()
        assert data["index"] == 1
        assert data["name"] == "B"

        restored = Pin.from_dict(data)
        assert restored.index == pin.index
        assert restored.name == pin.name
        assert restored.x == pin.x
        assert restored.y == pin.y


class TestComponent:
    def test_create_resistor(self):
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        assert comp.type == ComponentType.RESISTOR
        assert comp.name == "R1"
        assert len(comp.pins) == 2
        assert "resistance" in comp.parameters

    def test_create_mosfet(self):
        comp = Component(type=ComponentType.MOSFET_N, name="M1")
        assert comp.type == ComponentType.MOSFET_N
        assert len(comp.pins) == 3
        assert "vth" in comp.parameters

    def test_default_parameters(self):
        resistor = Component(type=ComponentType.RESISTOR)
        assert resistor.parameters["resistance"] == 1000.0

        cap = Component(type=ComponentType.CAPACITOR)
        assert cap.parameters["capacitance"] == 1e-6

    def test_pin_position_no_rotation(self):
        comp = Component(type=ComponentType.RESISTOR, x=100, y=200)
        x, y = comp.get_pin_position(0)
        assert x == 100 + comp.pins[0].x
        assert y == 200 + comp.pins[0].y

    def test_pin_position_with_rotation(self):
        comp = Component(type=ComponentType.RESISTOR, x=0, y=0, rotation=90)
        # 90-degree rotation maps local (x, y) -> (-y, x).
        pin = comp.pins[0]
        expected_x = -pin.y
        expected_y = pin.x
        x, y = comp.get_pin_position(0)
        assert abs(x - expected_x) < 0.001
        assert abs(y - expected_y) < 0.001

    def test_serialization(self):
        comp = Component(
            type=ComponentType.CAPACITOR,
            name="C1",
            x=50,
            y=100,
            rotation=180,
        )
        comp.parameters["capacitance"] = 10e-6

        data = comp.to_dict()
        assert data["type"] == "CAPACITOR"
        assert data["name"] == "C1"
        assert data["x"] == 50
        assert data["rotation"] == 180

        restored = Component.from_dict(data)
        assert restored.type == comp.type
        assert restored.name == comp.name
        assert restored.x == comp.x
        assert restored.rotation == comp.rotation
        assert restored.parameters["capacitance"] == 10e-6

    def test_uuid_preserved(self):
        comp = Component(type=ComponentType.RESISTOR)
        original_id = comp.id
        data = comp.to_dict()
        restored = Component.from_dict(data)
        assert restored.id == original_id

    def test_control_blocks_have_defaults(self):
        pi = Component(type=ComponentType.PI_CONTROLLER)
        assert len(pi.pins) == 2
        assert "kp" in pi.parameters and "ki" in pi.parameters
        assert pi.parameters["sample_time"] == 0.0

        pid = Component(type=ComponentType.PID_CONTROLLER)
        assert "kd" in pid.parameters
        assert pid.parameters["sample_time"] == 0.0

        math_block = Component(type=ComponentType.MATH_BLOCK)
        assert math_block.parameters["operation"] == "sum"
        assert math_block.parameters["sample_time"] == 0.0

        pwm = Component(type=ComponentType.PWM_GENERATOR)
        # DUTY_IN is hidden by default; only OUT is present until enable_duty_input=True
        assert len(pwm.pins) == 1
        assert pwm.parameters["frequency"] == 10000.0
        assert pwm.parameters["sample_time"] == 0.0

        gain = Component(type=ComponentType.GAIN)
        assert len(gain.pins) == 2
        assert gain.parameters["gain"] == 1.0
        assert gain.parameters["sample_time"] == 0.0

        summing = Component(type=ComponentType.SUM)
        assert len(summing.pins) == 3
        assert summing.parameters["input_count"] == 2
        assert summing.parameters["sample_time"] == 0.0

        subtractor = Component(type=ComponentType.SUBTRACTOR)
        assert len(subtractor.pins) == 3
        assert subtractor.parameters["signs"] == ["+", "-"]
        assert subtractor.parameters["sample_time"] == 0.0

        # Default pin layout: only OUT exposed (DUTY_IN requires enable_duty_input=True).
        assert pwm.pins[0].name == "OUT"

    def test_scopes_and_probes_do_not_expose_control_sample_time(self):
        scope = Component(type=ComponentType.ELECTRICAL_SCOPE)
        thermal_scope = Component(type=ComponentType.THERMAL_SCOPE)
        v_probe = Component(type=ComponentType.VOLTAGE_PROBE)
        i_probe = Component(type=ComponentType.CURRENT_PROBE)
        p_probe = Component(type=ComponentType.POWER_PROBE)

        assert "sample_time" not in scope.parameters
        assert "sample_time" not in thermal_scope.parameters
        assert "sample_time" not in v_probe.parameters
        assert "sample_time" not in i_probe.parameters
        assert "sample_time" not in p_probe.parameters

    def test_cblock_defaults_and_pin_names(self):
        cblock = Component(type=ComponentType.C_BLOCK, name="CB1")

        assert cblock.parameters["n_inputs"] == 1
        assert cblock.parameters["n_outputs"] == 1
        assert cblock.parameters["implementation"] == "source"
        assert [pin.name for pin in cblock.pins] == ["IN0", "OUT"]

    def test_cblock_io_updates_rebuild_pins(self):
        cblock = Component(type=ComponentType.C_BLOCK, name="CB1")

        set_cblock_io_counts(cblock, n_inputs=3, n_outputs=2)

        assert cblock.parameters["n_inputs"] == 3
        assert cblock.parameters["n_outputs"] == 2
        assert [pin.name for pin in cblock.pins] == ["IN0", "IN1", "IN2", "OUT0", "OUT1"]

    def test_cblock_io_clamps_to_valid_range(self):
        cblock = Component(type=ComponentType.C_BLOCK, name="CB1")

        set_cblock_io_counts(cblock, n_inputs=0, n_outputs=0)

        assert cblock.parameters["n_inputs"] == 1
        assert cblock.parameters["n_outputs"] == 1
        assert [pin.name for pin in cblock.pins] == ["IN0", "OUT"]

    def test_cblock_pins_use_signal_domain(self):
        cblock = Component(type=ComponentType.C_BLOCK, name="CB1")

        assert pin_connection_domain(cblock, 0) == CONNECTION_DOMAIN_SIGNAL
        assert pin_connection_domain(cblock, 1) == CONNECTION_DOMAIN_SIGNAL

    def test_thermal_port_default_is_disabled(self):
        resistor = Component(type=ComponentType.RESISTOR)
        assert resistor.parameters[THERMAL_PORT_PARAMETER] is False
        assert all(pin.name != THERMAL_PORT_PIN_NAME for pin in resistor.pins)

    def test_thermal_port_toggle_updates_pin_layout(self):
        resistor = Component(type=ComponentType.RESISTOR)
        assert len(resistor.pins) == 2

        set_thermal_port_enabled(resistor, True)
        assert resistor.parameters[THERMAL_PORT_PARAMETER] is True
        assert len(resistor.pins) == 3
        assert resistor.pins[-1].name == THERMAL_PORT_PIN_NAME

        set_thermal_port_enabled(resistor, False)
        assert resistor.parameters[THERMAL_PORT_PARAMETER] is False
        assert len(resistor.pins) == 2
        assert all(pin.name != THERMAL_PORT_PIN_NAME for pin in resistor.pins)

    def test_thermal_port_not_exposed_for_unsupported_components(self):
        pi = Component(type=ComponentType.PI_CONTROLLER)
        assert THERMAL_PORT_PARAMETER not in pi.parameters

    def test_legacy_mosfet_with_thermal_enabled_backfills_required_params(self):
        legacy = Component.from_dict(
            {
                "id": "6a7f6ecf-1f5c-4a17-89a1-53b8d57d1401",
                "type": "MOSFET_N",
                "name": "M1",
                "x": 0.0,
                "y": 0.0,
                "rotation": 0,
                "mirrored_h": False,
                "mirrored_v": False,
                "parameters": {
                    "vth": 2.0,
                    "kp": 0.1,
                    "thermal_enabled": True,
                },
                "pins": [],
            }
        )

        assert legacy.parameters["thermal_enabled"] is True
        assert legacy.parameters["thermal_network"] == "single_rc"
        assert legacy.parameters["thermal_rth"] > 0.0
        assert legacy.parameters["thermal_cth"] >= 0.0
        assert "thermal_rth_stages" in legacy.parameters
        assert "thermal_cth_stages" in legacy.parameters
        assert "thermal_temp_init" in legacy.parameters
        assert "thermal_temp_ref" in legacy.parameters
        assert "thermal_alpha" in legacy.parameters
        assert "thermal_shared_sink_id" in legacy.parameters
        assert "thermal_shared_sink_rth" in legacy.parameters
        assert "thermal_shared_sink_cth" in legacy.parameters

    def test_legacy_mosfet_with_thermal_port_enabled_backfills_required_params(self):
        legacy = Component.from_dict(
            {
                "id": "3d2fd604-df76-4dd1-bc78-f0ac63ee4934",
                "type": "MOSFET_N",
                "name": "M1",
                "x": 0.0,
                "y": 0.0,
                "rotation": 0,
                "mirrored_h": False,
                "mirrored_v": False,
                "parameters": {
                    "vth": 2.0,
                    "kp": 0.1,
                    THERMAL_PORT_PARAMETER: True,
                },
                "pins": [],
            }
        )

        assert legacy.parameters[THERMAL_PORT_PARAMETER] is True
        assert legacy.parameters["thermal_enabled"] is True
        assert legacy.parameters["thermal_rth"] > 0.0
        assert legacy.parameters["thermal_cth"] >= 0.0

    def test_legacy_component_with_serialized_th_pin_keeps_thermal_port_enabled(self):
        legacy = Component.from_dict(
            {
                "id": "12a177d5-c6d2-4f54-9f31-fb5f0cc874cf",
                "type": "RESISTOR",
                "name": "R1",
                "x": 0.0,
                "y": 0.0,
                "rotation": 0,
                "mirrored_h": False,
                "mirrored_v": False,
                "parameters": {"resistance": 1000.0},
                "pins": [
                    {"index": 0, "name": "1", "x": -30.0, "y": 0.0},
                    {"index": 1, "name": "2", "x": 30.0, "y": 0.0},
                    {"index": 2, "name": THERMAL_PORT_PIN_NAME, "x": 0.0, "y": 20.0},
                ],
            }
        )

        assert legacy.parameters[THERMAL_PORT_PARAMETER] is True
        assert legacy.pins[-1].name == THERMAL_PORT_PIN_NAME

    def test_voltage_probe_has_scope_output_pin(self):
        probe = Component(type=ComponentType.VOLTAGE_PROBE)
        assert len(probe.pins) == 3
        assert probe.pins[2].name == VOLTAGE_PROBE_OUTPUT_PIN_NAME

    def test_current_probe_has_scope_output_pin(self):
        probe = Component(type=ComponentType.CURRENT_PROBE)
        assert len(probe.pins) == 3
        assert probe.pins[2].name == CURRENT_PROBE_OUTPUT_PIN_NAME

    def test_voltage_probe_gnd_has_single_input_and_scope_output(self):
        probe = Component(type=ComponentType.VOLTAGE_PROBE_GND)
        assert len(probe.pins) == 2
        assert probe.pins[0].name == "IN"
        assert probe.pins[1].name == VOLTAGE_PROBE_OUTPUT_PIN_NAME

    def test_goto_and_from_pins_use_any_domain(self):
        goto = Component(type=ComponentType.GOTO_LABEL, parameters={"net_label": "BUS_A"})
        from_label = Component(type=ComponentType.FROM_LABEL, parameters={"net_label": "BUS_A"})

        assert pin_connection_domain(goto, 0) == CONNECTION_DOMAIN_ANY
        assert pin_connection_domain(from_label, 0) == CONNECTION_DOMAIN_ANY
        assert goto.pins[0].x < 0
        assert from_label.pins[0].x > 0

    def test_scope_connection_rules_for_electrical_probes(self):
        scope = Component(type=ComponentType.ELECTRICAL_SCOPE, name="ES1")
        v_probe = Component(type=ComponentType.VOLTAGE_PROBE, name="VP1")
        resistor = Component(type=ComponentType.RESISTOR, name="R1")
        pi = Component(type=ComponentType.PI_CONTROLLER, name="PI1")

        assert can_connect_measurement_pins(scope, 0, v_probe, 2)
        assert can_connect_measurement_pins(scope, 0, pi, 1)
        assert not can_connect_measurement_pins(scope, 0, pi, 0)
        assert not can_connect_measurement_pins(scope, 0, resistor, 0)

    def test_scope_connection_rules_for_thermal_outputs(self):
        scope = Component(type=ComponentType.THERMAL_SCOPE, name="TS1")
        resistor = Component(type=ComponentType.RESISTOR, name="R1")
        set_thermal_port_enabled(resistor, True)

        assert can_connect_measurement_pins(scope, 0, resistor, 2)
        assert not can_connect_measurement_pins(scope, 0, resistor, 1)

    def test_scope_channel_count_expands_pin_layout(self):
        scope = Component(type=ComponentType.ELECTRICAL_SCOPE, name="ES1")
        assert len(scope.pins) == 2

        set_scope_channel_count(scope, 6)
        assert scope.parameters["channel_count"] == 6
        assert len(scope.pins) == 6
        assert [pin.name for pin in scope.pins] == ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6"]
        constant = Component(type=ComponentType.CONSTANT, name="K1")
        assert can_connect_measurement_pins(scope, 3, constant, 0)

    def test_scope_channel_count_allows_up_to_sixteen_channels(self):
        scope = Component(type=ComponentType.THERMAL_SCOPE, name="TS1")
        set_scope_channel_count(scope, 16)

        assert scope.parameters["channel_count"] == 16
        assert len(scope.pins) == 16
        assert scope.pins[0].name == "CH1"
        assert scope.pins[-1].name == "CH16"

    def test_control_signal_links_are_not_limited_to_scope_only_routing(self):
        constant = Component(type=ComponentType.CONSTANT, name="K1")
        cblock = Component(type=ComponentType.C_BLOCK, name="CB1")
        pi = Component(type=ComponentType.PI_CONTROLLER, name="PI1")
        pwm = Component(type=ComponentType.PWM_GENERATOR, name="PWM1")
        v_probe = Component(type=ComponentType.VOLTAGE_PROBE, name="VP1")
        v_probe_gnd = Component(type=ComponentType.VOLTAGE_PROBE_GND, name="X1")
        i_probe = Component(type=ComponentType.CURRENT_PROBE, name="IP1")

        assert can_connect_measurement_pins(constant, 0, cblock, 0)
        assert can_connect_measurement_pins(pi, 1, pwm, 1)
        assert can_connect_measurement_pins(v_probe, 2, cblock, 0)
        assert can_connect_measurement_pins(v_probe_gnd, 1, cblock, 0)
        assert can_connect_measurement_pins(i_probe, 2, cblock, 0)


class TestLoadedPinPreservation:
    """Opening a saved circuit must snap pins to the current wiring grid.

    History: an earlier iteration preserved saved pin coordinates verbatim
    so wires would stay attached after a default-layout migration. That
    preservation pinned components to their *pre-snap* coordinates
    forever, which produced the user-visible "old blocks look off-grid,
    new blocks look correct" symptom. The current rule is the opposite:
    every restored coordinate is snapped to the 20-px wiring grid.

    On already-aligned files the snap is a no-op. On files saved before
    the grid-alignment pass it auto-migrates ±25 / ±30 / ±35 to
    ±20 / ±40 — the same positions a freshly-placed component would get.
    Wires get the same snap via
    ``SchematicScene._normalize_circuit_geometry`` so the endpoint still
    meets the migrated pin.
    """

    def _off_grid_dict(
        self,
        type_name: str,
        pins: list[tuple[str, float, float]],
        parameters: dict | None = None,
    ) -> dict:
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "type": type_name,
            "name": "X1",
            "x": 100.0,
            "y": 100.0,
            "rotation": 0,
            "mirrored_h": False,
            "mirrored_v": False,
            "parameters": parameters or {},
            "pins": [
                {"index": i, "name": n, "x": x, "y": y}
                for i, (n, x, y) in enumerate(pins)
            ],
        }

    def test_loaded_offgrid_resistor_pins_snap_to_grid(self):
        # ±25 saved → ±20 after load (half-rounded toward zero).
        comp = Component.from_dict(
            self._off_grid_dict("RESISTOR", [("1", -25.0, 0.0), ("2", 25.0, 0.0)])
        )
        coords = [(p.name, p.x, p.y) for p in comp.pins]
        assert coords == [("1", -20.0, 0.0), ("2", 20.0, 0.0)]

    def test_loaded_offgrid_device_pins_snap_to_grid(self):
        # PMSM-style ±25 / ±30 offsets (the pre-grid layout the user was
        # complaining about) → migrated to the current ±20 / ±40 layout
        # on load. Wire endpoints that were saved at the old positions
        # get the same snap via SchematicScene normalisation, so the
        # connection survives.
        comp = Component.from_dict(
            self._off_grid_dict(
                "PMSM",
                [("A", -30.0, -25.0), ("B", -30.0, 0.0), ("C", -30.0, 25.0), ("N", 30.0, 0.0)],
            )
        )
        coords = {p.name: (p.x, p.y) for p in comp.pins}
        for name, pos in {
            "A": (-40.0, -20.0),
            "B": (-40.0, 0.0),
            "C": (-40.0, 20.0),
            "N": (40.0, 0.0),
        }.items():
            assert coords[name] == pos
        # Synchronization appends the signal-bus pin (a new, on-grid pin) —
        # the migration must NOT skip it.
        assert "SIG" in coords

    def test_loaded_scope_channel_positions_snap_to_grid(self):
        comp = Component.from_dict(
            self._off_grid_dict(
                "ELECTRICAL_SCOPE",
                [("CH1", -40.0, -25.0), ("CH2", -40.0, 0.0), ("CH3", -40.0, 25.0)],
                parameters={"channel_count": 3},
            )
        )
        coords = {p.name: (p.x, p.y) for p in comp.pins}
        assert coords["CH1"] == (-40.0, -20.0)
        assert coords["CH3"] == (-40.0, 20.0)

    def test_already_aligned_positions_remain_unchanged(self):
        # A file saved after the grid-alignment pass: saved coords are
        # already snapped, so the migration is a no-op.
        comp = Component.from_dict(
            self._off_grid_dict(
                "RESISTOR", [("1", -40.0, 0.0), ("2", 40.0, 0.0)],
            )
        )
        coords = [(p.name, p.x, p.y) for p in comp.pins]
        assert coords == [("1", -40.0, 0.0), ("2", 40.0, 0.0)]

    def test_fresh_component_still_snaps_to_grid(self):
        # No pins provided => default layout + grid snap (unchanged behavior).
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        for pin in comp.pins:
            assert pin.x % 20.0 == 0.0 and pin.y % 20.0 == 0.0

    def test_structural_migration_still_applies_on_load(self):
        # Empty saved pins => generate defaults (legit structural change).
        comp = Component.from_dict(self._off_grid_dict("C_BLOCK", []))
        names = {p.name for p in comp.pins}
        assert "IN0" in names and "OUT" in names


class TestParameterBackfillOnLoad:
    """A saved component must auto-pick-up parameter defaults added in a
    newer release.

    Regression: an older save of a ``PFC_BOOST_CONTROLLER`` did not have
    ``soft_start_time`` / ``v_bus_initial`` because the keys didn't exist
    yet. When the user opened the file, the properties dialog only listed
    the saved keys, and the backend ``_build_pfc_loops`` had to fall back
    to hard-coded defaults the controller author couldn't override from
    the GUI. The post-init now ``setdefault``-merges every missing key
    from ``DEFAULT_PARAMETERS`` so the saved parameter set always
    matches a freshly-instantiated component of the same type, while
    every user-customised value survives untouched.
    """

    def test_pfc_controller_gets_new_soft_start_keys_on_load(self):
        data = {
            "id": "22222222-2222-2222-2222-222222222222",
            "type": "PFC_BOOST_CONTROLLER",
            "name": "PFC",
            "x": 0.0, "y": 0.0,
            "rotation": 0, "mirrored_h": False, "mirrored_v": False,
            "pins": [],
            "parameters": {
                # The keys the user picked when they saved the file —
                # ``soft_start_time`` / ``v_bus_initial`` are absent.
                "v_bus_ref": 400.0,
                "voltage_kp": 0.30,
                "voltage_ki": 6.0,
                "current_kp": 31.4,
                "current_ki": 3140.0,
                "i_pk_limit": 20.0,
            },
        }
        comp = Component.from_dict(data)
        # The user's saved values survived.
        assert comp.parameters["v_bus_ref"] == 400.0
        assert comp.parameters["voltage_kp"] == 0.30
        # The new keys came in from DEFAULT_PARAMETERS.
        assert "soft_start_time" in comp.parameters
        assert "v_bus_initial" in comp.parameters
        assert comp.parameters["soft_start_time"] > 0.0

    def test_user_customised_value_is_not_overwritten(self):
        # If the saved file already has a key, the default never wins.
        data = {
            "id": "33333333-3333-3333-3333-333333333333",
            "type": "PFC_BOOST_CONTROLLER",
            "name": "PFC",
            "x": 0.0, "y": 0.0,
            "rotation": 0, "mirrored_h": False, "mirrored_v": False,
            "pins": [],
            "parameters": {
                "v_bus_ref": 380.0,           # not the 400 V default
                "soft_start_time": 0.20,      # user tuned to slow ramp
            },
        }
        comp = Component.from_dict(data)
        assert comp.parameters["v_bus_ref"] == 380.0
        assert comp.parameters["soft_start_time"] == 0.20
        # Other defaults still fill in.
        assert "current_kp" in comp.parameters
        assert "vac_pk_nom" in comp.parameters
