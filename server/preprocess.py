"""
Pre-processes F1 race data and uploads it to Supabase.

Usage:
  python preprocess.py --year 2024 --round 1
  python preprocess.py --year 2024 --all       # processes all rounds in a season
"""

import argparse
import json
import os
import sys
import logging

from supabase import create_client, Client
from dotenv import load_dotenv

# Load your Supabase credentials from .env
load_dotenv()
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]  # use service key for writes

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Import your existing pipeline ───────────────────────────────────────────

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
from core.telemetry_processor import process_race_telemetry as process_telemetry
from utils.trackDataConverter import build_track_from_frames  # only if you want to validate


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def process_and_upload(year: int, round: int, supabase: Client, force: bool = False):
    logger.info(f"Processing {year} Round {round}...")

    # Check if already uploaded
    if not force:
        existing = supabase.table("races").select("id").eq("year", year).eq("round", round).execute()
        if existing.data:
            logger.info(f"  Already in DB, skipping. Use --force to overwrite.")
            return

    # ── 1. Track shape (fast) ────────────────────────────────────────────────
    logger.info("  Loading track shape...")
    session_min = load_session_minimal(year, round, "R")

    track_frames = get_track_shape(session_min)
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

    # ── 2. Full race frames ──────────────────────────────────────────────────
    logger.info("  Processing race frames (this takes a while on first run)...")
    session_full = load_session(year, round, "R")
    telemetry = get_race_telemetry(session_full, "R")

    all_frames = telemetry["frames"]
    driver_colors = get_driver_colors(session_full)

    driver_teams = {}
    for _, row in session_full.results.iterrows():
        code = row.get("Abbreviation")
        team = row.get("TeamName", "Unknown")
        if code:
            driver_teams[code] = team

    # Downsample to 5000 frames max so the DB row stays small
    max_frames = 5000
    if len(all_frames) > max_frames:
        step = len(all_frames) / max_frames
        frames_to_store = [all_frames[int(i * step)] for i in range(max_frames)]
    else:
        frames_to_store = all_frames

    logger.info(f"  Frames: {len(frames_to_store)} (from {len(all_frames)} total)")

    # ── 3. Upload to Supabase ────────────────────────────────────────────────
    logger.info("  Uploading to Supabase...")

    # races table
    supabase.table("races").upsert({
        "year":         year,
        "round":        round,
        "event_name":   session_info["event_name"],
        "circuit_name": session_info["circuit_name"],
        "country":      session_info["country"],
        "date":         session_info["date"],
        "total_laps":   telemetry.get("total_laps"),
    }).execute()

    # track_shapes table
    supabase.table("track_shapes").upsert({
        "year":             year,
        "round":            round,
        "circuit_rotation": circuit_rotation,
        "frames":           json.dumps(track_frames),
        "drs_zones":        json.dumps(drs_zones),
    }).execute()

    # race_frames table
    supabase.table("race_frames").upsert({
        "year":          year,
        "round":         round,
        "driver_colors": json.dumps(driver_colors),
        "driver_teams":  json.dumps(driver_teams),
        "frames":        json.dumps(frames_to_store),
    }).execute()

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
        rounds = [w["round_number"] for w in weekends]
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