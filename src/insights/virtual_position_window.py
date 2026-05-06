import sys
from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.gui.pit_wall_window import PitWallWindow
from src.insights.strategy_utils import (
    build_driver_snapshots,
    find_virtual_rejoin,
    recent_progress_rate,
)


class VirtualPositionWindow(PitWallWindow):
    def __init__(self):
        self._known_drivers = []
        self._history = {}
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Virtual Position")
        self.setMinimumSize(760, 560)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        controls = QGroupBox("Pit Rejoin Estimator")
        controls_layout = QFormLayout(controls)

        self.driver_combo = QComboBox()
        self.driver_combo.setMinimumWidth(120)
        self.pit_loss_spin = QDoubleSpinBox()
        self.pit_loss_spin.setRange(10.0, 40.0)
        self.pit_loss_spin.setDecimals(1)
        self.pit_loss_spin.setSingleStep(0.5)
        self.pit_loss_spin.setValue(22.0)

        self.ref_speed_label = QLabel("Reference speed: -")

        controls_layout.addRow("Driver", self.driver_combo)
        controls_layout.addRow("Pit loss (s)", self.pit_loss_spin)
        controls_layout.addRow("Field reference", self.ref_speed_label)
        root.addWidget(controls)

        summary = QGroupBox("Projection")
        summary_layout = QVBoxLayout(summary)
        self.summary_label = QLabel("Waiting for telemetry...")
        self.summary_label.setWordWrap(True)
        self.summary_label.setFont(QFont("Arial", 11))
        summary_layout.addWidget(self.summary_label)
        root.addWidget(summary)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Proj P", "Driver", "Gap Ahead", "Gap Behind"])
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, stretch=1)

    def on_telemetry_data(self, data):
        frame = data.get("frame")
        if not frame:
            return

        snapshots = build_driver_snapshots(frame)
        if not snapshots:
            return

        session_t = float(frame.get("t", 0.0))
        for snap in snapshots:
            history = self._history.setdefault(snap.code, deque(maxlen=180))
            history.append((session_t, snap.progress_m))

        current_codes = [snap.code for snap in snapshots]
        if current_codes != self._known_drivers:
            current = self.driver_combo.currentText()
            self.driver_combo.blockSignals(True)
            self.driver_combo.clear()
            self.driver_combo.addItems(current_codes)
            if current in current_codes:
                self.driver_combo.setCurrentText(current)
            self.driver_combo.blockSignals(False)
            self._known_drivers = current_codes

        selected = self.driver_combo.currentText() or current_codes[0]
        speeds = []
        for snap in snapshots:
            rate = recent_progress_rate(self._history.get(snap.code, deque()), 15.0)
            if rate:
                speeds.append(rate)
        reference_speed = sum(speeds) / len(speeds) if speeds else 55.0
        self.ref_speed_label.setText(f"Reference speed: {reference_speed * 3.6:.0f} km/h")

        projection = find_virtual_rejoin(
            snapshots,
            selected,
            self.pit_loss_spin.value(),
            reference_speed,
        )
        if not projection:
            return

        ahead_gap = _fmt_gap(projection["ahead_gap_s"])
        behind_gap = _fmt_gap(projection["behind_gap_s"])
        self.summary_label.setText(
            f"{selected} would rejoin P{projection['projected_position']}.\n"
            f"Ahead: {projection['ahead_code'] or '-'} ({ahead_gap})\n"
            f"Behind: {projection['behind_code'] or '-'} ({behind_gap})\n"
            f"Traffic risk: {projection['traffic_risk']}"
        )

        self.table.setRowCount(len(projection["ranking"]))
        rank_map = {code: idx + 1 for idx, (code, _) in enumerate(projection["ranking"])}
        ranking_progress = dict(projection["ranking"])
        for row, snap in enumerate(snapshots):
            proj_pos = rank_map[snap.code]
            proj_progress = ranking_progress[snap.code]
            ahead_code = projection["ranking"][proj_pos - 2][0] if proj_pos > 1 else None
            behind_code = projection["ranking"][proj_pos][0] if proj_pos < len(projection["ranking"]) else None
            ahead_gap = "-"
            behind_gap = "-"
            if ahead_code:
                ahead_gap = _fmt_gap((ranking_progress[ahead_code] - proj_progress) / max(1.0, reference_speed))
            if behind_code:
                behind_gap = _fmt_gap((proj_progress - ranking_progress[behind_code]) / max(1.0, reference_speed))

            items = [
                QTableWidgetItem(str(proj_pos)),
                QTableWidgetItem(snap.code),
                QTableWidgetItem(ahead_gap),
                QTableWidgetItem(behind_gap),
            ]
            if snap.code == selected:
                for item in items:
                    item.setBackground(Qt.darkYellow)
            for col, item in enumerate(items):
                self.table.setItem(row, col, item)


def _fmt_gap(value):
    return "-" if value is None else f"{value:.1f}s"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Virtual Position")
    window = VirtualPositionWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
