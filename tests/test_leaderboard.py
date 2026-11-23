from types import SimpleNamespace

import pytest

ui_components = pytest.importorskip("src.ui_components")


class FakeText:
    created = []

    def __init__(self, text, x, y, color=(255, 255, 255, 255), font_size=12, **kwargs):
        self.text, self.x, self.y = text, x, y
        self.color = ui_components.arcade.types.Color.from_iterable(color)
        self.drawn = 0
        FakeText.created.append(self)

    def draw(self):
        self.drawn += 1


@pytest.fixture
def leaderboard(monkeypatch):
    FakeText.created = []
    monkeypatch.setattr(ui_components.arcade, "Text", FakeText)
    for name in ("draw_circle_filled", "draw_circle_outline", "draw_rect_filled", "draw_texture_rect"):
        monkeypatch.setattr(ui_components.arcade, name, lambda *args, **kwargs: None)
    component = ui_components.LeaderboardComponent(x=20)
    component._tyre_textures = {"1.0": object()}
    return component


def make_window(**overrides):
    window = SimpleNamespace(
        height=800, selected_drivers=[], leaderboard_show_gaps=False, leaderboard_show_neighbor_gaps=True,
        degradation_integrator=None, max_tyre_life={}, frame_index=0, frames=[{}], ctx=SimpleNamespace(scissor=None),
    )
    for key, value in overrides.items():
        setattr(window, key, value)
    return window


def entries(order):
    return [
        (code, (255, 0, 0), {"lap": 2, "dist": 10000 - i * 100, "rel_dist": 0.5, "tyre": 1.0, "tyre_life": 5}, 10000 - i * 100)
        for i, code in enumerate(order)
    ]


def drawn_texts():
    return [t.text for t in FakeText.created if t.drawn]


def test_leaderboard_reuses_text_objects_between_frames(leaderboard):
    window = make_window()
    leaderboard.set_entries(entries(["VER", "NOR", "LEC"]))
    leaderboard.draw(window)
    created_first_frame = len(FakeText.created)

    leaderboard.draw(window)

    assert created_first_frame > 0
    assert len(FakeText.created) == created_first_frame


def test_leaderboard_updates_reused_text_when_order_changes(leaderboard):
    window = make_window()
    leaderboard.set_entries(entries(["VER", "NOR", "LEC"]))
    leaderboard.draw(window)

    leaderboard.set_entries(entries(["NOR", "VER", "LEC"]))
    for text in FakeText.created:
        text.drawn = 0
    leaderboard.draw(window)

    shown = drawn_texts()
    assert "1. NOR" in shown and "2. VER" in shown
    assert "1. VER" not in shown
