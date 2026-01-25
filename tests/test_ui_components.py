import pytest
import arcade
from src.ui_components import RaceControlsComponent


def test_speed_comp_missing_plus(monkeypatch):
    comp = RaceControlsComponent()
    # Only speed- texture present (simulate partial asset availability)
    comp._control_textures = {'speed-': object()}

    # Monkeypatch arcade drawing primitives to no-op to allow headless testing
    monkeypatch.setattr(arcade, 'draw_texture_rect', lambda *a, **k: None)
    monkeypatch.setattr(arcade, 'draw_rect_filled', lambda *a, **k: None)

    # Ensure no exception is raised and rects remain None
    comp._hide_speed_text = True
    comp._draw_speed_comp(100, 100, 1.0)
    assert comp.speed_increase_rect is None
    assert comp.speed_decrease_rect is None


def test_speed_comp_both_textures(monkeypatch):
    comp = RaceControlsComponent()
    comp._control_textures = {'speed-': object(), 'speed+': object()}

    monkeypatch.setattr(arcade, 'draw_texture_rect', lambda *a, **k: None)
    monkeypatch.setattr(arcade, 'draw_rect_filled', lambda *a, **k: None)

    # Provide a minimal Text replacement used by drawing
    class FakeText:
        def __init__(self, *a, **k):
            self.content_width = 10
        def draw(self):
            pass

    monkeypatch.setattr(arcade, 'Text', FakeText)

    comp._hide_speed_text = False
    # Should not raise and should set rect tuples for speed buttons
    comp._draw_speed_comp(200, 200, 2.0)
    assert comp.speed_increase_rect is not None
    assert comp.speed_decrease_rect is not None
