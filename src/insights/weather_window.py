"""
Weather insight window.

Shows, for the circuit of the session being replayed:

* a pre-race / in-race forecast from Open-Meteo (free, no API key) for the
  hours around the session start, with a rain-risk banner and hourly table,
* the current conditions at the circuit,
* the recorded weather at the current replay time (track/air temperature,
  humidity, wind, rain) taken from the replay's own telemetry.

The forecast is fetched on a background thread so the UI never blocks, and is
refreshed every 10 minutes (or via the Refresh button).
"""

import sys
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.gui.pit_wall_window import PitWallWindow
from src.services import weather_forecast as wf


# ── Colour palette (matches the app's existing dark theme) ────────────────
_BG = "#282828"
_BG_DARKER = "#1E1E1E"
_BORDER = "#3A3A3A"
_TEXT_PRIMARY = "#E0E0E0"
_TEXT_DIMMED = "#888888"
_ACCENT = "#3A5F8F"

RISK_COLOURS = {
    "Low": "#2ECC71",
    "Moderate": "#F39C12",
    "High": "#E74C3C",
    "Unknown": "#888888",
}

FORECAST_REFRESH_MS = 10 * 60 * 1000
TIMING_REFRESH_MS = 30 * 1000
HOURS_BEFORE = 2
HOURS_AFTER = 4
MS_TO_KPH = 3.6  # replay telemetry stores wind speed in m/s

TABLE_HEADERS = ["Local time", "Conditions", "Temp", "Rain chance", "Rain", "Wind"]


# ── Pure formatting helpers (no Qt state, unit-tested) ─────────────────────

def format_number(value, fmt="{:.0f}", suffix="", default="–"):
    """Format ``value`` or return ``default`` when it is missing."""
    if value is None:
        return default
    return fmt.format(value) + suffix


def forecast_row(point):
    """Turn an hourly forecast point into the table's display strings."""
    description, emoji = wf.describe_weather_code(point.weather_code)
    wind = format_number(point.wind_kph, suffix=" km/h")
    direction = wf.compass_direction(point.wind_direction_deg)
    if direction and point.wind_kph is not None:
        wind = f"{wind} {direction}"
    if point.wind_gust_kph is not None:
        wind = f"{wind} (gusts {point.wind_gust_kph:.0f})"
    return (
        point.time.strftime("%a %H:%M"),
        f"{emoji} {description}".strip(),
        format_number(point.temperature_c, suffix="°C"),
        format_number(point.rain_probability_pct, suffix="%"),
        format_number(point.precipitation_mm, fmt="{:.1f}", suffix=" mm"),
        wind,
    )


def summary_text(summary):
    """One-line headline for :func:`wf.summarize` output."""
    if not summary or not summary.get("hours"):
        return "No forecast hours available around the session."
    parts = []
    low, high = summary["temp_min_c"], summary["temp_max_c"]
    if low is not None and high is not None:
        parts.append(
            f"{low:.0f}°C" if round(low) == round(high) else f"{low:.0f}–{high:.0f}°C"
        )
    if summary["max_rain_probability_pct"] is not None:
        parts.append(f"rain chance up to {summary['max_rain_probability_pct']:.0f}%")
    if summary["total_precipitation_mm"] is not None:
        parts.append(f"{summary['total_precipitation_mm']:.1f} mm expected")
    if summary["max_wind_kph"] is not None:
        parts.append(f"wind up to {summary['max_wind_kph']:.0f} km/h")
    return "  ·  ".join(parts)


