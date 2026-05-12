from src.lib.tyres import get_tyre_compound_int, get_tyre_compound_str


def test_known_tyre_compounds_round_trip():
    for compound in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]:
        compound_id = get_tyre_compound_int(compound)
        assert get_tyre_compound_str(compound_id) == compound


def test_unknown_tyre_compounds_are_stable():
    assert get_tyre_compound_int("not-a-compound") == -1
    assert get_tyre_compound_str(-1) == "UNKNOWN"

