from fastf1.exceptions import DataNotLoadedError

import src.f1_data as f1_data


class FakeSession:
    def __init__(self, loaded):
        self._loaded = loaded

    def load(self, **kwargs):
        pass

    @property
    def laps(self):
        if not self._loaded:
            raise DataNotLoadedError("not loaded")
        return []


def test_load_session_returns_none_when_data_not_loaded(monkeypatch, capsys):
    monkeypatch.setattr(f1_data.fastf1, "get_session", lambda *a: FakeSession(loaded=False))

    assert f1_data.load_session(2025, 12, "R") is None
    assert "could not download" in capsys.readouterr().out


def test_load_session_returns_session_when_data_loaded(monkeypatch):
    session = FakeSession(loaded=True)
    monkeypatch.setattr(f1_data.fastf1, "get_session", lambda *a: session)

    assert f1_data.load_session(2025, 12, "R") is session
