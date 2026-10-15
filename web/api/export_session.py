"""
CLI utility to pre-export any session (metadata + track + frames)
into a static JSON file for zero-backend web deployment (e.g. Vercel, GitHub Pages).

Usage:
    python -m web.api.export_session --year 2026 --round 17 --session sprint --out web/public/data
"""

import argparse
import gzip
import json
import os
import sys

from web.api.session_service import SessionService


def export_session(year: int, round_no: int, session_type: str, output_dir: str, compress: bool = False, step: int = 1):
    service = SessionService()
    meta = service.get_metadata(year, round_no, session_type)
    if not meta:
        print(f"Error: Session {year} R{round_no} {session_type} not found in computed_data.")
        sys.exit(1)

    print(f"Loading frames for {year} R{round_no} {session_type} (step={step})...")
    frames = service.get_frames(year, round_no, session_type, step=step)
    if not frames:
        print("Error: Could not extract frames.")
        sys.exit(1)

    payload = {
        "metadata": meta,
        "frames": frames
    }

    os.makedirs(output_dir, exist_ok=True)
    filename = f"{year}_R{round_no}_{session_type.lower()}"

    if compress:
        out_file = os.path.join(output_dir, f"{filename}.json.gz")
        print(f"Writing compressed JSON to {out_file}...")
        with gzip.open(out_file, "wt", encoding="utf-8") as f:
            json.dump(payload, f)
    else:
        out_file = os.path.join(output_dir, f"{filename}.json")
        print(f"Writing JSON to {out_file}...")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    file_size_mb = os.path.getsize(out_file) / (1024 * 1024)
    print(f"✓ Export complete: {out_file} ({file_size_mb:.2f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export F1 replay session to static JSON for web")
    parser.add_argument("--year", type=int, default=2026, help="Season year (e.g. 2026)")
    parser.add_argument("--round", type=int, default=17, help="Round number (e.g. 17)")
    parser.add_argument("--session", type=str, default="sprint", help="Session type (race, sprint, qualifying)")
    parser.add_argument("--out", type=str, default="web/public/data", help="Output directory")
    parser.add_argument("--compress", action="store_true", help="Compress with gzip (.json.gz)")
    parser.add_argument("--step", type=int, default=2, help="Frame step stride (default 2 = 12.5 FPS for compact web payload)")

    args = parser.parse_args()
    export_session(args.year, args.round, args.session, args.out, compress=args.compress, step=args.step)
