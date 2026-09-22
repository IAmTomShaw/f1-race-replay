import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QLinearGradient
from PySide6.QtCore import Qt, QRect, QTimer
from src.gui.pit_wall_window import PitWallWindow


TYRE_COLOURS = {
    0.0: ("#888888", "UNK"),
    1.0: ("#E8002D", "S"),    # Soft  —  red
    2.0: ("#FFF200", "M"),    # Medium —  yellow
    3.0: ("#CACACA", "H"),    # Hard  — white/grey
    4.0: ("#39B54A", "I"),    # Inter — green
    5.0: ("#0067FF", "W"),    # Wet   — blue
    6.0: ("#888888", "UNK"),  # safety/unknown compound
}

TYRE_NAMES = {
    0.0: "Unknown", 1.0: "Soft", 2.0: "Medium",
    3.0: "Hard",    4.0: "Inter", 5.0: "Wet", 6.0: "Unknown"
}

TYRE_REMAP = {
    0: 1,  # SOFT
    1: 2,  # MEDIUM
    2: 3,  # HARD
    3: 4,  # INTERMEDIATE
    4: 5,  # WET
}

BG          = "#0f0f0f"
ROW_BG      = "#1a1a1a"
ROW_ALT     = "#141414"
HEADER_BG   = "#111111"
ACCENT      = "#e10600"
TEXT_WHITE  = "#ffffff"
TEXT_DIM    = "#888888"
BORDER      = "#2a2a2a"


