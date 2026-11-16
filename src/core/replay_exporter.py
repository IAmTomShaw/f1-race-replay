"""
Headless web replay exporter for F1 Race Replay.

Transforms FastF1 session telemetry (from ``src.f1_data``) into a compact two-part
web bundle:
  1. ``manifest.json`` — track geometry, DRS zones, drivers, race events,
     race control messages, track statuses, and championship standings.
  2. ``frames.json.gz`` — downsampled (default 5 Hz) columnar arrays designed for
     60 FPS client-side linear interpolation (~3–6 MB gzipped for a full Grand Prix).
"""

from __future__ import annotations

import gzip
import json
import math
import os
import re
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from src.core.track_geometry import (
    EVENT_DNF,
    EVENT_SAFETY_CAR,
    EVENT_YELLOW_FLAG,
    build_track_from_example_lap,
    extract_race_events,
)

ProgressCallback = Optional[Callable[[str, int], None]]


def extract_circuit_name(event_name: str) -> str:
    if not event_name:
        return ""
    suffixes = [
        r"\s+Grand\s+Prix$",
        r"\s+GP$",
        r"\s+Grand\s+Prix\s+$",
        r"\s+GP\s+$",
    ]
    name = event_name
    for suffix in suffixes:
        name = re.sub(suffix, "", name, flags=re.IGNORECASE)
    name = name.strip()
    return name or event_name


def _rgb_to_hex(rgb) -> str:
    if isinstance(rgb, str) and rgb.startswith("#"):
        return rgb
    try:
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        return f"#{r:02X}{g:02X}{b:02X}"
    except (TypeError, ValueError, IndexError):
        return "#9CA3AF"


def _resample_polyline(xs, ys, num_points: int = 1000) -> tuple[list[float], list[float]]:
    xs_arr = np.asarray(xs, dtype=float)
    ys_arr = np.asarray(ys, dtype=float)
    if len(xs_arr) == 0:
        return [], []
    if len(xs_arr) <= num_points:
        return (
            [round(float(v), 1) for v in xs_arr],
            [round(float(v), 1) for v in ys_arr],
        )
    t_old = np.linspace(0.0, 1.0, len(xs_arr))
    t_new = np.linspace(0.0, 1.0, num_points)
    xs_i = np.interp(t_new, t_old, xs_arr)
    ys_i = np.interp(t_new, t_old, ys_arr)
    return (
        [round(float(v), 1) for v in xs_i],
        [round(float(v), 1) for v in ys_i],
    )


def serialize_track_geometry(
    example_lap,
    circuit_rotation: float = 0.0,
    max_points: int = 1000,
    track_width: float = 200.0,
) -> dict:
    """Serialize track edges, bounds, and DRS outer polylines into JSON-ready lists."""
    (
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
        raw_drs_zones,
    ) = build_track_from_example_lap(example_lap, track_width=track_width)

    x_outer_np = np.asarray(x_outer, dtype=float)
    y_outer_np = np.asarray(y_outer, dtype=float)

    serialized_drs_zones = []
    for zone in raw_drs_zones:
        s_idx = int(zone["start"]["index"])
        e_idx = min(int(zone["end"]["index"]) + 1, len(x_outer_np))
        if e_idx - s_idx < 2:
            continue
        zx, zy = _resample_polyline(
            x_outer_np[s_idx:e_idx],
            y_outer_np[s_idx:e_idx],
            num_points=min(120, e_idx - s_idx),
        )
        serialized_drs_zones.append({"x": zx, "y": zy})

    rx_ref, ry_ref = _resample_polyline(plot_x_ref, plot_y_ref, num_points=max_points)
    rx_in, ry_in = _resample_polyline(x_inner, y_inner, num_points=max_points)
    rx_out, ry_out = _resample_polyline(x_outer, y_outer, num_points=max_points)

    return {
        "x_ref": rx_ref,
        "y_ref": ry_ref,
        "x_inner": rx_in,
        "y_inner": ry_in,
        "x_outer": rx_out,
        "y_outer": ry_out,
        "x_min": round(float(x_min), 1),
        "x_max": round(float(x_max), 1),
        "y_min": round(float(y_min), 1),
        "y_max": round(float(y_max), 1),
        "rotation_deg": round(float(circuit_rotation or 0.0), 2),
        "drs_zones": serialized_drs_zones,
    }


