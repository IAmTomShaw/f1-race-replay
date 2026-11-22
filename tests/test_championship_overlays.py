import pytest

ui_components = pytest.importorskip("src.ui_components")

ARROWS = {"▲", "▼", "•"}


class FakeSession:
    drivers = ["1", "2", "3"]

    def get_driver(self, number):
        return {"TeamName": {"1": "Red", "2": "Blue", "3": "Green"}[number]}


@pytest.fixture
def drawn_text(monkeypatch):
    calls = []
    monkeypatch.setattr(ui_components.arcade, "draw_text", lambda text, x, y, *args, **kwargs: calls.append((text, y)))
    monkeypatch.setattr(ui_components.arcade, "draw_rect_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(ui_components.fastf1.plotting, "get_team_color", lambda *args, **kwargs: "#ffffff")
    return calls


def rows_and_arrows(calls, names):
    rows = {text: y for text, y in calls if text in names}
    arrows = [(text, y) for text, y in calls if text in ARROWS]
    return rows, arrows


def test_drivers_overlay_draws_an_arrow_on_each_row(drawn_text):
    overlay = ui_components.DriversChampionshipOverlay(
        live_standings={1: {"VER": 25, "HAM": 18, "LEC": 15}},
        current_driver_standings={"HAM": 0, "VER": 0, "LEC": 0},
    )
    overlay.update(1)

    overlay.draw()

    rows, arrows = rows_and_arrows(drawn_text, {"VER", "HAM", "LEC"})
    assert arrows == [("▲", rows["VER"]), ("▼", rows["HAM"]), ("•", rows["LEC"])]


def test_constructors_overlay_draws_an_arrow_on_each_row(drawn_text):
    overlay = ui_components.ConstructorsChampionshipOverlay(
        live_constructors_standings={1: {"Red": 25, "Blue": 18, "Green": 15}},
        current_constructors_standings={"Blue": 0, "Red": 0, "Green": 0},
        session=FakeSession(),
    )
    overlay.update(1)

    overlay.draw()

    rows, arrows = rows_and_arrows(drawn_text, {"Red", "Blue", "Green"})
    assert arrows == [("▲", rows["Red"]), ("▼", rows["Blue"]), ("•", rows["Green"])]


def test_drivers_overlay_draws_an_arrow_on_the_last_row(drawn_text):
    standings = {f"D{i:02}": 100 - i for i in range(1, 24)}
    overlay = ui_components.DriversChampionshipOverlay(
        live_standings={1: standings},
        current_driver_standings=standings,
    )
    overlay.update(1)

    overlay.draw()

    rows, arrows = rows_and_arrows(drawn_text, set(standings))
    assert len(rows) == 22
    assert len(arrows) == 22
    assert arrows[-1][1] == rows["D22"]
