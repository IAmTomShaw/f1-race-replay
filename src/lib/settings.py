"""
Settings manager for F1 Race Replay application.
Handles loading, saving, and accessing application configuration.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional


class SettingsManager:
    """Manages application settings with JSON file persistence."""

    # Default settings values
    DEFAULTS = {
        "cache_location": ".fastf1-cache",
        "computed_data_location": "computed_data",
    }

    _instance: Optional["SettingsManager"] = None

    def __new__(cls) -> "SettingsManager":
        """Singleton pattern to ensure only one settings instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._settings: dict = {}
        self._settings_file = self._get_settings_file_path()
        self.load()

    def _get_settings_file_path(self) -> Path:
        """Get the path to the settings file.

        Settings are stored in the user's app data directory for persistence
        across different working directories.
        """
        # Use user's home directory for settings
        if os.name == "nt":  # Windows
            app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
            settings_dir = Path(app_data) / "F1RaceReplay"
        else:  # macOS/Linux
            settings_dir = Path.home() / ".config" / "f1-race-replay"

        settings_dir.mkdir(parents=True, exist_ok=True)
        return settings_dir / "settings.json"

    def load(self) -> None:
        """Load settings from the JSON file."""
        self._settings = dict(self.DEFAULTS)

        if self._settings_file.exists():
            try:
                with open(self._settings_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self._settings.update(loaded)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load settings file: {e}")

    def save(self) -> None:
        """Save current settings to the JSON file."""
        try:
            with open(self._settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save settings file: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key.

        Args:
            key: The setting key to retrieve.
            default: Default value if key doesn't exist.

        Returns:
            The setting value or default.
        """
        return self._settings.get(
            key, default if default is not None else self.DEFAULTS.get(key)
        )

    def set(self, key: str, value: Any) -> None:
        """Set a setting value.

        Args:
            key: The setting key to set.
            value: The value to store.
        """
        self._settings[key] = value

    def reset_to_defaults(self) -> None:
        """Reset all settings to their default values."""
        self._settings = dict(self.DEFAULTS)
        self.save()

    @property
    def cache_location(self) -> str:
        """Get the FastF1 cache location."""
        return self.get("cache_location")

    @cache_location.setter
    def cache_location(self, value: str) -> None:
        """Set the FastF1 cache location."""
        self.set("cache_location", value)

    @property
    def computed_data_location(self) -> str:
        """Get the computed data location."""
        return self.get("computed_data_location")

    @computed_data_location.setter
    def computed_data_location(self, value: str) -> None:
        """Set the computed data location."""
        self.set("computed_data_location", value)


# Global convenience function to get the settings instance
def get_settings() -> SettingsManager:
    """Get the global settings manager instance."""
    return SettingsManager()
