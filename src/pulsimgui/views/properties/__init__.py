"""Properties panel views."""

from pulsimgui.views.properties.properties_panel import PropertiesPanel, SIValueWidget
from pulsimgui.views.properties.waveform_editors import (
    DCEditor,
    PulseEditor,
    PWLEditor,
    PWMEditor,
    SineEditor,
    WaveformEditorDialog,
    WaveformPreview,
)

# Alias for backward compatibility
SILineEdit = SIValueWidget

__all__ = [
    "PropertiesPanel",
    "SIValueWidget",
    "SILineEdit",  # Backward compatibility alias
    "WaveformEditorDialog",
    "WaveformPreview",
    "DCEditor",
    "PulseEditor",
    "SineEditor",
    "PWLEditor",
    "PWMEditor",
]
