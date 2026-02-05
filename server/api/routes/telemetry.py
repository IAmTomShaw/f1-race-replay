"""
Telemetry data endpoints
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
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


@router.get("/race/{year}/{round}", response_model=TelemetryData)
async def get_race_telemetry_data(
    year: int = Query(..., ge=settings.min_year, le=settings.max_year),
    round: int = Query(..., ge=1, le=24),
    session_type: str = Query(
        "R",
        regex="^(R|S)$",
        description="Session type: R=Race, S=Sprint"
    ),
    force_refresh: bool = Query(False, description="Force refresh from source")
):
    """
    Get race telemetry data for a specific session
    
    Returns complete telemetry data including:
    - Frame-by-frame driver positions
    - Track status events (flags, safety car)
    - Driver colors
    - Weather data
    - Session information
    
    Data is cached for faster subsequent requests.
    """
    try:
        logger.info(f"Loading telemetry: {year} R{round} {session_type}")
        
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_data = cache.get(year, round, session_type)
            if cached_data:
                logger.info("Returning cached telemetry data")
                
                # Add session_info if not present (backwards compatibility)
                if "session_info" not in cached_data:
                    session = load_session(year, round, session_type)
                    cached_data["session_info"] = _build_session_info(session, year, round)
                
                return cached_data
        
        # Load fresh data
        logger.info("Loading fresh telemetry data from FastF1...")
        session = load_session(year, round, session_type)
        
        # Get telemetry (this may take time)
        telemetry_data = get_race_telemetry(session, session_type)
        
        # Get additional data
        driver_colors = get_driver_colors(session)
        circuit_rotation = get_circuit_rotation(session)
        
        # Build session info
        session_info = _build_session_info(session, year, round)
        
        # Combine all data
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
    year: int = Query(..., ge=settings.min_year, le=settings.max_year),
    round: int = Query(..., ge=1, le=24),
    session_type: str = Query("R", regex="^(R|S|Q|SQ)$")
):
    """
    Check if telemetry data is cached and available
    
    Returns cache status without loading the full data.
    Useful for UI to show if data needs to be loaded.
    """
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
async def get_cache_info(
    year: int,
    round: int,
    session_type: str = Query("R", regex="^(R|S|Q|SQ)$")
):
    """Get detailed cache information for a session"""
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
    """
    List all cached telemetry sessions
    
    Returns information about all sessions currently in cache.
    """
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
    year: int,
    round: int,
    session_type: str = Query("R", regex="^(R|S|Q|SQ)$")
):
    """
    Clear cache for a specific session
    
    Forces the next request to reload data from FastF1.
    """
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
    """
    Clear all cached telemetry data
    
    WARNING: This will delete all cached sessions.
    """
    try:
        count = cache.clear_all()
        
        return {
            "message": f"Cleared {count} cached sessions",
            "count": count
        }
        
    except Exception as e:
        logger.error(f"Error clearing all cache: {e}")
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
            "total_laps": None  # Will be filled by telemetry data
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