def pack_frames_columnar(
    frames: list[dict],
    source_fps: float = 25.0,
    stride: int = 5,
) -> dict:
    """
    Downsample per-frame nested dicts into compact columnar arrays.
    """
    if not frames:
        return {
            "fps": round(source_fps / max(1, stride), 3),
            "t": [],
            "lap": [],
            "drivers": {},
            "weather": None,
            "safety_car": None,
        }

    stride = max(1, int(stride))
    indices = list(range(0, len(frames), stride))
    if indices[-1] != len(frames) - 1:
        indices.append(len(frames) - 1)

    all_codes_ordered: list[str] = []
    seen_codes: set[str] = set()
    for f in frames[:: max(1, stride * 5)]:
        for code in f.get("drivers", {}).keys():
            if code not in seen_codes:
                seen_codes.add(code)
                all_codes_ordered.append(code)
    for code in frames[0].get("drivers", {}).keys():
        if code not in seen_codes:
            seen_codes.add(code)
            all_codes_ordered.append(code)

    t_col: list[float] = []
    lap_col: list[int] = []

    driver_cols: dict[str, dict[str, list]] = {
        code: {
            "x": [],
            "y": [],
            "dist": [],
            "rel_dist": [],
            "lap": [],
            "pos": [],
            "tyre": [],
            "tyre_life": [],
            "speed": [],
            "gear": [],
            "drs": [],
            "throttle": [],
            "brake": [],
            "in_pit": [],
            "is_out": [],
        }
        for code in all_codes_ordered
    }
    last_known: dict[str, dict] = {}

    has_weather = any("weather" in frames[idx] for idx in indices)
    weather_cols = (
        {
            "track_temp": [],
            "air_temp": [],
            "humidity": [],
            "wind_speed": [],
            "wind_direction": [],
            "rain": [],
        }
        if has_weather
        else None
    )

    has_sc = any(frames[idx].get("safety_car") is not None for idx in indices)
    sc_cols = (
        {
            "active": [],
            "x": [],
            "y": [],
            "phase": [],
            "alpha": [],
        }
        if has_sc
        else None
    )

    for idx in indices:
        frame = frames[idx]
        t_col.append(round(float(frame.get("t", 0.0)), 2))
        lap_col.append(int(frame.get("lap", 1)))

        f_drivers = frame.get("drivers", {})
        fallback_pos = len(f_drivers) + 1

        for code in all_codes_ordered:
            cols = driver_cols[code]
            car = f_drivers.get(code)
            if car is not None:
                last_known[code] = car
                rel_dist = float(car.get("rel_dist", 0.0))
                is_out = 1 if (car.get("is_out") or rel_dist == 1.0) else 0
                cols["x"].append(round(float(car.get("x", 0.0)), 1))
                cols["y"].append(round(float(car.get("y", 0.0)), 1))
                cols["dist"].append(round(float(car.get("dist", 0.0)), 1))
                cols["rel_dist"].append(round(rel_dist, 4))
                cols["lap"].append(int(car.get("lap", 1)))
                cols["pos"].append(int(car.get("position", fallback_pos)))
                cols["tyre"].append(int(round(float(car.get("tyre", -1)))))
                cols["tyre_life"].append(int(round(float(car.get("tyre_life", 0)))))
                cols["speed"].append(round(float(car.get("speed", 0.0)), 1))
                cols["gear"].append(int(car.get("gear", 0)))
                cols["drs"].append(int(car.get("drs", 0)))
                cols["throttle"].append(round(float(car.get("throttle", 0.0)), 1))
                cols["brake"].append(round(float(car.get("brake", 0.0)), 2))
                cols["in_pit"].append(1 if car.get("in_pit") else 0)
                cols["is_out"].append(is_out)
            else:
                prev = last_known.get(code, {})
                cols["x"].append(round(float(prev.get("x", 0.0)), 1))
                cols["y"].append(round(float(prev.get("y", 0.0)), 1))
                cols["dist"].append(round(float(prev.get("dist", 0.0)), 1))
                cols["rel_dist"].append(1.0)
                cols["lap"].append(int(prev.get("lap", 1)))
                cols["pos"].append(fallback_pos)
                cols["tyre"].append(int(round(float(prev.get("tyre", -1)))))
                cols["tyre_life"].append(int(round(float(prev.get("tyre_life", 0)))))
                cols["speed"].append(0.0)
                cols["gear"].append(0)
                cols["drs"].append(0)
                cols["throttle"].append(0.0)
                cols["brake"].append(0.0)
                cols["in_pit"].append(0)
                cols["is_out"].append(1)
                fallback_pos += 1

        if weather_cols is not None:
            w = frame.get("weather") or {}
            weather_cols["track_temp"].append(
                round(float(w["track_temp"]), 1) if w.get("track_temp") is not None else None
            )
            weather_cols["air_temp"].append(
                round(float(w["air_temp"]), 1) if w.get("air_temp") is not None else None
            )
            weather_cols["humidity"].append(
                round(float(w["humidity"]), 1) if w.get("humidity") is not None else None
            )
            weather_cols["wind_speed"].append(
                round(float(w["wind_speed"]), 1) if w.get("wind_speed") is not None else None
            )
            weather_cols["wind_direction"].append(
                round(float(w["wind_direction"]), 0)
                if w.get("wind_direction") is not None
                else None
            )
            weather_cols["rain"].append(1 if w.get("rain_state") == "RAINING" else 0)

        if sc_cols is not None:
            sc = frame.get("safety_car")
            if sc is not None:
                sc_cols["active"].append(1)
                sc_cols["x"].append(round(float(sc.get("x", 0.0)), 1))
                sc_cols["y"].append(round(float(sc.get("y", 0.0)), 1))
                sc_cols["phase"].append(str(sc.get("phase", "on_track")))
                sc_cols["alpha"].append(round(float(sc.get("alpha", 1.0)), 2))
            else:
                sc_cols["active"].append(0)
                sc_cols["x"].append(0.0)
                sc_cols["y"].append(0.0)
                sc_cols["phase"].append("")
                sc_cols["alpha"].append(0.0)

    return {
        "fps": round(source_fps / stride, 3),
        "t": t_col,
        "lap": lap_col,
        "drivers": driver_cols,
        "weather": weather_cols,
        "safety_car": sc_cols,
    }


