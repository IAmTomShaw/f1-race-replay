import numpy as np
import pandas as pd
import pytest

from src.eval.alignment import (
    find_lap_crossings,
)


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
