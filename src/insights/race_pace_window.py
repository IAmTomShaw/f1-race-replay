import time

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QFrame, QSizePolicy,
)

from src.gui.pit_wall_window import PitWallWindow

# ── Theme ──────────────────────────────────────────────────────────────────────
BG      = "#0f0f1a"
SURFACE = "#1e1e2e"
ACCENT  = "#e8002d"
TEXT    = "#e0e0e0"
DIM     = "#888899"
BORDER  = "#2a2a3e"

# Team colours — fallback palette cycles through these when team is unknown
_TEAM_COLOURS = {
    "Ferrari":       "#e8002d",
    "McLaren":       "#ff8000",
    "Mercedes":      "#27f4d2",
    "Red Bull":      "#3671c6",
    "Williams":      "#64c4ff",
    "Aston Martin":  "#358c75",
    "Alpine":        "#0093cc",
    "Haas":          "#b6babd",
    "Racing Bulls":  "#6692ff",
    "Audi":          "#c8f500",
    "Cadillac":      "#ffffff",
}

_FALLBACK_PALETTE = [
    "#e8002d", "#ff8000", "#27f4d2", "#3671c6", "#64c4ff",
    "#358c75", "#0093cc", "#b6babd", "#6692ff", "#c8f500",
    "#ffffff", "#ffcc00",
]


def _driver_colour(driver_code: str, team: str | None, colour_index: int) -> str:
    if team and team in _TEAM_COLOURS:
        return _TEAM_COLOURS[team]
    return _FALLBACK_PALETTE[colour_index % len(_FALLBACK_PALETTE)]


# pyqtgraph dark theme
pg.setConfigOption("background", BG)
pg.setConfigOption("foreground", TEXT)


