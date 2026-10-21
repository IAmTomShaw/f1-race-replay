import pytest

from src.lib.car_state import (
    AI,
    EST,
    LIVE,
    TAG_HELP,
    average_speed_mps,
    brake_fraction,
    compound_name,
    drs_state,
    estimate_fuel_kg,
    estimate_gap_s,
    format_lap_time,
    format_laps_left,
    last_completed_lap,
)


def test_every_tag_is_explained():
    assert set(TAG_HELP) == {LIVE, EST, AI}


@pytest.mark.parametrize("value, expected", [
    (0, "OFF"), (1, "OFF"), (8, "ELIGIBLE"), (10, "OPEN"), (12, "OPEN"), (14, "OPEN"),
    (None, "OFF"), ("x", "OFF"),
])
def test_drs_state(value, expected):
    assert drs_state(value) == expected


def test_compound_name():
    assert compound_name(0.0) == "SOFT"
    assert compound_name(3) == "INTERMEDIATE"
    assert compound_name(-1) == "UNKNOWN"
    assert compound_name(None) == "UNKNOWN"


def test_brake_fraction_handles_both_scales():
    assert brake_fraction(1.0) == 1.0
    assert brake_fraction(0) == 0.0
    assert brake_fraction(100) == 1.0
    assert brake_fraction(None) == 0.0


class TestFuel:
    def test_full_at_the_start_and_reserve_at_the_flag(self):
        assert estimate_fuel_kg(1, 0.0, 50) == pytest.approx(110.0)
        assert estimate_fuel_kg(50, 1.0, 50) == pytest.approx(1.0)

    def test_burns_evenly(self):
        half = estimate_fuel_kg(26, 0.0, 50)
        assert half == pytest.approx(110.0 - 109.0 / 2)

    def test_bad_input(self):
        assert estimate_fuel_kg(None, 0.0, 50) is None
        assert estimate_fuel_kg(3, 0.2, 0) is None


class TestGaps:
    def test_average_speed(self):
        assert average_speed_mps(4361.0, 76.0) == pytest.approx(57.38, abs=0.01)
        assert average_speed_mps(4361.0, 0) is None

    def test_gap_seconds(self):
        assert estimate_gap_s(57.4, 57.4) == pytest.approx(1.0)
        assert estimate_gap_s(10, 0) is None
        assert estimate_gap_s(None, 50) is None


def test_last_completed_lap_skips_current_and_invalid():
    entries = [
        {"lap": 1, "time_s": 90.0},
        {"lap": 2, "time_s": 78.1},
        {"lap": 3, "time_s": -1.0},   # no time recorded
        {"lap": 4, "time_s": 77.5},   # current lap: not complete yet
    ]
    assert last_completed_lap(entries, 4)["lap"] == 2
    assert last_completed_lap(entries, 1) is None
    assert last_completed_lap(None, 4) is None


def test_format_lap_time():
    assert format_lap_time(75.123) == "1:15.123"
    assert format_lap_time(59.9) == "0:59.900"
    assert format_lap_time(None) == "-"
    assert format_lap_time(-1) == "-"


def test_format_laps_left():
    assert format_laps_left(12.4, 30) == "≈ 12 laps"
    assert format_laps_left(80, 30) == "Lasts to the finish"
    assert format_laps_left(0.2, 30) == "Worn now"
    assert format_laps_left(None, 30) == "-"
