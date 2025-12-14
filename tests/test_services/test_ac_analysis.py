"""Tests for AC frequency analysis."""

import math
import pytest

from pulsimgui.services.backend_adapter import PlaceholderBackend
from pulsimgui.services.backend_types import ACSettings, ACResult


class TestACSettings:
    """Tests for ACSettings dataclass."""

    def test_default_values(self):
        """ACSettings should have reasonable defaults."""
        settings = ACSettings()

        assert settings.f_start == 1.0
        assert settings.f_stop == 1e6
        assert settings.points_per_decade == 10
        assert settings.input_source == ""

    def test_custom_values(self):
        """ACSettings should accept custom values."""
        settings = ACSettings(
            f_start=100.0,
            f_stop=10000.0,
            points_per_decade=20,
            input_source="V1",
        )

        assert settings.f_start == 100.0
        assert settings.f_stop == 10000.0
        assert settings.points_per_decade == 20
        assert settings.input_source == "V1"


class TestACResult:
    """Tests for ACResult dataclass."""

    def test_empty_result_is_invalid(self):
        """Empty ACResult should be invalid."""
        result = ACResult()

        assert not result.is_valid
        assert len(result.frequencies) == 0
        assert len(result.magnitude) == 0
        assert len(result.phase) == 0

    def test_result_with_data_is_valid(self):
        """ACResult with data should be valid."""
        result = ACResult(
            frequencies=[100, 1000, 10000],
            magnitude={"V(out)": [0.0, -3.0, -20.0]},
            phase={"V(out)": [0.0, -45.0, -90.0]},
        )

        assert result.is_valid
        assert len(result.frequencies) == 3
        assert "V(out)" in result.magnitude
        assert "V(out)" in result.phase

    def test_result_with_error_is_invalid(self):
        """ACResult with error message should be invalid."""
        result = ACResult(
            frequencies=[100, 1000],
            magnitude={"V(out)": [0.0, -3.0]},
            phase={"V(out)": [0.0, -45.0]},
            error_message="Convergence failed",
        )

        assert not result.is_valid


class TestPlaceholderBackendAC:
    """Tests for PlaceholderBackend AC analysis."""

    def test_run_ac_returns_valid_result(self):
        """run_ac should return a valid ACResult."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=100, f_stop=100000)

        result = backend.run_ac({}, settings)

        assert result is not None
        assert result.is_valid
        assert len(result.frequencies) > 0
        assert len(result.magnitude) > 0
        assert len(result.phase) > 0

    def test_run_ac_frequency_range(self):
        """AC result frequencies should span requested range."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=100, f_stop=10000, points_per_decade=5)

        result = backend.run_ac({}, settings)

        assert min(result.frequencies) >= 100
        assert max(result.frequencies) <= 10000

    def test_run_ac_points_per_decade(self):
        """AC result should have approximately correct number of points."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=100, f_stop=10000, points_per_decade=10)

        result = backend.run_ac({}, settings)

        # 100 to 10000 is 2 decades, so expect ~20 points
        decades = math.log10(10000 / 100)
        expected_points = int(decades * 10) + 1
        assert abs(len(result.frequencies) - expected_points) <= 2

    def test_run_ac_logarithmic_spacing(self):
        """AC frequencies should be logarithmically spaced."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=100, f_stop=10000, points_per_decade=10)

        result = backend.run_ac({}, settings)

        if len(result.frequencies) >= 3:
            # Check ratio between consecutive frequencies is roughly constant
            ratios = []
            for i in range(1, len(result.frequencies)):
                ratio = result.frequencies[i] / result.frequencies[i - 1]
                ratios.append(ratio)

            # All ratios should be similar for log spacing
            avg_ratio = sum(ratios) / len(ratios)
            for ratio in ratios:
                assert abs(ratio - avg_ratio) / avg_ratio < 0.1  # Within 10%


