"""Centralized configuration constants for F1 Race Replay.

This module provides a single source of truth for all configuration values,
making it easy to tune application behavior without modifying code logic.
"""


class UIConfig:
    """User interface display constants."""
    
    # Window dimensions
    SCREEN_WIDTH = 1280
    SCREEN_HEIGHT = 720
    SCREEN_TITLE = "F1 Race Replay"
    
    # Layout dimensions
    DEFAULT_MARGIN = 40
    LEFT_MARGIN = 40
    RIGHT_MARGIN = 40
    TOP_MARGIN = 40
    BOTTOM_MARGIN = 40
    
    # Row heights and spacing
    H_ROW = 38
    HEADER_H = 56
    
    # Qualifying interface specific
    QUALIFYING_LEFT_MARGIN = 340
    QUALIFYING_RIGHT_MARGIN = 0
    
    # Playback controls
    PLAYBACK_SPEEDS = [0.5, 1.0, 2.0, 4.0]
    DEFAULT_PLAYBACK_SPEED = 1.0
    SPEED_INCREASE_FACTOR = 1.5
    SPEED_DECREASE_FACTOR = 0.67
    
    # Component sizing
    BUTTON_SIZE = 40
    CONTROL_BUTTON_SIZE = 40
    
    # Line and shape styling
    TRACK_LINE_WIDTH = 2
    TELEMETRY_LINE_WIDTH = 2
    GEAR_CHART_LINE_WIDTH = 2
    CHART_LINE_WIDTH = 2
    
    # Colors (arcade colors)
    DEFAULT_COLOR = (255, 255, 255)  # White
    ERROR_COLOR = (255, 0, 0)  # Red
    WARNING_COLOR = (255, 165, 0)  # Orange
    SUCCESS_COLOR = (0, 255, 0)  # Green
    INFO_COLOR = (135, 206, 235)  # Sky Blue
    
    # Safety Car styling
    SAFETY_CAR_RADIUS = 8  # pixels
    REGULAR_CAR_RADIUS = 6  # pixels
    SAFETY_CAR_GLOW_ALPHA = 128
    
    # Animation durations (in seconds)
    SAFETY_CAR_DEPLOY_TIME = 3.0
    SAFETY_CAR_RETURN_TIME = 3.0
    
    # Reference point interpolation
    REFERENCE_POINT_INTERPOLATION = 4000


class NetworkConfig:
    """Network and telemetry streaming constants."""
    
    # Telemetry stream server
    TELEMETRY_HOST = 'localhost'
    TELEMETRY_PORT = 9999
    
    # Socket configuration
    SOCKET_TIMEOUT = 5.0  # seconds
    SOCKET_BUFFER_SIZE = 4096
    
    # Connection retry
    CONNECTION_RETRY_DELAY = 2.0  # seconds
    CONNECTION_MAX_RETRIES = 10
    
    # Data transmission
    MESSAGE_SEPARATOR = '\n'
    DATA_ENCODING = 'utf-8'


class DataConfig:
    """Data processing and caching constants."""
    
    # Cache settings
    CACHE_ENABLED = True
    DEFAULT_CACHE_LOCATION = '.cache/fastf1'
    
    # Driver data
    MAX_DRIVERS = 20
    DEFAULT_DRIVERS_TO_DISPLAY = 20
    
    # Telemetry frame rate
    FPS = 25  # frames per second
    DT = 1.0 / FPS  # time delta between frames
    
    # Data processing
    MULTIPROCESSING_ENABLED = True
    
    # Safety Car data
    SAFETY_CAR_BUFFER_DISTANCE = 500  # meters ahead of leader
    
    # Weather data
    WEATHER_PROCESSING_TIMEOUT = 30  # seconds
    
    # Session types
    SESSION_TYPES = {
        'R': 'Race',
        'Q': 'Qualifying',
        'S': 'Sprint',
        'SQ': 'Sprint Qualifying',
        'FP1': 'Free Practice 1',
        'FP2': 'Free Practice 2',
        'FP3': 'Free Practice 3',
    }


class QueryConfig:
    """Query and visualization parameters."""
    
    # Chart display
    CHART_HEIGHT_RATIO = 0.25
    CHART_LEFT_MARGIN = 50
    CHART_BOTTOM_MARGIN = 50
    CHART_RIGHT_MARGIN = 50
    
    # Min/max bounds for telemetry charts
    SPEED_MAX = 400  # km/h (approximate F1 top speed)
    GEAR_MAX = 9
    
    # Track geometry
    TRACK_WALL_OUTER_SCALE = 1.1
    TRACK_WALL_INNER_SCALE = 0.9


class PerformanceConfig:
    """Performance and optimization constants."""
    
    # Frame limiting
    TARGET_FPS = 60
    
    # Memory optimization
    TELEMETRY_CACHE_SIZE_MB = 500
    
    # Threading
    WORKER_THREAD_TIMEOUT = 30  # seconds
    
    # Display updates
    POSITION_UPDATE_INTERVAL = 0.1  # seconds


class CLIConfig:
    """Command-line interface constants."""
    
    # Default CLI values
    DEFAULT_YEAR = None  # Will use current season
    DEFAULT_ROUND = 12
    DEFAULT_SESSION_TYPE = 'R'
    DEFAULT_PLAYBACK_SPEED = 1.0
    
    # CLI flags
    SUPPORTED_FLAGS = [
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


class LoggingConfig:
    """Logging configuration constants."""
    
    # Log levels
    DEFAULT_LOG_LEVEL = 'INFO'
    DEBUG_LOG_LEVEL = 'DEBUG'
    
    # Third-party logger suppression
    SUPPRESS_LOGGERS = [
        'fastf1',
        'urllib3',
        'requests',
        'matplotlib',
    ]
    
    # Log format
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


# Convenience functions for accessing config by category
def get_ui_config() -> dict:
    """Get UI configuration as dictionary."""
    return {k: v for k, v in UIConfig.__dict__.items() if not k.startswith('_')}


def get_network_config() -> dict:
    """Get network configuration as dictionary."""
    return {k: v for k, v in NetworkConfig.__dict__.items() if not k.startswith('_')}


def get_data_config() -> dict:
    """Get data configuration as dictionary."""
    return {k: v for k, v in DataConfig.__dict__.items() if not k.startswith('_')}