def _bundle_dir(output_root: str | Path, year: int, round_number: int, session_type: str) -> Path:
    return Path(output_root) / f"{year}_{round_number}_{session_type.upper()}"


def get_cached_bundle_paths(
    year: int,
    round_number: int,
    session_type: str = "R",
    output_root: str | Path = "computed_data/web",
) -> Optional[tuple[Path, Path]]:
    folder = _bundle_dir(output_root, year, round_number, session_type)
    manifest_path = folder / "manifest.json"
    frames_path = folder / "frames.json.gz"
    if (
        manifest_path.exists()
        and frames_path.exists()
        and manifest_path.stat().st_size > 0
        and frames_path.stat().st_size > 0
    ):
        return manifest_path, frames_path
    return None


def _maybe_upload_to_s3(folder: Path, key_prefix: str) -> Optional[dict[str, str]]:
    """Optional hook to upload manifest + compressed frames to Cloudflare R2 / S3."""
    bucket = os.environ.get("R2_BUCKET") or os.environ.get("S3_BUCKET")
    if not bucket:
        return None
    try:
        import boto3

        endpoint_url = os.environ.get("R2_ENDPOINT_URL") or os.environ.get("S3_ENDPOINT_URL")
        public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
        s3 = boto3.client("s3", endpoint_url=endpoint_url)

        s3.upload_file(
            str(folder / "manifest.json"),
            bucket,
            f"{key_prefix}/manifest.json",
            ExtraArgs={"ContentType": "application/json", "CacheControl": "public, max-age=86400"},
        )
        s3.upload_file(
            str(folder / "frames.json.gz"),
            bucket,
            f"{key_prefix}/frames.json.gz",
            ExtraArgs={
                "ContentType": "application/json",
                "ContentEncoding": "gzip",
                "CacheControl": "public, max-age=86400",
            },
        )
        if public_base:
            return {
                "manifest_url": f"{public_base}/{key_prefix}/manifest.json",
                "frames_url": f"{public_base}/{key_prefix}/frames.json.gz",
            }
    except Exception as exc:
        print(f"Warning: S3/R2 upload skipped/failed: {exc}")
    return None


def _write_bundle_files(
    manifest: dict,
    packed_frames: dict,
    year: int,
    round_number: int,
    session_type: str,
    output_root: str | Path,
    progress_cb: ProgressCallback = None,
) -> tuple[Path, Path]:
    if progress_cb:
        progress_cb("Compressing web replay bundle...", 94)

    folder = _bundle_dir(output_root, year, round_number, session_type)
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    frames_path = folder / "frames.json.gz"
    manifest_tmp = folder / "manifest.json.tmp"
    frames_tmp = folder / "frames.json.gz.tmp"

    frames_bytes = json.dumps(packed_frames, separators=(",", ":")).encode("utf-8")
    with gzip.open(frames_tmp, "wb", compresslevel=6) as ff:
        ff.write(frames_bytes)

    with open(manifest_tmp, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, separators=(",", ":"))

    # Atomic replace so pollers never observe half-written files
    os.replace(frames_tmp, frames_path)
    os.replace(manifest_tmp, manifest_path)

    _maybe_upload_to_s3(folder, f"sessions/{year}_{round_number}_{session_type}")

    if progress_cb:
        progress_cb("Ready", 100)

    return manifest_path, frames_path


