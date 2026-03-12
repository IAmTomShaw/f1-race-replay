import sys
from collections import deque

import matplotlib

matplotlib.use("QtAgg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.gui.pit_wall_window import PitWallWindow

_TIME_WINDOW = 30  # seconds kept in rolling-time mode

_BG = "#282828"
_SPEED_COL = "#F0F0F0"
_GEAR_COL = "#B0B0B0"
_THROT_COL = "#2ECC71"
_BRAKE_COL = "#E74C3C"

_SPEED_COL_COMPARE = "#7EC8E3"
_GEAR_COL_COMPARE = "#D7C9FF"
_THROT_COL_COMPARE = "#8EF0B2"
_BRAKE_COL_COMPARE = "#F7A4A4"

_NO_COMPARE = "(None)"


class DriverTelemetryWindow(PitWallWindow):
    """
    Pit wall insight that shows live telemetry for one or two selected drivers.
    The second selected driver is overlaid on top of the first with dashed lines.
    """

    def __init__(self):
        self._known_drivers = []
        self._time_buffers: dict[str, deque] = {}
        self._lap_buffers: dict[str, dict] = {}
        self._lap_lengths: dict[str, float] = {}
        self._circuit_length_m: float | None = None
        self._corner_markers: list[dict] = []
        self._corner_artists: list = []
        self._x_mode = "time"  # "time" | "lap"
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Driver Live Telemetry")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setSpacing(6)
        root_layout.setContentsMargins(10, 10, 10, 10)

        control_row = QHBoxLayout()

        driver_label = QLabel("Driver:")
        driver_label.setFont(QFont("Arial", 11))
        self.driver_combo = QComboBox()
        self.driver_combo.setMinimumWidth(100)
        self.driver_combo.setPlaceholderText("Waiting for data...")
        self.driver_combo.setFont(QFont("Arial", 11))
        self.driver_combo.currentTextChanged.connect(self._on_selection_changed)

        compare_label = QLabel("Compare:")
        compare_label.setFont(QFont("Arial", 11))
        self.compare_driver_combo = QComboBox()
        self.compare_driver_combo.setMinimumWidth(100)
        self.compare_driver_combo.setFont(QFont("Arial", 11))
        self.compare_driver_combo.addItem(_NO_COMPARE)
        self.compare_driver_combo.currentTextChanged.connect(self._on_selection_changed)

        xmode_label = QLabel("X Axis:")
        xmode_label.setFont(QFont("Arial", 11))
        self.xmode_combo = QComboBox()
        self.xmode_combo.setFont(QFont("Arial", 11))
        self.xmode_combo.addItems(["Last 30 seconds", "Current Lap"])
        self.xmode_combo.currentIndexChanged.connect(self._on_xmode_changed)

        control_row.addWidget(driver_label)
        control_row.addWidget(self.driver_combo)
        control_row.addSpacing(14)
        control_row.addWidget(compare_label)
        control_row.addWidget(self.compare_driver_combo)
        control_row.addSpacing(14)
        control_row.addWidget(xmode_label)
        control_row.addWidget(self.xmode_combo)
        control_row.addStretch()
        root_layout.addLayout(control_row)

        self._fig = plt.figure(figsize=(10, 6), facecolor=_BG)
        gs = gridspec.GridSpec(3, 1, figure=self._fig, height_ratios=[2, 1, 1], hspace=0.08)

        self._ax_speed = self._fig.add_subplot(gs[0])
        self._line_speed, = self._ax_speed.plot([], [], color=_SPEED_COL, linewidth=1.8)
        self._line_speed_compare, = self._ax_speed.plot(
            [], [], color=_SPEED_COL_COMPARE, linewidth=1.6, linestyle="--"
        )
        self._ax_speed.set_facecolor(_BG)
        self._ax_speed.set_ylabel("Speed (km/h)", color=_SPEED_COL, fontsize=10)
        self._ax_speed.set_ylim(0, 380)
        self._ax_speed.tick_params(colors=_SPEED_COL, labelbottom=False)
        for spine in self._ax_speed.spines.values():
            spine.set_edgecolor("#555555")

        self._ax_gear = self._fig.add_subplot(gs[1])
        self._line_gear, = self._ax_gear.plot(
            [], [], color=_GEAR_COL, linewidth=1.8, drawstyle="steps-post"
        )
        self._line_gear_compare, = self._ax_gear.plot(
            [], [], color=_GEAR_COL_COMPARE, linewidth=1.6, linestyle="--", drawstyle="steps-post"
        )
        self._ax_gear.set_facecolor(_BG)
        self._ax_gear.set_ylabel("Gear", color=_GEAR_COL, fontsize=10)
        self._ax_gear.set_ylim(0, 9)
        self._ax_gear.set_yticks(range(1, 9))
        self._ax_gear.tick_params(colors=_GEAR_COL, labelbottom=False)
        for spine in self._ax_gear.spines.values():
            spine.set_edgecolor("#555555")

        self._ax_ctrl = self._fig.add_subplot(gs[2])
        self._line_throt, = self._ax_ctrl.plot([], [], color=_THROT_COL, linewidth=1.8)
        self._line_brake, = self._ax_ctrl.plot([], [], color=_BRAKE_COL, linewidth=1.8)
        self._line_throt_compare, = self._ax_ctrl.plot(
            [], [], color=_THROT_COL_COMPARE, linewidth=1.6, linestyle="--"
        )
        self._line_brake_compare, = self._ax_ctrl.plot(
            [], [], color=_BRAKE_COL_COMPARE, linewidth=1.6, linestyle="--"
        )
        self._ax_ctrl.set_facecolor(_BG)
        self._ax_ctrl.set_ylabel("Throttle / Brake (%)", color=_SPEED_COL, fontsize=10)
        self._ax_ctrl.set_ylim(-5, 105)
        self._ax_ctrl.tick_params(colors=_SPEED_COL)
        for spine in self._ax_ctrl.spines.values():
            spine.set_edgecolor("#555555")

        self._ax_ctrl.set_xlabel("Time (s)", color=_SPEED_COL, fontsize=9)

        self._canvas = FigureCanvas(self._fig)
        root_layout.addWidget(self._canvas)

        self._apply_xmode_labels()
        self._update_title("", "")

    def _on_selection_changed(self, _: str):
        self._redraw()

    def _on_xmode_changed(self, index: int):
        self._x_mode = "time" if index == 0 else "lap"
        self._apply_xmode_labels()
        self._redraw()

    def _apply_xmode_labels(self):
        if self._x_mode == "time":
            self._ax_ctrl.set_xlabel("Time (s)", color=_SPEED_COL, fontsize=9)
            self._ax_ctrl.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f"))
        else:
            self._ax_ctrl.set_xlabel("Distance (m)", color=_SPEED_COL, fontsize=9)
            self._ax_ctrl.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f"))

    def _update_title(self, primary_code: str, compare_code: str):
        if primary_code and compare_code:
            title = f"{primary_code} vs {compare_code}"
        elif primary_code:
            title = primary_code
        else:
            title = "Waiting for telemetry..."
        self._ax_speed.set_title(title, color=_SPEED_COL, fontsize=11)

    def _ensure_buffers(self, code: str):
        if code not in self._time_buffers:
            self._time_buffers[code] = deque()
        if code not in self._lap_buffers:
            self._lap_buffers[code] = {"lap": None, "start_dist": 0.0, "samples": []}

    def _append_sample(self, code: str, driver: dict, session_t: float):
        self._ensure_buffers(code)

        speed = float(driver.get("speed") or 0)
        gear = int(driver.get("gear") or 0)
        throttle = float(driver.get("throttle") or 0)
        brake = float(driver.get("brake") or 0) * 100
        dist = float(driver.get("dist") or 0)
        lap = driver.get("lap")

        tb = self._time_buffers[code]
        tb.append(
            {
                "t": session_t,
                "speed": speed,
                "gear": gear,
                "throttle": throttle,
                "brake": brake,
            }
        )
        cutoff = session_t - _TIME_WINDOW
        while tb and tb[0]["t"] < cutoff:
            tb.popleft()

        lb = self._lap_buffers[code]
        if lap is not None and lap != lb["lap"]:
            if lb["samples"]:
                self._lap_lengths[code] = lb["samples"][-1]["dist"]
            lb["lap"] = lap
            lb["start_dist"] = dist
            lb["samples"] = []

        lap_dist = dist - lb["start_dist"]
        lb["samples"].append(
            {
                "dist": lap_dist,
                "speed": speed,
                "gear": gear,
                "throttle": throttle,
                "brake": brake,
            }
        )

    def _refresh_driver_list(self, drivers: dict):
        incoming = sorted(drivers.keys())
        if incoming == self._known_drivers:
            return

        current_primary = self.driver_combo.currentText()
        current_compare = self.compare_driver_combo.currentText()

        self.driver_combo.blockSignals(True)
        self.compare_driver_combo.blockSignals(True)

        self.driver_combo.clear()
        self.driver_combo.addItems(incoming)

        self.compare_driver_combo.clear()
        self.compare_driver_combo.addItem(_NO_COMPARE)
        self.compare_driver_combo.addItems(incoming)

        if current_primary in incoming:
            self.driver_combo.setCurrentText(current_primary)
        elif incoming:
            self.driver_combo.setCurrentIndex(0)

        if current_compare in incoming:
            self.compare_driver_combo.setCurrentText(current_compare)
        else:
            self.compare_driver_combo.setCurrentText(_NO_COMPARE)

        self.driver_combo.blockSignals(False)
        self.compare_driver_combo.blockSignals(False)
        self._known_drivers = incoming

    def _selected_codes(self) -> tuple[str, str]:
        primary = self.driver_combo.currentText().strip()
        compare = self.compare_driver_combo.currentText().strip()
        if compare == _NO_COMPARE or compare == primary:
            compare = ""
        return primary, compare

    def _extract_time_series(self, code: str):
        tb = self._time_buffers.get(code)
        if not tb:
            return None
        samples = list(tb)
        t_now = samples[-1]["t"]
        xs = [s["t"] - t_now for s in samples]
        speeds = [s["speed"] for s in samples]
        gears = [s["gear"] for s in samples]
        throttles = [s["throttle"] for s in samples]
        brakes = [s["brake"] for s in samples]
        return xs, speeds, gears, throttles, brakes

    def _extract_lap_series(self, code: str):
        lb = self._lap_buffers.get(code)
        if not lb or not lb["samples"]:
            return None

        samples = lb["samples"]
        xs = [s["dist"] for s in samples]
        speeds = [s["speed"] for s in samples]
        gears = [s["gear"] for s in samples]
        throttles = [s["throttle"] for s in samples]
        brakes = [s["brake"] for s in samples]

        lap_length = self._circuit_length_m or self._lap_lengths.get(code) or max(xs)
        return xs, speeds, gears, throttles, brakes, lap_length

    def _set_primary_lines(self, xs, speeds, gears, throttles, brakes):
        self._line_speed.set_data(xs, speeds)
        self._line_gear.set_data(xs, gears)
        self._line_throt.set_data(xs, throttles)
        self._line_brake.set_data(xs, brakes)

    def _set_compare_lines(self, xs, speeds, gears, throttles, brakes):
        self._line_speed_compare.set_data(xs, speeds)
        self._line_gear_compare.set_data(xs, gears)
        self._line_throt_compare.set_data(xs, throttles)
        self._line_brake_compare.set_data(xs, brakes)

    def _clear_primary_lines(self):
        self._line_speed.set_data([], [])
        self._line_gear.set_data([], [])
        self._line_throt.set_data([], [])
        self._line_brake.set_data([], [])

    def _clear_compare_lines(self):
        self._line_speed_compare.set_data([], [])
        self._line_gear_compare.set_data([], [])
        self._line_throt_compare.set_data([], [])
        self._line_brake_compare.set_data([], [])

    def _clear_corner_overlays(self):
        for artist in self._corner_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self._corner_artists = []

    def _update_corner_markers_from_stream(self, raw_markers):
        if not isinstance(raw_markers, list) or not raw_markers:
            return

        parsed = []
        seen = set()
        for marker in raw_markers:
            if not isinstance(marker, dict):
                continue

            label = str(
                marker.get("label")
                or marker.get("number")
                or marker.get("corner")
                or ""
            ).strip()
            if not label or label in seen:
                continue

            distance_m = marker.get("distance_m")
            if distance_m is None:
                distance_m = marker.get("distance")

            if distance_m is None and self._circuit_length_m:
                rel_dist = marker.get("rel_dist")
                if rel_dist is not None:
                    distance_m = float(rel_dist) * float(self._circuit_length_m)

            if distance_m is None:
                continue

            try:
                distance_m = float(distance_m)
            except Exception:
                continue
            if distance_m < 0:
                continue

            parsed.append({"label": label, "distance_m": distance_m})
            seen.add(label)

        if parsed:
            self._corner_markers = sorted(parsed, key=lambda m: m["distance_m"])

    def _draw_corner_overlays_lap(self, x_max: float):
        self._clear_corner_overlays()
        if self._x_mode != "lap" or not self._corner_markers:
            return

        trans = self._ax_speed.get_xaxis_transform()
        for marker in self._corner_markers:
            x_val = marker["distance_m"]
            if x_val > x_max:
                continue
            line = self._ax_speed.axvline(
                x=x_val,
                color="#E8E8E8",
                alpha=0.22,
                linewidth=1.0,
                zorder=1,
            )
            text = self._ax_speed.text(
                x_val,
                0.98,
                marker["label"],
                transform=trans,
                color="#E8E8E8",
                alpha=0.60,
                fontsize=8,
                ha="center",
                va="top",
                clip_on=True,
                zorder=3,
            )
            self._corner_artists.extend([line, text])

    def _clear_lines(self):
        self._clear_primary_lines()
        self._clear_compare_lines()
        self._clear_corner_overlays()
        self._update_title("", "")
        self._canvas.draw_idle()

    def _redraw(self):
        primary_code, compare_code = self._selected_codes()
        if not primary_code:
            self._clear_lines()
            return

        shown_primary = ""
        shown_compare = ""

        if self._x_mode == "time":
            primary = self._extract_time_series(primary_code)
            compare = self._extract_time_series(compare_code) if compare_code else None

            if primary:
                self._set_primary_lines(*primary)
                shown_primary = primary_code
            else:
                self._clear_primary_lines()

            if compare:
                self._set_compare_lines(*compare)
                shown_compare = compare_code
            else:
                self._clear_compare_lines()

            for ax in (self._ax_speed, self._ax_gear, self._ax_ctrl):
                ax.set_xlim(-_TIME_WINDOW, 0)
            self._clear_corner_overlays()
        else:
            primary = self._extract_lap_series(primary_code)
            compare = self._extract_lap_series(compare_code) if compare_code else None

            x_max = 1.0
            if self._circuit_length_m:
                x_max = max(x_max, float(self._circuit_length_m))

            if primary:
                p_xs, p_speeds, p_gears, p_throttles, p_brakes, p_len = primary
                self._set_primary_lines(p_xs, p_speeds, p_gears, p_throttles, p_brakes)
                x_max = max(x_max, float(p_len))
                shown_primary = primary_code
            else:
                self._clear_primary_lines()

            if compare:
                c_xs, c_speeds, c_gears, c_throttles, c_brakes, c_len = compare
                self._set_compare_lines(c_xs, c_speeds, c_gears, c_throttles, c_brakes)
                x_max = max(x_max, float(c_len))
                shown_compare = compare_code
            else:
                self._clear_compare_lines()

            for ax in (self._ax_speed, self._ax_gear, self._ax_ctrl):
                ax.set_xlim(0, x_max)
            self._draw_corner_overlays_lap(x_max)

        self._update_title(shown_primary, shown_compare)
        self._canvas.draw_idle()

    def on_telemetry_data(self, data):
        if "frame" not in data or not data["frame"]:
            return

        drivers = data["frame"].get("drivers", {})
        if not drivers:
            return

        if self._circuit_length_m is None and data.get("circuit_length_m"):
            self._circuit_length_m = float(data["circuit_length_m"])
        self._update_corner_markers_from_stream(data.get("corner_markers"))

        session_t = float(data["frame"].get("t") or 0)

        self._refresh_driver_list(drivers)
        for code, driver in drivers.items():
            self._append_sample(code, driver, session_t)

        self._redraw()

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
