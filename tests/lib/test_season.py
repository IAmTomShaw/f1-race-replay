from datetime import datetime

import src.lib.season as season


class FixedDate(datetime):
    fixed_now = datetime(2025, 3, 1)

    @classmethod
    def now(cls):
        return cls.fixed_now


def test_get_season_returns_current_year_from_february(monkeypatch):
    FixedDate.fixed_now = datetime(2025, 2, 1)
    monkeypatch.setattr(season, "date", FixedDate)

    assert season.get_season() == 2025


def test_get_season_returns_current_year_after_february(monkeypatch):
    FixedDate.fixed_now = datetime(2025, 7, 15)
    monkeypatch.setattr(season, "date", FixedDate)

    assert season.get_season() == 2025


def test_get_season_returns_previous_year_in_january(monkeypatch):
    FixedDate.fixed_now = datetime(2025, 1, 15)
    monkeypatch.setattr(season, "date", FixedDate)

    assert season.get_season() == 2024