def export_race_bundle(
    year: int,
    round_number: int,
    session_type: str = "R",
    stride: int = 5,
    refresh: bool = False,
    output_root: str | Path = "computed_data/web",
    progress_cb: ProgressCallback = None,
) -> tuple[Path, Path]:
    """
    Compute (or load cached) race/sprint session and write ``manifest.json``
    + ``frames.json.gz`` to ``output_root``.

    Uses OpenF1 automatically for 2023+ sessions when F1 account credentials
    (``F1_USERNAME`` / ``F1_PASSWORD``) are not set, avoiding F1 CloudFront 401s.
    """
    session_type = session_type.upper()
    if session_type not in ("R", "S"):
        raise ValueError(f"Unsupported race replay session_type '{session_type}' (expected 'R' or 'S').")

    cached = get_cached_bundle_paths(year, round_number, session_type, output_root=output_root)
    if cached and not refresh:
        if progress_cb:
            progress_cb("Loaded cached web bundle", 100)
        return cached

    has_f1_creds = bool(os.environ.get("F1_USERNAME") and os.environ.get("F1_PASSWORD"))
    target_fps = round(25.0 / max(1, stride), 3)

    if year >= 2023 and not has_f1_creds:
        from src.core.openf1_loader import build_openf1_bundle

        manifest, packed_frames = build_openf1_bundle(
            year=year,
            round_number=round_number,
            session_type=session_type,
            target_fps=target_fps,
            progress_cb=progress_cb,
        )
        return _write_bundle_files(
            manifest, packed_frames, year, round_number, session_type, output_root, progress_cb
        )

    from src.f1_data import (
        FPS,
        _get_current_championship_standings,
        enable_cache,
        get_circuit_rotation,
        get_live_standings,
        get_race_telemetry,
        load_session,
    )

    try:
        if progress_cb:
            progress_cb(f"Loading FastF1 session ({year} Round {round_number} {session_type})...", 10)

        enable_cache()
        session = load_session(year, round_number, session_type)
        if session is None:
            raise RuntimeError(f"Unable to load FastF1 session {year} R{round_number} {session_type}")

        if progress_cb:
            progress_cb("Extracting & resampling 20-driver telemetry...", 30)

        race_telemetry = get_race_telemetry(session, session_type=session_type)
        raw_frames = race_telemetry["frames"]
        if not raw_frames:
            raise RuntimeError("Session contained no telemetry frames.")
    except Exception as fastf1_exc:
        if year >= 2023:
            from src.core.openf1_loader import build_openf1_bundle

            manifest, packed_frames = build_openf1_bundle(
                year=year,
                round_number=round_number,
                session_type=session_type,
                target_fps=target_fps,
                progress_cb=progress_cb,
            )
            return _write_bundle_files(
                manifest, packed_frames, year, round_number, session_type, output_root, progress_cb
            )
        raise RuntimeError(
            f"FastF1 telemetry unavailable for {year} R{round_number} "
            f"(Formula 1 requires F1_USERNAME & F1_PASSWORD env vars for archival F1 streams prior to 2023): {fastf1_exc}"
        ) from fastf1_exc

    if progress_cb:
        progress_cb("Building circuit geometry & DRS zones...", 65)

    example_lap = None
    try:
        quali_session = load_session(year, round_number, "Q")
        if quali_session is not None and len(quali_session.laps) > 0:
            fastest_quali = quali_session.laps.pick_fastest()
            if fastest_quali is not None:
                quali_tel = fastest_quali.get_telemetry()
                if "DRS" in quali_tel.columns:
                    example_lap = quali_tel
    except Exception:
        example_lap = None

    if example_lap is None:
        fastest_race = session.laps.pick_fastest()
        if fastest_race is None:
            raise RuntimeError("No valid fastest lap found to build circuit layout.")
        example_lap = fastest_race.get_telemetry()

    circuit_rotation = get_circuit_rotation(session)
    track_geom = serialize_track_geometry(example_lap, circuit_rotation=circuit_rotation)

    if progress_cb:
        progress_cb("Computing championship standings & race events...", 80)

    current_drv_standings, current_con_standings = _get_current_championship_standings(session)
    live_drv_standings, live_con_standings = get_live_standings(
        current_drv_standings, current_con_standings, session
    )

    driver_colors_rgb = race_telemetry.get("driver_colors", {})
    drivers_meta: dict[str, dict] = {}
    for drv_num in session.drivers:
        info = session.get_driver(drv_num)
        code = str(info.get("Abbreviation") or drv_num)
        drivers_meta[code] = {
            "code": code,
            "number": str(info.get("DriverNumber") or drv_num),
            "full_name": str(info.get("FullName") or code),
            "team": str(info.get("TeamName") or ""),
            "color": _rgb_to_hex(driver_colors_rgb.get(code, (156, 163, 175))),
        }

    packed_frames = pack_frames_columnar(raw_frames, source_fps=float(FPS), stride=stride)
    duration_s = float(packed_frames["t"][-1]) if packed_frames["t"] else 0.0

    raw_events = extract_race_events(
        raw_frames,
        race_telemetry.get("track_statuses", []),
        race_telemetry.get("total_laps", 0),
        fps=float(FPS),
    )
    normalized_events = []
    for ev in raw_events:
        start_s = float(
            ev.get("start_time_s")
            if ev.get("start_time_s") is not None
            else ev.get("time_s", ev.get("frame", 0) / float(FPS))
        )
        end_s = (
            float(ev["end_time_s"])
            if ev.get("end_time_s") is not None
            else (
                float(ev["end_frame"]) / float(FPS)
                if ev.get("end_frame") is not None
                else None
            )
        )
        normalized_events.append(
            {
                "type": ev["type"],
                "time_s": round(max(0.0, start_s), 2),
                "end_time_s": round(min(duration_s, end_s), 2) if end_s is not None else None,
                "label": ev.get("label", ""),
                "lap": ev.get("lap"),
            }
        )

    event_name = str(session.event.get("EventName", ""))
    event_date = session.event.get("EventDate")
    date_str = event_date.strftime("%B %d, %Y") if hasattr(event_date, "strftime") else str(event_date or "")
    circuit_length_m = (
        round(float(example_lap["Distance"].max()), 1)
        if example_lap is not None and "Distance" in example_lap
        else None
    )

    manifest = {
        "schema_version": 1,
        "session_id": f"{year}_{round_number}_{session_type}",
        "session_info": {
            "event_name": event_name,
            "circuit_name": extract_circuit_name(event_name),
            "country": str(session.event.get("Country", "")),
            "year": int(year),
            "round": int(round_number),
            "session_type": session_type,
            "session_name": "Sprint" if session_type == "S" else "Race",
            "date": date_str,
            "total_laps": int(race_telemetry.get("total_laps", 0)),
            "circuit_length_m": circuit_length_m,
            "fps": packed_frames["fps"],
            "total_frames": len(packed_frames["t"]),
            "duration_s": round(duration_s, 2),
        },
        "track": track_geom,
        "drivers": drivers_meta,
        "track_statuses": race_telemetry.get("track_statuses", []),
        "race_events": normalized_events,
        "race_control_messages": race_telemetry.get("race_control_messages", []),
        "standings": {
            "current_drivers": current_drv_standings,
            "current_constructors": current_con_standings,
            "live_drivers": {str(k): v for k, v in (live_drv_standings or {}).items()},
            "live_constructors": {str(k): v for k, v in (live_con_standings or {}).items()},
        },
    }

    if progress_cb:
        progress_cb("Compressing web replay bundle...", 92)

    folder = _bundle_dir(output_root, year, round_number, session_type)
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    frames_path = folder / "frames.json.gz"

    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, separators=(",", ":"))

    frames_bytes = json.dumps(packed_frames, separators=(",", ":")).encode("utf-8")
    with gzip.open(frames_path, "wb", compresslevel=6) as ff:
        ff.write(frames_bytes)

    _maybe_upload_to_s3(folder, f"sessions/{year}_{round_number}_{session_type}")

    if progress_cb:
        progress_cb("Ready", 100)

    return manifest_path, frames_path


