"""
API models module

Contains Pydantic models for request/response validation.
"""

from api.models.race import (
    RaceWeekend,
    SessionType,
    SessionInfo,
    AvailableYearsResponse,
    RaceScheduleResponse,
)
from api.models.telemetry import (
    TelemetryData,
    Frame,
    WeatherData,
    TrackStatus,
    TelemetryStatusResponse,
    CacheInfoResponse,
)
from api.models.driver import (
    DriverPosition,
    DriverColor,
    DriverInfo,
)

__all__ = [
    # Race models
    "RaceWeekend",
    "SessionType",
    "SessionInfo",
    "AvailableYearsResponse",
    "RaceScheduleResponse",
    # Telemetry models
    "TelemetryData",
    "Frame",
    "WeatherData",
    "TrackStatus",
    "TelemetryStatusResponse",
    "CacheInfoResponse",
    # Driver models
    "DriverPosition",
    "DriverColor",
    "DriverInfo",
]
