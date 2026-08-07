import sys
import pytest
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import Qt

from src.gui.race_selection import RaceSelectionWindow

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

def test_race_selection_populates_practice_sessions(qapp):
    win = RaceSelectionWindow()
    
    mock_event = {
        "round_number": 1,
        "event_name": "Bahrain Grand Prix",
        "country": "Bahrain",
        "date": "2024-03-02",
        "type": "conventional",
        "year": 2024,
        "session_dates": {}
    }
    
    # Simulate clicking a conventional race item
    from PySide6.QtWidgets import QTreeWidgetItem
    item = QTreeWidgetItem(["1", "Bahrain Grand Prix", "Bahrain", "2024-03-02"])
    item.setData(0, Qt.UserRole, mock_event)
    
    win.on_race_clicked(item, 0)
    
    # Collect button labels
    buttons = []
    for i in range(win.session_list_layout.count()):
        w = win.session_list_layout.itemAt(i).widget()
        if isinstance(w, QPushButton):
            buttons.append(w.text())
            
    assert "FP1" in buttons
    assert "FP2" in buttons
    assert "FP3" in buttons
    assert "Qualifying" in buttons
    assert "Race" in buttons
    
    win.close()

def test_race_selection_populates_sprint_sessions(qapp):
    win = RaceSelectionWindow()
    
    mock_sprint_event = {
        "round_number": 5,
        "event_name": "Chinese Grand Prix",
        "country": "China",
        "date": "2024-04-21",
        "type": "sprint",
        "year": 2024,
        "session_dates": {}
    }
    
    from PySide6.QtWidgets import QTreeWidgetItem
    item = QTreeWidgetItem(["5", "Chinese Grand Prix", "China", "2024-04-21"])
    item.setData(0, Qt.UserRole, mock_sprint_event)
    
    win.on_race_clicked(item, 0)
    
    buttons = []
    for i in range(win.session_list_layout.count()):
        w = win.session_list_layout.itemAt(i).widget()
        if isinstance(w, QPushButton):
            buttons.append(w.text())
            
    assert "FP1" in buttons
    assert "Sprint Qualifying" in buttons
    assert "Sprint" in buttons
    assert "Qualifying" in buttons
    assert "Race" in buttons
    
    win.close()
