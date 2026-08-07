"""
Unified PySide6 Pit Wall Control Center (Dockable Dashboard).

Consolidates all live telemetry insight views (Track Position Map, Driver
Telemetry, Live Tyre Strategy, Race Control Feed, Lap Time & Gap Evolution)
into a single, highly-customizable workspace using QDockWidget.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QToolBar, QMenu, QStatusBar, QPushButton, QComboBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QAction, QIcon

from src.gui.pit_wall_window import PitWallWindow
from src.insights.track_position_window import TrackPositionWindow
from src.insights.driver_telemetry_window import DriverTelemetryWindow
from src.insights.tyre_strategy_window import TyreStrategyWindow
from src.insights.race_control_feed_window import RaceControlFeedWindow
from src.insights.lap_time_chart_window import LapTimeChartWindow

# Modern F1 Dark QSS Theme
DASHBOARD_QSS = """
QMainWindow {
    background-color: #12121A;
    color: #E0E0E0;
}

QDockWidget {
    border: 1px solid #2B2B3D;
    font-weight: bold;
    font-size: 12px;
}

QDockWidget::title {
    background: #1C1C28;
    color: #E10600;
    padding: 6px;
    border-bottom: 2px solid #E10600;
    text-transform: uppercase;
    letter-spacing: 1px;
}

QDockWidget::float-button, QDockWidget::close-button {
    border: 1px solid transparent;
    background: #252535;
    padding: 2px;
}

QDockWidget::float-button:hover, QDockWidget::close-button:hover {
    background: #E10600;
}

QToolBar {
    background: #181824;
    border-bottom: 1px solid #2B2B3D;
    spacing: 8px;
    padding: 4px;
}

QToolButton {
    background: #222230;
    color: #FFFFFF;
    border: 1px solid #3A3A50;
    border-radius: 4px;
    padding: 5px 12px;
    font-weight: bold;
}

QToolButton:hover {
    background: #E10600;
    border-color: #E10600;
}

QToolButton:pressed {
    background: #B30000;
}

