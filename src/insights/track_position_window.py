"""
Track Position Map insight.

Plots driver positions on the circuit in real-time. Two view modes are
available: the actual circuit layout, or a circular schematic.
"""

import sys
import math
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QPolygonF,
    QPainterPath
)
from src.gui.pit_wall_window import PitWallWindow

# Visually distinct colours assigned to drivers in order of first appearance
_PALETTE = [
    "#E8002D", "#FF8000", "#00D2BE", "#1565C0", "#F596C8",
    "#DC0000", "#B6BABD", "#5E8FAA", "#2293D1", "#FFF500",
    "#006F62", "#900000", "#0090FF", "#FF87BC", "#64C4FF",
    "#358C75", "#AAAAAA", "#6CD3BF", "#ABB7C4", "#C92D4B",
]

_TRACK_BG          = QColor("#1a1a1a")
_TRACK_ROAD        = QColor("#383838")
_TRACK_EDGE        = QColor("#555555")
_TRACK_CENTRE      = QColor("#2a2a2a")
_TRACK_RING_DARK   = QColor("#303030")
_TRACK_RING_LINE   = QColor("#303030")
_SF_LINE_COLOR     = QColor("#FFFFFF")
_LABEL_SHADOW      = QColor(0, 0, 0, 180)
_LEADER_ARROW      = QColor("#FFD700")
_DIST_MARKER_COLOR = QColor("#606060")
_DIST_LABEL_COLOR  = QColor("#585858")


