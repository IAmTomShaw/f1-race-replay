"""
Telemetry data endpoints
"""

from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional
import logging

from api.models.telemetry import (
    TelemetryData,
    TelemetryStatusResponse,
    CacheInfoResponse
)
from api.models.race import SessionInfo

from core.f1_data import (
    load_session,
    load_session_minimal,   # add this import
    get_track_shape,        # add this import
    get_race_telemetry,
    get_driver_colors,
    get_circuit_rotation
)
from core.cache_manager import get_cache_manager
from config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()
cache = get_cache_manager()


@router.get("/race/{year}/{round}")  # Remove response_model=TelemetryData
async def get_race_telemetry_data(
    year: int = Path(..., ge=2019, le=2025),
    round: int = Path(..., ge=1, le=24),
    session_type: str = Query("R", regex="^(R|S)$"),
    force_refresh: bool = Query(False)
):
    """Get race telemetry data"""
    try:
        logger.info(f"Loading telemetry: {year} R{round} {session_type}")
        
        if not force_refresh:
            cached_data = cache.get(year, round, session_type)
            if cached_data:
                logger.info("Returning cached telemetry data")
                
                if "session_info" not in cached_data:
                    session = load_session(year, round, session_type)
                    cached_data["session_info"] = _build_session_info(session, year, round)
                
                return cached_data
        
        logger.info("Loading fresh telemetry data from FastF1...")
        session = load_session(year, round, session_type)
        
        telemetry_data = get_race_telemetry(session, session_type)
        
        driver_colors = get_driver_colors(session)
        circuit_rotation = get_circuit_rotation(session)
        
        session_info = _build_session_info(session, year, round)
        
        response_data = {
            "frames": telemetry_data["frames"],
            "track_statuses": telemetry_data["track_statuses"],
            "driver_colors": driver_colors,
            "circuit_rotation": circuit_rotation,
            "total_laps": telemetry_data["total_laps"],
            "session_info": session_info,
        }
        
        logger.info(f"Successfully loaded {len(response_data['frames'])} frames")
        return response_data
        
    except Exception as e:
        logger.error(f"Error loading telemetry: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load telemetry data: {str(e)}"
        )

@router.get("/status/{year}/{round}", response_model=TelemetryStatusResponse)
async def get_telemetry_status(
    year: int = Path(..., ge=2018, le=2025),  # Changed to Path
    round: int = Path(..., ge=1, le=24),  # Changed to Path
    session_type: str = Query("R", regex="^(R|S|Q|SQ)$")
):
    """Check if telemetry data is cached"""
    try:
        exists = cache.exists(year, round, session_type)
        
        if not exists:
            return {
                "exists": False,
                "cached": False
            }
        
        info = cache.get_cache_info(year, round, session_type)
        
        return {
            "exists": True,
            "cached": True,
            "size_mb": info.get("size_mb"),
            "created": info.get("created"),
            "modified": info.get("modified")
        }
        
    except Exception as e:
        logger.error(f"Error checking telemetry status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/info/{year}/{round}", response_model=CacheInfoResponse)
async def get_cache_info_endpoint(
    year: int = Path(...),  # Changed to Path
    round: int = Path(...),  # Changed to Path
    session_type: str = Query("R", regex="^(R|S|Q|SQ)$")
):
    """Get detailed cache information"""
    try:
        info = cache.get_cache_info(year, round, session_type)
        
        if not info:
            return {"exists": False}
        
        info.update({
            "year": year,
            "round": round,
            "session_type": session_type
        })
        
        return info
        
    except Exception as e:
        logger.error(f"Error getting cache info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/list")
async def list_cached_sessions():
    """List all cached sessions"""
    try:
        sessions = cache.list_cached_sessions()
        return {
            "sessions": sessions,
            "total": len(sessions)
        }
    except Exception as e:
        logger.error(f"Error listing cached sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache/{year}/{round}")
