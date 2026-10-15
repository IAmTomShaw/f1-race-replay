"""
Data serializers converting FastF1, FrameStore, and NumPy data
structures into clean, lightweight JSON for the web frontend.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from src.ui_components import build_track_from_example_lap


def serialize_track_geometry(example_lap, interp_points: int = 1200) -> Dict[str, Any]:
    """
    Extract and interpolate inner, outer, and center track boundaries.
    Rounds coordinates to 2 decimal places to minimize JSON payload.
    """
    if example_lap is None:
        return {}

    (plot_x_ref, plot_y_ref,
     x_inner, y_inner,
     x_outer, y_outer,
     x_min, x_max,
     y_min, y_max, drs_zones) = build_track_from_example_lap(example_lap)

    def _interpolate_coords(xs, ys, num_pts=interp_points):
        x_arr = np.asarray(xs, dtype=np.float64)
        y_arr = np.asarray(ys, dtype=np.float64)
        t = np.linspace(0, 1, len(x_arr))
        t_new = np.linspace(0, 1, num_pts)
        x_new = np.interp(t_new, t, x_arr)
        y_new = np.interp(t_new, t, y_arr)
        return [[round(float(x), 2), round(float(y), 2)] for x, y in zip(x_new, y_new)]

    inner = _interpolate_coords(x_inner, y_inner)
    outer = _interpolate_coords(x_outer, y_outer)
    center = _interpolate_coords(plot_x_ref, plot_y_ref)

    serialized_drs = []
    for zone in drs_zones:
        start_pt = zone.get("start", {})
        end_pt = zone.get("end", {})
        serialized_drs.append({
            "start": [round(float(start_pt.get("x", 0)), 2), round(float(start_pt.get("y", 0)), 2)],
            "end": [round(float(end_pt.get("x", 0)), 2), round(float(end_pt.get("y", 0)), 2)]
        })

    return {
        "bounds": {
            "x_min": round(float(x_min), 2),
            "x_max": round(float(x_max), 2),
            "y_min": round(float(y_min), 2),
            "y_max": round(float(y_max), 2)
        },
        "center": center,
        "inner": inner,
        "outer": outer,
        "drs_zones": serialized_drs
    }


def serialize_metadata(meta: Dict[str, Any], session_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Serialize session metadata and track geometry."""
    driver_colors_raw = meta.get("driver_colors", {})
    driver_colors = {}
    for code, col in driver_colors_raw.items():
        if isinstance(col, (tuple, list)):
            driver_colors[code] = [int(c) for c in col[:3]]
        elif isinstance(col, str):
            driver_colors[code] = col

    track_statuses_raw = meta.get("track_statuses", [])
    track_statuses = []
    for st in track_statuses_raw:
        if isinstance(st, dict):
            track_statuses.append({
                "status": str(st.get("status", "1")),
                "start_time": round(float(st.get("start_time", 0)), 2),
                "end_time": round(float(st.get("end_time", 0)), 2) if st.get("end_time") is not None else None
            })

    example_lap = meta.get("example_lap")
    track_geo = serialize_track_geometry(example_lap)

    info = session_info or {}
    return {
        "event_name": info.get("event_name", ""),
        "circuit_name": info.get("circuit_name", ""),
        "country": info.get("country", ""),
        "year": info.get("year"),
        "round": info.get("round"),
        "total_laps": meta.get("total_laps", 0),
        "driver_colors": driver_colors,
        "track_statuses": track_statuses,
        "track": track_geo
    }


def serialize_framestore_columnar(
    frame_store,
    start: int = 0,
    limit: Optional[int] = None,
    step: int = 1
) -> Dict[str, Any]:
    """
    Serialize FrameStore in columnar format for efficient transmission.
    Payload size is drastically smaller than list-of-dicts and compresses
    exceptionally well with gzip / brotli.
    """
    total_len = len(frame_store)
    end = total_len if limit is None else min(total_len, start + limit)
    indices = np.arange(start, end, step)

    t_slice = [round(float(t_val), 3) for t_val in frame_store.t[indices]]
    leader_laps = [int(lap_val) for lap_val in frame_store.leader_lap[indices]]

    drivers_data = {}
    channels = frame_store.channels
    codes = frame_store.codes

    for j, code in enumerate(codes):
        # Extract slices across frames for driver j
        x_col = np.round(channels["x"][indices, j], 1).tolist()
        y_col = np.round(channels["y"][indices, j], 1).tolist()
        speed_col = np.round(channels["speed"][indices, j], 0).astype(int).tolist()
        gear_col = channels["gear"][indices, j].tolist()
        throttle_col = np.round(channels["throttle"][indices, j], 0).astype(int).tolist()
        brake_col = np.round(channels["brake"][indices, j], 0).astype(int).tolist()
        drs_col = channels["drs"][indices, j].tolist()
        lap_col = channels["lap"][indices, j].tolist()
        pos_col = channels["position"][indices, j].tolist()
        in_pit_col = frame_store.in_pit[indices, j].tolist()

        drivers_data[code] = {
            "x": x_col,
            "y": y_col,
            "speed": speed_col,
            "gear": gear_col,
            "throttle": throttle_col,
            "brake": brake_col,
            "drs": drs_col,
            "lap": lap_col,
            "pos": pos_col,
            "in_pit": in_pit_col
        }

    return {
        "fps": 25 // step,
        "start_index": start,
        "end_index": end,
        "total_frames": total_len,
        "timestamps": t_slice,
        "leader_lap": leader_laps,
        "drivers": drivers_data
    }
