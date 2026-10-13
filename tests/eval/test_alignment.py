import numpy as np
import pandas as pd
import pytest

from src.eval.alignment import (
    build_eval_table,
    find_lap_crossings,
    sample_computed_positions,
)
from src.eval.ground_truth import build_ground_truth


def make_frames(laps_by_driver, positions_by_driver=None, dt=0.5):
    """Synthetic replay frames. A value of None means the driver is missing from that frame."""
    n = len(next(iter(laps_by_driver.values())))
    frames = []
    for i in range(n):
        drivers = {}
        for code, laps in laps_by_driver.items():
            if laps[i] is None:
                continue
            pos = positions_by_driver[code][i] if positions_by_driver else None
            drivers[code] = {"lap": laps[i], "position": pos}
        leader_lap = max((d["lap"] for d in drivers.values()), default=1)
        frames.append({"t": round(i * dt, 3), "lap": leader_lap, "drivers": drivers})
    return frames


def sample(computed, driver, lap):
    match = computed[(computed["driver"] == driver) & (computed["lap"] == lap)]
    assert len(match) == 1, f"expected one row for {driver} lap {lap}, got {len(match)}"
    return match.iloc[0]


# ---------- find_lap_crossings ----------

def test_crossing_is_first_frame_on_next_lap():
    frames = make_frames({"VER": [1, 1, 2, 2, 3, 3]})
    assert find_lap_crossings(frames, "VER") == {1: 2, 2: 4}


def test_crossing_skips_frames_where_driver_is_missing():
    frames = make_frames({"HAM": [1, None, None, 2, 2], "VER": [1, 1, 1, 1, 1]})
    assert find_lap_crossings(frames, "HAM") == {1: 3}


def test_skipped_lap_has_no_crossing():
    # Lap 2 is never seen: lap 1 ends at the jump, lap 2 gets nothing.
    frames = make_frames({"LEC": [1, 1, 3, 3]})
    assert find_lap_crossings(frames, "LEC") == {1: 2}


def test_unknown_driver_has_no_crossings():
    frames = make_frames({"VER": [1, 2, 3]})
    assert find_lap_crossings(frames, "XXX") == {}


def test_lap_value_going_backwards_is_ignored():
    frames = make_frames({"VER": [1, 2, 1, 2, 3]})
    assert find_lap_crossings(frames, "VER") == {1: 1, 2: 4}


# ---------- sample_computed_positions ----------

@pytest.fixture
def race():
    # dt = 0.5 s, so an offset of 1.0 s is 2 frames.
    laps = {
        "VER": [1, 1, 2, 2, 2, 2, 3, 3, 3, 3],
        "HAM": [1, 1, 1, 2, 2, 2, 2, 3, 3, 3],
        "LEC": [1, 1, 1, 1, 2, 2, 2, 2, 3, 3],
    }
    positions = {
        "VER": [1, 1, 1, 1, 1, 2, 2, 2, 2, 1],
        "HAM": [2, 2, 2, 2, 2, 1, 1, 1, 1, 2],
        "LEC": [3] * 10,
    }
    return make_frames(laps, positions)


def test_zero_offset_samples_at_the_crossing(race):
    computed = sample_computed_positions(race, offset_s=0.0)
    row = sample(computed, "VER", 1)
    assert row["frame_idx"] == 2
    assert row["method"] == "crossing"
    assert row["computed_pos"] == 1


def test_offset_moves_sample_forward_in_time(race):
    computed = sample_computed_positions(race, offset_s=1.0)
    # VER crosses into lap 2 at frame 2 (t=1.0) -> sample at t=2.0 -> frame 4.
    assert sample(computed, "VER", 1)["frame_idx"] == 4
    # VER crosses into lap 3 at frame 6 (t=3.0) -> sample at t=4.0 -> frame 8, where VER is P2.
    row = sample(computed, "VER", 2)
    assert row["frame_idx"] == 8
    assert row["computed_pos"] == 2


def test_offset_is_clipped_to_last_frame(race):
    computed = sample_computed_positions(race, offset_s=100.0)
    assert sample(computed, "LEC", 2)["frame_idx"] == len(race) - 1


