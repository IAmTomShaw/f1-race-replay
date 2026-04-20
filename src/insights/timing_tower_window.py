from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
)

from src.gui.pit_wall_window import PitWallWindow
from src.data.f1_season_data import uses_mom

# ── Theme ──────────────────────────────────────────────────────────────────────
BG      = "#0f0f1a"
SURFACE = "#1e1e2e"
ACCENT  = "#e8002d"
TEXT    = "#e0e0e0"
DIM     = "#888899"
BORDER  = "#2a2a3e"

# Gap colour thresholds
GAP_DANGER = "#e8002d"   # < 1.0 s — DRS range
GAP_AMBER  = "#ffaa00"   # 1.0 – 3.0 s
GAP_SAFE   = "#e0e0e0"   # > 3.0 s

# Tyre compound integer -> short label
_COMPOUND = {0: "S", 1: "M", 2: "H", 3: "I", 4: "W"}

# Estimated circuit lap distance for speed-to-gap conversion (metres).
# Used only when we cannot derive it from telemetry. 5 km is a reasonable default.
_DEFAULT_CIRCUIT_LEN = 5000.0

_COLS = ["Pos", "Driver", "Gap Ahead", "Gap Leader", "Tyre", "Lap"]
_COL_WIDTHS = [40, 70, 90, 90, 45, 45]


