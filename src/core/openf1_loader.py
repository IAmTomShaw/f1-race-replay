"""
Unauthenticated OpenF1 + MultiViewer race/sprint bundle builder.

Why this exists:
Formula 1 recently gated ``livetiming.formula1.com/static/...`` behind F1 account
credentials (HTTP 401 in unauthenticated FastF1 v3.9+). OpenF1's historical REST
API (2023–present) and MultiViewer's circuit geometry API are free and require
zero credentials, allowing any user to load real 2023–2026 Grand Prix replays
out of the box.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import numpy as np
import requests
from scipy.spatial import cKDTree

from src.core.track_geometry import (
    EVENT_DNF,
    EVENT_RED_FLAG,
    EVENT_SAFETY_CAR,
    EVENT_VSC,
    EVENT_YELLOW_FLAG,
    build_track_from_example_lap,
)
from src.lib.tyres import get_tyre_compound_int

OPENF1_BASE = "https://api.openf1.org/v1"
MULTIVIEWER_CIRCUIT_URL = "https://api.multiviewer.app/api/v1/circuits/{circuit_key}/{year}"
HEADERS = {"User-Agent": "f1-race-replay/0.2"}

ProgressCallback = Optional[Callable[[str, int], None]]


def _get_json(url: str, params: Optional[dict[str, Any]] = None, retries: int = 4) -> Any:
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if resp.status_code == 429:
                time.sleep(0.8 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_err = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"OpenF1 request failed ({url}): {last_err}") from last_err


def _parse_iso(ts: Optional[str]) -> Optional[float]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _fmt_iso(epoch_s: float) -> str:
    dt = datetime.fromtimestamp(epoch_s, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+00:00"


def list_openf1_sessions_for_year(year: int) -> list[dict[str, Any]]:
    """Return all Race and Sprint sessions published on OpenF1 for ``year``."""
    if year < 2023:
        return []
    sessions = _get_json(f"{OPENF1_BASE}/sessions", params={"year": year})
    now_ts = datetime.now(timezone.utc).timestamp()
    usable = []
    for s in sessions:
        if s.get("is_cancelled"):
            continue
        s_name = str(s.get("session_name", ""))
        if s_name not in ("Race", "Sprint"):
            continue
        end_ts = _parse_iso(s.get("date_end")) or _parse_iso(s.get("date_start")) or 0.0
        usable.append(
            {
                **s,
                "is_completed": end_ts > 0 and end_ts <= now_ts,
            }
        )
    usable.sort(key=lambda item: item.get("date_start") or "")
    return usable


def resolve_openf1_session(
    year: int, round_number: int, session_type: str = "R"
) -> tuple[dict[str, Any], Optional[str]]:
    """
    Match (year, round_number, session_type) to an OpenF1 session dict + official event name.
    Matches against FastF1's official event schedule date (±4 days) when available so
    cancelled rounds never shift round numbering.
    """
    sessions = list_openf1_sessions_for_year(year)
    if not sessions:
        raise ValueError(f"No OpenF1 sessions found for {year}.")

    want_name = "Sprint" if session_type.upper() == "S" else "Race"
    official_event_name: Optional[str] = None
    target_epoch: Optional[float] = None

    try:
        import fastf1

        sched = fastf1.get_event_schedule(year)
        row_matches = sched[sched["RoundNumber"] == round_number]
        if not row_matches.empty:
            ev_row = row_matches.iloc[0]
            official_event_name = str(ev_row.get("EventName") or "") or None
            ev_date = ev_row.get("EventDate")
            if ev_date is not None and hasattr(ev_date, "timestamp"):
                target_epoch = float(ev_date.timestamp())
    except Exception:
        pass

    chosen: Optional[dict[str, Any]] = None
    if target_epoch is not None:
        candidates = [s for s in sessions if s.get("session_name") == want_name]
        best_diff = float("inf")
        for cand in candidates:
            c_ts = _parse_iso(cand.get("date_start"))
            if c_ts is not None:
                diff = abs(c_ts - target_epoch)
                if diff < best_diff and diff <= 5 * 86400:
                    best_diff = diff
                    chosen = cand

    if chosen is None:
        races = [s for s in sessions if s.get("session_name") == "Race"]
        if round_number < 1 or round_number > len(races):
            raise ValueError(f"Round {round_number} not found in {year} schedule.")
        meeting_key = races[round_number - 1]["meeting_key"]
        matches = [
            s
            for s in sessions
            if s.get("meeting_key") == meeting_key and s.get("session_name") == want_name
        ]
        if not matches:
            raise ValueError(f"No {want_name} session found for {year} Round {round_number}.")
        chosen = matches[0]

    if not chosen.get("is_completed", True):
        raise RuntimeError(
            f"{official_event_name or chosen.get('location')} ({year} R{round_number}) has not taken place yet."
        )
    return chosen, official_event_name


def _fetch_windowed(
    endpoint: str,
    session_key: int,
    start_ts: float,
    end_ts: float,
    window_s: float = 720.0,
    progress_cb: ProgressCallback = None,
    pct_start: int = 20,
    pct_end: int = 55,
    label: str = "telemetry",
) -> list[dict[str, Any]]:
    """Fetch high-volume OpenF1 rows (`location` or `car_data`) in time slices."""
    rows: list[dict[str, Any]] = []
    total_span = max(1.0, end_ts - start_ts)
    n_windows = max(1, math.ceil(total_span / window_s))

    for w_idx in range(n_windows):
        w0 = start_ts + w_idx * window_s
        w1 = min(end_ts, w0 + window_s)
        if progress_cb:
            pct = int(pct_start + ((w_idx / n_windows) * (pct_end - pct_start)))
            progress_cb(f"Downloading {label} ({w_idx + 1}/{n_windows})...", pct)

        query_url = (
            f"{OPENF1_BASE}/{endpoint}?session_key={session_key}"
            f"&date>={_fmt_iso(w0)}&date<{_fmt_iso(w1)}"
        )
        chunk = _get_json(query_url)
        if isinstance(chunk, list):
            rows.extend(chunk)
        # Respect OpenF1 free-tier rate limit (~3 req/s)
        time.sleep(0.32)

    return rows


def _build_track_status_and_rc(
    rc_raw: list[dict[str, Any]],
    t0_epoch: float,
    duration_s: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    formatted_rc = []
    status_spans: list[dict[str, Any]] = [
        {"status": "1", "start_time": 0.0, "end_time": None}
    ]

    def _push_status(code: str, t_rel: float) -> None:
        t_clamped = round(max(0.0, t_rel), 2)
        if status_spans[-1]["status"] == code:
            return
        status_spans[-1]["end_time"] = t_clamped
        status_spans.append({"status": code, "start_time": t_clamped, "end_time": None})

    sorted_rc = sorted(rc_raw, key=lambda m: m.get("date") or "")
    for msg in sorted_rc:
        ts = _parse_iso(msg.get("date"))
        if ts is None:
            continue
        t_rel = ts - t0_epoch
        text = str(msg.get("message") or "")
        upper = text.upper()
        cat = str(msg.get("category") or "")
        flag = str(msg.get("flag") or "")

        if t_rel >= -5.0:
            formatted_rc.append(
                {
                    "time": round(max(0.0, t_rel), 2),
                    "category": cat,
                    "message": text,
                    "flag": flag,
                    "scope": str(msg.get("scope") or ""),
                    "sector": str(msg["sector"]) if msg.get("sector") is not None else "",
                    "racing_number": str(msg["driver_number"]) if msg.get("driver_number") is not None else "",
                }
            )

        if t_rel < 0:
            continue

        if "VIRTUAL SAFETY CAR DEPLOYED" in upper:
            _push_status("6", t_rel)
        elif "VIRTUAL SAFETY CAR ENDING" in upper:
            _push_status("7", t_rel)
        elif "SAFETY CAR DEPLOYED" in upper and "VIRTUAL" not in upper:
            _push_status("4", t_rel)
        elif flag == "RED" or "RED FLAG" in upper:
            _push_status("5", t_rel)
        elif flag in ("YELLOW", "DOUBLE YELLOW") and status_spans[-1]["status"] == "1":
            _push_status("2", t_rel)
        elif (
            flag in ("GREEN", "CLEAR")
            or "TRACK CLEAR" in upper
            or "VSC ENDED" in upper
            or "SAFETY CAR IN THIS LAP" in upper
        ):
            if "SAFETY CAR IN THIS LAP" in upper:
                # SC enters pits ~18s after "IN THIS LAP" message
                _push_status("1", min(duration_s, t_rel + 18.0))
            else:
                _push_status("1", t_rel)

    status_spans[-1]["end_time"] = round(duration_s, 2)

    events = []
    for sp in status_spans:
        c = sp["status"]
        s_t = sp["start_time"]
        e_t = sp["end_time"] or duration_s
        if e_t <= s_t:
            continue
        ev_type = None
        if c == "2":
            ev_type = EVENT_YELLOW_FLAG
        elif c == "4":
            ev_type = EVENT_SAFETY_CAR
        elif c == "5":
            ev_type = EVENT_RED_FLAG
        elif c in ("6", "7"):
            ev_type = EVENT_VSC
        if ev_type:
            events.append(
                {
                    "type": ev_type,
                    "time_s": s_t,
                    "end_time_s": e_t,
                    "label": "",
                    "lap": None,
                }
            )

    return status_spans, formatted_rc, events


def build_openf1_bundle(
    year: int,
    round_number: int,
    session_type: str = "R",
    target_fps: float = 5.0,
    progress_cb: ProgressCallback = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Download and assemble a web-ready ``(manifest, frames)`` tuple from OpenF1 + MultiViewer.
    """
    if progress_cb:
        progress_cb(f"Locating {year} Round {round_number} on OpenF1...", 6)

    session_meta, official_event_name = resolve_openf1_session(
        year, round_number, session_type=session_type
    )
    session_key = int(session_meta["session_key"])
    circuit_key = session_meta.get("circuit_key")

    if progress_cb:
        progress_cb("Fetching drivers, laps, tyre stints & race control...", 12)

    drivers_raw = _get_json(f"{OPENF1_BASE}/drivers", params={"session_key": session_key})
    laps_raw = _get_json(f"{OPENF1_BASE}/laps", params={"session_key": session_key})
    stints_raw = _get_json(f"{OPENF1_BASE}/stints", params={"session_key": session_key})
    pits_raw = _get_json(f"{OPENF1_BASE}/pit", params={"session_key": session_key})
    pos_raw = _get_json(f"{OPENF1_BASE}/position", params={"session_key": session_key})
    rc_raw = _get_json(f"{OPENF1_BASE}/race_control", params={"session_key": session_key})
    weather_raw = _get_json(f"{OPENF1_BASE}/weather", params={"session_key": session_key})

    if not laps_raw or not drivers_raw:
        raise RuntimeError("No lap/driver telemetry available yet for this session.")

    # Determine Lights-Out (t0) and Checkered-Flag (t_end) from Lap 1..N timestamps
    lap1_starts = [
        _parse_iso(lp.get("date_start"))
        for lp in laps_raw
        if lp.get("lap_number") == 1 and lp.get("date_start")
    ]
    lap1_starts = [t for t in lap1_starts if t is not None]
    session_start_ts = _parse_iso(session_meta.get("date_start")) or 0.0
    session_end_ts = _parse_iso(session_meta.get("date_end")) or (session_start_ts + 7200.0)

    t0_epoch = (min(lap1_starts) - 5.5) if lap1_starts else session_start_ts

    lap_ends = []
    max_lap_number = 1
    for lp in laps_raw:
        l_num = int(lp.get("lap_number") or 1)
        max_lap_number = max(max_lap_number, l_num)
        ls = _parse_iso(lp.get("date_start"))
        ld = lp.get("lap_duration")
        if ls is not None and isinstance(ld, (int, float)) and ld > 0:
            lap_ends.append(ls + float(ld))

    t_end_epoch = (max(lap_ends) + 15.0) if lap_ends else session_end_ts
    t_end_epoch = min(max(t_end_epoch, t0_epoch + 120.0), t0_epoch + 10800.0)

    # Map driver numbers -> metadata
    num_to_code: dict[int, str] = {}
    drivers_meta: dict[str, dict[str, Any]] = {}
    for d in drivers_raw:
        d_num = d.get("driver_number")
        if d_num is None:
            continue
        d_num = int(d_num)
        code = str(d.get("name_acronym") or d_num)
        raw_col = str(d.get("team_colour") or "9CA3AF").lstrip("#")
        hex_col = f"#{raw_col}" if len(raw_col) == 6 else "#9CA3AF"
        num_to_code[d_num] = code
        drivers_meta[code] = {
            "code": code,
            "number": str(d_num),
            "full_name": str(d.get("full_name") or code).title(),
            "team": str(d.get("team_name") or ""),
            "color": hex_col,
        }

    # Fetch location & car_data windows
    loc_rows = _fetch_windowed(
        "location",
        session_key,
        t0_epoch,
        t_end_epoch,
        window_s=720.0,
        progress_cb=progress_cb,
        pct_start=18,
        pct_end=54,
        label="GPS track positions",
    )
    car_rows = _fetch_windowed(
        "car_data",
        session_key,
        t0_epoch,
        t_end_epoch,
        window_s=720.0,
        progress_cb=progress_cb,
        pct_start=55,
        pct_end=84,
        label="car speed & pedal telemetry",
    )

    if not loc_rows:
        raise RuntimeError("OpenF1 returned empty GPS position telemetry for this session.")

    if progress_cb:
        progress_cb("Building circuit geometry & resampling 20 cars...", 88)

    # Fetch circuit geometry from MultiViewer (fallback to clean lap trace if unavailable)
    mv_x: Optional[np.ndarray] = None
    mv_y: Optional[np.ndarray] = None
    mv_meeting_name: Optional[str] = None
    rotation_deg = 0.0
    if circuit_key is not None:
        for try_yr in (year, year - 1, 2025, 2024):
            try:
                mv_data = _get_json(
                    MULTIVIEWER_CIRCUIT_URL.format(circuit_key=circuit_key, year=try_yr),
                    retries=2,
                )
                if mv_data.get("x") and mv_data.get("y"):
                    mv_x = np.asarray(mv_data["x"], dtype=float)
                    mv_y = np.asarray(mv_data["y"], dtype=float)
                    rotation_deg = float(mv_data.get("rotation") or 0.0)
                    mv_meeting_name = str(mv_data.get("meetingName") or "") or None
                    break
            except Exception:
                continue

    # Group location & car_data per driver
    loc_by_num: dict[int, list[tuple[float, float, float]]] = {n: [] for n in num_to_code}
    for r in loc_rows:
        dn = r.get("driver_number")
        if dn in loc_by_num and r.get("x") is not None and r.get("y") is not None:
            ts = _parse_iso(r.get("date"))
            if ts is not None:
                loc_by_num[dn].append((ts - t0_epoch, float(r["x"]), float(r["y"])))

    car_by_num: dict[int, list[tuple[float, float, int, int, float, float]]] = {
        n: [] for n in num_to_code
    }
    drs_samples_xy: list[tuple[float, float]] = []

    for r in car_rows:
        dn = r.get("driver_number")
        if dn in car_by_num:
            ts = _parse_iso(r.get("date"))
            if ts is not None:
                car_by_num[dn].append(
                    (
                        ts - t0_epoch,
                        float(r.get("speed") or 0.0),
                        int(r.get("n_gear") or 0),
                        int(r.get("drs") or 0),
                        float(r.get("throttle") or 0.0),
                        1.0 if (r.get("brake") or 0) > 0 else 0.0,
                    )
                )

    # Fallback circuit trace from a clean mid-race lap if MultiViewer didn't return one
    if mv_x is None or mv_y is None:
        for dn, pts in loc_by_num.items():
            if len(pts) > 400:
                mv_x = np.array([p[1] for p in pts[100:450]], dtype=float)
                mv_y = np.array([p[2] for p in pts[100:450]], dtype=float)
                break
    if mv_x is None or mv_y is None:
        raise RuntimeError("Could not construct circuit reference polyline.")

    # Build dense 2000-point reference loop for fast along-track distance projection
    t_old = np.linspace(0.0, 1.0, len(mv_x))
    t_dense = np.linspace(0.0, 1.0, 2000)
    ref_x = np.interp(t_dense, t_old, mv_x)
    ref_y = np.interp(t_dense, t_old, mv_y)
    # World units are 1/10 meter (decimeters) -> divide by 10 for meters
    seg_m = np.sqrt(np.diff(ref_x) ** 2 + np.diff(ref_y) ** 2) / 10.0
    cum_m = np.concatenate(([0.0], np.cumsum(seg_m)))
    circuit_length_m = round(float(cum_m[-1]), 1) if len(cum_m) > 0 else 5000.0
    track_tree = cKDTree(np.column_stack((ref_x, ref_y)))

    # Detect DRS zones along mv_x/mv_y by matching car DRS-open timestamps to car positions
    drs_mask = np.zeros(len(mv_x), dtype=int)
    raw_tree = cKDTree(np.column_stack((mv_x, mv_y)))
    for dn in list(num_to_code.keys())[:5]:
        c_pts = car_by_num.get(dn, [])
        l_pts = loc_by_num.get(dn, [])
        if not c_pts or not l_pts:
            continue
        lt = np.array([p[0] for p in l_pts])
        lx = np.array([p[1] for p in l_pts])
        ly = np.array([p[2] for p in l_pts])
        drs_times = [p[0] for p in c_pts if p[3] in (10, 12, 14)]
        if drs_times:
            dx_s = np.interp(drs_times[:400], lt, lx)
            dy_s = np.interp(drs_times[:400], lt, ly)
            dists, idxs = raw_tree.query(np.column_stack((dx_s, dy_s)))
            for dist_val, idx_val in zip(dists, idxs):
                if dist_val < 300.0:
                    drs_mask[int(idx_val)] = 12

    from src.core.replay_exporter import serialize_track_geometry

    track_geom = serialize_track_geometry(
        {"X": mv_x, "Y": mv_y, "DRS": drs_mask},
        circuit_rotation=rotation_deg,
        max_points=800,
        track_width=200.0,
    )

    # Build 5 Hz timeline
    dt = 1.0 / target_fps
    duration_s = round(float(t_end_epoch - t0_epoch), 2)
    timeline = np.round(np.arange(0.0, duration_s, dt), 2)
    n_frames = len(timeline)

    # Organize laps, stints, and pits per driver
    laps_by_num: dict[int, list[tuple[float, int]]] = {n: [] for n in num_to_code}
    driver_max_lap: dict[int, int] = {n: 0 for n in num_to_code}
    for lp in laps_raw:
        dn = lp.get("driver_number")
        ls = _parse_iso(lp.get("date_start"))
        lnum = lp.get("lap_number")
        if dn in laps_by_num and lnum is not None:
            driver_max_lap[dn] = max(driver_max_lap[dn], int(lnum))
            if ls is not None:
                laps_by_num[dn].append((ls - t0_epoch, int(lnum)))

    stints_by_num: dict[int, list[tuple[int, int, int, int]]] = {n: [] for n in num_to_code}
    for st in stints_raw:
        dn = st.get("driver_number")
        if dn in stints_by_num:
            l_start = int(st.get("lap_start") or 1)
            l_end = int(st.get("lap_end") or max_lap_number)
            comp_int = get_tyre_compound_int(str(st.get("compound") or "UNKNOWN"))
            age0 = int(st.get("tyre_age_at_start") or 0)
            stints_by_num[dn].append((l_start, l_end, comp_int, age0))

    pits_by_num: dict[int, list[tuple[float, float]]] = {n: [] for n in num_to_code}
    for p in pits_raw:
        dn = p.get("driver_number")
        ps = _parse_iso(p.get("date"))
        dur = float(p.get("lane_duration") or p.get("pit_duration") or 20.0)
        if dn in pits_by_num and ps is not None:
            p_end = ps - t0_epoch
            pits_by_num[dn].append((p_end - dur, p_end))

    pos_events_by_num: dict[int, list[tuple[float, int]]] = {n: [] for n in num_to_code}
    if isinstance(pos_raw, list):
        for pr in pos_raw:
            dn = pr.get("driver_number")
            pval = pr.get("position")
            pts = _parse_iso(pr.get("date"))
            if dn in pos_events_by_num and pval is not None and pts is not None:
                pos_events_by_num[dn].append((pts - t0_epoch, int(pval)))
        for dn in pos_events_by_num:
            pos_events_by_num[dn].sort(key=lambda item: item[0])

    # Resample each driver onto timeline
    driver_arrays: dict[str, dict[str, np.ndarray]] = {}
    dnf_events: list[dict[str, Any]] = []

    for dn, code in num_to_code.items():
        l_pts = loc_by_num.get(dn, [])
        if len(l_pts) < 5:
            continue
        l_pts.sort(key=lambda item: item[0])
        lt = np.array([p[0] for p in l_pts], dtype=float)
        lx = np.array([p[1] for p in l_pts], dtype=float)
        ly = np.array([p[2] for p in l_pts], dtype=float)

        xs = np.interp(timeline, lt, lx)
        ys = np.interp(timeline, lt, ly)

        # Detect if driver retired early: max_lap < (max_lap_number - 2) and stationary near end
        d_max_lap = driver_max_lap.get(dn, 0)
        retired_early = d_max_lap < max(1, max_lap_number - 2)
        out_after_t = float("inf")
        if retired_early:
            diffs_xy = np.hypot(np.diff(lx), np.diff(ly))
            moving_idxs = np.where(diffs_xy > 30.0)[0]
            if len(moving_idxs) > 0:
                out_after_t = float(lt[moving_idxs[-1]]) + 5.0
                dnf_events.append(
                    {
                        "type": EVENT_DNF,
                        "time_s": round(max(0.0, out_after_t), 2),
                        "end_time_s": None,
                        "label": code,
                        "lap": d_max_lap or 1,
                    }
                )
            else:
                out_after_t = 0.0

        # Project (xs, ys) onto reference track and unwrap across start/finish cleanly
        _, nearest_idx = track_tree.query(np.column_stack((xs, ys)))
        along_m = cum_m[nearest_idx]
        rel_dist = np.round(along_m / max(1.0, circuit_length_m), 4)

        theta = (along_m / max(1.0, circuit_length_m)) * (2.0 * np.pi)
        unwrapped_m = np.unwrap(theta) * (max(1.0, circuit_length_m) / (2.0 * np.pi))
        # If the starting grid sits just behind cum_m[0] (along_m > 0.7 * L),
        # shift initial unwrapped_m back by 1 lap so pre-line grid positions are negative (< 0)
        # and crossing the start line passes cleanly through 0 -> +L -> +2L...
        if along_m[0] > 0.7 * circuit_length_m:
            unwrapped_m = unwrapped_m - circuit_length_m

        # Determine lap number at each timeline step
        drv_laps = sorted(laps_by_num.get(dn, []), key=lambda item: item[0])
        lap_arr = np.ones(n_frames, dtype=int)
        for l_time, l_num in drv_laps:
            lap_arr[timeline >= l_time] = l_num

        # Official FIA position series from /v1/position
        p_evts = pos_events_by_num.get(dn, [])
        official_pos_arr = np.full(n_frames, 99, dtype=int)
        if p_evts:
            # Initialize with earliest known position (starting grid)
            official_pos_arr[:] = p_evts[0][1]
            p_times = np.array([e[0] for e in p_evts], dtype=float)
            p_vals = np.array([e[1] for e in p_evts], dtype=int)
            idxs = np.searchsorted(p_times, timeline, side="right") - 1
            valid = idxs >= 0
            official_pos_arr[valid] = p_vals[idxs[valid]]

        # Stint tyre & tyre_life
        tyre_arr = np.full(n_frames, -1, dtype=int)
        tyre_life_arr = np.zeros(n_frames, dtype=int)
        for l_start, l_end, comp_int, age0 in sorted(stints_by_num.get(dn, [])):
            mask = (lap_arr >= l_start) & (lap_arr <= max(l_end, max_lap_number))
            tyre_arr[mask] = comp_int
            tyre_life_arr[mask] = age0 + (lap_arr[mask] - l_start)

        # Pit windows
        in_pit_arr = np.zeros(n_frames, dtype=int)
        for p0, p1 in pits_by_num.get(dn, []):
            in_pit_arr[(timeline >= p0) & (timeline <= p1)] = 1

        # Car telemetry (speed, gear, drs, throttle, brake)
        c_pts = car_by_num.get(dn, [])
        if len(c_pts) >= 2:
            c_pts.sort(key=lambda item: item[0])
            ct = np.array([p[0] for p in c_pts], dtype=float)
            spd_arr = np.interp(timeline, ct, [p[1] for p in c_pts])
            c_idx = np.clip(np.searchsorted(ct, timeline, side="right") - 1, 0, len(c_pts) - 1)
            gear_arr = np.array([c_pts[i][2] for i in c_idx], dtype=int)
            drs_arr = np.array([c_pts[i][3] for i in c_idx], dtype=int)
            thr_arr = np.interp(timeline, ct, [p[4] for p in c_pts])
            brk_arr = np.interp(timeline, ct, [p[5] for p in c_pts])
        else:
            spd_arr = np.maximum(0.0, np.gradient(unwrapped_m, dt) * 3.6)
            gear_arr = np.clip((spd_arr // 42).astype(int) + 1, 1, 8)
            drs_arr = np.zeros(n_frames, dtype=int)
            thr_arr = np.zeros(n_frames, dtype=float)
            brk_arr = np.zeros(n_frames, dtype=float)

        is_out_arr = (timeline >= out_after_t).astype(int)
        spd_arr[is_out_arr == 1] = 0.0
        thr_arr[is_out_arr == 1] = 0.0
        brk_arr[is_out_arr == 1] = 0.0
        drs_arr[is_out_arr == 1] = 0
        in_pit_arr[is_out_arr == 1] = 0
        rel_dist[is_out_arr == 1] = 1.0

        driver_arrays[code] = {
            "x": np.round(xs, 1),
            "y": np.round(ys, 1),
            "dist": unwrapped_m,
            "rel_dist": rel_dist,
            "lap": lap_arr,
            "official_pos": official_pos_arr,
            "tyre": tyre_arr,
            "tyre_life": tyre_life_arr,
            "speed": np.round(spd_arr, 1),
            "gear": gear_arr,
            "drs": drs_arr,
            "throttle": np.round(thr_arr, 1),
            "brake": np.round(brk_arr, 2),
            "in_pit": in_pit_arr,
            "is_out": is_out_arr,
        }

    # Normalize dist so P1 on the starting grid begins at dist = 0.0
    if driver_arrays:
        pole_code = min(
            driver_arrays.keys(),
            key=lambda c: (int(driver_arrays[c]["official_pos"][0]), -float(driver_arrays[c]["dist"][0])),
        )
        pole_start_m = float(driver_arrays[pole_code]["dist"][0])
        for arrs in driver_arrays.values():
            arrs["dist"] = np.round(arrs["dist"] - pole_start_m, 1)

    # Compute positions 1..N per frame using official FIA timing order (with retired cars at back)
    active_codes = list(driver_arrays.keys())
    pos_by_code = {c: np.zeros(n_frames, dtype=int) for c in active_codes}
    leader_lap_col = np.ones(n_frames, dtype=int)
    leader_dist_col = np.zeros(n_frames, dtype=float)

    for i in range(n_frames):
        order = sorted(
            active_codes,
            key=lambda c: (
                1 if driver_arrays[c]["is_out"][i] == 1 else 0,
                int(driver_arrays[c]["official_pos"][i]),
                -float(driver_arrays[c]["dist"][i]),
            ),
        )
        if order:
            lead_c = order[0]
            leader_lap_col[i] = int(driver_arrays[lead_c]["lap"][i])
            leader_dist_col[i] = float(driver_arrays[lead_c]["dist"][i])
        for rank, c in enumerate(order, start=1):
            pos_by_code[c][i] = rank

    # Track Statuses, Race Control & Events
    status_spans, formatted_rc, status_events = _build_track_status_and_rc(
        rc_raw, t0_epoch, duration_s
    )
    all_events = sorted(dnf_events + status_events, key=lambda e: e["time_s"])

    # Simulated Safety Car during status == "4"
    sc_active = np.zeros(n_frames, dtype=int)
    sc_x = np.zeros(n_frames, dtype=float)
    sc_y = np.zeros(n_frames, dtype=float)
    sc_phase = [""] * n_frames
    sc_alpha = np.zeros(n_frames, dtype=float)

    for sp in status_spans:
        if sp["status"] != "4":
            continue
        s0 = float(sp["start_time"])
        s1 = float(sp["end_time"] or duration_s)
        idxs = np.where((timeline >= s0) & (timeline <= s1))[0]
        for idx in idxs:
            t_val = float(timeline[idx])
            target_m = (leader_dist_col[idx] + 450.0) % max(1.0, circuit_length_m)
            r_idx = int(np.searchsorted(cum_m, target_m)) % len(ref_x)
            sc_active[idx] = 1
            sc_x[idx] = round(float(ref_x[r_idx]), 1)
            sc_y[idx] = round(float(ref_y[r_idx]), 1)
            if t_val - s0 < 4.0:
                sc_phase[idx] = "deploying"
                sc_alpha[idx] = round(min(1.0, (t_val - s0) / 4.0), 2)
            elif s1 - t_val < 4.0:
                sc_phase[idx] = "returning"
                sc_alpha[idx] = round(max(0.15, (s1 - t_val) / 4.0), 2)
            else:
                sc_phase[idx] = "on_track"
                sc_alpha[idx] = 1.0

    # Weather resampling
    weather_cols = None
    if weather_raw:
        w_pts = []
        for w in weather_raw:
            wt = _parse_iso(w.get("date"))
            if wt is not None:
                w_pts.append((wt - t0_epoch, w))
        if w_pts:
            w_pts.sort(key=lambda item: item[0])
            wt_arr = np.array([p[0] for p in w_pts], dtype=float)
            weather_cols = {
                "track_temp": np.round(
                    np.interp(timeline, wt_arr, [float(p[1].get("track_temperature") or 0) for p in w_pts]), 1
                ).tolist(),
                "air_temp": np.round(
                    np.interp(timeline, wt_arr, [float(p[1].get("air_temperature") or 0) for p in w_pts]), 1
                ).tolist(),
                "humidity": np.round(
                    np.interp(timeline, wt_arr, [float(p[1].get("humidity") or 0) for p in w_pts]), 1
                ).tolist(),
                "wind_speed": np.round(
                    np.interp(timeline, wt_arr, [float(p[1].get("wind_speed") or 0) for p in w_pts]), 1
                ).tolist(),
                "wind_direction": np.round(
                    np.interp(timeline, wt_arr, [float(p[1].get("wind_direction") or 0) for p in w_pts]), 0
                ).tolist(),
                "rain": [
                    1 if v >= 0.5 else 0
                    for v in np.interp(timeline, wt_arr, [float(p[1].get("rainfall") or 0) for p in w_pts])
                ],
            }

    # Assemble JSON-serializable columnar payload
    drivers_out = {}
    for code, arrs in driver_arrays.items():
        drivers_out[code] = {
            "x": arrs["x"].tolist(),
            "y": arrs["y"].tolist(),
            "dist": arrs["dist"].tolist(),
            "rel_dist": arrs["rel_dist"].tolist(),
            "lap": arrs["lap"].tolist(),
            "pos": pos_by_code[code].tolist(),
            "tyre": arrs["tyre"].tolist(),
            "tyre_life": arrs["tyre_life"].tolist(),
            "speed": arrs["speed"].tolist(),
            "gear": arrs["gear"].tolist(),
            "drs": arrs["drs"].tolist(),
            "throttle": arrs["throttle"].tolist(),
            "brake": arrs["brake"].tolist(),
            "in_pit": arrs["in_pit"].tolist(),
            "is_out": arrs["is_out"].tolist(),
        }

    country_name = str(session_meta.get("country_name") or "")
    location_name = str(session_meta.get("location") or session_meta.get("circuit_short_name") or "")
    event_title = (
        official_event_name
        or mv_meeting_name
        or (f"{location_name} Grand Prix" if location_name else f"{country_name} Grand Prix")
    )
    date_parsed = _parse_iso(session_meta.get("date_start"))
    date_str = (
        datetime.fromtimestamp(date_parsed, tz=timezone.utc).strftime("%B %d, %Y")
        if date_parsed
        else ""
    )

    manifest = {
        "schema_version": 1,
        "session_id": f"{year}_{round_number}_{session_type.upper()}",
        "session_info": {
            "event_name": event_title,
            "circuit_name": str(session_meta.get("circuit_short_name") or location_name),
            "country": country_name,
            "year": int(year),
            "round": int(round_number),
            "session_type": session_type.upper(),
            "session_name": "Sprint" if session_type.upper() == "S" else "Race",
            "date": date_str,
            "total_laps": int(max_lap_number),
            "circuit_length_m": circuit_length_m,
            "fps": target_fps,
            "total_frames": n_frames,
            "duration_s": duration_s,
        },
        "track": track_geom,
        "drivers": {c: drivers_meta[c] for c in active_codes if c in drivers_meta},
        "track_statuses": status_spans,
        "race_events": all_events,
        "race_control_messages": formatted_rc,
        "standings": {
            "current_drivers": {},
            "current_constructors": {},
            "live_drivers": {},
            "live_constructors": {},
        },
    }

    frames = {
        "fps": target_fps,
        "t": timeline.tolist(),
        "lap": leader_lap_col.tolist(),
        "drivers": drivers_out,
        "weather": weather_cols,
        "safety_car": (
            {
                "active": sc_active.tolist(),
                "x": sc_x.tolist(),
                "y": sc_y.tolist(),
                "phase": sc_phase,
                "alpha": sc_alpha.tolist(),
            }
            if int(np.sum(sc_active)) > 0
            else None
        ),
    }

    return manifest, frames