def test_last_lap_uses_last_frame(race):
    computed = sample_computed_positions(race, offset_s=1.0)
    for driver, expected_pos in [("VER", 1), ("HAM", 2), ("LEC", 3)]:
        row = sample(computed, driver, 3)
        assert row["method"] == "last_frame"
        assert row["frame_idx"] == len(race) - 1
        assert row["computed_pos"] == expected_pos


def test_one_row_per_driver_lap(race):
    computed = sample_computed_positions(race)
    assert len(computed) == 9
    assert not computed.duplicated(["driver", "lap"]).any()


def test_missing_driver_at_sample_frame_steps_back():
    frames = make_frames(
        {"VER": [1, 2, 2, None, 2], "HAM": [1, 1, 1, 1, 1]},
        {"VER": [1, 1, 1, None, 1], "HAM": [2, 2, 2, 2, 2]},
    )
    computed = sample_computed_positions(frames, offset_s=1.0)
    # Crossing at frame 1 (t=0.5) -> target t=1.5 -> frame 3, VER missing -> frame 2.
    assert sample(computed, "VER", 1)["frame_idx"] == 2


def test_retired_driver_last_lap_uses_last_frame_they_appear_in():
    frames = make_frames(
        {"VER": [1, 2, 2, 2, 2], "SAR": [1, 2, 2, None, None]},
        {"VER": [1, 1, 1, 1, 1], "SAR": [2, 2, 2, None, None]},
    )
    computed = sample_computed_positions(frames, offset_s=0.0)
    row = sample(computed, "SAR", 2)
    assert row["method"] == "last_frame"
    assert row["frame_idx"] == 2


def test_custom_position_fn_is_used(race):
    def everyone_p9(frame):
        return {code: 9 for code in frame["drivers"]}

    computed = sample_computed_positions(race, position_fn=everyone_p9)
    assert (computed["computed_pos"] == 9).all()


def test_negative_offset_is_rejected(race):
    with pytest.raises(ValueError):
        sample_computed_positions(race, offset_s=-1.0)


def test_empty_frames_give_empty_table():
    computed = sample_computed_positions([])
    assert computed.empty
    assert list(computed.columns) == ["driver", "lap", "computed_pos", "frame_idx", "method"]


# ---------- build_eval_table ----------

def make_laps(rows):
    """rows: (driver, lap, position)."""
    return pd.DataFrame(
        {
            "Driver": [r[0] for r in rows],
            "LapNumber": [float(r[1]) for r in rows],
            "Position": [np.nan if r[2] is None else float(r[2]) for r in rows],
            "PitInTime": pd.to_timedelta([np.nan] * len(rows), unit="s"),
            "PitOutTime": pd.to_timedelta([np.nan] * len(rows), unit="s"),
            "TrackStatus": ["1"] * len(rows),
        }
    )


def test_eval_table_joins_and_marks_exclusions(race):
    laps = make_laps(
        [
            ("VER", 1, 1), ("VER", 2, 2), ("VER", 3, 1),
            ("HAM", 1, 2), ("HAM", 2, 1), ("HAM", 3, 2),
            ("LEC", 1, 3), ("LEC", 2, None), ("LEC", 3, 3),
            ("BOT", 1, 4),  # in the official data but not in the replay
        ]
    )
    gt = build_ground_truth(laps)
    table = build_eval_table(gt, sample_computed_positions(race, offset_s=1.0))

    assert len(table) == len(gt)
    reasons = table.set_index(["driver", "lap"])["excluded_reason"]
    assert reasons[("BOT", 1)] == "no_crossing"
    assert reasons[("LEC", 2)] == "official_pos_nan"  # first reason wins
    assert reasons.notna().sum() == 2

    ver2 = table[(table["driver"] == "VER") & (table["lap"] == 2)].iloc[0]
    assert ver2["computed_pos"] == 2
    assert ver2["error"] == 0
    assert set(table["segment"]) <= {"final", "lap1", "pit", "sc_vsc", "normal"}
    assert table.set_index(["driver", "lap"])["segment"][("VER", 3)] == "final"


def test_eval_table_rejects_duplicate_computed_rows(race):
    gt = build_ground_truth(make_laps([("VER", 1, 1)]))
    computed = sample_computed_positions(race)
    computed = pd.concat([computed, computed])
    with pytest.raises(pd.errors.MergeError):
        build_eval_table(gt, computed)
