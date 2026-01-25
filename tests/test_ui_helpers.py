"""
Unit tests for UI helper functions in src/ui_components.py

Tests standalone helper functions that don't require the Arcade framework
to be running, focusing on _format_wind_direction().

Note: These tests mock the arcade import to avoid requiring arcade to be installed
for testing pure utility functions.
"""
import pytest
import sys
from unittest.mock import MagicMock

# Mock arcade before importing ui_components
sys.modules['arcade'] = MagicMock()

# Now we can import the helper function
from src.ui_components import _format_wind_direction


class TestFormatWindDirection:
    """Tests for _format_wind_direction() that converts degrees to compass directions."""

    # =========================================================================
    # Cardinal Directions
    # =========================================================================

    @pytest.mark.parametrize("degrees,expected", [
        (0, "N"),
        (90, "E"),
        (180, "S"),
        (270, "W"),
    ])
    def test_cardinal_directions(self, degrees, expected):
        """Test the four main cardinal directions."""
        assert _format_wind_direction(degrees) == expected

    # =========================================================================
    # Intercardinal (Ordinal) Directions
    # =========================================================================

    @pytest.mark.parametrize("degrees,expected", [
        (45, "NE"),
        (135, "SE"),
        (225, "SW"),
        (315, "NW"),
    ])
    def test_intercardinal_directions(self, degrees, expected):
        """Test the four intercardinal directions."""
        assert _format_wind_direction(degrees) == expected

    # =========================================================================
    # Secondary Intercardinal Directions (16-point compass)
    # =========================================================================

    @pytest.mark.parametrize("degrees,expected", [
        (22.5, "NNE"),
        (67.5, "ENE"),
        (112.5, "ESE"),
        (157.5, "SSE"),
        (202.5, "SSW"),
        (247.5, "WSW"),
        (292.5, "WNW"),
        (337.5, "NNW"),
    ])
    def test_secondary_intercardinal_directions(self, degrees, expected):
        """Test all 16-point compass secondary intercardinal directions."""
        assert _format_wind_direction(degrees) == expected

    # =========================================================================
    # Boundary Tests (edges of direction segments)
    # =========================================================================

    @pytest.mark.parametrize("degrees,expected", [
        # Just below N threshold
        (11.24, "N"),
        # Just above N threshold  
        (11.26, "NNE"),
        # Near E boundary
        (78.74, "ENE"),
        (78.76, "E"),
        # Near S boundary
        (168.74, "SSE"),
        (168.76, "S"),
        # Near W boundary
        (258.74, "WSW"),
        (258.76, "W"),
    ])
    def test_direction_boundaries(self, degrees, expected):
        """Test values near the boundaries between directions."""
        assert _format_wind_direction(degrees) == expected

    # =========================================================================
    # Normalization (values outside 0-360)
    # =========================================================================

    @pytest.mark.parametrize("degrees,expected", [
        (360, "N"),      # Exactly 360 normalizes to 0
        (450, "E"),      # 450 - 360 = 90
        (720, "N"),      # 720 - 720 = 0
        (540, "S"),      # 540 - 360 = 180
        (630, "W"),      # 630 - 360 = 270
    ])
    def test_values_over_360_normalize(self, degrees, expected):
        """Test that values over 360 are normalized correctly."""
        assert _format_wind_direction(degrees) == expected

    @pytest.mark.parametrize("degrees,expected", [
        (-90, "W"),      # -90 + 360 = 270
        (-180, "S"),     # -180 + 360 = 180
        (-270, "E"),     # -270 + 360 = 90
        (-360, "N"),     # -360 + 360 = 0
    ])
    def test_negative_values_normalize(self, degrees, expected):
        """Test that negative values are normalized correctly."""
        # Note: Python's % operator handles negatives, so -90 % 360 = 270
        assert _format_wind_direction(degrees) == expected

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_none_returns_na(self):
        """Test that None input returns 'N/A'."""
        assert _format_wind_direction(None) == "N/A"

    def test_zero_is_north(self):
        """Test that 0 degrees is North."""
        assert _format_wind_direction(0) == "N"
        assert _format_wind_direction(0.0) == "N"

    @pytest.mark.parametrize("degrees", [
        359.99,  # Just before full circle
        0.01,    # Just after zero
        179.99,  # Just before south
        180.01,  # Just after south
    ])
    def test_floating_point_precision(self, degrees):
        """Test that floating point values work correctly."""
        result = _format_wind_direction(degrees)
        assert result in ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                         "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

    # =========================================================================
    # Fixture-Based Tests
    # =========================================================================

    def test_cardinal_directions_fixture(self, cardinal_directions):
        """Test using cardinal_directions fixture from conftest.py."""
        for degrees, expected in cardinal_directions:
            assert _format_wind_direction(degrees) == expected

    def test_intercardinal_directions_fixture(self, intercardinal_directions):
        """Test using intercardinal_directions fixture from conftest.py."""
        for degrees, expected in intercardinal_directions:
            assert _format_wind_direction(degrees) == expected


class TestWindDirectionCompleteness:
    """Tests to verify the wind direction function covers all compass points."""

    def test_all_16_directions_reachable(self):
        """Test that all 16 compass directions can be produced."""
        expected_directions = {
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        }
        
        # Test at 22.5 degree increments (center of each segment)
        actual_directions = set()
        for i in range(16):
            degrees = i * 22.5
            direction = _format_wind_direction(degrees)
            actual_directions.add(direction)
        
        assert actual_directions == expected_directions

    def test_full_rotation_returns_same_direction(self):
        """Test that adding 360 to any angle returns the same direction."""
        for degrees in [0, 45, 90, 135, 180, 225, 270, 315]:
            original = _format_wind_direction(degrees)
            rotated = _format_wind_direction(degrees + 360)
            assert original == rotated, f"Failed at {degrees}°"
