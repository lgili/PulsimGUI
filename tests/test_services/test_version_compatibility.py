"""Tests for version compatibility checking."""

from __future__ import annotations

import pytest

from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.backend_types import BackendVersion, MIN_BACKEND_API


class TestBackendVersion:
    """Tests for BackendVersion parsing and comparison."""

    def test_parse_simple_version(self) -> None:
        """Test parsing a simple version string."""
        version = BackendVersion.from_string("0.2.1")
        assert version.major == 0
        assert version.minor == 2
        assert version.patch == 1
        assert version.api_version == 1

    def test_parse_version_with_api(self) -> None:
        """Test parsing version with API suffix."""
        version = BackendVersion.from_string("1.0.0+api2")
        assert version.major == 1
        assert version.minor == 0
        assert version.patch == 0
        assert version.api_version == 2

    def test_parse_version_with_prerelease(self) -> None:
        """Test parsing version with prerelease suffix."""
        version = BackendVersion.from_string("0.3.0-beta")
        assert version.major == 0
        assert version.minor == 3
        assert version.patch == 0

    def test_parse_two_part_version(self) -> None:
        """Test parsing version with only major.minor."""
        version = BackendVersion.from_string("1.5")
        assert version.major == 1
        assert version.minor == 5
        assert version.patch == 0

    def test_parse_invalid_version_raises(self) -> None:
        """Test that invalid version strings raise ValueError."""
        with pytest.raises(ValueError):
            BackendVersion.from_string("invalid")

        with pytest.raises(ValueError):
            BackendVersion.from_string("1")

    def test_is_compatible_with_same_version(self) -> None:
        """Test compatibility with same version."""
        v1 = BackendVersion(0, 2, 0)
        v2 = BackendVersion(0, 2, 0)
        assert v1.is_compatible_with(v2)

    def test_is_compatible_with_newer_version(self) -> None:
        """Test compatibility when current is newer."""
        current = BackendVersion(0, 3, 0)
        required = BackendVersion(0, 2, 0)
        assert current.is_compatible_with(required)

    def test_is_not_compatible_with_older_version(self) -> None:
        """Test incompatibility when current is older."""
        current = BackendVersion(0, 1, 0)
        required = BackendVersion(0, 2, 0)
        assert not current.is_compatible_with(required)

    def test_api_version_takes_precedence(self) -> None:
        """Test that API version is checked first."""
        # Higher semantic version but lower API
        current = BackendVersion(1, 0, 0, api_version=1)
        required = BackendVersion(0, 1, 0, api_version=2)
        assert not current.is_compatible_with(required)

        # Lower semantic version but higher API
        current = BackendVersion(0, 1, 0, api_version=2)
        required = BackendVersion(1, 0, 0, api_version=1)
        assert current.is_compatible_with(required)

    def test_version_string_representation(self) -> None:
        """Test string representation of version."""
        version = BackendVersion(0, 2, 1, api_version=2)
        assert str(version) == "0.2.1+api2"

        version = BackendVersion(1, 0, 0, api_version=1)
        assert str(version) == "1.0.0"


class TestBackendInfoCompatibility:
    """Tests for BackendInfo compatibility checking."""

    def test_check_compatibility_with_valid_version(self) -> None:
        """Test compatibility check with valid version."""
        info = BackendInfo(
            identifier="test",
            name="Test",
            version="0.3.0",
            status="available",
            capabilities={"dc", "ac", "transient"},
        )
        info.check_compatibility()

        assert info.is_compatible
        assert info.compatibility_warning == ""
        assert info.parsed_version is not None
        assert info.parsed_version.major == 0
        assert info.parsed_version.minor == 3

    def test_check_compatibility_with_old_version(self) -> None:
        """Test compatibility check with old version."""
        info = BackendInfo(
            identifier="test",
            name="Test",
            version="0.1.0",
            status="available",
            capabilities={"transient"},
        )
        info.check_compatibility()

        assert not info.is_compatible
        assert "older than minimum required" in info.compatibility_warning
        assert "0.2.0" in info.compatibility_warning  # MIN_BACKEND_API version

    def test_check_compatibility_with_invalid_version(self) -> None:
        """Test compatibility check with unparseable version."""
        info = BackendInfo(
            identifier="test",
            name="Test",
            version="unknown",
            status="available",
        )
        info.check_compatibility()

        assert not info.is_compatible
        assert "Unable to parse version" in info.compatibility_warning

    def test_unavailable_features_calculated(self) -> None:
        """Test that unavailable features are calculated."""
        info = BackendInfo(
            identifier="test",
            name="Test",
            version="0.3.0",
            status="available",
            capabilities={"transient", "dc"},  # Missing ac, thermal
        )
        info.check_compatibility()

        assert "ac" in info.unavailable_features
        assert "thermal" in info.unavailable_features
        assert "transient" not in info.unavailable_features
        assert "dc" not in info.unavailable_features

    def test_all_features_available(self) -> None:
        """Test when all features are available."""
        info = BackendInfo(
            identifier="test",
            name="Test",
            version="0.3.0",
            status="available",
            capabilities={"transient", "dc", "ac", "thermal"},
        )
        info.check_compatibility()

        assert info.unavailable_features == []


class TestMinBackendAPI:
    """Tests for MIN_BACKEND_API constant."""

    def test_min_backend_api_defined(self) -> None:
        """Test that MIN_BACKEND_API is properly defined."""
        assert MIN_BACKEND_API.major == 0
        assert MIN_BACKEND_API.minor == 2
        assert MIN_BACKEND_API.patch == 0
        assert MIN_BACKEND_API.api_version == 1

    def test_current_version_compatible(self) -> None:
        """Test that typical current versions are compatible."""
        current = BackendVersion.from_string("0.3.0")
        assert current.is_compatible_with(MIN_BACKEND_API)

        current = BackendVersion.from_string("1.0.0")
        assert current.is_compatible_with(MIN_BACKEND_API)

    def test_old_version_incompatible(self) -> None:
        """Test that old versions are incompatible."""
        old = BackendVersion.from_string("0.1.9")
        assert not old.is_compatible_with(MIN_BACKEND_API)