class TimingTowerWindow(PitWallWindow):
    """Precision timing tower: live gaps to car ahead and to the leader."""

    def __init__(self):
        self._pending_data: dict | None = None   # latest frame waiting for repaint
        self._repaint_count = 0
        self._session_year: int = 2026

        super().__init__()
        self.setWindowTitle("Timing Tower")
        self.setGeometry(100, 100, 460, 680)

        # Throttle UI repaints to max 4 per second
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setInterval(250)
        self._repaint_timer.timeout.connect(self._flush_pending)
        self._repaint_timer.start()

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

        title = QLabel("Timing Tower")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT}; background: transparent;")

        self._session_label = QLabel("—")
        self._session_label.setFont(QFont("Arial", 10))
        self._session_label.setStyleSheet(f"color: {DIM}; background: transparent;")
        self._session_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        h_layout.addWidget(title)
        h_layout.addStretch()
        h_layout.addWidget(self._session_label)
        layout.addWidget(header)

        # Table
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: {SURFACE};"
            f"  color: {TEXT};"
            f"  border: 1px solid {BORDER};"
            f"  gridline-color: {BORDER};"
            f"  border-radius: 6px;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background-color: {BG};"
            f"  color: {DIM};"
            f"  border: none;"
            f"  padding: 4px;"
            f"  font-size: 10px;"
            f"}}"
            f"QTableWidget::item {{ padding: 4px; }}"
            f"QScrollBar:vertical {{ background: {BG}; width: 6px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; }}"
        )
        self._table.setFont(QFont("Courier", 11))
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setFont(QFont("Arial", 9))
        self._table.setShowGrid(True)

        hh = self._table.horizontalHeader()
        for i, w in enumerate(_COL_WIDTHS):
            hh.resizeSection(i, w)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)

        layout.addWidget(self._table, stretch=1)

        # Legend — text updated once session year is known
        self._legend = QLabel()
        self._legend.setFont(QFont("Arial", 9))
        self._legend.setStyleSheet(f"color: {DIM}; background: transparent;")
        self._update_legend()
        layout.addWidget(self._legend)

        if hasattr(self, "status_bar"):
            self.status_bar.hide()

    def _update_legend(self):
        aid = "MOM" if uses_mom(self._session_year) else "DRS"
        self._legend.setText(
            f'<span style="color:{GAP_DANGER}">■</span> &lt;1.0s ({aid})  '
            f'<span style="color:{GAP_AMBER}">■</span> 1.0–3.0s  '
            f'<span style="color:{GAP_SAFE}">■</span> &gt;3.0s'
        )

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def on_telemetry_data(self, data):
        self._pending_data = data

    def _flush_pending(self):
        if self._pending_data is None:
            return
        data = self._pending_data
        self._pending_data = None
        self._update_table(data)

    def _update_table(self, data):
        frame = data.get("frame", {})
        session = data.get("session_data", {})
        session_info = data.get("session_info", {}) or {}
        drivers = frame.get("drivers", {})
        if not drivers:
            return

        year = int(session_info.get("year") or self._session_year)
        if year != self._session_year:
            self._session_year = year
            self._update_legend()

        lap = session.get("lap", frame.get("lap", "?"))
        total_laps = session.get("total_laps", "?")
        self._session_label.setText(f"Lap {lap} / {total_laps}")

        # Sort by position; treat missing position as 99
        ranked = sorted(
            drivers.items(),
            key=lambda item: int(item[1].get("position") or 99),
        )

        # Separate active from retired drivers (position > 20 or speed == 0 heuristic)
        active = []
        retired = []
        for code, d in ranked:
            pos = int(d.get("position") or 99)
            if pos <= 22:
                active.append((code, d))
            else:
                retired.append((code, d))

        rows = active + retired
        self._table.setRowCount(len(rows))

        leader_rel = None
        if active:
            leader_rel = float(active[0][1].get("rel_dist") or 0.0)

        for row_idx, (code, d) in enumerate(rows):
            pos = int(d.get("position") or 99)
            rel_dist = float(d.get("rel_dist") or 0.0)
            speed = float(d.get("speed") or 150.0)  # km/h; fallback prevents div/0
            tyre_raw = d.get("tyre")
            tyre = _COMPOUND.get(int(tyre_raw), "?") if tyre_raw is not None else "?"
            lap_num = int(d.get("lap") or 0)
            is_retired = pos > 22

            # Gap to car ahead
            if row_idx == 0 or is_retired:
                gap_ahead_str = "LEADER" if row_idx == 0 else "OUT"
                gap_ahead_colour = DIM if is_retired else ACCENT
            else:
                prev_rel = float(rows[row_idx - 1][1].get("rel_dist") or 0.0)
                # rel_dist is fractional (0–1). Difference * circuit_len / speed → seconds
                speed_ms = max(speed / 3.6, 1.0)
                dist_diff = (prev_rel - rel_dist) % 1.0  # handle wrap-around
                gap_s = dist_diff * _DEFAULT_CIRCUIT_LEN / speed_ms
                gap_ahead_str = f"{gap_s:.2f}s"
                if gap_s < 1.0:
                    gap_ahead_colour = GAP_DANGER
                elif gap_s < 3.0:
                    gap_ahead_colour = GAP_AMBER
                else:
                    gap_ahead_colour = GAP_SAFE

            # Gap to leader
            if row_idx == 0 or is_retired:
                gap_leader_str = "LEADER" if row_idx == 0 else "OUT"
                gap_leader_colour = ACCENT if row_idx == 0 else DIM
            else:
                speed_ms = max(speed / 3.6, 1.0)
                dist_to_leader = (leader_rel - rel_dist) % 1.0
                gap_leader_s = dist_to_leader * _DEFAULT_CIRCUIT_LEN / speed_ms
                gap_leader_str = f"+{gap_leader_s:.2f}s"
                gap_leader_colour = GAP_SAFE

            row_data = [
                (f"P{pos}", TEXT if not is_retired else DIM),
                (code,      DIM if is_retired else TEXT),
                (gap_ahead_str,  gap_ahead_colour),
                (gap_leader_str, gap_leader_colour),
                (tyre,      TEXT),
                (str(lap_num), TEXT),
            ]

            for col, (cell_text, cell_colour) in enumerate(row_data):
                item = QTableWidgetItem(cell_text)
                item.setForeground(QColor(cell_colour))
                item.setTextAlignment(Qt.AlignCenter)
                if is_retired:
                    item.setBackground(QColor("#1a1a2a"))
                self._table.setItem(row_idx, col, item)

    def on_connection_status_changed(self, status: str):
        pass
