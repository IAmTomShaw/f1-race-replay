from types import SimpleNamespace

import pytest

ui_components = pytest.importorskip("src.ui_components")

# Changing any of these makes arcade re-lay out the text
STYLE_ATTRIBUTES = {"color", "bold", "font_size", "anchor_x", "anchor_y"}


class FakeText:
    created = []
    style_changes = []

    def __init__(self, text, x, y, color=(255, 255, 255, 255), font_size=12, **kwargs):
        object.__setattr__(self, "drawn", 0)
        self.__dict__.update(text=text, x=x, y=y, color=color, font_size=font_size, **kwargs)
        FakeText.created.append(self)

    def __setattr__(self, name, value):
        if name in STYLE_ATTRIBUTES:
            FakeText.style_changes.append(name)
        object.__setattr__(self, name, value)

    def draw(self):
        object.__setattr__(self, "drawn", self.drawn + 1)


@pytest.fixture(autouse=True)
def fake_text(monkeypatch):
    FakeText.created = []
    FakeText.style_changes = []
    monkeypatch.setattr(ui_components.arcade, "Text", FakeText)
    for name in ("draw_rect_filled", "draw_rect_outline", "draw_texture_rect"):
        monkeypatch.setattr(ui_components.arcade, name, lambda *args, **kwargs: None)


def drawn_texts():
    texts = [t.text for t in FakeText.created if t.drawn]
    for t in FakeText.created:
        object.__setattr__(t, "drawn", 0)
    return texts


def draw_twice(component, window):
    component.draw(window)
    drawn_texts()
    created, style_changes = len(FakeText.created), len(FakeText.style_changes)
    component.draw(window)
    return len(FakeText.created) - created, len(FakeText.style_changes) - style_changes


WEATHER = {"track_temp": 38.0, "air_temp": 24.0, "humidity": 50.0, "wind_speed": 3.0,
           "wind_direction": 180.0, "rain_state": "DRY"}


def test_weather_panel_reuses_text_without_restyling():
    weather = ui_components.WeatherComponent()
    weather.set_info(WEATHER)
    window = SimpleNamespace(height=800, has_weather=True)

    new_texts, style_changes = draw_twice(weather, window)

    assert (new_texts, style_changes) == (0, 0)
    shown = drawn_texts()
    assert shown.count("Weather") == 1
    assert "Track: 38.0°C" in shown


def test_weather_panel_shows_updated_values():
    weather = ui_components.WeatherComponent()
    window = SimpleNamespace(height=800, has_weather=True)
    weather.set_info(WEATHER)
    weather.draw(window)
    drawn_texts()

    weather.set_info({**WEATHER, "track_temp": 41.5, "rain_state": "RAINING"})
    weather.draw(window)

    shown = drawn_texts()
    assert "Track: 41.5°C" in shown
    assert "Rain: RAINING" in shown


def test_session_info_banner_reuses_text_without_restyling():
    banner = ui_components.SessionInfoComponent()
    banner.set_info(event_name="Bench GP", circuit_name="Bench", country="Nowhere", year=2025,
                    round_num=1, date="March 1, 2025", total_laps=57)
    window = SimpleNamespace(width=1600, height=900)

    new_texts, style_changes = draw_twice(banner, window)

    assert (new_texts, style_changes) == (0, 0)
    shown = drawn_texts()
    assert "🏁 Bench GP | Bench | 🌍 Nowhere" in shown
    assert "📅 2025 Round 1 | March 1, 2025 | 57 Laps" in shown
