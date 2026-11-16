"""
Pure-Python + NumPy track geometry and race event extraction helpers.

Kept free of Arcade / PySide6 imports so both the desktop UI and the headless
FastAPI web exporter can share the exact same geometry calculations.
"""

from typing import List
import numpy as np

EVENT_DNF = "dnf"
EVENT_LAP = "lap"
EVENT_YELLOW_FLAG = "yellow_flag"
EVENT_RED_FLAG = "red_flag"
EVENT_SAFETY_CAR = "safety_car"
EVENT_VSC = "vsc"


def _to_numpy_1d(values) -> np.ndarray:
    if hasattr(values, "to_numpy"):
        return values.to_numpy(dtype=float)
    return np.asarray(values, dtype=float)


def _at_index(values, idx: int) -> float:
    if hasattr(values, "iloc"):
        return float(values.iloc[idx])
    return float(values[idx])


def plot_drs_zones(example_lap) -> list[dict]:
    """Identify DRS activation zones along an example lap's (X, Y, DRS) series."""
    x_val = example_lap["X"]
    y_val = example_lap["Y"]
    drs_col = example_lap["DRS"]
    drs_zones = []
    drs_start = None

    n_points = len(drs_col)
    for i, val in enumerate(drs_col):
        if val in (10, 12, 14):
            if drs_start is None:
                drs_start = i
        else:
            if drs_start is not None:
                drs_end = i - 1
                drs_zones.append(
                    {
                        "start": {
                            "x": _at_index(x_val, drs_start),
                            "y": _at_index(y_val, drs_start),
                            "index": drs_start,
                        },
                        "end": {
                            "x": _at_index(x_val, drs_end),
                            "y": _at_index(y_val, drs_end),
                            "index": drs_end,
                        },
                    }
                )
                drs_start = None

    if drs_start is not None:
        drs_end = n_points - 1
        drs_zones.append(
            {
                "start": {
                    "x": _at_index(x_val, drs_start),
                    "y": _at_index(y_val, drs_start),
                    "index": drs_start,
                },
                "end": {
                    "x": _at_index(x_val, drs_end),
                    "y": _at_index(y_val, drs_end),
                    "index": drs_end,
                },
            }
        )

    return drs_zones


def build_track_from_example_lap(example_lap, track_width: float = 200):
    """Build inner/outer track edges, bounds, and DRS zones from an example lap."""
    drs_zones = plot_drs_zones(example_lap)
    plot_x_ref = example_lap["X"]
    plot_y_ref = example_lap["Y"]

    dx = np.gradient(plot_x_ref)
    dy = np.gradient(plot_y_ref)

    norm = np.sqrt(dx**2 + dy**2)
    norm[norm == 0] = 1.0
    dx /= norm
    dy /= norm

    nx = -dy
    ny = dx

    x_outer = plot_x_ref + nx * (track_width / 2)
    y_outer = plot_y_ref + ny * (track_width / 2)
    x_inner = plot_x_ref - nx * (track_width / 2)
    y_inner = plot_y_ref - ny * (track_width / 2)

    x_min = float(min(np.min(plot_x_ref), np.min(x_inner), np.min(x_outer)))
    x_max = float(max(np.max(plot_x_ref), np.max(x_inner), np.max(x_outer)))
    y_min = float(min(np.min(plot_y_ref), np.min(y_inner), np.min(y_outer)))
    y_max = float(max(np.max(plot_y_ref), np.max(y_inner), np.max(y_outer)))

    return (
        plot_x_ref,
        plot_y_ref,
        x_inner,
        y_inner,
        x_outer,
        y_outer,
        x_min,
        x_max,
        y_min,
        y_max,
        drs_zones,
    )


def extract_race_events(
    frames: List[dict],
    track_statuses: List[dict],
    total_laps: int,
    fps: float = 25.0,
) -> List[dict]:
    """
    Extract timeline markers (DNFs, Yellow/Red flags, Safety Car, VSC) from frames.
    """
    events = []
    if not frames:
        return events

    n_frames = len(frames)
    prev_drivers = set()
    sample_rate = max(1, int(round(fps)))

    for i in range(0, n_frames, sample_rate):
        frame = frames[i]
        drivers_data = frame.get("drivers", {})
        active_drivers = {
            code
            for code, info in drivers_data.items()
            if info.get("rel_dist", 0) != 1
        }
        current_drivers = active_drivers if active_drivers else set(drivers_data.keys())

        if prev_drivers:
            dnf_drivers = prev_drivers - current_drivers
            for driver_code in sorted(dnf_drivers):
                prev_frame = frames[max(0, i - sample_rate)]
                driver_info = prev_frame.get("drivers", {}).get(driver_code, {})
                lap = driver_info.get("lap", "?")
                events.append(
                    {
                        "type": EVENT_DNF,
                        "frame": i,
                        "time_s": float(frame.get("t", i / fps)),
                        "label": driver_code,
                        "lap": lap,
                    }
                )

        prev_drivers = current_drivers

    for status in track_statuses:
        status_code = str(status.get("status", ""))
        start_time = float(status.get("start_time", 0.0))
        end_time = status.get("end_time")

        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps) if end_time is not None else start_frame + int(10 * fps)

        if end_frame <= 0:
            continue

        if n_frames > 0:
            end_frame = min(end_frame, n_frames)

        event_type = None
        if status_code == "2":
            event_type = EVENT_YELLOW_FLAG
        elif status_code == "4":
            event_type = EVENT_SAFETY_CAR
        elif status_code == "5":
            event_type = EVENT_RED_FLAG
        elif status_code in ("6", "7"):
            event_type = EVENT_VSC

        if event_type:
            events.append(
                {
                    "type": event_type,
                    "frame": start_frame,
                    "end_frame": end_frame,
                    "start_time_s": max(0.0, start_time),
                    "end_time_s": float(end_time) if end_time is not None else max(0.0, start_time) + 10.0,
                    "label": "",
                    "lap": None,
                }
            )

    return events
