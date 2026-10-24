"""
Car Detail insight.

Everything about one car at a glance: live telemetry, tyres, pace and race
position. Every field is tagged with where it comes from:

  LIVE - recorded timing / telemetry, replayed as it happened
  EST  - a simple estimate with stated assumptions
  AI   - a prediction from the Bayesian tyre model, with its uncertainty

so a model output is never mistaken for telemetry. By default the window
follows whichever driver you click on the replay's leaderboard.
"""

import sys

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.gui.pit_wall_window import PitWallWindow
from src.lib.car_state import (
    AI,
    EST,
    LIVE,
    TAG_HELP,
    average_speed_mps,
    brake_fraction,
    compound_name,
    drs_state,
    estimate_fuel_kg,
    estimate_gap_s,
    format_lap_time,
    format_laps_left,
    last_completed_lap,
)

BG = "#121317"
CARD = "#1b1d22"
BORDER = "#2a2d34"
TEXT = "#eef0f2"
MUTED = "#8b919a"
TRACK = "#2a2d34"

TAG_COLOURS = {LIVE: "#22c55e", EST: "#f59e0b", AI: "#a78bfa"}
COMPOUND_COLOURS = {
    "SOFT": "#e8002d", "MEDIUM": "#ffd12e", "HARD": "#ecece6",
    "INTERMEDIATE": "#43b02a", "WET": "#0a7bd6", "UNKNOWN": "#6b7280",
}
DRS_COLOURS = {"OPEN": "#22c55e", "ELIGIBLE": "#f59e0b", "OFF": MUTED}

# Used for the gap estimate until the car has a completed lap (about 200 km/h).
FALLBACK_SPEED_MPS = 55.6

STYLE = f"""
QWidget#root {{ background: {BG}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; border: none; }}
QLabel {{ color: {TEXT}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#cardTitle {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#rowLabel {{ color: {MUTED}; font-size: 12px; }}
QLabel#rowValue {{ color: {TEXT}; font-size: 13px; font-weight: 600; }}
QLabel#bigValue {{ color: {TEXT}; font-size: 30px; font-weight: 700; }}
QLabel#unit {{ color: {MUTED}; font-size: 11px; }}
QLabel#legend {{ color: {MUTED}; font-size: 11px; }}
QLabel#waiting {{ color: {MUTED}; font-size: 13px; }}
QComboBox {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};
             border-radius: 6px; padding: 4px 8px; min-width: 70px; }}
QComboBox QAbstractItemView {{ background: {CARD}; color: {TEXT}; selection-background-color: #33363e; }}
QCheckBox {{ color: {TEXT}; spacing: 6px; }}
QStatusBar {{ background: #0e0f12; color: {MUTED}; }}
QStatusBar QLabel {{ color: {MUTED}; }}
"""


def _mono(size: int, bold: bool = True) -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.Monospace)
    font.setPointSize(size)
    font.setBold(bold)
    return font


class TagChip(QLabel):
    """Small outlined pill saying where a value comes from."""

    def __init__(self, tag: str, parent=None):
        super().__init__(tag, parent)
        colour = TAG_COLOURS[tag]
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(38, 18)
        self.setToolTip(TAG_HELP[tag])
        self.setStyleSheet(
            f"QLabel {{ color: {colour}; border: 1px solid {colour}; border-radius: 9px;"
            f" font-size: 9px; font-weight: 700; background: transparent; }}"
        )


class Meter(QWidget):
    """Thin rounded bar showing a 0..1 value."""

    def __init__(self, colour: str = TEXT, parent=None):
        super().__init__(parent)
        self._fraction = 0.0
        self._colour = QColor(colour)
        self.setMinimumWidth(90)
        self.setFixedHeight(12)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, fraction, colour: str = None):
        try:
            fraction = float(fraction)
        except (TypeError, ValueError):
            fraction = 0.0
        self._fraction = max(0.0, min(1.0, fraction))
        if colour:
            self._colour = QColor(colour)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bar = QRectF(0, 3, self.width(), 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(bar, 3, 3)
        if self._fraction > 0:
            p.setBrush(self._colour)
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), bar.width() * self._fraction, bar.height()), 3, 3)


