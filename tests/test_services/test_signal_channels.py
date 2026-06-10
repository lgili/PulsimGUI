"""Channel enumeration + the *_from_channel picker in the properties panel."""
from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.services.signal_channels import (
    enumerate_channels,
    is_channel_parameter,
)


def _circuit() -> Circuit:
    circuit = Circuit(name="test")
    for ctype, name in [
        (ComponentType.VOLTAGE_PROBE_GND, "VP_bus"),
        (ComponentType.CURRENT_PROBE, "IP_load"),
        (ComponentType.PI_CONTROLLER, "PI_v"),
        (ComponentType.C_BLOCK, "CTRL"),
        (ComponentType.PLL, "PLL1"),
        (ComponentType.RESISTOR, "R1"),          # not a channel
        (ComponentType.GROUND, "GND1"),          # not a channel
    ]:
        circuit.add_component(Component(type=ctype, name=name))
    return circuit


def test_enumerate_channels_probes_first_then_blocks() -> None:
    channels = enumerate_channels(_circuit())
    assert channels[:2] == ["IP_load", "VP_bus"]            # probes, sorted
    assert "PI_v" in channels and "CTRL" in channels        # block outputs
    assert "PLL1.theta" in channels and "PLL1.omega" in channels
    assert "R1" not in channels and "GND1" not in channels


def test_enumerate_handles_empty() -> None:
    assert enumerate_channels(None) == []
    assert enumerate_channels(Circuit(name="empty")) == []


def test_is_channel_parameter() -> None:
    assert is_channel_parameter("duty_from_channel")
    assert is_channel_parameter("theta_from_channel")
    assert not is_channel_parameter("resistance")
    assert not is_channel_parameter("channel_count")


def test_properties_panel_renders_channel_picker(qapp) -> None:
    """A PWM_GENERATOR's duty_from_channel renders as an editable combo with
    the circuit's channels when a provider is installed."""
    from PySide6.QtWidgets import QComboBox

    from pulsimgui.views.properties.properties_panel import PropertiesPanel

    circuit = _circuit()
    panel = PropertiesPanel()
    panel.set_channel_provider(lambda: enumerate_channels(circuit))
    component = Component(type=ComponentType.PWM_GENERATOR, name="PWM1")
    component.parameters["duty_from_channel"] = "PI_v"
    widget = panel._create_widget_for_value("duty_from_channel", "PI_v")
    try:
        assert isinstance(widget, QComboBox)
        assert widget.isEditable()
        items = [widget.itemText(i) for i in range(widget.count())]
        assert "" in items                      # explicit unbound entry
        assert "PI_v" in items and "VP_bus" in items
        assert widget.currentText() == "PI_v"
        # a plain string param still renders as a line edit
        other = panel._create_widget_for_value("some_label", "abc")
        assert not isinstance(other, QComboBox)
    finally:
        panel.deleteLater()
