"""Track layout extraction, DRS frame-projection enrichment, and terminal flag resolution.

Extracted from `src.f1_data` for high cohesion and clean separation of circuit
geometry/metadata services from 25Hz frame resampling.
"""
from __future__ import annotations

import math

try:
    import fastf1
    import fastf1.plotting
except ImportError:
    fastf1 = None
import numpy as np


def enrich_example_lap_drs_from_frames(example_lap, frames):
    """Project all DRS-open coordinates from race frames onto example_lap['DRS']."""
    if example_lap is None or not frames:
        return example_lap
    try:
        xs = np.asarray(example_lap["X"], dtype=float)
        ys = np.asarray(example_lap["Y"], dtype=float)
        n_pts = len(xs)
        if n_pts < 10:
            return example_lap
        drs_arr = (
            np.asarray(example_lap["DRS"], dtype=int).copy()
            if "DRS" in example_lap and len(example_lap["DRS"]) == n_pts
            else np.zeros(n_pts, dtype=int)
        )

        drs_xs = []
        drs_ys = []
        step = max(1, len(frames) // 3000)
        for frame in frames[::step]:
            drivers = frame.get("drivers", {}) if isinstance(frame, dict) else {}
            for pos in drivers.values():
                if not isinstance(pos, dict):
                    continue
                d_val = pos.get("drs")
                if d_val is not None and isinstance(d_val, (int, float)) and d_val >= 10:
                    px, py = pos.get("x"), pos.get("y")
                    if (
                        px is not None
                        and py is not None
                        and math.isfinite(px)
                        and math.isfinite(py)
                    ):
                        drs_xs.append(float(px))
                        drs_ys.append(float(py))

        if drs_xs:
            qx = np.asarray(drs_xs, dtype=float)
            qy = np.asarray(drs_ys, dtype=float)
            valid_idx_list = []
            for c_start in range(0, len(qx), 512):
                cx = qx[c_start:c_start + 512, None]
                cy = qy[c_start:c_start + 512, None]
                d2 = (xs[None, :] - cx) ** 2 + (ys[None, :] - cy) ** 2
                min_idx = np.argmin(d2, axis=1)
                min_d2 = d2[np.arange(len(min_idx)), min_idx]
                valid_idx_list.append(min_idx[min_d2 <= 6400.0])
            valid_idxs = (
                np.concatenate(valid_idx_list)
                if valid_idx_list
                else np.array([], dtype=int)
            )
            if len(valid_idxs) > 0:
                mask = drs_arr >= 10
                mask[valid_idxs] = True
                for i in range(1, n_pts - 4):
                    if mask[i - 1] and np.any(mask[i + 1:i + 5]):
                        mask[i] = True
                drs_arr[mask] = np.maximum(drs_arr[mask], 12)

        if isinstance(example_lap, dict):
            out = dict(example_lap)
            out["DRS"] = drs_arr
            return out
        out = example_lap.copy()
        out["DRS"] = drs_arr
        return out
    except Exception:
        return example_lap


def extract_example_lap_telemetry(session, year=None, round_number=None, frames=None):
    """Extract a compact example lap dict (X, Y, Distance, DRS) for track layout."""
    if year is None and session is not None and hasattr(session, "event"):
        try:
            ev_date = session.event.get("EventDate")
            if ev_date is not None and hasattr(ev_date, "year"):
                year = int(ev_date.year)
        except Exception:
            pass
    if round_number is None and session is not None and hasattr(session, "event"):
        try:
            rn = session.event.get("RoundNumber")
            if rn is not None:
                round_number = int(rn)
        except Exception:
            pass

    if year is not None and round_number is not None:
        try:
            quali_session = fastf1.get_session(year, round_number, "Q")
            quali_session.load(telemetry=True, weather=False, messages=False)
            if quali_session is not None and len(quali_session.laps) > 0:
                fastest_q = quali_session.laps.pick_fastest()
                if fastest_q is not None:
                    q_tel = fastest_q.get_telemetry()
                    if (
                        q_tel is not None
                        and not q_tel.empty
                        and "X" in q_tel
                        and "Y" in q_tel
                        and "DRS" in q_tel
                    ):
                        if np.any(q_tel["DRS"].to_numpy() >= 8):
                            res = {
                                "X": q_tel["X"].to_numpy().copy(),
                                "Y": q_tel["Y"].to_numpy().copy(),
                                "Distance": (
                                    q_tel["Distance"].to_numpy().copy()
                                    if "Distance" in q_tel
                                    else np.zeros(len(q_tel))
                                ),
                                "DRS": q_tel["DRS"].to_numpy().copy(),
                            }
                            return enrich_example_lap_drs_from_frames(res, frames)
        except Exception:
            pass

    fallback_tel = None
    try:
        if session is not None and hasattr(session, "laps") and len(session.laps) > 0:
            fastest = session.laps.pick_fastest()
            if fastest is not None:
                tel = fastest.get_telemetry()
                if tel is not None and not tel.empty and "X" in tel and "Y" in tel:
                    fallback_tel = {
                        "X": tel["X"].to_numpy().copy(),
                        "Y": tel["Y"].to_numpy().copy(),
                        "Distance": (
                            tel["Distance"].to_numpy().copy()
                            if "Distance" in tel
                            else np.zeros(len(tel))
                        ),
                        "DRS": (
                            tel["DRS"].to_numpy().copy()
                            if "DRS" in tel
                            else np.zeros(len(tel), dtype=int)
                        ),
                    }
    except Exception:
        pass

    return enrich_example_lap_drs_from_frames(fallback_tel, frames)


def get_driver_colors(session):
    """Map driver 3-letter codes to (R, G, B) integer tuples."""
    color_mapping = fastf1.plotting.get_driver_color_mapping(session)
    rgb_colors = {}
    for driver, hex_color in color_mapping.items():
        hex_color = hex_color.lstrip("#")
        rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        rgb_colors[driver] = rgb
    return rgb_colors


def get_circuit_rotation(session):
    """Return the official FastF1 circuit rotation in degrees."""
    circuit = session.get_circuit_info()
    return circuit.rotation


def resolve_track_length(session, fallback_max_lap_dist: float = 0.0) -> float:
    """Resolve circuit lap length in meters from circuit_info or fastest lap telemetry."""
    try:
        tl = float(getattr(session.get_circuit_info(), "length", 0.0) or 0.0)
        if tl > 0:
            return tl
    except Exception:
        pass
    if fallback_max_lap_dist and fallback_max_lap_dist > 0:
        return float(fallback_max_lap_dist)
    try:
        fastest = session.laps.pick_fastest()
        if fastest is not None:
            tel = fastest.get_telemetry()
            if tel is not None and not tel.empty and "Distance" in tel:
                d_max = float(tel["Distance"].max())
                if math.isfinite(d_max) and d_max > 0:
                    return d_max
    except Exception:
        pass
    return 0.0


def resolve_driver_terminal_flags(
    session,
    driver_max_lags,
    driver_t_max,
    max_lap_number,
    global_t_max,
):
    """Determine (finished, retired) per driver from session.results or telemetry bounds."""
    finished_codes = set()
    retired_codes = set()
    try:
        results_df = getattr(session, "results", None)
        if results_df is not None and not results_df.empty:
            for _, row in results_df.iterrows():
                code = str(row.get("Abbreviation", "")).strip()
                if not code:
                    continue
                status = str(row.get("Status", "")).strip()
                c_pos = str(row.get("ClassifiedPosition", "")).strip().upper()
                if status == "Finished" or status.startswith("+") or status == "Lapped":
                    finished_codes.add(code)
                elif (
                    c_pos in ("R", "D", "E", "W", "F", "N")
                    or "retire" in status.lower()
                    or "accident" in status.lower()
                    or "collision" in status.lower()
                    or "engine" in status.lower()
                    or "gearbox" in status.lower()
                    or "brakes" in status.lower()
                    or "hydraulics" in status.lower()
                    or "electrical" in status.lower()
                    or "power unit" in status.lower()
                ):
                    retired_codes.add(code)
    except Exception:
        pass

    flags = {}
    for code, d_max_lap in driver_max_lags.items():
        if code in finished_codes:
            flags[code] = (True, False)
        elif code in retired_codes:
            flags[code] = (False, True)
        else:
            d_tmax = driver_t_max.get(code, 0.0)
            if max_lap_number > 0 and d_max_lap >= max_lap_number:
                flags[code] = (True, False)
            elif (
                max_lap_number > 0
                and d_max_lap < max_lap_number - 1
                and (global_t_max - d_tmax) > 45.0
            ):
                flags[code] = (False, True)
            elif (global_t_max - d_tmax) <= 120.0 and d_max_lap >= max(
                1, max_lap_number - 2
            ):
                flags[code] = (True, False)
            else:
                flags[code] = (False, False)
    return flags


_resolve_track_length = resolve_track_length
_resolve_driver_terminal_flags = resolve_driver_terminal_flags
