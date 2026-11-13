"""
FastAPI backend for the F1 Race Replay Web Pit Wall.

Endpoints:
  - GET  /api/health
  - GET  /api/seasons
  - GET  /api/seasons/{year}
  - GET  /api/sessions/demo/manifest
  - GET  /api/sessions/demo/frames
  - POST /api/sessions/{year}/{round_number}/{session_type}/prepare
  - GET  /api/sessions/{year}/{round_number}/{session_type}/status
  - GET  /api/sessions/{year}/{round_number}/{session_type}/manifest
  - GET  /api/sessions/{year}/{round_number}/{session_type}/frames
"""

from __future__ import annotations

import gzip
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.core.replay_exporter import (
    build_demo_bundle,
    export_race_bundle,
    get_cached_bundle_paths,
)

WEB_BUNDLE_DIR = Path(os.environ.get("WEB_BUNDLE_DIR", "computed_data/web"))

app = FastAPI(
    title="F1 Race Replay API",
    version="0.2.0",
    description="Headless FastF1 telemetry exporter & replay API",
)

cors_origins_env = os.environ.get("CORS_ORIGINS", "*")
allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bounded worker pool for telemetry builds so concurrent requests share jobs cleanly.
_export_executor = ThreadPoolExecutor(max_workers=2)
_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}

# Cached demo bundle in memory (built lazily once in ~40ms)
_demo_lock = threading.Lock()
_demo_cache: tuple[bytes, bytes, bytes] | None = None  # (manifest_json, frames_json, frames_gzip)

# Cached raw FastF1 season calendars in memory
_weekends_cache: dict[int, list[dict[str, Any]]] = {}


def _get_demo_payloads() -> tuple[bytes, bytes, bytes]:
    global _demo_cache
    with _demo_lock:
        if _demo_cache is None:
            manifest, frames = build_demo_bundle()
            manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
            frames_bytes = json.dumps(frames, separators=(",", ":")).encode("utf-8")
            frames_gz = gzip.compress(frames_bytes, compresslevel=6)
            _demo_cache = (manifest_bytes, frames_bytes, frames_gz)
        return _demo_cache


def _job_key(year: int, round_number: int, session_type: str) -> str:
    return f"{year}_{round_number}_{session_type.upper()}"


def _run_export_job(year: int, round_number: int, session_type: str, refresh: bool = False) -> None:
    key = _job_key(year, round_number, session_type)

    def _on_progress(message: str, pct: int) -> None:
        with _jobs_lock:
            _jobs[key] = {
                "status": "building" if pct < 100 else "ready",
                "progress": pct,
                "message": message,
                "updated_at": time.time(),
            }

    try:
        export_race_bundle(
            year=year,
            round_number=round_number,
            session_type=session_type,
            stride=5,
            refresh=refresh,
            output_root=WEB_BUNDLE_DIR,
            progress_cb=_on_progress,
        )
        with _jobs_lock:
            _jobs[key] = {
                "status": "ready",
                "progress": 100,
                "message": "Ready",
                "updated_at": time.time(),
            }
    except Exception as exc:
        with _jobs_lock:
            _jobs[key] = {
                "status": "error",
                "progress": 0,
                "message": str(exc),
                "updated_at": time.time(),
            }


@app.get("/api/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "f1-race-replay-api",
        "bundle_dir": str(WEB_BUNDLE_DIR),
    }


@app.get("/api/seasons")
def list_seasons() -> dict[str, Any]:
    today = date.today()
    current_year = max(2025, today.year)
    has_f1_creds = bool(os.environ.get("F1_USERNAME") and os.environ.get("F1_PASSWORD"))
    min_year = 2018 if has_f1_creds else 2023
    years = list(range(current_year, min_year - 1, -1))
    default_year = current_year if today.month >= 3 else max(min_year, current_year - 1)
    return {
        "seasons": years,
        "default_year": default_year,
        "has_f1_credentials": has_f1_creds,
    }


@app.get("/api/seasons/{year}")
def get_season_schedule(year: int) -> dict[str, Any]:
    today_iso = date.today().isoformat()
    if year < 2018 or year > date.today().year + 1:
        raise HTTPException(status_code=400, detail="Supported seasons are 2018 through current season.")

    weekends = _weekends_cache.get(year)
    if weekends is None:
        try:
            from src.f1_data import get_race_weekends_by_year

            weekends = get_race_weekends_by_year(year)
            _weekends_cache[year] = weekends
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to load F1 schedule for {year}: {exc}") from exc

    events = []
    for w in weekends:
        fmt = str(w.get("type", "")).lower()
        has_sprint = "sprint" in fmt
        sessions = ["R"]
        if has_sprint:
            sessions.insert(0, "S")

        round_num = int(w["round_number"])
        cached_sessions = [
            s
            for s in sessions
            if get_cached_bundle_paths(year, round_num, s, output_root=WEB_BUNDLE_DIR) is not None
        ]
        ev_date = str(w.get("date", ""))
        is_completed = bool(cached_sessions) or (bool(ev_date) and ev_date <= today_iso)

        events.append(
            {
                "round_number": round_num,
                "event_name": w["event_name"],
                "country": w["country"],
                "date": ev_date,
                "format": w["type"],
                "sessions": sessions,
                "cached_sessions": cached_sessions,
                "is_completed": is_completed,
            }
        )

    return {"year": year, "events": events}


