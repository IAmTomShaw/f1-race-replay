"""Pure track geometry, coordinate validation, and DRS zone detection utilities.

Designed for high cohesion and zero coupling to GUI/rendering frameworks
(no Arcade, PySide6, or FastF1 dependencies).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


def is_finite_coord(x, y) -> bool:
    """Return True iff both x and y are finite numerical values.

    Rejects None, NaN, +Inf, -Inf, and non-numeric types.
    Does not rely on truthiness (0.0 is valid).
    """
    if x is None or y is None:
        return False
    if not isinstance(x, (int, float, np.number)) or not isinstance(
        y, (int, float, np.number)
    ):
        return False
    return math.isfinite(x) and math.isfinite(y)


_is_finite_coord = is_finite_coord


def format_wind_direction(degrees: Optional[float]) -> str:
    """Convert compass degrees [0, 360) into a 16-point cardinal direction."""
    if (
        degrees is None
        or not isinstance(degrees, (int, float))
        or not math.isfinite(degrees)
    ):
        return "N/A"
    deg_norm = degrees % 360
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    idx = int((deg_norm / 22.5) + 0.5) % len(dirs)
    return dirs[idx]


_format_wind_direction = format_wind_direction


def interpolate_points(xs, ys, interp_points: int = 2000):
    """Linearly resample a 2D polyline (xs, ys) to `interp_points` vertices."""
    t_old = np.linspace(0, 1, len(xs))
    t_new = np.linspace(0, 1, interp_points)
    xs_i = np.interp(t_new, t_old, xs)
    ys_i = np.interp(t_new, t_old, ys)
    return list(zip(xs_i, ys_i))


def _extract_zones_from_mask(mask, x_get, y_get, min_len: int = 2):
    drs_zones = []
    drs_start = None
    n = len(mask)
    for i, active in enumerate(mask):
        if active:
            if drs_start is None:
                drs_start = i
        else:
            if drs_start is not None:
                drs_end = i - 1
                if drs_end - drs_start + 1 >= min_len:
                    drs_zones.append({
                        "start": {
                            "x": x_get[drs_start],
                            "y": y_get[drs_start],
                            "index": drs_start,
                        },
                        "end": {
                            "x": x_get[drs_end],
                            "y": y_get[drs_end],
                            "index": drs_end,
                        },
                    })
                drs_start = None
    if drs_start is not None:
        drs_end = n - 1
        if drs_end - drs_start + 1 >= min_len:
            drs_zones.append({
                "start": {
                    "x": x_get[drs_start],
                    "y": y_get[drs_start],
                    "index": drs_start,
                },
                "end": {
                    "x": x_get[drs_end],
                    "y": y_get[drs_end],
                    "index": drs_end,
                },
            })
    return drs_zones


def plotDRSzones(example_lap):
    """Identify DRS zones along the circuit reference telemetry."""
    if example_lap is None or not hasattr(example_lap, "__getitem__"):
        return []
    try:
        if "DRS" not in example_lap:
            return []
    except (TypeError, Exception):
        return []

    x_val = example_lap["X"]
    y_val = example_lap["Y"]
    x_get = getattr(x_val, "iloc", x_val)
    y_get = getattr(y_val, "iloc", y_val)
    drs_col = example_lap["DRS"]
    n = len(drs_col)
    if n == 0:
        return []

    # 1. Primary: standard FastF1 active DRS values (10, 12, 14 or >= 10)
    mask_open = []
    mask_elig = []
    for val in drs_col:
        try:
            v = int(float(val)) if val is not None and pd.notna(val) else 0
        except (ValueError, TypeError):
            v = 0
        mask_open.append(v in (10, 12, 14) or v >= 10)
        mask_elig.append(v >= 8)

    drs_zones = _extract_zones_from_mask(mask_open, x_get, y_get, min_len=1)
    if drs_zones:
        return drs_zones

    # 2. Secondary: DRS eligible/detection zone code (8)
    drs_zones = _extract_zones_from_mask(mask_elig, x_get, y_get, min_len=2)
    if drs_zones:
        return drs_zones

    # 3. Fallback: if example_lap came from a clean-air race lap (all DRS == 0)
    # and the track is non-circular (real circuit geometry, not a synthetic circle),
    # detect the longest low-curvature straight sections.
    if n >= 60:
        try:
            xs = np.asarray(x_val, dtype=float)
            ys = np.asarray(y_val, dtype=float)
            dx = np.gradient(xs)
            dy = np.gradient(ys)
            ds = np.hypot(dx, dy)
            ds_safe = np.where(ds > 1e-6, ds, 1.0)
            ddx = np.gradient(dx / ds_safe)
            ddy = np.gradient(dy / ds_safe)
            curvature = np.hypot(ddx, ddy) / ds_safe
            curv_mean = float(np.nanmean(curvature))
            curv_std = float(np.nanstd(curvature))
            if curv_mean > 0 and (curv_std / curv_mean) > 0.35:
                thresh = float(np.nanpercentile(curvature, 25))
                straight_mask = (curvature <= max(thresh, 1e-4)).tolist()
                cand_zones = _extract_zones_from_mask(
                    straight_mask, x_get, y_get, min_len=max(6, n // 35)
                )
                if cand_zones:
                    cand_zones.sort(
                        key=lambda z: z["end"]["index"] - z["start"]["index"],
                        reverse=True,
                    )
                    top_zones = sorted(
                        cand_zones[:2], key=lambda z: z["start"]["index"]
                    )
                    return top_zones
        except Exception:
            pass

    return []


def build_track_from_example_lap(example_lap, track_width: float = 200):
    """Build inner/outer track boundaries, bounding box, and DRS zones."""
    if example_lap is None or not hasattr(example_lap, "__getitem__"):
        t = np.linspace(0, 2 * np.pi, 200)
        example_lap = {
            "X": np.asarray(1000.0 * np.cos(t)),
            "Y": np.asarray(1000.0 * np.sin(t)),
            "DRS": np.zeros(200, dtype=int),
        }

    drs_zones = plotDRSzones(example_lap)
    plot_x_ref = np.asarray(example_lap["X"])
    plot_y_ref = np.asarray(example_lap["Y"])

    # compute tangents
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

    # world bounds
    x_min = min(plot_x_ref.min(), x_inner.min(), x_outer.min())
    x_max = max(plot_x_ref.max(), x_inner.max(), x_outer.max())
    y_min = min(plot_y_ref.min(), y_inner.min(), y_outer.min())
    y_max = max(plot_y_ref.max(), y_inner.max(), y_outer.max())

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
