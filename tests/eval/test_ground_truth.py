import numpy as np
import pandas as pd
import pytest

from src.eval.ground_truth import build_ground_truth


def make_laps(rows):
    """rows: (driver, lap, position, pit_in, pit_out, track_status)."""
    return pd.DataFrame(
        {
            "Driver": [r[0] for r in rows],
            "LapNumber": [float(r[1]) for r in rows],
            "Position": [np.nan if r[2] is None else float(r[2]) for r in rows],
            "PitInTime": pd.to_timedelta([100.0 if r[3] else np.nan for r in rows], unit="s"),
            "PitOutTime": pd.to_timedelta([120.0 if r[4] else np.nan for r in rows], unit="s"),
            "TrackStatus": [r[5] for r in rows],
        }
    )


@pytest.fixture
def three_driver_laps():
    # VER finishes all 3 laps, pits on lap 2.
    # HAM finishes all 3 laps, lap 2 is under the safety car.
    # LEC retires on lap 3 (Position is NaN on the crash lap).
    return make_laps(
        [
            ("VER", 1, 1, False, False, "1"),
            ("VER", 2, 2, True, False, "1"),
            ("VER", 3, 1, False, False, "1"),
            ("HAM", 1, 2, False, False, "1"),
            ("HAM", 2, 1, False, False, "41"),
            ("HAM", 3, 2, False, False, "1"),
            ("LEC", 1, 3, False, False, "1"),
            ("LEC", 2, 3, False, False, "4"),
            ("LEC", 3, None, False, False, "12"),
        ]
    )


def row(gt, driver, lap):
    match = gt[(gt["driver"] == driver) & (gt["lap"] == lap)]
    assert len(match) == 1
    return match.iloc[0]


def test_one_row_per_driver_lap_with_expected_columns(three_driver_laps):
    gt = build_ground_truth(three_driver_laps)
    assert list(gt.columns) == [
        "driver", "lap", "official_pos", "is_pit", "is_sc_vsc", "is_final", "is_lap1", "excluded_reason",
    ]
    assert len(gt) == 9
    assert gt["lap"].dtype.kind == "i"


def test_official_position_is_copied(three_driver_laps):
    gt = build_ground_truth(three_driver_laps)
    assert row(gt, "VER", 2)["official_pos"] == 2
    assert row(gt, "HAM", 2)["official_pos"] == 1


def test_nan_position_is_kept_but_excluded(three_driver_laps):
    gt = build_ground_truth(three_driver_laps)
    crash = row(gt, "LEC", 3)
    assert np.isnan(crash["official_pos"])
    assert crash["excluded_reason"] == "official_pos_nan"
    assert gt["excluded_reason"].notna().sum() == 1


def test_final_lap_is_last_lap_with_known_position(three_driver_laps):
    gt = build_ground_truth(three_driver_laps)
    finals = gt[gt["is_final"]].set_index("driver")["lap"].to_dict()
    # LEC retired on lap 3, so their last classified lap is 2.
    assert finals == {"HAM": 3, "LEC": 2, "VER": 3}


def test_driver_without_any_position_has_no_final_lap():
    laps = make_laps([("SAR", 1, None, False, False, "1"), ("VER", 1, 1, False, False, "1")])
    gt = build_ground_truth(laps)
    assert not row(gt, "SAR", 1)["is_final"]
    assert row(gt, "VER", 1)["is_final"]


def test_pit_flag_covers_in_lap_and_out_lap():
    laps = make_laps(
        [
            ("VER", 1, 1, False, False, "1"),
            ("VER", 2, 1, True, False, "1"),   # in-lap
            ("VER", 3, 1, False, True, "1"),   # out-lap
            ("VER", 4, 1, False, False, "1"),
        ]
    )
    gt = build_ground_truth(laps)
    assert gt.set_index("lap")["is_pit"].to_dict() == {1: False, 2: True, 3: True, 4: False}


@pytest.mark.parametrize(
    ("status", "expected"),
    [("1", False), ("2", False), ("4", True), ("41", True), ("6", True), ("671", True), ("7", True), ("5", False)],
)
def test_sc_vsc_flag_from_track_status(status, expected):
    gt = build_ground_truth(make_laps([("VER", 5, 1, False, False, status)]))
    assert bool(gt.iloc[0]["is_sc_vsc"]) is expected


def test_missing_track_status_is_not_sc():
    gt = build_ground_truth(make_laps([("VER", 5, 1, False, False, np.nan)]))
    assert not gt.iloc[0]["is_sc_vsc"]


def test_rows_without_lap_number_are_dropped():
    laps = make_laps([("VER", 1, 1, False, False, "1"), ("VER", 2, 1, False, False, "1")])
    laps.loc[1, "LapNumber"] = np.nan
    gt = build_ground_truth(laps)
    assert gt["lap"].tolist() == [1]


def test_duplicate_driver_lap_rows_keep_first():
    laps = make_laps([("VER", 1, 1, False, False, "1"), ("VER", 1, 5, False, False, "1")])
    gt = build_ground_truth(laps)
    assert len(gt) == 1
    assert gt.iloc[0]["official_pos"] == 1


def test_missing_columns_raise_clear_error():
    with pytest.raises(ValueError, match="Position"):
        build_ground_truth(pd.DataFrame({"Driver": ["VER"], "LapNumber": [1.0]}))
