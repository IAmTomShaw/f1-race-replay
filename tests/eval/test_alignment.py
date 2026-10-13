import numpy as np
import pandas as pd
import pytest

from src.eval.alignment import (
    EVAL_COLUMNS,
    build_eval_table,
    compare_lap_times,
    crossing_timing_errors,
    find_lap_crossings,
    freeze_index,
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


def race_frames(laps_by_driver, dist_by_driver, dt=0.5):
    """Frames like get_race_telemetry builds them: every driver in every frame,
    positions from sorting by (lap, dist), cars held still after their data ends."""
    n = len(next(iter(laps_by_driver.values())))
    frames = []
    for i in range(n):
        cars = {code: {"lap": laps_by_driver[code][i], "dist": dist_by_driver[code][i]} for code in laps_by_driver}
        order = sorted(cars, key=lambda c: (cars[c]["lap"], cars[c]["dist"]), reverse=True)
        for pos, code in enumerate(order, start=1):
            cars[code]["position"] = pos
        frames.append({"t": round(i * dt, 3), "lap": cars[order[0]]["lap"], "drivers": cars})
    return frames


@pytest.fixture
def garage_retirement():
    # SAR retires into the garage after lap 2 (frozen from frame 3). LEC is behind SAR
    # at that moment but keeps going, so by the end of the race LEC is ahead of SAR.
    laps = {
        "VER": [1, 1, 2, 2, 3, 3, 4, 4, 4, 4],
        "HAM": [1, 1, 2, 2, 3, 3, 4, 4, 4, 4],
        "SAR": [1, 1, 2, 2, 2, 2, 2, 2, 2, 2],
        "LEC": [1, 1, 1, 2, 2, 2, 3, 3, 3, 3],
    }
    dists = {
        "VER": [0, 1, 2, 3, 4, 5, 6, 7, 7, 7],  # finishes at frame 7
        "HAM": [0, 0.9, 1.9, 2.9, 3.9, 4.9, 5.9, 6.9, 7, 7],  # finishes at frame 8
        "SAR": [0, 0.8, 1.8, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5],
        "LEC": [0, 0.5, 1.0, 1.5, 2.0, 2.6, 3.5, 4.5, 5.5, 6.0],  # lapped, still moving at the end
    }
    return race_frames(laps, dists)


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


def test_freeze_index_finds_when_the_car_stops(garage_retirement):
    last = len(garage_retirement) - 1
    assert freeze_index(garage_retirement, "SAR", last) == 3
    assert freeze_index(garage_retirement, "VER", last) == 7
    assert freeze_index(garage_retirement, "LEC", last) == last


def test_garage_retirement_is_read_when_data_ends_not_at_race_end(garage_retirement):
    computed = sample_computed_positions(garage_retirement, offset_s=0.0)
    row = sample(computed, "SAR", 2)
    assert row["method"] == "data_end"
    assert row["event_idx"] == 3
    assert row["computed_pos"] == 3  # P3 when they stopped; the last frame would say P4
    assert garage_retirement[-1]["drivers"]["SAR"]["position"] == 4


def test_finishers_and_lapped_finishers_use_last_frame(garage_retirement):
    computed = sample_computed_positions(garage_retirement, offset_s=0.0)
    last = len(garage_retirement) - 1
    for driver, lap in [("VER", 4), ("HAM", 4), ("LEC", 3)]:
        row = sample(computed, driver, lap)
        assert row["method"] == "last_frame"
        assert row["frame_idx"] == last
    assert sample(computed, "VER", 4)["event_idx"] == 7


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
    assert list(computed.columns) == ["driver", "lap", "computed_pos", "frame_idx", "event_idx", "method"]


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


def test_eval_table_has_documented_column_order(race):
    gt = build_ground_truth(make_laps([("VER", 1, 1)]))
    table = build_eval_table(gt, sample_computed_positions(race))
    assert list(table.columns) == EVAL_COLUMNS
    assert table["timing_error_s"].isna().all()  # no timing given


# ---------- crossing_timing_errors ----------

def laps_with_times(frames, shift_s=100.0, offsets=None):
    """Official laps whose Time is the replay crossing time plus a constant shift."""
    offsets = offsets or {}
    rows = []
    computed = sample_computed_positions(frames, offset_s=0.0)
    for r in computed.itertuples(index=False):
        end_s = frames[r.event_idx]["t"] + shift_s + offsets.get((r.driver, r.lap), 0.0)
        rows.append((r.driver, float(r.lap), float(r.computed_pos), end_s))
    laps = make_laps([(d, l, p) for d, l, p, _ in rows])
    laps["Time"] = pd.to_timedelta([e for *_, e in rows], unit="s")
    return laps


def test_timing_errors_are_zero_when_crossings_match(race):
    laps = laps_with_times(race)
    timing = crossing_timing_errors(race, sample_computed_positions(race), laps)
    assert len(timing) == 9
    assert timing["timing_error_s"].abs().max() == pytest.approx(0.0)


def test_mistimed_crossing_is_excluded(race):
    laps = laps_with_times(race, offsets={("HAM", 2): 5.0})  # official lap end 5 s later
    computed = sample_computed_positions(race)
    timing = crossing_timing_errors(race, computed, laps)
    errors = timing.set_index(["driver", "lap"])["timing_error_s"]
    assert errors[("HAM", 2)] == pytest.approx(-5.0)  # the median shift ignores the outlier
    assert errors.drop(("HAM", 2)).abs().max() == pytest.approx(0.0)

    table = build_eval_table(build_ground_truth(laps), computed, timing)
    reasons = table.set_index(["driver", "lap"])["excluded_reason"]
    assert reasons[("HAM", 2)] == "crossing_mistimed"
    assert reasons.notna().sum() == 1


def test_timing_errors_need_official_time_column(race):
    laps = make_laps([("VER", 1, 1)])
    assert crossing_timing_errors(race, sample_computed_positions(race), laps).empty


# ---------- compare_lap_times ----------

def test_replay_lap_times_match_official_lap_times():
    # Crossings at frames 4 (t=2.0) and 8 (t=4.0): lap 2 lasted 2.0 s in the replay.
    frames = make_frames({"VER": [1, 1, 1, 1, 2, 2, 2, 2, 3]})
    laps = pd.DataFrame(
        {
            "Driver": ["VER", "VER", "VER"],
            "LapNumber": [1.0, 2.0, 3.0],
            "LapTime": pd.to_timedelta([np.nan, 2.1, np.nan], unit="s"),
        }
    )
    check = compare_lap_times(frames, laps, "VER")
    assert check["lap"].tolist() == [2]
    assert check["replay_lap_time_s"].iloc[0] == pytest.approx(2.0)
    assert check["diff_s"].iloc[0] == pytest.approx(-0.1)
