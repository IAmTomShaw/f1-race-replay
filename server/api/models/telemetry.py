"""
Telemetry-related Pydantic models for API validation
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Tuple
from api.models.driver import DriverPosition
from api.models.race import SessionInfo


class WeatherData(BaseModel):
    """Weather conditions at a specific moment"""
    track_temp: Optional[float] = Field(None, description="Track temperature (°C)")
    air_temp: Optional[float] = Field(None, description="Air temperature (°C)")
    humidity: Optional[float] = Field(None, ge=0, le=100, description="Humidity percentage")
    wind_speed: Optional[float] = Field(None, ge=0, description="Wind speed (km/h)")
    wind_direction: Optional[float] = Field(None, ge=0, lt=360, description="Wind direction (degrees)")
    rain_state: str = Field(..., description="Rain state: DRY or RAINING")
    
    class Config:
        json_schema_extra = {
            "example": {
                "track_temp": 32.5,
                "air_temp": 28.0,
                "humidity": 45.0,
                "wind_speed": 12.5,
                "wind_direction": 180.0,
                "rain_state": "DRY"
            }
        }


class Frame(BaseModel):
    """Single frame of telemetry data"""
    t: float = Field(..., ge=0, description="Time in seconds since start")
    lap: int = Field(..., ge=1, description="Leader's current lap")
    drivers: Dict[str, DriverPosition] = Field(..., description="Driver positions keyed by driver code")
    weather: Optional[WeatherData] = Field(None, description="Weather data for this frame")
    
    class Config:
        json_schema_extra = {
            "example": {
                "t": 125.5,
                "lap": 5,
                "drivers": {
                    "VER": {
                        "x": 1234.5,
                        "y": 5678.9,
                        "dist": 12500.0,
                        "lap": 5,
                        "rel_dist": 0.45,
                        "tyre": 0.0,
                        "position": 1,
                        "speed": 285.5,
                        "gear": 7,
                        "drs": 0,
                        "throttle": 100.0,
                        "brake": 0.0
                    }
                },
                "weather": {
                    "track_temp": 32.5,
                    "air_temp": 28.0,
                    "humidity": 45.0,
                    "wind_speed": 12.5,
                    "wind_direction": 180.0,
                    "rain_state": "DRY"
                }
            }
        }


class TrackStatus(BaseModel):
    """Track status event (flags, safety car, etc.)"""
    status: str = Field(..., description="Status code")
    start_time: float = Field(..., ge=0, description="Start time in seconds")
    end_time: Optional[float] = Field(None, ge=0, description="End time in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "2",
                "start_time": 1250.5,
                "end_time": 1350.0
            }
        }


class TelemetryData(BaseModel):
    """Complete telemetry data for a session"""
    frames: List[Frame] = Field(..., description="List of telemetry frames")
    track_statuses: List[TrackStatus] = Field(..., description="Track status events")
    driver_colors: Dict[str, Tuple[int, int, int]] = Field(..., description="Driver colors")
    circuit_rotation: float = Field(default=0.0, description="Circuit rotation in degrees")
    total_laps: int = Field(..., ge=1, description="Total number of laps")
    session_info: SessionInfo = Field(..., description="Session information")
    
    class Config:
        json_schema_extra = {
            "example": {
                "frames": [],  # Would contain Frame examples
                "track_statuses": [],
                "driver_colors": {
                    "VER": [30, 65, 255],
                    "HAM": [0, 210, 190]
                },
                "circuit_rotation": 0.0,
                "total_laps": 57,
                "session_info": {
                    "event_name": "Bahrain Grand Prix",
                    "circuit_name": "Bahrain International Circuit",
                    "country": "Bahrain",
                    "year": 2024,
                    "round": 1,
                    "date": "2024-03-02",
                    "total_laps": 57
                }
            }
        }


class TelemetryStatusResponse(BaseModel):
    """Response for telemetry status check"""
    exists: bool
    cached: bool
    size_mb: Optional[float] = None
    created: Optional[str] = None
    modified: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "exists": True,
                "cached": True,
                "size_mb": 45.2,
                "created": "2024-03-02T14:30:00",
                "modified": "2024-03-02T14:30:00"
            }
        }


class CacheInfoResponse(BaseModel):
    """Response for cache information"""
    exists: bool
    size_bytes: Optional[int] = None
    size_mb: Optional[float] = None
    created: Optional[str] = None
    modified: Optional[str] = None
    cache_key: Optional[str] = None
    year: Optional[int] = None
    round: Optional[int] = None
    session_type: Optional[str] = None
    