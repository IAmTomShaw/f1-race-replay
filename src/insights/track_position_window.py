"""
Track Position Map insight.

Displays all drivers as dots on a smooth circle representing the circuit,
positioned according to their current distance into the lap.
"""

import sys
import math
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QPolygonF
)
from src.gui.pit_wall_window import PitWallWindow

# Visually distinct colours assigned to drivers in order of first appearance
_PALETTE = [
    "#E8002D", "#FF8000", "#00D2BE", "#1565C0", "#F596C8",
    "#DC0000", "#B6BABD", "#5E8FAA", "#2293D1", "#FFF500",
    "#006F62", "#900000", "#0090FF", "#FF87BC", "#64C4FF",
    "#358C75", "#AAAAAA", "#6CD3BF", "#ABB7C4", "#C92D4B",
]

_TRACK_BG          = QColor("#282828")
_TRACK_RING_DARK   = QColor("#303030")
_TRACK_RING_LINE   = QColor("#303030")
_SF_LINE_COLOR     = QColor("#FFFFFF")
_LABEL_SHADOW      = QColor(0, 0, 0, 180)
_LEADER_ARROW      = QColor("#FFD700")
_DIST_MARKER_COLOR = QColor("#606060")
_DIST_LABEL_COLOR  = QColor("#585858")


