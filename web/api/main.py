"""
FastAPI backend for F1 Race Replay web application.
Serves track geometry, session metadata, and high-performance frame data.
"""

from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from web.api.session_service import SessionService

app = FastAPI(
    title="F1 Race Replay API",
    description="Web API serving F1 track geometry, telemetry, and race replay frames",
    version="1.0.0"
)

# Enable CORS for local Vite dev server and web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Automatic GZip compression for large JSON payloads (> 1000 bytes)
app.add_middleware(GZipMiddleware, minimum_size=1000)

session_service = SessionService()


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "f1-race-replay-api"}


@app.get("/api/sessions/cached")
def list_cached_sessions():
    """Return all sessions that have precomputed replay data ready."""
    return session_service.list_cached_sessions()


@app.get("/api/schedule/{year}")
def get_schedule(year: int):
    """Get full race weekend calendar for a given year."""
    try:
        from src.f1_data import get_race_weekends_by_year
        events = get_race_weekends_by_year(year)
        # Convert date objects to ISO strings for JSON
        for ev in events:
            if "date" in ev and ev["date"] is not None:
                ev["date"] = str(ev["date"])
        return events
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch schedule: {exc}")


@app.get("/api/session/{year}/{round_no}/{session_type}/meta")
def get_session_meta(year: int, round_no: int, session_type: str):
    """
    Return session metadata and full track geometry (inner/outer boundaries,
    drs zones, bounds, and driver colors).
    """
    meta = session_service.get_metadata(year, round_no, session_type)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found or not yet computed for {year} R{round_no} {session_type}"
        )
    return meta


@app.get("/api/session/{year}/{round_no}/{session_type}/frames")
def get_session_frames(
    year: int,
    round_no: int,
    session_type: str,
    start: int = Query(0, ge=0, description="Start frame index"),
    limit: Optional[int] = Query(None, ge=1, description="Max number of frames to return"),
    step: int = Query(1, ge=1, le=10, description="Step stride (1 = 25 FPS, 2 = 12.5 FPS)")
):
    """
    Return columnar frame data for the session.
    Automatically compressed with Gzip middleware.
    """
    frames = session_service.get_frames(
        year=year,
        round_no=round_no,
        session_type=session_type,
        start=start,
        limit=limit,
        step=step
    )
    if not frames:
        raise HTTPException(
            status_code=404,
            detail=f"Replay frames not found for {year} R{round_no} {session_type}"
        )
    return frames


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.api.main:app", host="0.0.0.0", port=8000, reload=True)