def build_demo_bundle() -> tuple[dict, dict]:
    """
    Build an instant, self-contained 20-driver F1 Grand Prix replay bundle
    (10 laps at 5 Hz with DRS zones, pit stops, a DNF, and a Safety Car period)
    so the web app works out-of-the-box in <50ms without waiting on FastF1.
    """
    n_track = 600
    theta = np.linspace(0.0, 2.0 * np.pi, n_track, endpoint=False)

    # Multi-harmonic closed Grand Prix circuit (~5,400m length, realistic straights + hairpins)
    r = (
        1650.0
        + 420.0 * np.cos(2 * theta - 0.4)
        + 290.0 * np.sin(3 * theta + 0.8)
        + 180.0 * np.cos(5 * theta - 1.1)
    )
    x_ref = r * np.cos(theta) * 1.25
    y_ref = r * np.sin(theta) * 0.82

    # Compute arc length and curvature to derive realistic speed/gear/throttle/brake profiles
    dx = np.gradient(np.append(x_ref, x_ref[0]))[:-1]
    dy = np.gradient(np.append(y_ref, y_ref[0]))[:-1]
    ddx = np.gradient(np.append(dx, dx[0]))[:-1]
    ddy = np.gradient(np.append(dy, dy[0]))[:-1]

    seg_ds = np.sqrt(
        np.diff(np.append(x_ref, x_ref[0])) ** 2 + np.diff(np.append(y_ref, y_ref[0])) ** 2
    )
    cum_s = np.concatenate(([0.0], np.cumsum(seg_ds[:-1])))
    circuit_length_m = 5412.0
    scale_factor = circuit_length_m / float(np.sum(seg_ds))
    x_ref *= scale_factor
    y_ref *= scale_factor
    cum_s *= scale_factor

    curvature = np.abs(dx * ddy - dy * ddx) / np.maximum((dx**2 + dy**2) ** 1.5, 1e-6)
    curv_norm = np.clip(curvature / np.percentile(curvature, 92), 0.0, 1.0)
    # Smooth curvature slightly
    kernel = np.ones(15) / 15.0
    curv_smooth = np.convolve(np.concatenate([curv_norm[-7:], curv_norm, curv_norm[:7]]), kernel, mode="valid")

    base_speed_profile = 328.0 - 225.0 * (curv_smooth**0.75)

    # Two DRS zones on the lowest-curvature sections
    drs_flag = np.zeros(n_track, dtype=int)
    drs_flag[35:115] = 12
    drs_flag[325:405] = 12

    example_lap = {"X": x_ref, "Y": y_ref, "DRS": drs_flag}
    track_geom = serialize_track_geometry(example_lap, circuit_rotation=14.0, max_points=600, track_width=165.0)

    roster = [
        ("VER", "1", "Max Verstappen", "Red Bull Racing", "#3671C6", 1.004, 1, 5),
        ("NOR", "4", "Lando Norris", "McLaren", "#FF8000", 1.003, 0, 4),
        ("LEC", "16", "Charles Leclerc", "Ferrari", "#E80020", 1.001, 0, 5),
        ("PIA", "81", "Oscar Piastri", "McLaren", "#FF8000", 1.000, 1, 6),
        ("HAM", "44", "Lewis Hamilton", "Ferrari", "#E80020", 0.998, 1, 5),
        ("RUS", "63", "George Russell", "Mercedes", "#27F4D2", 0.997, 1, 6),
        ("ANT", "12", "Kimi Antonelli", "Mercedes", "#27F4D2", 0.994, 0, 4),
        ("SAI", "55", "Carlos Sainz", "Williams", "#64C4FF", 0.992, 1, 6),
        ("ALB", "23", "Alex Albon", "Williams", "#64C4FF", 0.990, 2, 7),
        ("ALO", "14", "Fernando Alonso", "Aston Martin", "#229971", 0.989, 1, 5),
        ("GAS", "10", "Pierre Gasly", "Alpine", "#0093CC", 0.987, 0, 0),  # DNF on lap 4
        ("TSU", "22", "Yuki Tsunoda", "Red Bull Racing", "#3671C6", 0.986, 0, 4),
        ("HAD", "6", "Isack Hadjar", "Racing Bulls", "#6692FF", 0.984, 1, 6),
        ("LAW", "30", "Liam Lawson", "Racing Bulls", "#6692FF", 0.983, 2, 7),
        ("HUL", "27", "Nico Hulkenberg", "Kick Sauber", "#52E252", 0.981, 1, 5),
        ("STR", "18", "Lance Stroll", "Aston Martin", "#229971", 0.980, 2, 6),
        ("OCO", "31", "Esteban Ocon", "Haas F1 Team", "#B6BABD", 0.979, 1, 5),
        ("BEA", "87", "Oliver Bearman", "Haas F1 Team", "#B6BABD", 0.978, 0, 4),
        ("DOO", "7", "Jack Doohan", "Alpine", "#0093CC", 0.976, 1, 6),
        ("BOR", "5", "Gabriel Bortoleto", "Kick Sauber", "#52E252", 0.975, 2, 7),
    ]

    drivers_meta = {
        code: {
            "code": code,
            "number": num,
            "full_name": name,
            "team": team,
            "color": color,
        }
        for code, num, name, team, color, _, _, _ in roster
    }

    fps = 5.0
    dt = 1.0 / fps
    total_laps = 8
    total_race_dist = total_laps * circuit_length_m

    # Helper to sample track coordinates & kinematics at along-track distance s (in [0, circuit_length_m))
    x_closed = np.append(x_ref, x_ref[0])
    y_closed = np.append(y_ref, y_ref[0])
    s_closed = np.append(cum_s, circuit_length_m)
    spd_closed = np.append(base_speed_profile, base_speed_profile[0])

    # Pre-simulate timeline until leader finishes + 8s
    max_steps = 3600  # up to 12 minutes
    t_list: list[float] = []
    leader_lap_list: list[int] = []

    sc_start_s = 232.0
    sc_end_s = 322.0
    yellow_start_s = 220.0

    driver_state = {}
    pole_dist = 120.0
    for idx, (code, _, _, _, _, pace, start_tyre, pit_lap) in enumerate(roster):
        # Stagger starting grid 6 meters apart behind P1's start box
        driver_state[code] = {
            "dist": max(0.0, pole_dist - idx * 6.0),
            "pace": pace,
            "tyre": start_tyre,
            "tyre_life": 0,
            "pit_lap": pit_lap,
            "pitted": False,
            "pit_timer": 0.0,
            "retired": False,
            "finished": False,
        }

    driver_cols = {
        code: {
            "x": [],
            "y": [],
            "dist": [],
            "rel_dist": [],
            "lap": [],
            "pos": [],
            "tyre": [],
            "tyre_life": [],
            "speed": [],
            "gear": [],
            "drs": [],
            "throttle": [],
            "brake": [],
            "in_pit": [],
            "is_out": [],
        }
        for code, *_ in roster
    }
    weather_cols = {
        "track_temp": [],
        "air_temp": [],
        "humidity": [],
        "wind_speed": [],
        "wind_direction": [],
        "rain": [],
    }
    sc_cols = {"active": [], "x": [], "y": [], "phase": [], "alpha": []}

    finish_timer = None
    dnf_time_s = None

    lights_out_s = 6.0

    for step in range(max_steps):
        t = round(step * dt, 2)
        t_list.append(t)

        pre_start = t < lights_out_s
        in_yellow = yellow_start_s <= t < sc_start_s
        in_sc = sc_start_s <= t <= sc_end_s

        # Update each car
        step_cars = []
        for idx, (code, *_rest) in enumerate(roster):
            st = driver_state[code]
            lap_num = min(total_laps, max(1, int((st["dist"] - pole_dist) // circuit_length_m) + 1))
            s_mod = float(st["dist"] % circuit_length_m)

            # Trigger GAS DNF around t = 220s
            if code == "GAS" and t >= yellow_start_s and not st["retired"]:
                st["retired"] = True
                dnf_time_s = t

            if pre_start:
                spd_kph = 0.0
                in_pit = 0
                is_out = 0
            elif st["retired"]:
                spd_kph = 0.0
                in_pit = 0
                is_out = 1
            elif st["finished"]:
                spd_kph = 140.0
                st["dist"] += (spd_kph / 3.6) * dt
                in_pit = 0
                is_out = 0
            else:
                # Check pit entry near end of pit_lap
                if (
                    st["pit_lap"] > 0
                    and not st["pitted"]
                    and lap_num == st["pit_lap"]
                    and s_mod > circuit_length_m - 180.0
                ):
                    st["pitted"] = True
                    st["pit_timer"] = 16.0  # pit lane loss

                if st["pit_timer"] > 0.0:
                    st["pit_timer"] = max(0.0, st["pit_timer"] - dt)
                    spd_kph = 80.0
                    in_pit = 1
                    if st["pit_timer"] == 0.0:
                        st["tyre"] = 2 if st["tyre"] == 1 else 1
                        st["tyre_life"] = 1
                else:
                    in_pit = 0
                    track_spd = float(np.interp(s_mod, s_closed, spd_closed))
                    tyre_bonus = 1.008 if st["tyre"] == 0 else (1.0 if st["tyre"] == 1 else 0.994)
                    launch_ramp = min(1.0, (t - lights_out_s) / 3.5)
                    spd_kph = track_spd * st["pace"] * tyre_bonus * launch_ramp
                    if in_sc:
                        spd_kph = min(spd_kph, 185.0)
                    elif in_yellow:
                        spd_kph = min(spd_kph, 225.0)

                prev_lap = max(1, int((st["dist"] - pole_dist) // circuit_length_m) + 1)
                st["dist"] += (spd_kph / 3.6) * dt
                new_lap = max(1, int((st["dist"] - pole_dist) // circuit_length_m) + 1)
                if new_lap > prev_lap and not in_pit:
                    st["tyre_life"] += 1
                if (st["dist"] - pole_dist) >= total_race_dist:
                    st["finished"] = True
                is_out = 0

            s_mod = float(st["dist"] % circuit_length_m)
            x_car = float(np.interp(s_mod, s_closed, x_closed))
            y_car = float(np.interp(s_mod, s_closed, y_closed))

            # Derive gear, throttle, brake, DRS from speed & acceleration gradient
            s_ahead = (s_mod + 35.0) % circuit_length_m
            spd_ahead = float(np.interp(s_ahead, s_closed, spd_closed))
            delta_spd = spd_ahead - float(np.interp(s_mod, s_closed, spd_closed))

            if pre_start or is_out:
                gear, throttle, brake, drs_active = 0, 0.0, 0.0, 0
            else:
                gear = int(np.clip(math.floor(spd_kph / 41.0) + 1, 1, 8))
                if delta_spd < -6.0 and not in_pit:
                    throttle = round(max(0.0, 25.0 + delta_spd * 2.0), 1)
                    brake = 1.0
                else:
                    throttle = 100.0 if spd_kph > 210.0 and not in_pit else 78.0
                    brake = 0.0

                track_idx = int((s_mod / circuit_length_m) * n_track) % n_track
                drs_active = (
                    12
                    if (
                        drs_flag[track_idx] in (10, 12, 14)
                        and lap_num >= 2
                        and not in_sc
                        and not in_yellow
                        and not in_pit
                        and idx > 0
                    )
                    else 0
                )

            step_cars.append(
                {
                    "code": code,
                    "x": x_car,
                    "y": y_car,
                    "dist": round(st["dist"] - pole_dist, 1),
                    "rel_dist": 1.0 if is_out else round(s_mod / circuit_length_m, 4),
                    "lap": min(total_laps, max(1, int((st["dist"] - pole_dist) // circuit_length_m) + 1)),
                    "tyre": st["tyre"],
                    "tyre_life": st["tyre_life"],
                    "speed": spd_kph,
                    "gear": gear,
                    "drs": drs_active,
                    "throttle": throttle,
                    "brake": brake,
                    "in_pit": in_pit,
                    "is_out": is_out,
                }
            )

        # Sort active cars ahead of retired cars, then by distance covered
        step_cars.sort(key=lambda c: (0 if c["is_out"] else 1, c["dist"]), reverse=True)
        leader = step_cars[0]
        leader_lap_list.append(int(leader["lap"]))

        for pos_idx, car in enumerate(step_cars, start=1):
            cols = driver_cols[car["code"]]
            cols["x"].append(round(car["x"], 1))
            cols["y"].append(round(car["y"], 1))
            cols["dist"].append(round(car["dist"], 1))
            cols["rel_dist"].append(car["rel_dist"])
            cols["lap"].append(car["lap"])
            cols["pos"].append(pos_idx)
            cols["tyre"].append(car["tyre"])
            cols["tyre_life"].append(car["tyre_life"])
            cols["speed"].append(round(car["speed"], 1))
            cols["gear"].append(car["gear"])
            cols["drs"].append(car["drs"])
            cols["throttle"].append(round(car["throttle"], 1))
            cols["brake"].append(round(car["brake"], 2))
            cols["in_pit"].append(car["in_pit"])
            cols["is_out"].append(car["is_out"])

        # Weather
        weather_cols["track_temp"].append(round(31.4 - 0.004 * t, 1))
        weather_cols["air_temp"].append(round(22.8 - 0.002 * t, 1))
        weather_cols["humidity"].append(round(54.0 + 0.01 * t, 1))
        weather_cols["wind_speed"].append(round(2.4 + 0.6 * math.sin(t / 45.0), 1))
        weather_cols["wind_direction"].append(215.0)
        weather_cols["rain"].append(0)

        # Simulated Safety Car 450m ahead of leader during [sc_start_s, sc_end_s]
        if in_sc:
            sc_s = (leader["dist"] + pole_dist + 450.0) % circuit_length_m
            sc_x = float(np.interp(sc_s, s_closed, x_closed))
            sc_y = float(np.interp(sc_s, s_closed, y_closed))
            if t - sc_start_s < 4.0:
                phase = "deploying"
                alpha = round(min(1.0, (t - sc_start_s) / 4.0), 2)
            elif sc_end_s - t < 4.0:
                phase = "returning"
                alpha = round(max(0.1, (sc_end_s - t) / 4.0), 2)
            else:
                phase = "on_track"
                alpha = 1.0
            sc_cols["active"].append(1)
            sc_cols["x"].append(round(sc_x, 1))
            sc_cols["y"].append(round(sc_y, 1))
            sc_cols["phase"].append(phase)
            sc_cols["alpha"].append(alpha)
        else:
            sc_cols["active"].append(0)
            sc_cols["x"].append(0.0)
            sc_cols["y"].append(0.0)
            sc_cols["phase"].append("")
            sc_cols["alpha"].append(0.0)

        if (leader["dist"] + pole_dist) >= (total_race_dist + pole_dist):
            if finish_timer is None:
                finish_timer = 10.0
            else:
                finish_timer -= dt
                if finish_timer <= 0:
                    break

    duration_s = t_list[-1]
    track_statuses = [
        {"status": "1", "start_time": 0.0, "end_time": yellow_start_s},
        {"status": "2", "start_time": yellow_start_s, "end_time": sc_start_s},
        {"status": "4", "start_time": sc_start_s, "end_time": sc_end_s},
        {"status": "1", "start_time": sc_end_s, "end_time": duration_s},
    ]

    race_events = [
        {
            "type": EVENT_YELLOW_FLAG,
            "time_s": yellow_start_s,
            "end_time_s": sc_start_s,
            "label": "Sector 2 Yellow",
            "lap": 3,
        },
        {
            "type": EVENT_SAFETY_CAR,
            "time_s": sc_start_s,
            "end_time_s": sc_end_s,
            "label": "Safety Car",
            "lap": 3,
        },
    ]
    if dnf_time_s is not None:
        race_events.insert(
            0,
            {
                "type": EVENT_DNF,
                "time_s": dnf_time_s,
                "end_time_s": None,
                "label": "GAS",
                "lap": 3,
            },
        )

    rc_messages = [
        {"time": 2.0, "category": "Flag", "message": "GREEN LIGHT - PIT EXIT OPEN", "flag": "GREEN", "scope": "Track", "sector": "", "racing_number": ""},
        {"time": 95.0, "category": "Drs", "message": "DRS ENABLED", "flag": "", "scope": "Track", "sector": "", "racing_number": ""},
        {"time": yellow_start_s, "category": "Flag", "message": "YELLOW IN TRACK SECTOR 2 - CAR 10 (GAS) STOPPED", "flag": "YELLOW", "scope": "Sector", "sector": "2", "racing_number": "10"},
        {"time": sc_start_s, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED", "flag": "SC", "scope": "Track", "sector": "", "racing_number": ""},
        {"time": sc_end_s - 6.0, "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP", "flag": "SC", "scope": "Track", "sector": "", "racing_number": ""},
        {"time": sc_end_s, "category": "Flag", "message": "TRACK CLEAR - GREEN FLAG", "flag": "GREEN", "scope": "Track", "sector": "", "racing_number": ""},
        {"time": sc_end_s + 35.0, "category": "Drs", "message": "DRS ENABLED", "flag": "", "scope": "Track", "sector": "", "racing_number": ""},
    ]

    base_drv_pts = {
        "VER": 185.0, "NOR": 178.0, "LEC": 154.0, "PIA": 146.0, "HAM": 122.0,
        "RUS": 118.0, "ANT": 68.0, "SAI": 54.0, "ALB": 42.0, "ALO": 36.0,
    }
    base_con_pts = {
        "McLaren": 324.0, "Ferrari": 276.0, "Red Bull Racing": 211.0,
        "Mercedes": 186.0, "Williams": 96.0, "Aston Martin": 48.0,
        "Racing Bulls": 34.0, "Alpine": 22.0, "Haas F1 Team": 20.0, "Kick Sauber": 12.0,
    }

    manifest = {
        "schema_version": 1,
        "session_id": "demo",
        "session_info": {
            "event_name": "British Grand Prix (Instant Demo)",
            "circuit_name": "Silverstone GP Showcase",
            "country": "United Kingdom",
            "year": 2025,
            "round": 12,
            "session_type": "R",
            "session_name": "Race (8-Lap Demo)",
            "date": "July 06, 2025",
            "total_laps": total_laps,
            "circuit_length_m": circuit_length_m,
            "fps": fps,
            "total_frames": len(t_list),
            "duration_s": duration_s,
        },
        "track": track_geom,
        "drivers": drivers_meta,
        "track_statuses": track_statuses,
        "race_events": race_events,
        "race_control_messages": rc_messages,
        "standings": {
            "current_drivers": base_drv_pts,
            "current_constructors": base_con_pts,
            "live_drivers": {},
            "live_constructors": {},
        },
    }

    frames = {
        "fps": fps,
        "t": t_list,
        "lap": leader_lap_list,
        "drivers": driver_cols,
        "weather": weather_cols,
        "safety_car": sc_cols,
    }

    return manifest, frames
