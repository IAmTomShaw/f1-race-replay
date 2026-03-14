import math
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.pit_wall_window import PitWallWindow


class TyreHologramCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(420)
        self.health = 0
        self.driver_code = "-"
        self.compound = "UNKNOWN"
        self.laps_on_tyre = 0
        self.tyre_life = 0
        self.expected_delta = 0.0
        self.uncertainty = 0.0
        self._model_points = []
        self._model_depths = []
        self._model_edges = []
        self._model_faces = []
        self._model_uvs = []
        self._model_verts = []
        self._model_texture = None
        self._model_label = "model: unavailable"
        self._model_color = QColor(80, 220, 255)
        self._yaw_deg = 0.0
        self._pitch_deg = 0.0
        self._corner_stats = {
            "FL": {"health": 99, "temp_c": 95},
            "FR": {"health": 98, "temp_c": 96},
            "RL": {"health": 97, "temp_c": 93},
            "RR": {"health": 96, "temp_c": 94},
        }
        self._load_real_model()

    def set_data(
        self,
        driver_code,
        health,
        compound,
        laps_on_tyre,
        tyre_life,
        expected_delta=0.0,
        uncertainty=0.0,
        corner_stats=None,
    ):
        self.driver_code = driver_code or "-"
        self.health = int(max(0, min(100, health or 0)))
        self.compound = str(compound or "UNKNOWN")
        self.laps_on_tyre = int(laps_on_tyre or 0)
        self.tyre_life = int(round(tyre_life or 0))
        self.expected_delta = float(expected_delta or 0.0)
        self.uncertainty = float(uncertainty or 0.0)
        if isinstance(corner_stats, dict):
            self._corner_stats = corner_stats
        self.update()

    def _health_color(self, h=None):
        h = self.health if h is None else int(max(0, min(100, h)))
        if h < 80:
            return QColor(240, 60, 60)   # red
        if h < 95:
            return QColor(230, 210, 55)  # yellow
        return QColor(20, 220, 120)      # green

    def _load_real_model(self):
        candidates = []
        env_path = os.environ.get("F1_HOLOGRAM_MODEL")
        if env_path:
            candidates.append(env_path)
        candidates.append(os.path.join("resources", "models", "f1_car.obj"))

        model_path = None
        for c in candidates:
            if c and os.path.exists(c):
                model_path = c
                break
        if not model_path:
            self._model_label = "model: missing"
            return

        try:
            verts, uvs, faces, edges, mtl_name = self._parse_obj(model_path)
            if not verts or not edges:
                self._model_label = "model: parse failed"
                return
            self._model_verts = verts
            self._model_faces = faces
            self._model_uvs = uvs
            self._model_edges = edges
            (
                self._model_points,
                self._model_depths,
                self._model_edges,
                self._model_faces,
                self._model_uvs,
            ) = self._prepare_projected_model(verts, edges, faces, uvs, self._yaw_deg, self._pitch_deg)
            self._model_texture = self._load_texture_from_mtl(model_path, mtl_name)
            self._model_color = self._extract_model_color(model_path) or QColor(80, 220, 255)
            self._model_label = f"model: {os.path.basename(model_path)}"
        except Exception:
            self._model_label = "model: load error"

    def _parse_obj(self, path):
        verts = []
        uvs = []
        faces = []
        edges = set()
        mtl_name = None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("mtllib "):
                    mtl_name = line.split(None, 1)[1].strip()
                if line.startswith("v "):
                    p = line.split()
                    if len(p) >= 4:
                        verts.append((float(p[1]), float(p[2]), float(p[3])))
                elif line.startswith("vt "):
                    p = line.split()
                    if len(p) >= 3:
                        uvs.append((float(p[1]), float(p[2])))
                elif line.startswith("f "):
                    items = line.split()[1:]
                    idxs = []
                    tidxs = []
                    for tok in items:
                        parts = tok.split("/")
                        base = parts[0]
                        if not base:
                            continue
                        i = int(base)
                        i = len(verts) + i if i < 0 else i - 1
                        if 0 <= i < len(verts):
                            idxs.append(i)
                            if len(parts) > 1 and parts[1]:
                                t = int(parts[1])
                                t = len(uvs) + t if t < 0 else t - 1
                                tidxs.append(t if 0 <= t < len(uvs) else -1)
                            else:
                                tidxs.append(-1)
                    for i in range(len(idxs)):
                        a = idxs[i]
                        b = idxs[(i + 1) % len(idxs)]
                        if a == b:
                            continue
                        edges.add((a, b) if a < b else (b, a))
                    if len(idxs) >= 3:
                        for i in range(1, len(idxs) - 1):
                            faces.append(
                                (
                                    (idxs[0], idxs[i], idxs[i + 1]),
                                    (tidxs[0], tidxs[i], tidxs[i + 1]),
                                )
                            )
        return verts, uvs, faces, sorted(edges), mtl_name

    def _prepare_projected_model(self, verts, edges, faces, uvs, yaw_deg, pitch_deg):
        # Projection angles for non-top presets.
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)

        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        zs = [v[2] for v in verts]
        cx = (min(xs) + max(xs)) * 0.5
        cy0 = (min(ys) + max(ys)) * 0.5
        cz = (min(zs) + max(zs)) * 0.5

        projected = []
        depth_values = []
        for x, y, z in verts:
            x -= cx
            y -= cy0
            z -= cz
            # True top-down mode: project onto X/Z plane (ignore vertical Y)
            if abs(yaw_deg) < 1e-6 and abs(pitch_deg) < 1e-6:
                xr = x * cy - z * sy
                zr = x * sy + z * cy
                projected.append((xr, zr))
                depth_values.append(-y)
            else:
                xr = x * cy - y * sy
                yr = x * sy + y * cy
                zr = z
                y2 = yr * cp - zr * sp
                z2 = yr * sp + zr * cp
                # Simple perspective-ish factor
                d = 135.0
                k = d / max(1.0, d + z2 * 0.45)
                projected.append((xr * k, y2 * k))
                depth_values.append(z2)

        # Auto-align model long axis (OBJ local orientation varies wildly).
        # Then apply a fixed display angle close to the Sketchfab reference.
        mean_x = sum(p[0] for p in projected) / max(1, len(projected))
        mean_y = sum(p[1] for p in projected) / max(1, len(projected))
        sxx = syy = sxy = 0.0
        for x, y in projected:
            dx = x - mean_x
            dy = y - mean_y
            sxx += dx * dx
            syy += dy * dy
            sxy += dx * dy
        # Principal component angle in 2D
        principal_angle = 0.5 * math.atan2(2.0 * sxy, (sxx - syy) if (sxx - syy) != 0 else 1e-9)
        # Desired screen angle:
        # top-down preset -> nose up (vertical car)
        # non-top presets -> slight horizontal bias
        target_angle = math.radians(90.0) if (abs(yaw_deg) < 1e-6 and abs(pitch_deg) < 1e-6) else math.radians(-4.0)
        rot = target_angle - principal_angle
        cr = math.cos(rot)
        sr = math.sin(rot)
        projected = [
            (
                (x - mean_x) * cr - (y - mean_y) * sr + mean_x,
                (x - mean_x) * sr + (y - mean_y) * cr + mean_y,
            )
            for x, y in projected
        ]

        px = [p[0] for p in projected]
        py = [p[1] for p in projected]
        minx, maxx = min(px), max(px)
        miny, maxy = min(py), max(py)
        span = max(maxx - minx, maxy - miny, 1e-6)
        norm_points = [((x - (minx + maxx) * 0.5) / span, (y - (miny + maxy) * 0.5) / span) for x, y in projected]

        # Cap edge count for performance in QPainter.
        if len(edges) > 32000:
            step = max(1, len(edges) // 32000)
            edges = edges[::step]
        return norm_points, depth_values, edges, faces, uvs

    def _reproject_model(self):
        if not self._model_verts or not self._model_edges:
            return
        (
            self._model_points,
            self._model_depths,
            _edges_limited,
            _faces,
            _uvs,
        ) = self._prepare_projected_model(
            self._model_verts,
            self._model_edges,
            self._model_faces,
            self._model_uvs,
            self._yaw_deg,
            self._pitch_deg,
        )
        # Keep the original full face/uv data, but use limited edges for drawing.
        self._model_edges = _edges_limited
        self.update()

    # Fixed angle mode intentionally disables drag-rotate for performance.

    def _load_texture_from_mtl(self, obj_path, mtl_name):
        if not mtl_name:
            return None
        obj_dir = os.path.dirname(obj_path)
        mtl_path = os.path.join(obj_dir, mtl_name.replace("/", os.sep))
        if not os.path.exists(mtl_path):
            return None
        tex_name = None
        with open(mtl_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if line.lower().startswith("map_kd "):
                    tex_name = line.split(None, 1)[1].strip().strip('"')
                    break
        if not tex_name:
            return None
        tex_base = os.path.basename(tex_name.replace("\\", "/"))
        candidates = [
            os.path.join(os.path.dirname(mtl_path), tex_base),
            os.path.join(obj_dir, tex_base),
            os.path.join(obj_dir, "textures", tex_base),
            os.path.join("resources", "models", tex_base),
            os.path.join("resources", "models", "f1_model_unpack", "textures", tex_base),
        ]
        for c in candidates:
            if os.path.exists(c):
                img = QImage(c)
                return img if not img.isNull() else None
        return None

    def _extract_model_color(self, obj_path):
        obj_dir = os.path.dirname(obj_path)
        mtl_name = None
        with open(obj_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if line.startswith("mtllib "):
                    mtl_name = line.split(None, 1)[1].strip()
                    break
        if not mtl_name:
            return None

        mtl_path = os.path.join(obj_dir, mtl_name.replace("/", os.sep))
        if not os.path.exists(mtl_path):
            return None

        tex_name = None
        kd = None
        with open(mtl_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if line.lower().startswith("map_kd "):
                    tex_name = line.split(None, 1)[1].strip().strip('"')
                    break
                if line.startswith("Kd "):
                    p = line.split()
                    if len(p) >= 4:
                        kd = (float(p[1]), float(p[2]), float(p[3]))

        if tex_name:
            tex_base = os.path.basename(tex_name.replace("\\", "/"))
            candidates = [
                os.path.join(os.path.dirname(mtl_path), tex_base),
                os.path.join(obj_dir, tex_base),
                os.path.join(obj_dir, "textures", tex_base),
                os.path.join("resources", "models", tex_base),
                os.path.join("resources", "models", "f1_model_unpack", "textures", tex_base),
            ]
            for c in candidates:
                if os.path.exists(c):
                    img = QImage(c)
                    if img.isNull():
                        continue
                    img = img.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    r = g = b = 0
                    n = max(1, img.width() * img.height())
                    for y in range(img.height()):
                        for x in range(img.width()):
                            pc = img.pixelColor(x, y)
                            r += pc.red()
                            g += pc.green()
                            b += pc.blue()
                    return QColor(int(r / n), int(g / n), int(b / n))

        if kd:
            return QColor(int(max(0, min(1, kd[0])) * 255), int(max(0, min(1, kd[1])) * 255), int(max(0, min(1, kd[2])) * 255))
        return None

    def _draw_glow_line(self, p, x1, y1, x2, y2, color):
        p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 45), 5))
        p.drawLine(int(x1), int(y1), int(x2), int(y2))
        p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 170), 2))
        p.drawLine(int(x1), int(y1), int(x2), int(y2))

    def _draw_tyre(self, p, tx, ty, radius, label):
        c = self._corner_stats.get(label, {})
        ch = int(max(0, min(100, c.get("health", self.health))))
        ct = int(max(0, min(180, c.get("temp_c", 95))))
        tyre_color = self._health_color(ch)
        glow = QRadialGradient(tx, ty, radius * 1.8)
        glow.setColorAt(0.0, QColor(tyre_color.red(), tyre_color.green(), tyre_color.blue(), 120))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(glow)
        p.setPen(Qt.NoPen)
        p.drawEllipse(int(tx - radius * 1.8), int(ty - radius * 1.8), int(radius * 3.6), int(radius * 3.6))

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(130, 240, 255, 140), 1))
        p.drawEllipse(int(tx - radius * 1.25), int(ty - radius * 1.25), int(radius * 2.5), int(radius * 2.5))

        p.setPen(QPen(tyre_color, 3))
        p.drawEllipse(int(tx - radius), int(ty - radius), int(radius * 2), int(radius * 2))

        p.setPen(QPen(QColor(190, 250, 255), 1))
        p.setFont(QFont("Consolas", 9, QFont.Bold))
        p.drawText(int(tx - 13), int(ty - 9), label)
        p.setFont(QFont("Consolas", 8))
        p.drawText(int(tx - 18), int(ty + 5), f"{ch}%")
        p.drawText(int(tx - 20), int(ty + 18), f"{ct}C")

    def paintEvent(self, event):
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(3, 10, 18))

        w = self.width()
        h = self.height()
        cx = w * 0.5
        cy = h * 0.56
        scale = min(w, h)
        car_w = scale * 0.42
        car_h = scale * 0.56
        neon = QColor(60, 200, 255)
        wheel_r = scale * 0.055

        tyre_points = [
            (cx - car_w * 0.58, cy - car_h * 0.30),
            (cx + car_w * 0.58, cy - car_h * 0.30),
            (cx - car_w * 0.58, cy + car_h * 0.34),
            (cx + car_w * 0.58, cy + car_h * 0.34),
        ]

        if not (self._model_points and self._model_edges):
            body_outline = [
                (cx, cy - car_h * 0.53),
                (cx + car_w * 0.13, cy - car_h * 0.43),
                (cx + car_w * 0.17, cy - car_h * 0.26),
                (cx + car_w * 0.28, cy - car_h * 0.10),
                (cx + car_w * 0.25, cy + car_h * 0.18),
                (cx + car_w * 0.20, cy + car_h * 0.38),
                (cx + car_w * 0.08, cy + car_h * 0.50),
                (cx - car_w * 0.08, cy + car_h * 0.50),
                (cx - car_w * 0.20, cy + car_h * 0.38),
                (cx - car_w * 0.25, cy + car_h * 0.18),
                (cx - car_w * 0.28, cy - car_h * 0.10),
                (cx - car_w * 0.17, cy - car_h * 0.26),
                (cx - car_w * 0.13, cy - car_h * 0.43),
            ]

            for i in range(len(body_outline)):
                x1, y1 = body_outline[i]
                x2, y2 = body_outline[(i + 1) % len(body_outline)]
                self._draw_glow_line(p, x1, y1, x2, y2, neon)

            self._draw_glow_line(p, cx - car_w * 0.40, cy - car_h * 0.50, cx + car_w * 0.40, cy - car_h * 0.50, neon)
            self._draw_glow_line(p, cx - car_w * 0.27, cy + car_h * 0.50, cx + car_w * 0.27, cy + car_h * 0.50, neon)

        labels = ["RL", "RR", "FL", "FR"]
        for i, (tx, ty) in enumerate(tyre_points):
            self._draw_tyre(p, tx, ty, wheel_r, labels[i])

        # Draw real Formula 1 model filled faces + wireframe (if loaded)
        if self._model_points and self._model_edges:
            draw_scale = min(w, h) * 0.90
            car_offset_x = -min(w, h) * 0.02
            car_offset_y = -min(w, h) * 0.01
            # Filled faces first (painter's algorithm by average depth)
            if self._model_faces:
                ordered_faces = []
                for vi, ti in self._model_faces:
                    depth = (
                        self._model_depths[vi[0]]
                        + self._model_depths[vi[1]]
                        + self._model_depths[vi[2]]
                    ) / 3.0
                    ordered_faces.append((depth, vi, ti))
                ordered_faces.sort(reverse=True, key=lambda x: x[0])

                p.setPen(Qt.NoPen)
                for _, vi, ti in ordered_faces:
                    pts = []
                    for idx in vi:
                        xn, yn = self._model_points[idx]
                        sx = cx + car_offset_x + xn * draw_scale
                        sy = cy + car_offset_y - yn * draw_scale
                        pts.append(QPointF(sx, sy))

                    face_color = self._model_color
                    if self._model_texture is not None and ti[0] >= 0 and ti[1] >= 0 and ti[2] >= 0:
                        uu = (self._model_uvs[ti[0]][0] + self._model_uvs[ti[1]][0] + self._model_uvs[ti[2]][0]) / 3.0
                        vv = (self._model_uvs[ti[0]][1] + self._model_uvs[ti[1]][1] + self._model_uvs[ti[2]][1]) / 3.0
                        tx = int(max(0, min(self._model_texture.width() - 1, uu * (self._model_texture.width() - 1))))
                        ty = int(max(0, min(self._model_texture.height() - 1, (1.0 - vv) * (self._model_texture.height() - 1))))
                        face_color = self._model_texture.pixelColor(tx, ty)

                    p.setBrush(QColor(face_color.red(), face_color.green(), face_color.blue(), 200))
                    p.drawPolygon(pts)

            # Keep the real model clean: no wireframe overlay on top.

        p.setPen(QColor(175, 245, 255))
        p.setFont(QFont("Consolas", 11, QFont.Bold))
        p.drawText(18, 26, f"Driver: {self.driver_code}")
        p.drawText(18, 46, f"Compound: {self.compound}")
        p.drawText(18, 66, f"Stint age: {self.laps_on_tyre} laps")
        p.drawText(18, 86, f"Model health: {self.health}%  |  +{self.expected_delta:.2f}s")
        p.drawText(18, 106, self._model_label)

        p.end()


