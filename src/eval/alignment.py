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

COMPUTED_COLUMNS = ["driver", "lap", "computed_pos", "frame_idx", "event_idx", "method"]

EVAL_COLUMNS = [
    "driver", "lap", "segment", "official_pos", "computed_pos", "error", "excluded_reason",
    "method", "frame_idx", "event_idx", "timing_error_s", "is_pit", "is_sc_vsc", "is_final", "is_lap1",
]

# A replay lap end this far from the official one means the crossing is wrong.
MAX_TIMING_ERROR_S = 1.0


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

    Only laps the driver was seen on get a crossing; frames without the driver
    are skipped. Note: get_race_telemetry interpolates the lap number across
    gaps in the telemetry, so a lap missing from the telemetry still gets a
    crossing, at the wrong time. ``crossing_timing_errors`` catches those.
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


def _car_state(frame: dict, driver: str):
    car = frame.get("drivers", {}).get(driver)
    if car is None:
        return None
    return (car.get("lap"), car.get("dist"), car.get("x"), car.get("y"))


def freeze_index(frames: list, driver: str, last_idx: int) -> int:
    """First frame of the final stretch in which the driver no longer moves.

    get_race_telemetry holds a car at its last telemetry point (np.interp
    clamps), so lap, dist, x and y stay exactly equal from the moment the
    driver's own data ends: the chequered flag for a finisher, the garage or
    the stopping point for a retirement.
    """
    final = _car_state(frames[last_idx], driver)
    idx = last_idx
    while idx > 0 and _car_state(frames[idx - 1], driver) == final:
        idx -= 1
    return idx


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

    ``event_idx`` is the frame where the replay says the lap ended and
    ``frame_idx`` is the frame the position was read from.

    - Lap N with a crossing: read ``offset_s`` seconds after the crossing
      (method ``"crossing"``).
    - A driver's last replay lap has no crossing. If they stopped moving after
      the winner did, they finished: read the last frame, i.e. the final order
      the replay shows (method ``"last_frame"``). If they stopped before the
      winner finished, they retired (e.g. into the garage): read ``offset_s``
      after their data ends (method ``"data_end"``), not at the end of the race.

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

    last_laps = []  # (driver, lap, last_idx, stop_idx) for last laps without a crossing
    for driver in driver_codes(frames):
        crossings = find_lap_crossings(frames, driver)
        for lap, cross_idx in sorted(crossings.items()):
            idx = _sample_index(times, frames, driver, cross_idx, offset_s)
            rows.append((driver, lap, position_at(idx, driver), idx, cross_idx, "crossing"))

        last_idx, last_lap = last_seen(frames, driver)
        if last_idx is not None and last_lap not in crossings:
            last_laps.append((driver, last_lap, last_idx, freeze_index(frames, driver, last_idx)))

    if last_laps:
        # The winner is the first car on the highest lap to stop moving.
        top_lap = max(lap for _, lap, _, _ in last_laps)
        winner_stop = min(stop for _, lap, _, stop in last_laps if lap == top_lap)
        for driver, lap, last_idx, stop_idx in last_laps:
            if stop_idx >= winner_stop:
                rows.append((driver, lap, position_at(last_idx, driver), last_idx, stop_idx, "last_frame"))
            else:
                idx = _sample_index(times, frames, driver, stop_idx, offset_s)
                rows.append((driver, lap, position_at(idx, driver), idx, stop_idx, "data_end"))

    out = pd.DataFrame(rows, columns=COMPUTED_COLUMNS)
    out["computed_pos"] = pd.to_numeric(out["computed_pos"], errors="coerce")
    return out.sort_values(["driver", "lap"]).reset_index(drop=True)