class StintBar(QWidget):
    """Single driver row: name + horizontal coloured stint bars."""

    def __init__(self, code, stints, total_laps, position=None, current_lap=1, parent=None):
        super().__init__(parent)
        self.code        = code
        self.stints      = stints
        self.total_laps  = total_laps or 60
        self.position    = position
        self.current_lap = current_lap
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def update_data(self, stints, total_laps, position=None, current_lap=1):
        self.stints      = stints
        self.total_laps  = total_laps or self.total_laps
        self.position    = position
        self.current_lap = current_lap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        W = self.width()
        H = self.height()
        NAME_W   = 52
        POS_W    = 34
        BAR_PAD  = 6
        bar_x    = NAME_W + POS_W + BAR_PAD
        bar_w    = W - bar_x - BAR_PAD

        # Row background
        painter.fillRect(0, 0, W, H, QColor(ROW_BG))

        # Position badge
        if self.position:
            if self.position == 1:
                pos_color = QColor("#FFD700")
            elif self.position <= 3:
                pos_color = QColor(ACCENT)
            else:
                pos_color = QColor("#222222")

            painter.fillRect(0, 6, POS_W - 4, H - 12, pos_color)
            painter.setPen(QColor(TEXT_WHITE))
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(QRect(0, 6, POS_W - 4, H - 12),
                             Qt.AlignCenter, str(self.position))

        # Driver code
        painter.setPen(QColor(TEXT_WHITE))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(QRect(POS_W, 0, NAME_W - 4, H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.code)

        # Lap axis background
        painter.fillRect(bar_x, 10, bar_w, H - 20, QColor("#111111"))

        # Stint blocks
        for stint in self.stints:
            s_lap = stint["start_lap"]
            e_lap = stint["end_lap"] if stint["end_lap"] else self.current_lap
            tyre  = stint["tyre"]

            colour_hex, abbr = TYRE_COLOURS.get(tyre, ("#888888", "?"))
            colour = QColor(colour_hex)

            x1 = bar_x + int((s_lap - 1) / self.total_laps * bar_w)
            x2 = bar_x + int((e_lap - 1) / self.total_laps * bar_w)
            bw = max(x2 - x1, 2)

            # Gradient fill
            grad = QLinearGradient(x1, 10, x1, H - 10)
            grad.setColorAt(0,   colour.lighter(130))
            grad.setColorAt(0.5, colour)
            grad.setColorAt(1,   colour.darker(130))
            painter.fillRect(x1, 10, bw, H - 20, QBrush(grad))

            # Compound letter centred in block
            if bw > 14:
                text_col = QColor("#000000") if tyre in (2.0, 3.0) else QColor("#ffffff")
                painter.setPen(text_col)
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                label_w = min(bw - 4, 18)
                painter.drawText(QRect(x1 + 3, 10, label_w, H - 20),
                                 Qt.AlignVCenter | Qt.AlignLeft, abbr)

        # Current lap marker
        if self.current_lap and self.current_lap > 1:
            lx = bar_x + int((self.current_lap - 1) / self.total_laps * bar_w)
            painter.setPen(QPen(QColor("#ffffff"), 1, Qt.DotLine))
            painter.drawLine(lx, 4, lx, H - 4)

        # Thin separator line
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawLine(0, H - 1, W, H - 1)

        painter.end()


class LapAxisWidget(QWidget):
    """Draws lap numbers along the bottom."""

    def __init__(self, total_laps=60, parent=None):
        super().__init__(parent)
        self.total_laps = total_laps
        self.setFixedHeight(24)

    def set_total_laps(self, n):
        self.total_laps = n
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        W = self.width()
        NAME_W = 80
        BAR_PAD = 6
        bar_x = NAME_W + BAR_PAD
        bar_w = W - bar_x - BAR_PAD

        painter.fillRect(0, 0, W, self.height(), QColor(HEADER_BG))
        painter.setPen(QColor(TEXT_DIM))
        painter.setFont(QFont("Arial", 8))

        step = max(1, self.total_laps // 10)
        for lap in range(0, self.total_laps + 1, step):
            x = bar_x + int(lap / self.total_laps * bar_w)
            painter.drawText(x - 8, 0, 20, 20, Qt.AlignCenter, str(lap))
        painter.end()


class TyreStrategyWindow(PitWallWindow):

    def __init__(self):
        # attrs FIRST — super().__init__() calls setup_ui() immediately
        self.stints      = {}
        self.prev_tyres  = {}
        self.positions   = {}
        self.total_laps  = 60
        self.current_lap = 1
        self._row_widgets: dict[str, StintBar] = {}
        self._redraw_pending = False

        # Load persisted state if exists
        self._load_state()

        super().__init__()
        self.setWindowTitle("F1 Tyre Strategy")
        self.statusBar().hide()
        self.setStyleSheet("QMainWindow { background: #0f0f0f; } QStatusBar { background: #111111; }")

        # Timer init AFTER super — needs Qt event loop ready
        self._timer = QTimer()
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._flush_redraw)
        self._timer.start()

    # ------------------------------------------------------------------ State --

    def _load_state(self):
        try:
            import json, os
            if os.path.exists("computed_data/tyre_state.json"):
                with open("computed_data/tyre_state.json") as f:
                    saved = json.load(f)
                    self.stints      = saved.get("stints", {})
                    self.positions   = saved.get("positions", {})
                    self.prev_tyres  = saved.get("prev_tyres", {})
                    self.current_lap = saved.get("current_lap", 1)
                    self.total_laps  = saved.get("total_laps", 60)
                    print("Tyre state loaded successfully.")
        except FileNotFoundError:
            print("No saved tyre state found. Starting fresh.")
        except json.JSONDecodeError:
            print("Saved tyre state corrupted. Starting fresh.")
        except Exception as e:
            print(f"Failed to load tyre state: {e}")

    def _save_state(self):
        try:
            import json, os
            if not os.path.exists("computed_data"):
                os.makedirs("computed_data")
            with open("computed_data/tyre_state.json", "w") as f:
                json.dump({
                    "stints":      self.stints,
                    "positions":   self.positions,
                    "prev_tyres":  self.prev_tyres,
                    "current_lap": self.current_lap,
                    "total_laps":  self.total_laps,
                }, f)
            print("Tyre state saved successfully.")
        except PermissionError:
            print("Permission denied saving tyre state.")
        except OSError as e:
            print(f"OS error saving tyre state: {e}")
        except Exception as e:
            print(f"Failed to save tyre state: {e}")

    def closeEvent(self, event):
        self._save_state()
        super().closeEvent(event)

    # ------------------------------------------------------------------ UI --

    def setup_ui(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {BG}; }}
            QWidget {{ background: {BG}; color: {TEXT_WHITE}; }}
            QFrame#header {{ background: #111111; }}
        """)
        self.resize(900, 640)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(52)
        header.setStyleSheet("background:#111111; border-bottom:1px solid #2a2a2a; color:#ffffff;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 0, 14, 0)

        flag = QLabel("🏁")
        flag.setFont(QFont("Arial", 20))
        h_layout.addWidget(flag)

        title = QLabel("TYRE STRATEGY")
        title.setFont(QFont("Arial", 15, QFont.Bold))
        title.setStyleSheet(f"color:{TEXT_WHITE}; letter-spacing:3px;")
        h_layout.addWidget(title)

        h_layout.addStretch()

        self.lap_label = QLabel("LAP — / —")
        self.lap_label.setFont(QFont("Arial", 11, QFont.Bold))
        self.lap_label.setStyleSheet(f"color:{TEXT_WHITE};")
        h_layout.addWidget(self.lap_label)

        outer.addWidget(header)

        # ── Legend ────────────────────────────────────────────────────────
        legend_row = QFrame()
        legend_row.setFixedHeight(30)
        legend_row.setStyleSheet(f"background:#111111; border-bottom:1px solid {BORDER};")
        leg_layout = QHBoxLayout(legend_row)
        leg_layout.setContentsMargins(80, 0, 12, 0)
        leg_layout.setSpacing(18)

        for tval, (col, abbr) in TYRE_COLOURS.items():
            if tval == 0.0:
                continue
            dot = QLabel(f"● {TYRE_NAMES[tval]}")
            dot.setFont(QFont("Arial", 9))
            dot.setStyleSheet(f"color:{col};")
            leg_layout.addWidget(dot)

        leg_layout.addStretch()
        outer.addWidget(legend_row)

        # ── Scroll area for driver rows ───────────────────────────────────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            f"QScrollArea{{border:none; background:{BG};}}"
            f"QScrollBar:vertical{{background:#1a1a1a; width:6px; border-radius:3px;}}"
            f"QScrollBar::handle:vertical{{background:#444; border-radius:3px;}}"
        )

        self.rows_container = QWidget()
        self.rows_container.setStyleSheet(f"background:{BG};")
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.rows_layout.addStretch()

        self.scroll_area.setWidget(self.rows_container)
        outer.addWidget(self.scroll_area, 1)

        # ── Lap axis at bottom ────────────────────────────────────────────
        self.axis_widget = LapAxisWidget(self.total_laps)
        self.axis_widget.setStyleSheet("background:#111111;")
        outer.addWidget(self.axis_widget)

        # ── Status bar ────────────────────────────────────────────────────
        status_bar = QFrame()
        status_bar.setFixedHeight(22)
        status_bar.setStyleSheet(
            f"background:#0a0a0a; border-top:1px solid {BORDER};"
        )
        sb_layout = QHBoxLayout(status_bar)
        sb_layout.setContentsMargins(12, 0, 12, 0)
        self.status_label = QLabel("● Waiting for telemetry…")
        self.status_label.setFont(QFont("Arial", 8))
        self.status_label.setStyleSheet(f"color:{TEXT_DIM};")
        sb_layout.addWidget(self.status_label)
        sb_layout.addStretch()
        outer.addWidget(status_bar)

    # --------------------------------------------------------- Telemetry ---

    def on_telemetry_data(self, data):
        if "frame" not in data:
            return

        frame   = data["frame"]
        drivers = frame.get("drivers", {})

        sess = data.get("session_data", {})
        if sess.get("total_laps"):
            new_total = int(sess["total_laps"])
            if new_total != self.total_laps and self.current_lap <= 2:
                print("New session detected. Wiping old tyre state.")
                self.stints     = {}
                self.prev_tyres = {}
                self.positions  = {}
            self.total_laps = new_total

        self.current_lap = int(frame.get("lap", self.current_lap))

        for code, driver in drivers.items():
            tyre = driver.get("tyre")
            lap  = driver.get("lap")
            pos  = driver.get("position")

            if pos is not None:
                self.positions[code] = int(pos)

            if tyre is not None and isinstance(tyre, (int, float)):
                tyre = TYRE_REMAP.get(round(float(tyre)), tyre)
            if tyre is None or lap is None or not isinstance(tyre, (int, float)) or tyre == 0.0:
                continue

            lap = int(lap)
            if code not in self.stints:
                self.stints[code]     = [{"tyre": tyre, "start_lap": lap, "end_lap": None}]
                self.prev_tyres[code] = tyre
            elif tyre != self.prev_tyres[code]:
                self.stints[code][-1]["end_lap"] = lap - 1
                self.stints[code].append({"tyre": tyre, "start_lap": lap, "end_lap": None})
                self.prev_tyres[code] = tyre

        self._redraw_pending = True

    # ----------------------------------------------------------- Render ----

    def _flush_redraw(self):
        if not self._redraw_pending:
            return
        self._redraw_pending = False

        self.lap_label.setText(f"LAP {self.current_lap} / {self.total_laps}")
        self.axis_widget.set_total_laps(self.total_laps)
        self.status_label.setText(
            f"● Live  │  {len(self.stints)} drivers  │  Lap {self.current_lap}"
        )

        # Sort by position, fallback alphabetical
        sorted_codes = sorted(
            self.stints.keys(),
            key=lambda c: (self.positions.get(c, 999), c)
        )

        for i, code in enumerate(sorted_codes):
            pos = self.positions.get(code)
            if code not in self._row_widgets:
                bar = StintBar(code, self.stints[code], self.total_laps, pos, self.current_lap)
                self._row_widgets[code] = bar
            else:
                self._row_widgets[code].update_data(
                    self.stints[code], self.total_laps, pos, self.current_lap
                )
            self.rows_layout.insertWidget(i, self._row_widgets[code])