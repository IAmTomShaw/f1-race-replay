"""
Session management endpoints

Handles session-related operations and metadata.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging

from api.models.race import SessionType, SessionInfo
from core.f1_data import load_session, get_circuit_rotation
from config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/info/{year}/{round}")
async def get_session_info(
    year: int = Query(..., ge=settings.min_year, le=settings.max_year),
    round: int = Query(..., ge=1, le=24),
    session_type: str = Query("R", regex="^(R|S|Q|SQ)$")
):
    """
    Get basic session information without loading full telemetry
    
    Returns metadata about the session including:
    - Event name
    - Circuit name
    - Country
    - Date
    """
    try:
        logger.info(f"Loading session info: {year} R{round} {session_type}")
        
        session = load_session(year, round, session_type)
        
        return {
            "event_name": str(session.event['EventName']),
            "circuit_name": str(session.event.get('Location', 'Unknown')),
            "country": str(session.event['Country']),
            "year": year,
            "round": round,
            "date": str(session.event['EventDate'].date()),
            "session_type": session_type,
            "circuit_rotation": get_circuit_rotation(session)
        }
        
    except Exception as e:
        logger.error(f"Error loading session info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load session info: {str(e)}"
        )


@router.get("/types")
async def get_session_types():
    """
    Get available session types
    
    Returns list of valid session type codes.
    """
    return {
        "session_types": [
            {"code": "R", "name": "Race", "description": "Main race"},
            {"code": "S", "name": "Sprint", "description": "Sprint race"},
            {"code": "Q", "name": "Qualifying", "description": "Qualifying session"},
            {"code": "SQ", "name": "Sprint Qualifying", "description": "Sprint qualifying"}
        ]
    }


@router.get("/validate/{year}/{round}")
async def validate_session(
    year: int = Query(..., ge=settings.min_year, le=settings.max_year),
    round: int = Query(..., ge=1, le=24),
    session_type: str = Query("R", regex="^(R|S|Q|SQ)$")
):
    """
    Validate if a session exists and can be loaded
    
    Useful for checking availability before attempting to load telemetry.
    """
    try:
        # Try to load the session
        session = load_session(year, round, session_type)
        
        return {
            "valid": True,
            "exists": True,
            "event_name": str(session.event['EventName']),
            "message": "Session is available"
        }
        
    except Exception as e:
        logger.warning(f"Session validation failed: {e}")
        return {
            "valid": False,
            "exists": False,
            "message": str(e)
        }
    
    