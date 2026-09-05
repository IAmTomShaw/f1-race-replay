import pytest

from src.lib.tyres import get_tyre_compound_int, get_tyre_compound_str


@pytest.mark.parametrize(
    ("compound", "expected"),
    [
        ("SOFT", 0),
        ("MEDIUM", 1),
        ("HARD", 2),
        ("INTERMEDIATE", 3),
        ("WET", 4),
    ],
)
def test_get_tyre_compound_int_known_compounds(compound, expected):
    assert get_tyre_compound_int(compound) == expected


@pytest.mark.parametrize(
    ("compound", "expected"),
    [
        ("soft", 0),
        ("medium", 1),
        ("hard", 2),
        ("intermediate", 3),
        ("wet", 4),
    ],
)
def test_get_tyre_compound_int_is_case_insensitive(compound, expected):
    assert get_tyre_compound_int(compound) == expected


@pytest.mark.parametrize(
    "compound",
    [
        "UNKNOWN",
        "SUPERSOFT",
        "",
    ],
)
def test_get_tyre_compound_int_unknown_compounds(compound):
    assert get_tyre_compound_int(compound) == -1


@pytest.mark.parametrize(
    ("compound_id", "expected"),
    [
        (0, "SOFT"),
        (1, "MEDIUM"),
        (2, "HARD"),
        (3, "INTERMEDIATE"),
        (4, "WET"),
    ],
)
def test_get_tyre_compound_str_known_ids(compound_id, expected):
    assert get_tyre_compound_str(compound_id) == expected


@pytest.mark.parametrize(
    "compound_id",
    [
        -1,
        5,
        999,
    ],
)
def test_get_tyre_compound_str_unknown_ids(compound_id):
    assert get_tyre_compound_str(compound_id) == "UNKNOWN"
