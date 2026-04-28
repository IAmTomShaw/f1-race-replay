"""
Lap Time Evolution Chart.

Plots each driver's lap time across the race, updating live as the
replay progresses.  Features include:

- Tyre compound markers (circle/square/triangle/diamond/star)
- Pit stop in/out lap separation
- Safety Car and VSC shaded zones
- 3-lap rolling pace trend line
- Interactive crosshair tooltip on hover
- Pit stop vertical markers with tyre change annotations
- Click-to-isolate legend interaction
- Gap-to-leader Y-axis mode toggle

Lap times are pre-computed by the replay server from the full frame
data, so they are deterministic regardless of playback speed.
"""

import sys
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QCheckBox, QFrame, QDoubleSpinBox,
    QDialog, QFormLayout, QDialogButtonBox
)
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtCore import Qt, QEvent
from src.gui.pit_wall_window import PitWallWindow
from src.lib.tyres import get_tyre_compound_int, get_tyre_compound_str

# Colour palette
_BG = "#282828"
_GRID = "#3A3A3A"
_TEXT = "#E0E0E0"
_TEXT_DIM = "#888888"
_DEFAULT_COLOUR = "#666666"

# Safety Car / VSC zone colours
_SC_COLOUR = "#FFD700"     # gold
_VSC_COLOUR = "#FF8C00"    # dark orange
_RED_FLAG_COLOUR = "#FF2020"

# Tyre compound → marker shape
_TYRE_MARKERS = {
    get_tyre_compound_int("SOFT"):         "o",
    get_tyre_compound_int("MEDIUM"):       "s",
    get_tyre_compound_int("HARD"):         "^",
    get_tyre_compound_int("INTERMEDIATE"): "D",
    get_tyre_compound_int("WET"):          "*",
}
_DEFAULT_MARKER = "o"

# Tyre compound → colour for stint shading
_TYRE_COLOURS = {
    get_tyre_compound_int("SOFT"):         "#FF3333",
    get_tyre_compound_int("MEDIUM"):       "#FFD700",
    get_tyre_compound_int("HARD"):         "#FFFFFF",
    get_tyre_compound_int("INTERMEDIATE"): "#43B02A",
    get_tyre_compound_int("WET"):          "#0072CE",
}

# Moving average window
_MA_WINDOW = 3