class TyreHologramRoomWindow(PitWallWindow):
    def __init__(self):
        self._known_drivers = []
        self._latest_frame = {}
        self._latest_health = {}
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Tyre Hologram Room")
        self.setGeometry(120, 80, 1160, 780)

    def setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        title = QLabel("Tyre Degradation Hologram Room")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        self.driver_combo = QComboBox()
        self.driver_combo.setMinimumWidth(120)
        self.driver_combo.currentTextChanged.connect(self._on_driver_changed)
        self.meta_label = QLabel("Waiting for telemetry...")
        self.meta_label.setFont(QFont("Consolas", 10))
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(QLabel("Driver:"))
        header_layout.addWidget(self.driver_combo)
        layout.addWidget(header)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        holo_tab = QWidget()
        holo_layout = QVBoxLayout(holo_tab)
        self.holo_canvas = TyreHologramCanvas()
        self.detail_grid = QGridLayout()
        self.detail_grid.setHorizontalSpacing(20)
        self.detail_grid.setVerticalSpacing(4)
        self._detail_labels = {}
        fields = [
            ("Health", "health"),
            ("Expected Delta", "expected_delta"),
            ("Uncertainty", "uncertainty"),
            ("Track Condition", "track_condition"),
            ("Overdriving", "overdriving"),
            ("Position", "position"),
            ("Speed (km/h)", "speed"),
            ("Lap", "lap"),
        ]
        for idx, (label, key) in enumerate(fields):
            left = QLabel(f"{label}:")
            left.setFont(QFont("Consolas", 10, QFont.Bold))
            value = QLabel("-")
            value.setFont(QFont("Consolas", 10))
            self.detail_grid.addWidget(left, idx // 2, (idx % 2) * 2)
            self.detail_grid.addWidget(value, idx // 2, (idx % 2) * 2 + 1)
            self._detail_labels[key] = value
        holo_layout.addWidget(self.holo_canvas, 1)
        holo_layout.addLayout(self.detail_grid)
        holo_layout.addWidget(self.meta_label)
        tabs.addTab(holo_tab, "Hologram Room")

        table_tab = QWidget()
        table_layout = QVBoxLayout(table_tab)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Pos", "Driver", "Compound", "Age", "Health", "Expected +s",
            "Uncertainty", "Overdriving", "Speed", "Track"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        table_layout.addWidget(self.table)
        tabs.addTab(table_tab, "All Drivers")

    def _refresh_driver_combo(self, drivers):
        incoming = sorted(drivers.keys())
        if incoming == self._known_drivers:
            return
        current = self.driver_combo.currentText()
        self.driver_combo.blockSignals(True)
        self.driver_combo.clear()
        self.driver_combo.addItems(incoming)
        if current in incoming:
            self.driver_combo.setCurrentText(current)
        elif incoming:
            self.driver_combo.setCurrentIndex(0)
        self.driver_combo.blockSignals(False)
        self._known_drivers = incoming

    def _on_driver_changed(self, code):
        self._render_selected_driver(code)

    def _build_corner_stats(self, driver_data, base_health, time_s):
        speed = float(driver_data.get("speed", 0.0) or 0.0)
        throttle_raw = float(driver_data.get("throttle", 0.0) or 0.0)
        brake_raw = float(driver_data.get("brake", 0.0) or 0.0)
        throttle = throttle_raw / 100.0 if throttle_raw > 1.0 else throttle_raw
        brake = brake_raw / 100.0 if brake_raw > 1.0 else brake_raw

        # Dynamic left/right split for realism; subtle and stable.
        osc = math.sin(time_s * 0.12)
        left_bias = max(0.0, osc) * 1.4
        right_bias = max(0.0, -osc) * 1.4

        front_load = 0.65 * brake + 0.20 * (1.0 - throttle)
        rear_load = 0.60 * throttle + 0.15 * (1.0 - brake)

        fl_h = int(round(base_health - (1.0 + 4.0 * front_load + left_bias)))
        fr_h = int(round(base_health - (1.5 + 4.5 * front_load + right_bias)))
        rl_h = int(round(base_health - (4.0 + 5.0 * rear_load + left_bias)))
        rr_h = int(round(base_health - (4.5 + 5.5 * rear_load + right_bias)))

        fl_h = max(0, min(100, fl_h))
        fr_h = max(0, min(100, fr_h))
        rl_h = max(0, min(100, rl_h))
        rr_h = max(0, min(100, rr_h))

        base_temp = 82.0 + (100.0 - base_health) * 0.55 + speed * 0.035
        fl_t = int(round(base_temp + 17.0 * brake + 1.5 * left_bias))
        fr_t = int(round(base_temp + 18.0 * brake + 1.5 * right_bias))
        rl_t = int(round(base_temp + 12.0 * throttle + 1.0 * left_bias))
        rr_t = int(round(base_temp + 13.0 * throttle + 1.0 * right_bias))

        return {
            "FL": {"health": fl_h, "temp_c": max(60, min(160, fl_t))},
            "FR": {"health": fr_h, "temp_c": max(60, min(160, fr_t))},
            "RL": {"health": rl_h, "temp_c": max(60, min(160, rl_t))},
            "RR": {"health": rr_h, "temp_c": max(60, min(160, rr_t))},
        }

    def _render_selected_driver(self, code):
        if not code:
            return
        drivers = self._latest_frame.get("drivers", {})
        d = drivers.get(code, {})
        h = self._latest_health.get(code, {})

        health = int(h.get("health", 0) or 0)
        compound = h.get("compound", "UNKNOWN")
        laps_on_tyre = int(h.get("laps_on_tyre", 0) or 0)
        tyre_life = d.get("tyre_life", 0)
        expected_delta = float(h.get("expected_delta", 0.0) or 0.0)
        uncertainty = float(h.get("uncertainty", 0.0) or 0.0)
        time_s = float(self._latest_frame.get("t", 0.0) or 0.0)
        corner_stats = self._build_corner_stats(d, health, time_s)

        self.holo_canvas.set_data(
            code,
            health,
            compound,
            laps_on_tyre,
            tyre_life,
            expected_delta,
            uncertainty,
            corner_stats=corner_stats,
        )

        self._detail_labels["health"].setText(f"{health}%")
        self._detail_labels["expected_delta"].setText(f"+{expected_delta:.2f}s")
        self._detail_labels["uncertainty"].setText(f"{uncertainty:.2f}")
        self._detail_labels["track_condition"].setText(str(h.get("track_condition", "N/A")))
        self._detail_labels["overdriving"].setText("YES" if h.get("overdriving", False) else "NO")
        self._detail_labels["position"].setText(str(d.get("position", "-")))
        self._detail_labels["speed"].setText(f"{float(d.get('speed', 0.0) or 0.0):.1f}")
        self._detail_labels["lap"].setText(str(d.get("lap", "-")))

        track = self._latest_frame.get("track_condition") or self._latest_frame.get("weather", {}).get("rain_state", "DRY")
        self.meta_label.setText(f"t={time_s:.1f}s  |  Track: {track}")

    def _render_table(self):
        drivers = self._latest_frame.get("drivers", {})
        if not drivers:
            self.table.setRowCount(0)
            return

        ordered = sorted(drivers.items(), key=lambda item: item[1].get("position", 999))
        self.table.setRowCount(len(ordered))
        for row, (code, d) in enumerate(ordered):
            h = self._latest_health.get(code, {})
            values = [
                d.get("position", "-"),
                code,
                h.get("compound", "UNKNOWN"),
                h.get("laps_on_tyre", d.get("tyre_life", 0)),
                f"{int(h.get('health', 0) or 0)}%",
                f"+{float(h.get('expected_delta', 0.0) or 0.0):.2f}",
                f"{float(h.get('uncertainty', 0.0) or 0.0):.2f}",
                "YES" if h.get("overdriving", False) else "NO",
                f"{float(d.get('speed', 0.0) or 0.0):.1f}",
                str(h.get("track_condition", "N/A")),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))

        self.table.resizeColumnsToContents()

    def on_telemetry_data(self, data):
        frame = data.get("frame")
        if not frame:
            return
        drivers = frame.get("drivers", {})
        if not drivers:
            return

        self._latest_frame = frame
        self._latest_health = data.get("tyre_health", {}) or {}
        self._refresh_driver_combo(drivers)
        self._render_table()

        selected = self.driver_combo.currentText()
        if selected:
            self._render_selected_driver(selected)

    def on_connection_status_changed(self, status):
        if status != "Connected":
            self.meta_label.setText(f"{status} - waiting for telemetry stream")

    def on_stream_error(self, error_msg):
        self.meta_label.setText(f"Stream error: {error_msg}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Tyre Hologram Room")
    window = TyreHologramRoomWindow()
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
