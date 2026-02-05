"""
Configuration Settings for F1 Race Replay API

Manages application settings using environment variables and default values.
Uses pydantic for validation and type safety.
"""

import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Application Info
    app_name: str = "F1 Race Replay API"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, description="Enable debug mode")
    
    # API Settings
    api_host: str = Field(default="0.0.0.0", description="API host address")
    api_port: int = Field(default=8000, description="API port")
    api_prefix: str = Field(default="/api", description="API route prefix")
    
    # CORS Settings
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        description="Allowed CORS origins"
    )
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    
    # Paths
    project_root: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent,
        description="Project root directory"
    )
    cache_dir: str = Field(default="computed_data", description="Cache directory name")
    fastf1_cache_dir: str = Field(default=".fastf1-cache", description="FastF1 cache directory")
    static_dir: str = Field(default="shared", description="Static files directory")
    
    # FastF1 Settings
    fastf1_enable_cache: bool = Field(default=True, description="Enable FastF1 caching")
    cache_max_age_days: int = Field(default=30, description="Maximum cache age in days")
    
    # Data Processing Settings
    telemetry_fps: int = Field(default=25, description="Frames per second for telemetry")
    enable_multiprocessing: bool = Field(default=False, description="Enable multiprocessing")
    max_workers: Optional[int] = Field(default=None, description="Max worker processes")
    
    # API Rate Limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Max requests per window")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")
    
    # WebSocket Settings
    ws_heartbeat_interval: int = Field(default=30, description="WebSocket heartbeat interval")
    ws_timeout: int = Field(default=60, description="WebSocket timeout in seconds")
    
    # Logging Settings
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )
    log_file: Optional[str] = Field(default=None, description="Log file path")
    
    # Database Settings (for future use)
    database_url: Optional[str] = Field(default=None, description="Database connection URL")
    
    # Security Settings
    secret_key: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT/sessions"
    )
    access_token_expire_minutes: int = Field(default=30, description="Access token expiry")
    
    # Feature Flags
    enable_qualifying: bool = Field(default=False, description="Enable qualifying features")
    enable_weather: bool = Field(default=True, description="Enable weather data")
    enable_telemetry_streaming: bool = Field(default=False, description="Enable telemetry streaming")
    
    # Performance Settings
    request_timeout: int = Field(default=300, description="Request timeout in seconds")
    max_request_size: int = Field(default=10 * 1024 * 1024, description="Max request size in bytes")
    
    # Data Range Settings
    min_year: int = Field(default=2018, description="Minimum supported year")
    max_year: int = Field(default=2025, description="Maximum supported year")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v_upper
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    def get_cache_path(self) -> Path:
        """Get full cache directory path"""
        return self.project_root / self.cache_dir
    
    def get_fastf1_cache_path(self) -> Path:
        """Get full FastF1 cache directory path"""
        return self.project_root / self.fastf1_cache_dir
    
    def get_static_path(self) -> Path:
        """Get full static files directory path"""
        return self.project_root / self.static_dir
    
    def ensure_directories(self):
        """Create necessary directories if they don't exist"""
        directories = [
            self.get_cache_path(),
            self.get_fastf1_cache_path(),
            self.get_static_path(),
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return not self.debug
    
    def get_allowed_years(self) -> List[int]:
        """Get list of allowed years"""
        return list(range(self.min_year, self.max_year + 1))


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the global settings instance
    
    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings


# Convenience function to reload settings
def reload_settings():
    """Reload settings from environment"""
    global _settings
    _settings = None
    return get_settings()
