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
import time

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backend_bases import MouseEvent

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QCheckBox
)
from PySide6.QtGui import QFont, QFontMetrics, QCursor
from PySide6.QtCore import Qt, QEvent, QTimer
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
_YMODE_TIME = "absolute"
_YMODE_GAP = "gap"


def _hex_to_rgb01(colour):
    colour = str(colour or "").strip()
    if not colour.startswith("#") or len(colour) != 7:
        return None
    try:
        return tuple(int(colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    except ValueError:
        return None


def _rgb01_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(
        int(max(0.0, min(1.0, rgb[0])) * 255.0),
        int(max(0.0, min(1.0, rgb[1])) * 255.0),
        int(max(0.0, min(1.0, rgb[2])) * 255.0),
    )


def _srgb_to_linear(channel):
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb):
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg_hex, bg_hex):
    fg_rgb = _hex_to_rgb01(fg_hex)
    bg_rgb = _hex_to_rgb01(bg_hex)
    if fg_rgb is None or bg_rgb is None:
        return 1.0
    fg_l = _relative_luminance(fg_rgb)
    bg_l = _relative_luminance(bg_rgb)
    lighter = max(fg_l, bg_l)
    darker = min(fg_l, bg_l)
    return (lighter + 0.05) / (darker + 0.05)


def _mix_rgb(rgb_a, rgb_b, amount):
    return tuple(
        (1.0 - amount) * a + amount * b
        for a, b in zip(rgb_a, rgb_b)
    )


def _display_safe_colour(colour, bg_colour=_BG, min_contrast=3.2):
    if _contrast_ratio(colour, bg_colour) >= min_contrast:
        return colour

    rgb = _hex_to_rgb01(colour)
    if rgb is None:
        return colour

    white = (1.0, 1.0, 1.0)
    lo, hi = 0.0, 1.0
    best = white
    for _ in range(16):
        mid = (lo + hi) / 2.0
        candidate = _mix_rgb(rgb, white, mid)
        candidate_hex = _rgb01_to_hex(candidate)
        if _contrast_ratio(candidate_hex, bg_colour) >= min_contrast:
            best = candidate
            hi = mid
        else:
            lo = mid
    return _rgb01_to_hex(best)


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


def _entry_is_pit_entry(entry):
    return bool(entry.get("is_pit_entry"))


def _entry_is_pit_affected(entry, pit_threshold):
    explicit = entry.get("is_pit_affected")
    if explicit is not None:
        return bool(explicit)
    legacy = entry.get("is_pit")
    if legacy is not None:
        return bool(legacy)
    return entry.get("time_s", -1) > pit_threshold and entry.get("lap", 0) > 1


def _entry_is_out_lap(entry):
    return bool(entry.get("is_out_lap"))


def _entry_is_outlier(entry, pit_threshold):
    explicit = entry.get("is_outlier")
    if explicit is not None:
        return bool(explicit)
    return (
        entry.get("time_s", -1) > pit_threshold
        and not _entry_is_pit_affected(entry, pit_threshold)
        and not _entry_is_out_lap(entry)
    )


def _is_clean_timed_entry(entry, pit_threshold, sc_vsc_laps):
    if not entry:
        return False
    return (
        0 < entry.get("time_s", -1) <= pit_threshold
        and entry.get("lap") not in sc_vsc_laps
        and not _entry_is_pit_affected(entry, pit_threshold)
        and not _entry_is_out_lap(entry)
        and not _entry_is_outlier(entry, pit_threshold)
    )


def _entry_has_gap_discontinuity(entry, pit_threshold, sc_vsc_laps):
    if not entry:
        return False
    lap = entry.get("lap")
    return (
        _entry_is_pit_affected(entry, pit_threshold)
        or _entry_is_out_lap(entry)
        or _entry_is_outlier(entry, pit_threshold)
        or (lap in sc_vsc_laps if lap is not None else False)
    )


def _terminal_status_display_text(status):
    status_text = str(status or "").strip()
    if not status_text or status_text.lower() == "retired":
        return "Retired (DNF)"
    return status_text


