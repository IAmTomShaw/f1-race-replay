from fastapi import APIRouter, HTTPException
from core.cache_manager import get_cache_manager
from core.f1_data import load_session, get_race_telemetry

router = APIRouter()

@router.get("/race/{year}/{round}")
async def get_race_telemetry_data(year: int, round: int, session_type: str = "R"):
    """Get race telemetry data (cached if available)"""
    
    cache = get_cache_manager()
    
    # Check cache first
    cached_data = cache.get(year, round, session_type)
    if cached_data:
        return cached_data
    
    # Load from FastF1 if not cached
    try:
        session = load_session(year, round, session_type)
        telemetry_data = get_race_telemetry(session, session_type)
        
        # Cache for next time
        cache.set(year, round, session_type, telemetry_data)
        
        return telemetry_data
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/info/{year}/{round}")
async def get_cache_info(year: int, round: int, session_type: str = "R"):
    """Get cache information for a session"""
    cache = get_cache_manager()
    info = cache.get_cache_info(year, round, session_type)
    
    if not info:
        return {"exists": False}
    
    return info


@router.get("/cache/list")
async def list_cached_sessions():
    """List all cached sessions"""
    cache = get_cache_manager()
    return {"sessions": cache.list_cached_sessions()}


@router.delete("/cache/{year}/{round}")
async def clear_session_cache(year: int, round: int, session_type: str = "R"):
    """Clear cache for a specific session"""
    cache = get_cache_manager()
    success = cache.delete(year, round, session_type)
    
    if success:
        return {"message": "Cache cleared successfully"}
    else:
        raise HTTPException(status_code=404, detail="Cache not found")
    