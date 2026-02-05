"""
Race schedule and event endpoints
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List
import logging

from api.models.race import RaceWeekend, AvailableYearsResponse
from core.f1_data import get_race_weekends_by_year
from config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/available-years", response_model=AvailableYearsResponse)
async def get_available_years():
    """
    Get list of years with available F1 data
    
    Returns a list of years between min_year and max_year from settings.
    """
    try:
        years = settings.get_allowed_years()
        return {"years": years}
    except Exception as e:
        logger.error(f"Error getting available years: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule/{year}", response_model=List[RaceWeekend])
async def get_race_schedule(
    year: int = Query(
        ...,
        ge=settings.min_year,
        le=settings.max_year,
        description="Season year"
    )
):
    """
    Get race schedule for a specific year
    
    Returns all race weekends including:
    - Round numbers
    - Event names
    - Dates
    - Countries
    - Event types (conventional, sprint, etc.)
    """
    try:
        logger.info(f"Fetching schedule for year {year}")
        events = get_race_weekends_by_year(year)
        logger.info(f"Found {len(events)} events for {year}")
        return events
    except Exception as e:
        logger.error(f"Error fetching schedule for {year}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load schedule for {year}: {str(e)}"
        )


@router.get("/schedule/{year}/{round}", response_model=RaceWeekend)
async def get_race_weekend(
    year: int = Query(..., ge=settings.min_year, le=settings.max_year),
    round: int = Query(..., ge=1, le=24, description="Round number")
):
    """
    Get details for a specific race weekend
    
    Returns information about a single race weekend.
    """
    try:
        events = get_race_weekends_by_year(year)
        
        # Find the specific round
        weekend = next((e for e in events if e["round_number"] == round), None)
        
        if not weekend:
            raise HTTPException(
                status_code=404,
                detail=f"Round {round} not found for year {year}"
            )
        
        return weekend
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching round {round} for {year}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
