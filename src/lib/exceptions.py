class F1RaceReplayError(Exception):
    """Base exception for all F1 Race Replay errors."""
    pass


# ============================================================================
# Data & Configuration Errors
# ============================================================================

class ConfigurationError(F1RaceReplayError):
    """Raised when configuration is invalid or missing."""
    pass


class SettingsError(ConfigurationError):
    """Raised when settings cannot be loaded or saved."""
    pass


class SettingsLoadError(SettingsError):
    """Raised when settings file fails to load."""
    pass


class SettingsSaveError(SettingsError):
    """Raised when settings file fails to save."""
    pass


class CacheError(F1RaceReplayError):
    """Raised when cache operations fail."""
    pass


# ============================================================================
# Data Processing Errors
# ============================================================================

class DataError(F1RaceReplayError):
    """Raised when data processing fails."""
    pass


class TelemetryError(DataError):
    """Raised when telemetry data is invalid or unavailable."""
    pass


class TelemetryParsingError(TelemetryError):
    """Raised when telemetry data cannot be parsed."""
    pass


class F1DataError(DataError):
    """Raised when F1 data operations fail."""
    pass


class SessionDataError(F1DataError):
    """Raised when session data is invalid or incomplete."""
    pass


class SessionNotAvailableError(SessionDataError):
    """Raised when requested session data is not available."""
    pass


class TimeParseError(DataError):
    """Raised when time string parsing fails."""
    pass


# ============================================================================
# Model/Degradation Errors
# ============================================================================

class ModelError(F1RaceReplayError):
    """Raised when model operations fail."""
    pass


class TyreDegradationError(ModelError):
    """Raised when tyre degradation calculations fail."""
    pass


class TyreDegradationInitializationError(TyreDegradationError):
    """Raised when tyre degradation model fails to initialize."""
    pass


class TyreDegradationQueryError(TyreDegradationError):
    """Raised when tyre degradation query fails."""
    pass


class BayesianModelError(ModelError):
    """Raised when Bayesian model operations fail."""
    pass


class BayesianFitError(BayesianModelError):
    """Raised when Bayesian model fitting fails."""
    pass


# ============================================================================
# Streaming/Network Errors
# ============================================================================

class StreamError(F1RaceReplayError):
    """Raised when streaming operations fail."""
    pass


class TelemetryStreamError(StreamError):
    """Raised when telemetry streaming fails."""
    pass


class StreamConnectionError(StreamError):
    """Raised when stream connection fails."""
    pass


class StreamBroadcastError(StreamError):
    """Raised when broadcasting to stream clients fails."""
    pass


# ============================================================================
# UI/Rendering Errors
# ============================================================================

class UIError(F1RaceReplayError):
    """Raised when UI operations fail."""
    pass


class ComponentError(UIError):
    """Raised when UI component operations fail."""
    pass


class WindowError(UIError):
    """Raised when window operations fail."""
    pass


class RenderError(UIError):
    """Raised when rendering fails."""
    pass


# ============================================================================
# Track/Geometry Errors
# ============================================================================

class TrackError(F1RaceReplayError):
    """Raised when track geometry operations fail."""
    pass


class TrackBuildError(TrackError):
    """Raised when track cannot be built from telemetry."""
    pass


class CoordinateTransformError(TrackError):
    """Raised when coordinate transformation fails."""
    pass


# ============================================================================
# File/IO Errors
# ============================================================================

class FileIOError(F1RaceReplayError):
    """Raised when file I/O operations fail."""
    pass


class FileNotFoundError(FileIOError):
    """Raised when required file is not found."""
    pass


class FileReadError(FileIOError):
    """Raised when file reading fails."""
    pass


class FileWriteError(FileIOError):
    """Raised when file writing fails."""
    pass