class _TrackMapWidget(QWidget):
    """Custom widget that paints a circular track map with driver dots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.driver_positions: dict[str, float] = {}   # code → fraction 0–1
        self.driver_colors: dict[str, str] = {}        # code → hex colour
        self.leader_code: str | None = None
        self.circuit_length_m: float | None = None
        self.setMinimumSize(420, 420)

    def update_positions(
        self,
        positions: dict,
        colors: dict,
        leader_code: str | None = None,
        circuit_length_m: float | None = None,
    ) -> None:
        self.driver_positions = positions
        self.driver_colors = colors
        self.leader_code = leader_code
        self.circuit_length_m = circuit_length_m
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        margin = 72
        radius = min(w, h) / 2 - margin

        # ── background ──────────────────────────────────────────────────
        painter.fillRect(self.rect(), _TRACK_BG)

        # ── track ring (thick dark band) ────────────────────────────────
        ring_pen = QPen(_TRACK_RING_DARK, 22)
        ring_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # ── track centre line ───────────────────────────────────────────
        painter.setPen(QPen(_TRACK_RING_LINE, 2))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # ── start / finish tick (top of circle = 0 % into lap) ──────────
        sf_angle = -math.pi / 2
        self._draw_sf_line(painter, cx, cy, radius, sf_angle)

        # ── distance markers every 1 000 m ──────────────────────────────
        self._draw_distance_markers(painter, cx, cy, radius, sf_angle)

        # ── drivers ─────────────────────────────────────────────────────
        for code, fraction in self.driver_positions.items():
            angle = sf_angle + fraction * 2 * math.pi
            dx = cx + radius * math.cos(angle)
            dy = cy + radius * math.sin(angle)
            color = QColor(self.driver_colors.get(code, "#FFFFFF"))
            self._draw_driver(painter, dx, dy, angle, code, color, cx, cy, radius)

        # ── leader arrow ─────────────────────────────────────────────────
        if self.leader_code and self.leader_code in self.driver_positions:
            leader_fraction = self.driver_positions[self.leader_code]
            leader_angle = sf_angle + leader_fraction * 2 * math.pi
            self._draw_leader_arrow(painter, leader_angle, cx, cy, radius)

        painter.end()

    # ------------------------------------------------------------------
    def _draw_sf_line(self, painter, cx, cy, radius, angle):
        half = 13
        nx = math.cos(angle)
        ny = math.sin(angle)
        # perpendicular direction (tangent to circle)
        tx = -ny
        ty = nx
        mid_x = cx + radius * nx
        mid_y = cy + radius * ny
        painter.setPen(QPen(_SF_LINE_COLOR, 2))
        painter.drawLine(
            QPointF(mid_x - tx * half, mid_y - ty * half),
            QPointF(mid_x + tx * half, mid_y + ty * half),
        )
        # small "S/F" label inside the circle near the tick
        painter.setPen(QPen(QColor("#888888")))
        font = QFont("Arial", 7)
        painter.setFont(font)
        label_r = radius - 22
        painter.drawText(
            QPointF(cx + label_r * nx - 8, cy + label_r * ny + 4),
            "S/F",
        )

    def _draw_distance_markers(self, painter, cx, cy, radius, sf_angle):
        """Draw tick marks and kilometre labels every 1 000 m, like clock-face hour marks."""
        if not self.circuit_length_m or self.circuit_length_m <= 0:
            return

        step_m = 1000
        n_marks = int(self.circuit_length_m // step_m)

        font = QFont("Arial", 6)
        painter.setFont(font)
        fm = QFontMetrics(font)

        for i in range(1, n_marks + 1):
            dist = i * step_m
            if dist >= self.circuit_length_m:
                break

            fraction = dist / self.circuit_length_m
            angle = sf_angle + fraction * 2 * math.pi
            nx = math.cos(angle)
            ny = math.sin(angle)
            # tangent direction (perpendicular to radius)
            tx = -ny
            ty = nx

            mid_x = cx + radius * nx
            mid_y = cy + radius * ny
            half = 8

            painter.setPen(QPen(_DIST_MARKER_COLOR, 1.5))
            painter.drawLine(
                QPointF(mid_x - tx * half, mid_y - ty * half),
                QPointF(mid_x + tx * half, mid_y + ty * half),
            )

            # kilometre label placed just inside the ring
            font = QFont("Arial", 12)
            painter.setFont(font)
            fm = QFontMetrics(font)

            label = f"{i}K"
            tw = fm.horizontalAdvance(label)
            th = fm.ascent()
            label_r = radius - 20
            lx = cx + label_r * nx - tw / 2
            ly = cy + label_r * ny + th / 2
            painter.setPen(QPen(_DIST_LABEL_COLOR))
            painter.drawText(QPointF(lx, ly), label)

    def _draw_leader_arrow(self, painter, angle, cx, cy, radius):
        """Draw a gold arrow inside the track ring pointing outward toward the race leader."""
        nx = math.cos(angle)
        ny = math.sin(angle)
        px = -math.sin(angle)   # perpendicular (tangent)
        py = math.cos(angle)

        # Tip of the arrow sits just inside the ring; base pulls further inward
        tip_r   = radius - 10
        base_r  = radius - 26
        half_w  = 7

        tip_x  = cx + tip_r  * nx
        tip_y  = cy + tip_r  * ny
        base_x = cx + base_r * nx
        base_y = cy + base_r * ny

        triangle = QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(base_x + px * half_w, base_y + py * half_w),
            QPointF(base_x - px * half_w, base_y - py * half_w),
        ])

        # Drop shadow for depth
        shadow_color = QColor(0, 0, 0, 140)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow_color))
        offset = QPointF(1.5, 1.5)
        shadow_tri = QPolygonF([p + offset for p in triangle])
        painter.drawPolygon(shadow_tri)

        # Gold arrow
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(_LEADER_ARROW))
        painter.drawPolygon(triangle)

    def _draw_driver(self, painter, x, y, angle, code, color, cx, cy, radius):
        dot_r = 7

        # glow / halo behind the dot
        halo = QColor(color)
        halo.setAlpha(60)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(x, y), dot_r + 4, dot_r + 4)

        # coloured dot
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x, y), dot_r, dot_r)

        # driver code label — push outward from circle centre
        font = QFont("Arial", 7, QFont.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(code)
        th = fm.ascent()

        outward = dot_r + 10
        nx = math.cos(angle)
        ny = math.sin(angle)
        lx = cx + (radius + outward) * nx - tw / 2
        ly = cy + (radius + outward) * ny + th / 2

        # shadow for readability
        painter.setPen(QPen(_LABEL_SHADOW))
        for ox, oy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            painter.drawText(QPointF(lx + ox, ly + oy), code)

        painter.setPen(QPen(color))
        painter.drawText(QPointF(lx, ly), code)


# ──────────────────────────────────────────────────────────────────────────────

class TrackPositionWindow(PitWallWindow):
    """
    Insight window showing all drivers plotted on a circular track map,
    positioned by their current distance into the lap.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Track Position Map")
        self.setMinimumSize(520, 560)
        self._circuit_length_m: float | None = None
        self._driver_colors: dict[str, str] = {}
        self._color_idx = 0

    # ── PitWallWindow interface ───────────────────────────────────────

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # ── status bar ──────────────────────────────────────────────
        status_row = QHBoxLayout()
        status_row.setSpacing(16)

        self._lap_label = self._status_label("Lap: —")
        self._track_label = self._status_label("Track: —")
        self._circuit_label = self._status_label("Circuit: —")

        status_row.addWidget(self._lap_label)
        status_row.addStretch()
        status_row.addWidget(self._track_label)
        status_row.addStretch()
        status_row.addWidget(self._circuit_label)
        root.addLayout(status_row)

        # ── map ──────────────────────────────────────────────────────
        self._map = _TrackMapWidget()
        root.addWidget(self._map, stretch=1)

    def on_telemetry_data(self, data):
        if data.get("circuit_length_m"):
            self._circuit_length_m = float(data["circuit_length_m"])
            self._circuit_label.setText(f"Circuit: {self._circuit_length_m:.0f} m")

        if "track_status" in data:
            self._track_label.setText(f"Track: {data['track_status']}")

        if "driver_colors" in data:
            self._driver_colors.update(data["driver_colors"])

        frame = data.get("frame")
        if not frame or "drivers" not in frame:
            return

        drivers = frame["drivers"]

        max_lap = max((d.get("lap", 0) for d in drivers.values()), default=0)
        if max_lap:
            self._lap_label.setText(f"Lap: {max_lap}")

        if not self._circuit_length_m:
            return

        positions: dict[str, float] = {}
        for code, info in drivers.items():
            self._ensure_color(code)
            dist = info.get("dist", 0.0)
            positions[code] = (dist % self._circuit_length_m) / self._circuit_length_m

        leader_code = next(
            (code for code, info in drivers.items() if info.get("position") == 1),
            max(drivers, key=lambda c: drivers[c].get("dist", 0.0)) if drivers else None,
        )
        self._map.update_positions(positions, self._driver_colors, leader_code, self._circuit_length_m)

    def on_connection_status_changed(self, status):
        if status == "Disconnected":
            self._track_label.setText("Track: Disconnected")
        elif status == "Connected":
            self._track_label.setText("Track: Connected")

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _status_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Arial", 10))
        lbl.setStyleSheet("color: #cccccc;")
        return lbl

    def _ensure_color(self, code: str) -> None:
        if code not in self._driver_colors:
            self._driver_colors[code] = _PALETTE[self._color_idx % len(_PALETTE)]
            self._color_idx += 1


# ──────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Track Position Map")
    window = TrackPositionWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