def _format_laptime(seconds, _pos=None):
    """Format lap time as M:SS.sss. Uses 1 decimal place for Y-axis labels."""
    if seconds <= 0:
        return ""
    m = int(seconds // 60)
    s = seconds % 60
    
    if _pos is not None:
        # Y-axis ticks
        return f"{m}:{s:04.1f}"
    
    # Tooltips and HUD
    return f"{m}:{s:06.3f}"


def _format_delta(seconds, _pos=None):
    """Format delta time, omitting the '+' sign for exactly 0.0."""
    if abs(seconds) < 0.0005:  # Effectively zero
        if _pos is not None:
            return "0.0"
        return "0.000s"
    if _pos is not None:
        return f"{seconds:+.1f}"
    return f"{seconds:+.3f}s"


def _moving_average(values, window):
    """Compute a simple moving average, returning same-length array with NaN padding."""
    if len(values) < window:
        return values[:]
    result = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            avg = sum(values[i - window + 1:i + 1]) / window
            result.append(avg)
    return result


def _entry_is_pit(entry, pit_threshold):
    is_pit = entry.get("is_pit")
    if is_pit is not None:
        return bool(is_pit)
    return entry.get("time_s", -1) > pit_threshold and entry.get("lap", 0) > 1


def _entry_is_out_lap(entry):
    return bool(entry.get("is_out_lap"))


def _entry_is_outlier(entry, pit_threshold):
    explicit = entry.get("is_outlier")
    if explicit is not None:
        return bool(explicit)
    return (
        entry.get("time_s", -1) > pit_threshold
        and not _entry_is_pit(entry, pit_threshold)
        and not _entry_is_out_lap(entry)
    )


class LapTimeChartWindow(PitWallWindow):
    """
    Pit wall insight that plots lap times for all drivers across the race.
    """

    def __init__(self):
        self._lap_times = {}        # code -> list of {"lap", "time_s", "tyre"}
        self._status_laps = []      # list of {"status", "start_lap", "end_lap"}
        self._driver_colors = {}    # code -> hex colour
        self._known_drivers = []
        self._total_laps = 0
        self._leader_lap = 0
        self._last_drawn_lap = 0
        self._needs_full_redraw = True
        self._focused_drivers = set()   # set of codes
        self._y_mode = "absolute"       # "absolute" | "gap"
        self._has_ever_drawn = False    # True after first successful redraw
        self._legend_visible = True

        # Crosshair annotation
        self._annot = None
        self._crosshair_v = None
        self._crosshair_h = None

        # Pan state — uses PIXEL coords to avoid feedback loops
        self._pan_press_px = None    # (px_x, px_y) at mouse-down
        self._pan_origin_xlim = None
        self._pan_origin_ylim = None
        self._pan_active = False

        # Home limits for zoom/pan clamping
        self._home_xlim = None
        self._home_ylim = None

        # User zoom state: preserved across live redraws
        self._user_xlim = None
        self._user_ylim = None
        self._view_state_by_mode = {}
        self._undo_stack = []
        self._redo_stack = []
        # Crosshair debounce
        self._last_crosshair_state = None

        super().__init__()

        # Map graph line artists to driver codes
        self._artist_to_driver = {}
        self.setWindowTitle("F1 Race Replay - Lap Time Evolution")
        self.setGeometry(120, 120, 1000, 600)
        
        self.status_bar.setStyleSheet("""
            QStatusBar {
                border-top: 1px solid #6A6A6A;
            }
            QStatusBar::item {
                border: none;
            }
        """)
        

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()

    def _reposition_overlays(self):
        """Keep the help overlay centered."""
        if hasattr(self, '_help_overlay') and self._help_overlay:
            hx = (self._canvas.width() - self._help_overlay.width()) // 2
            hy = (self._canvas.height() - self._help_overlay.height()) // 2
            self._help_overlay.move(max(0, hx), max(0, hy))

    def _gap_ref_s(self, entry):
        if not entry:
            return None
        if entry.get("source") == "official":
            line_time_s = entry.get("line_time_s")
            if line_time_s is not None:
                return float(line_time_s)
            if entry.get("end_time_s") is not None:
                return float(entry["end_time_s"])
        gap_clock_s = entry.get("gap_clock_s")
        if gap_clock_s is not None:
            return float(gap_clock_s)
        return None

    def _official_gap_to_leader_s(self, entry):
        if not entry:
            return None
        gap_s = entry.get("official_gap_to_leader_s")
        if gap_s is not None:
            return float(gap_s)
        return None

    def _official_gap_is_approx(self, entry):
        if not entry:
            return False
        return entry.get("official_gap_source") not in (None, "direct")

    def _official_finish_gap_s(self, entry):
        if (
            entry
            and self._total_laps
            and self._leader_lap >= self._total_laps
            and entry.get("lap") == self._total_laps
        ):
            gap_s = entry.get("official_finish_gap_s")
            if gap_s is not None:
                return float(gap_s)
        return None

    def _is_approx_time_entry(self, entry):
        if not entry:
            return False
        return (
            entry.get("time_source") == "frame_backfill"
            or entry.get("source") == "derived"
        )

    def _raw_gap_fallback_s(self, entry, leader_refs=None):
        if not entry or leader_refs is None:
            return None
        lap = entry.get("lap")
        ref = leader_refs.get(lap)
        if ref is None:
            return None
        ref_s = self._gap_ref_s(entry)
        if ref_s is None:
            return None
        return ref_s - ref["ref_s"]

    def _display_gap_meta(self, entry, leader_refs=None, official_gap_laps=None, code=None):
        if not entry:
            return None, False

        if code is not None:
            override = getattr(self, "_cached_gap_overrides", {}).get((code, entry.get("lap")))
            if override is not None:
                return (0.0 if -0.05 < override < 0 else override), True

        gap_s = self._official_gap_to_leader_s(entry)
        if gap_s is not None:
            return (0.0 if -0.05 < gap_s < 0 else gap_s), self._official_gap_is_approx(entry)

        finish_gap_s = self._official_finish_gap_s(entry)
        if finish_gap_s is not None:
            return (0.0 if -0.05 < finish_gap_s < 0 else finish_gap_s), False

        adjusted = None
        if code is not None:
            adjusted = getattr(self, "_cached_gap_adjustments", {}).get((code, entry.get("lap")))
        if adjusted is None:
            val = self._raw_gap_fallback_s(entry, leader_refs)
        else:
            val = adjusted
        if val is None:
            return None, False
        return (0.0 if -0.05 < val < 0 else val), True

    def _display_gap_value(self, entry, leader_refs=None, official_gap_laps=None, code=None):
        val, _ = self._display_gap_meta(entry, leader_refs, official_gap_laps, code)
        return val

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)
        root.setContentsMargins(10, 10, 10, 10)

        # Control row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        driver_label = QLabel("Driver:")
        driver_label.setFont(QFont("Arial", 11))
        self._driver_combo = QComboBox()
        self._driver_combo.setMinimumWidth(120)
        self._driver_combo.setPlaceholderText("Waiting for data…")
        self._driver_combo.setFont(QFont("Arial", 11))
        self._driver_combo.addItem("All Drivers")
        self._driver_combo.currentTextChanged.connect(self._on_driver_changed)

        ctrl.addWidget(driver_label)
        ctrl.addWidget(self._driver_combo)
        
        ctrl.addSpacing(20)

        # Y-axis mode selector
        ymode_label = QLabel("Y Axis:")
        ymode_label.setFont(QFont("Arial", 11))
        self._ymode_combo = QComboBox()
        self._ymode_combo.setFont(QFont("Arial", 11))
        self._ymode_combo.addItems(["Lap Time", "Gap to Leader"])
        self._ymode_combo.currentIndexChanged.connect(self._on_ymode_changed)

        ctrl.addWidget(ymode_label)
        ctrl.addWidget(self._ymode_combo)
        ctrl.addSpacing(20)

        self._pure_pace_cb = QCheckBox("Pure Pace (Hide SC/Pits)")
        self._pure_pace_cb.setFont(QFont("Arial", 11))
        self._pure_pace_cb.stateChanged.connect(self._on_pure_pace_toggled)
        ctrl.addWidget(self._pure_pace_cb)

        ctrl.addSpacing(18)

        self._axis_limits_btn = QPushButton("Axis Limits")
        self._axis_limits_btn.setFont(QFont("Arial", 10))
        self._axis_limits_btn.clicked.connect(self._open_axis_limits_dialog)
        ctrl.addWidget(self._axis_limits_btn)

        self._undo_btn = QPushButton("Undo")
        self._undo_btn.setFont(QFont("Arial", 10))
        self._undo_btn.clicked.connect(self._undo_view)
        ctrl.addWidget(self._undo_btn)

        self._redo_btn = QPushButton("Redo")
        self._redo_btn.setFont(QFont("Arial", 10))
        self._redo_btn.clicked.connect(self._redo_view)
        ctrl.addWidget(self._redo_btn)
        
        ctrl.addStretch()
        
        self._help_btn = QPushButton("?")
        self._help_btn.setFixedSize(26, 26)
        self._help_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: white;
                border-radius: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #555555; }
        """)
        self._help_btn.clicked.connect(self._toggle_help)
        ctrl.addWidget(self._help_btn)

        mono_font = QFont("Consolas", 10)
        self._lap_status = QLabel("")
        self._lap_status.setFont(mono_font)
        self._lap_status.setStyleSheet(f"color: {_TEXT_DIM};")
        self._lap_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ctrl.addWidget(self._lap_status)

        self._status_sep = QLabel(" · ")
        self._status_sep.setFont(mono_font)
        self._status_sep.setStyleSheet(f"color: {_TEXT_DIM};")
        self._status_sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ctrl.addWidget(self._status_sep)

        self._time_status = QLabel("")
        self._time_status.setFont(mono_font)
        self._time_status.setStyleSheet(f"color: {_TEXT_DIM};")
        self._time_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ctrl.addWidget(self._time_status)

        self._reserve_status_width()

        root.addLayout(ctrl)
        self._update_history_buttons()

        # tighten layout
        self._fig, self._ax = plt.subplots(figsize=(6, 4), facecolor=_BG, edgecolor=_BG)
        self._fig.subplots_adjust(left=0.08, right=0.97, top=0.95, bottom=0.10)
        self._fig.patch.set_linewidth(0)
        self._setup_axes(self._ax)

        self._canvas = FigureCanvas(self._fig)
        self._canvas.setStyleSheet("border: none; outline: none;")
        self._canvas.setSizePolicy(
            self._canvas.sizePolicy().horizontalPolicy(),
            self._canvas.sizePolicy().verticalPolicy(),
        )
        root.addWidget(self._canvas, stretch=1)

        # Connect mouse events: crosshair, legend/line pick, scroll-zoom, drag-pan
        self._canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self._canvas.mpl_connect("pick_event", self._on_pick)
        self._canvas.mpl_connect("scroll_event", self._on_scroll)
        self._canvas.mpl_connect("button_press_event", self._on_button_press)
        self._canvas.mpl_connect("button_release_event", self._on_button_release)

        # Enable pinch-to-zoom gesture on macOS trackpad
        self._canvas.grabGesture(Qt.GestureType.PinchGesture)
        self._canvas.installEventFilter(self)
        self._pinch_scale_accum = 1.0

        self._create_overlays()

    def _create_overlays(self):
        # Help Overlay
        self._help_overlay = QLabel(self._canvas)
        self._help_overlay.setStyleSheet("""
            QLabel {
                background-color: #1E1E1E;
                color: #E0E0E0;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 20px;
            }
            h3 { margin-top: 0; color: #FFFFFF; font-size: 14px; margin-bottom: 8px; }
            h4 { margin-top: 12px; margin-bottom: 4px; color: #AAAAAA; font-size: 12px; text-transform: uppercase; }
            ul { margin-top: 0; margin-bottom: 0; padding-left: 20px; }
            li { margin-bottom: 4px; line-height: 1.4; }
        """)
        self._help_overlay.setFont(QFont("Arial", 11))
        self._help_overlay.setText(
            "<h3>🏎️ Lap Time Evolution</h3>"
            "<h4>Key Features</h4>"
            "<ul>"
            "<li><b>Tyre Compounds:</b> Markers indicate compound (Soft=●, Medium=■, Hard=▲, Inter=◆, Wet=★)</li>"
            "<li><b>Stints & Pit Stops:</b> Dashed lines show stint averages; vertical lines with x on top indicate pit stops</li>"
            "<li><b>Best Laps:</b> <b><font color='#B027C9'>Purple</font></b> = Session Best, <b><font color='#27C93F'>Green</font></b> = Personal Best</li>"
            "<li><b>Pace Filters:</b> Toggle 'Pure Pace' to hide SC/VSC and pit stop outliers</li>"
            "<li><b>Gap Mode:</b> Compare each driver's lap-completion time to the leader at the timing line</li>"
            "</ul>"
            "<h4>Controls</h4>"
            "<ul>"
            "<li><b>Scroll / Pinch:</b> Zoom in & out</li>"
            "<li><b>Axis Limits:</b> Enter exact X/Y ranges</li>"
            "<li><b>Left-Click & Drag:</b> Pan around the chart</li>"
            "<li><b>Undo / Redo:</b> Step backward or forward through chart views</li>"
            "<li><b>Double-Click:</b> Reset view to full race</li>"
            "<li><b>Click Legend:</b> Toggle driver isolation for comparison</li>"
            "<li><b>H:</b> Toggle this help overlay</li>"
            "<li><b>I:</b> Show or hide the legend</li>"
            "<li><b>Hover:</b> View exact lap times & tyre life</li>"
            "</ul>"
        )
        self._help_overlay.adjustSize()
        self._help_overlay.hide()

    def _reserve_status_width(self):
        if not hasattr(self, "_lap_status"):
            return
        sample_total_laps = max(int(self._total_laps or 0), 99)
        metrics = QFontMetrics(self._lap_status.font())
        lap_sample = f"Lap {sample_total_laps}/{sample_total_laps}"
        self._lap_status.setFixedWidth(metrics.horizontalAdvance(lap_sample) + 8)
        self._status_sep.setFixedWidth(metrics.horizontalAdvance(" · ") + 2)
        self._time_status.setFixedWidth(metrics.horizontalAdvance("00:00:00") + 8)

    def _setup_axes(self, ax):
        """Apply consistent styling to the axes."""
        ax.set_facecolor(_BG)
        ax.set_xlabel("Lap", color=_TEXT, fontsize=10)
        if self._y_mode == "gap":
            ax.set_ylabel("Gap to Leader (s)", color=_TEXT, fontsize=10)
        else:
            ax.set_ylabel("Lap Time", color=_TEXT, fontsize=10)
        ax.tick_params(colors=_TEXT, labelsize=9)
        if self._y_mode == "absolute":
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(_format_laptime))
        else:
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(_format_delta))
        ax.grid(True, color=_GRID, alpha=0.5, linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_edgecolor("#555555")

    # Telemetry handling

    def on_telemetry_data(self, data):
        frame = data.get("frame")
        if not frame:
            return

        drivers = frame.get("drivers", {})
        if not drivers:
            return

        # Capture colours
        colors = data.get("driver_colors", {})
        if colors:
            self._driver_colors = colors

        # Capture session info
        sd = data.get("session_data", {})
        if sd:
            tl = sd.get("total_laps", 0)
            if tl:
                self._total_laps = int(tl)
                self._reserve_status_width()
            new_leader_lap = sd.get("lap", self._leader_lap)
            if isinstance(new_leader_lap, (int, float)):
                self._leader_lap = int(new_leader_lap)
            self._lap_status.setText(f"Lap {sd.get('lap', '?')}/{self._total_laps or '?'}")
            self._status_sep.setText(" · ")
            self._time_status.setText(sd.get('time', ''))

        # Detect rewind
        if self._leader_lap < self._last_drawn_lap:
            self._last_drawn_lap = 0
            self._needs_full_redraw = True
            self._user_xlim = None
            self._user_ylim = None
            self._view_state_by_mode.clear()

        # Ingest pre-computed data from server
        server_lap_times = data.get("lap_times")
        if server_lap_times:
            # Only flag for redraw if data actually changed
            if server_lap_times is not self._lap_times:
                self._lap_times = server_lap_times
                if not self._has_ever_drawn:
                    self._needs_full_redraw = True

        server_status_laps = data.get("status_laps")
        if server_status_laps:
            self._status_laps = server_status_laps

        # Update driver list
        self._refresh_driver_list(drivers)

        # Redraw when leader crosses a new lap or first data arrival
        if self._leader_lap > self._last_drawn_lap or self._needs_full_redraw:
            self._last_drawn_lap = self._leader_lap
            self._needs_full_redraw = False
            self._redraw()

    def _refresh_driver_list(self, drivers):
        incoming = sorted(drivers.keys())
        if incoming == self._known_drivers:
            return
        current = self._driver_combo.currentText()
        self._driver_combo.blockSignals(True)
        self._driver_combo.clear()
        self._driver_combo.addItem("All Drivers")
        self._driver_combo.addItem("Multiple Drivers")
        self._driver_combo.addItems(incoming)
        if current and current in [self._driver_combo.itemText(i) for i in range(self._driver_combo.count())]:
            self._driver_combo.setCurrentText(current)
        elif current == "All Drivers":
            self._driver_combo.setCurrentText("All Drivers")
        else:
            self._driver_combo.setCurrentIndex(0)
        self._driver_combo.blockSignals(False)
        self._known_drivers = incoming

    def _on_driver_changed(self, text):
        if text == "Multiple Drivers":
            return
        if text == "All Drivers":
            self._focused_drivers.clear()
        else:
            self._focused_drivers = {text}
        self._needs_full_redraw = True
        self._redraw()

    def _on_ymode_changed(self, index):
        self._push_undo_state()
        self._save_view_state()
        self._y_mode = "absolute" if index == 0 else "gap"
        self._restore_view_state()
        self._needs_full_redraw = True
        self._redraw()

    def _save_view_state(self):
        if not getattr(self, "_has_ever_drawn", False):
            return
        if not hasattr(self, "_ax"):
            return
        self._view_state_by_mode[self._y_mode] = (self._ax.get_xlim(), self._ax.get_ylim())

    def _restore_view_state(self):
        state = self._view_state_by_mode.get(self._y_mode)
        if state:
            self._user_xlim, self._user_ylim = state
        else:
            self._user_xlim = None
            self._user_ylim = None

    def _set_user_view(self, xlim, ylim):
        self._user_xlim = tuple(xlim)
        self._user_ylim = tuple(ylim)
        self._view_state_by_mode[self._y_mode] = (self._user_xlim, self._user_ylim)

    def _capture_view_snapshot(self):
        if not hasattr(self, "_ax"):
            return None
        return {
            "mode": self._y_mode,
            "xlim": tuple(self._ax.get_xlim()),
            "ylim": tuple(self._ax.get_ylim()),
        }

    def _push_undo_state(self):
        snapshot = self._capture_view_snapshot()
        if not snapshot:
            return
        if self._undo_stack and self._undo_stack[-1] == snapshot:
            return
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()
        self._update_history_buttons()

    def _restore_view_snapshot(self, snapshot):
        if not snapshot:
            return
        mode = snapshot.get("mode", self._y_mode)
        if mode != self._y_mode:
            self._y_mode = mode
            self._ymode_combo.blockSignals(True)
            self._ymode_combo.setCurrentIndex(0 if mode == "absolute" else 1)
            self._ymode_combo.blockSignals(False)
            self._user_xlim = tuple(snapshot["xlim"])
            self._user_ylim = tuple(snapshot["ylim"])
            self._needs_full_redraw = True
            self._redraw()
            self._update_history_buttons()
            return
        self._ax.set_xlim(snapshot["xlim"])
        self._ax.set_ylim(snapshot["ylim"])
        self._set_user_view(snapshot["xlim"], snapshot["ylim"])
        self._update_history_buttons()
        self._canvas.draw_idle()

    def _undo_view(self):
        if not self._undo_stack:
            return
        current = self._capture_view_snapshot()
        previous = self._undo_stack.pop()
        if current:
            self._redo_stack.append(current)
        self._restore_view_snapshot(previous)
        self._update_history_buttons()

    def _redo_view(self):
        if not self._redo_stack:
            return
        current = self._capture_view_snapshot()
        nxt = self._redo_stack.pop()
        if current:
            self._undo_stack.append(current)
        self._restore_view_snapshot(nxt)
        self._update_history_buttons()

    def _update_history_buttons(self):
        if hasattr(self, "_undo_btn"):
            self._undo_btn.setEnabled(bool(self._undo_stack))
        if hasattr(self, "_redo_btn"):
            self._redo_btn.setEnabled(bool(self._redo_stack))

    def _open_axis_limits_dialog(self):
        if not hasattr(self, "_ax"):
            return
        x_lo, x_hi = self._ax.get_xlim()
        y_lo, y_hi = self._ax.get_ylim()
        allowed_x_lo, allowed_x_hi = self._home_xlim if self._home_xlim else (x_lo, x_hi)
        allowed_y_lo, allowed_y_hi = self._max_ylim if hasattr(self, "_max_ylim") else (y_lo, y_hi)

        dialog = QDialog(self)
        dialog.setWindowTitle("Axis Limits")
        form = QFormLayout(dialog)
        spinboxes = []
        for label, value, min_value, max_value, step in (
            ("X min", x_lo, allowed_x_lo, allowed_x_hi, 1.0),
            ("X max", x_hi, allowed_x_lo, allowed_x_hi, 1.0),
            ("Y min", y_lo, allowed_y_lo, allowed_y_hi, 1.0),
            ("Y max", y_hi, allowed_y_lo, allowed_y_hi, 1.0),
        ):
            spin = QDoubleSpinBox(dialog)
            spin.setRange(float(min_value), float(max_value))
            spin.setDecimals(3)
            spin.setSingleStep(step)
            spin.setValue(float(min(max(value, min_value), max_value)))
            form.addRow(label, spin)
            spinboxes.append(spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_x_lo, new_x_hi, new_y_lo, new_y_hi = [spin.value() for spin in spinboxes]
        new_x_lo = max(allowed_x_lo, min(new_x_lo, allowed_x_hi))
        new_x_hi = max(allowed_x_lo, min(new_x_hi, allowed_x_hi))
        new_y_lo = max(allowed_y_lo, min(new_y_lo, allowed_y_hi))
        new_y_hi = max(allowed_y_lo, min(new_y_hi, allowed_y_hi))
        if new_x_hi <= new_x_lo or new_y_hi <= new_y_lo:
            return
        self._push_undo_state()
        self._ax.set_xlim(new_x_lo, new_x_hi)
        self._ax.set_ylim(new_y_lo, new_y_hi)
        self._set_user_view((new_x_lo, new_x_hi), (new_y_lo, new_y_hi))
        self._canvas.draw_idle()

    def _on_pure_pace_toggled(self, state):
        self._needs_full_redraw = True
        self._redraw()

    def _toggle_help(self):
        if self._help_overlay.isHidden():
            self._reposition_overlays()
            self._help_overlay.show()
            self._help_overlay.raise_()
        else:
            self._help_overlay.hide()

    # Chart rendering

    def _redraw(self):
        ax = self._ax
        ax.clear()
        self._setup_axes(ax)
        self._annot = None
        self._legend_artist = None

        if not self._lap_times:
            self._canvas.draw_idle()
            return

        focus = self._focused_drivers

        # Show completed laps only during replay, but include the final lap once
        # the race has actually finished.
        visible_data = {}
        lap_cutoff = self._leader_lap
        include_final_lap = self._total_laps and self._leader_lap >= self._total_laps
        for code, entries in self._lap_times.items():
            terminal_lap = next((e["lap"] for e in entries if e.get("is_terminal_lap")), None)
            effective_cutoff = lap_cutoff
            if terminal_lap is not None:
                effective_cutoff = min(effective_cutoff, terminal_lap)
            if include_final_lap:
                visible = [e for e in entries if e["lap"] <= effective_cutoff]
            else:
                visible = [e for e in entries if e["lap"] < effective_cutoff or (e.get("is_terminal_lap") and e["lap"] == effective_cutoff)]
            if visible:
                visible_data[code] = visible

        if not visible_data:
            self._canvas.draw_idle()
            return

        pure_pace = self._pure_pace_cb.isChecked()
        sc_vsc_laps = set()
        
        # ── 1. Safety Car / VSC shaded zones ──
        # Merge overlapping/adjacent periods into unified visual spans
        # to prevent label overlap (e.g. VSC → SC on consecutive laps).
        merged_zones = []
        for sp in self._status_laps:
            if sp["start_lap"] > self._leader_lap:
                continue
            end_lap = min(sp["end_lap"], self._leader_lap)
            status = sp["status"]
            if status == "4":
                colour, label = _SC_COLOUR, "SC"
            elif status in ("6", "7"):
                colour, label = _VSC_COLOUR, "VSC"
            elif status == "5":
                colour, label = _RED_FLAG_COLOUR, "RED"
            else:
                continue
                
            # Record SC laps to filter them out of pace calcs
            for l in range(sp["start_lap"], end_lap + 1):
                sc_vsc_laps.add(l)

        # Compute median for pit lap filtering (excluding SC laps for accuracy)
        clean_times = [e["time_s"] for v in visible_data.values() for e in v if e["lap"] not in sc_vsc_laps]
        if clean_times:
            clean_times.sort()
            median_time = clean_times[len(clean_times) // 2]
            # A pit stop always adds at least ~18-20s. We use max(15, 10%) to be robust 
            # for both short tracks (Austria) and long tracks (Spa).
            pit_threshold = median_time + max(15.0, median_time * 0.12)
        else:
            pit_threshold = 9999.0
            
        self._cached_pit_threshold = pit_threshold
        self._cached_sc_vsc_laps = sc_vsc_laps

        # Build timing-screen-style gap references for gap mode.
        # For lap N, the baseline is the first classified driver to complete
        # lap N. Drivers behind should therefore be >= 0 unless source timing
        # data is inconsistent.
        lap_entry_lookup = {
            code: {e["lap"]: e for e in entries if e["time_s"] > 0}
            for code, entries in visible_data.items()
        }
        leader_refs = {}
        if self._y_mode == "gap":
            for lap in sorted({e["lap"] for entries in visible_data.values() for e in entries}):
                official_candidates = []
                candidates = []
                for code, lap_entries in lap_entry_lookup.items():
                    entry = lap_entries.get(lap)
                    official_gap_s = self._official_gap_to_leader_s(entry)
                    if official_gap_s is not None:
                        official_candidates.append((official_gap_s, code, entry))
                    ref_s = self._gap_ref_s(entry)
                    if ref_s is not None:
                        candidates.append((ref_s, code, entry))
                if official_candidates:
                    _, leader_code, entry = min(official_candidates, key=lambda item: item[0])
                    leader_refs[lap] = {
                        "code": leader_code,
                        "time_s": entry["time_s"],
                        "ref_s": self._gap_ref_s(entry),
                        "uses_official_gap": True,
                    }
                elif candidates:
                    ref_s, leader_code, entry = min(candidates, key=lambda item: item[0])
                    leader_refs[lap] = {
                        "code": leader_code,
                        "time_s": entry["time_s"],
                        "ref_s": ref_s,
                        "uses_official_gap": False,
                    }
        gap_adjustments = {}
        gap_overrides = {}
        if self._y_mode == "gap":
            for code, entries in visible_data.items():
                sorted_entries = sorted(entries, key=lambda item: item["lap"])
                anchors = []
                for entry in sorted_entries:
                    official_val = self._official_gap_to_leader_s(entry)
                    if official_val is None:
                        official_val = self._official_finish_gap_s(entry)
                    raw_val = self._raw_gap_fallback_s(entry, leader_refs)
                    if official_val is not None and raw_val is not None:
                        anchors.append({
                            "lap": entry["lap"],
                            "offset": float(official_val) - float(raw_val),
                        })

                if not anchors:
                    continue

                for entry in sorted_entries:
                    if self._official_gap_to_leader_s(entry) is not None or self._official_finish_gap_s(entry) is not None:
                        continue
                    raw_val = self._raw_gap_fallback_s(entry, leader_refs)
                    if raw_val is None:
                        continue
                    lap = entry["lap"]
                    prev_anchor = None
                    next_anchor = None
                    for anchor in anchors:
                        if anchor["lap"] < lap:
                            prev_anchor = anchor
                        elif anchor["lap"] > lap:
                            next_anchor = anchor
                            break
                    if prev_anchor and next_anchor:
                        span = next_anchor["lap"] - prev_anchor["lap"]
                        if span > 0:
                            t = (lap - prev_anchor["lap"]) / span
                            offset = prev_anchor["offset"] + t * (next_anchor["offset"] - prev_anchor["offset"])
                        else:
                            offset = prev_anchor["offset"]
                    elif prev_anchor:
                        offset = prev_anchor["offset"]
                    elif next_anchor:
                        offset = next_anchor["offset"]
                    else:
                        continue
                    gap_adjustments[(code, lap)] = raw_val + offset
            gap_override_threshold = 5.0
            for code, entries in visible_data.items():
                sorted_entries = sorted(entries, key=lambda item: item["lap"])
                prev_gap = None
                for entry in sorted_entries:
                    lap = entry["lap"]
                    leader_ref = leader_refs.get(lap)
                    leader_time_s = None if leader_ref is None else leader_ref.get("time_s")
                    official_val = self._official_gap_to_leader_s(entry)
                    if official_val is None:
                        official_val = self._official_finish_gap_s(entry)
                    fallback_val = gap_adjustments.get((code, lap))
                    if fallback_val is None:
                        fallback_val = self._raw_gap_fallback_s(entry, leader_refs)

                    display_val = official_val if official_val is not None else fallback_val
                    if (
                        official_val is not None
                        and prev_gap is not None
                        and entry.get("time_s", -1) > 0
                        and leader_time_s is not None
                        and leader_time_s > 0
                    ):
                        predicted = prev_gap + float(entry["time_s"]) - float(leader_time_s)
                        if (
                            abs(float(official_val) - predicted) > gap_override_threshold
                            and (
                                _entry_is_pit(entry, pit_threshold)
                                or _entry_is_out_lap(entry)
                                or _entry_is_outlier(entry, pit_threshold)
                            )
                        ):
                            gap_overrides[(code, lap)] = predicted
                            display_val = predicted

                    if display_val is not None:
                        prev_gap = float(display_val)
        official_gap_laps = {
            lap for lap, ref in leader_refs.items() if ref.get("uses_official_gap")
        }

        # Cache variables for O(1) lookups during high-frequency mouse hover events
        self._cached_visible_data = visible_data
        self._cached_pit_threshold = pit_threshold
        self._cached_leader_refs = leader_refs
        self._cached_official_gap_laps = official_gap_laps
        self._cached_gap_adjustments = gap_adjustments
        self._cached_gap_overrides = gap_overrides
        self._cached_terminal_no_time_points = []
                        
        for sp in self._status_laps:
            if sp["start_lap"] > self._leader_lap:
                continue
            end_lap = min(sp["end_lap"], self._leader_lap)
            status = sp["status"]
            if status not in ("4", "5", "6", "7"):
                continue
            if status == "4":
                colour, label = _SC_COLOUR, "SC"
            elif status in ("6", "7"):
                colour, label = _VSC_COLOUR, "VSC"
            elif status == "5":
                colour, label = _RED_FLAG_COLOUR, "RED"
            
            # Check if this zone overlaps/touches the previous one
            if merged_zones and sp["start_lap"] <= merged_zones[-1]["end"] + 1:
                prev = merged_zones[-1]
                prev["end"] = max(prev["end"], end_lap)
                # Combine labels if different (e.g. "VSC → SC")
                if label not in prev["label"]:
                    prev["label"] += f"→{label}"
                    prev["colour"] = colour  # use the later period's colour
            else:
                merged_zones.append({
                    "start": sp["start_lap"], "end": end_lap,
                    "colour": colour, "label": label,
                })

        for zone in merged_zones:
            ax.axvspan(
                zone["start"] - 0.5, zone["end"] + 0.5,
                color=zone["colour"], alpha=0.08, zorder=0,
            )
            mid = (zone["start"] + zone["end"]) / 2
            ax.text(
                mid, 1.02, zone["label"],
                transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=7, fontweight="bold",
                color=zone["colour"], alpha=0.7,
            )

        # ── 2-6. Per-driver rendering ──
        y_min = float("inf")
        y_max = float("-inf")

        # Store line references for picking
        self._artist_to_driver = {}
        driver_stints_text = {}
        display_y_vals = []
        all_axis_y_vals = []

        session_best = float("inf")
        session_best_code = None
        for code_sb, entries in visible_data.items():
            for e in entries:
                if (
                    0 < e["time_s"] <= pit_threshold
                    and e["lap"] not in sc_vsc_laps
                    and not _entry_is_pit(e, pit_threshold)
                    and not _entry_is_out_lap(e)
                    and not _entry_is_outlier(e, pit_threshold)
                ):
                    if e["time_s"] < session_best:
                        session_best = e["time_s"]
                        session_best_code = code_sb
        self._cached_session_best = session_best
        self._cached_session_best_code = session_best_code
        self._cached_driver_personal_bests = {}

        for code, entries in visible_data.items():
            colour = self._driver_colors.get(code, _DEFAULT_COLOUR)

            if focus:
                is_focused = code in focus
                alpha = 1.0 if is_focused else 0.10
                lw = 2.2 if is_focused else 0.6
                zorder = 10 if is_focused else 1
                show_detail = is_focused
            else:
                alpha = 0.75
                lw = 1.2
                zorder = 2
                show_detail = True

            clean_laps, clean_vals, clean_time_s, clean_tyres = [], [], [], []
            pit_laps, pit_vals = [], []
            all_laps, all_vals, all_markers = [], [], []
            terminal_no_time_laps = []
            
            drv_clean_times = [
                e["time_s"] for e in entries
                if (
                    0 < e["time_s"] <= pit_threshold
                    and e["lap"] not in sc_vsc_laps
                    and not _entry_is_pit(e, pit_threshold)
                    and not _entry_is_out_lap(e)
                    and not _entry_is_outlier(e, pit_threshold)
                )
            ]
            personal_best = min(drv_clean_times) if drv_clean_times else float("inf")
            self._cached_driver_personal_bests[code] = personal_best

            for e in entries:
                lap = e["lap"]
                raw_time = e["time_s"]
                is_pit = _entry_is_pit(e, pit_threshold)
                is_out_lap = _entry_is_out_lap(e)
                is_outlier = _entry_is_outlier(e, pit_threshold)

                if pure_pace and (lap in sc_vsc_laps or is_pit or is_out_lap or is_outlier):
                    continue

                if self._y_mode == "gap":
                    val = self._display_gap_value(e, leader_refs, official_gap_laps, code)
                    if val is None:
                        if is_pit:
                            pit_laps.append(lap)
                            pit_vals.append(0)
                        continue
                else:
                    if raw_time < 0:
                        if e.get("is_terminal_lap"):
                            terminal_no_time_laps.append(lap)
                        if is_pit:
                            pit_laps.append(lap)
                            pit_vals.append(0) # Dummy value, won't be plotted on main line
                        continue
                    val = raw_time
                    
                all_laps.append(lap)
                all_vals.append(val)
                all_markers.append(_TYRE_MARKERS.get(e.get("tyre", -1), _DEFAULT_MARKER))

                if is_pit:
                    # Explicit pit stop (In-Lap)
                    pit_laps.append(lap)
                    pit_vals.append(val)
                elif is_out_lap or is_outlier:
                    # Just a really slow lap (like a standing start or an Out-Lap).
                    # Ignore it completely so it doesn't squish the Y-axis.
                    pass
                else:
                    clean_laps.append(lap)
                    clean_vals.append(val)
                    clean_time_s.append(raw_time)
                    clean_tyres.append(e.get("tyre", -1))

            # Main pace line
            if all_laps:
                line, = ax.plot(
                    all_laps, all_vals,
                    color=colour, alpha=alpha, linewidth=lw,
                    zorder=zorder,
                    label=code,
                )
                self._artist_to_driver[line] = code

                purple_laps, purple_vals = [], []
                green_laps, green_vals = [], []
                for lp, tv, ts in zip(clean_laps, clean_vals, clean_time_s):
                    if ts == session_best and session_best < float("inf"):
                        purple_laps.append(lp)
                        purple_vals.append(tv)
                    elif ts == personal_best and personal_best < float("inf"):
                        green_laps.append(lp)
                        green_vals.append(tv)
                
                if green_laps and focus and is_focused:
                    ax.scatter(green_laps, green_vals, color="#00FF00", edgecolors="black", linewidths=0.5, zorder=zorder+3, s=40)
                if purple_laps:
                    ax.scatter(purple_laps, purple_vals, color="#800080", edgecolors="white", linewidths=0.8, zorder=zorder+4, s=45)

                # ── 3. Tyre compound markers ──
                prev_mk = None
                gx, gy = [], []
                for lp, tv, mk in zip(all_laps, all_vals, all_markers):
                    if mk != prev_mk and gx:
                        ax.scatter(
                            gx, gy, marker=prev_mk,
                            color=colour, alpha=alpha * 0.9,
                            s=22 if show_detail else 6,
                            zorder=zorder + 1, edgecolors="none",
                        )
                        gx, gy = [], []
                    gx.append(lp)
                    gy.append(tv)
                    prev_mk = mk
                if gx:
                    ax.scatter(
                        gx, gy, marker=prev_mk,
                        color=colour, alpha=alpha * 0.9,
                        s=22 if show_detail else 6,
                        zorder=zorder + 1, edgecolors="none",
                    )

                # ── 5. Tyre stint background bands (focused driver only) ──
                if show_detail and focus:
                    drv_pit_lap_set = {e["lap"] for e in entries if _entry_is_pit(e, pit_threshold)}
                    stint_str = self._draw_stint_bands(ax, clean_laps, clean_vals, clean_tyres, zorder - 1, drv_pit_lap_set)
                    if stint_str:
                        driver_stints_text[code] = stint_str

                # ── 2. Pace trend line (3-lap moving average) ──
                # Only show for the focused driver to reduce clutter
                if focus and is_focused and len(clean_vals) >= _MA_WINDOW:
                    ma = _moving_average(clean_vals, _MA_WINDOW)
                    ma_laps = [l for l, v in zip(clean_laps, ma) if v is not None]
                    ma_vals = [v for v in ma if v is not None]
                    if ma_laps:
                        ax.plot(
                            ma_laps, ma_vals,
                            color=colour, alpha=alpha * 0.5,
                            linewidth=lw + 1.5, linestyle="--",
                            zorder=zorder - 1,
                        )

                for v in clean_vals:
                    y_min = min(y_min, v)
                    y_max = max(y_max, v)
                display_y_vals.extend(clean_vals)
                all_axis_y_vals.extend(clean_vals)

            # ── 4. Pit stop vertical markers & × markers ──
            # Only show when a driver is focused (in All Drivers view,
            # dozens of pit-lap outlier points create noise)
            if pit_laps and focus and is_focused and not pure_pace:
                for pl in pit_laps:
                    ax.axvline(
                        pl, color=colour, alpha=0.3,
                        linewidth=0.8, linestyle=":",
                        zorder=zorder - 2,
                    )
                    ax.scatter(
                        pl, 0.95, marker="x",
                        color=colour, alpha=0.6, s=35,
                        zorder=zorder, linewidths=1.5,
                        transform=ax.get_xaxis_transform()
                    )

            if terminal_no_time_laps and focus and is_focused and self._y_mode == "time":
                for pl in terminal_no_time_laps:
                    status_text = next(
                        (
                            e.get("result_status", "Retired")
                            for e in entries
                            if e.get("lap") == pl and e.get("is_terminal_lap")
                        ),
                        "Retired",
                    )
                    self._cached_terminal_no_time_points.append({
                        "code": code,
                        "lap": pl,
                        "colour": colour,
                        "alpha": alpha,
                        "zorder": zorder + 2,
                        "status": status_text,
                    })

        # ── 4b. HUD Statistics (prepared for drawing at the end) ──
        hud_handles, hud_labels = [], []
        if focus and len(focus) <= 4:
            import matplotlib.lines as mlines
            for code in sorted(focus):
                if code not in visible_data: continue
                # Calculate best lap and avg true pace
                drv_clean_times = [
                    e["time_s"] for e in visible_data[code] 
                    if (
                        e["time_s"] <= pit_threshold
                        and e["lap"] not in sc_vsc_laps
                        and not _entry_is_pit(e, pit_threshold)
                        and not _entry_is_out_lap(e)
                        and not _entry_is_outlier(e, pit_threshold)
                    )
                ]
                # Count actual pit stops (group consecutive in/out laps)
                pit_laps = [e["lap"] for e in visible_data[code] if _entry_is_pit(e, pit_threshold)]
                drv_pit_stops = len(pit_laps)
                
                if drv_clean_times:
                    best = min(drv_clean_times)
                    avg = sum(drv_clean_times) / len(drv_clean_times)
                    hex_col = self._driver_colors.get(code, "#FFFFFF")
                    hud_handles.append(
                        mlines.Line2D([], [], color=hex_col, marker='s', linestyle='None', markersize=5)
                    )
                    stint_str = driver_stints_text.get(code, "")
                    if stint_str:
                        hud_labels.append(f'{code} | Best: {_format_laptime(best)} | Avg: {_format_laptime(avg)} | Stops: {drv_pit_stops} | Stints: {stint_str}')
                    else:
                        hud_labels.append(f'{code} | Best: {_format_laptime(best)} | Avg: {_format_laptime(avg)} | Stops: {drv_pit_stops}')

        # Y-axis padding. Gap mode defaults to a useful battle view instead
        # of letting retired or long-stopped cars flatten the competitive field.
        if display_y_vals:
            if self._y_mode == "gap":
                # Keep a stable default race-gap view even when a driver is
                # focused. Long garage stops / repairs should not re-scale the
                # whole chart around one outlier trace.
                inliers = [v for v in display_y_vals if v <= 120.0]
                y_hi = max(inliers) if len(inliers) >= 5 else float(np.percentile(display_y_vals, 85))
                ax.set_ylim(-5.0, max(5.0, y_hi + max(2.0, y_hi * 0.08)))
            elif all_axis_y_vals:
                y_min_display = min(all_axis_y_vals)
                y_max_display = max(all_axis_y_vals)
                pad = max(2.0, (y_max_display - y_min_display) * 0.06)
                ax.set_ylim(y_min_display - pad, y_max_display + pad)

        if self._cached_terminal_no_time_points and self._y_mode == "time":
            y_lo, y_hi = ax.get_ylim()
            span = max(y_hi - y_lo, 1.0)
            marker_y = y_hi - span * 0.045
            for point in self._cached_terminal_no_time_points:
                point["val"] = marker_y
                ax.scatter(
                    point["lap"], marker_y,
                    marker="o", facecolors=_BG, edgecolors=point["colour"],
                    alpha=point["alpha"], s=46, linewidths=1.4,
                    zorder=point["zorder"],
                )

        # X-axis
        all_laps = [e["lap"] for v in visible_data.values() for e in v]
        if all_laps:
            x_max = max(self._total_laps, max(all_laps)) + 0.5
            ax.set_xlim(min(all_laps) - 0.5, x_max)
            ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

        # ── 6. Interactive legend (click to isolate) ──
        handles, labels = ax.get_legend_handles_labels()
        if handles and self._legend_visible:
            leg = ax.legend(
                loc="upper right", fontsize=7, framealpha=0.6,
                facecolor=_BG, edgecolor="#555555", labelcolor=_TEXT,
                ncol=2 if len(handles) > 10 else 1,
            )
            self._legend_artist = leg
            # Make legend items pickable
            self._legend_map = {}
            for leg_line, orig_label in zip(leg.get_lines(), labels):
                leg_line.set_picker(5)
                leg_line.set_pickradius(5)
                self._legend_map[leg_line] = orig_label
            ax.add_artist(leg)

        # ── 7. HUD Statistics Legend ──
        if hud_handles:
            # Place HUD in the top left, but slightly offset so it doesn't overlap the coordinates readout
            hud_leg = ax.legend(
                hud_handles, hud_labels,
                loc="upper left", bbox_to_anchor=(0.0, 1.0),
                fontsize=8, framealpha=0.85,
                facecolor=_BG, edgecolor="#555555", labelcolor=_TEXT
            )
            hud_leg.set_zorder(50)

        # Setup crosshair annotation (hidden by default)
        self._annot = ax.annotate(
            "", xy=(0, 0), xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc="#1E1E1E", ec="#555555", alpha=0.92),
            fontsize=8, color=_TEXT,
            arrowprops=dict(arrowstyle="->", color="#666666"),
            zorder=100,
        )
        self._annot.set_visible(False)

        # Crosshair lines
        self._crosshair_v = ax.axvline(0, color="#555555", linewidth=0.5, linestyle="--", visible=False, zorder=99)
        self._crosshair_h = ax.axhline(0, color="#555555", linewidth=0.5, linestyle="--", visible=False, zorder=99)


        # Store home limits for zoom clamping
        self._home_xlim = ax.get_xlim()
        self._home_ylim = ax.get_ylim()

        all_v = []
        for vlist in visible_data.values():
            for e in vlist:
                if self._y_mode == "gap":
                    val = self._display_gap_value(e, leader_refs, official_gap_laps)
                    if val is not None:
                        all_v.append(val)
                else:
                    if e["time_s"] < 0:
                        continue
                    all_v.append(e["time_s"])
        
        if all_v:
            y_min_abs, y_max_abs = min(all_v), max(all_v)
            pad_abs = (y_max_abs - y_min_abs) * 0.05
            if self._y_mode == "gap":
                self._max_ylim = (-5.0, y_max_abs + max(2.0, pad_abs))
            else:
                # Keep the normal analytical lower bound from the default
                # visible view, but still allow users to pan/zoom upward into
                # anomalously long pit/garage laps when they want to inspect
                # them explicitly.
                self._max_ylim = (self._home_ylim[0], y_max_abs + pad_abs)
        else:
            self._max_ylim = self._home_ylim

        # If user had a custom zoom/pan, restore it
        if self._user_xlim is not None:
            ax.set_xlim(self._user_xlim)
        if self._user_ylim is not None:
            ax.set_ylim(self._user_ylim)

        self._has_ever_drawn = True
        self._canvas.draw_idle()

    def _draw_stint_bands(self, ax, laps, vals, tyres, zorder, pit_laps=None):
        """Draw faint tyre-coloured background bands behind the focused driver's line, and return stint averages."""
        if not laps:
            return ""
        
        if pit_laps is None:
            pit_laps = set()
        
        stints = []
        stint_start_idx = 0
        stint_tyre = tyres[0]
        
        for i in range(1, len(laps) + 1):
            # Detect stint boundary: compound change OR a pit stop occurred in the gap
            compound_change = (i < len(laps) and tyres[i] != stint_tyre)
            pit_in_gap = False
            if i < len(laps) and laps[i] - laps[i - 1] > 1:
                # Check if any lap in the gap was an actual pit stop
                for gap_lap in range(laps[i - 1], laps[i] + 1):
                    if gap_lap in pit_laps:
                        pit_in_gap = True
                        break
            is_boundary = (i == len(laps)) or compound_change or pit_in_gap
            if is_boundary:
                end_idx = i - 1
                start_lap = laps[stint_start_idx]
                end_lap = laps[end_idx]
                
                colour = _TYRE_COLOURS.get(stint_tyre, "#666666")
                ax.axvspan(
                    start_lap - 0.5, end_lap + 0.5,
                    color=colour, alpha=0.04, zorder=zorder,
                )
                
                stint_vals = vals[stint_start_idx:end_idx+1]
                if stint_vals:
                    avg_val = sum(stint_vals) / len(stint_vals)
                    ax.hlines(avg_val, start_lap - 0.5, end_lap + 0.5, color=colour, linestyle='--', alpha=0.8, zorder=zorder + 2)
                    
                    tyre_name = get_tyre_compound_str(stint_tyre)
                    if tyre_name:
                        tyre_char = tyre_name[0].upper()
                        if self._y_mode == "gap":
                            stints.append(f"{tyre_char}({_format_delta(avg_val)})")
                        else:
                            stints.append(f"{tyre_char}({_format_laptime(avg_val)})")

                if i < len(laps):
                    stint_start_idx = i
                    stint_tyre = tyres[i]
                    
        return ", ".join(stints)

    # Interactive features

    def _px_to_data_delta(self, dx_px, dy_px):
        """Convert pixel deltas to data-coordinate deltas using the axes transform."""
        inv = self._ax.transData.inverted()
        origin = inv.transform((0, 0))
        moved = inv.transform((dx_px, dy_px))
        return moved[0] - origin[0], moved[1] - origin[1]

    def _on_mouse_move(self, event):
        """Crosshair + tooltip on hover, and pixel-based drag-to-pan."""
        # Guard: ignore events with no valid data coordinates
        if event.xdata is None or event.ydata is None:
            if self._annot and self._annot.get_visible():
                self._annot.set_visible(False)
                if self._crosshair_v:
                    self._crosshair_v.set_visible(False)
                if self._crosshair_h:
                    self._crosshair_h.set_visible(False)
                self._last_crosshair_state = None
                self._canvas.draw_idle()
            return

        if self._is_over_legend(event):
            self._hide_hover()
            return

        # Handle panning using PIXEL deltas (avoids feedback loop)
        if self._pan_press_px is not None:
            dx_px = event.x - self._pan_press_px[0]
            dy_px = event.y - self._pan_press_px[1]
            if not self._pan_active:
                if abs(dx_px) > 5 or abs(dy_px) > 5:
                    self._pan_active = True
                else:
                    return
            if self._pan_active:
                # Convert pixel delta to data delta
                ddx, ddy = self._px_to_data_delta(dx_px, dy_px)
                ox_lo, ox_hi = self._pan_origin_xlim
                oy_lo, oy_hi = self._pan_origin_ylim
                # Subtract because dragging right should move view left
                new_x_lo, new_x_hi = ox_lo - ddx, ox_hi - ddx
                new_y_lo, new_y_hi = oy_lo - ddy, oy_hi - ddy
                # Clamp to home boundaries
                if self._home_xlim:
                    hx_lo, hx_hi = self._home_xlim
                    if new_x_lo < hx_lo:
                        shift = hx_lo - new_x_lo
                        new_x_lo, new_x_hi = new_x_lo + shift, new_x_hi + shift
                    if new_x_hi > hx_hi:
                        shift = new_x_hi - hx_hi
                        new_x_lo, new_x_hi = new_x_lo - shift, new_x_hi - shift
                if hasattr(self, '_max_ylim'):
                    hy_lo, hy_hi = self._max_ylim
                    if new_y_lo < hy_lo:
                        shift = hy_lo - new_y_lo
                        new_y_lo, new_y_hi = new_y_lo + shift, new_y_hi + shift
                    if new_y_hi > hy_hi:
                        shift = new_y_hi - hy_hi
                        new_y_lo, new_y_hi = new_y_lo - shift, new_y_hi - shift
                self._ax.set_xlim(new_x_lo, new_x_hi)
                self._ax.set_ylim(new_y_lo, new_y_hi)
                self._set_user_view((new_x_lo, new_x_hi), (new_y_lo, new_y_hi))
                self._pan_active = True
                self._canvas.draw_idle()
                return


        if not event.inaxes or self._annot is None:
            if self._annot and self._annot.get_visible():
                self._annot.set_visible(False)
                if self._crosshair_v:
                    self._crosshair_v.set_visible(False)
                if self._crosshair_h:
                    self._crosshair_h.set_visible(False)
                self._canvas.draw_idle()
            return

        # Find nearest data point
        best_dist_px2 = float("inf")
        best_info = None

        focus = self._focused_drivers
        visible_data = getattr(self, '_cached_visible_data', None)
        if not visible_data:
            return

        pit_threshold = getattr(self, '_cached_pit_threshold', float('inf'))
        leader_refs = getattr(self, '_cached_leader_refs', {})
        official_gap_laps = getattr(self, '_cached_official_gap_laps', set())
        terminal_no_time_points = getattr(self, '_cached_terminal_no_time_points', [])

        for code, entries in visible_data.items():
            is_focused_drv = (not focus) or (code in focus)
            session_best_val = getattr(self, '_cached_session_best', float('inf'))
            
            if not is_focused_drv:
                # For non-focused drivers, only check their session-best lap
                entries = [e for e in entries if e["time_s"] == session_best_val]
                if not entries:
                    continue
            for e in entries:
                if self._pure_pace_cb.isChecked() and (
                    _entry_is_pit(e, pit_threshold)
                    or _entry_is_out_lap(e)
                    or _entry_is_outlier(e, pit_threshold)
                    or e["lap"] in getattr(self, '_cached_sc_vsc_laps', set())
                ):
                    continue
                lap = e["lap"]
                if self._y_mode == "gap":
                    val, gap_is_approx = self._display_gap_meta(e, leader_refs, official_gap_laps, code)
                    if val is None:
                        continue
                else:
                    if e["time_s"] < 0:
                        continue
                    val = e["time_s"]
                    gap_is_approx = False

                px, py = self._ax.transData.transform((lap, val))
                dx_px = px - event.x
                dy_px = py - event.y
                dist_px2 = dx_px * dx_px + dy_px * dy_px
                if dist_px2 < best_dist_px2:
                    best_dist_px2 = dist_px2
                    best_info = {
                        "code": code, "lap": lap,
                        "time_s": e["time_s"], "val": val,
                        "tyre": e.get("tyre", -1),
                        "tyre_life": e.get("tyre_life", 0),
                        "is_approx": self._is_approx_time_entry(e) if self._y_mode == "time" else gap_is_approx,
                        "is_terminal_lap": bool(e.get("is_terminal_lap")),
                        "status": e.get("result_status"),
                    }

        if self._y_mode == "time":
            for point in terminal_no_time_points:
                px, py = self._ax.transData.transform((point["lap"], point["val"]))
                dx_px = px - event.x
                dy_px = py - event.y
                dist_px2 = dx_px * dx_px + dy_px * dy_px
                if dist_px2 < best_dist_px2:
                    best_dist_px2 = dist_px2
                    best_info = {
                        "code": point["code"],
                        "lap": point["lap"],
                        "time_s": -1.0,
                        "val": point["val"],
                        "tyre": -1,
                        "tyre_life": 0,
                        "is_approx": False,
                        "is_terminal_no_time": True,
                        "status": point.get("status", "Retired"),
                    }

        hover_radius_px = 16
        if best_info and best_dist_px2 <= (hover_radius_px * hover_radius_px):
            info = best_info
            colour = self._driver_colors.get(info["code"], _DEFAULT_COLOUR)
            tyre_name = get_tyre_compound_str(info["tyre"])

            leader_ref = leader_refs.get(info["lap"])
            if self._y_mode == "gap":
                val_str = _format_delta(info['val'])
            else:
                val_str = _format_laptime(info["time_s"])
            if info.get("is_approx"):
                val_str += " (approx)"
                
            tyre_life_str = f", {int(info['tyre_life'])} Laps Old" if info.get('tyre_life') else ""

            # Check if this is a session best or personal best lap
            session_best = getattr(self, '_cached_session_best', float('inf'))
            is_session_best = (info['time_s'] == session_best)
            
            personal_best = getattr(
                self, '_cached_driver_personal_bests', {}
            ).get(info['code'], float('inf'))
            is_personal_best = (info['time_s'] == personal_best and not is_session_best)
            
            badge = ""
            if is_session_best:
                badge = "  (Session Best Lap Time)"
            elif is_personal_best:
                badge = "  (Personal Best Lap Time)"

            extra_lines = []
            if (
                self._y_mode == "absolute"
                and is_personal_best
                and personal_best < float('inf')
                and session_best < float('inf')
            ):
                pb_gap = personal_best - session_best
                extra_lines.append(f"Gap to SB: {_format_delta(pb_gap)}")

            if self._y_mode == "gap" and leader_ref is not None:
                extra_lines.append(
                    f"Race leader: {leader_ref['code']}"
                )
            if info.get("is_terminal_lap") and info.get("status"):
                extra_lines.append(info["status"])

            if info.get("is_terminal_no_time"):
                text = (
                    f"{info['code']}  Lap {info['lap']}\n"
                    f"Lap time not available\n"
                    f"({info.get('status', 'Retired')})"
                )
            elif self._y_mode == "gap":
                text = (
                    f"{info['code']}  Lap {info['lap']}{badge}\n"
                    f"Gap: {val_str}\n"
                    f"({tyre_name}{tyre_life_str})"
                )
            else:
                text = (
                    f"{info['code']}  Lap {info['lap']}{badge}\n"
                    f"{val_str}  ({tyre_name}{tyre_life_str})"
                )
            if extra_lines:
                text += "\n" + "\n".join(extra_lines)

            # Only redraw if crosshair state actually changed (debounce)
            new_state = (info["code"], info["lap"])
            if new_state == self._last_crosshair_state:
                return
            self._last_crosshair_state = new_state

            self._annot.xy = (info["lap"], info["val"])
            self._annot.set_text(text)
            self._annot.get_bbox_patch().set_edgecolor(colour)

            # Smart offset: place the tooltip, then clamp it back inside the axes
            x_lo, x_hi = self._ax.get_xlim()
            y_lo, y_hi = self._ax.get_ylim()
            x_frac = (info["lap"] - x_lo) / max(x_hi - x_lo, 1)
            y_frac = (info["val"] - y_lo) / max(y_hi - y_lo, 1)
            self._annot.set_visible(True)
            off_x = -140 if x_frac > 0.72 else 15
            off_y = -35 if y_frac > 0.85 else 15
            self._annot.xyann = (off_x, off_y)

            try:
                renderer = self._canvas.renderer
                axes_bbox = self._ax.get_window_extent(renderer)
                annot_bbox = self._annot.get_window_extent(renderer)
                pad = 8

                if annot_bbox.x1 > axes_bbox.x1 - pad:
                    off_x -= (annot_bbox.x1 - (axes_bbox.x1 - pad))
                if annot_bbox.x0 < axes_bbox.x0 + pad:
                    off_x += ((axes_bbox.x0 + pad) - annot_bbox.x0)
                if annot_bbox.y1 > axes_bbox.y1 - pad:
                    off_y -= (annot_bbox.y1 - (axes_bbox.y1 - pad))
                if annot_bbox.y0 < axes_bbox.y0 + pad:
                    off_y += ((axes_bbox.y0 + pad) - annot_bbox.y0)

                self._annot.xyann = (off_x, off_y)
            except Exception:
                pass

            if self._crosshair_v:
                self._crosshair_v.set_xdata([info["lap"]])
                self._crosshair_v.set_visible(True)
            if self._crosshair_h:
                self._crosshair_h.set_ydata([info["val"]])
                self._crosshair_h.set_visible(True)

            self._canvas.draw_idle()
        else:
            if self._annot.get_visible():
                self._hide_hover()

    def _is_over_legend(self, event):
        legend = getattr(self, "_legend_artist", None)
        if legend is None:
            return False
        try:
            bbox = legend.get_window_extent(self._canvas.renderer)
        except Exception:
            return False
        return bbox.contains(event.x, event.y)

    def _hide_hover(self):
        if self._annot:
            self._annot.set_visible(False)
        if self._crosshair_v:
            self._crosshair_v.set_visible(False)
        if self._crosshair_h:
            self._crosshair_h.set_visible(False)
        self._last_crosshair_state = None
        self._canvas.draw_idle()

    def _on_scroll(self, event):
        """Scroll to zoom, centered on cursor position."""
        if not event.inaxes:
            return
        scale_factor = 0.85 if event.button == "up" else 1.15
        self._push_undo_state()
        self._apply_zoom(scale_factor, event.xdata, event.ydata, zoom_x=True, zoom_y=True)

    def _apply_zoom(self, scale_factor, cx, cy, zoom_x=True, zoom_y=True):
        """Apply zoom centered on (cx, cy) with strict clamping."""
        ax = self._ax
        x_lo, x_hi = ax.get_xlim()
        y_lo, y_hi = ax.get_ylim()

        if zoom_x:
            new_x_lo = cx - (cx - x_lo) * scale_factor
            new_x_hi = cx + (x_hi - cx) * scale_factor
        else:
            new_x_lo, new_x_hi = x_lo, x_hi

        if zoom_y:
            new_y_lo = cy - (cy - y_lo) * scale_factor
            new_y_hi = cy + (y_hi - cy) * scale_factor
        else:
            new_y_lo, new_y_hi = y_lo, y_hi

        # Minimum zoom: 3 laps wide, 1.5 seconds tall
        if zoom_x and (new_x_hi - new_x_lo) < 3:
            return
        if zoom_y and self._y_mode == "absolute" and (new_y_hi - new_y_lo) < 1.5:
            return
        if zoom_y and self._y_mode == "gap" and (new_y_hi - new_y_lo) < 0.5:
            return

        # Maximum zoom out: strictly clamp to home, no overshoot
        if zoom_x and self._home_xlim:
            hx_lo, hx_hi = self._home_xlim
            home_xspan = hx_hi - hx_lo
            if (new_x_hi - new_x_lo) >= home_xspan:
                new_x_lo, new_x_hi = hx_lo, hx_hi
            else:
                # Keep view within home bounds
                if new_x_lo < hx_lo:
                    new_x_lo, new_x_hi = hx_lo, hx_lo + (new_x_hi - new_x_lo)
                if new_x_hi > hx_hi:
                    new_x_lo, new_x_hi = hx_hi - (new_x_hi - new_x_lo), hx_hi
        if zoom_y and hasattr(self, '_max_ylim'):
            hy_lo, hy_hi = self._max_ylim
            home_yspan = hy_hi - hy_lo
            if (new_y_hi - new_y_lo) >= home_yspan:
                new_y_lo, new_y_hi = hy_lo, hy_hi
            else:
                if new_y_lo < hy_lo:
                    new_y_lo, new_y_hi = hy_lo, hy_lo + (new_y_hi - new_y_lo)
                if new_y_hi > hy_hi:
                    new_y_lo, new_y_hi = hy_hi - (new_y_hi - new_y_lo), hy_hi

        ax.set_xlim(new_x_lo, new_x_hi)
        ax.set_ylim(new_y_lo, new_y_hi)
        self._set_user_view((new_x_lo, new_x_hi), (new_y_lo, new_y_hi))
        self._canvas.draw_idle()

    def _on_button_press(self, event):
        """Left-click starts pan; double-left-click resets view."""
        if event.xdata is None or event.ydata is None:
            return
        if event.button == 1:
            if event.dblclick:
                self._push_undo_state()
                self._pan_press_px = None
                self._pan_active = False
                self._user_xlim = None
                self._user_ylim = None
                self._view_state_by_mode.pop(self._y_mode, None)
                self._redraw()
            else:
                self._push_undo_state()
                self._pan_press_px = (event.x, event.y)
                self._pan_origin_xlim = self._ax.get_xlim()
                self._pan_origin_ylim = self._ax.get_ylim()
                self._pan_active = True

    def _on_button_release(self, event):
        """End pan on left-click release."""
        if event.button == 1:
            self._pan_press_px = None
            self._pan_active = False

    def _on_pick(self, event):
        """Toggle isolation when clicking a driver's legend."""
        if getattr(event.mouseevent, 'button', None) != 1:
            return  # Only left clicks
        if self._pan_active:
            return  # Don't trigger clicks while dragging

        artist = event.artist
        # We only allow picking on the legend now to avoid accidental line clicks
        if artist in getattr(self, '_legend_map', {}):
            code = self._legend_map[artist]
            
            # Toggle isolation
            if code in self._focused_drivers:
                self._focused_drivers.remove(code)
                if not self._focused_drivers:
                    self._driver_combo.setCurrentText("All Drivers")
                elif len(self._focused_drivers) == 1:
                    self._driver_combo.setCurrentText(list(self._focused_drivers)[0])
                else:
                    self._driver_combo.setCurrentText("Multiple Drivers")
            else:
                self._focused_drivers.add(code)
                if len(self._focused_drivers) == 1:
                    self._driver_combo.setCurrentText(code)
                else:
                    self._driver_combo.setCurrentText("Multiple Drivers")
            
            self._needs_full_redraw = True
            self._redraw()

    def eventFilter(self, obj, event):
        """Handle Qt pinch gesture for trackpad zoom."""
        if event.type() == QEvent.Type.KeyPress:
            if self._handle_ui_key_event(event):
                return True
        if event.type() == QEvent.Type.Gesture:
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if pinch:
                scale = pinch.scaleFactor()
                if scale != 1.0:
                    # Convert pinch to zoom: spread out = zoom in
                    center = pinch.centerPoint()
                    # Map widget coords to axes data coords
                    pos = self._canvas.mapFromGlobal(center.toPoint())
                    inv = self._ax.transData.inverted()
                    
                    # Handle Retina / high-DPI scaling
                    ratio = self._canvas.devicePixelRatio()
                    px_x = pos.x() * ratio
                    px_y = (self._canvas.height() - pos.y()) * ratio
                    
                    cx, cy = inv.transform((px_x, px_y))
                    
                    # Invert: scale > 1 = spread = zoom in = shrink factor
                    zoom_factor = 1.0 / scale
                    self._apply_zoom(zoom_factor, cx, cy)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if self._handle_ui_key_event(event):
            return
        super().keyPressEvent(event)

    def _handle_ui_key_event(self, event):
        key = event.key()
        if key == Qt.Key.Key_H:
            self._toggle_help()
            event.accept()
            return True
        if key == Qt.Key.Key_I:
            self._legend_visible = not self._legend_visible
            self._needs_full_redraw = True
            self._redraw()
            event.accept()
            return True
        return False

    def on_connection_status_changed(self, status):
        if status != "Connected":
            self._lap_status.setText(status)
            self._status_sep.setText("")
            self._time_status.setText("")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lap Time Evolution")
    window = LapTimeChartWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
