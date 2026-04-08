"""
Pre-processes F1 race data and uploads it to Supabase.

Usage:
  python preprocess.py --year 2024 --round 1
  python preprocess.py --year 2024 --all       # processes all rounds in a season
"""

import argparse
import json
import math
import os
import sys
import logging

import numpy as np
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))

from core.f1_data import (
    load_session,
    load_session_minimal,
    get_track_shape,
    get_race_telemetry,
    get_driver_colors,
    get_circuit_rotation,
    get_race_weekends_by_year,
    enable_cache,
)


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── JSON serialisation ───────────────────────────────────────────────────────

def _sanitize(obj):
    """Recursively coerce numpy scalars and NaN/Inf to JSON-safe Python types."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.bool_):       # must be before np.integer check
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def dumps(obj) -> str:
    return json.dumps(_sanitize(obj))


def sanitize_frames(frames: list) -> list:
    return _sanitize(frames)


# ── Official positions ───────────────────────────────────────────────────────

def get_official_positions(session) -> dict[str, int]:
    """Get official race finishing positions.
    Priority: FastF1 session.results → Jolpica API → mid-race lap fallback."""
    import pandas as pd

    # 1. FastF1 session.results
    results = session.results
    if results is not None and not results.empty and 'Position' in results.columns:
        pos = {}
        for _, row in results.iterrows():
            code = row.get('Abbreviation', '')
            p    = row.get('Position')
            if code and p is not None and not pd.isna(p):
                pos[code] = int(p)
        if pos:
            logger.info(f"  Official positions from session.results: {pos}")
            return pos

    # 2. Jolpica (community-maintained Ergast mirror)
    try:
        year      = session.event['EventDate'].year
        round_num = session.event['RoundNumber']
        url  = f"https://api.jolpi.ca/ergast/f1/{year}/{round_num}/results.json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        races = resp.json()['MRData']['RaceTable']['Races']
        if races:
            pos = {}
            for result in races[0]['Results']:
                code = result.get('Driver', {}).get('code', '')
                p    = result.get('position')
                if code and p:
                    pos[code] = int(p)
            if pos:
                logger.info(f"  Official positions from Jolpica: {pos}")
                return pos
    except Exception as e:
        logger.warning(f"  Jolpica request failed: {e}")

    # 3. Fallback: positions from ~5 laps before the end
    logger.warning("  Falling back to mid-race positions (may be inaccurate)")
    laps = session.laps
    if laps.empty:
        return {}

    leader_lap = int(laps['LapNumber'].max())
    sample_lap = max(1, leader_lap - 5)
    pos = {}
    for _, lap in laps[laps['LapNumber'] == sample_lap].iterrows():
        code = lap.get('Driver', '')
        p    = lap.get('Position')
        if code and p is not None and not pd.isna(p):
            pos[code] = int(p)

    logger.info(f"  Fallback positions from lap {sample_lap}: {pos}")
    return pos


# ── Frame flags ──────────────────────────────────────────────────────────────

def mark_retired_drivers(frames: list, session) -> list:
    """Set is_out=True on drivers whose distance stopped increasing more than
    RETIREMENT_THRESHOLD seconds before the race ended (i.e. they retired).
    Lapped finishers keep moving until the end so they are not flagged."""
    if not frames:
        return frames

    race_end_t = frames[-1].get('t', 0)
    RETIREMENT_THRESHOLD = 120  # seconds

    last_active: dict[str, float] = {}
    last_dist:   dict[str, float] = {}

    for frame in frames:
        t = frame.get('t', 0)
        for code, d in frame.get('drivers', {}).items():
            dist = d.get('dist')
            if dist is None:
                continue
            prev = last_dist.get(code)
            if prev is None or dist > prev:
                last_active[code] = t
                last_dist[code]   = dist

    retired_codes = {
        code for code, t in last_active.items()
        if (race_end_t - t) > RETIREMENT_THRESHOLD
    }

    if not retired_codes:
        logger.info("  No retired drivers detected.")
    else:
        logger.info(f"  Retired drivers: {retired_codes}")

    for frame in frames:
        t = frame.get('t', 0)
        for code, d in frame.get('drivers', {}).items():
            if code in retired_codes:
                d['is_out'] = t > last_active.get(code, 0)
            else:
                d['is_out'] = False

    return frames


def freeze_finishing_positions(frames, total_laps, official_positions=None):
    if not frames or not total_laps:
        return frames

    official_positions = official_positions or {}

    # Pass 1: find first frame where each lead-lap driver exceeds total_laps
    finish_positions = {}
    leader_finish_frame = None

    for frame_idx, frame in enumerate(frames):
        for code, d in frame.get('drivers', {}).items():
            if code not in finish_positions and d.get('lap', 0) > total_laps:
                finish_positions[code] = official_positions.get(code, d.get('position', 99))
                if official_positions.get(code) == 1 and leader_finish_frame is None:
                    leader_finish_frame = frame_idx

    # Pass 2: stamp flags
    for frame_idx, frame in enumerate(frames):
        after_leader_finished = leader_finish_frame is not None and frame_idx >= leader_finish_frame

        for code, d in frame.get('drivers', {}).items():
            if d.get('is_out', False):
                d['finished'] = False
                continue

            lead_lap_finished = code in finish_positions and d.get('lap', 0) > total_laps

            if lead_lap_finished:
                d['finished'] = True
                d['position'] = finish_positions[code]
            elif after_leader_finished and code in official_positions:
                # Lapped driver — race is over, apply official position
                d['finished'] = True
                d['position'] = official_positions[code]
            else:
                d['finished'] = False

    return frames

# ── Main pipeline ────────────────────────────────────────────────────────────

def process_and_upload(year: int, round: int, supabase: Client, force: bool = False):
    logger.info(f"Processing {year} Round {round}...")

    # ── 0. Skip if already uploaded ─────────────────────────────────────────
    if not force:
        existing = supabase.table("races").select("id").eq("year", year).eq("round", round).execute()
        if existing.data:
            logger.info("  Already in DB, skipping. Use --force to overwrite.")
            return

    # ── 1. Track shape (fast, minimal session load) ──────────────────────────
    logger.info("  Loading track shape...")
    session_min      = load_session_minimal(year, round, "R")
    track_frames     = get_track_shape(session_min)
    circuit_rotation = get_circuit_rotation(session_min)

    n = len(track_frames)
    drs_zones = [
        {"start_index": int(n * 0.15), "end_index": int(n * 0.25)},
        {"start_index": int(n * 0.85), "end_index": int(n * 0.95)},
    ]
    session_info = {
        "event_name":   str(session_min.event["EventName"]),
        "circuit_name": str(session_min.event.get("Location", "Unknown")),
        "country":      str(session_min.event["Country"]),
        "date":         str(session_min.event["EventDate"].date()),
    }
    logger.info(f"  Track shape: {n} points")

    # ── 2. Full race telemetry ───────────────────────────────────────────────
    logger.info("  Processing race frames (this takes a while on first run)...")
    session_full = load_session(year, round, "R")
    telemetry    = get_race_telemetry(session_full, "R")
    total_laps   = telemetry.get("total_laps") or 0
    all_frames   = telemetry["frames"]

    driver_colors = get_driver_colors(session_full)
    driver_teams  = {}
    for _, row in session_full.results.iterrows():
        code = row.get("Abbreviation")
        team = row.get("TeamName", "Unknown")
        if code:
            driver_teams[code] = team

    # ── 3. Official finishing positions ──────────────────────────────────────
    official_positions = get_official_positions(session_full)
    logger.info(f"  Official positions: {official_positions}")

    # ── 4. Apply flags on full data before downsampling ──────────────────────
    all_frames = mark_retired_drivers(all_frames, session_full)
    all_frames = freeze_finishing_positions(all_frames, total_laps, official_positions)

    # ── 5. Downsample to 5000 frames max ─────────────────────────────────────
    max_frames = 5000
    if len(all_frames) > max_frames:
        step = len(all_frames) / max_frames
        frames_to_store = [all_frames[int(i * step)] for i in range(max_frames)]
    else:
        frames_to_store = all_frames

    frames_to_store = sanitize_frames(frames_to_store)
    logger.info(f"  Frames: {len(frames_to_store)} (downsampled from {len(all_frames)})")

    # ── 5b. Build track statuses ─────────────────────────────────────────────
    track_statuses = []
    status_data = session_full.track_status
    if status_data is not None and not status_data.empty:
        # Offset: align status times to the same clock as frame t values
        race_start_offset = session_full.laps['LapStartTime'].min().total_seconds()
        logger.info(f"  Race start offset: {race_start_offset:.1f}s")

        for i in range(len(status_data)):
            row    = status_data.iloc[i]
            start_t = row['Time'].total_seconds() - race_start_offset
            end_t   = (status_data.iloc[i + 1]['Time'].total_seconds() - race_start_offset) \
                      if i + 1 < len(status_data) else None

            # Skip statuses that ended before the race started
            if end_t is not None and end_t <= 0:
                continue

            track_statuses.append({
                'status':     str(row['Status']),
                'start_time': max(0.0, start_t),
                'end_time':   end_t,
            })
    logger.info(f"  Track statuses: {len(track_statuses)} entries")

    # ── 6. Upload to Supabase ────────────────────────────────────────────────
    logger.info("  Uploading to Supabase...")

    supabase.table("races").upsert({
        "year":           year,
        "round":          round,
        "event_name":     session_info["event_name"],
        "circuit_name":   session_info["circuit_name"],
        "country":        session_info["country"],
        "date":           session_info["date"],
        "total_laps":     total_laps,
        "track_statuses": dumps(track_statuses),
    }, on_conflict="year,round").execute()

    supabase.table("track_shapes").upsert({
        "year":             year,
        "round":            round,
        "circuit_rotation": circuit_rotation,
        "frames":           dumps(track_frames),
        "drs_zones":        dumps(drs_zones),
    }, on_conflict="year,round").execute()

    supabase.table("race_frames").delete().eq("year", year).eq("round", round).execute()

    CHUNK_SIZE   = 500
    chunks       = [frames_to_store[i:i+CHUNK_SIZE] for i in range(0, len(frames_to_store), CHUNK_SIZE)]
    total_chunks = len(chunks)
    logger.info(f"  Uploading {total_chunks} frame chunks...")

    for idx, chunk in enumerate(chunks):
        supabase.table("race_frames").insert({
            "year":               year,
            "round":              round,
            "driver_colors":      dumps(driver_colors),
            "driver_teams":       dumps(driver_teams),
            "official_positions": dumps(official_positions),
            "frames":             dumps(chunk),
            "chunk_index":        idx,
            "total_chunks":       total_chunks,
        }).execute()
        logger.info(f"    Chunk {idx+1}/{total_chunks} uploaded")

    logger.info(f"  ✅ Done — {session_info['event_name']} uploaded.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year",  type=int, required=True)
    parser.add_argument("--round", type=int, default=None)
    parser.add_argument("--all",   action="store_true", help="Process all rounds for the year")
    parser.add_argument("--force", action="store_true", help="Re-upload even if already in DB")
    args = parser.parse_args()

    enable_cache()
    supabase = get_supabase()

    if args.all:
        weekends = get_race_weekends_by_year(args.year)
        rounds   = [w["round_number"] for w in weekends]
        logger.info(f"Processing all {len(rounds)} rounds for {args.year}...")
        for r in rounds:
            try:
                process_and_upload(args.year, r, supabase, force=args.force)
            except Exception as e:
                logger.error(f"  ❌ Failed round {r}: {e}")
    elif args.round:
        process_and_upload(args.year, args.round, supabase, force=args.force)
    else:
        parser.error("Provide --round N or --all")


if __name__ == "__main__":
    main()