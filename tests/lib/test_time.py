import pytest

from src.lib.time import format_time, parse_time_string


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00.000"),
        (1.234, "00:01.234"),
        (61.5, "01:01.500"),
        (3661.25, "61:01.250"),
    ],
)
def test_format_time_valid_values(seconds, expected):
    assert format_time(seconds) == expected


@pytest.mark.parametrize("seconds", [None, -1, -10.5])
def test_format_time_invalid_values(seconds):
    assert format_time(seconds) == "N/A"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("00:01:26:123000", 86.123),
        ("00:01:26.123000", 86.123),
        ("01:26.123", 86.123),
        ("01:26", 86.0),
        ("0 days 00:01:27.060000", 87.06),
        ("00:01:26.123000 extra text", 86.123),
    ],
)
def test_parse_time_string_supported_formats(value, expected):
    assert parse_time_string(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-time",
        "1",
        "::::",
        None,
    ],
)
def test_parse_time_string_invalid_values(value):
    assert parse_time_string(value) is None
