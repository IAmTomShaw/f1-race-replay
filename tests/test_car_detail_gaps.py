import pytest

pytest.importorskip("PySide6")

from src.insights.car_detail_window import CarDetailWindow


def drivers(**positions):
    return {code: {"position": pos, "dist": 1000.0 - pos * 50} for code, pos in positions.items()}


def test_leader_has_no_car_ahead_and_last_has_no_car_behind():
    d = drivers(VER=1, NOR=2, RUS=3)
    assert CarDetailWindow._neighbours(d, "VER") == (None, "NOR")
    assert CarDetailWindow._neighbours(d, "RUS") == ("NOR", None)


def test_gaps_in_position_numbers_still_find_the_neighbour():
    d = drivers(VER=1, NOR=4, RUS=7)          # e.g. retired cars removed
    assert CarDetailWindow._neighbours(d, "NOR") == ("VER", "RUS")


def test_cars_without_a_valid_position_are_ignored():
    d = drivers(VER=1, NOR=2)
    d["ALB"] = {"position": None, "dist": 0.0}
    assert CarDetailWindow._neighbours(d, "NOR") == ("VER", None)
    assert CarDetailWindow._neighbours(d, "ALB") == (None, None)


def test_gap_text_names_the_neighbour():
    d = drivers(VER=1, NOR=2)
    text = CarDetailWindow._gap_text(d, "NOR", "VER", 55.0, 4300.0)
    assert text.endswith("(VER)") and text[0].isdigit()
