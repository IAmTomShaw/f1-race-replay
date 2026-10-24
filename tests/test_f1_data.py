import os
import pickle
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("fastf1")
import src.f1_data as f1_data


@pytest.mark.parametrize("rotation", [92, 0, -45, "92.5"])
def test_circuit_rotation_preserves_valid_metadata(rotation):
    session = SimpleNamespace(get_circuit_info=lambda: SimpleNamespace(rotation=rotation))
    assert f1_data.get_circuit_rotation(session) == float(rotation)


@pytest.mark.parametrize("circuit", [
    None, SimpleNamespace(), SimpleNamespace(rotation=None),
    SimpleNamespace(rotation="invalid"), SimpleNamespace(rotation=float("nan")),
    SimpleNamespace(rotation=float("inf")),
])
def test_circuit_rotation_falls_back_for_unusable_metadata(circuit):
    session = SimpleNamespace(get_circuit_info=lambda: circuit)
    assert f1_data.get_circuit_rotation(session) == 0.0


def test_bahrain_circuit_metadata_exception_does_not_abort_playback():
    session = SimpleNamespace(get_circuit_info=Mock(
        side_effect=AttributeError("'NoneType' object has no attribute 'add_marker_distance'")
    ))
    assert f1_data.get_circuit_rotation(session) == 0.0


@pytest.mark.parametrize("session_type,suffix,loader", [
    ("R", "race", f1_data.get_race_telemetry),
    ("S", "sprint", f1_data.get_race_telemetry),
    ("Q", "quali", f1_data.get_quali_telemetry),
    ("SQ", "sprintquali", f1_data.get_quali_telemetry),
])
def test_bahrain_portable_cache_is_reused(tmp_path, monkeypatch, session_type, suffix, loader):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(f1_data.sys, "argv", ["main.py"])
    cache = tmp_path / "computed_data"
    cache.mkdir()
    # Supply no telemetry attributes: loading must use the existing cache.
    session = "2026 Season Round 16: Bahrain Grand Prix - Race"
    filename = f"2026_Season_Round_16__Bahrain_Grand_Prix_-_Race_{suffix}_telemetry.pkl"
    payload = {"frames": [{"time": 1}], "total_laps": 57}
    (cache / filename).write_bytes(pickle.dumps(payload))
    assert loader(session, session_type) == payload


def test_cache_path_sanitizes_reserved_characters():
    path = f1_data._telemetry_cache_path('Round 16: Bahrain <>"/\\|?*\x00\x1f', "race")
    assert os.path.dirname(path) == "computed_data"
    assert not set('<>:"/\\|?*\x00\x1f').intersection(os.path.basename(path))


@pytest.mark.skipif(os.name == "nt", reason="legacy colon filenames are for POSIX only")
def test_existing_mac_cache_remains_readable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = tmp_path / "computed_data"
    cache.mkdir()
    payload = {"frames": ["existing data"]}
    (cache / "Bahrain:_Race_race_telemetry.pkl").write_bytes(pickle.dumps(payload))
    assert f1_data._load_telemetry_cache("Bahrain: Race", "race") == payload


def test_windows_never_opens_legacy_colon_cache(monkeypatch):
    # Mock only this module's platform view, not global os.name (which would
    # change pathlib's behavior on the host running pytest).
    monkeypatch.setattr(f1_data, "os", SimpleNamespace(name="nt", path=os.path))
    cache_open = Mock(side_effect=FileNotFoundError)
    monkeypatch.setattr(f1_data, "open", cache_open, raising=False)
    with pytest.raises(FileNotFoundError):
        f1_data._load_telemetry_cache("Bahrain: Race", "race")
    cache_open.assert_called_once_with(os.path.join("computed_data", "Bahrain__Race_race_telemetry.pkl"), "rb")


@pytest.mark.parametrize("session_type,suffix", [("Q", "quali"), ("SQ", "sprintquali")])
def test_fresh_qualifying_cache_uses_portable_filename(tmp_path, monkeypatch, session_type, suffix):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(f1_data.sys, "argv", ["main.py"])
    session = Mock(drivers=["1"])
    session.__str__ = Mock(return_value="Bahrain: Qualifying")
    session.get_driver.return_value = {"Abbreviation": "VER"}
    monkeypatch.setattr(f1_data, "get_qualifying_results", lambda _: [])
    pool = Mock()
    pool.map.return_value = [{
        "driver_code": "VER", "driver_full_name": "Max Verstappen",
        "driver_telemetry_data": {}, "max_speed": 300.0, "min_speed": 50.0,
    }]
    pool_context = Mock()
    pool_context.__enter__ = Mock(return_value=pool)
    pool_context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(f1_data, "Pool", lambda **_: pool_context)
    result = f1_data.get_quali_telemetry(session, session_type)
    cache_path = Path("computed_data") / f"Bahrain__Qualifying_{suffix}_telemetry.pkl"
    assert pickle.loads(cache_path.read_bytes()) == result
