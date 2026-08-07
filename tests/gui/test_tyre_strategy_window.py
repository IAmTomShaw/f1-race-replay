import sys
import pytest
from PySide6.QtWidgets import QApplication

from src.insights.tyre_strategy_window import TyreStrategyWindow, StintBar

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

def test_tyre_strategy_window_initialization(qapp):
    win = TyreStrategyWindow(auto_start=False)
    assert hasattr(win, "_redraw_pending")
    assert hasattr(win, "_row_widgets")
    assert hasattr(win, "positions")
    assert hasattr(win, "stints")
    assert win._redraw_pending is False
    assert isinstance(win._row_widgets, dict)
    assert isinstance(win.positions, dict)
    win.close()

def test_tyre_strategy_window_telemetry_and_redraw(qapp):
    win = TyreStrategyWindow(auto_start=False)
    
    mock_data = {
        "frame": {
            "lap": 5,
            "drivers": {
                "VER": {"lap": 5, "tyre": 1, "position": 1},
                "HAM": {"lap": 5, "tyre": 2, "position": 2},
            }
        },
        "session_data": {
            "total_laps": 57
        }
    }
    
    win.on_telemetry_data(mock_data)
    assert win._redraw_pending is True
    assert win.current_lap == 5
    assert win.total_laps == 57
    assert "VER" in win.stints
    assert "HAM" in win.stints
    
    # Trigger redraw flush manually
    win._flush_redraw()
    assert win._redraw_pending is False
    assert "VER" in win._row_widgets
    assert "HAM" in win._row_widgets
    
    bar_ver = win._row_widgets["VER"]
    assert isinstance(bar_ver, StintBar)
    assert bar_ver.code == "VER"
    assert bar_ver.position == 1
    
    win.close()
