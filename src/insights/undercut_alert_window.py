import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QSizePolicy,
)

from src.gui.pit_wall_window import PitWallWindow

# ── Theme ──────────────────────────────────────────────────────────────────────
BG      = "#0f0f1a"
SURFACE = "#1e1e2e"
ACCENT  = "#e8002d"
TEXT    = "#e0e0e0"
DIM     = "#888899"
BORDER  = "#2a2a3e"

ALERT_UNDERCUT = "#e8002d"
ALERT_OVERCUT  = "#ffaa00"
ALERT_INFO     = "#27f4d2"

# ── Constants ──────────────────────────────────────────────────────────────────
PIT_LOSS_S       = 22.0   # seconds lost in the pit lane (default)
MIN_TYRE_DELTA   = 8      # laps difference to flag undercut as likely effective
CIRCUIT_LEN      = 5000.0 # metres, used for gap estimate; override if known

# Overcut overlife thresholds (laps)
OVERCUT_SOFT   = 20
OVERCUT_MEDIUM = 35
OVERCUT_HARD   = 50

_COMPOUND_NAME = {0: "Softs", 1: "Mediums", 2: "Hards", 3: "Inters", 4: "Wets"}
_COMPOUND_KEY  = {0: "S", 1: "M", 2: "H", 3: "I", 4: "W"}


