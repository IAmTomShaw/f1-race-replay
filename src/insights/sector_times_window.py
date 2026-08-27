"""
Sector Times insight window.

Shows a timing-screen-style breakdown of sector 1/2/3 times for every lap
of a selected driver, coloured like the official F1 timing screens:

- Purple: session best (fastest anyone has gone in that sector so far)
- Green: personal best (driver's fastest in that sector so far)
- White: no improvement

Laps appear as the replay progresses, so the colouring always reflects the
state of the session "so far" rather than leaking end-of-race information.
Sector data comes from the ``lap_times`` payload broadcast by the replay
server (official FastF1 lap data); frame-derived fallback laps without
sector times are shown with dashes.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtGui import QFont, QColor, QBrush
from PySide6.QtCore import Qt

from src.gui.pit_wall_window import PitWallWindow
from src.lib.sectors import (
    SECTOR_KEYS,
    STATUS_SESSION_BEST,
    STATUS_PERSONAL_BEST,
    classify_sector_statuses,
    session_best_holders,
    best_sectors,
    theoretical_best_s,
)

# Palette (consistent with the other insight windows)
_BG = "#0f0f0f"
_ROW_BG = "#1a1a1a"
_ROW_ALT = "#141414"
_HEADER_BG = "#111111"
_TEXT = "#E0E0E0"
_TEXT_DIM = "#888888"
_BORDER = "#2a2a2a"

# Timing screen colours
_SESSION_BEST_COLOUR = "#B027C9"   # purple
_PERSONAL_BEST_COLOUR = "#27C93F"  # green

_COLUMNS = ("Lap", "Sector 1", "Sector 2", "Sector 3", "Lap Time")


def _format_sector(seconds):
    """Format a sector time in seconds as SS.mmm (or M:SS.mmm if over a minute)."""
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "—"
    if seconds >= 60:
        m = int(seconds // 60)
        return f"{m}:{seconds % 60:06.3f}"
    return f"{seconds:.3f}"


def _format_laptime(seconds):
    """Format a lap time in seconds as M:SS.mmm."""
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "—"
    m = int(seconds // 60)
    return f"{m}:{seconds % 60:06.3f}"


class SectorTimesWindow(PitWallWindow):
    """Pit wall insight showing per-lap sector times for a selected driver."""

    def __init__(self):
        self._lap_times = {}          # code -> [lap entry dicts]
        self._known_drivers = []
        self._selected_driver = None
        self._current_time_s = None
        self._leader_lap = 0
        self._total_laps = 0
        self._last_signature = None

        super().__init__()

        self.setWindowTitle("F1 Race Replay - Sector Times")
        self.setGeometry(140, 140, 620, 640)

    # ------------------------------------------------------------------ UI

    def setup_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background-color: {_BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # Control row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        driver_label = QLabel("Driver:")
        driver_label.setFont(QFont("Arial", 11))
        driver_label.setStyleSheet(f"color: {_TEXT};")
        ctrl.addWidget(driver_label)

        self._driver_combo = QComboBox()
        self._driver_combo.setMinimumWidth(120)
        self._driver_combo.setFont(QFont("Arial", 11))
        self._driver_combo.setPlaceholderText("Waiting for data…")
        self._driver_combo.currentTextChanged.connect(self._on_driver_changed)
        ctrl.addWidget(self._driver_combo)

        ctrl.addStretch()

        legend = QLabel(
            f"<span style='color:{_SESSION_BEST_COLOUR};'>■</span> Session best   "
            f"<span style='color:{_PERSONAL_BEST_COLOUR};'>■</span> Personal best"
        )
        legend.setFont(QFont("Arial", 10))
        legend.setStyleSheet(f"color: {_TEXT_DIM};")
        ctrl.addWidget(legend)

        root.addLayout(ctrl)

        # Session-best summary
        self._session_best_label = QLabel("Waiting for lap data…")
        self._session_best_label.setFont(QFont("Consolas", 10))
        self._session_best_label.setStyleSheet(
            f"color: {_TEXT}; background-color: {_HEADER_BG};"
            f"border: 1px solid {_BORDER}; padding: 6px;"
        )
        root.addWidget(self._session_best_label)

        # Lap table
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setFont(QFont("Consolas", 10))
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {_ROW_BG};
                alternate-background-color: {_ROW_ALT};
                color: {_TEXT};
                border: 1px solid {_BORDER};
            }}
            QHeaderView::section {{
                background-color: {_HEADER_BG};
                color: {_TEXT_DIM};
                border: none;
                border-bottom: 1px solid {_BORDER};
                padding: 4px;
                font-weight: bold;
            }}
        """)
        root.addWidget(self._table, stretch=1)

        # Personal summary for the selected driver
        self._driver_summary_label = QLabel("")
        self._driver_summary_label.setFont(QFont("Consolas", 10))
        self._driver_summary_label.setStyleSheet(
            f"color: {_TEXT}; background-color: {_HEADER_BG};"
            f"border: 1px solid {_BORDER}; padding: 6px;"
        )
        root.addWidget(self._driver_summary_label)

    # ----------------------------------------------------------- telemetry

    def on_telemetry_data(self, data):
        sd = data.get("session_data", {})
        if sd:
            time_s = sd.get("time_s")
            if isinstance(time_s, (int, float)):
                self._current_time_s = float(time_s)
            leader_lap = sd.get("lap")
            if isinstance(leader_lap, (int, float)):
                self._leader_lap = int(leader_lap)
            total_laps = sd.get("total_laps")
            if isinstance(total_laps, (int, float)) and total_laps:
                self._total_laps = int(total_laps)

        if "lap_times" in data and data.get("lap_times"):
            self._lap_times = data["lap_times"]

        if not self._lap_times:
            return

        self._refresh_driver_list()

        # Only rebuild the table when the set of visible laps changes —
        # broadcasts arrive every frame, so rebuilding each time would
        # waste CPU redrawing an identical table.
        visible = self._visible_entries_by_code()
        signature = tuple(sorted(
            (code, int(entry["lap"]))
            for code, entries in visible.items()
            for entry in entries
        ))
        if signature != self._last_signature:
            self._last_signature = signature
            self._rebuild(visible)

    # ------------------------------------------------------------- helpers

    def _entry_visible(self, entry):
        """Mirror the lap chart's reveal logic: a lap only appears once the
        replay has reached the moment the driver completed it."""
        if entry.get("is_terminal_lap"):
            return False
        visible_at_s = None
        for key in ("replay_line_time_s", "replay_end_time_s"):
            value = entry.get(key)
            if isinstance(value, (int, float)):
                visible_at_s = float(value)
                break
        if visible_at_s is None and (
            entry.get("time_source") == "frame_backfill"
            or entry.get("source") == "derived"
        ):
            for key in ("line_time_s", "end_time_s"):
                value = entry.get(key)
                if isinstance(value, (int, float)):
                    visible_at_s = float(value)
                    break
        if visible_at_s is not None and isinstance(self._current_time_s, (int, float)):
            return self._current_time_s >= visible_at_s
        lap = entry.get("lap")
        if isinstance(lap, (int, float)):
            return self._leader_lap > int(lap)
        return False

    def _visible_entries_by_code(self):
        visible = {}
        for code, entries in self._lap_times.items():
            shown = [e for e in entries if self._entry_visible(e)]
            if shown:
                visible[code] = shown
        return visible

    def _refresh_driver_list(self):
        incoming = sorted(self._lap_times.keys())
        if incoming == self._known_drivers:
            return
        current = self._driver_combo.currentText()
        self._driver_combo.blockSignals(True)
        self._driver_combo.clear()
        self._driver_combo.addItems(incoming)
        if current in incoming:
            self._driver_combo.setCurrentText(current)
        elif incoming:
            self._driver_combo.setCurrentIndex(0)
        self._driver_combo.blockSignals(False)
        self._known_drivers = incoming
        self._selected_driver = self._driver_combo.currentText() or None

    def _on_driver_changed(self, text):
        if not text or text == self._selected_driver:
            return
        self._selected_driver = text
        self._last_signature = None  # force rebuild on next update
        self._rebuild(self._visible_entries_by_code())

    # ------------------------------------------------------------ rendering

    def _rebuild(self, visible):
        statuses = classify_sector_statuses(visible)
        self._update_session_best_label(visible)

        code = self._selected_driver
        entries = sorted(
            visible.get(code, []),
            key=lambda e: e.get("lap", 0),
        )

        self._table.setRowCount(len(entries))
        for row_idx, entry in enumerate(entries):
            lap = int(entry.get("lap", 0))

            lap_text = str(lap)
            if entry.get("is_pit_entry"):
                lap_text += "  (in)"
            elif entry.get("is_out_lap"):
                lap_text += "  (out)"
            lap_item = QTableWidgetItem(lap_text)
            lap_item.setTextAlignment(Qt.AlignCenter)
            if entry.get("is_pit_entry") or entry.get("is_out_lap"):
                lap_item.setForeground(QBrush(QColor(_TEXT_DIM)))
            self._table.setItem(row_idx, 0, lap_item)

            entry_statuses = statuses.get((code, lap), {})
            for col_offset, key in enumerate(SECTOR_KEYS):
                item = QTableWidgetItem(_format_sector(entry.get(key)))
                item.setTextAlignment(Qt.AlignCenter)
                status = entry_statuses.get(key)
                if status == STATUS_SESSION_BEST:
                    item.setForeground(QBrush(QColor(_SESSION_BEST_COLOUR)))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                elif status == STATUS_PERSONAL_BEST:
                    item.setForeground(QBrush(QColor(_PERSONAL_BEST_COLOUR)))
                self._table.setItem(row_idx, 1 + col_offset, item)

            time_item = QTableWidgetItem(_format_laptime(entry.get("time_s")))
            time_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row_idx, len(_COLUMNS) - 1, time_item)

        self._table.scrollToBottom()
        self._update_driver_summary(entries)

    def _update_session_best_label(self, visible):
        holders = session_best_holders(visible)
        parts = []
        for idx, key in enumerate(SECTOR_KEYS, start=1):
            best, codes = holders[key]
            if best is None:
                parts.append(f"S{idx} —")
            else:
                parts.append(f"S{idx} {_format_sector(best)} ({'/'.join(codes)})")
        self._session_best_label.setText("Session best:   " + "   ·   ".join(parts))

    def _update_driver_summary(self, entries):
        if not entries:
            self._driver_summary_label.setText("No completed laps yet for this driver.")
            return
        bests = best_sectors(entries)
        parts = []
        for idx, key in enumerate(SECTOR_KEYS, start=1):
            parts.append(f"S{idx} {_format_sector(bests[key])}")
        ideal = theoretical_best_s(entries)
        best_lap = min(
            (e.get("time_s") for e in entries
             if isinstance(e.get("time_s"), (int, float)) and e.get("time_s") > 0),
            default=None,
        )
        self._driver_summary_label.setText(
            "Personal best:  " + "   ·   ".join(parts)
            + f"   ·   Best lap {_format_laptime(best_lap)}"
            + f"   ·   Ideal lap {_format_laptime(ideal)}"
        )
