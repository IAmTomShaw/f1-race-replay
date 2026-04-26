import sys
from collections import deque

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.gui.pit_wall_window import PitWallWindow
from src.insights.strategy_utils import (
    build_driver_snapshots,
    classify_strategy_signal,
    equivalent_lap_time,
    estimate_gap_seconds,
    find_virtual_rejoin,
    recent_progress_rate,
)


class UndercutOvercutWindow(PitWallWindow):
    def __init__(self):
        self._known_drivers = []
        self._history = {}
        self._circuit_length_m = None
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Undercut / Overcut")
        self.setMinimumSize(760, 620)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        controls = QGroupBox("Comparison")
        form = QFormLayout(controls)
        self.attacker_combo = QComboBox()
        self.defender_combo = QComboBox()
        self.pit_loss_spin = QDoubleSpinBox()
        self.pit_loss_spin.setRange(10.0, 40.0)
        self.pit_loss_spin.setDecimals(1)
        self.pit_loss_spin.setSingleStep(0.5)
        self.pit_loss_spin.setValue(22.0)
        form.addRow("Car A", self.attacker_combo)
        form.addRow("Car B", self.defender_combo)
        form.addRow("Pit loss (s)", self.pit_loss_spin)
        root.addWidget(controls)

        self.headline = QLabel("Waiting for telemetry...")
        self.headline.setFont(QFont("Arial", 12, QFont.Bold))
        self.headline.setWordWrap(True)
        root.addWidget(self.headline)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFont(QFont("Courier", 10))
        root.addWidget(self.detail_text, stretch=1)

    def on_telemetry_data(self, data):
        frame = data.get("frame")
        if not frame:
            return

        if data.get("circuit_length_m"):
            self._circuit_length_m = float(data["circuit_length_m"])

        snapshots = build_driver_snapshots(frame)
        if not snapshots:
            return

        session_t = float(frame.get("t", 0.0))
        for snap in snapshots:
            history = self._history.setdefault(snap.code, deque(maxlen=180))
            history.append((session_t, snap.progress_m))

        codes = [snap.code for snap in snapshots]
        if codes != self._known_drivers:
            attacker = self.attacker_combo.currentText()
            defender = self.defender_combo.currentText()
            for combo, current in ((self.attacker_combo, attacker), (self.defender_combo, defender)):
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(codes)
                if current in codes:
                    combo.setCurrentText(current)
                combo.blockSignals(False)
            if len(codes) > 1 and not self.defender_combo.currentText():
                self.defender_combo.setCurrentIndex(1)
            self._known_drivers = codes

        code_a = self.attacker_combo.currentText() or codes[0]
        code_b = self.defender_combo.currentText() or (codes[1] if len(codes) > 1 else codes[0])
        if code_a == code_b:
            self.headline.setText("Select two different drivers to compare.")
            return

        snap_a = next((snap for snap in snapshots if snap.code == code_a), None)
        snap_b = next((snap for snap in snapshots if snap.code == code_b), None)
        if not snap_a or not snap_b:
            return

        if snap_a.progress_m >= snap_b.progress_m:
            front, back = snap_a, snap_b
        else:
            front, back = snap_b, snap_a

        gap_s = estimate_gap_seconds(front, back)
        rate_a = recent_progress_rate(self._history.get(code_a, deque()), 20.0)
        rate_b = recent_progress_rate(self._history.get(code_b, deque()), 20.0)
        lap_time_a = equivalent_lap_time(rate_a, self._circuit_length_m)
        lap_time_b = equivalent_lap_time(rate_b, self._circuit_length_m)
        pace_delta = None
        if lap_time_a is not None and lap_time_b is not None:
            pace_delta = lap_time_a - lap_time_b

        # Positive tyre_life_delta means back car is on older tyres than front car.
        tyre_life_delta = back.tyre_life - front.tyre_life

        field_rates = [rate for rate in (recent_progress_rate(self._history.get(s.code, deque()), 15.0) for s in snapshots) if rate]
        reference_speed = sum(field_rates) / len(field_rates) if field_rates else 55.0
        projection = find_virtual_rejoin(
            snapshots,
            back.code,
            self.pit_loss_spin.value(),
            reference_speed,
        )
        traffic_risk = projection["traffic_risk"] if projection else "Unknown"

        back_pace_delta = None
        if pace_delta is not None:
            if back.code == code_a:
                back_pace_delta = pace_delta
            else:
                back_pace_delta = -pace_delta

        signal, rationale = classify_strategy_signal(
            gap_s=gap_s,
            pace_delta_s_per_lap=back_pace_delta,
            tyre_life_delta=tyre_life_delta,
            traffic_risk=traffic_risk,
        )

        self.headline.setText(
            f"Front: {front.code}  |  Chasing: {back.code}  |  Call: {signal}"
        )

        details = [
            f"Current gap: {gap_s:.2f}s",
            f"{code_a} current pos: P{snap_a.position}  tyre age: {snap_a.tyre_life:.0f}  speed: {snap_a.speed_kph:.0f} km/h",
            f"{code_b} current pos: P{snap_b.position}  tyre age: {snap_b.tyre_life:.0f}  speed: {snap_b.speed_kph:.0f} km/h",
            "",
            f"Recent pace delta ({code_a} - {code_b}): {_fmt_optional_delta(pace_delta)} per lap",
            f"Tyre age delta (chasing - front): {tyre_life_delta:+.0f} laps",
            f"Projected rejoin for {back.code} if pitting now: "
            f"P{projection['projected_position']}  |  traffic: {traffic_risk}" if projection else
            "Projected rejoin: unavailable",
            "",
            f"Reading: {rationale}",
        ]

        if projection:
            details.extend(
                [
                    f"Ahead at rejoin: {projection['ahead_code'] or '-'} ({_fmt_gap(projection['ahead_gap_s'])})",
                    f"Behind at rejoin: {projection['behind_code'] or '-'} ({_fmt_gap(projection['behind_gap_s'])})",
                ]
            )

        self.detail_text.setText("\n".join(details))


def _fmt_optional_delta(value):
    return "n/a" if value is None else f"{value:+.2f}s"


def _fmt_gap(value):
    return "-" if value is None else f"{value:.1f}s"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Undercut / Overcut")
    window = UndercutOvercutWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