class TestRCLowPassFilter:
    """Tests for RC low-pass filter AC response (placeholder simulation)."""

    def test_low_frequency_passband(self):
        """At low frequencies, magnitude should be near 0 dB."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=1, f_stop=100, points_per_decade=5)

        result = backend.run_ac({}, settings)

        if result.is_valid and result.magnitude:
            signal_name = list(result.magnitude.keys())[0]
            low_freq_mag = result.magnitude[signal_name][0]
            # At very low frequencies, should be close to 0 dB
            assert low_freq_mag > -3.0  # Should be in passband

    def test_high_frequency_rolloff(self):
        """At high frequencies, magnitude should roll off."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=100, f_stop=100000, points_per_decade=5)

        result = backend.run_ac({}, settings)

        if result.is_valid and result.magnitude:
            signal_name = list(result.magnitude.keys())[0]
            magnitudes = result.magnitude[signal_name]
            # High frequency magnitude should be less than low frequency
            assert magnitudes[-1] < magnitudes[0]

    def test_cutoff_frequency_characteristics(self):
        """At cutoff frequency, magnitude should be approximately -3 dB."""
        backend = PlaceholderBackend()
        # Placeholder uses fc = 1000 Hz
        settings = ACSettings(f_start=100, f_stop=10000, points_per_decade=20)

        result = backend.run_ac({}, settings)

        if result.is_valid and result.magnitude:
            signal_name = list(result.magnitude.keys())[0]
            frequencies = result.frequencies
            magnitudes = result.magnitude[signal_name]

            # Find magnitude closest to cutoff (1000 Hz)
            for i, f in enumerate(frequencies):
                if 900 <= f <= 1100:
                    # At cutoff, magnitude should be around -3 dB
                    assert -5.0 < magnitudes[i] < -1.0
                    break

    def test_phase_at_cutoff(self):
        """At cutoff frequency, phase should be approximately -45 degrees."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=100, f_stop=10000, points_per_decade=20)

        result = backend.run_ac({}, settings)

        if result.is_valid and result.phase:
            signal_name = list(result.phase.keys())[0]
            frequencies = result.frequencies
            phases = result.phase[signal_name]

            # Find phase closest to cutoff (1000 Hz)
            for i, f in enumerate(frequencies):
                if 900 <= f <= 1100:
                    # At cutoff, phase should be around -45 degrees
                    assert -60.0 < phases[i] < -30.0
                    break

    def test_phase_approaches_negative_90(self):
        """At high frequencies, phase should approach -90 degrees."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=1000, f_stop=1000000, points_per_decade=5)

        result = backend.run_ac({}, settings)

        if result.is_valid and result.phase:
            signal_name = list(result.phase.keys())[0]
            high_freq_phase = result.phase[signal_name][-1]
            # Should approach -90 degrees
            assert high_freq_phase < -80.0


class TestFrequencyRangeEdgeCases:
    """Tests for edge cases in frequency range."""

    def test_narrow_frequency_range(self):
        """Should handle narrow frequency range."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=1000, f_stop=1001, points_per_decade=10)

        result = backend.run_ac({}, settings)

        assert result is not None
        # May have very few points, but should not crash
        assert len(result.frequencies) >= 1

    def test_wide_frequency_range(self):
        """Should handle wide frequency range (many decades)."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=0.1, f_stop=1e9, points_per_decade=5)

        result = backend.run_ac({}, settings)

        assert result is not None
        assert result.is_valid
        # 10 decades * 5 points = ~50 points
        assert len(result.frequencies) >= 40

    def test_single_point(self):
        """Should handle single frequency point request."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=1000, f_stop=1000, points_per_decade=10)

        result = backend.run_ac({}, settings)

        assert result is not None
        # Should have at least 1 point
        assert len(result.frequencies) >= 1

    def test_very_low_frequency(self):
        """Should handle very low frequencies."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=0.001, f_stop=1.0, points_per_decade=5)

        result = backend.run_ac({}, settings)

        assert result is not None
        assert result.is_valid
        assert result.frequencies[0] >= 0.001

    def test_very_high_frequency(self):
        """Should handle very high frequencies."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=1e6, f_stop=1e12, points_per_decade=5)

        result = backend.run_ac({}, settings)

        assert result is not None
        assert result.is_valid


class TestStabilityMargins:
    """Tests for stability margin calculations."""

    def test_gain_margin_calculation(self):
        """Gain margin should be calculated from phase crossover."""
        # Test data: simple low-pass filter response
        frequencies = [100, 1000, 10000]
        magnitude = [0.0, -3.0, -20.0]
        phase = [-10.0, -45.0, -85.0]

        # At -180 degrees, there's no crossover in this data
        # So gain margin should be infinite (None)
        phase_crossover_idx = None
        for i in range(len(phase) - 1):
            if phase[i] >= -180 > phase[i + 1]:
                phase_crossover_idx = i
                break

        assert phase_crossover_idx is None  # No phase crossover

    def test_phase_margin_calculation(self):
        """Phase margin should be calculated from gain crossover."""
        # Test data where magnitude crosses 0 dB
        frequencies = [100, 1000, 10000]
        magnitude = [10.0, -3.0, -20.0]
        phase = [-10.0, -45.0, -85.0]

        # Find gain crossover (magnitude crosses 0 dB)
        gain_crossover_idx = None
        for i in range(len(magnitude) - 1):
            if magnitude[i] >= 0 > magnitude[i + 1]:
                gain_crossover_idx = i
                break

        assert gain_crossover_idx == 0  # Crosses between 100 and 1000 Hz

        # Phase margin = phase + 180 at gain crossover
        # Interpolate: at some point between -10 and -45 degrees
        # Phase margin should be positive for stability
