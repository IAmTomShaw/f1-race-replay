"""Read the replay's computed positions at the moments the official ones are measured.

The official ``Position`` for lap N is taken when the driver crosses the line at
the end of lap N. In the replay, that is the first frame where the driver's
``lap`` value reaches N+1. We read the replay position slightly after that frame
(``offset_s``) so that rounding noise right on the line does not decide the result.
"""

from typing import Callable, Optional

import numpy as np
import pandas as pd

from src.eval.ground_truth import label_segments

PositionFn = Callable[[dict], dict]

COMPUTED_COLUMNS = ["driver", "lap", "computed_pos", "frame_idx", "method"]


def frame_positions(frame: dict) -> dict:
    """Default position source: the ``position`` that ``get_race_telemetry`` stored in the frame."""
    return {code: d.get("position") for code, d in frame.get("drivers", {}).items()}


def driver_codes(frames: list) -> list:
    """Every driver code that appears in at least one frame, sorted."""
    codes = set()
    for frame in frames:
        codes.update(frame.get("drivers", {}).keys())
    return sorted(codes)


def find_lap_crossings(frames: list, driver: str) -> dict:
    """Map lap N to the index of the first frame where the driver's lap is >= N+1.

    Only laps the driver was actually seen on get a crossing. If the replay jumps
    from lap 3 to lap 5, lap 3 ends at the jump and lap 4 has no crossing.
    Frames without the driver are skipped.
    """
    crossings = {}
    current = None
    for idx, frame in enumerate(frames):
        car = frame.get("drivers", {}).get(driver)
        if car is None or car.get("lap") is None:
            continue
        lap = int(car["lap"])
        if current is None:
            current = lap
        elif lap > current:
            crossings[current] = idx
            current = lap
    return crossings


def last_seen(frames: list, driver: str):
    """Return (frame_idx, lap) of the last frame that contains the driver, or (None, None)."""
    for idx in range(len(frames) - 1, -1, -1):
        car = frames[idx].get("drivers", {}).get(driver)
        if car is not None and car.get("lap") is not None:
            return idx, int(car["lap"])
    return None, None


def _sample_index(times: np.ndarray, frames: list, driver: str, start_idx: int, offset_s: float) -> int:
    """First frame at or after ``t[start_idx] + offset_s`` (clipped to the last frame).

    If the driver is missing from that frame, step back towards ``start_idx``.
    """
    target = times[start_idx] + offset_s
    idx = max(start_idx, int(np.searchsorted(times, target, side="left")))
    idx = min(idx, len(frames) - 1)
    while idx > start_idx and driver not in frames[idx].get("drivers", {}):
        idx -= 1
    return idx


def sample_computed_positions(
    frames: list,
    offset_s: float = 1.0,
    position_fn: Optional[PositionFn] = None,
) -> pd.DataFrame:
    """One row per driver-lap with the replay's position for that lap.

    - Lap N with a crossing: position at ``offset_s`` seconds after the crossing
      frame (method ``"crossing"``).
    - The driver's last lap in the replay has no crossing (the race ended, or
      they retired): position in the last frame that contains them (method
      ``"last_frame"``). For finishers this is the final classification shown
      at the end of the replay.

    ``position_fn(frame) -> {driver: position}`` lets you benchmark another way
    of ordering drivers, e.g. the on-screen leaderboard. Defaults to the
    ``position`` stored in each frame.
    """
    if offset_s < 0:
        raise ValueError("offset_s must be >= 0")
    position_fn = position_fn or frame_positions
    rows = []
    if not frames:
        return pd.DataFrame(columns=COMPUTED_COLUMNS)

    times = np.array([float(f["t"]) for f in frames])
    cache = {}

    def position_at(idx, driver):
        if idx not in cache:
            cache[idx] = position_fn(frames[idx])
        return cache[idx].get(driver)

    for driver in driver_codes(frames):
        crossings = find_lap_crossings(frames, driver)
        for lap, cross_idx in sorted(crossings.items()):
            idx = _sample_index(times, frames, driver, cross_idx, offset_s)
            rows.append((driver, lap, position_at(idx, driver), idx, "crossing"))

        last_idx, last_lap = last_seen(frames, driver)
        if last_idx is not None and last_lap not in crossings:
            rows.append((driver, last_lap, position_at(last_idx, driver), last_idx, "last_frame"))

    out = pd.DataFrame(rows, columns=COMPUTED_COLUMNS)
    out["computed_pos"] = pd.to_numeric(out["computed_pos"], errors="coerce")
    return out
