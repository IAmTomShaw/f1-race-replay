import threading

import pytest

pytest.importorskip("arcade")

import src.services.circuit_map as circuit_map
from src.ui_components import MapUnderlayComponent


def bare_component():
    # Skip __init__ (it creates a GL text object); only the loading state matters here.
    comp = MapUnderlayComponent.__new__(MapUnderlayComponent)
    comp._pending, comp._texture, comp._status = None, None, None
    return comp


def run_load(comp, monkeypatch, fake):
    monkeypatch.setattr(circuit_map, "build_track_map", fake)
    started = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self) or self.run())
    comp.load_async()
    assert started, "map should load on a background thread"


def test_download_failure_shows_a_visible_status(monkeypatch):
    comp = bare_component()

    def offline(**_):
        raise OSError("no network")

    run_load(comp, monkeypatch, offline)
    assert comp._pending is None
    assert "unavailable" in comp._status


def test_no_matching_layout_says_so(monkeypatch):
    comp = bare_component()
    run_load(comp, monkeypatch, lambda **_: None)
    assert comp._status == "No real-world map for this track layout"
