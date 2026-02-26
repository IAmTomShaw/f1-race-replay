from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Application Info
    app_name: str = "F1 Race Replay API"
    app_version: str = "1.0.0"
    debug: bool = True
    
    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api"
    
    # CORS Settings - Simple list, no complex parsing
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    
    # Paths
    project_root: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent
    )
    cache_dir: str = "computed_data"
    fastf1_cache_dir: str = ".fastf1-cache"
    static_dir: str = "shared"
    
    # FastF1 Settings
    fastf1_enable_cache: bool = True
    cache_max_age_days: int = 30
    
    # Data Processing
    telemetry_fps: int = 25
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Data Range
    min_year: int = 2018
    max_year: int = 2025
    
    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    
    # Features
    enable_qualifying: bool = False
    enable_weather: bool = True
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            return "INFO"  # Default instead of error
        return v_upper
    
    def get_cache_path(self) -> Path:
        return self.project_root / self.cache_dir
    
    def get_fastf1_cache_path(self) -> Path:
        return self.project_root / self.fastf1_cache_dir
    
    def get_static_path(self) -> Path:
        return self.project_root / self.static_dir
    
    def ensure_directories(self):
        directories = [
            self.get_cache_path(),
            self.get_fastf1_cache_path(),
            self.get_static_path(),
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_allowed_years(self) -> List[int]:
        return list(range(self.min_year, self.max_year + 1))


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings


def reload_settings():
    global _settings
    _settings = None
    return get_settings()


def get_allowed_years(self) -> list[int]:
    # 2018 and earlier lack position_data on the FastF1 livetiming source.
    # 2019 works partially; 2020+ is reliable.
    return list(range(2019, 2025))  # was range(2018, 2025)
