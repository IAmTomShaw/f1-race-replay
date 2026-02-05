"""
Driver-related Pydantic models for API validation
"""

from pydantic import BaseModel, Field
from typing import Tuple, Optional


class DriverPosition(BaseModel):
    """Driver position and telemetry at a specific frame"""
    x: float = Field(..., description="X coordinate on track (meters)")
    y: float = Field(..., description="Y coordinate on track (meters)")
    dist: float = Field(..., ge=0, description="Total distance covered (meters)")
    lap: int = Field(..., ge=1, description="Current lap number")
    rel_dist: float = Field(..., ge=0, le=1, description="Relative distance around lap (0-1)")
    tyre: float = Field(..., description="Tyre compound (numeric)")
    position: int = Field(..., ge=1, le=20, description="Current position in race")
    speed: float = Field(..., ge=0, description="Speed in km/h")
    gear: int = Field(..., ge=0, le=8, description="Current gear")
    drs: int = Field(..., ge=0, description="DRS status")
    throttle: float = Field(..., ge=0, le=100, description="Throttle percentage")
    brake: float = Field(..., ge=0, le=100, description="Brake percentage")
    
    class Config:
        json_schema_extra = {
            "example": {
                "x": 1234.5,
                "y": 5678.9,
                "dist": 12500.0,
                "lap": 5,
                "rel_dist": 0.45,
                "tyre": 0.0,
                "position": 3,
                "speed": 285.5,
                "gear": 7,
                "drs": 0,
                "throttle": 100.0,
                "brake": 0.0
            }
        }


class DriverColor(BaseModel):
    """Driver team color in RGB"""
    code: str = Field(..., min_length=3, max_length=3, description="3-letter driver code")
    color: Tuple[int, int, int] = Field(..., description="RGB color tuple")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "VER",
                "color": [30, 65, 255]
            }
        }


class DriverInfo(BaseModel):
    """Basic driver information"""
    code: str = Field(..., min_length=3, max_length=3)
    full_name: str
    team: Optional[str] = None
    number: Optional[int] = Field(None, ge=1, le=99)
    color: Optional[Tuple[int, int, int]] = None
    