def crossing_timing_errors(frames: list, computed: pd.DataFrame, laps: pd.DataFrame) -> pd.DataFrame:
    """Seconds between the replay's lap end (``event_idx``) and the official lap end (``laps.Time``).

    Replay ``t`` starts at 0 and FastF1 ``Time`` is session time, so the two
    differ by a constant. That constant is estimated as the median difference
    over all laps, which a few bad laps cannot move. A large error means the
    replay put the end of that lap at the wrong moment (e.g. a lap missing
    from the telemetry, or a red-flag stoppage).
    """
    columns = ["driver", "lap", "timing_error_s"]
    if computed.empty or not frames or "Time" not in laps.columns:
        return pd.DataFrame(columns=columns)

    valid = laps["LapNumber"].notna() & laps["Driver"].notna() & laps["Time"].notna()
    official = pd.DataFrame(
        {
            "driver": laps.loc[valid, "Driver"].astype(str).to_numpy(),
            "lap": laps.loc[valid, "LapNumber"].astype(int).to_numpy(),
            "official_end_s": pd.to_timedelta(laps.loc[valid, "Time"]).dt.total_seconds().to_numpy(),
        }
    ).drop_duplicates(["driver", "lap"])

    df = computed[["driver", "lap", "event_idx"]].merge(official, on=["driver", "lap"], how="inner")
    if df.empty:
        return pd.DataFrame(columns=columns)
    times = np.array([float(f["t"]) for f in frames])
    replay_end_s = times[df["event_idx"].astype(int).to_numpy()]
    shift = float(np.median(df["official_end_s"].to_numpy() - replay_end_s))
    df["timing_error_s"] = replay_end_s + shift - df["official_end_s"].to_numpy()
    return df[columns]


def build_eval_table(
    ground_truth: pd.DataFrame,
    computed: pd.DataFrame,
    timing: Optional[pd.DataFrame] = None,
    max_timing_error_s: float = MAX_TIMING_ERROR_S,
) -> pd.DataFrame:
    """Left-join official and computed positions on (driver, lap).

    Every ground-truth row is kept. Exclusion reasons, first one wins:
    ``official_pos_nan`` (from ground truth), ``no_crossing`` (no replay
    value), ``crossing_mistimed`` (replay lap end more than
    ``max_timing_error_s`` from the official one; needs ``timing``).
    """
    table = ground_truth.merge(
        computed[["driver", "lap", "computed_pos", "frame_idx", "event_idx", "method"]],
        on=["driver", "lap"],
        how="left",
        validate="one_to_one",
    )
    if timing is not None and not timing.empty:
        table = table.merge(timing[["driver", "lap", "timing_error_s"]], on=["driver", "lap"],
                            how="left", validate="one_to_one")
    else:
        table["timing_error_s"] = np.nan
    table["timing_error_s"] = pd.to_numeric(table["timing_error_s"], errors="coerce")

    table["segment"] = label_segments(table)
    reason = table["excluded_reason"].astype(object)
    reason[table["computed_pos"].isna() & reason.isna()] = "no_crossing"
    reason[(table["timing_error_s"].abs() > max_timing_error_s) & reason.isna()] = "crossing_mistimed"
    table["excluded_reason"] = reason
    table["error"] = table["computed_pos"] - table["official_pos"]
    return table[EVAL_COLUMNS]


def compare_lap_times(frames: list, laps: pd.DataFrame, driver: str) -> pd.DataFrame:
    """Sanity check: replay lap time (time between crossings) vs official LapTime.

    If the crossings are found at the right moments, these should agree to
    within a fraction of a second on normal laps.
    """
    crossings = find_lap_crossings(frames, driver)
    rows = []
    for lap in sorted(crossings):
        prev = crossings.get(lap - 1)
        if prev is None:
            continue
        rows.append((lap, float(frames[crossings[lap]]["t"]) - float(frames[prev]["t"])))
    replay = pd.DataFrame(rows, columns=["lap", "replay_lap_time_s"])

    official = laps.loc[laps["Driver"] == driver, ["LapNumber", "LapTime"]].dropna(subset=["LapNumber"])
    official = pd.DataFrame(
        {
            "lap": official["LapNumber"].astype(int).to_numpy(),
            "official_lap_time_s": pd.to_timedelta(official["LapTime"]).dt.total_seconds().to_numpy(),
        }
    )
    out = replay.merge(official, on="lap", how="inner")
    out["diff_s"] = out["replay_lap_time_s"] - out["official_lap_time_s"]
    return out
