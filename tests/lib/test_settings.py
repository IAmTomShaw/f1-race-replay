import json
from pathlib import Path

from src.lib.settings import SettingsManager


def reset_settings_singleton():
    SettingsManager._instance = None


def test_settings_manager_loads_defaults(monkeypatch, tmp_path):
    reset_settings_singleton()
    settings_file = tmp_path / "settings.json"

    monkeypatch.setattr(
        SettingsManager,
        "_get_settings_file_path",
        lambda self: settings_file,
    )

    manager = SettingsManager()

    assert manager.cache_location == ".fastf1-cache"
    assert manager.computed_data_location == "computed_data"


def test_settings_manager_reads_existing_json_file(monkeypatch, tmp_path):
    reset_settings_singleton()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "cache_location": "custom-cache",
                "computed_data_location": "custom-data",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        SettingsManager,
        "_get_settings_file_path",
        lambda self: settings_file,
    )

    manager = SettingsManager()

    assert manager.cache_location == "custom-cache"
    assert manager.computed_data_location == "custom-data"


def test_settings_manager_set_and_get_values(monkeypatch, tmp_path):
    reset_settings_singleton()
    settings_file = tmp_path / "settings.json"

    monkeypatch.setattr(
        SettingsManager,
        "_get_settings_file_path",
        lambda self: settings_file,
    )

    manager = SettingsManager()
    manager.set("example_key", "example-value")

    assert manager.get("example_key") == "example-value"
    assert manager.get("missing_key", "fallback") == "fallback"


def test_settings_manager_property_setters(monkeypatch, tmp_path):
    reset_settings_singleton()
    settings_file = tmp_path / "settings.json"

    monkeypatch.setattr(
        SettingsManager,
        "_get_settings_file_path",
        lambda self: settings_file,
    )

    manager = SettingsManager()
    manager.cache_location = "cache-dir"
    manager.computed_data_location = "computed-dir"

    assert manager.cache_location == "cache-dir"
    assert manager.computed_data_location == "computed-dir"


def test_settings_manager_save_writes_json_file(monkeypatch, tmp_path):
    reset_settings_singleton()
    settings_file = tmp_path / "settings.json"

    monkeypatch.setattr(
        SettingsManager,
        "_get_settings_file_path",
        lambda self: settings_file,
    )

    manager = SettingsManager()
    manager.cache_location = "saved-cache"
    manager.save()

    saved_data = json.loads(settings_file.read_text(encoding="utf-8"))

    assert saved_data["cache_location"] == "saved-cache"


def test_settings_manager_reset_to_defaults(monkeypatch, tmp_path):
    reset_settings_singleton()
    settings_file = tmp_path / "settings.json"

    monkeypatch.setattr(
        SettingsManager,
        "_get_settings_file_path",
        lambda self: settings_file,
    )

    manager = SettingsManager()
    manager.cache_location = "custom-cache"

    manager.reset_to_defaults()

    assert manager.cache_location == ".fastf1-cache"
    assert manager.computed_data_location == "computed_data"
