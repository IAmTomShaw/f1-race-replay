"""Centralized configuration for F1 Race Replay using Pydantic Settings.

This module provides a single source of truth for all configuration values,
with support for loading from .env files and environment variables.
All values use snake_case (Pythonic) instead of UPPER_CASE.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Dict, Optional


class UIConfig(BaseSettings):
    """User interface display constants."""
    
    # Window dimensions
    screen_width: int = 1280
    screen_height: int = 720
    screen_title: str = "F1 Race Replay"
    
    # Layout dimensions
    default_margin: int = 40
    left_margin: int = 40
    right_margin: int = 40
    top_margin: int = 40
    bottom_margin: int = 40
    
    # Row heights and spacing
    h_row: int = 38
    header_h: int = 56
    
    # Qualifying interface specific
    qualifying_left_margin: int = 340
    qualifying_right_margin: int = 0
    
    # Playback controls
    playback_speeds: List[float] = [0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]
    default_playback_speed: float = 1.0
    
    # Component sizing
    button_size: int = 40
    control_button_size: int = 40
    
    # Line and shape styling
    track_line_width: int = 2
    gear_chart_line_width: int = 2
    chart_line_width: int = 2
    
    # Colors (arcade colors)
    default_color: tuple = (255, 255, 255)  # White
    error_color: tuple = (255, 0, 0)  # Red
    warning_color: tuple = (255, 165, 0)  # Orange
    success_color: tuple = (0, 255, 0)  # Green
    info_color: tuple = (135, 206, 235)  # Sky Blue
    
    # Safety Car styling
    safety_car_radius: int = 8  # pixels
    regular_car_radius: int = 6  # pixels
    safety_car_glow_alpha: int = 128
    
    # Animation durations (in seconds)
    safety_car_deploy_time: float = 3.0
    safety_car_return_time: float = 3.0
    
    # Reference point interpolation
    reference_point_interpolation: int = 4000
    
    class Config:
        env_prefix = "UI_"


class NetworkConfig(BaseSettings):
    """Network and telemetry streaming constants."""
    
    # Telemetry stream server
    telemetry_host: str = "localhost"
    telemetry_port: int = 9999
    
    # Socket configuration
    socket_timeout: float = 5.0  # seconds
    socket_buffer_size: int = 4096
    
    # Connection retry
    connection_retry_delay: float = 2.0  # seconds
    connection_max_retries: int = 10
    
    # Data transmission
    message_separator: str = "\n"
    data_encoding: str = "utf-8"
    
    class Config:
        env_prefix = "NETWORK_"


class DataConfig(BaseSettings):
    """Data processing and caching constants."""
    
    # Cache settings
    cache_enabled: bool = True
    default_cache_location: str = ".cache/fastf1"
    cache_directory: str = "computed_data"
    cache_file_extension: str = ".pkl"
    telemetry_cache_suffix: str = "telemetry"
    
    # Driver data
    max_drivers: int = 20
    default_drivers_to_display: int = 20
    
    # Telemetry frame rate
    fps: int = 25  # frames per second
    dt: float = Field(default_factory=lambda: 1.0 / 25)  # time delta between frames
    
    # Data processing
    multiprocessing_enabled: bool = True
    
    # Safety Car data
    safety_car_buffer_distance: int = 500  # meters ahead of leader
    
    # Weather data
    weather_processing_timeout: int = 30  # seconds
    
    # Session types
    session_types: Dict[str, str] = {
        'R': 'Race',
        'Q': 'Qualifying',
        'S': 'Sprint',
        'SQ': 'Sprint Qualifying',
        'FP1': 'Free Practice 1',
        'FP2': 'Free Practice 2',
        'FP3': 'Free Practice 3',
    }
    
    class Config:
        env_prefix = "DATA_"


class QueryConfig(BaseSettings):
    """Query and visualization parameters."""
    
    # Chart display
    chart_height_ratio: float = 0.25
    chart_left_margin: int = 50
    chart_bottom_margin: int = 50
    chart_right_margin: int = 50
    
    # Min/max bounds for telemetry charts
    speed_max: int = 400  # km/h (approximate F1 top speed)
    gear_max: int = 9
    
    # Track geometry
    track_wall_outer_scale: float = 1.1
    track_wall_inner_scale: float = 0.9
    
    class Config:
        env_prefix = "QUERY_"


class PerformanceConfig(BaseSettings):
    """Performance and optimization constants."""
    
    # Frame limiting
    target_fps: int = 60
    
    # Memory optimization
    telemetry_cache_size_mb: int = 500
    
    # Threading
    worker_thread_timeout: int = 30  # seconds
    
    # Display updates
    position_update_interval: float = 0.1  # seconds
    
    class Config:
        env_prefix = "PERF_"


class CLIConfig(BaseSettings):
    """Command-line interface constants."""
    
    # Default CLI values
    default_year: Optional[int] = None
    default_round: int = 12
    default_session_type: str = "R"
    default_playback_speed: float = 1.0
    
    # CLI flags
    supported_flags: List[str] = [
        '--cli',
        '--viewer',
        '--debug',
        '--verbose',
        '--qualifying',
        '--sprint-qualifying',
        '--sprint',
        '--no-hud',
        '--year',
        '--round',
        '--list-rounds',
        '--list-sprints',
        '--ready-file',
    ]
    
    class Config:
        env_prefix = "CLI_"


class LoggingConfig(BaseSettings):
    """Logging configuration constants."""
    
    # Log levels
    default_log_level: str = "INFO"
    debug_log_level: str = "DEBUG"
    
    # Third-party logger suppression
    suppress_loggers: List[str] = [
        'fastf1',
        'urllib3',
        'requests',
        'matplotlib',
    ]
    
    class Config:
        env_prefix = "LOGGING_"


# Global configuration instances - instantiate for use
# Import these and access attributes in snake_case (e.g., ui_config.screen_width)
ui_config = UIConfig()
network_config = NetworkConfig()
data_config = DataConfig()
query_config = QueryConfig()
performance_config = PerformanceConfig()
cli_config = CLIConfig()
logging_config = LoggingConfig()

# Legacy uppercase aliases for backward compatibility during migration
# These are the same instances as above
UIConfig = ui_config
NetworkConfig = network_config
DataConfig = data_config
QueryConfig = query_config
PerformanceConfig = performance_config
CLIConfig = cli_config
LoggingConfig = logging_config