def replay_weather_lines(weather):
    """Display ``(label, value)`` pairs for a replay frame's ``weather`` dict."""
    if not weather:
        return []
    wind = weather.get("wind_speed")
    wind_kph = None if wind is None else wind * MS_TO_KPH
    direction = weather.get("wind_direction")
    wind_text = format_number(wind_kph, suffix=" km/h")
    compass = wf.compass_direction(direction)
    if compass and wind_kph is not None:
        wind_text = f"{wind_text} {compass}"
    rain_state = weather.get("rain_state")
    return [
        ("Track temp", format_number(weather.get("track_temp"), fmt="{:.1f}", suffix="°C")),
        ("Air temp", format_number(weather.get("air_temp"), fmt="{:.1f}", suffix="°C")),
        ("Humidity", format_number(weather.get("humidity"), suffix="%")),
        ("Wind", wind_text),
        ("Rain", rain_state.title() if isinstance(rain_state, str) else "–"),
    ]


def current_conditions_text(current, location_name=""):
    """Sentence describing the circuit's conditions right now."""
    if current is None:
        return "Current conditions unavailable."
    description, emoji = wf.describe_weather_code(current.weather_code)
    bits = [f"{emoji} {description}".strip()]
    if current.temperature_c is not None:
        bits.append(f"{current.temperature_c:.0f}°C")
    if current.wind_kph is not None:
        wind = f"wind {current.wind_kph:.0f} km/h"
        compass = wf.compass_direction(current.wind_direction_deg)
        bits.append(f"{wind} {compass}".strip())
    if current.precipitation_mm:
        bits.append(f"{current.precipitation_mm:.1f} mm rain")
    prefix = f"Right now at {location_name}: " if location_name else "Right now: "
    return prefix + "  ·  ".join(bits)


def candidate_names(event_info):
    """Place names to geocode, most specific first."""
    return [
        event_info.get("location") or "",
        event_info.get("circuit_name") or "",
        event_info.get("country") or "",
    ]


# ── Background fetch ──────────────────────────────────────────────────────

class _ForecastThread(QThread):
    loaded = Signal(object)  # wf.Forecast
    failed = Signal(str)

    def __init__(self, candidates, country, use_cache=True, parent=None):
        super().__init__(parent)
        self._candidates = list(candidates)
        self._country = country
        self._use_cache = use_cache

    def run(self):
        try:
            location = wf.resolve_location(self._candidates, self._country)
            forecast = wf.fetch_forecast(location, use_cache=self._use_cache)
        except wf.WeatherServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # never let a worker thread die silently
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.loaded.emit(forecast)


# ── Window ────────────────────────────────────────────────────────────────