@app.get("/api/sessions/demo/manifest")
def get_demo_manifest() -> Response:
    manifest_bytes, _, _ = _get_demo_payloads()
    return Response(
        content=manifest_bytes,
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/sessions/demo/frames")
def get_demo_frames(request: Request) -> Response:
    _, frames_bytes, frames_gz = _get_demo_payloads()
    accept_enc = request.headers.get("accept-encoding", "")
    if "gzip" in accept_enc.lower():
        return Response(
            content=frames_gz,
            media_type="application/json",
            headers={
                "Content-Encoding": "gzip",
                "Vary": "Accept-Encoding",
                "Cache-Control": "public, max-age=3600",
            },
        )
    return Response(content=frames_bytes, media_type="application/json")


@app.post("/api/sessions/{year}/{round_number}/{session_type}/prepare")
def prepare_session(
    year: int,
    round_number: int,
    session_type: str,
    refresh: bool = False,
) -> dict[str, Any]:
    session_type = session_type.upper()
    if session_type not in ("R", "S"):
        raise HTTPException(status_code=400, detail="Only 'R' (Race) and 'S' (Sprint) are supported in replay MVP.")

    cached = get_cached_bundle_paths(year, round_number, session_type, output_root=WEB_BUNDLE_DIR)
    if cached and not refresh:
        return {
            "session_id": _job_key(year, round_number, session_type),
            "status": "ready",
            "progress": 100,
            "message": "Ready",
        }

    key = _job_key(year, round_number, session_type)
    with _jobs_lock:
        existing = _jobs.get(key)
        if existing and existing["status"] == "building":
            return {"session_id": key, **existing}

        _jobs[key] = {
            "status": "building",
            "progress": 5,
            "message": "Queued FastF1 telemetry build...",
            "updated_at": time.time(),
        }

    _export_executor.submit(_run_export_job, year, round_number, session_type, refresh)
    with _jobs_lock:
        return {"session_id": key, **_jobs[key]}


@app.get("/api/sessions/{year}/{round_number}/{session_type}/status")
def get_session_status(year: int, round_number: int, session_type: str) -> dict[str, Any]:
    session_type = session_type.upper()
    key = _job_key(year, round_number, session_type)

    with _jobs_lock:
        job = _jobs.get(key)
        if job and job.get("status") == "building":
            return {"session_id": key, **job}

    cached = get_cached_bundle_paths(year, round_number, session_type, output_root=WEB_BUNDLE_DIR)
    if cached:
        return {
            "session_id": key,
            "status": "ready",
            "progress": 100,
            "message": "Ready",
        }

    with _jobs_lock:
        job = _jobs.get(key)
        if job:
            return {"session_id": key, **job}

    return {
        "session_id": key,
        "status": "missing",
        "progress": 0,
        "message": "Session has not been built yet.",
    }


@app.get("/api/sessions/{year}/{round_number}/{session_type}/manifest")
def get_session_manifest(year: int, round_number: int, session_type: str) -> Response:
    session_type = session_type.upper()
    cached = get_cached_bundle_paths(year, round_number, session_type, output_root=WEB_BUNDLE_DIR)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="Session bundle not ready. Call POST .../prepare first.",
        )
    manifest_path, _ = cached
    return Response(
        content=manifest_path.read_bytes(),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/sessions/{year}/{round_number}/{session_type}/frames")
def get_session_frames(year: int, round_number: int, session_type: str, request: Request) -> Response:
    session_type = session_type.upper()
    cached = get_cached_bundle_paths(year, round_number, session_type, output_root=WEB_BUNDLE_DIR)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="Session bundle not ready. Call POST .../prepare first.",
        )
    _, frames_gz_path = cached
    gz_bytes = frames_gz_path.read_bytes()
    accept_enc = request.headers.get("accept-encoding", "")
    if "gzip" in accept_enc.lower():
        return Response(
            content=gz_bytes,
            media_type="application/json",
            headers={
                "Content-Encoding": "gzip",
                "Vary": "Accept-Encoding",
                "Cache-Control": "public, max-age=86400",
            },
        )
    raw_bytes = gzip.decompress(gz_bytes)
    return Response(content=raw_bytes, media_type="application/json")
