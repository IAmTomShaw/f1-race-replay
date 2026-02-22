import sys
from collections import deque

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as ticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox
)
from PySide6.QtGui import QFont
from src.gui.pit_wall_window import PitWallWindow

_TIME_WINDOW = 30        # seconds kept in rolling-time mode

# Colours matching the qualifying viewer
_BG        = "#282828"   # panel background
_SPEED_COL = "#F0F0F0"   # anti-flash white
_GEAR_COL  = "#B0B0B0"   # light gray
_THROT_COL = "#2ECC71"   # green
_BRAKE_COL = "#E74C3C"   # red


class DriverTelemetryWindow(PitWallWindow):
    """
    Pit wall insight that shows live telemetry for a selected driver as
    three stacked line charts: Speed (top 50%), Gear (middle 25%),
    and Throttle / Brake (bottom 25%).
    """

    def __init__(self):
        self._known_drivers = []
        # time mode: deque of {"t", "speed", "gear", "throttle", "brake"}
        self._time_buffers: dict[str, deque] = {}
        # lap mode: {"lap", "start_dist", "samples": list of {"dist", ...}}
        self._lap_buffers: dict[str, dict] = {}
        # length of the most recently completed lap per driver (metres)
        self._lap_lengths: dict[str, float] = {}
        # circuit length from the session (metres), received via stream
        self._circuit_length_m: float | None = None
        self._x_mode = "time"   # "time" | "lap"
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Driver Live Telemetry")

    # ── UI setup ─────────────────────────────────────────────────────────

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setSpacing(6)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # Top control row: driver selector + x-axis mode
        control_row = QHBoxLayout()

        driver_label = QLabel("Driver:")
        driver_label.setFont(QFont("Arial", 11))
        self.driver_combo = QComboBox()
        self.driver_combo.setMinimumWidth(100)
        self.driver_combo.setPlaceholderText("Waiting for data…")
        self.driver_combo.setFont(QFont("Arial", 11))
        self.driver_combo.currentTextChanged.connect(self._on_driver_selected)

        xmode_label = QLabel("X Axis:")
        xmode_label.setFont(QFont("Arial", 11))
        self.xmode_combo = QComboBox()
        self.xmode_combo.setFont(QFont("Arial", 11))
        self.xmode_combo.addItems(["Last 30 seconds", "Current Lap"])
        self.xmode_combo.currentIndexChanged.connect(self._on_xmode_changed)

        control_row.addWidget(driver_label)
        control_row.addWidget(self.driver_combo)
        control_row.addSpacing(20)
        control_row.addWidget(xmode_label)
        control_row.addWidget(self.xmode_combo)
        control_row.addStretch()
        root_layout.addLayout(control_row)

        # Matplotlib figure – three stacked panels, same proportions as qualifying viewer
        self._fig = plt.figure(figsize=(10, 6), facecolor=_BG)
        gs = gridspec.GridSpec(
            3, 1,
            figure=self._fig,
            height_ratios=[2, 1, 1],
            hspace=0.08,
        )

        # Speed panel
        self._ax_speed = self._fig.add_subplot(gs[0])
        self._line_speed, = self._ax_speed.plot([], [], color=_SPEED_COL, linewidth=1.5)
        self._ax_speed.set_facecolor(_BG)
        self._ax_speed.set_ylabel("Speed (km/h)", color=_SPEED_COL, fontsize=10)
        self._ax_speed.set_ylim(0, 380)
        self._ax_speed.tick_params(colors=_SPEED_COL, labelbottom=False)
        for spine in self._ax_speed.spines.values():
            spine.set_edgecolor("#555555")

        # Gear panel
        self._ax_gear = self._fig.add_subplot(gs[1])
        self._line_gear, = self._ax_gear.plot([], [], color=_GEAR_COL, linewidth=1.5, drawstyle="steps-post")
        self._ax_gear.set_facecolor(_BG)
        self._ax_gear.set_ylabel("Gear", color=_GEAR_COL, fontsize=10)
        self._ax_gear.set_ylim(0, 9)
        self._ax_gear.set_yticks(range(1, 9))
        self._ax_gear.tick_params(colors=_GEAR_COL, labelbottom=False)
        for spine in self._ax_gear.spines.values():
            spine.set_edgecolor("#555555")

        # Throttle / Brake panel
        self._ax_ctrl = self._fig.add_subplot(gs[2])
        self._line_throt, = self._ax_ctrl.plot([], [], color=_THROT_COL, linewidth=1.5)
        self._line_brake, = self._ax_ctrl.plot([], [], color=_BRAKE_COL, linewidth=1.5)
        self._ax_ctrl.set_facecolor(_BG)
        self._ax_ctrl.set_ylabel("Throttle / Brake (%)", color=_SPEED_COL, fontsize=10)
        self._ax_ctrl.set_ylim(-5, 105)
        self._ax_ctrl.tick_params(colors=_SPEED_COL)
        for spine in self._ax_ctrl.spines.values():
            spine.set_edgecolor("#555555")

        # x-axis label lives on the bottom panel only
        self._ax_ctrl.set_xlabel("Time (s)", color=_SPEED_COL, fontsize=9)

        self._canvas = FigureCanvas(self._fig)
        root_layout.addWidget(self._canvas)

        self._apply_xmode_labels()

    # ── X-axis mode helpers ───────────────────────────────────────────────

    def _on_xmode_changed(self, index: int):
        self._x_mode = "time" if index == 0 else "lap"
        self._apply_xmode_labels()
        self._redraw(self.driver_combo.currentText())

    def _apply_xmode_labels(self):
        if self._x_mode == "time":
            self._ax_ctrl.set_xlabel("Time (s)", color=_SPEED_COL, fontsize=9)
            self._ax_ctrl.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f"))
        else:
            self._ax_ctrl.set_xlabel("Distance (m)", color=_SPEED_COL, fontsize=9)
            self._ax_ctrl.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f"))

    # ── Buffer management ─────────────────────────────────────────────────

    def _ensure_buffers(self, code: str):
        if code not in self._time_buffers:
            self._time_buffers[code] = deque()
        if code not in self._lap_buffers:
            self._lap_buffers[code] = {"lap": None, "start_dist": 0.0, "samples": []}

    def _append_sample(self, code: str, driver: dict, session_t: float):
        self._ensure_buffers(code)

        speed    = float(driver.get("speed")    or 0)
        gear     = int(driver.get("gear")       or 0)
        throttle = float(driver.get("throttle") or 0)
        brake    = float(driver.get("brake")    or 0) * 100 # Convert to percentage as brake is 0-1 in the stream but we want 0-100 on the chart
        dist     = float(driver.get("dist")     or 0)
        lap      = driver.get("lap")

        # ── time buffer: prune samples older than _TIME_WINDOW ──
        tb = self._time_buffers[code]
        tb.append({"t": session_t, "speed": speed, "gear": gear,
                   "throttle": throttle, "brake": brake})
        cutoff = session_t - _TIME_WINDOW
        while tb and tb[0]["t"] < cutoff:
            tb.popleft()

        # ── lap buffer: reset on new lap ──
        lb = self._lap_buffers[code]
        if lap is not None and lap != lb["lap"]:
            # Record the completed lap's total distance before resetting
            if lb["samples"]:
                self._lap_lengths[code] = lb["samples"][-1]["dist"]
            lb["lap"] = lap
            lb["start_dist"] = dist
            lb["samples"] = []
        lap_dist = dist - lb["start_dist"]
        lb["samples"].append({"dist": lap_dist, "speed": speed, "gear": gear,
                               "throttle": throttle, "brake": brake})

    # ── Driver selector ───────────────────────────────────────────────────

    def _on_driver_selected(self, driver_code: str):
        self._redraw(driver_code)

    def _refresh_driver_list(self, drivers: dict):
        incoming = sorted(drivers.keys())
        if incoming == self._known_drivers:
            return
        current = self.driver_combo.currentText()
        self.driver_combo.blockSignals(True)
        self.driver_combo.clear()
        self.driver_combo.addItems(incoming)
        if current in incoming:
            self.driver_combo.setCurrentText(current)
        elif incoming:
            self.driver_combo.setCurrentIndex(0)
        self.driver_combo.blockSignals(False)
        self._known_drivers = incoming

    # ── Chart redraw ──────────────────────────────────────────────────────

    def _redraw(self, driver_code: str):
        if not driver_code:
            self._clear_lines()
            return

        if self._x_mode == "time":
            self._redraw_time(driver_code)
        else:
            self._redraw_lap(driver_code)

        self._canvas.draw_idle()

    def _redraw_time(self, code: str):
        tb = self._time_buffers.get(code)
        if not tb:
            self._clear_lines()
            return

        samples = list(tb)
        t_now = samples[-1]["t"]
        xs        = [s["t"] - t_now for s in samples]   # 0 = now, -30 = 30s ago
        speeds    = [s["speed"]    for s in samples]
        gears     = [s["gear"]     for s in samples]
        throttles = [s["throttle"] for s in samples]
        brakes    = [s["brake"]    for s in samples]

        self._set_lines(xs, speeds, gears, throttles, brakes)

        x_min = -_TIME_WINDOW
        x_max = 0
        for ax in (self._ax_speed, self._ax_gear, self._ax_ctrl):
            ax.set_xlim(x_min, x_max)

    def _redraw_lap(self, code: str):
        lb = self._lap_buffers.get(code)
        if not lb or not lb["samples"]:
            self._clear_lines()
            return

        samples   = lb["samples"]
        xs        = [s["dist"]     for s in samples]
        speeds    = [s["speed"]    for s in samples]
        gears     = [s["gear"]     for s in samples]
        throttles = [s["throttle"] for s in samples]
        brakes    = [s["brake"]    for s in samples]

        self._set_lines(xs, speeds, gears, throttles, brakes)

        # X-axis: prefer the authoritative circuit length from the session.
        # Fall back to the most recently completed lap's distance, then the
        # current max distance (grows during the very first lap only).
        lap_length = (
            self._circuit_length_m
            or self._lap_lengths.get(code)
            or max(xs)
        )
        for ax in (self._ax_speed, self._ax_gear, self._ax_ctrl):
            ax.set_xlim(0, lap_length)

    def _set_lines(self, xs, speeds, gears, throttles, brakes):
        self._line_speed.set_data(xs, speeds)
        self._line_gear.set_data(xs, gears)
        self._line_throt.set_data(xs, throttles)
        self._line_brake.set_data(xs, brakes)

    def _clear_lines(self):
        for line in (self._line_speed, self._line_gear, self._line_throt, self._line_brake):
            line.set_data([], [])
        self._canvas.draw_idle()

    # ── PitWallWindow overrides ───────────────────────────────────────────

    def on_telemetry_data(self, data):
        if "frame" not in data or not data["frame"]:
            return
        drivers = data["frame"].get("drivers", {})
        if not drivers:
            return

        # Capture circuit length the first time it arrives
        if self._circuit_length_m is None and data.get("circuit_length_m"):
            self._circuit_length_m = float(data["circuit_length_m"])

        session_t = float(data["frame"].get("t") or 0)

        self._refresh_driver_list(drivers)

        for code, driver in drivers.items():
            self._append_sample(code, driver, session_t)

        selected = self.driver_combo.currentText()
        if selected:
            self._redraw(selected)

    def on_connection_status_changed(self, status):
        if status != "Connected":
            self._clear_lines()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Driver Live Telemetry")
    window = DriverTelemetryWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