class _AlertWidget(QFrame):
    """Single alert entry displayed in the log."""

    def __init__(self, alert_type: str, timestamp: str, lap: int, text: str, parent=None):
        super().__init__(parent)
        colour = {
            "undercut": ALERT_UNDERCUT,
            "overcut":  ALERT_OVERCUT,
            "info":     ALERT_INFO,
        }.get(alert_type, TEXT)

        self.setStyleSheet(
            f"background-color: {SURFACE}; border-left: 3px solid {colour}; border-radius: 4px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        meta_line = QHBoxLayout()
        badge = QLabel(alert_type.upper())
        badge.setFont(QFont("Arial", 8, QFont.Bold))
        badge.setStyleSheet(f"color: {colour}; background: transparent; border: none;")

        ts_label = QLabel(f"Lap {lap}  ·  {timestamp}")
        ts_label.setFont(QFont("Arial", 8))
        ts_label.setStyleSheet(f"color: {DIM}; background: transparent; border: none;")
        ts_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        meta_line.addWidget(badge)
        meta_line.addStretch()
        meta_line.addWidget(ts_label)
        layout.addLayout(meta_line)

        msg = QLabel(text)
        msg.setFont(QFont("Arial", 11))
        msg.setStyleSheet(f"color: {TEXT}; background: transparent; border: none;")
        msg.setWordWrap(True)
        layout.addWidget(msg)


class UndercutAlertWindow(PitWallWindow):
    """
    Proactive strategy analysis: detects undercut and overcut opportunities
    from live telemetry using deterministic logic only.
    """

    def __init__(self):
        # Per-driver state
        self._tyre_history: dict[str, dict] = {}      # code -> {tyre_raw, lap, tyre_age_start_lap}
        self._positions: dict[str, int] = {}          # code -> position
        self._rel_dist: dict[str, float] = {}         # code -> rel_dist
        self._speed: dict[str, float] = {}            # code -> speed km/h
        self._current_lap: dict[str, int] = {}        # code -> current lap number
        self._overcut_warned: set[str] = set()        # codes already warned for overcut

        self._alert_count = 0
        self._current_session_lap = 0

        super().__init__()
        self.setWindowTitle("Undercut & Overcut Alerts")
        self.setGeometry(100, 100, 560, 700)

    # ── UI ─────────────────────────────────────────────────────────────────────

    def setup_ui(self):
        self.setStyleSheet(f"background-color: {BG};")

        central = QWidget()
        central.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QFrame()
        header.setStyleSheet(
            f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("Strategy Alerts")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT}; background: transparent;")

        self._count_label = QLabel("0 alerts")
        self._count_label.setFont(QFont("Arial", 10))
        self._count_label.setStyleSheet(f"color: {DIM}; background: transparent;")
        self._count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        h_layout.addWidget(title)
        h_layout.addStretch()
        h_layout.addWidget(self._count_label)
        layout.addWidget(header)

        # Legend
        legend = QLabel(
            f'<span style="color:{ALERT_UNDERCUT}">■</span> Undercut  '
            f'<span style="color:{ALERT_OVERCUT}">■</span> Overcut  '
            f'<span style="color:{ALERT_INFO}">■</span> Info'
        )
        legend.setFont(QFont("Arial", 9))
        legend.setStyleSheet(f"color: {DIM}; background: transparent;")
        layout.addWidget(legend)

        # Scrollable alert log
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {BG}; border: none; }}"
            f"QScrollBar:vertical {{ background: {BG}; width: 6px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )

        self._log_container = QWidget()
        self._log_container.setStyleSheet(f"background-color: {BG};")
        self._log_layout = QVBoxLayout(self._log_container)
        self._log_layout.setSpacing(4)
        self._log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_layout.addStretch()

        self._scroll.setWidget(self._log_container)
        layout.addWidget(self._scroll, stretch=1)

        # Empty state label
        self._empty_label = QLabel("No alerts yet — monitoring pit strategy...")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setFont(QFont("Arial", 12))
        self._empty_label.setStyleSheet(f"color: {DIM}; background: transparent;")
        self._empty_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._empty_label)

        if hasattr(self, "status_bar"):
            self.status_bar.hide()

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def on_telemetry_data(self, data):
        frame = data.get("frame", {})
        session = data.get("session_data", {})
        drivers = frame.get("drivers", {})
        if not drivers:
            return

        self._current_session_lap = int(session.get("lap", frame.get("lap", 0)) or 0)

        # Build position / rel_dist snapshot for this frame
        for code, d in drivers.items():
            self._positions[code]   = int(d.get("position") or 99)
            self._rel_dist[code]    = float(d.get("rel_dist") or 0.0)
            self._speed[code]       = float(d.get("speed") or 150.0)
            self._current_lap[code] = int(d.get("lap") or 0)

            tyre_raw = d.get("tyre")
            lap = self._current_lap[code]

            prev = self._tyre_history.get(code)
            if prev is None:
                self._tyre_history[code] = {
                    "tyre_raw": tyre_raw,
                    "lap":      lap,
                    "age_start_lap": lap,
                }
            elif tyre_raw is not None and prev["tyre_raw"] != tyre_raw:
                # Driver pitted — new tyre detected
                self._tyre_history[code] = {
                    "tyre_raw": tyre_raw,
                    "lap":      lap,
                    "age_start_lap": lap,
                }
                self._overcut_warned.discard(code)  # reset overcut warn on new stints
                self._evaluate_undercut(code, prev)

        # Overcut check — scan all drivers every frame (cheap)
        self._check_overcuts()

    def _tyre_age(self, code: str) -> int:
        hist = self._tyre_history.get(code)
        if hist is None:
            return 0
        return max(0, self._current_lap.get(code, 0) - hist.get("age_start_lap", 0))

    def _gap_seconds(self, rel_a: float, rel_b: float, speed_kmh: float) -> float:
        """Approximate gap in seconds between two rel_dist values."""
        speed_ms = max(speed_kmh / 3.6, 1.0)
        diff = (rel_a - rel_b) % 1.0
        return diff * CIRCUIT_LEN / speed_ms

    def _evaluate_undercut(self, pitting_code: str, old_hist: dict):
        """Called when pitting_code just pitted. Evaluate undercut on cars ahead."""
        pit_pos = self._positions.get(pitting_code, 99)
        pit_rel = self._rel_dist.get(pitting_code, 0.0)
        pit_lap = self._current_lap.get(pitting_code, 0)

        compound_name = _COMPOUND_NAME.get(
            int(old_hist.get("tyre_raw") or 0), "Unknown"
        )
        old_tyre_age = max(0, pit_lap - old_hist.get("age_start_lap", pit_lap))

        for code, d_pos in self._positions.items():
            if code == pitting_code:
                continue
            if d_pos >= pit_pos:
                continue  # only check cars ahead

            target_rel  = self._rel_dist.get(code, 0.0)
            target_speed = self._speed.get(code, 150.0)
            gap_s = self._gap_seconds(target_rel, pit_rel, target_speed)

            if gap_s > 3.0:
                continue  # too far ahead to be relevant

            target_tyre_age  = self._tyre_age(code)
            target_tyre_raw  = (self._tyre_history.get(code) or {}).get("tyre_raw")
            target_compound  = _COMPOUND_NAME.get(int(target_tyre_raw or 0), "Unknown")

            tyre_age_delta = target_tyre_age - old_tyre_age

            likely_effective = gap_s < PIT_LOSS_S and tyre_age_delta >= MIN_TYRE_DELTA

            # Estimate the required out-lap time for the undercut to work
            out_lap_needed = PIT_LOSS_S - gap_s
            out_lap_str = f"{out_lap_needed:.1f}s faster than {code}" if out_lap_needed > 0 else "any pace"

            if likely_effective:
                msg = (
                    f"{pitting_code} pitted from P{pit_pos}. Undercut attempt on "
                    f"{code} (P{d_pos}, gap {gap_s:.1f}s, {code} on "
                    f"{target_tyre_age}-lap-old {target_compound}). "
                    f"Likely effective if {pitting_code}'s out-lap is sub-{out_lap_str}."
                )
                self._add_alert("undercut", pit_lap, msg)
            else:
                msg = (
                    f"{pitting_code} pitted from P{pit_pos}. Undercut on {code} "
                    f"(P{d_pos}, gap {gap_s:.1f}s) unlikely — tyre delta only "
                    f"{tyre_age_delta} laps. {code} on {target_tyre_age}-lap-old {target_compound}."
                )
                self._add_alert("info", pit_lap, msg)

    def _check_overcuts(self):
        """Flag drivers running beyond compound life thresholds."""
        thresholds = {0: OVERCUT_SOFT, 1: OVERCUT_MEDIUM, 2: OVERCUT_HARD}
        for code, hist in self._tyre_history.items():
            if code in self._overcut_warned:
                continue
            tyre_raw = hist.get("tyre_raw")
            if tyre_raw is None:
                continue
            t = int(tyre_raw)
            threshold = thresholds.get(t)
            if threshold is None:
                continue
            age = self._tyre_age(code)
            if age >= threshold:
                compound = _COMPOUND_NAME.get(t, "Unknown")
                pos = self._positions.get(code, 99)
                msg = (
                    f"{code} (P{pos}) is on lap {age} of {compound} — "
                    f"past the {threshold}-lap overcut threshold. "
                    f"Potential overcut setup or delayed stop."
                )
                self._add_alert("overcut", self._current_lap.get(code, 0), msg)
                self._overcut_warned.add(code)

    # ── Alert log ──────────────────────────────────────────────────────────────

    def _add_alert(self, alert_type: str, lap: int, text: str):
        self._empty_label.hide()
        self._alert_count += 1
        self._count_label.setText(f"{self._alert_count} alert{'s' if self._alert_count != 1 else ''}")

        ts = datetime.now().strftime("%H:%M:%S")
        widget = _AlertWidget(alert_type, ts, lap, text)
        # Insert above the stretch spacer (index count-1)
        self._log_layout.insertWidget(self._log_layout.count() - 1, widget)

        # Auto-scroll to newest alert
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def on_connection_status_changed(self, status: str):
        pass
