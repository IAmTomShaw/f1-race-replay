# Comparative Telemetry Module
# Provides tools for comparing telemetry data between two laps

from .telemetry_compare import (
    interpolate_telemetry_to_distance,
    align_telemetry_by_distance,
    calculate_delta_time,
    create_telemetry_comparison,
    extract_lap_telemetry_from_frames,
    TelemetryComparison,
)
from .compare_chart import (
    create_comparison_chart,
    show_comparison_chart,
    create_mini_comparison_chart,
)

__all__ = [
    'interpolate_telemetry_to_distance',
    'align_telemetry_by_distance', 
    'calculate_delta_time',
    'create_telemetry_comparison',
    'extract_lap_telemetry_from_frames',
    'TelemetryComparison',
    'create_comparison_chart',
    'show_comparison_chart',
    'create_mini_comparison_chart',
]
