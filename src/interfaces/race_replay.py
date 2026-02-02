import os
import arcade
import numpy as np
from src.f1_data import FPS
from src.ui_components import (
    LeaderboardComponent, 
    WeatherComponent, 
    LegendComponent, 
    DriverInfoComponent, 
    RaceProgressBarComponent,
    RaceControlsComponent,
    ControlsPopupComponent,
    SessionInfoComponent,
    extract_race_events,
    build_track_from_example_lap,
    draw_finish_line
)
from src.tyre_degradation_integration import TyreDegradationIntegrator
from src.lib.sync import TelemetrySender

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "F1 Race Replay"
PLAYBACK_SPEEDS = [0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]

class F1RaceReplayWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, circuit_rotation=0.0,
                 left_ui_margin=340, right_ui_margin=260, total_laps=None, visible_hud=True,
                 session_info=None, session=None):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, title, resizable=True)
        self.maximize()

        self.frames = frames
        self.track_statuses = track_statuses
        self.n_frames = len(frames)
        self.drivers = list(drivers)
        self.playback_speed = PLAYBACK_SPEEDS[PLAYBACK_SPEEDS.index(playback_speed)] if playback_speed in PLAYBACK_SPEEDS else 1.0
        self.driver_colors = driver_colors or {}
        self.frame_index = 0.0 
        self.paused = False
        self.total_laps = total_laps
        self.has_weather = any("weather" in frame for frame in frames) if frames else False
        self.visible_hud = visible_hud
        
        # Sync Sender
        self.sender = TelemetrySender()
        self.selected_driver = None

        # Rotation
        self.circuit_rotation = circuit_rotation
        self._rot_rad = float(np.deg2rad(self.circuit_rotation)) if self.circuit_rotation else 0.0
        self._cos_rot = float(np.cos(self._rot_rad))
        self._sin_rot = float(np.sin(self._rot_rad))
        self.finished_drivers = []
        self.left_ui_margin = left_ui_margin
        self.right_ui_margin = right_ui_margin
        self.toggle_drs_zones = True 
        self.show_driver_labels = False
        
        # UI components
        leaderboard_x = max(20, self.width - self.right_ui_margin + 12)
        self.leaderboard_comp = LeaderboardComponent(x=leaderboard_x, width=240, visible=visible_hud)
        self.weather_comp = WeatherComponent(left=20, top_offset=170, visible=visible_hud)
        self.legend_comp = LegendComponent(x=max(12, self.left_ui_margin - 320), visible=visible_hud)
        self.driver_info_comp = DriverInfoComponent(left=20, width=300)
        self.controls_popup_comp = ControlsPopupComponent()
        self.controls_popup_comp.set_size(340, 250)
        self.controls_popup_comp.set_font_sizes(header_font_size=16, body_font_size=13)

        # Tyre Deg Model
        self.degradation_integrator = None
        if session is not None:
            try:
                print("Initializing tyre degradation model...")
                self.degradation_integrator = TyreDegradationIntegrator(session=session)
                init_success = self.degradation_integrator.initialize_from_session()
                if init_success:
                    print("✓ Tyre degradation model initialized successfully")
                    self.driver_info_comp.degradation_integrator = self.degradation_integrator
                else:
                    self.degradation_integrator = None
            except Exception as e:
                print(f"✗ Tyre degradation initialization error: {e}")
                self.degradation_integrator = None

        # Progress bar
        self.progress_bar_comp = RaceProgressBarComponent(
            left_margin=left_ui_margin,
            right_margin=right_ui_margin,
            bottom=30,
            height=24,
            marker_height=16
        )

        # Controls
        self.race_controls_comp = RaceControlsComponent(
            center_x=self.width // 2,
            center_y=100,
            visible = visible_hud
        )
        
        self.session_info = session_info
        self.session_info_comp = SessionInfoComponent(visible=False)

        self.is_rewinding = False
        self.is_forwarding = False
        self.was_paused_before_hold = False
        
        # Events
        race_events = extract_race_events(frames, track_statuses, total_laps or 0)
        self.progress_bar_comp.set_race_data(
            total_frames=len(frames),
            total_laps=total_laps or 0,
            events=race_events
        )

        # Track Geometry
        (self.plot_x_ref, self.plot_y_ref,
         self.x_inner, self.y_inner,
         self.x_outer, self.y_outer,
         self.x_min, self.x_max,
         self.y_min, self.y_max, self.drs_zones) = build_track_from_example_lap(example_lap)

        ref_points = self._interpolate_points(self.plot_x_ref, self.plot_y_ref, interp_points=4000)
        self._ref_xs = np.array([p[0] for p in ref_points])
        self._ref_ys = np.array([p[1] for p in ref_points])

        dx = np.gradient(self._ref_xs)
        dy = np.gradient(self._ref_ys)
        norm = np.sqrt(dx**2 + dy**2)
        norm[norm == 0] = 1.0
        self._ref_nx = -dy / norm
        self._ref_ny = dx / norm

        signed_area = np.sum(self._ref_xs[:-1] * self._ref_ys[1:] - self._ref_xs[1:] * self._ref_ys[:-1])
        signed_area += (self._ref_xs[-1] * self._ref_ys[0] - self._ref_xs[0] * self._ref_ys[-1])
        if signed_area > 0:
            self._ref_nx = -self._ref_nx
            self._ref_ny = -self._ref_ny

        diffs = np.sqrt(np.diff(self._ref_xs)**2 + np.diff(self._ref_ys)**2)
        self._ref_seg_len = diffs
        self._ref_cumdist = np.concatenate(([0.0], np.cumsum(diffs)))
        self._ref_total_length = float(self._ref_cumdist[-1]) if len(self._ref_cumdist) > 0 else 0.0

        self.world_inner_points = self._interpolate_points(self.x_inner, self.y_inner)
        self.world_outer_points = self._interpolate_points(self.x_outer, self.y_outer)
        self.screen_inner_points = []
        self.screen_outer_points = []
        
        self.world_scale = 1.0
        self.tx = 0
        self.ty = 0

        bg_path = os.path.join("resources", "background.png")
        self.bg_texture = arcade.load_texture(bg_path) if os.path.exists(bg_path) else None
        arcade.set_background_color(arcade.color.BLACK)

        self.update_scaling(self.width, self.height)
        
        self.flag_texture = None
        if self.session_info:
            try:
                country = self.session_info.get('country', 'Unknown')
                flag_path = os.path.join("resources", "flags", f"{country}.png")
                if os.path.exists(flag_path):
                    self.flag_texture = arcade.load_texture(flag_path)
            except Exception:
                pass

    def _interpolate_points(self, xs, ys, interp_points=2000):
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def _project_to_reference(self, x, y):
        if self._ref_total_length == 0.0: return 0.0
        dx = self._ref_xs - x
        dy = self._ref_ys - y
        d2 = dx * dx + dy * dy
        idx = int(np.argmin(d2))
        return float(self._ref_cumdist[idx])

    def update_scaling(self, screen_w, screen_h):
        padding = 0.05
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2

        def _rotate_about_center(x, y):
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            return rx + world_cx, ry + world_cy

        rotated_points = []
        for x, y in self.world_inner_points:
            rotated_points.append(_rotate_about_center(x, y))
        for x, y in self.world_outer_points:
            rotated_points.append(_rotate_about_center(x, y))

        xs = [p[0] for p in rotated_points]
        ys = [p[1] for p in rotated_points]
        world_x_min = min(xs) if xs else self.x_min
        world_x_max = max(xs) if xs else self.x_max
        world_y_min = min(ys) if ys else self.y_min
        world_y_max = max(ys) if ys else self.y_max

        world_w = max(1.0, world_x_max - world_x_min)
        world_h = max(1.0, world_y_max - world_y_min)
        
        inner_w = max(1.0, screen_w - self.left_ui_margin - self.right_ui_margin)
        usable_w = inner_w * (1 - 2 * padding)
        usable_h = screen_h * (1 - 2 * padding)

        scale_x = usable_w / world_w
        scale_y = usable_h / world_h
        self.world_scale = min(scale_x, scale_y)

        screen_cx = self.left_ui_margin + inner_w / 2
        screen_cy = screen_h / 2

        self.tx = screen_cx - self.world_scale * world_cx
        self.ty = screen_cy - self.world_scale * world_cy

        self.screen_inner_points = [self.world_to_screen(x, y) for x, y in self.world_inner_points]
        self.screen_outer_points = [self.world_to_screen(x, y) for x, y in self.world_outer_points]

    def on_resize(self, width, height):
        super().on_resize(width, height)
        self.update_scaling(width, height)
        self.leaderboard_comp.x = max(20, self.width - self.right_ui_margin + 12)
        for c in (self.leaderboard_comp, self.weather_comp, self.legend_comp, self.driver_info_comp, self.progress_bar_comp, self.race_controls_comp):
            c.on_resize(self)

    def world_to_screen(self, x, y):
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2
        if self._rot_rad:
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            x, y = rx + world_cx, ry + world_cy
        sx = self.world_scale * x + self.tx
        sy = self.world_scale * y + self.ty
        return sx, sy

    def draw_gauge(self, x, y, value, max_val, label, color, fmt="{}", is_binary=False):
        radius = 24
        arcade.draw_circle_outline(x, y, radius, (40, 40, 40), 3)
        if is_binary:
            if value > 0:
                arcade.draw_circle_outline(x, y, radius, color, 3)
        else:
            start_angle = -90
            pct = max(0.0, min(1.0, float(value) / max_val))
            arcade.draw_arc_outline(x, y, radius*2, radius*2, color, start_angle, start_angle + (pct * 360), 3)
        
        if is_binary:
            val_text = fmt
            font_size = 10
        else:
            val_text = fmt.format(value)
            font_size = 12

        arcade.draw_text(val_text, x, y, arcade.color.WHITE, font_size, bold=True, anchor_x="center", anchor_y="center")
        arcade.draw_text(label, x, y - radius - 10, color, 9, anchor_x="center", bold=True)

    def draw_dashboard_header(self, session_info, current_lap, total_laps, race_time_str, weather_data):
        header_height = 90
        top_y = self.height
        bottom_y = self.height - header_height
        center_x = self.width // 2 
        
        # --- FIX: USE draw_rect_filled INSTEAD OF draw_lrtb_... ---
        # Background Bar
        arcade.draw_rect_filled(
            arcade.XYWH(self.width / 2, bottom_y + (header_height / 2), self.width, header_height),
            (10, 10, 12, 255)
        )
        
        arcade.draw_line(0, bottom_y, self.width, bottom_y, (60, 60, 70), 2)

        flag_width, flag_height = 60, 40
        flag_x = 50 
        base_y = bottom_y + (header_height / 2)

        if hasattr(self, 'flag_texture') and self.flag_texture:
            arcade.draw_texture_rectangle(flag_x, base_y, flag_width, flag_height, self.flag_texture)
        else:
            arcade.draw_rect_filled(arcade.XYWH(flag_x, base_y, flag_width, flag_height), arcade.color.RED_DEVIL)

        text_x = flag_x + (flag_width / 2) + 15 
        e_name = session_info.get('event_name', 'Grand Prix')
        arcade.draw_text(e_name, text_x, base_y + 12, arcade.color.WHITE, 20, bold=True, anchor_y="bottom")
        c_name = session_info.get('circuit_name', 'Circuit') 
        arcade.draw_text(c_name, text_x, base_y + 2, arcade.color.GRAY, 12, bold=True, anchor_y="center")
        arcade.draw_text(race_time_str, text_x, base_y - 18, arcade.color.LIGHT_GRAY, 14, bold=True, anchor_y="top")

        # Weather Gauges
        w = weather_data or {}
        track_temp = float(w.get('track_temp') or 0)
        air_temp = float(w.get('air_temp') or 0)
        humidity = float(w.get('humidity') or 0)
        wind_speed = float(w.get('wind_speed') or 0)
        rain_state = w.get('rain_state', 'DRY')
        is_raining = 1 if rain_state == 'RAINING' else 0

        start_gauge_x = center_x - 160
        spacing = 70

        self.draw_gauge(start_gauge_x, base_y, track_temp, 60, "TRC", (255, 60, 0), "{:.1f}")
        self.draw_gauge(start_gauge_x + spacing, base_y, air_temp, 40, "AIR", (100, 255, 50), "{:.1f}")
        self.draw_gauge(start_gauge_x + spacing*2, base_y, humidity, 100, "HUM", (50, 150, 255), "{:.1f}")
        self.draw_gauge(start_gauge_x + spacing*3, base_y, wind_speed, 15, "WIND", (200, 200, 200), "{:.1f}")
        
        rain_color = (0, 100, 255) if is_raining else (80, 80, 80)
        rain_label = "YES" if is_raining else "NO"
        self.draw_gauge(start_gauge_x + spacing*4, base_y, is_raining, 1, "RAIN", rain_color, rain_label, is_binary=True)
        
        arcade.draw_text("LAP", self.width - 160, base_y + 12, arcade.color.GRAY, 12, anchor_x="right", bold=True)
        lap_str = f"{int(current_lap)} / {total_laps}"
        arcade.draw_text(lap_str, self.width - 30, base_y - 12, arcade.color.WHITE, 30, bold=True, anchor_x="right")

    def draw_track_status_indicator(self, status_code):
        if status_code == "1": color, text = (0, 200, 50), "TRACK CLEAR"
        elif status_code == "2": color, text = (255, 200, 0), "YELLOW FLAG"
        elif status_code == "4": color, text = (255, 120, 0), "SAFETY CAR"
        elif status_code == "5": color, text = (200, 0, 0), "RED FLAG"
        elif status_code in ["6", "7"]: color, text = (255, 160, 50), "VIRTUAL SAFETY CAR"
        else: color, text = (0, 200, 50), "TRACK CLEAR"

        header_height, bar_height = 90, 24
        center_x = self.width // 2
        center_y = self.height - header_height - (bar_height / 2) - 1 
        arcade.draw_rect_filled(arcade.XYWH(center_x, center_y, 200, bar_height), color)
        arcade.draw_text(text, center_x, center_y - 5, arcade.color.BLACK if status_code != "5" else arcade.color.WHITE, 12, bold=True, anchor_x="center")

    def on_draw(self):
        self.clear()

        # 1. Background
        if self.bg_texture:
            # FIX: Use LRBT (Bottom-Top) which is supported, or standard XYWH
            # Using XYWH for consistency and safety
            arcade.draw_rect_filled(
                arcade.XYWH(self.width/2, self.height/2, self.width, self.height),
                color=(255, 255, 255), # Tint
                texture=self.bg_texture
            )

        # 2. Track Logic
        idx = min(int(self.frame_index), self.n_frames - 1)
        frame = self.frames[idx]
        current_time = frame["t"]
        
        current_track_status = "1"
        for status in self.track_statuses:
            if status['start_time'] <= current_time and (status['end_time'] is None or current_time < status['end_time']):
                current_track_status = status['status']
                break

        STATUS_COLORS = {
            "GREEN": (150, 150, 150), "YELLOW": (220, 180, 0), "RED": (200, 30, 30),
            "VSC": (200, 130, 50), "SC": (180, 100, 30),
        }
        track_color = STATUS_COLORS.get("GREEN")
        if current_track_status == "2": track_color = STATUS_COLORS.get("YELLOW")
        elif current_track_status == "4": track_color = STATUS_COLORS.get("SC")
        elif current_track_status == "5": track_color = STATUS_COLORS.get("RED")
        elif current_track_status in ["6", "7"]: track_color = STATUS_COLORS.get("VSC")
            
        if len(self.screen_inner_points) > 1: arcade.draw_line_strip(self.screen_inner_points, track_color, 4)
        if len(self.screen_outer_points) > 1: arcade.draw_line_strip(self.screen_outer_points, track_color, 4)
        
        if hasattr(self, 'drs_zones') and self.drs_zones and self.toggle_drs_zones:
            drs_color = (0, 255, 0)
            for _, zone in enumerate(self.drs_zones):
                start_idx, end_idx = zone["start"]["index"], zone["end"]["index"]
                drs_outer_points = []
                for i in range(start_idx, min(end_idx + 1, len(self.x_outer))):
                    sx, sy = self.world_to_screen(self.x_outer.iloc[i], self.y_outer.iloc[i])
                    drs_outer_points.append((sx, sy))
                if len(drs_outer_points) > 1: arcade.draw_line_strip(drs_outer_points, drs_color, 6)

        draw_finish_line(self)

        # 3. Cars
        selected_drivers = getattr(self, "selected_drivers", [])
        if not selected_drivers and getattr(self, "selected_driver", None):
            selected_drivers = [self.selected_driver]

        for i, (code, pos) in enumerate(frame["drivers"].items()):
            sx, sy = self.world_to_screen(pos["x"], pos["y"])
            color = self.driver_colors.get(code, arcade.color.WHITE)
            is_selected = code in selected_drivers
            
            if self.show_driver_labels or is_selected:
                r_dx, r_dy = self._ref_xs - pos["x"], self._ref_ys - pos["y"]
                idx_ref = int(np.argmin(r_dx*r_dx + r_dy*r_dy))
                nx, ny = self._ref_nx[idx_ref], self._ref_ny[idx_ref]
                
                if self._rot_rad:
                    snx = nx * self._cos_rot - ny * self._sin_rot
                    sny = nx * self._sin_rot + ny * self._cos_rot
                else:
                    snx, sny = nx, ny
                
                offset_dist = 45 if i % 2 == 0 else 75
                lx, ly = sx + snx * offset_dist, sy + sny * offset_dist
                arcade.draw_line(sx, sy, lx, ly, color, 1)
                anchor = "left" if snx >= 0 else "right"
                arcade.draw_text(code, lx + (3 if snx >= 0 else -3), ly, color, 10, anchor_x=anchor, anchor_y="center", bold=True)
            arcade.draw_circle_filled(sx, sy, 6, color)
        
        # 4. Data Logic
        driver_progress = {}
        for code, pos in frame["drivers"].items():
            lap_raw = pos.get("lap", 1)
            try: lap = int(lap_raw)
            except: lap = 1
            projected_m = self._project_to_reference(pos.get("x", 0.0), pos.get("y", 0.0))
            driver_progress[code] = float((max(lap, 1) - 1) * self._ref_total_length + projected_m)

        if driver_progress:
            leader_code = max(driver_progress, key=lambda c: driver_progress[c])
            leader_lap = frame["drivers"][leader_code].get("lap", 1)
        else:
            leader_lap = 1

        # Leaderboard calculation
        driver_list = []
        for code, pos in frame["drivers"].items():
            color = self.driver_colors.get(code, arcade.color.WHITE)
            progress_m = driver_progress.get(code, float(pos.get("dist", 0.0)))
            driver_list.append((code, color, pos, progress_m))
        driver_list.sort(key=lambda x: x[3], reverse=True)
        
        REFERENCE_SPEED_MS = 55.56
        leaderboard_gaps = {}
        leaderboard_neighbor_gaps = {}
        leader_progress_val = driver_list[0][3] if driver_list else None

        if driver_list and leader_progress_val is not None:
            for idx, (code, _, pos, progress_m) in enumerate(driver_list):
                try:
                    raw_to_leader = abs(leader_progress_val - (progress_m or 0.0))
                    time_to_leader = (raw_to_leader / 10.0) / REFERENCE_SPEED_MS
                    leaderboard_gaps[code] = 0.0 if idx == 0 else time_to_leader
                except: leaderboard_gaps[code] = None

                ahead_info = None
                try:
                    if idx > 0:
                        code_ahead, _, _, progress_ahead = driver_list[idx - 1]
                        raw = abs((progress_m or 0.0) - (progress_ahead or 0.0))
                        dist_m = raw / 10.0
                        time_s = dist_m / REFERENCE_SPEED_MS
                        ahead_info = (code_ahead, dist_m, time_s)
                except: ahead_info = None
                leaderboard_neighbor_gaps[code] = {"ahead": ahead_info}

        self.leaderboard_gaps = leaderboard_gaps
        self.leaderboard_neighbor_gaps = leaderboard_neighbor_gaps
        self.leaderboard_comp.set_entries(driver_list)

        # 5. UI Rendering
        if self.visible_hud:
            m, s = divmod(int(current_time), 60)
            h, m = divmod(m, 60)
            time_str = f"{h:02d}:{m:02d}:{s:02d}"
            weather_info = frame.get("weather") if frame else {}
            
            self.draw_dashboard_header(
                self.session_info or {},
                leader_lap,
                self.total_laps,
                time_str,
                weather_info
            )
            self.draw_track_status_indicator(current_track_status)

        self.weather_comp.set_info(frame.get("weather"))
        self.weather_bottom = self.height - 170 - 130

        self.leaderboard_comp.draw(self)
        self.leaderboard_rects = self.leaderboard_comp.rects
        self.legend_comp.draw(self)
        self.driver_info_comp.draw(self)
        self.progress_bar_comp.draw(self)
        self.race_controls_comp.draw(self)
        self.controls_popup_comp.draw(self)
        self.progress_bar_comp.draw_overlays(self)
                    
    def on_update(self, delta_time: float):
        self.race_controls_comp.on_update(delta_time)
        
        current_driver = self.selected_driver if hasattr(self, "selected_driver") else None
        self.sender.send_update(self.frame_index, current_driver)

        seek_speed = 3.0 * max(1.0, self.playback_speed)
        if self.is_rewinding:
            self.frame_index = max(0.0, self.frame_index - delta_time * FPS * seek_speed)
            self.race_controls_comp.flash_button('rewind')
        elif self.is_forwarding:
            self.frame_index = min(self.n_frames - 1, self.frame_index + delta_time * FPS * seek_speed)
            self.race_controls_comp.flash_button('forward')

        if self.paused:
            return

        self.frame_index += delta_time * FPS * self.playback_speed
        
        if self.frame_index >= self.n_frames:
            self.frame_index = float(self.n_frames - 1)

    def on_key_press(self, symbol: int, modifiers: int):
        if symbol == arcade.key.ESCAPE:
            arcade.close_window()
            return
        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
            self.race_controls_comp.flash_button('play_pause')
        elif symbol == arcade.key.RIGHT:
            self.was_paused_before_hold = self.paused
            self.is_forwarding = True
            self.paused = True
        elif symbol == arcade.key.LEFT:
            self.was_paused_before_hold = self.paused
            self.is_rewinding = True
            self.paused = True
        elif symbol == arcade.key.UP:
            if self.playback_speed < PLAYBACK_SPEEDS[-1]:
                for spd in PLAYBACK_SPEEDS:
                    if spd > self.playback_speed:
                        self.playback_speed = spd
                        break
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.DOWN:
            if self.playback_speed > PLAYBACK_SPEEDS[0]:
                for spd in reversed(PLAYBACK_SPEEDS):
                    if spd < self.playback_speed:
                        self.playback_speed = spd
                        break
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_1:
            self.playback_speed = 0.5
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_2:
            self.playback_speed = 1.0
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_3:
            self.playback_speed = 2.0
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.KEY_4:
            self.playback_speed = 4.0
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.R:
            self.frame_index = 0.0
            self.playback_speed = 1.0
            if self.degradation_integrator:
                self.degradation_integrator.clear_cache()
            self.race_controls_comp.flash_button('rewind')
        elif symbol == arcade.key.D:
            self.toggle_drs_zones = not self.toggle_drs_zones
        elif symbol == arcade.key.L:
            self.show_driver_labels = not self.show_driver_labels
        elif symbol == arcade.key.H:
            margin_x = 20
            margin_y = 20
            left_pos = float(margin_x)
            top_pos = float(margin_y + self.controls_popup_comp.height)
            if self.controls_popup_comp.visible:
                self.controls_popup_comp.hide()
            else:
                self.controls_popup_comp.show_over(left_pos, top_pos)
        elif symbol == arcade.key.B:
            self.progress_bar_comp.toggle_visibility()
        elif symbol == arcade.key.I:
            self.session_info_comp.toggle_visibility()

    def on_key_release(self, symbol: int, modifiers: int):
        if symbol == arcade.key.RIGHT:
            self.is_forwarding = False
            self.paused = self.was_paused_before_hold
        elif symbol == arcade.key.LEFT:
            self.is_rewinding = False
            self.paused = self.was_paused_before_hold

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int):
        if self.is_forwarding or self.is_rewinding:
            self.is_forwarding = False
            self.is_rewinding = False
            self.paused = self.was_paused_before_hold

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        if self.controls_popup_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.race_controls_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.progress_bar_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.leaderboard_comp.on_mouse_press(self, x, y, button, modifiers):
            if getattr(self, "telemetry_window", None) or hasattr(self, "sender"):
                if self.selected_driver:
                    pass
            return
        if self.legend_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        self.selected_driver = None
        
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        self.progress_bar_comp.on_mouse_motion(self, x, y, dx, dy)
        self.race_controls_comp.on_mouse_motion(self, x, y, dx, dy)