"""Tests for the leaderboard ordering helpers (issue #309).

These use small synthetic frames rather than live FastF1 data so they run
offline and deterministically.
"""

import pandas as pd

from src.lib.leaderboard import official_finishing_order, order_leaderboard_codes


def _results(rows):
    """Build a session.results-like DataFrame from (abbr, position, classified,
    status) tuples."""
    return pd.DataFrame(
        [
            {
                "Abbreviation": abbr,
                "Position": position,
                "ClassifiedPosition": classified,
                "Status": status,
            }
            for abbr, position, classified, status in rows
        ]
    )


def test_official_order_follows_position_not_row_order():
    # Rows deliberately out of Position order; a lapped car and a retirement
    # are classified behind the finishers.
    results = _results(
        [
            ("HAM", 3.0, "3", "Finished"),
            ("VER", 1.0, "1", "Finished"),
            ("ALO", 5.0, "5", "Lapped"),
            ("NOR", 2.0, "2", "Finished"),
            ("PIA", 4.0, "R", "Collision"),
        ]
    )
    assert official_finishing_order(results) == ["VER", "NOR", "HAM", "PIA", "ALO"]


def test_official_order_puts_unclassified_positions_last():
    results = _results(
        [
            ("VER", 1.0, "1", "Finished"),
            ("SAR", float("nan"), "R", "Accident"),
            ("NOR", 2.0, "2", "Finished"),
        ]
    )
    assert official_finishing_order(results) == ["VER", "NOR", "SAR"]


def test_official_order_empty_or_none():
    assert official_finishing_order(None) == []
    assert official_finishing_order(pd.DataFrame()) == []


def test_live_order_is_kept_while_race_running():
    live = ["VER", "NOR", "HAM"]
    official = ["HAM", "VER", "NOR"]
    assert order_leaderboard_codes(live, official, race_finished=False) == live


def test_official_order_used_once_race_finished():
    live = ["VER", "NOR", "HAM"]  # live on-track proxy
    official = ["HAM", "VER", "NOR"]  # e.g. after a penalty shuffles the order
    assert order_leaderboard_codes(live, official, race_finished=True) == official


def test_finished_without_official_order_keeps_live():
    live = ["VER", "NOR", "HAM"]
    assert order_leaderboard_codes(live, [], race_finished=True) == live


def test_driver_missing_from_official_is_appended_not_dropped():
    live = ["VER", "NOR", "HAM"]
    official = ["NOR", "VER"]  # HAM missing from classification for some reason
    assert order_leaderboard_codes(live, official, race_finished=True) == [
        "NOR",
        "VER",
        "HAM",
    ]


def test_official_code_absent_from_live_is_ignored():
    live = ["VER", "NOR"]
    official = ["NOR", "GONE", "VER"]
    assert order_leaderboard_codes(live, official, race_finished=True) == ["NOR", "VER"]
