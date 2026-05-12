import pickle

from src.lib.settings import SettingsManager


def _reset_settings_singleton(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    SettingsManager._instance = None


def test_settings_default_computed_data_location(monkeypatch, tmp_path):
    _reset_settings_singleton(monkeypatch, tmp_path)

    settings = SettingsManager()

    assert settings.computed_data_location == "computed_data"


def test_computed_data_file_uses_configured_location(monkeypatch, tmp_path):
    _reset_settings_singleton(monkeypatch, tmp_path)

    settings = SettingsManager()
    settings.computed_data_location = str(tmp_path / "custom-computed")

    from src.lib.cache import get_computed_data_file

    path = get_computed_data_file("sample.pkl")

    assert path == tmp_path / "custom-computed" / "sample.pkl"
    assert path.parent.exists()


def test_cache_round_trip_uses_schema_wrapper(tmp_path):
    from src.lib.cache import CACHE_SCHEMA_VERSION, load_cached_payload, save_cached_payload

    path = tmp_path / "cache.pkl"
    payload = {"frames": [1, 2, 3]}

    save_cached_payload(path, payload)

    with open(path, "rb") as f:
        raw = pickle.load(f)

    assert raw["_cache_schema_version"] == CACHE_SCHEMA_VERSION
    assert load_cached_payload(path) == payload


def test_cache_loader_rejects_legacy_unversioned_payload(tmp_path):
    from src.lib.cache import load_cached_payload

    path = tmp_path / "legacy.pkl"
    with open(path, "wb") as f:
        pickle.dump({"frames": []}, f)

    assert load_cached_payload(path) is None


def test_cache_loader_rejects_incompatible_schema(tmp_path):
    from src.lib.cache import load_cached_payload

    path = tmp_path / "future.pkl"
    with open(path, "wb") as f:
        pickle.dump({"_cache_schema_version": 999, "payload": {"frames": []}}, f)

    assert load_cached_payload(path) is None

