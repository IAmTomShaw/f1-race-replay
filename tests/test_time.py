from src.lib.time import format_time, parse_time_string


def test_format_time_handles_invalid_values():
    assert format_time(None) == "N/A"
    assert format_time(-1) == "N/A"


def test_format_time_formats_seconds():
    assert format_time(86.1234) == "01:26.123"


def test_parse_time_string_supports_common_fastf1_formats():
    assert parse_time_string("0 days 00:01:27.060000") == 87.06
    assert parse_time_string("00:01:26.123000") == 86.123
    assert parse_time_string("01:26.123") == 86.123
    assert parse_time_string("01:26") == 86.0