class _TrackMapWidget(QWidget):
    """Custom widget that paints the track map with driver dots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.driver_positions: dict[str, float] = {}   # code -> fraction 0-1
        self.driver_colors: dict[str, str] = {}        # code -> hex colour
        self.leader_code: str | None = None
        self.circuit_length_m: float | None = None
        self.setMinimumSize(420, 420)

        self.force_circle: bool = False

        # Real-track geometry
        self.has_real_track: bool = False
        # Rotated world coordinates (center, inner, outer)
        self._center_xs: list[float] = []
        self._center_ys: list[float] = []
        self._inner_xs: list[float] = []
        self._inner_ys: list[float] = []
        self._outer_xs: list[float] = []
        self._outer_ys: list[float] = []
        # Cumulative fractional distances along center line [0.0 ... 1.0]
        self._cum_fracs: list[float] = []

    # -- public API -------------------------------------------------------

    def set_track_geometry(
        self,
        x_center: list[float],
        y_center: list[float],
        x_inner: list[float],
        y_inner: list[float],
        x_outer: list[float],
        y_outer: list[float],
        rotation_deg: float = 0.0,
    ) -> None:
        """Set track outline from FastF1 reference-lap coordinates."""
        if len(x_center) < 3:
            return

        # Rotate around bbox midpoint (matches the Arcade window's world_to_screen)
        all_xs = list(x_center) + list(x_inner) + list(x_outer)
        all_ys = list(y_center) + list(y_inner) + list(y_outer)
        cx = (min(all_xs) + max(all_xs)) / 2
        cy = (min(all_ys) + max(all_ys)) / 2
        rad = math.radians(rotation_deg)
        cos_r, sin_r = math.cos(rad), math.sin(rad)

        def rotate_list(xs, ys):
            rxs, rys = [], []
            for x, y in zip(xs, ys):
                dx, dy = x - cx, y - cy
                rxs.append(cx + dx * cos_r - dy * sin_r)
                rys.append(cy + dx * sin_r + dy * cos_r)
            return rxs, rys

        self._center_xs, self._center_ys = rotate_list(x_center, y_center)
        self._inner_xs, self._inner_ys = rotate_list(x_inner, y_inner)
        self._outer_xs, self._outer_ys = rotate_list(x_outer, y_outer)

        # Cumulative fractional distances along center polyline
        cum = [0.0]
        for i in range(1, len(self._center_xs)):
            seg = math.hypot(
                self._center_xs[i] - self._center_xs[i - 1],
                self._center_ys[i] - self._center_ys[i - 1],
            )
            cum.append(cum[-1] + seg)
        total = cum[-1] if cum[-1] > 0 else 1.0
        self._cum_fracs = [d / total for d in cum]

        self.has_real_track = True
        self.update()

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

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), _TRACK_BG)

        if self.has_real_track and not self.force_circle:
            self._paint_real_track(painter)
        else:
            self._paint_circle_track(painter)

        painter.end()

    # =====================================================================
    # Real track rendering
    # =====================================================================

    def _paint_real_track(self, painter: QPainter):
        w, h = self.width(), self.height()
        margin = 60

        # Bounding box of ALL coordinates (inner + outer)
        all_xs = self._inner_xs + self._outer_xs
        all_ys = self._inner_ys + self._outer_ys
        min_x, max_x = min(all_xs), max(all_xs)
        min_y, max_y = min(all_ys), max(all_ys)
        world_w = max_x - min_x or 1.0
        world_h = max_y - min_y or 1.0

        # Scale to fit widget (aspect-ratio preserving)
        available_w = w - 2 * margin
        available_h = h - 2 * margin
        scale = min(available_w / world_w, available_h / world_h)

        cx_off = w / 2
        cy_off = h / 2
        world_cx = (min_x + max_x) / 2
        world_cy = (min_y + max_y) / 2

        def to_widget(wx, wy):
            sx = cx_off + (wx - world_cx) * scale
            sy = cy_off - (wy - world_cy) * scale  # Y-flip
            return sx, sy

        # -- Draw filled road surface between inner and outer edges -------
        # Build a closed polygon: outer edge forward + inner edge reversed
        road_polygon = QPolygonF()
        for i in range(len(self._outer_xs)):
            sx, sy = to_widget(self._outer_xs[i], self._outer_ys[i])
            road_polygon.append(QPointF(sx, sy))
        for i in range(len(self._inner_xs) - 1, -1, -1):
            sx, sy = to_widget(self._inner_xs[i], self._inner_ys[i])
            road_polygon.append(QPointF(sx, sy))

        # Fill the road
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(_TRACK_ROAD))
        painter.drawPolygon(road_polygon)

        # -- Draw track edge lines (inner + outer) ------------------------
        edge_pen = QPen(_TRACK_EDGE, 2)
        painter.setPen(edge_pen)
        painter.setBrush(Qt.NoBrush)

        inner_path = QPainterPath()
        sx0, sy0 = to_widget(self._inner_xs[0], self._inner_ys[0])
        inner_path.moveTo(sx0, sy0)
        for i in range(1, len(self._inner_xs)):
            sx, sy = to_widget(self._inner_xs[i], self._inner_ys[i])
            inner_path.lineTo(sx, sy)
        inner_path.closeSubpath()
        painter.drawPath(inner_path)

        outer_path = QPainterPath()
        sx0, sy0 = to_widget(self._outer_xs[0], self._outer_ys[0])
        outer_path.moveTo(sx0, sy0)
        for i in range(1, len(self._outer_xs)):
            sx, sy = to_widget(self._outer_xs[i], self._outer_ys[i])
            outer_path.lineTo(sx, sy)
        outer_path.closeSubpath()
        painter.drawPath(outer_path)

        # -- Centre line (dashed, faint) ----------------------------------
        centre_pen = QPen(_TRACK_CENTRE, 1, Qt.DashLine)
        painter.setPen(centre_pen)
        centre_path = QPainterPath()
        sx0, sy0 = to_widget(self._center_xs[0], self._center_ys[0])
        centre_path.moveTo(sx0, sy0)
        for i in range(1, len(self._center_xs)):
            sx, sy = to_widget(self._center_xs[i], self._center_ys[i])
            centre_path.lineTo(sx, sy)
        centre_path.closeSubpath()
        painter.drawPath(centre_path)

        # -- Start / finish line ------------------------------------------
        if len(self._center_xs) >= 2:
            sfx, sfy = to_widget(self._center_xs[0], self._center_ys[0])
            si_x, si_y = to_widget(self._inner_xs[0], self._inner_ys[0])
            so_x, so_y = to_widget(self._outer_xs[0], self._outer_ys[0])
            # Draw S/F line across the track width
            painter.setPen(QPen(_SF_LINE_COLOR, 2))
            painter.drawLine(QPointF(si_x, si_y), QPointF(so_x, so_y))
            # S/F label
            painter.setPen(QPen(QColor("#888888")))
            painter.setFont(QFont("Arial", 7))
            painter.drawText(QPointF(sfx - 8, sfy - 14), "S/F")

        # -- Distance markers every 1000 m --------------------------------
        self._draw_real_distance_markers(painter, to_widget)

        # -- Drivers ------------------------------------------------------
        for code, fraction in self.driver_positions.items():
            sx, sy = self._pos_on_track(fraction, to_widget)
            color = QColor(self.driver_colors.get(code, "#FFFFFF"))
            self._draw_driver_dot(painter, sx, sy, code, color)

        # -- Leader arrow -------------------------------------------------
        if self.leader_code and self.leader_code in self.driver_positions:
            frac = self.driver_positions[self.leader_code]
            lx, ly = self._pos_on_track(frac, to_widget)
            idx = self._frac_to_index(frac)
            idx_next = (idx + 1) % len(self._center_xs)
            nx, ny = to_widget(self._center_xs[idx_next], self._center_ys[idx_next])
            angle = math.atan2(ny - ly, nx - lx)
            self._draw_leader_arrow_at(painter, lx, ly, angle)

    def _draw_real_distance_markers(self, painter, to_widget):
        if not self.circuit_length_m or self.circuit_length_m <= 0:
            return
        step_m = 1000
        n_marks = int(self.circuit_length_m // step_m)
        font = QFont("Arial", 10)
        painter.setFont(font)
        fm = QFontMetrics(font)

        for i in range(1, n_marks + 1):
            dist = i * step_m
            if dist >= self.circuit_length_m:
                break
            frac = dist / self.circuit_length_m
            sx, sy = self._pos_on_track(frac, to_widget)

            # Compute perpendicular for tick direction
            idx = self._frac_to_index(frac)
            idx_next = (idx + 1) % len(self._center_xs)
            nx, ny = to_widget(self._center_xs[idx_next], self._center_ys[idx_next])
            tx, ty = nx - sx, ny - sy
            tlen = math.hypot(tx, ty) or 1.0
            px, py = -ty / tlen, tx / tlen

            label = f"{i}K"
            tw = fm.horizontalAdvance(label)
            th = fm.ascent()
            lx = sx + px * 22 - tw / 2
            ly = sy + py * 22 + th / 2
            painter.setPen(QPen(_DIST_LABEL_COLOR))
            painter.drawText(QPointF(lx, ly), label)

    def _pos_on_track(self, fraction, to_widget):
        """Interpolate position along the center polyline for a given fraction [0-1]."""
        fraction = fraction % 1.0
        idx = self._frac_to_index(fraction)
        idx_next = (idx + 1) % len(self._center_xs)

        frac_lo = self._cum_fracs[idx]
        frac_hi = self._cum_fracs[idx_next] if idx_next != 0 else 1.0
        seg_frac = (fraction - frac_lo) / (frac_hi - frac_lo) if (frac_hi - frac_lo) > 0 else 0.0
        seg_frac = max(0.0, min(1.0, seg_frac))

        wx = self._center_xs[idx] + seg_frac * (self._center_xs[idx_next] - self._center_xs[idx])
        wy = self._center_ys[idx] + seg_frac * (self._center_ys[idx_next] - self._center_ys[idx])
        return to_widget(wx, wy)

    def _frac_to_index(self, fraction):
        """Binary search cumulative fraction list for the segment index."""
        lo, hi = 0, len(self._cum_fracs) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self._cum_fracs[mid] <= fraction:
                lo = mid + 1
            else:
                hi = mid
        return max(lo - 1, 0)

    # -- Shared drawing helpers -------------------------------------------

    def _draw_driver_dot(self, painter, x, y, code, color):
        dot_r = 7
        # Halo
        halo = QColor(color)
        halo.setAlpha(60)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(x, y), dot_r + 4, dot_r + 4)
        # Dot
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x, y), dot_r, dot_r)
        # Label
        font = QFont("Arial", 7, QFont.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(code)
        lx = x - tw / 2
        ly = y - dot_r - 6
        painter.setPen(QPen(_LABEL_SHADOW))
        for ox, oy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            painter.drawText(QPointF(lx + ox, ly + oy), code)
        painter.setPen(QPen(color))
        painter.drawText(QPointF(lx, ly), code)

    def _draw_leader_arrow_at(self, painter, x, y, angle):
        nx = math.cos(angle)
        ny = math.sin(angle)
        px = -math.sin(angle)
        py = math.cos(angle)
        tip_off, base_off, half_w = 18, 10, 7
        tip_x = x - nx * tip_off
        tip_y = y - ny * tip_off
        base_x = x - nx * (tip_off + base_off)
        base_y = y - ny * (tip_off + base_off)
        triangle = QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(base_x + px * half_w, base_y + py * half_w),
            QPointF(base_x - px * half_w, base_y - py * half_w),
        ])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
        painter.drawPolygon(QPolygonF([p + QPointF(1.5, 1.5) for p in triangle]))
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(_LEADER_ARROW))
        painter.drawPolygon(triangle)

    # =====================================================================
    # Circular track rendering
    # =====================================================================

    def _paint_circle_track(self, painter: QPainter):
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        margin = 72
        radius = min(w, h) / 2 - margin

        ring_pen = QPen(_TRACK_RING_DARK, 22)
        ring_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        painter.setPen(QPen(_TRACK_RING_LINE, 2))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        sf_angle = -math.pi / 2
        self._draw_sf_line(painter, cx, cy, radius, sf_angle)
        self._draw_distance_markers(painter, cx, cy, radius, sf_angle)

        for code, fraction in self.driver_positions.items():
            angle = sf_angle + fraction * 2 * math.pi
            dx = cx + radius * math.cos(angle)
            dy = cy + radius * math.sin(angle)
            color = QColor(self.driver_colors.get(code, "#FFFFFF"))
            self._draw_driver(painter, dx, dy, angle, code, color, cx, cy, radius)

        if self.leader_code and self.leader_code in self.driver_positions:
            leader_fraction = self.driver_positions[self.leader_code]
            leader_angle = sf_angle + leader_fraction * 2 * math.pi
            self._draw_leader_arrow(painter, leader_angle, cx, cy, radius)

    # -- Circle-mode helpers -----------------------------------------------

    def _draw_sf_line(self, painter, cx, cy, radius, angle):
        half = 13
        nx = math.cos(angle)
        ny = math.sin(angle)
        tx = -ny
        ty = nx
        mid_x = cx + radius * nx
        mid_y = cy + radius * ny
        painter.setPen(QPen(_SF_LINE_COLOR, 2))
        painter.drawLine(
            QPointF(mid_x - tx * half, mid_y - ty * half),
            QPointF(mid_x + tx * half, mid_y + ty * half),
        )
        painter.setPen(QPen(QColor("#888888")))
        font = QFont("Arial", 7)
        painter.setFont(font)
        label_r = radius - 22
        painter.drawText(
            QPointF(cx + label_r * nx - 8, cy + label_r * ny + 4), "S/F",
        )

    def _draw_distance_markers(self, painter, cx, cy, radius, sf_angle):
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
        nx = math.cos(angle)
        ny = math.sin(angle)
        px = -math.sin(angle)
        py = math.cos(angle)
        tip_r = radius - 10
        base_r = radius - 26
        half_w = 7
        tip_x = cx + tip_r * nx
        tip_y = cy + tip_r * ny
        base_x = cx + base_r * nx
        base_y = cy + base_r * ny
        triangle = QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(base_x + px * half_w, base_y + py * half_w),
            QPointF(base_x - px * half_w, base_y - py * half_w),
        ])
        shadow_color = QColor(0, 0, 0, 140)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow_color))
        painter.drawPolygon(QPolygonF([p + QPointF(1.5, 1.5) for p in triangle]))
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(_LEADER_ARROW))
        painter.drawPolygon(triangle)

    def _draw_driver(self, painter, x, y, angle, code, color, cx, cy, radius):
        dot_r = 7
        halo = QColor(color)
        halo.setAlpha(60)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(x, y), dot_r + 4, dot_r + 4)
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x, y), dot_r, dot_r)
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
        painter.setPen(QPen(_LABEL_SHADOW))
        for ox, oy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            painter.drawText(QPointF(lx + ox, ly + oy), code)
        painter.setPen(QPen(color))
        painter.drawText(QPointF(lx, ly), code)


# -------------------------------------------------------------------------

class TrackPositionWindow(PitWallWindow):
    """
    Insight window showing all drivers plotted on a track map.
    Renders real circuit shape when geometry is available, else a circle.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Track Position Map")
        self.setMinimumSize(520, 560)
        self._circuit_length_m: float | None = None
        self._driver_colors: dict[str, str] = {}
        self._color_idx = 0
        self._geometry_received = False

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        status_row = QHBoxLayout()
        status_row.setSpacing(16)
        self._lap_label = self._status_label("Lap: —")
        self._track_label = self._status_label("Track: —")
        self._circuit_label = self._status_label("Circuit: —")

        # View mode toggle
        _btn_active = (
            "QPushButton { background: #555; color: #fff; border: 1px solid #777; "
            "padding: 3px 10px; font-size: 10px; border-radius: 0px; }"
        )
        _btn_inactive = (
            "QPushButton { background: #2a2a2a; color: #888; border: 1px solid #555; "
            "padding: 3px 10px; font-size: 10px; border-radius: 0px; }"
        )
        self._btn_style_active = _btn_active
        self._btn_style_inactive = _btn_inactive

        self._btn_real = QPushButton("Real Track")
        self._btn_real.setFixedHeight(24)
        self._btn_real.setStyleSheet(_btn_inactive)
        self._btn_real.clicked.connect(lambda: self._set_view_mode("real"))

        self._btn_schematic = QPushButton("Circular")
        self._btn_schematic.setFixedHeight(24)
        self._btn_schematic.setStyleSheet(_btn_active) # default active
        self._btn_schematic.clicked.connect(lambda: self._set_view_mode("schematic"))

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)
        toggle_row.addWidget(self._btn_schematic)
        toggle_row.addWidget(self._btn_real)

        status_row.addWidget(self._lap_label)
        status_row.addStretch()
        status_row.addWidget(self._track_label)
        status_row.addStretch()
        status_row.addLayout(toggle_row)
        status_row.addStretch()
        status_row.addWidget(self._circuit_label)
        root.addLayout(status_row)

        self._map = _TrackMapWidget()
        root.addWidget(self._map, stretch=1)

    def _set_view_mode(self, mode: str):
        """Toggle between Real Track and Schematic circle views."""
        is_schematic = (mode == "schematic")
        self._map.force_circle = is_schematic
        self._btn_real.setStyleSheet(
            self._btn_style_inactive if is_schematic else self._btn_style_active
        )
        self._btn_schematic.setStyleSheet(
            self._btn_style_active if is_schematic else self._btn_style_inactive
        )
        self._map.update()

    def on_telemetry_data(self, data):
        if data.get("circuit_length_m"):
            self._circuit_length_m = float(data["circuit_length_m"])
            self._circuit_label.setText(f"Circuit: {self._circuit_length_m:.0f} m")

        if "track_status" in data:
            self._track_label.setText(f"Track: {data['track_status']}")

        if "driver_colors" in data:
            self._driver_colors.update(data["driver_colors"])

        # Ingest track geometry once
        if not self._geometry_received and "track_geometry" in data:
            geo = data["track_geometry"]
            x_center = geo.get("x", [])
            y_center = geo.get("y", [])
            x_inner = geo.get("x_inner", [])
            y_inner = geo.get("y_inner", [])
            x_outer = geo.get("x_outer", [])
            y_outer = geo.get("y_outer", [])
            rotation = geo.get("rotation_deg", 0.0)
            if x_center and y_center and x_inner and x_outer:
                self._map.set_track_geometry(
                    x_center, y_center,
                    x_inner, y_inner,
                    x_outer, y_outer,
                    rotation,
                )
                self._geometry_received = True

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
            if "fraction" in info:
                positions[code] = info["fraction"]
            else:
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


# -------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Track Position Map")
    window = TrackPositionWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
