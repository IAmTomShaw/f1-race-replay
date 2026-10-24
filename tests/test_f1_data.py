import pytest

f1_data = pytest.importorskip("src.f1_data")
from fastf1.exceptions import DataNotLoadedError


class FakeSession:
    def __init__(self, laps_loaded):
        self._laps_loaded = laps_loaded

    def load(self, **kwargs):
        pass

    @property
    def laps(self):
        if not self._laps_loaded:
            raise DataNotLoadedError("The data you are trying to access has not been loaded yet.")
        return ["lap"]


def test_load_session_returns_session_with_timing_data(monkeypatch):
    session = FakeSession(laps_loaded=True)
    monkeypatch.setattr(f1_data.fastf1, "get_session", lambda *args: session)

    assert f1_data.load_session(2025, 2, "Q") is session


def test_load_session_returns_none_without_timing_data(monkeypatch, capsys):
    monkeypatch.setattr(f1_data.fastf1, "get_session", lambda *args: FakeSession(laps_loaded=False))

    assert f1_data.load_session(2025, 2, "Q") is None
    assert "No timing data available" in capsys.readouterr().out
