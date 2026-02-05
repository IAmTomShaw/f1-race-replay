"""
Race-related Pydantic models for API validation
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class SessionType(str, Enum):
    """F1 session types"""
    RACE = "R"
    SPRINT = "S"
    QUALIFYING = "Q"
    SPRINT_QUALIFYING = "SQ"


class RaceWeekend(BaseModel):
    """Race weekend information"""
    round_number: int = Field(..., ge=1, le=24, description="Round number in the season")
    event_name: str = Field(..., min_length=1, description="Event name")
    date: str = Field(..., description="Event date (YYYY-MM-DD)")
    country: str = Field(..., min_length=1, description="Country where event takes place")
    type: str = Field(..., description="Event format type")
    
    class Config:
        json_schema_extra = {
            "example": {
                "round_number": 1,
                "event_name": "Bahrain Grand Prix",
                "date": "2024-03-02",
                "country": "Bahrain",
                "type": "conventional"
            }
        }


class SessionInfo(BaseModel):
    """Detailed session information"""
    event_name: str
    circuit_name: str
    country: str
    year: int = Field(..., ge=2018, le=2030)
    round: int = Field(..., ge=1, le=24)
    date: str
    total_laps: Optional[int] = Field(None, ge=1, le=100)
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_name": "Bahrain Grand Prix",
                "circuit_name": "Bahrain International Circuit",
                "country": "Bahrain",
                "year": 2024,
                "round": 1,
                "date": "2024-03-02",
                "total_laps": 57
            }
        }


class AvailableYearsResponse(BaseModel):
    """Response for available years endpoint"""
    years: List[int]
    
    class Config:
        json_schema_extra = {
            "example": {
                "years": [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
            }
        }


class RaceScheduleResponse(BaseModel):
    """Response containing list of race weekends"""
    weekends: List[RaceWeekend]
    year: int
    total_rounds: int
