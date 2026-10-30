import pytest

main = pytest.importorskip("main")


def test_main_enables_cache_before_loading_session(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "enable_cache", lambda: calls.append("enable_cache"))
    monkeypatch.setattr(main, "load_session", lambda *args: calls.append("load_session"))

    main.main(2025, 2, session_type="Q")

    assert calls[:2] == ["enable_cache", "load_session"]