class WeatherWindow(PitWallWindow):
    """Pre-race / in-race weather forecast plus recorded replay conditions."""

    def __init__(self):
        # Must exist before PitWallWindow.__init__ calls setup_ui().
        self._event_info = {}
        self._start_utc = None
        self._forecast = None
        self._thread = None
        super().__init__()
        self.setWindowTitle("Weather")
        self.setGeometry(140, 140, 720, 640)

        self._forecast_timer = QTimer(self)
        self._forecast_timer.timeout.connect(self.refresh_forecast)
        self._forecast_timer.start(FORECAST_REFRESH_MS)

        self._timing_timer = QTimer(self)
        self._timing_timer.timeout.connect(self._update_timing)
        self._timing_timer.start(TIMING_REFRESH_MS)

    # -- UI ----------------------------------------------------------------

    def setup_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background: {_BG}; color: {_TEXT_PRIMARY};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet(f"background: {_BG_DARKER}; border-bottom: 1px solid {_BORDER};")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title = QLabel("WEATHER")
        title.setFont(QFont("Arial", 13, QFont.Bold))
        title.setStyleSheet("border: none;")
        title_row.addWidget(title)
        title_row.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ background: {_BORDER}; color: {_TEXT_PRIMARY}; border: none;"
            f" padding: 4px 12px; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: #4A4A4A; }}"
            f"QPushButton:disabled {{ color: {_TEXT_DIMMED}; }}"
        )
        self._refresh_btn.clicked.connect(lambda: self.refresh_forecast(force=True))
        title_row.addWidget(self._refresh_btn)
        header_layout.addLayout(title_row)

        self._subtitle = QLabel("Waiting for session data...")
        self._subtitle.setFont(QFont("Arial", 10))
        self._subtitle.setStyleSheet(f"color: {_TEXT_DIMMED}; border: none;")
        header_layout.addWidget(self._subtitle)

        self._timing_label = QLabel("")
        self._timing_label.setFont(QFont("Arial", 10))
        self._timing_label.setStyleSheet(f"color: {_TEXT_DIMMED}; border: none;")
        header_layout.addWidget(self._timing_label)
        root.addWidget(header)

        body = QVBoxLayout()
        body.setContentsMargins(14, 12, 14, 12)
        body.setSpacing(10)

        # Rain-risk banner
        self._risk_label = QLabel("")
        self._risk_label.setFont(QFont("Arial", 12, QFont.Bold))
        self._risk_label.setAlignment(Qt.AlignCenter)
        self._risk_label.setMinimumHeight(34)
        self._risk_label.hide()
        body.addWidget(self._risk_label)

        self._summary_label = QLabel("")
        self._summary_label.setFont(QFont("Arial", 11))
        self._summary_label.setWordWrap(True)
        body.addWidget(self._summary_label)

        self._now_label = QLabel("")
        self._now_label.setFont(QFont("Arial", 10))
        self._now_label.setStyleSheet(f"color: {_TEXT_DIMMED};")
        self._now_label.setWordWrap(True)
        body.addWidget(self._now_label)

        # Hourly table
        self._table = QTableWidget(0, len(TABLE_HEADERS))
        self._table.setHorizontalHeaderLabels(TABLE_HEADERS)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.setShowGrid(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {_BG}; border: 1px solid {_BORDER}; gridline-color: {_BORDER}; }}"
            f"QHeaderView::section {{ background: {_BG_DARKER}; color: {_TEXT_DIMMED};"
            f" border: none; border-bottom: 1px solid {_BORDER}; padding: 4px; }}"
        )
        self._table.setMinimumHeight(200)
        body.addWidget(self._table, stretch=1)

        self._status_label = QLabel("Forecast will load when the replay connects.")
        self._status_label.setFont(QFont("Arial", 10))
        self._status_label.setStyleSheet(f"color: {_TEXT_DIMMED};")
        self._status_label.setWordWrap(True)
        body.addWidget(self._status_label)

        # Recorded replay conditions
        replay_title = QLabel("RECORDED CONDITIONS AT REPLAY TIME")
        replay_title.setFont(QFont("Arial", 10, QFont.Bold))
        replay_title.setStyleSheet(f"color: {_TEXT_DIMMED};")
        body.addWidget(replay_title)

        self._replay_labels = {}
        replay_row = QHBoxLayout()
        for name in ("Track temp", "Air temp", "Humidity", "Wind", "Rain"):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            caption = QLabel(name)
            caption.setFont(QFont("Arial", 9))
            caption.setStyleSheet(f"color: {_TEXT_DIMMED};")
            value = QLabel("–")
            value.setFont(QFont("Arial", 12, QFont.Bold))
            cell.addWidget(caption)
            cell.addWidget(value)
            replay_row.addLayout(cell)
            self._replay_labels[name] = value
        body.addLayout(replay_row)

        root.addLayout(body, stretch=1)

    # -- Telemetry stream --------------------------------------------------

    def on_telemetry_data(self, data):
        info = data.get("event_info")
        if info and info != self._event_info:
            self._set_event(info)

        frame = data.get("frame") or {}
        self._update_replay_weather(frame.get("weather"))

    def on_connection_status_changed(self, status):
        if status == "Disconnected" and self._forecast is None:
            self._status_label.setText(
                "Not connected to a replay. Start a race replay to load its forecast."
            )

    def _set_event(self, info):
        self._event_info = dict(info)
        self._start_utc = wf.parse_session_start(info.get("session_start_utc"))
        name = info.get("event_name") or info.get("circuit_name") or "Session"
        year = info.get("year")
        self._subtitle.setText(f"{name} {year}".strip() if year else name)
        self._forecast = None
        self._update_timing()
        self.refresh_forecast()

    def _update_replay_weather(self, weather):
        lines = replay_weather_lines(weather)
        if not lines:
            for label in self._replay_labels.values():
                label.setText("–")
            return
        for name, value in lines:
            self._replay_labels[name].setText(value)

    # -- Forecast ----------------------------------------------------------

    def refresh_forecast(self, force=False):
        """Fetch the forecast on a background thread (no-op if one is running)."""
        if not self._event_info:
            return
        if self._thread is not None and self._thread.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._status_label.setText("Loading forecast…")
        thread = _ForecastThread(
            candidate_names(self._event_info),
            self._event_info.get("country") or "",
            use_cache=not force,
            parent=self,
        )
        thread.loaded.connect(self._on_forecast_loaded)
        thread.failed.connect(self._on_forecast_failed)
        thread.finished.connect(lambda: self._refresh_btn.setEnabled(True))
        self._thread = thread
        thread.start()

    def _on_forecast_failed(self, message):
        self._status_label.setText(f"Forecast unavailable: {message}")
        if self._forecast is None:
            self._risk_label.hide()
            self._summary_label.setText("")
            self._now_label.setText("")
            self._table.setRowCount(0)

    def _on_forecast_loaded(self, forecast):
        self._forecast = forecast
        self._render_forecast()

    def _render_forecast(self):
        forecast = self._forecast
        if forecast is None:
            return
        location = forecast.location
        place = ", ".join(part for part in (location.name, location.country) if part)
        self._now_label.setText(current_conditions_text(forecast.current, place))

        start = self._start_utc or datetime.now(timezone.utc)
        if not wf.forecast_covers(start):
            self._risk_label.hide()
            self._summary_label.setText("")
            self._table.setRowCount(0)
            self._status_label.setText(
                f"Forecasts are only available for sessions within the next "
                f"{wf.MAX_FORECAST_DAYS} days (and the last {wf.PAST_DAYS}). "
                "Showing recorded replay conditions only."
            )
            return

        points = wf.hourly_window(forecast, start, HOURS_BEFORE, HOURS_AFTER)
        summary = wf.summarize(points)
        self._summary_label.setText(summary_text(summary))

        risk = summary["rain_risk"]
        colour = RISK_COLOURS.get(risk, RISK_COLOURS["Unknown"])
        self._risk_label.setText(f"Rain risk: {risk}")
        self._risk_label.setStyleSheet(
            f"background: {colour}; color: #111111; border-radius: 4px;"
        )
        self._risk_label.show()

        self._fill_table(points, start, forecast.utc_offset_seconds)
        updated = datetime.fromtimestamp(forecast.fetched_at).strftime("%H:%M")
        self._status_label.setText(
            f"Forecast for {place} (Open-Meteo), updated {updated}. Times are local to the circuit."
        )

    def _fill_table(self, points, start_utc, utc_offset_seconds):
        local_start = wf.to_local_naive(start_utc, utc_offset_seconds)
        self._table.setRowCount(len(points))
        for row, point in enumerate(points):
            is_session_hour = point.time.replace(minute=0, second=0, microsecond=0) == \
                local_start.replace(minute=0, second=0, microsecond=0)
            for column, text in enumerate(forecast_row(point)):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                if is_session_hour:
                    item.setBackground(QBrush(QColor(_ACCENT)))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self._table.setItem(row, column, item)

    def _update_timing(self):
        if self._start_utc is None:
            self._timing_label.setText("")
            return
        _, text = wf.session_timing(self._start_utc)
        self._timing_label.setText(text)

    # -- Lifecycle ---------------------------------------------------------

    def closeEvent(self, event):
        self._forecast_timer.stop()
        self._timing_timer.stop()
        if self._thread is not None and self._thread.isRunning():
            self._thread.wait(3000)
        super().closeEvent(event)


# ──────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Weather")
    window = WeatherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