QStatusBar {
    background: #14141E;
    color: #8888AA;
    border-top: 1px solid #2B2B3D;
}
"""


class PitWallDashboardWindow(PitWallWindow):
    """
    Unified Dockable Pit Wall Control Center containing all telemetry
    insight modules in an adaptable, multi-dock workspace.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Pit Wall Control Center 🏎️")
        self.resize(1400, 900)
        self.setStyleSheet(DASHBOARD_QSS)

        # Configure dockable layout behavior
        self.setDockOptions(
            QMainWindow.AllowNestedDocks |
            QMainWindow.AllowTabbedDocks |
            QMainWindow.AnimatedDocks
        )

        self._dock_widgets = {}
        self._insight_windows = {}

        self._setup_docks()
        self._setup_menu_and_toolbar()

    def setup_ui(self):
        """Called during base class init for central widget setup."""
        central = QWidget()
        central.setMinimumSize(0, 0)
        self.setCentralWidget(central)

    def _setup_docks(self):
        """Instantiate and embed insight modules into QDockWidgets."""

        # 1. Track Position Map Dock
        self._track_window = TrackPositionWindow(master_client=self.client, auto_start=False)
        dock_track = self._create_dock("Track Position Map", self._track_window.centralWidget())
        self.addDockWidget(Qt.LeftDockWidgetArea, dock_track)
        self._dock_widgets["track"] = dock_track
        self._insight_windows["track"] = self._track_window

        # 2. Driver Telemetry Dock
        self._driver_telemetry_window = DriverTelemetryWindow(master_client=self.client, auto_start=False)
        dock_telemetry = self._create_dock("Driver Telemetry", self._driver_telemetry_window.centralWidget())
        self.addDockWidget(Qt.RightDockWidgetArea, dock_telemetry)
        self._dock_widgets["telemetry"] = dock_telemetry
        self._insight_windows["telemetry"] = self._driver_telemetry_window

        # 3. Live Tyre Strategy Dock
        self._tyre_window = TyreStrategyWindow(master_client=self.client, auto_start=False)
        dock_tyre = self._create_dock("Tyre Strategy & Stints", self._tyre_window.centralWidget())
        self.addDockWidget(Qt.BottomDockWidgetArea, dock_tyre)
        self._dock_widgets["tyre"] = dock_tyre
        self._insight_windows["tyre"] = self._tyre_window

        # 4. Race Control Feed Dock
        self._race_control_window = RaceControlFeedWindow(master_client=self.client, auto_start=False)
        dock_rc = self._create_dock("Race Control Feed", self._race_control_window.centralWidget())
        self.splitDockWidget(dock_tyre, dock_rc, Qt.Horizontal)
        self._dock_widgets["race_control"] = dock_rc
        self._insight_windows["race_control"] = self._race_control_window

        # 5. Lap Time & Pace Dock
        self._lap_window = LapTimeChartWindow(master_client=self.client, auto_start=False)
        dock_lap = self._create_dock("Lap Pace & Gap Evolution", self._lap_window.centralWidget())
        self.tabifyDockWidget(dock_telemetry, dock_lap)
        self._dock_widgets["lap_time"] = dock_lap
        self._insight_windows["lap_time"] = self._lap_window

    def _create_dock(self, title: str, widget: QWidget) -> QDockWidget:
        """Helper to create a styled QDockWidget hosting a central insight widget."""
        dock = QDockWidget(f"  {title}", self)
        dock.setObjectName(f"Dock_{title.replace(' ', '_')}")
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        dock.setWidget(widget)
        return dock

    def _setup_menu_and_toolbar(self):
        """Create header toolbar and view menu for preset toggles."""
        toolbar = QToolBar("Pit Wall Controls", self)
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # Title Label
        title_label = QLabel(" 🏎️ PIT WALL CONTROL CENTER  ")
        title_label.setFont(QFont("Arial", 11, QFont.Bold))
        title_label.setStyleSheet("color: #E10600;")
        toolbar.addWidget(title_label)

        toolbar.addSeparator()

        # Preset View Selector
        preset_label = QLabel(" Preset View: ")
        preset_label.setStyleSheet("color: #A0A0B0; font-weight: bold;")
        toolbar.addWidget(preset_label)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Full Pit Wall (All Docks)",
            "Quad View (Track, Telemetry, Tyres, Control)",
            "Driver Focus (Telemetry & Track Map)",
            "Strategy & Pace Focus"
        ])
        self.preset_combo.setStyleSheet("background: #222230; color: white; padding: 4px;")
        self.preset_combo.currentTextChanged.connect(self._apply_preset_view)
        toolbar.addWidget(self.preset_combo)

        toolbar.addSeparator()

        # Docks Menu Toggle
        dock_menu_btn = QPushButton(" 👁️ Toggle Panels ")
        dock_menu = QMenu(self)
        dock_menu.setStyleSheet("background: #1C1C28; color: white;")
        for name, dock in self._dock_widgets.items():
            action = dock.toggleViewAction()
            dock_menu.addAction(action)
        dock_menu_btn.setMenu(dock_menu)
        toolbar.addWidget(dock_menu_btn)

        toolbar.addSeparator()

        reset_btn = QPushButton(" 🔄 Reset Layout ")
        reset_btn.clicked.connect(lambda: self._apply_preset_view(self.preset_combo.currentText()))
        toolbar.addWidget(reset_btn)

    def _apply_preset_view(self, preset_name: str):
        """Apply preset docking layouts."""
        for dock in self._dock_widgets.values():
            dock.show()

        if "Quad View" in preset_name:
            self._dock_widgets["lap_time"].hide()
        elif "Driver Focus" in preset_name:
            self._dock_widgets["tyre"].hide()
            self._dock_widgets["race_control"].hide()
            self._dock_widgets["lap_time"].hide()
        elif "Strategy & Pace Focus" in preset_name:
            self._dock_widgets["telemetry"].hide()
            self._dock_widgets["track"].hide()

    def on_telemetry_data(self, data):
        """Broadcast incoming telemetry data packet to all embedded insight modules."""
        for window in self._insight_windows.values():
            if hasattr(window, "on_telemetry_data"):
                try:
                    window.on_telemetry_data(data)
                except Exception as e:
                    print(f"Error updating dock window {window}: {e}")

    def on_connection_status_changed(self, status):
        """Broadcast connection status to all embedded insight modules."""
        for window in self._insight_windows.values():
            if hasattr(window, "on_connection_status_changed"):
                window.on_connection_status_changed(status)

    def on_stream_error(self, error_msg):
        """Broadcast stream errors to all embedded insight modules."""
        for window in self._insight_windows.values():
            if hasattr(window, "on_stream_error"):
                window.on_stream_error(error_msg)


def main():
    app = QApplication(sys.argv)
    window = PitWallDashboardWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
