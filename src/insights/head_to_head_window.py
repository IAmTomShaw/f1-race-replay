from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QComboBox, QSizePolicy,
)
import pyqtgraph as pg

from src.gui.pit_wall_window import PitWallWindow
from src.data.f1_season_data import uses_mom

# ── Theme ──────────────────────────────────────────────────────────────────────
BG      = "#0f0f1a"
SURFACE = "#1e1e2e"
ACCENT  = "#e8002d"
TEXT    = "#e0e0e0"
DIM     = "#888899"
BORDER  = "#2a2a3e"

GREEN   = "#22cc66"
RED_CLR = "#e8002d"

_COMPOUND = {0: "Soft", 1: "Medium", 2: "Hard", 3: "Inter", 4: "Wet"}

CIRCUIT_LEN = 5000.0  # metres

pg.setConfigOption("background", BG)
pg.setConfigOption("foreground", TEXT)

_METRICS = [
    "Position",
    "Speed (km/h)",
    "Throttle (%)",
    "Gear",
    "DRS",        # label swapped to "MOM" at runtime for 2026+ sessions
    "Tyre",
    "Tyre Age (laps)",
    "Gap on Track",
]

_DRS_ROW = _METRICS.index("DRS")


class HeadToHeadWindow(PitWallWindow):
    """Live comparative telemetry panel for two user-selected drivers."""

    def __init__(self):
        self._all_drivers: set[str] = set()
        self._latest_frame: dict = {}
        self._session_year: int = 2026

        # Position history for mini chart — last 10 lap-changes
        self._pos_history: dict[str, list[int]] = {}
        self._last_lap: dict[str, int] = {}

        self._pending_update = False

        super().__init__()
        self.setWindowTitle("Driver Head-to-Head")
        self.setGeometry(100, 100, 620, 700)

        # Throttle table updates to 1/s
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(1000)
        self._update_timer.timeout.connect(self._flush_update)
        self._update_timer.start()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def setup_ui(self):
        self.setStyleSheet(f"background-color: {BG};")

        central = QWidget()
        central.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Driver selectors ──────────────────────────────────────────────────
        selector_frame = QFrame()
        selector_frame.setStyleSheet(
            f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;"
        )
        sel_layout = QHBoxLayout(selector_frame)
        sel_layout.setContentsMargins(12, 8, 12, 8)
        sel_layout.setSpacing(12)

        combo_style = (
            f"QComboBox {{"
            f"  background-color: {BG}; color: {TEXT};"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 8px;"
            f"}}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{"
            f"  background-color: {SURFACE}; color: {TEXT}; selection-background-color: {BORDER};"
            f"}}"
        )

        lbl_a = QLabel("Driver A:")
        lbl_a.setFont(QFont("Arial", 11, QFont.Bold))
        lbl_a.setStyleSheet(f"color: {TEXT}; background: transparent;")

        self._combo_a = QComboBox()
        self._combo_a.setFont(QFont("Arial", 11))
        self._combo_a.setStyleSheet(combo_style)
        self._combo_a.setMinimumWidth(100)

        lbl_b = QLabel("Driver B:")
        lbl_b.setFont(QFont("Arial", 11, QFont.Bold))
        lbl_b.setStyleSheet(f"color: {TEXT}; background: transparent;")

        self._combo_b = QComboBox()
        self._combo_b.setFont(QFont("Arial", 11))
        self._combo_b.setStyleSheet(combo_style)
        self._combo_b.setMinimumWidth(100)

        sel_layout.addWidget(lbl_a)
        sel_layout.addWidget(self._combo_a)
        sel_layout.addStretch()
        sel_layout.addWidget(lbl_b)
        sel_layout.addWidget(self._combo_b)
        root.addWidget(selector_frame)

        # ── Comparison table ──────────────────────────────────────────────────
        self._table = QTableWidget(len(_METRICS), 4)
        self._table.setHorizontalHeaderLabels(["Metric", "Driver A", "Driver B", "Delta"])
        self._table.setVerticalHeaderLabels([""] * len(_METRICS))
        self._table.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: {SURFACE};"
            f"  color: {TEXT};"
            f"  border: 1px solid {BORDER};"
            f"  gridline-color: {BORDER};"
            f"  border-radius: 6px;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background-color: {BG}; color: {DIM};"
            f"  border: none; padding: 4px; font-size: 10px;"
            f"}}"
        )
        self._table.setFont(QFont("Courier New", 11))
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.verticalHeader().setVisible(False)

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)

        # Pre-fill metric names, swapping DRS→MOM for 2026+ sessions
        aid_label = "MOM" if uses_mom(self._session_year) else "DRS"
        for row, metric in enumerate(_METRICS):
            label = aid_label if row == _DRS_ROW else metric
            item = QTableWidgetItem(label)
            item.setForeground(QColor(DIM))
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._table.setItem(row, 0, item)

        root.addWidget(self._table)

        # ── Mini position chart ───────────────────────────────────────────────
        chart_label = QLabel("Position History (last 10 laps)")
        chart_label.setFont(QFont("Arial", 10, QFont.Bold))
        chart_label.setStyleSheet(f"color: {DIM}; background: transparent;")
        root.addWidget(chart_label)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel("bottom", "Lap offset")
        self._plot_widget.setLabel("left", "Position")
        self._plot_widget.invertY(True)   # P1 at top
        self._plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self._plot_widget.setMaximumHeight(160)
        self._plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(self._plot_widget)

        if hasattr(self, "status_bar"):
            self.status_bar.hide()

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def on_telemetry_data(self, data):
        frame = data.get("frame", {})
        drivers = frame.get("drivers", {})
        if not drivers:
            return

        session_info = data.get("session_info", {}) or {}
        year = int(session_info.get("year") or self._session_year)
        if year != self._session_year:
            self._session_year = year
            aid_label = "MOM" if uses_mom(self._session_year) else "DRS"
            item = self._table.item(_DRS_ROW, 0)
            if item:
                item.setText(aid_label)
                item.setForeground(QColor(DIM))

        self._latest_frame = drivers

        # Populate dropdowns as new drivers appear
        new_codes = set(drivers.keys()) - self._all_drivers
        if new_codes:
            for code in sorted(new_codes):
                self._combo_a.addItem(code)
                self._combo_b.addItem(code)
                self._all_drivers.add(code)
                self._pos_history[code] = []
                self._last_lap[code] = 0

        # Track position history (on lap change)
        for code, d in drivers.items():
            lap = int(d.get("lap") or 0)
            pos = int(d.get("position") or 99)
            if lap > self._last_lap.get(code, 0):
                self._last_lap[code] = lap
                hist = self._pos_history.setdefault(code, [])
                hist.append(pos)
                if len(hist) > 10:
                    hist.pop(0)

        self._pending_update = True

    def _flush_update(self):
        if not self._pending_update:
            return
        self._pending_update = False
        self._refresh_table()
        self._refresh_chart()

    # ── Table refresh ──────────────────────────────────────────────────────────

    def _refresh_table(self):
        code_a = self._combo_a.currentText()
        code_b = self._combo_b.currentText()
        if not code_a or not code_b:
            return

        da = self._latest_frame.get(code_a, {})
        db = self._latest_frame.get(code_b, {})

        def tyre_age(code):
            # Approximate from lap — we don't have exact pit lap here; return current lap
            d = self._latest_frame.get(code, {})
            return int(d.get("lap") or 0)

        def drs_str(d):
            if uses_mom(self._session_year):
                return "Available" if d.get("drs", 0) else "Unavailable"
            return "Active" if d.get("drs", 0) else "Inactive"

        def tyre_str(d):
            raw = d.get("tyre")
            return _COMPOUND.get(int(raw), "?") if raw is not None else "?"

        speed_a = float(da.get("speed") or 0)
        speed_b = float(db.get("speed") or 0)

        rel_a = float(da.get("rel_dist") or 0.0)
        rel_b = float(db.get("rel_dist") or 0.0)
        speed_ms = max((speed_a + speed_b) / 2 / 3.6, 1.0)
        gap_s = abs(rel_a - rel_b) % 1.0 * CIRCUIT_LEN / speed_ms

        pos_a = int(da.get("position") or 99)
        pos_b = int(db.get("position") or 99)

        rows = [
            # (metric, val_a, val_b, higher_is_better_for_A)
            # None = non-comparable
            (f"P{pos_a}",              f"P{pos_b}",              pos_a < pos_b,    True),   # lower pos = better
            (f"{speed_a:.0f}",         f"{speed_b:.0f}",         speed_a > speed_b, False),
            (f"{da.get('throttle', 0):.0f}%", f"{db.get('throttle', 0):.0f}%", float(da.get('throttle') or 0) > float(db.get('throttle') or 0), False),
            (str(int(da.get("gear") or 0)), str(int(db.get("gear") or 0)), None, False),
            (drs_str(da),              drs_str(db),              None,             False),
            (tyre_str(da),             tyre_str(db),             None,             False),
            (str(int(da.get("lap") or 0)), str(int(db.get("lap") or 0)), None, False),
            (f"{gap_s:.2f}s",          "—",                      None,             False),
        ]

        for row_idx, (val_a, val_b, a_better, invert) in enumerate(rows):
            self._set_cell(row_idx, 1, val_a, TEXT)
            self._set_cell(row_idx, 2, val_b, TEXT)

            if a_better is None:
                delta = "—"
                delta_colour = DIM
            elif a_better:
                # Compute numeric delta where possible
                try:
                    num_a = float(val_a.replace("P", "").replace("s", "").replace("%", ""))
                    num_b = float(val_b.replace("P", "").replace("s", "").replace("%", ""))
                    delta = f"+{num_a - num_b:.0f}" if not invert else f"+{num_b - num_a:.0f}"
                except ValueError:
                    delta = "A"
                delta_colour = GREEN
            else:
                try:
                    num_a = float(val_a.replace("P", "").replace("s", "").replace("%", ""))
                    num_b = float(val_b.replace("P", "").replace("s", "").replace("%", ""))
                    delta = f"{num_a - num_b:.0f}" if not invert else f"{num_b - num_a:.0f}"
                except ValueError:
                    delta = "B"
                delta_colour = RED_CLR

            self._set_cell(row_idx, 3, delta, delta_colour)

    def _set_cell(self, row: int, col: int, text: str, colour: str):
        item = self._table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self._table.setItem(row, col, item)
        item.setText(text)
        item.setForeground(QColor(colour))
        item.setTextAlignment(Qt.AlignCenter)

    # ── Chart refresh ──────────────────────────────────────────────────────────

    def _refresh_chart(self):
        code_a = self._combo_a.currentText()
        code_b = self._combo_b.currentText()

        self._plot_widget.clear()

        hist_a = self._pos_history.get(code_a, [])
        hist_b = self._pos_history.get(code_b, [])

        if hist_a:
            x = list(range(1, len(hist_a) + 1))
            self._plot_widget.plot(x, hist_a, pen=pg.mkPen(ACCENT, width=2), name=code_a)

        if hist_b:
            x = list(range(1, len(hist_b) + 1))
            self._plot_widget.plot(x, hist_b, pen=pg.mkPen("#27f4d2", width=2), name=code_b)

    def on_connection_status_changed(self, status: str):
        pass
