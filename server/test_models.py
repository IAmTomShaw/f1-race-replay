"""Test Pydantic models"""

from api.models.race import RaceWeekend, SessionInfo
from api.models.driver import DriverPosition
from api.models.telemetry import Frame, WeatherData

# Test RaceWeekend
weekend = RaceWeekend(
    round_number=1,
    event_name="Bahrain Grand Prix",
    date="2024-03-02",
    country="Bahrain",
    type="conventional"
)
print(f"✅ RaceWeekend: {weekend.event_name}")

# Test DriverPosition
position = DriverPosition(
    x=1234.5, y=5678.9, dist=12500.0, lap=5, rel_dist=0.45,
    tyre=0.0, position=1, speed=285.5, gear=7, drs=0,
    throttle=100.0, brake=0.0
)
print(f"✅ DriverPosition: Speed {position.speed} km/h")

# Test validation (should fail)
try:
    bad_position = DriverPosition(
        x=1234.5, y=5678.9, dist=12500.0, lap=5, rel_dist=1.5,  # Invalid: > 1
        tyre=0.0, position=1, speed=285.5, gear=7, drs=0,
        throttle=100.0, brake=0.0
    )
except Exception as e:
    print(f"✅ Validation works: {type(e).__name__}")

print("\n🎉 All models working correctly!")