class _OverlayBlitManager:
    """Manage a tiny animated overlay layer for hover crosshair and tooltip."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.enabled = bool(getattr(canvas, "supports_blit", False))
        self._artists = []
        self._background = None
        self._cid = canvas.mpl_connect("draw_event", self._on_draw)

    def set_artists(self, artists):
        self._artists = [artist for artist in artists if artist is not None]
        if self.enabled:
            for artist in self._artists:
                artist.set_animated(True)

    def reset(self):
        self._background = None

    def _on_draw(self, event):
        if not self.enabled:
            return
        try:
            self._background = self.canvas.copy_from_bbox(self.canvas.figure.bbox)
            self._draw_artists()
            self.canvas.blit(self.canvas.figure.bbox)
        except Exception:
            self._background = None

    def _draw_artists(self):
        fig = self.canvas.figure
        for artist in self._artists:
            if artist is not None and artist.get_visible():
                fig.draw_artist(artist)

    def update(self):
        if not self.enabled or self._background is None:
            return False
        try:
            self.canvas.restore_region(self._background)
            self._draw_artists()
            self.canvas.blit(self.canvas.figure.bbox)
            return True
        except Exception:
            self._background = None
            return False


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
        self._current_time_s = None
        self._last_drawn_lap = 0
        self._needs_full_redraw = True
        self._focused_drivers = set()   # set of codes
        self._y_mode = _YMODE_TIME
        self._has_ever_drawn = False    # True after first successful redraw
        self._legend_visible = True
        self._legend_artist = None
        self._legend_map = {}
        self._legend_line_by_code = {}
        self._legend_text_by_code = {}
        self._legend_line_style_by_code = {}
        self._legend_text_style_by_code = {}
        self._legend_bbox = None
        self._legend_hitboxes = []
        self._plot_line_by_code = {}
        self._plot_line_style_by_code = {}
        self._hover_legend_code = None
        self._use_native_pinch_zoom = False
        self._cached_hover_screen_points = []

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
        self._last_zoom_ts = 0.0
        self._last_pan_draw_ts = 0.0
        self._last_interaction_ts = 0.0
        self._pending_live_redraw = False
        # Crosshair debounce
        self._last_crosshair_state = None
        self._hover_point_key = None
        self._last_rendered_visibility_signature = ()
        self._chart_dirty = False
        self._render_in_flight = False
        self._last_render_monotonic = 0.0
        self._latest_stream_version = 0
        self._last_rendered_stream_version = 0
        self._resize_active = False
        self._resize_started_monotonic = None
        self._hover_cache_dirty = False
        self._debug_perf_enabled = False
        self._perf_stats = {
            "full_redraw_count": 0,
            "coalesced_live_updates": 0,
            "redraw_durations_ms": [],
            "resize_freeze_ms": 0.0,
        }
        self._overlay_blit = None

        super().__init__()

        self._deferred_redraw_timer = QTimer(self)
        self._deferred_redraw_timer.setSingleShot(True)
        self._deferred_redraw_timer.timeout.connect(self._flush_deferred_redraw)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._flush_live_render)
        self._resize_refresh_timer = QTimer(self)
        self._resize_refresh_timer.setSingleShot(True)
        self._resize_refresh_timer.timeout.connect(self._refresh_after_resize)
        self._view_refresh_timer = QTimer(self)
        self._view_refresh_timer.setSingleShot(True)
        self._view_refresh_timer.timeout.connect(self._refresh_after_view_change)

        self.setWindowTitle("F1 Race Replay - Lap Time & Gap Evolution")
        self.setGeometry(120, 120, 1000, 600)
        
        self.status_bar.setStyleSheet("""
            QStatusBar {
                border-top: 1px solid #6A6A6A;
            }
            QStatusBar::item {
                border: none;
            }
        """)

    def _terminal_entry_visibility_time_s(self, entry):
        if not entry or not entry.get("is_terminal_lap"):
            return None
        for key in (
            "terminal_event_time_s",
            "replay_line_time_s",
            "replay_end_time_s",
            "line_time_s",
            "end_time_s",
        ):
            value = entry.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _entry_completion_visibility_time_s(self, entry):
        if not entry or entry.get("is_terminal_lap"):
            return None
        for key in ("replay_line_time_s", "replay_end_time_s"):
            value = entry.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        if entry.get("time_source") == "frame_backfill" or entry.get("source") == "derived":
            for key in ("line_time_s", "end_time_s"):
                value = entry.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        return None

    def _is_normal_entry_visible(self, entry):
        if not entry or entry.get("is_terminal_lap"):
            return False
        visible_at_s = self._entry_completion_visibility_time_s(entry)
        if visible_at_s is not None and isinstance(self._current_time_s, (int, float)):
            return self._current_time_s >= visible_at_s
        lap = entry.get("lap")
        if isinstance(lap, (int, float)):
            lap_int = int(lap)
            if self._total_laps and lap_int >= int(self._total_laps):
                return False
            return self._leader_lap > lap_int
        return False

    def _is_terminal_entry_visible(self, entry, include_final=False):
        if not entry or not entry.get("is_terminal_lap"):
            return False
        visible_at_s = self._terminal_entry_visibility_time_s(entry)
        if visible_at_s is not None and isinstance(self._current_time_s, (int, float)):
            return self._current_time_s >= visible_at_s
        lap = entry.get("lap")
        if isinstance(lap, (int, float)):
            return self._leader_lap > int(lap)
        return False

    def _visible_entry_signature(self):
        if not self._lap_times:
            return ()
        visible = []
        for code, entries in self._lap_times.items():
            for entry in entries:
                if entry.get("is_terminal_lap"):
                    if self._is_terminal_entry_visible(entry, include_final=False):
                        visible.append((code, int(entry.get("lap", -1)), "terminal"))
                elif self._is_normal_entry_visible(entry):
                    visible.append((code, int(entry.get("lap", -1)), "lap"))
        return tuple(sorted(visible))
        

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()
        if getattr(self, "_has_ever_drawn", False):
            if not self._resize_active:
                self._resize_active = True
                self._resize_started_monotonic = time.monotonic()
            self._view_refresh_timer.stop()
            self._resize_refresh_timer.start(140)

    def _reposition_overlays(self):
        """Keep the help overlay centered."""
        if hasattr(self, '_help_overlay') and self._help_overlay:
            hx = (self._canvas.width() - self._help_overlay.width()) // 2
            hy = (self._canvas.height() - self._help_overlay.height()) // 2
            self._help_overlay.move(max(0, hx), max(0, hy))

    def _refresh_after_resize(self):
        if not hasattr(self, "_canvas") or not getattr(self, "_has_ever_drawn", False):
            return
        if self._resize_active and self._resize_started_monotonic is not None:
            self._perf_stats["resize_freeze_ms"] += (time.monotonic() - self._resize_started_monotonic) * 1000.0
        self._resize_active = False
        self._resize_started_monotonic = None
        self._overlay_reset()
        self._mark_chart_dirty()
        self._request_live_render(immediate=True)

    def _refresh_after_view_change(self):
        if self._resize_active or not getattr(self, "_has_ever_drawn", False):
            return
        self._hover_cache_dirty = False
        self._rebuild_hover_screen_cache()
        self._refresh_hover_from_cursor()

    def _invalidate_hover_screen_cache(self, refresh_delay_ms=80):
        self._hover_cache_dirty = True
        self._view_refresh_timer.start(refresh_delay_ms)

    def _overlay_reset(self):
        if self._overlay_blit is not None:
            self._overlay_blit.reset()

    def _overlay_update(self):
        if self._overlay_blit is not None and self._overlay_blit.update():
            return
        self._canvas.draw_idle()

    def _mark_chart_dirty(self):
        self._chart_dirty = True

    def _target_render_interval_ms(self):
        if self._hover_legend_code is not None:
            return 280
        if self._is_interaction_hot():
            return 100
        return 50

    def _request_live_render(self, immediate=False):
        self._mark_chart_dirty()
        if self._resize_active:
            return
        if immediate:
            if self._render_timer.isActive():
                self._render_timer.stop()
            self._flush_live_render()
            return
        interval_ms = self._target_render_interval_ms()
        elapsed_ms = (time.monotonic() - self._last_render_monotonic) * 1000.0 if self._last_render_monotonic else None
        if elapsed_ms is None or elapsed_ms >= interval_ms:
            delay_ms = 0
        else:
            delay_ms = max(0, int(interval_ms - elapsed_ms))
        if self._render_timer.isActive():
            self._perf_stats["coalesced_live_updates"] += 1
            return
        self._render_timer.start(delay_ms)

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

    def _display_gap_meta(self, entry, leader_refs=None, code=None):
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

        if code is not None and (code, entry.get("lap")) in getattr(self, "_cached_gap_suppressed_laps", set()):
            return None, False

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

    def _is_time_mode(self):
        return self._y_mode == _YMODE_TIME

    def _is_gap_mode(self):
        return self._y_mode == _YMODE_GAP

    def _display_gap_value(self, entry, leader_refs=None, code=None):
        val, _ = self._display_gap_meta(entry, leader_refs, code)
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

        self._undo_btn = QPushButton("Undo")
        self._undo_btn.setFont(QFont("Arial", 10))
        self._undo_btn.clicked.connect(self._undo_view)
        ctrl.addWidget(self._undo_btn)

        self._redo_btn = QPushButton("Redo")
        self._redo_btn.setFont(QFont("Arial", 10))
        self._redo_btn.clicked.connect(self._redo_view)
        ctrl.addWidget(self._redo_btn)

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setFont(QFont("Arial", 10))
        self._reset_btn.clicked.connect(self._reset_view)
        ctrl.addWidget(self._reset_btn)

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
        self._canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._canvas.setSizePolicy(
            self._canvas.sizePolicy().horizontalPolicy(),
            self._canvas.sizePolicy().verticalPolicy(),
        )
        self._overlay_blit = _OverlayBlitManager(self._canvas)
        root.addWidget(self._canvas, stretch=1)

        # Connect mouse events: crosshair, legend/line pick, drag-pan
        self._canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self._canvas.mpl_connect("pick_event", self._on_pick)
        self._canvas.mpl_connect("button_press_event", self._on_button_press)
        self._canvas.mpl_connect("button_release_event", self._on_button_release)

        app = QApplication.instance()
        platform_name = (app.platformName().lower() if app is not None else "")
        self._use_native_pinch_zoom = platform_name in {"cocoa", "wayland"}
        if not self._use_native_pinch_zoom:
            self._canvas.grabGesture(Qt.GestureType.PinchGesture)
        self._canvas.installEventFilter(self)

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
            "<h3>🏎️ Lap Time & Gap Evolution</h3>"
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
            "<li><b>Scroll / Pinch:</b> Zoom at the cursor</li>"
            "<li><b>Left-Click & Drag:</b> Pan the chart</li>"
            "<li><b>Arrow Keys:</b> Pan the view after clicking the chart</li>"
            "<li><b>Undo / Redo:</b> Step backward or forward through chart views</li>"
            "<li><b>Double-Click:</b> Return to the default view</li>"
            "<li><b>Click Legend:</b> Click a driver line or label to toggle isolation</li>"
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
        ax.set_xscale("linear")
        ax.set_yscale("linear")
        ax.set_facecolor(_BG)
        ax.set_xlabel("Lap", color=_TEXT, fontsize=10)
        if self._is_gap_mode():
            ax.set_ylabel("Gap to Leader (s)", color=_TEXT, fontsize=10)
        else:
            ax.set_ylabel("Lap Time", color=_TEXT, fontsize=10)
        ax.tick_params(colors=_TEXT, labelsize=9)
        if self._is_time_mode():
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(_format_laptime))
        else:
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(_format_delta))
        ax.grid(True, color=_GRID, alpha=0.5, linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_edgecolor("#555555")

    # Telemetry handling

    def on_telemetry_data(self, data):
        self._latest_stream_version += 1
        frame = data.get("frame")
        if not frame:
            return

        drivers = frame.get("drivers", {})
        if not drivers:
            return

        # Capture colours
        colors = data.get("driver_colors", {})
        if colors:
            self._driver_colors = {
                code: _display_safe_colour(hex_colour)
                for code, hex_colour in colors.items()
            }

        # Capture session info
        sd = data.get("session_data", {})
        if sd:
            tl = sd.get("total_laps", 0)
            if tl:
                self._total_laps = int(tl)
                self._reserve_status_width()
            new_time_s = sd.get("time_s", self._current_time_s)
            if isinstance(new_time_s, (int, float)):
                self._current_time_s = float(new_time_s)
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
            self._last_rendered_visibility_signature = ()

        # Ingest pre-computed data from server
        if "lap_times" in data:
            server_lap_times = data.get("lap_times")
            # Only flag for redraw if data actually changed
            if server_lap_times is not self._lap_times:
                self._lap_times = server_lap_times
                if not self._has_ever_drawn:
                    self._needs_full_redraw = True

        if "status_laps" in data:
            self._status_laps = data.get("status_laps") or []

        # Update driver list
        self._refresh_driver_list(drivers)

        visible_entries_changed = (
            self._visible_entry_signature() != self._last_rendered_visibility_signature
        )

        # Redraw when leader crosses a new lap, terminal state becomes visible,
        # or the chart needs a full rebuild.
        if self._leader_lap > self._last_drawn_lap or self._needs_full_redraw or visible_entries_changed:
            self._last_drawn_lap = self._leader_lap
            force_redraw = self._needs_full_redraw
            self._needs_full_redraw = False
            if not self._has_ever_drawn:
                self._pending_live_redraw = False
                self._redraw_now()
            elif force_redraw and not self._resize_active:
                self._pending_live_redraw = False
                self._request_live_render(immediate=True)
            else:
                self._pending_live_redraw = True
                self._request_live_render(immediate=False)

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
        self._redraw_now()

    def _on_ymode_changed(self, index):
        self._push_undo_state()
        self._save_view_state()
        self._y_mode = _YMODE_TIME if index == 0 else _YMODE_GAP
        self._restore_view_state()
        self._needs_full_redraw = True
        self._redraw_now()

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
            self._ymode_combo.setCurrentIndex(0 if mode == _YMODE_TIME else 1)
            self._ymode_combo.blockSignals(False)
            self._user_xlim = tuple(snapshot["xlim"])
            self._user_ylim = tuple(snapshot["ylim"])
            self._needs_full_redraw = True
            self._redraw_now()
            self._update_history_buttons()
            return
        self._ax.set_xlim(snapshot["xlim"])
        self._ax.set_ylim(snapshot["ylim"])
        self._set_user_view(snapshot["xlim"], snapshot["ylim"])
        self._overlay_reset()
        self._invalidate_hover_screen_cache(refresh_delay_ms=30)
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

    def _on_pure_pace_toggled(self, state):
        self._needs_full_redraw = True
        self._redraw_now()

    def _redraw_now(self):
        started = time.monotonic()
        self._render_in_flight = True
        try:
            self._redraw()
            self._chart_dirty = False
            self._last_rendered_stream_version = self._latest_stream_version
        finally:
            elapsed_ms = (time.monotonic() - started) * 1000.0
            self._last_render_monotonic = time.monotonic()
            self._render_in_flight = False
            self._perf_stats["full_redraw_count"] += 1
            self._perf_stats["redraw_durations_ms"].append(elapsed_ms)
            if len(self._perf_stats["redraw_durations_ms"]) > 120:
                self._perf_stats["redraw_durations_ms"] = self._perf_stats["redraw_durations_ms"][-120:]

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
        self._pending_live_redraw = False
        self._overlay_reset()
        previous_hover_legend_code = self._hover_legend_code
        previous_hover_point_key = self._hover_point_key
        ax.clear()
        self._setup_axes(ax)
        self._annot = None
        self._legend_artist = None
        self._legend_map = {}
        self._legend_line_by_code = {}
        self._legend_text_by_code = {}
        self._legend_line_style_by_code = {}
        self._legend_text_style_by_code = {}
        self._legend_bbox = None
        self._legend_hitboxes = []
        self._plot_line_by_code = {}
        self._plot_line_style_by_code = {}
        self._hover_legend_code = None

        if not self._lap_times:
            self._canvas.draw_idle()
            return

        focus = self._focused_drivers

        # Show each driver's laps only once that driver actually completes them.
        # Terminal no-time laps remain special event markers and become visible
        # once the replay has reached their event timestamp.
        visible_data = {}
        for code, entries in self._lap_times.items():
            visible = []
            for entry in entries:
                if entry.get("is_terminal_lap"):
                    if self._is_terminal_entry_visible(entry, include_final=False):
                        visible.append(entry)
                elif self._is_normal_entry_visible(entry):
                    visible.append(entry)
            if visible:
                visible_data[code] = visible

        if not visible_data:
            self._canvas.draw_idle()
            return

        completed_lap_cutoff = max(
            (
                int(entry["lap"])
                for entries in visible_data.values()
                for entry in entries
                if not entry.get("is_terminal_lap")
            ),
            default=0,
        )

        pure_pace = self._pure_pace_cb.isChecked()
        # Gap mode should stay completed-lap based for rendering, but the
        # fallback/interpolation math can safely use the full session-known
        # lap set as anchor points. This prevents completed laps from popping
        # in late simply because their next official anchor is only revealed
        # on the chart one replay lap later.
        gap_source_data = {}
        for code, entries in self._lap_times.items():
            source_entries = [
                e for e in entries
                if not e.get("is_terminal_lap")
            ]
            if source_entries:
                gap_source_data[code] = source_entries
        sc_vsc_laps = set()
        
        # ── 1. Safety Car / VSC shaded zones ──
        # Merge overlapping/adjacent periods into unified visual spans
        # to prevent label overlap (e.g. VSC → SC on consecutive laps).
        merged_zones = []
        for sp in self._status_laps:
            if sp["start_lap"] > completed_lap_cutoff:
                continue
            end_lap = min(sp["end_lap"], completed_lap_cutoff)
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
            for code, entries in gap_source_data.items()
        }
        leader_refs = {}
        if self._is_gap_mode():
            for lap in sorted({e["lap"] for entries in gap_source_data.values() for e in entries}):
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
        gap_suppressed_laps = set()
        if self._is_gap_mode():
            for code, entries in gap_source_data.items():
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
                            "official_gap": float(official_val),
                            "offset": float(official_val) - float(raw_val),
                        })

                if not anchors:
                    continue

                for entry in sorted_entries:
                    lap = entry["lap"]
                    has_official = (
                        self._official_gap_to_leader_s(entry) is not None
                        or self._official_finish_gap_s(entry) is not None
                    )
                    if has_official:
                        continue
                    raw_val = self._raw_gap_fallback_s(entry, leader_refs)
                    if raw_val is None:
                        continue
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
                    adjusted_val = raw_val + offset
                    bridged_val = None
                    if prev_anchor and next_anchor:
                        span = next_anchor["lap"] - prev_anchor["lap"]
                        if span > 0:
                            t = (lap - prev_anchor["lap"]) / span
                            bridged_val = (
                                prev_anchor["official_gap"]
                                + t * (next_anchor["official_gap"] - prev_anchor["official_gap"])
                            )
                    if (
                        bridged_val is not None
                        and _entry_has_gap_discontinuity(entry, pit_threshold, sc_vsc_laps)
                        and (
                            not np.isfinite(adjusted_val)
                            or adjusted_val < -0.05
                            or abs(adjusted_val - bridged_val) > 45.0
                        )
                    ):
                        adjusted_val = bridged_val
                    if not np.isfinite(adjusted_val) or adjusted_val < -0.05:
                        gap_suppressed_laps.add((code, lap))
                        continue
                    gap_adjustments[(code, lap)] = adjusted_val
            gap_override_threshold = 5.0
            for code, entries in gap_source_data.items():
                sorted_entries = sorted(entries, key=lambda item: item["lap"])
                prev_gap = None
                prev_gap_lap = None
                prev_gap_trustworthy = False
                for entry in sorted_entries:
                    lap = entry["lap"]
                    if (code, lap) in gap_suppressed_laps:
                        prev_gap = None
                        prev_gap_lap = None
                        prev_gap_trustworthy = False
                        continue
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
                        and prev_gap_lap == lap - 1
                        and prev_gap_trustworthy
                        and entry.get("time_s", -1) > 0
                        and leader_time_s is not None
                        and leader_time_s > 0
                    ):
                        predicted = prev_gap + float(entry["time_s"]) - float(leader_time_s)
                        if (
                            predicted >= -0.05
                            and
                            abs(float(official_val) - predicted) > gap_override_threshold
                            and (
                                _entry_is_pit_affected(entry, pit_threshold)
                                or _entry_is_out_lap(entry)
                                or _entry_is_outlier(entry, pit_threshold)
                            )
                        ):
                            gap_overrides[(code, lap)] = predicted
                            display_val = predicted

                    if display_val is not None:
                        prev_gap = float(display_val)
                        prev_gap_lap = lap
                        prev_gap_trustworthy = official_val is not None
                    else:
                        prev_gap = None
                        prev_gap_lap = None
                        prev_gap_trustworthy = False
        # Cache variables for O(1) lookups during high-frequency mouse hover events
        self._cached_pit_threshold = pit_threshold
        self._cached_leader_refs = leader_refs
        self._cached_gap_adjustments = gap_adjustments
        self._cached_gap_overrides = gap_overrides
        self._cached_gap_suppressed_laps = gap_suppressed_laps
        self._cached_terminal_marker_points = []
        self._cached_hover_candidates = []
                        
        for sp in self._status_laps:
            if sp["start_lap"] > completed_lap_cutoff:
                continue
            end_lap = min(sp["end_lap"], completed_lap_cutoff)
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
        driver_stints_text = {}
        pending_pit_markers = []
        focused_hud_rows = min(len(focus), 4) if focus else 0
        pit_marker_y_by_focus_rows = {
            1: 0.88,
            2: 0.83,
            3: 0.78,
            4: 0.73,
        }
        display_y_vals = []
        all_axis_y_vals = []

        session_best = float("inf")
        for code_sb, entries in visible_data.items():
            for e in entries:
                if _is_clean_timed_entry(e, pit_threshold, sc_vsc_laps):
                    if e["time_s"] < session_best:
                        session_best = e["time_s"]
        self._cached_session_best = session_best
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
            pit_laps = []
            all_laps, all_vals, all_markers, all_marker_colours = [], [], [], []
            terminal_marker_entries = []
            
            drv_clean_times = [
                e["time_s"] for e in entries
                if _is_clean_timed_entry(e, pit_threshold, sc_vsc_laps)
            ]
            personal_best = min(drv_clean_times) if drv_clean_times else float("inf")
            self._cached_driver_personal_bests[code] = personal_best

            for e in entries:
                lap = e["lap"]
                raw_time = e["time_s"]
                is_pit_affected = _entry_is_pit_affected(e, pit_threshold)
                is_pit_entry = _entry_is_pit_entry(e)
                is_out_lap = _entry_is_out_lap(e)
                is_outlier = _entry_is_outlier(e, pit_threshold)

                if pure_pace and (lap in sc_vsc_laps or is_pit_affected or is_out_lap or is_outlier):
                    continue

                terminal_generated_entry = bool(e.get("is_terminal_lap") and raw_time < 0)
                gap_is_approx = False
                if self._is_gap_mode():
                    gap_val, gap_is_approx = self._display_gap_meta(e, leader_refs, code)
                    if terminal_generated_entry:
                        terminal_marker_entries.append({
                            "entry": e,
                            "prev_lap": all_laps[-1] if all_laps else None,
                            "prev_val": all_vals[-1] if all_vals else None,
                            "display_val": gap_val,
                        })
                        if is_pit_entry:
                            pit_laps.append(lap)
                        continue
                    val = gap_val
                    if val is None:
                        if is_pit_entry:
                            pit_laps.append(lap)
                        continue
                else:
                    if terminal_generated_entry:
                        terminal_marker_entries.append({
                            "entry": e,
                            "prev_lap": all_laps[-1] if all_laps else None,
                            "prev_val": all_vals[-1] if all_vals else None,
                            "display_val": None,
                        })
                        if is_pit_entry:
                            pit_laps.append(lap)
                        continue
                    if raw_time < 0:
                        if is_pit_entry:
                            pit_laps.append(lap)
                        continue
                    val = raw_time
                    
                all_laps.append(lap)
                all_vals.append(val)
                all_markers.append(_TYRE_MARKERS.get(e.get("tyre", -1), _DEFAULT_MARKER))
                all_marker_colours.append(_TYRE_COLOURS.get(e.get("tyre", -1), colour))

                if is_pit_entry:
                    # Explicit pit stop (In-Lap)
                    pit_laps.append(lap)
                elif is_out_lap or is_outlier:
                    # Just a really slow lap (like a standing start or an Out-Lap).
                    # Ignore it completely so it doesn't squish the Y-axis.
                    pass
                else:
                    clean_laps.append(lap)
                    clean_vals.append(val)
                    clean_time_s.append(raw_time)
                    clean_tyres.append(e.get("tyre", -1))

                if show_detail or e["time_s"] == session_best:
                    self._cached_hover_candidates.append({
                        "code": code,
                        "lap": lap,
                        "time_s": e["time_s"],
                        "val": val,
                        "tyre": e.get("tyre", -1),
                        "tyre_life": e.get("tyre_life", 0),
                        "is_pit_entry": is_pit_entry,
                        "is_approx": self._is_approx_time_entry(e) if self._is_time_mode() else gap_is_approx,
                        "is_terminal_lap": bool(e.get("is_terminal_lap")),
                        "status": e.get("result_status"),
                    })

            # Main pace line
            if all_laps:
                line, = ax.plot(
                    all_laps, all_vals,
                    color=colour, alpha=alpha, linewidth=lw,
                    zorder=zorder,
                    label=code,
                )
                self._plot_line_by_code[code] = line
                self._plot_line_style_by_code[code] = {
                    "alpha": 1.0 if line.get_alpha() is None else float(line.get_alpha()),
                    "linewidth": float(line.get_linewidth()),
                    "zorder": float(line.get_zorder()),
                }
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
                prev_marker_colour = None
                gx, gy = [], []
                for lp, tv, mk, mk_colour in zip(all_laps, all_vals, all_markers, all_marker_colours):
                    if (mk != prev_mk or mk_colour != prev_marker_colour) and gx:
                        ax.scatter(
                            gx, gy, marker=prev_mk,
                            facecolors=prev_marker_colour,
                            alpha=alpha * 0.95,
                            s=22 if show_detail else 6,
                            zorder=zorder + 1, edgecolors=colour, linewidths=0.4 if show_detail else 0.25,
                        )
                        gx, gy = [], []
                    gx.append(lp)
                    gy.append(tv)
                    prev_mk = mk
                    prev_marker_colour = mk_colour
                if gx:
                    ax.scatter(
                        gx, gy, marker=prev_mk,
                        facecolors=prev_marker_colour,
                        alpha=alpha * 0.95,
                        s=22 if show_detail else 6,
                        zorder=zorder + 1, edgecolors=colour, linewidths=0.4 if show_detail else 0.25,
                    )

                # ── 5. Tyre stint background bands (focused driver only) ──
                if show_detail and focus:
                    drv_pit_lap_set = {e["lap"] for e in entries if _entry_is_pit_entry(e)}
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
                pending_pit_markers.append({
                    "code": code,
                    "laps": list(pit_laps),
                    "colour": colour,
                    "zorder": zorder,
                    "y_frac": pit_marker_y_by_focus_rows.get(focused_hud_rows, 0.87),
                })

            if terminal_marker_entries and focus and is_focused and not pure_pace:
                for item in terminal_marker_entries:
                    e = item["entry"]
                    self._cached_terminal_marker_points.append({
                        "code": code,
                        "lap": e["lap"],
                        "colour": colour,
                        "alpha": alpha,
                        "zorder": zorder + 2,
                        "line_width": lw,
                        "prev_lap": item.get("prev_lap"),
                        "prev_val": item.get("prev_val"),
                        "display_val": item.get("display_val"),
                        "tyre": e.get("tyre", -1),
                        "tyre_life": e.get("tyre_life", 0),
                        "status": _terminal_status_display_text(e.get("result_status")),
                        "is_pit_entry": bool(e.get("is_pit_entry")),
                    })

        # ── 4b. HUD Statistics (prepared for drawing at the end) ──
        hud_handles, hud_labels = [], []
        if focus and len(focus) <= 4:
            for code in sorted(focus):
                if code not in visible_data: continue
                # Calculate best lap and avg true pace
                drv_clean_times = [
                    e["time_s"] for e in visible_data[code] 
                    if _is_clean_timed_entry(e, pit_threshold, sc_vsc_laps)
                ]
                # Count actual pit stops (group consecutive in/out laps)
                pit_laps = [e["lap"] for e in visible_data[code] if _entry_is_pit_entry(e)]
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
            if self._is_gap_mode():
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

        if self._cached_terminal_marker_points:
            y_lo, y_hi = ax.get_ylim()
            span = max(y_hi - y_lo, 1.0)
            marker_y = y_hi - span * 0.045
            for point in self._cached_terminal_marker_points:
                draw_val = point.get("display_val")
                if draw_val is None:
                    draw_val = marker_y
                point["val"] = draw_val
                if point.get("prev_lap") is not None and point.get("prev_val") is not None:
                    ax.plot(
                        [point["prev_lap"], point["lap"]],
                        [point["prev_val"], draw_val],
                        color=point["colour"],
                        alpha=min(1.0, point["alpha"] * 0.95),
                        linewidth=max(1.0, point.get("line_width", 1.0)),
                        linestyle="-",
                        zorder=point["zorder"] - 1,
                    )
                ax.scatter(
                    point["lap"], draw_val,
                    marker="o", facecolors=_BG, edgecolors=point["colour"],
                    alpha=point["alpha"], s=46, linewidths=1.4,
                    zorder=point["zorder"],
                )
                self._cached_hover_candidates.append({
                    "code": point["code"],
                    "lap": point["lap"],
                    "time_s": -1.0,
                    "val": draw_val,
                    "tyre": point.get("tyre", -1),
                    "tyre_life": point.get("tyre_life", 0),
                    "is_pit_entry": point.get("is_pit_entry", False),
                    "is_approx": False,
                    "is_terminal_no_time": True,
                    "status": point.get("status", "Retired (DNF)"),
                })

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
                handles, labels,
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
                self._legend_line_by_code[orig_label] = leg_line
                self._legend_line_style_by_code[orig_label] = {
                    "alpha": 1.0 if leg_line.get_alpha() is None else float(leg_line.get_alpha()),
                    "linewidth": float(leg_line.get_linewidth()),
                }
            for leg_text, orig_label in zip(leg.get_texts(), labels):
                leg_text.set_picker(True)
                self._legend_map[leg_text] = orig_label
                self._legend_text_by_code[orig_label] = leg_text
                self._legend_text_style_by_code[orig_label] = {
                    "color": leg_text.get_color(),
                    "fontweight": leg_text.get_fontweight(),
                    "alpha": 1.0 if leg_text.get_alpha() is None else float(leg_text.get_alpha()),
                }
            self._rebuild_legend_hitboxes()
            ax.add_artist(leg)
            if previous_hover_legend_code in self._legend_line_by_code or previous_hover_legend_code in self._legend_text_by_code:
                self._hover_legend_code = previous_hover_legend_code
                self._apply_legend_hover_style(previous_hover_legend_code, active=True)

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
        else:
            hud_leg = None

        if pending_pit_markers:
            for marker_info in pending_pit_markers:
                pit_marker_y_frac = marker_info["y_frac"]
                for pl in marker_info["laps"]:
                    ax.axvline(
                        pl, color=marker_info["colour"], alpha=0.55,
                        linewidth=1.2, linestyle=":",
                        zorder=marker_info["zorder"] - 2,
                    )
                    ax.scatter(
                        pl, pit_marker_y_frac, marker="x",
                        color=marker_info["colour"], alpha=0.9, s=46,
                        zorder=marker_info["zorder"], linewidths=1.8,
                        transform=ax.get_xaxis_transform()
                    )

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
        if self._overlay_blit is not None:
            self._overlay_blit.set_artists([self._annot, self._crosshair_v, self._crosshair_h])


        # Store home limits for zoom clamping
        self._home_xlim = ax.get_xlim()
        self._home_ylim = ax.get_ylim()

        all_v = []
        for vlist in visible_data.values():
            for e in vlist:
                if self._is_gap_mode():
                    val = self._display_gap_value(e, leader_refs)
                    if val is not None:
                        all_v.append(val)
                else:
                    if e["time_s"] < 0:
                        continue
                    all_v.append(e["time_s"])
        
        if all_v:
            y_min_abs, y_max_abs = min(all_v), max(all_v)
            pad_abs = (y_max_abs - y_min_abs) * 0.05
            if self._is_gap_mode():
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

        self._hover_cache_dirty = False
        self._rebuild_hover_screen_cache()
        self._has_ever_drawn = True
        self._last_crosshair_state = None
        self._last_rendered_visibility_signature = self._visible_entry_signature()
        legend_hover_restored = (
            previous_hover_legend_code is not None
            and self._hover_legend_code == previous_hover_legend_code
        )
        if not legend_hover_restored and not self._restore_hover_point(previous_hover_point_key):
            self._refresh_hover_from_cursor()
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
                        if self._is_gap_mode():
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

    def _clamp_view_limits(self, new_x_lo, new_x_hi, new_y_lo, new_y_hi):
        if self._home_xlim:
            hx_lo, hx_hi = self._home_xlim
            if new_x_lo < hx_lo:
                shift = hx_lo - new_x_lo
                new_x_lo, new_x_hi = new_x_lo + shift, new_x_hi + shift
            if new_x_hi > hx_hi:
                shift = new_x_hi - hx_hi
                new_x_lo, new_x_hi = new_x_lo - shift, new_x_hi - shift
        if hasattr(self, "_max_ylim"):
            hy_lo, hy_hi = self._max_ylim
            if new_y_lo < hy_lo:
                shift = hy_lo - new_y_lo
                new_y_lo, new_y_hi = new_y_lo + shift, new_y_hi + shift
            if new_y_hi > hy_hi:
                shift = new_y_hi - hy_hi
                new_y_lo, new_y_hi = new_y_lo - shift, new_y_hi - shift
        return new_x_lo, new_x_hi, new_y_lo, new_y_hi

    def _pan_view_by_fraction(self, frac_x=0.0, frac_y=0.0):
        if not hasattr(self, "_ax"):
            return
        x_lo, x_hi = self._ax.get_xlim()
        y_lo, y_hi = self._ax.get_ylim()
        x_span = x_hi - x_lo
        y_span = y_hi - y_lo
        new_x_lo = x_lo + x_span * frac_x
        new_x_hi = x_hi + x_span * frac_x
        new_y_lo = y_lo + y_span * frac_y
        new_y_hi = y_hi + y_span * frac_y
        new_x_lo, new_x_hi, new_y_lo, new_y_hi = self._clamp_view_limits(
            new_x_lo, new_x_hi, new_y_lo, new_y_hi
        )
        self._ax.set_xlim(new_x_lo, new_x_hi)
        self._ax.set_ylim(new_y_lo, new_y_hi)
        self._set_user_view((new_x_lo, new_x_hi), (new_y_lo, new_y_hi))
        self._mark_interaction_activity()
        self._overlay_reset()
        self._invalidate_hover_screen_cache()
        self._canvas.draw_idle()

    def _reset_view(self):
        self._pan_press_px = None
        self._pan_active = False
        self._last_pan_draw_ts = 0.0
        self._user_xlim = None
        self._user_ylim = None
        self._view_state_by_mode.pop(self._y_mode, None)
        self._canvas.unsetCursor()
        self._redraw_now()

    def _on_mouse_move(self, event):
        """Crosshair + tooltip on hover, and pixel-based drag-to-pan."""
        legend_code = self._hovered_legend_code(event)
        if legend_code is not None:
            self._set_legend_hover_code(legend_code)
            self._hide_hover()
            return
        self._set_legend_hover_code(None)

        # Guard: ignore events with no valid data coordinates
        if event.xdata is None or event.ydata is None:
            if self._annot and self._annot.get_visible():
                self._annot.set_visible(False)
                if self._crosshair_v:
                    self._crosshair_v.set_visible(False)
                if self._crosshair_h:
                    self._crosshair_h.set_visible(False)
                self._last_crosshair_state = None
                self._overlay_update()
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
                    self._push_undo_state()
                    self._pan_active = True
                    self._canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
                    if self._annot and self._annot.get_visible():
                        self._annot.set_visible(False)
                    if self._crosshair_v:
                        self._crosshair_v.set_visible(False)
                    if self._crosshair_h:
                        self._crosshair_h.set_visible(False)
                    self._last_crosshair_state = None
                    self._last_pan_draw_ts = 0.0
                else:
                    return
            if self._pan_active:
                now = time.monotonic()
                if now - self._last_pan_draw_ts < (1.0 / 90.0):
                    return
                # Convert pixel delta to data delta
                ddx, ddy = self._px_to_data_delta(dx_px, dy_px)
                ox_lo, ox_hi = self._pan_origin_xlim
                oy_lo, oy_hi = self._pan_origin_ylim
                # Subtract because dragging right should move view left
                new_x_lo, new_x_hi = ox_lo - ddx, ox_hi - ddx
                new_y_lo, new_y_hi = oy_lo - ddy, oy_hi - ddy
                new_x_lo, new_x_hi, new_y_lo, new_y_hi = self._clamp_view_limits(
                    new_x_lo, new_x_hi, new_y_lo, new_y_hi
                )
                self._ax.set_xlim(new_x_lo, new_x_hi)
                self._ax.set_ylim(new_y_lo, new_y_hi)
                self._set_user_view((new_x_lo, new_x_hi), (new_y_lo, new_y_hi))
                self._mark_interaction_activity()
                self._invalidate_hover_screen_cache()
                self._last_pan_draw_ts = now
                self._canvas.draw_idle()
                return


        if not event.inaxes or self._annot is None:
            if self._annot and self._annot.get_visible():
                self._annot.set_visible(False)
                if self._crosshair_v:
                    self._crosshair_v.set_visible(False)
                if self._crosshair_h:
                    self._crosshair_h.set_visible(False)
                self._overlay_update()
            return

        hover_points = getattr(self, "_cached_hover_screen_points", None)
        if not hover_points:
            return

        # Find nearest data point
        best_dist_px2 = float("inf")
        best_info = None
        leader_refs = getattr(self, '_cached_leader_refs', {})
        for px, py, info in hover_points:
            dx_px = px - event.x
            dy_px = py - event.y
            dist_px2 = dx_px * dx_px + dy_px * dy_px
            if dist_px2 < best_dist_px2:
                best_dist_px2 = dist_px2
                best_info = info

        hover_radius_px = 16
        if best_info and best_dist_px2 <= (hover_radius_px * hover_radius_px):
            self._show_hover_info(best_info, leader_refs)
        else:
            if self._annot.get_visible():
                self._hide_hover()

    def _is_over_legend(self, event):
        bbox = getattr(self, "_legend_bbox", None)
        return bool(bbox is not None and bbox.contains(event.x, event.y))

    def _hovered_legend_code(self, event):
        if not getattr(self, "_legend_map", None):
            return None
        if event is None:
            return None
        hitboxes = getattr(self, "_legend_hitboxes", None) or []
        for bbox, code in hitboxes:
            if bbox.contains(event.x, event.y):
                return code
        for artist, code in self._legend_map.items():
            try:
                contains, _ = artist.contains(event)
            except Exception:
                contains = False
            if contains:
                return code
            try:
                bbox = artist.get_window_extent(self._canvas.renderer)
            except Exception:
                continue
            if bbox is not None and bbox.expanded(1.08, 1.25).contains(event.x, event.y):
                return code
        return None

    def _rebuild_legend_hitboxes(self):
        self._legend_bbox = None
        self._legend_hitboxes = []
        legend = getattr(self, "_legend_artist", None)
        if legend is None:
            return
        renderer = getattr(self._canvas, "renderer", None)
        if renderer is None:
            try:
                renderer = self._canvas.get_renderer()
            except Exception:
                renderer = None
        if renderer is None:
            return
        try:
            self._legend_bbox = legend.get_window_extent(renderer)
        except Exception:
            self._legend_bbox = None
        for artist, code in getattr(self, "_legend_map", {}).items():
            try:
                bbox = artist.get_window_extent(renderer)
            except Exception:
                continue
            if bbox is None:
                continue
            self._legend_hitboxes.append((bbox.expanded(1.08, 1.25), code))

    def _set_legend_hover_code(self, code):
        if code == self._hover_legend_code:
            return
        if self._hover_legend_code is not None:
            self._apply_legend_hover_style(self._hover_legend_code, active=False)
        entering_hover = code is not None and self._hover_legend_code is None
        leaving_hover = code is None and self._hover_legend_code is not None
        self._hover_legend_code = code
        if entering_hover:
            if self._render_timer.isActive():
                self._render_timer.stop()
            if self._deferred_redraw_timer.isActive():
                self._deferred_redraw_timer.stop()
        if code is not None:
            self._apply_legend_hover_style(code, active=True)
        self._canvas.draw_idle()
        if entering_hover and (self._chart_dirty or self._pending_live_redraw or self._last_rendered_stream_version != self._latest_stream_version):
            self._request_live_render(immediate=False)
        if leaving_hover and (self._chart_dirty or self._pending_live_redraw or self._last_rendered_stream_version != self._latest_stream_version):
            self._request_live_render(immediate=False)

    def _apply_legend_hover_style(self, code, active):
        plot_line = self._plot_line_by_code.get(code)
        plot_style = self._plot_line_style_by_code.get(code, {})
        if plot_line is not None and plot_style:
            if active:
                plot_line.set_alpha(min(1.0, plot_style["alpha"] + 0.20))
                plot_line.set_linewidth(plot_style["linewidth"] + 1.0)
                plot_line.set_zorder(plot_style["zorder"] + 5.0)
            else:
                plot_line.set_alpha(plot_style["alpha"])
                plot_line.set_linewidth(plot_style["linewidth"])
                plot_line.set_zorder(plot_style["zorder"])

        legend_line = self._legend_line_by_code.get(code)
        legend_line_style = self._legend_line_style_by_code.get(code, {})
        if legend_line is not None and legend_line_style:
            if active:
                legend_line.set_alpha(1.0)
                legend_line.set_linewidth(legend_line_style["linewidth"] + 1.0)
            else:
                legend_line.set_alpha(legend_line_style["alpha"])
                legend_line.set_linewidth(legend_line_style["linewidth"])

        legend_text = self._legend_text_by_code.get(code)
        legend_text_style = self._legend_text_style_by_code.get(code, {})
        if legend_text is not None and legend_text_style:
            if active:
                legend_text.set_color("#FFFFFF")
                legend_text.set_alpha(1.0)
            else:
                legend_text.set_color(legend_text_style["color"])
                legend_text.set_alpha(legend_text_style["alpha"])
                legend_text.set_fontweight(legend_text_style["fontweight"])

    def _find_hover_info_by_key(self, hover_key):
        if not hover_key:
            return None
        hover_candidates = getattr(self, "_cached_hover_candidates", None) or []
        code, lap = hover_key
        for info in hover_candidates:
            if info.get("code") == code and info.get("lap") == lap:
                return info
        return None

    def _restore_hover_point(self, hover_key):
        info = self._find_hover_info_by_key(hover_key)
        if info is None:
            return False
        self._show_hover_info(info, getattr(self, "_cached_leader_refs", {}))
        return True

    def _show_hover_info(self, info, leader_refs):
        if info is None or self._annot is None:
            return

        colour = self._driver_colors.get(info["code"], _DEFAULT_COLOUR)
        tyre_name = get_tyre_compound_str(info["tyre"])

        leader_ref = leader_refs.get(info["lap"])
        if self._is_gap_mode():
            val_str = _format_delta(info['val'])
        else:
            val_str = _format_laptime(info["time_s"])
        if info.get("is_approx"):
            val_str += " (approx)"

        tyre_life_str = f", {int(info['tyre_life'])} Laps Old" if info.get('tyre_life') else ""

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
            self._is_time_mode()
            and is_personal_best
            and personal_best < float('inf')
            and session_best < float('inf')
        ):
            pb_gap = personal_best - session_best
            extra_lines.append(f"Gap to SB: {_format_delta(pb_gap)}")

        if self._is_gap_mode() and leader_ref is not None:
            extra_lines.append(f"Race leader: {leader_ref['code']}")
        if info.get("is_pit_entry"):
            extra_lines.append("Pit stop")
        if info.get("is_terminal_lap") and info.get("status"):
            extra_lines.append(info["status"])

        if info.get("is_terminal_no_time"):
            text = f"{info['code']}  Lap {info['lap']}"
            if tyre_name:
                text += f"\n({tyre_name}{tyre_life_str})"
            text += f"\n{_terminal_status_display_text(info.get('status'))}"
        elif self._is_gap_mode():
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

        new_state = (info["code"], info["lap"])
        if new_state == self._last_crosshair_state and self._annot.get_visible():
            return
        self._last_crosshair_state = new_state
        self._hover_point_key = new_state

        self._annot.xy = (info["lap"], info["val"])
        self._annot.set_text(text)
        self._annot.get_bbox_patch().set_edgecolor(colour)

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

        self._overlay_update()

    def _hide_hover(self):
        changed = False
        if self._annot:
            if self._annot.get_visible():
                self._annot.set_visible(False)
                changed = True
        if self._crosshair_v:
            if self._crosshair_v.get_visible():
                self._crosshair_v.set_visible(False)
                changed = True
        if self._crosshair_h:
            if self._crosshair_h.get_visible():
                self._crosshair_h.set_visible(False)
                changed = True
        self._last_crosshair_state = None
        self._hover_point_key = None
        if changed:
            self._overlay_update()

    def _rebuild_hover_screen_cache(self):
        hover_candidates = getattr(self, "_cached_hover_candidates", None)
        if not hover_candidates or not hasattr(self, "_ax"):
            self._cached_hover_screen_points = []
            self._hover_cache_dirty = False
            return
        transform = self._ax.transData.transform
        screen_points = []
        for info in hover_candidates:
            try:
                px, py = transform((info["lap"], info["val"]))
            except Exception:
                continue
            screen_points.append((float(px), float(py), info))
        self._cached_hover_screen_points = screen_points
        self._hover_cache_dirty = False

    def _refresh_hover_from_cursor(self):
        if (
            not hasattr(self, "_canvas")
            or not getattr(self, "_has_ever_drawn", False)
            or self._hover_cache_dirty
            or self._resize_active
        ):
            return
        local_pos = self._canvas.mapFromGlobal(QCursor.pos())
        if not self._canvas.rect().contains(local_pos):
            return
        ratio = self._canvas.devicePixelRatio()
        px_x = float(local_pos.x()) * ratio
        px_y = (self._canvas.height() - float(local_pos.y())) * ratio
        event = MouseEvent("motion_notify_event", self._canvas, px_x, px_y)
        self._on_mouse_move(event)

    def _mark_interaction_activity(self):
        self._last_interaction_ts = time.monotonic()

    def _is_interaction_hot(self):
        now = time.monotonic()
        latest = max(self._last_interaction_ts, self._last_zoom_ts)
        return (
            self._pan_press_px is not None
            or self._pan_active
            or (latest > 0.0 and (now - latest) < 0.18)
        )

    def _schedule_deferred_redraw(self):
        self._deferred_redraw_timer.start(110 if self._hover_legend_code is not None else 140)

    def _flush_deferred_redraw(self):
        if self._pending_live_redraw:
            self._request_live_render(immediate=False)

    def _flush_live_render(self):
        if not self._chart_dirty or self._resize_active or self._render_in_flight:
            return
        if self._is_interaction_hot():
            self._schedule_deferred_redraw()
            return
        self._render_in_flight = True
        self._pending_live_redraw = False
        started = time.monotonic()
        stream_version = self._latest_stream_version
        try:
            self._redraw()
            self._chart_dirty = False
            self._last_rendered_stream_version = stream_version
        finally:
            elapsed_ms = (time.monotonic() - started) * 1000.0
            self._last_render_monotonic = time.monotonic()
            self._render_in_flight = False
            self._perf_stats["full_redraw_count"] += 1
            self._perf_stats["redraw_durations_ms"].append(elapsed_ms)
            if len(self._perf_stats["redraw_durations_ms"]) > 120:
                self._perf_stats["redraw_durations_ms"] = self._perf_stats["redraw_durations_ms"][-120:]
        if self._chart_dirty or self._last_rendered_stream_version != self._latest_stream_version:
            self._request_live_render(immediate=False)

    def _widget_pos_to_data(self, pointf):
        if pointf is None:
            return None, None
        ratio = self._canvas.devicePixelRatio()
        px_x = float(pointf.x()) * ratio
        px_y = (self._canvas.height() - float(pointf.y())) * ratio
        try:
            cx, cy = self._ax.transData.inverted().transform((px_x, px_y))
        except Exception:
            return None, None
        return cx, cy

    def _begin_zoom_gesture(self):
        now = time.monotonic()
        if now - self._last_zoom_ts > 0.35:
            self._push_undo_state()
        self._last_zoom_ts = now

    def _apply_zoom_from_input(self, scale_factor, cx, cy):
        if cx is None or cy is None or scale_factor is None or scale_factor <= 0:
            return
        self._mark_interaction_activity()
        self._apply_zoom(scale_factor, cx, cy)
        self._last_zoom_ts = time.monotonic()

    def _smooth_zoom_factor(self, scale_factor, *, deadband=0.006, clamp=0.12):
        if scale_factor is None or scale_factor <= 0:
            return None
        delta = scale_factor - 1.0
        if abs(delta) < deadband:
            return None
        delta = max(-clamp, min(clamp, delta))
        return 1.0 + delta

    def _scale_factor_from_wheel_event(self, event):
        if event is None:
            return None
        use_pixel_delta = not event.pixelDelta().isNull()
        app = QApplication.instance()
        if app is not None and app.platformName() == "xcb":
            use_pixel_delta = False
        delta = event.pixelDelta() if use_pixel_delta else event.angleDelta()
        dx = float(delta.x())
        dy = float(delta.y())
        dominant = dy if abs(dy) >= abs(dx) else dx
        if abs(dominant) < 1e-6:
            return None
        steps = abs(dominant if use_pixel_delta else (dominant / 120.0))
        base_zoom = 0.985 if use_pixel_delta else 0.965
        if dominant > 0:
            raw = base_zoom ** steps
        else:
            raw = (1.0 / base_zoom) ** steps
        return self._smooth_zoom_factor(raw, deadband=0.004, clamp=0.16)

    def _apply_zoom(self, scale_factor, cx, cy):
        """Apply zoom centered on (cx, cy) with strict clamping."""
        ax = self._ax
        x_lo, x_hi = ax.get_xlim()
        y_lo, y_hi = ax.get_ylim()

        new_x_lo = cx - (cx - x_lo) * scale_factor
        new_x_hi = cx + (x_hi - cx) * scale_factor
        new_y_lo = cy - (cy - y_lo) * scale_factor
        new_y_hi = cy + (y_hi - cy) * scale_factor

        # Minimum zoom: 3 laps wide, 1.5 seconds tall
        if (new_x_hi - new_x_lo) < 3:
            return
        if self._is_time_mode() and (new_y_hi - new_y_lo) < 1.5:
            return
        if self._is_gap_mode() and (new_y_hi - new_y_lo) < 0.5:
            return

        # Maximum zoom out: strictly clamp to home, no overshoot
        if self._home_xlim:
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
        if hasattr(self, '_max_ylim'):
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
        self._overlay_reset()
        self._invalidate_hover_screen_cache()
        self._canvas.draw_idle()

    def _on_button_press(self, event):
        """Left-click starts pan; double-left-click resets view."""
        if event.xdata is None or event.ydata is None:
            return
        if event.button == 1:
            self._canvas.setFocus()
            if event.dblclick:
                self._push_undo_state()
                self._reset_view()
            else:
                self._mark_interaction_activity()
                self._pan_press_px = (event.x, event.y)
                self._pan_origin_xlim = self._ax.get_xlim()
                self._pan_origin_ylim = self._ax.get_ylim()
                self._pan_active = False

    def _on_button_release(self, event):
        """End pan on left-click release."""
        if event.button == 1:
            self._pan_press_px = None
            self._pan_active = False
            self._last_pan_draw_ts = 0.0
            self._canvas.unsetCursor()
            if self._hover_cache_dirty:
                self._view_refresh_timer.start(30)

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
            self._hover_legend_code = code
            
            # Toggle isolation
            if code in self._focused_drivers:
                self._focused_drivers.remove(code)
                if not self._focused_drivers:
                    combo_text = "All Drivers"
                elif len(self._focused_drivers) == 1:
                    combo_text = next(iter(self._focused_drivers))
                else:
                    combo_text = "Multiple Drivers"
            else:
                self._focused_drivers.add(code)
                if len(self._focused_drivers) == 1:
                    combo_text = code
                else:
                    combo_text = "Multiple Drivers"

            self._driver_combo.blockSignals(True)
            self._driver_combo.setCurrentText(combo_text)
            self._driver_combo.blockSignals(False)
            
            self._needs_full_redraw = True
            self._redraw_now()
            QTimer.singleShot(0, self._refresh_hover_from_cursor)

    def eventFilter(self, obj, event):
        """Handle Qt wheel and gesture zoom directly for consistent UX."""
        if event.type() == QEvent.Type.KeyPress:
            if self._handle_ui_key_event(event):
                return True
        if event.type() == QEvent.Type.Wheel and obj is self._canvas:
            cx, cy = self._widget_pos_to_data(event.position())
            if cx is None or cy is None:
                return False
            self._begin_zoom_gesture()
            scale_factor = self._scale_factor_from_wheel_event(event)
            self._apply_zoom_from_input(scale_factor, cx, cy)
            return True
        if self._use_native_pinch_zoom and event.type() == QEvent.Type.NativeGesture and obj is self._canvas:
            gesture_type = event.gestureType()
            if gesture_type == Qt.NativeGestureType.BeginNativeGesture:
                self._begin_zoom_gesture()
                return True
            if gesture_type == Qt.NativeGestureType.EndNativeGesture:
                return True
            if gesture_type == Qt.NativeGestureType.ZoomNativeGesture:
                cx, cy = self._widget_pos_to_data(event.position())
                if cx is None or cy is None:
                    return False
                if self._last_zoom_ts == 0.0:
                    self._begin_zoom_gesture()
                scale_delta = 1.0 + float(event.value())
                if scale_delta <= 0.0:
                    return True
                zoom_factor = self._smooth_zoom_factor(1.0 / scale_delta, deadband=0.0035, clamp=0.10)
                self._apply_zoom_from_input(zoom_factor, cx, cy)
                return True
        if (not self._use_native_pinch_zoom) and event.type() == QEvent.Type.Gesture:
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if pinch:
                state = pinch.state()
                if state == Qt.GestureState.GestureStarted:
                    self._begin_zoom_gesture()
                if state == Qt.GestureState.GestureFinished:
                    return True
                current_scale = float(pinch.scaleFactor())
                last_scale = float(pinch.lastScaleFactor() or 1.0)
                if last_scale <= 0.0:
                    last_scale = 1.0
                incremental_scale = current_scale / last_scale if current_scale > 0.0 else 1.0
                zoom_factor = self._smooth_zoom_factor(1.0 / incremental_scale, deadband=0.0035, clamp=0.10)
                if zoom_factor is not None:
                    cx, cy = self._widget_pos_to_data(pinch.centerPoint())
                    self._apply_zoom_from_input(zoom_factor, cx, cy)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if self._handle_ui_key_event(event):
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)

    def _handle_ui_key_event(self, event):
        key = event.key()
        if key in (Qt.Key.Key_K, Qt.Key.Key_L):
            event.accept()
            return True
        if key == Qt.Key.Key_H:
            self._toggle_help()
            event.accept()
            return True
        if key == Qt.Key.Key_I:
            self._legend_visible = not self._legend_visible
            self._needs_full_redraw = True
            self._redraw_now()
            event.accept()
            return True
        if self._canvas.hasFocus():
            pan_step_x = 0.12
            pan_step_y = 0.10
            if key == Qt.Key.Key_Left:
                self._push_undo_state()
                self._pan_view_by_fraction(frac_x=-pan_step_x)
                event.accept()
                return True
            if key == Qt.Key.Key_Right:
                self._push_undo_state()
                self._pan_view_by_fraction(frac_x=pan_step_x)
                event.accept()
                return True
            if key == Qt.Key.Key_Up:
                self._push_undo_state()
                self._pan_view_by_fraction(frac_y=pan_step_y)
                event.accept()
                return True
            if key == Qt.Key.Key_Down:
                self._push_undo_state()
                self._pan_view_by_fraction(frac_y=-pan_step_y)
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
    app.setApplicationName("Lap Time & Gap Evolution")
    window = LapTimeChartWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
