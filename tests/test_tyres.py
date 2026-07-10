"""
Unit tests for src/lib/tyres.py

Tests the tyre compound conversion functions with comprehensive coverage
of all F1 tyre compounds, case insensitivity, and edge cases.
"""
import pytest
from src.lib.tyres import get_tyre_compound_int, get_tyre_compound_str, tyre_compounds_ints


class TestGetTyreCompoundInt:
    """Tests for get_tyre_compound_int() that converts compound names to integers."""

    # =========================================================================
    # Standard Compounds
    # =========================================================================

    @pytest.mark.parametrize("compound,expected", [
        ("SOFT", 0),
        ("MEDIUM", 1),
        ("HARD", 2),
        ("INTERMEDIATE", 3),
        ("WET", 4),
    ])
    def test_standard_compounds_uppercase(self, compound, expected):
        """Test all standard F1 tyre compounds in uppercase."""
        assert get_tyre_compound_int(compound) == expected

    # =========================================================================
    # Case Insensitivity
    # =========================================================================

    @pytest.mark.parametrize("compound,expected", [
        ("soft", 0),
        ("Soft", 0),
        ("SOFT", 0),
        ("sOfT", 0),
        ("medium", 1),
        ("Medium", 1),
        ("MEDIUM", 1),
        ("hard", 2),
        ("Hard", 2),
        ("HARD", 2),
        ("intermediate", 3),
        ("Intermediate", 3),
        ("INTERMEDIATE", 3),
        ("wet", 4),
        ("Wet", 4),
        ("WET", 4),
    ])
    def test_case_insensitivity(self, compound, expected):
        """Test that compound names are case insensitive."""
        assert get_tyre_compound_int(compound) == expected

    # =========================================================================
    # Edge Cases and Invalid Input
    # =========================================================================

    @pytest.mark.parametrize("invalid_compound", [
        "UNKNOWN",
        "SUPERSOFT",
        "ULTRASOFT",
        "HYPERSOFT",
        "",
        "S",
        "M",
        "H",
        "I",
        "W",
        "SOFTT",
        " SOFT",
        "SOFT ",
        "  ",
    ])
    def test_invalid_compound_returns_minus_one(self, invalid_compound):
        """Test that unknown compounds return -1."""
        assert get_tyre_compound_int(invalid_compound) == -1

    # =========================================================================
    # Fixture-Based Tests
    # =========================================================================

    def test_all_tyre_compounds_fixture(self, all_tyre_compounds):
        """Test using the all_tyre_compounds fixture."""
        for compound, expected in all_tyre_compounds.items():
            assert get_tyre_compound_int(compound) == expected

    def test_case_variations_fixture(self, tyre_compound_case_variations):
        """Test using the case variations fixture."""
        for compound, expected in tyre_compound_case_variations:
            assert get_tyre_compound_int(compound) == expected


class TestGetTyreCompoundStr:
    """Tests for get_tyre_compound_str() that converts integers to compound names."""

    # =========================================================================
    # Standard Reverse Lookup
    # =========================================================================

    @pytest.mark.parametrize("compound_int,expected", [
        (0, "SOFT"),
        (1, "MEDIUM"),
        (2, "HARD"),
        (3, "INTERMEDIATE"),
        (4, "WET"),
    ])
    def test_valid_integers(self, compound_int, expected):
        """Test reverse lookup for valid integer values."""
        assert get_tyre_compound_str(compound_int) == expected

    # =========================================================================
    # Invalid Integers
    # =========================================================================

    @pytest.mark.parametrize("invalid_int", [
        -1,
        -100,
        5,
        10,
        99,
        1000,
    ])
    def test_invalid_integer_returns_unknown(self, invalid_int):
        """Test that invalid integers return 'UNKNOWN'."""
        assert get_tyre_compound_str(invalid_int) == "UNKNOWN"

    # =========================================================================
    # Fixture-Based Tests
    # =========================================================================

    def test_all_tyre_compounds_reverse(self, all_tyre_compounds):
        """Test reverse lookup using the fixture."""
        for compound, int_value in all_tyre_compounds.items():
            assert get_tyre_compound_str(int_value) == compound


class TestTyreCompoundConsistency:
    """Tests for bidirectional consistency between the conversion functions."""

    @pytest.mark.parametrize("compound", ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"])
    def test_int_to_str_to_int_roundtrip(self, compound):
        """Test that str -> int -> str returns the original compound."""
        int_value = get_tyre_compound_int(compound)
        str_value = get_tyre_compound_str(int_value)
        assert str_value == compound

    @pytest.mark.parametrize("int_value", [0, 1, 2, 3, 4])
    def test_str_to_int_to_str_roundtrip(self, int_value):
        """Test that int -> str -> int returns the original integer."""
        str_value = get_tyre_compound_str(int_value)
        int_result = get_tyre_compound_int(str_value)
        assert int_result == int_value

    def test_dictionary_integrity(self):
        """Test that the internal mapping dictionary is complete and unique."""
        # All expected compounds exist
        expected_compounds = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"}
        assert set(tyre_compounds_ints.keys()) == expected_compounds
        
        # All values are unique
        values = list(tyre_compounds_ints.values())
        assert len(values) == len(set(values)), "Duplicate values in tyre_compounds_ints"
        
        # Values are 0-4
        assert set(values) == {0, 1, 2, 3, 4}


class TestTyreCompoundEdgeCases:
    """Additional edge case tests for tyre compound functions."""

    def test_soft_is_fastest_zero(self):
        """Test that SOFT (fastest dry compound) is 0."""
        assert get_tyre_compound_int("SOFT") == 0

    def test_wet_is_highest_value(self):
        """Test that WET has the highest integer value."""
        all_ints = [get_tyre_compound_int(c) for c in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]]
        assert get_tyre_compound_int("WET") == max(all_ints)

    def test_slick_tyres_ordering(self):
        """Test that slick tyres (SOFT, MEDIUM, HARD) are in correct order."""
        soft = get_tyre_compound_int("SOFT")
        medium = get_tyre_compound_int("MEDIUM")
        hard = get_tyre_compound_int("HARD")
        assert soft < medium < hard

    def test_rain_tyres_are_higher(self):
        """Test that rain tyres have higher values than slicks."""
        hard = get_tyre_compound_int("HARD")
        inter = get_tyre_compound_int("INTERMEDIATE")
        wet = get_tyre_compound_int("WET")
        assert hard < inter < wet
