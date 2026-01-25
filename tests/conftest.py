"""
Pytest configuration and shared fixtures for f1-race-replay tests.

This module provides common fixtures and test data used across multiple test modules.
"""
import pytest


# =============================================================================
# Time String Test Data Fixtures
# =============================================================================

@pytest.fixture
def valid_time_strings():
    """
    Collection of valid time string formats with their expected parsed values in seconds.
    
    Returns:
        list of tuples: (input_string, expected_seconds)
    """
    return [
        ("01:26.123", 86.123),           # MM:SS.micro
        ("01:26", 86.0),                  # MM:SS (no microseconds)
        ("00:01:26.123000", 86.123),     # HH:MM:SS.micro
        ("00:01:26:123000", 86.123),     # HH:MM:SS:micro (colon separator)
        ("00:00.000", 0.0),              # Zero
        ("00:00", 0.0),                  # Zero without micro
        ("59:59.999", 3599.999),         # Max MM:SS
        ("01:00.000", 60.0),             # Exact minute
        ("00:30.500", 30.5),             # Half minute
    ]


@pytest.fixture
def timedelta_format_strings():
    """
    Time strings in pandas Timedelta format.
    
    Note: Current parse_time_string implementation discards the day count,
    only parsing the time portion after 'days '.
    
    Returns:
        list of tuples: (input_string, expected_seconds)
    """
    return [
        ("0 days 00:01:27.060000", 87.06),
        ("0 days 00:00:30.123456", 30.123),
        ("0 days 01:30:00.000000", 5400.0),
        # Note: 1 days -> returns 0.0 because days are discarded (known limitation)
        ("1 days 00:00:00.000000", 0.0),
    ]


@pytest.fixture
def invalid_time_strings():
    """
    Collection of invalid time strings that should return None when parsed.
    
    Returns:
        list of strings
    """
    return [
        "",           # Empty string
        "   ",        # Whitespace only
        "invalid",    # Non-time string
        "abc:def",    # Invalid format
        ":",          # Just separator
    ]


# =============================================================================
# Tyre Compound Test Data Fixtures
# =============================================================================

@pytest.fixture
def all_tyre_compounds():
    """
    All valid F1 tyre compounds with their integer mappings.
    
    Returns:
        dict: compound_name -> integer_value
    """
    return {
        "SOFT": 0,
        "MEDIUM": 1,
        "HARD": 2,
        "INTERMEDIATE": 3,
        "WET": 4,
    }


@pytest.fixture
def tyre_compound_case_variations():
    """
    Different case variations of tyre compound names.
    
    Returns:
        list of tuples: (input, expected_int)
    """
    return [
        ("SOFT", 0),
        ("soft", 0),
        ("Soft", 0),
        ("MEDIUM", 1),
        ("medium", 1),
        ("Medium", 1),
        ("HARD", 2),
        ("hard", 2),
        ("INTERMEDIATE", 3),
        ("intermediate", 3),
        ("WET", 4),
        ("wet", 4),
    ]


# =============================================================================
# Wind Direction Test Data Fixtures
# =============================================================================

@pytest.fixture
def cardinal_directions():
    """
    Cardinal wind directions (N, E, S, W) with their degree values.
    
    Returns:
        list of tuples: (degrees, expected_direction)
    """
    return [
        (0, "N"),
        (90, "E"),
        (180, "S"),
        (270, "W"),
    ]


@pytest.fixture
def intercardinal_directions():
    """
    Intercardinal wind directions (NE, SE, SW, NW) with their degree values.
    
    Returns:
        list of tuples: (degrees, expected_direction)
    """
    return [
        (45, "NE"),
        (135, "SE"),
        (225, "SW"),
        (315, "NW"),
    ]


@pytest.fixture
def secondary_intercardinal_directions():
    """
    Secondary intercardinal directions (16-point compass: NNE, ENE, ESE, etc.).
    
    Returns:
        list of tuples: (degrees, expected_direction)
    """
    return [
        (22.5, "NNE"),
        (67.5, "ENE"),
        (112.5, "ESE"),
        (157.5, "SSE"),
        (202.5, "SSW"),
        (247.5, "WSW"),
        (292.5, "WNW"),
        (337.5, "NNW"),
    ]