class CarSchematic(QWidget):
    """
    Top-down car drawn from LIVE data only: team colour, tyres in the
    compound colour, brakes glowing when the driver brakes, DRS flap state.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.team = QColor("#888888")
        self.compound = "UNKNOWN"
        self.brake = 0.0
        self.drs = "OFF"
        self.setMinimumSize(120, 230)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setToolTip("Live: team colour, tyre compound, brakes and DRS flap.")

    def set_state(self, team_colour: str, compound: str, brake: float, drs: str):
        self.team = QColor(team_colour) if team_colour else QColor("#888888")
        self.compound = compound
        self.brake = brake
        self.drs = drs
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Design space is 100 x 220, scaled to fit and centred.
        scale = min(self.width() / 110.0, self.height() / 230.0)
        p.translate((self.width() - 100 * scale) / 2, (self.height() - 220 * scale) / 2)
        p.scale(scale, scale)

        carbon = QColor("#2b2e35")
        dark = QColor("#0d0e11")
        tyre = QColor(COMPOUND_COLOURS.get(self.compound, COMPOUND_COLOURS["UNKNOWN"]))

        def tyre_at(x, y, w, h):
            p.setPen(Qt.NoPen)
            p.setBrush(dark)
            p.drawRoundedRect(QRectF(x, y, w, h), 4, 4)
            p.setPen(QPen(tyre, 3))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(x + 2.5, y + 2.5, w - 5, h - 5), 3, 3)
            if self.brake > 0:
                glow = QRadialGradient(QPointF(x + w / 2, y + h / 2), w * 0.9)
                glow.setColorAt(0.0, QColor(255, 80, 40, int(200 * self.brake)))
                glow.setColorAt(1.0, QColor(255, 80, 40, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(glow))
                p.drawEllipse(QPointF(x + w / 2, y + h / 2), w * 0.9, w * 0.9)

        # Front wing with team-colour end plates
        p.setPen(Qt.NoPen)
        p.setBrush(carbon)
        p.drawRoundedRect(QRectF(6, 6, 88, 11), 3, 3)
        p.setBrush(self.team)
        p.drawRect(QRectF(6, 4, 5, 15))
        p.drawRect(QRectF(89, 4, 5, 15))

        tyre_at(4, 30, 18, 36)
        tyre_at(78, 30, 18, 36)
        tyre_at(2, 148, 22, 42)
        tyre_at(76, 148, 22, 42)

        # Suspension arms
        p.setPen(QPen(carbon, 2))
        for y in (42, 54):
            p.drawLine(QPointF(22, y), QPointF(42, y + 6))
            p.drawLine(QPointF(78, y), QPointF(58, y + 6))
        for y in (160, 176):
            p.drawLine(QPointF(24, y), QPointF(36, y))
            p.drawLine(QPointF(76, y), QPointF(64, y))

        # Body: nose -> sidepods -> engine cover, in team colour
        body = QPainterPath()
        body.moveTo(46, 17)
        body.lineTo(54, 17)
        body.lineTo(58, 70)
        body.cubicTo(70, 82, 76, 100, 74, 122)
        body.cubicTo(72, 146, 64, 168, 60, 192)
        body.lineTo(40, 192)
        body.cubicTo(36, 168, 28, 146, 26, 122)
        body.cubicTo(24, 100, 30, 82, 42, 70)
        body.closeSubpath()
        p.setPen(QPen(self.team.darker(160), 1.2))
        p.setBrush(self.team)
        p.drawPath(body)

        # Cockpit + halo
        p.setPen(Qt.NoPen)
        p.setBrush(dark)
        p.drawEllipse(QRectF(42, 84, 16, 26))
        p.setPen(QPen(QColor("#5b5f68"), 2.5))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(40, 80, 20, 30), 0, 180 * 16)

        # Rear wing + DRS flap
        p.setPen(Qt.NoPen)
        p.setBrush(carbon)
        p.drawRoundedRect(QRectF(16, 200, 68, 10), 2, 2)
        flap = QColor(DRS_COLOURS[self.drs]) if self.drs != "OFF" else QColor("#3a3e46")
        p.setBrush(flap)
        flap_y = 192 if self.drs == "OPEN" else 196
        p.drawRoundedRect(QRectF(18, flap_y, 64, 5), 2, 2)


class _Card(QFrame):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(14, 12, 14, 12)
        self.layout_.setSpacing(8)
        if title:
            label = QLabel(title.upper())
            label.setObjectName("cardTitle")
            self.layout_.addWidget(label)


class CarDetailWindow(PitWallWindow):
    """Pit wall insight: one car's live state with LIVE / EST / AI tagged fields."""

    REFRESH_MS = 66  # ~15 Hz is plenty for reading numbers

    def __init__(self):
        self._latest = None
        self._driver_order = []
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Car Detail")
        self.resize(470, 860)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(self.REFRESH_MS)

    # ── UI ───────────────────────────────────────────────────────────────

    def setup_ui(self):
        self.setStyleSheet(STYLE)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root = QWidget()
        root.setObjectName("root")
        scroll.setWidget(root)
        self.setCentralWidget(scroll)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Driver picker
        controls = QHBoxLayout()
        self.driver_combo = QComboBox()
        self.driver_combo.setPlaceholderText("Driver")
        self.driver_combo.currentTextChanged.connect(lambda _: self._refresh())
        self.follow_check = QCheckBox("Follow leaderboard selection")
        self.follow_check.setChecked(True)
        self.follow_check.setToolTip("Switch to whichever driver you click on the replay's leaderboard.")
        controls.addWidget(self.driver_combo)
        controls.addSpacing(8)
        controls.addWidget(self.follow_check)
        controls.addStretch()
        layout.addLayout(controls)

        self.waiting = QLabel("Waiting for the replay… start a race replay to see car data.")
        self.waiting.setObjectName("waiting")
        self.waiting.setWordWrap(True)
        layout.addWidget(self.waiting)

        # Header: driver, position, lap
        self.header = _Card()
        head = QHBoxLayout()
        self.team_bar = QFrame()
        self.team_bar.setFixedSize(6, 44)
        self.code_label = QLabel("—")
        self.code_label.setFont(_mono(22))
        self.position_label = QLabel("")
        self.position_label.setFont(_mono(20))
        self.lap_label = QLabel("")
        self.lap_label.setObjectName("rowLabel")
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "QLabel { color: #f59e0b; border: 1px solid #f59e0b; border-radius: 9px;"
            " padding: 1px 8px; font-size: 10px; font-weight: 700; }")
        self.status_label.hide()
        head_text = QVBoxLayout()
        head_text.setSpacing(0)
        head_text.addWidget(self.code_label)
        head_text.addWidget(self.lap_label)
        head.addWidget(self.team_bar)
        head.addSpacing(8)
        head.addLayout(head_text)
        head.addStretch()
        head.addWidget(self.status_label)
        head.addSpacing(8)
        head.addWidget(self.position_label)
        self.header.layout_.addLayout(head)
        layout.addWidget(self.header)

        # Car + live telemetry
        self.telemetry_card = _Card("Telemetry")
        body = QHBoxLayout()
        body.setSpacing(14)
        self.schematic = CarSchematic()
        body.addWidget(self.schematic)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        speed_box = QVBoxLayout()
        speed_box.setSpacing(0)
        self.speed_label = QLabel("—")
        self.speed_label.setFont(_mono(26))
        speed_unit = QLabel("km/h")
        speed_unit.setObjectName("unit")
        speed_box.addWidget(self.speed_label)
        speed_box.addWidget(speed_unit)
        gear_box = QVBoxLayout()
        gear_box.setSpacing(0)
        self.gear_label = QLabel("—")
        self.gear_label.setFont(_mono(26))
        gear_unit = QLabel("gear")
        gear_unit.setObjectName("unit")
        gear_box.addWidget(self.gear_label)
        gear_box.addWidget(gear_unit)
        big = QHBoxLayout()
        big.addLayout(speed_box)
        big.addSpacing(16)
        big.addLayout(gear_box)
        big.addStretch()
        big.addWidget(TagChip(LIVE), alignment=Qt.AlignTop)
        grid.addLayout(big, 0, 0, 1, 3)

        self.speed_meter = Meter("#eef0f2")
        grid.addWidget(self.speed_meter, 1, 0, 1, 3)
        self.throttle_meter, self.throttle_value = self._meter_row(grid, 2, "Throttle", "#22c55e")
        self.brake_meter, self.brake_value = self._meter_row(grid, 3, "Brake", "#ef4444")
        drs_label = QLabel("DRS")
        drs_label.setObjectName("rowLabel")
        self.drs_value = QLabel("—")
        self.drs_value.setObjectName("rowValue")
        grid.addWidget(drs_label, 4, 0)
        grid.addWidget(self.drs_value, 4, 1)
        grid.addWidget(TagChip(LIVE), 4, 2, alignment=Qt.AlignRight)
        grid.setRowStretch(5, 1)
        body.addLayout(grid, 1)
        self.telemetry_card.layout_.addLayout(body)
        layout.addWidget(self.telemetry_card)

        # Tyres
        self.tyre_card = _Card("Tyres")
        tgrid = self._grid()
        self.compound_value = self._row(tgrid, 0, "Compound", LIVE,
                                        tip="Tyre compound and laps on this set, from timing data.")
        self.health_meter = Meter("#22c55e")
        self.health_value = QLabel("—")
        self.health_value.setObjectName("rowValue")
        health_box = QHBoxLayout()
        health_box.addWidget(self.health_meter, 1)
        health_box.addWidget(self.health_value)
        self._row(tgrid, 1, "Health", AI, widget=health_box,
                  tip="Remaining tyre life from the Bayesian tyre model.")
        self.wear_value = self._row(tgrid, 2, "Wear rate", AI,
                                    tip="Lap time lost per lap to tyre wear, fitted by the model.")
        self.lost_value = self._row(tgrid, 3, "Lost so far", AI,
                                    tip="Total lap time lost to wear on this set (model).")
        self.left_value = self._row(tgrid, 4, "Worn out in", AI,
                                    tip="Laps until the model's wear limit for this compound.")
        self.tyre_card.layout_.addLayout(tgrid)
        layout.addWidget(self.tyre_card)

        # Pace & race
        self.race_card = _Card("Pace & race")
        rgrid = self._grid()
        self.last_lap_value = self._row(rgrid, 0, "Last lap", LIVE, tip="Official lap time.")
        self.next_lap_value = self._row(
            rgrid, 1, "Next lap", AI,
            tip="Last clean lap on these tyres + one more lap of wear − fuel burned.\n"
                "The ± range is the model's 95% interval.")
        self.gap_ahead_value = self._row(
            rgrid, 2, "Gap ahead", EST,
            tip="Distance to the car ahead divided by this car's average lap speed.")
        self.gap_behind_value = self._row(
            rgrid, 3, "Gap behind", EST,
            tip="Distance to the car behind divided by this car's average lap speed.")
        self.fuel_value = self._row(
            rgrid, 4, "Fuel load", EST,
            tip="Rough estimate, not a measurement. Assumes a full 110 kg at the start,\n"
                "burned evenly to ~1 kg at the flag. Safety-car laps burn less, so it\n"
                "reads low after long caution periods. Teams don't publish real fuel loads.")
        self.race_card.layout_.addLayout(rgrid)
        layout.addWidget(self.race_card)

        legend = QLabel(
            f"<span style='color:{TAG_COLOURS[LIVE]}'>■ LIVE</span> recorded timing &amp; telemetry · "
            f"<span style='color:{TAG_COLOURS[EST]}'>■ EST</span> simple estimate · "
            f"<span style='color:{TAG_COLOURS[AI]}'>■ AI</span> model prediction")
        legend.setObjectName("legend")
        legend.setWordWrap(True)
        layout.addWidget(legend)
        layout.addStretch()

        self._set_cards_visible(False)

    @staticmethod
    def _grid() -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)
        return grid

    @staticmethod
    def _row(grid, row, label, tag, widget=None, tip=None):
        name = QLabel(label)
        name.setObjectName("rowLabel")
        grid.addWidget(name, row, 0)
        if widget is None:
            value = QLabel("—")
            value.setObjectName("rowValue")
            grid.addWidget(value, row, 1)
        elif isinstance(widget, QWidget):
            value = widget
            grid.addWidget(value, row, 1)
        else:
            value = widget
            grid.addLayout(value, row, 1)
        chip = TagChip(tag)
        if tip:
            name.setToolTip(tip)
            chip.setToolTip(f"{tip}\n\n{TAG_HELP[tag]}")
        grid.addWidget(chip, row, 2, alignment=Qt.AlignRight)
        return value

    @staticmethod
    def _meter_row(grid, row, label, colour):
        name = QLabel(label)
        name.setObjectName("rowLabel")
        meter = Meter(colour)
        value = QLabel("—")
        value.setObjectName("rowValue")
        value.setMinimumWidth(42)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        box = QHBoxLayout()
        box.addWidget(meter, 1)
        box.addWidget(value)
        grid.addWidget(name, row, 0)
        grid.addLayout(box, row, 1)
        grid.addWidget(TagChip(LIVE), row, 2, alignment=Qt.AlignRight)
        return meter, value

    def _set_cards_visible(self, visible: bool):
        for card in (self.header, self.telemetry_card, self.tyre_card, self.race_card):
            card.setVisible(visible)
        self.waiting.setVisible(not visible)

    # ── Data ─────────────────────────────────────────────────────────────

    def on_telemetry_data(self, data):
        # Just keep the newest message; the timer redraws at a readable rate.
        self._latest = data

    def on_connection_status_changed(self, status):
        if status != "Connected":
            self._set_cards_visible(False)

    def _update_driver_list(self, order):
        if order == self._driver_order:
            return
        current = self.driver_combo.currentText()
        self.driver_combo.blockSignals(True)
        self.driver_combo.clear()
        self.driver_combo.addItems(order)
        if current in order:
            self.driver_combo.setCurrentText(current)
        elif order:
            self.driver_combo.setCurrentIndex(0)
        self.driver_combo.blockSignals(False)
        self._driver_order = order

    def _refresh(self):
        data = self._latest
        frame = (data or {}).get("frame") or {}
        drivers = frame.get("drivers") or {}
        if not drivers:
            return

        def position_of(code):
            try:
                return int(drivers[code].get("position") or 99)
            except (TypeError, ValueError):
                return 99

        order = sorted(drivers, key=position_of)
        self._update_driver_list(order)

        if self.follow_check.isChecked():
            selected = [c for c in (data.get("selected_drivers") or []) if c in drivers]
            if selected and selected[-1] != self.driver_combo.currentText():
                self.driver_combo.blockSignals(True)
                self.driver_combo.setCurrentText(selected[-1])
                self.driver_combo.blockSignals(False)

        code = self.driver_combo.currentText()
        car = drivers.get(code)
        if not car:
            return
        self._set_cards_visible(True)

        colours = data.get("driver_colors") or {}
        team = colours.get(code, "#888888")
        session = data.get("session_data") or {}
        total_laps = session.get("total_laps")
        lap = car.get("lap") or 1
        position = position_of(code)

        # Header
        self.team_bar.setStyleSheet(f"background: {team}; border-radius: 3px;")
        self.code_label.setText(code)
        self.code_label.setStyleSheet(f"color: {team};")
        self.position_label.setText(f"P{position}" if position < 99 else "")
        self.lap_label.setText(f"Lap {lap}/{total_laps}" if total_laps else f"Lap {lap}")
        if car.get("in_pit"):
            self.status_label.setText("IN PIT")
            self.status_label.show()
        else:
            self.status_label.hide()

        # LIVE telemetry
        speed = float(car.get("speed") or 0.0)
        throttle = max(0.0, min(100.0, float(car.get("throttle") or 0.0)))
        brake = brake_fraction(car.get("brake"))
        drs = drs_state(car.get("drs"))
        compound = compound_name(car.get("tyre"))
        self.speed_label.setText(f"{speed:.0f}")
        self.gear_label.setText(str(car.get("gear") or "N"))
        self.speed_meter.set_value(speed / 360.0)
        self.throttle_meter.set_value(throttle / 100.0)
        self.throttle_value.setText(f"{throttle:.0f}%")
        self.brake_meter.set_value(brake)
        self.brake_value.setText("ON" if brake > 0.05 else "OFF")
        self.drs_value.setText(drs)
        self.drs_value.setStyleSheet(f"color: {DRS_COLOURS[drs]};")
        self.schematic.set_state(team, compound, brake, drs)

        tyre_age = car.get("tyre_life")
        try:
            age_text = f" · {int(float(tyre_age))} laps old"
        except (TypeError, ValueError):
            age_text = ""
        self.compound_value.setText(f"{compound.title()}{age_text}")
        self.compound_value.setStyleSheet(f"color: {COMPOUND_COLOURS.get(compound, TEXT)};")

        # AI: tyre model
        model = (data.get("tyre_model") or {}).get(code)
        laps_remaining = (int(total_laps) - int(lap) + 1) if total_laps else None
        if model:
            health = int(model.get("health", 0))
            colour = "#22c55e" if health >= 60 else "#f59e0b" if health >= 30 else "#ef4444"
            self.health_meter.set_value(health / 100.0, colour)
            self.health_value.setText(f"{health}%")
            self.wear_value.setText(f"+{model.get('wear_s_per_lap', 0):.3f} s / lap")
            self.lost_value.setText(f"+{model.get('time_lost_s', 0):.2f} s")
            self.left_value.setText(format_laps_left(model.get("laps_left"), laps_remaining))
            if model.get("next_lap_s"):
                spread = (model["next_lap_high_s"] - model["next_lap_low_s"]) / 2
                self.next_lap_value.setText(f"{format_lap_time(model['next_lap_s'])}  ± {spread:.2f} s")
            else:
                self.next_lap_value.setText("Needs a clean lap on these tyres")
        else:
            self.health_meter.set_value(0)
            for label in (self.health_value, self.wear_value, self.lost_value, self.left_value):
                label.setText("—")
            self.next_lap_value.setText("Model unavailable")

        # LIVE: last lap time
        entries = (data.get("lap_times") or {}).get(code)
        last = last_completed_lap(entries, lap)
        self.last_lap_value.setText(format_lap_time(last["time_s"]) if last else "—")

        # EST: gaps from track distance and this car's average lap speed
        circuit_m = data.get("circuit_length_m")
        avg_speed = average_speed_mps(circuit_m, last["time_s"]) if last else None
        ahead, behind = self._neighbours(drivers, code)
        self.gap_ahead_value.setText(
            self._gap_text(drivers, code, ahead, avg_speed, circuit_m) if ahead else "Leading")
        self.gap_behind_value.setText(
            self._gap_text(drivers, code, behind, avg_speed, circuit_m) if behind else "Last car")

        # EST: fuel
        fuel = estimate_fuel_kg(lap, car.get("rel_dist"), total_laps)
        self.fuel_value.setText(f"≈ {fuel:.0f} kg" if fuel is not None else "—")

    @staticmethod
    def _neighbours(drivers, code):
        """
        Cars directly ahead and behind in the running order. Sorted by position
        rather than looking up position +/- 1, so gaps in the numbering (retired
        cars, missing data) still find the right neighbour. None at either end.
        """
        def pos(c):
            try:
                return int(drivers[c].get("position") or 0)
            except (TypeError, ValueError):
                return 0
        order = sorted((c for c in drivers if pos(c) > 0), key=pos)
        if code not in order:
            return None, None
        i = order.index(code)
        return (order[i - 1] if i > 0 else None,
                order[i + 1] if i + 1 < len(order) else None)

    @staticmethod
    def _gap_text(drivers, code, other, avg_speed, circuit_m) -> str:
        try:
            gap_m = abs(float(drivers[other]["dist"]) - float(drivers[code]["dist"]))
        except (KeyError, TypeError, ValueError):
            return "—"
        try:
            lap_m = float(circuit_m)
        except (TypeError, ValueError):
            lap_m = None
        if lap_m and gap_m >= lap_m:
            laps = int(gap_m // lap_m)
            return f"{laps} lap{'s' if laps > 1 else ''} ({other})"
        seconds = estimate_gap_s(gap_m, avg_speed or FALLBACK_SPEED_MPS)
        if seconds is None:
            return "—"
        # No sign: the row label already says ahead or behind.
        return f"{seconds:.1f} s  ({other})"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Car Detail")
    window = CarDetailWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
