"""Live tyre strategy window with stint tracking table."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.gui.pit_wall_window import PitWallWindow
from src.lib.tyres import get_tyre_compound_str


class TyreStrategyWindow(PitWallWindow):
    """Display current tyre compound/life and stint status by track position."""

    def setup_ui(self):
        self.setWindowTitle("Tyre Strategy")
        self.setGeometry(140, 140, 760, 520)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.session_label = QLabel("Waiting for session data...")
        self.session_label.setFont(QFont("Arial", 11))
        layout.addWidget(self.session_label)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Pos",
                "Driver",
                "Compound",
                "Tyre Life",
                "Lap",
                "In Pit",
                "Gap Leader (s)",
                "Interval (s)",
                "Speed (km/h)",
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    def on_telemetry_data(self, data):
        frame = data.get("frame", {})
        drivers = frame.get("drivers", {})

        if not drivers:
            return

        session_data = data.get("session_data", {})
        lap = session_data.get("lap", "?")
        total_laps = session_data.get("total_laps", "?")
        race_time = session_data.get("time", "--:--:--")
        self.session_label.setText(f"Lap {lap}/{total_laps}  |  Race Time {race_time}")

        sorted_drivers = sorted(
            drivers.items(),
            key=lambda item: int(item[1].get("position", 99)),
        )

        self.table.setRowCount(len(sorted_drivers))
        for row_idx, (code, payload) in enumerate(sorted_drivers):
            tyre_code = int(payload.get("tyre", -1))
            tyre_compound = get_tyre_compound_str(tyre_code)
            tyre_life = payload.get("tyre_life", 0)
            in_pit = "YES" if payload.get("in_pit", False) else "NO"
            gap_leader = float(payload.get("gap_to_leader_s", 0.0))
            interval_ahead = float(payload.get("interval_ahead_s", 0.0))
            speed = float(payload.get("speed", 0.0))

            values = [
                str(payload.get("position", "-")),
                code,
                tyre_compound,
                str(int(round(float(tyre_life)))),
                str(payload.get("lap", "-")),
                in_pit,
                f"{gap_leader:.3f}",
                f"{interval_ahead:.3f}",
                f"{speed:.1f}",
            ]

            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, col_idx, item)


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = TyreStrategyWindow()
    window.setup_ui()
    
    # Add dummy data for the screenshot
    dummy_data = {
        "session_data": {"lap": 45, "total_laps": 70, "time": "01:15:22"},
        "frame": {
            "drivers": {
                "VER": {"position": 1, "tyre": 3, "tyre_life": 12, "lap": 45, "in_pit": False, "gap_to_leader_s": 0, "interval_ahead_s": 0, "speed": 285.4},
                "HAM": {"position": 2, "tyre": 3, "tyre_life": 15, "lap": 45, "in_pit": False, "gap_to_leader_s": 5.234, "interval_ahead_s": 5.234, "speed": 282.1},
                "NOR": {"position": 3, "tyre": 2, "tyre_life": 8, "lap": 45, "in_pit": False, "gap_to_leader_s": 12.876, "interval_ahead_s": 7.642, "speed": 288.9},
                "LEC": {"position": 4, "tyre": 3, "tyre_life": 22, "lap": 44, "in_pit": True, "gap_to_leader_s": 35.122, "interval_ahead_s": 22.246, "speed": 78.5},
            }
        }
    }
    window.on_telemetry_data(dummy_data)
    
    window.show()
    sys.exit(app.exec())