async def clear_session_cache(
    year: int = Path(...),  # Changed to Path
    round: int = Path(...),  # Changed to Path
    session_type: str = Query("R", regex="^(R|S|Q|SQ)$")
):
    """Clear cache for a specific session"""
    try:
        success = cache.delete(year, round, session_type)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Cache entry not found"
            )
        
        return {
            "message": "Cache cleared successfully",
            "year": year,
            "round": round,
            "session_type": session_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache/clear-all")
async def clear_all_cache():
    """Clear all cached telemetry data"""
    try:
        count = cache.clear_all()
        
        return {
            "message": f"Cleared {count} cached sessions",
            "count": count
        }
        
    except Exception as e:
        logger.error(f"Error clearing all cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from core.drs_zones import get_drs_zones_for_session

@router.get("/track/{year}/{round}")
async def get_track_data(
    year: int = Path(..., ge=2019, le=2025),
    round: int = Path(..., ge=1, le=24),
    session_type: str = Query("R", regex="^(R|S)$")
):
    """Get track shape data. Uses a minimal session load — no full telemetry pipeline."""
    try:
        logger.info(f"Loading track shape: {year} R{round} {session_type}")

        # Fast path: only load laps + position, skip weather/messages
        session = load_session_minimal(year, round, session_type)

        track_frames = get_track_shape(session)
        logger.info(f"Extracted {len(track_frames)} track shape points")

        # Hardcoded DRS zones (proportional to track length)
        n = len(track_frames)
        drs_zones = [
            {"start_index": int(n * 0.15), "end_index": int(n * 0.25)},
            {"start_index": int(n * 0.85), "end_index": int(n * 0.95)},
        ]

        session_info = _build_session_info(session, year, round)
        circuit_rotation = get_circuit_rotation(session)

        return {
            "frames": track_frames,
            "drs_zones": drs_zones,
            "circuit_rotation": circuit_rotation,
            "session_info": session_info,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Position data unavailable for {year} Round {round}: {e}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading track data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def _build_session_info(session, year: int, round: int) -> dict:
    """Helper function to build session info dictionary"""
    try:
        return {
            "event_name": str(session.event['EventName']),
            "circuit_name": str(session.event.get('Location', 'Unknown')),
            "country": str(session.event['Country']),
            "year": year,
            "round": round,
            "date": str(session.event['EventDate'].date()),
            "total_laps": None
        }
    except Exception as e:
        logger.warning(f"Error building session info: {e}")
        return {
            "event_name": "Unknown",
            "circuit_name": "Unknown",
            "country": "Unknown",
            "year": year,
            "round": round,
            "date": "",
            "total_laps": None
        }

@router.get("/frames/{year}/{round}")
async def get_race_frames(
    year: int = Path(..., ge=2019, le=2025),   # was ge=2018
    round: int = Path(..., ge=1, le=24),
    session_type: str = Query("R", regex="^(R|S)$"),
    max_frames: int = Query(5000, ge=100, le=50000)
):
    """Get race frames with team info"""
    try:
        logger.info(f"Loading frames: {year} R{round} {session_type}, max={max_frames}")
        
        cached_data = cache.get(year, round, session_type)
        
        if not cached_data:
            session = load_session(year, round, session_type)
            telemetry_data = get_race_telemetry(session, session_type)
            cached_data = telemetry_data
        
        all_frames = cached_data.get("frames", [])
        driver_colors = cached_data.get("driver_colors", {})
        
        # Get team info from session
        session = load_session(year, round, session_type)
        driver_teams = {}
        
        for _, row in session.results.iterrows():
            driver_code = row.get("Abbreviation")
            team_name = row.get("TeamName", "Unknown")
            if driver_code:
                driver_teams[driver_code] = team_name
        
        logger.info(f"Driver teams: {driver_teams}")
        
        # Sample frames
        if len(all_frames) > max_frames:
            step = len(all_frames) / max_frames
            sampled_frames = [all_frames[int(i * step)] for i in range(max_frames)]
            logger.info(f"Sampled {len(sampled_frames)} frames from {len(all_frames)}")
        else:
            sampled_frames = all_frames
        
        logger.info(f"✅ Returning {len(sampled_frames)} frames")
        
        return {
            "frames": sampled_frames,
            "driver_colors": driver_colors,
            "driver_teams": driver_teams,
            "total_frames": len(all_frames),
        }
        
    except Exception as e:
        logger.error(f"Error loading frames: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))   