class RacePaceWindow(PitWallWindow):
    """Live-updating lap time progression chart, one line per driver."""

    def __init__(self):
        # State initialised before super().__init__() calls setup_ui()
        self._lap_times: dict[str, list[float]] = {}       # driver -> [lap_time_s, ...]
        self._prev_rel_dist: dict[str, float] = {}         # driver -> last rel_dist
        self._prev_frame_time: dict[str, float] = {}       # driver -> wall time at lap start
        self._prev_lap: dict[str, int] = {}                # driver -> last known lap number
        self._driver_teams: dict[str, str] = {}            # driver -> team name
        self._colour_index: dict[str, int] = {}            # driver -> palette index counter

        self._active_drivers: set[str] = set()             # checked in sidebar
        self._session_fastest: float | None = None
        self._fastest_line: pg.InfiniteLine | None = None

        self._last_chart_update: float = 0.0
        self._chart_interval: float = 5.0                  # seconds between redraws

        super().__init__()
        self.setWindowTitle("Race Pace Chart")
        self.setGeometry(100, 100, 900, 600)

        # Redraw timer — checks every second, only redraws if 5 s have elapsed
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._maybe_refresh_chart)
        self._timer.start()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def setup_ui(self):
        self.setStyleSheet(f"background-color: {BG};")

        central = QWidget()
        central.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Chart area ────────────────────────────────────────────────────────
        chart_frame = QFrame()
        chart_frame.setStyleSheet(
            f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;"
        )
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(8, 8, 8, 8)

        # Header
        title = QLabel("Race Pace — Lap Time Progression")
        title.setFont(QFont("Arial", 13, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT}; background: transparent; border: none;")
        chart_layout.addWidget(title)

        # Placeholder label (shown when < 2 laps of data)
        self._placeholder = QLabel("Waiting for lap data...")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setFont(QFont("Arial", 14))
        self._placeholder.setStyleSheet(f"color: {DIM}; background: transparent; border: none;")
        self._placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # PyQtGraph plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel("bottom", "Lap")
        self._plot_widget.setLabel("left", "Lap Time (s)")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self._plot_widget.getAxis("bottom").setStyle(tickFont=QFont("Arial", 9))
        self._plot_widget.getAxis("left").setStyle(tickFont=QFont("Arial", 9))
        self._plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._plot_widget.hide()

        chart_layout.addWidget(self._placeholder)
        chart_layout.addWidget(self._plot_widget)

        root.addWidget(chart_frame, stretch=1)

        # ── Driver sidebar ────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setFixedWidth(130)
        sidebar.setStyleSheet(
            f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 8, 6, 8)
        sidebar_layout.setSpacing(4)

        sidebar_title = QLabel("Drivers")
        sidebar_title.setFont(QFont("Arial", 11, QFont.Bold))
        sidebar_title.setStyleSheet(f"color: {TEXT}; background: transparent; border: none;")
        sidebar_layout.addWidget(sidebar_title)

        self._driver_list = QListWidget()
        self._driver_list.setStyleSheet(
            f"QListWidget {{ background: {BG}; border: none; color: {TEXT}; }}"
            f"QListWidget::item {{ padding: 4px; }}"
            f"QListWidget::item:selected {{ background: {BORDER}; }}"
        )
        self._driver_list.setFont(QFont("Arial", 10))
        self._driver_list.itemChanged.connect(self._on_driver_toggled)
        sidebar_layout.addWidget(self._driver_list)

        root.addWidget(sidebar)

        if hasattr(self, "status_bar"):
            self.status_bar.hide()

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def on_telemetry_data(self, data):
        frame = data.get("frame", {})
        drivers = frame.get("drivers", {})
        if not drivers:
            return

        now = time.monotonic()

        for code, d in drivers.items():
            lap = int(d.get("lap") or 0)
            rel_dist = float(d.get("rel_dist") or 0.0)
            team = d.get("team")
            if team:
                self._driver_teams[code] = team

            # Assign colour index on first sight
            if code not in self._colour_index:
                self._colour_index[code] = len(self._colour_index)
                self._lap_times[code] = []
                self._active_drivers.add(code)
                self._add_driver_to_sidebar(code)

            prev_lap = self._prev_lap.get(code, lap)
            prev_rel = self._prev_rel_dist.get(code)
            prev_time = self._prev_frame_time.get(code)

            # Detect lap boundary crossing: lap number incremented
            if lap > prev_lap and prev_time is not None:
                elapsed = now - prev_time
                # Sanity-check: lap time should be between 30 s and 300 s
                if 30.0 < elapsed < 300.0:
                    self._lap_times[code].append(round(elapsed, 3))
                    if self._session_fastest is None or elapsed < self._session_fastest:
                        self._session_fastest = elapsed

            self._prev_lap[code] = lap
            self._prev_rel_dist[code] = rel_dist
            self._prev_frame_time[code] = now

    # ── Chart rendering ────────────────────────────────────────────────────────

    def _maybe_refresh_chart(self):
        now = time.monotonic()
        if now - self._last_chart_update < self._chart_interval:
            return
        self._last_chart_update = now
        self._redraw_chart()

    def _redraw_chart(self):
        # Check if any driver has at least 2 completed laps
        has_data = any(len(laps) >= 2 for laps in self._lap_times.values())

        if not has_data:
            self._placeholder.show()
            self._plot_widget.hide()
            return

        self._placeholder.hide()
        self._plot_widget.show()

        plot = self._plot_widget
        plot.clear()
        self._fastest_line = None

        for code in sorted(self._active_drivers):
            laps = self._lap_times.get(code, [])
            if len(laps) < 2 or code not in self._active_drivers:
                continue
            team = self._driver_teams.get(code)
            colour = _driver_colour(code, team, self._colour_index.get(code, 0))
            x = list(range(1, len(laps) + 1))
            pen = pg.mkPen(color=colour, width=2)
            plot.plot(x, laps, pen=pen, name=code)

        if self._session_fastest is not None:
            pen = pg.mkPen(color=ACCENT, width=1, style=Qt.DashLine)
            self._fastest_line = pg.InfiniteLine(
                pos=self._session_fastest, angle=0, pen=pen,
                label=f"Fastest: {self._session_fastest:.3f}s",
                labelOpts={"color": ACCENT, "position": 0.95},
            )
            plot.addItem(self._fastest_line)

    # ── Sidebar management ─────────────────────────────────────────────────────

    def _add_driver_to_sidebar(self, code: str):
        item = QListWidgetItem(code)
        item.setCheckState(Qt.Checked)
        item.setForeground(QColor(TEXT))
        self._driver_list.addItem(item)

    def _on_driver_toggled(self, item: QListWidgetItem):
        code = item.text()
        if item.checkState() == Qt.Checked:
            self._active_drivers.add(code)
        else:
            self._active_drivers.discard(code)
        self._redraw_chart()

    def on_connection_status_changed(self, status: str):
        if status != "Connected":
            self._placeholder.show()
            self._plot_widget.hide()
