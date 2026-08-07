"""
Unit tests for PySide6 Unified Pit Wall Dashboard (PitWallDashboardWindow).
"""

import sys
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from src.gui.pit_wall_dashboard import PitWallDashboardWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_pit_wall_dashboard_initialization(qapp):
    """Test that PitWallDashboardWindow initializes with all 5 dock widgets."""
    dash = PitWallDashboardWindow()
    assert dash is not None
    assert len(dash._dock_widgets) == 5
    assert "track" in dash._dock_widgets
    assert "telemetry" in dash._dock_widgets
    assert "tyre" in dash._dock_widgets
    assert "race_control" in dash._dock_widgets
    assert "lap_time" in dash._dock_widgets


def test_pit_wall_dashboard_preset_views(qapp):
    """Test applying docking layout presets."""
    dash = PitWallDashboardWindow()
    
    # Quad View hides lap time dock
    dash._apply_preset_view("Quad View")
    assert dash._dock_widgets["lap_time"].isHidden()

    # Driver Focus shows telemetry & track map
    dash._apply_preset_view("Driver Focus")
    assert dash._dock_widgets["tyre"].isHidden()
    assert dash._dock_widgets["race_control"].isHidden()
    assert not dash._dock_widgets["track"].isHidden()
    assert not dash._dock_widgets["telemetry"].isHidden()

    # Full Pit Wall shows all docks
    dash._apply_preset_view("Full Pit Wall")
    for dock in dash._dock_widgets.values():
        assert not dock.isHidden()
