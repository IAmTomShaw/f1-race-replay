import sys
from collections import deque

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.gui.pit_wall_window import PitWallWindow
from src.insights.strategy_utils import (
    build_driver_snapshots,
    detect_drs_trains,
    drs_state,
    estimate_gap_seconds,
)


class DrsTrafficWindow(PitWallWindow):
    def __init__(self):
        self._known_drivers = []
        super().__init__()
        self.setWindowTitle("F1 Race Replay - DRS Train / Traffic")
        self.setMinimumSize(780, 620)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        controls = QGroupBox("Traffic Detector")
        form = QFormLayout(controls)
        self.driver_combo = QComboBox()
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.5, 3.0)
        self.threshold_spin.setDecimals(1)
        self.threshold_spin.setSingleStep(0.1)
        self.threshold_spin.setValue(1.2)
        form.addRow("Focus driver", self.driver_combo)
        form.addRow("Train threshold (s)", self.threshold_spin)
        root.addWidget(controls)

        self.summary = QLabel("Waiting for telemetry...")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Lead", "Cars", "Train", "Avg Gap", "DRS Followers"])
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, stretch=1)

    def on_telemetry_data(self, data):
        frame = data.get("frame")
        if not frame:
            return

        snapshots = build_driver_snapshots(frame)
        if not snapshots:
            return

        codes = [snap.code for snap in snapshots]
        if codes != self._known_drivers:
            current = self.driver_combo.currentText()
            self.driver_combo.blockSignals(True)
            self.driver_combo.clear()
            self.driver_combo.addItems(codes)
            if current in codes:
                self.driver_combo.setCurrentText(current)
            self.driver_combo.blockSignals(False)
            self._known_drivers = codes

        trains = detect_drs_trains(snapshots, self.threshold_spin.value())
        self.table.setRowCount(len(trains))
        for row, train in enumerate(trains):
            values = [
                train["lead"],
                str(train["length"]),
                " -> ".join(train["cars"]),
                f"{train['avg_gap_s']:.2f}s",
                str(train["active_drs_followers"]),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

        focus = self.driver_combo.currentText() or codes[0]
        focus_snap = next((snap for snap in snapshots if snap.code == focus), None)
        focus_text = f"{focus}: no live data"
        if focus_snap:
            idx = snapshots.index(focus_snap)
            ahead_gap = None
            behind_gap = None
            if idx > 0:
                ahead_gap = estimate_gap_seconds(snapshots[idx - 1], focus_snap)
            if idx < len(snapshots) - 1:
                behind_gap = estimate_gap_seconds(focus_snap, snapshots[idx + 1])

            in_train = next((train for train in trains if focus in train["cars"]), None)
            if in_train:
                focus_text = (
                    f"{focus} is in a {in_train['length']}-car train led by {in_train['lead']} "
                    f"with avg gap {in_train['avg_gap_s']:.2f}s. "
                    f"DRS state: {drs_state(focus_snap.drs)}. "
                    f"Gaps: ahead {_fmt_gap(ahead_gap)}, behind {_fmt_gap(behind_gap)}."
                )
            else:
                traffic_tag = "traffic" if (ahead_gap is not None and ahead_gap < 2.0) or (behind_gap is not None and behind_gap < 2.0) else "clear air"
                focus_text = (
                    f"{focus} is not currently in a detected DRS train. "
                    f"DRS state: {drs_state(focus_snap.drs)}. "
                    f"Gaps: ahead {_fmt_gap(ahead_gap)}, behind {_fmt_gap(behind_gap)}. "
                    f"Local picture: {traffic_tag}."
                )

        self.summary.setText(
            f"Detected trains: {len(trains)}\n{focus_text}"
        )


def _fmt_gap(value):
    return "-" if value is None else f"{value:.1f}s"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DRS Train / Traffic")
    window = DrsTrafficWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
