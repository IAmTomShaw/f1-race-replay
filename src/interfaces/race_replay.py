import os
import math
import arcade
import numpy as np
from scipy.spatial import cKDTree
from arcade.camera import Camera2D
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
    TyreStrategyTimelineComponent,
    ChaseCamHUDComponent,
    extract_race_events,
    build_track_from_example_lap,
    draw_finish_line
)
from src.tyre_degradation_integration import TyreDegradationIntegrator


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "F1 Race Replay"
PLAYBACK_SPEEDS = [0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]

class F1RaceReplayWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, circuit_rotation=0.0,
                 left_ui_margin=340, right_ui_margin=260, total_laps=None, visible_hud=True,
                 session_info=None, session=None, strategy_data=None):
        # Set resizable to True so the user can adjust mid-sim
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, title, resizable=True)
        self.maximize()

        self.frames = frames
        self.track_statuses = track_statuses
        self.n_frames = len(frames)
        self.drivers = list(drivers)
        self.playback_speed = PLAYBACK_SPEEDS[PLAYBACK_SPEEDS.index(playback_speed)] if playback_speed in PLAYBACK_SPEEDS else 1.0
        self.driver_colors = driver_colors or {}
        self.frame_index = 0.0  # use float for fractional-frame accumulation
        self.paused = False
        self.total_laps = total_laps
        self.has_weather = any("weather" in frame for frame in frames) if frames else False
        self.visible_hud = visible_hud # If it displays HUD or not (leaderboard, controls, weather, etc)

        # Rotation (degrees) to apply to the whole circuit around its centre
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

        self.controls_popup_comp.set_size(340, 290) # width/height of the popup box
        self.controls_popup_comp.set_font_sizes(header_font_size=16, body_font_size=13) # adjust font sizes
        self.degradation_integrator = None
        if session is not None:
            try:
                print("Initializing tyre degradation model...")
                self.degradation_integrator = TyreDegradationIntegrator(session=session)
                
                # This computes curves once at startup (1-2 seconds)
                init_success = self.degradation_integrator.initialize_from_session()
                
                if init_success:
                    print("✓ Tyre degradation model initialized successfully")
                    # Link integrator to driver info component
                    self.driver_info_comp.degradation_integrator = self.degradation_integrator
                else:
                    print("✗ Tyre degradation model initialization failed")
                    self.degradation_integrator = None
            except Exception as e:
                print(f"✗ Tyre degradation initialization error: {e}")
                self.degradation_integrator = None
        else:
            print("Note: Session not provided, tyre degradation disabled")


        # Progress bar component with race event markers
        self.progress_bar_comp = RaceProgressBarComponent(
            left_margin=left_ui_margin,
            right_margin=right_ui_margin,
            bottom=30,
            height=24,
            marker_height=16
        )

        # Race control buttons component
        self.race_controls_comp = RaceControlsComponent(
            center_x=self.width // 2,
            center_y=100,
            visible = visible_hud
        )
        
        # Session info banner component
        self.session_info_comp = SessionInfoComponent(visible=visible_hud)
        if session_info:
            self.session_info_comp.set_info(
                event_name=session_info.get('event_name', ''),
                circuit_name=session_info.get('circuit_name', ''),
                country=session_info.get('country', ''),
                year=session_info.get('year'),
                round_num=session_info.get('round'),
                date=session_info.get('date', ''),
                total_laps=total_laps
            )

        # Tyre strategy timeline component
        self.tyre_strategy_comp = TyreStrategyTimelineComponent(visible=False)
        if strategy_data:
            self.tyre_strategy_comp.set_data(
                strategy_data=strategy_data,
                driver_colors=driver_colors or {},
                total_laps=total_laps or 0,
            )

        self.is_rewinding = False
        self.is_forwarding = False
        self.was_paused_before_hold = False
        
        # Extract race events for the progress bar
        race_events = extract_race_events(frames, track_statuses, total_laps or 0)
        self.progress_bar_comp.set_race_data(
            total_frames=len(frames),
            total_laps=total_laps or 0,
            events=race_events
        )

        # Build track geometry (Raw World Coordinates)
        (self.plot_x_ref, self.plot_y_ref,
         self.x_inner, self.y_inner,
         self.x_outer, self.y_outer,
         self.x_min, self.x_max,
         self.y_min, self.y_max, self.drs_zones) = build_track_from_example_lap(example_lap)

        # Build a dense reference polyline (used for projecting car (x,y) -> along-track distance)
        ref_points = self._interpolate_points(self.plot_x_ref, self.plot_y_ref, interp_points=4000)
        # store as numpy arrays for vectorized ops
        self._ref_xs = np.array([p[0] for p in ref_points])
        self._ref_ys = np.array([p[1] for p in ref_points])

        # Calculate normals for the reference line
        dx = np.gradient(self._ref_xs)
        dy = np.gradient(self._ref_ys)
        norm = np.sqrt(dx**2 + dy**2)
        norm[norm == 0] = 1.0
        self._ref_nx = -dy / norm
        self._ref_ny = dx / norm

        # Build KD-Tree for fast closest-point lookup
        self.track_tree = cKDTree(np.column_stack((self._ref_xs, self._ref_ys)))

        # Determine track winding using the shoelace formula to ensure normals point outwards.
        # A positive area indicates counter-clockwise winding (normals point Left=Inside, so we flip).
        # A negative area indicates clockwise winding (normals point Left=Outside, so we keep).
        signed_area = np.sum(self._ref_xs[:-1] * self._ref_ys[1:] - self._ref_xs[1:] * self._ref_ys[:-1])
        signed_area += (self._ref_xs[-1] * self._ref_ys[0] - self._ref_xs[0] * self._ref_ys[-1])
        if signed_area > 0:
            self._ref_nx = -self._ref_nx
            self._ref_ny = -self._ref_ny

        # cumulative distances along the reference polyline (metres)
        diffs = np.sqrt(np.diff(self._ref_xs)**2 + np.diff(self._ref_ys)**2)
        self._ref_seg_len = diffs
        self._ref_cumdist = np.concatenate(([0.0], np.cumsum(diffs)))
        self._ref_total_length = float(self._ref_cumdist[-1]) if len(self._ref_cumdist) > 0 else 0.0

        # Pre-calculate interpolated world points ONCE (optimization)
        self.world_inner_points = self._interpolate_points(self.x_inner, self.y_inner)
        self.world_outer_points = self._interpolate_points(self.x_outer, self.y_outer)

        # These will hold the actual screen coordinates to draw
        self.screen_inner_points = []
        self.screen_outer_points = []
        
        # Scaling parameters (initialized to 0, calculated in update_scaling)
        self.world_scale = 1.0
        self.tx = 0
        self.ty = 0

        # Load Background
        bg_path = os.path.join("resources", "background.png")
        self.bg_texture = arcade.load_texture(bg_path) if os.path.exists(bg_path) else None

        arcade.set_background_color(arcade.color.BLACK)

        # Persistent UI Text objects (avoid per-frame allocations)
        self.lap_text = arcade.Text("", 20, self.height - 40, arcade.color.WHITE, 24, anchor_y="top")
        self.time_text = arcade.Text("", 20, self.height - 80, arcade.color.WHITE, 20, anchor_y="top")
        self.status_text = arcade.Text("", 20, self.height - 120, arcade.color.WHITE, 24, bold=True, anchor_y="top")

        # Trigger initial scaling calculation
        self.update_scaling(self.width, self.height)

        # Selection & hit-testing state for leaderboard
        self.selected_driver = None
        self.leaderboard_rects = []  # list of tuples: (code, left, bottom, right, top)
        # store previous leaderboard order for up/down arrows
        self.last_leaderboard_order = None

        # --- Chase Cam State ---
        self.chase_cam_active = False
        self.chase_cam_driver = None       # driver code being followed
        self.chase_cam = None              # Camera2D instance (created lazily)
        self._chase_cam_x = 0.0
        self._chase_cam_y = 0.0
        self._chase_cam_angle = 0.0        # camera angle in degrees
        self._prev_driver_pos = {}         # code -> (x, y) for heading calc
        self.chase_cam_hud = ChaseCamHUDComponent()
        self._chase_intervals = {}  # code -> gap_seconds to car ahead
        self._chase_label = arcade.Text("", 0, 0, arcade.color.WHITE, 9,
                                        bold=True, anchor_x="center", anchor_y="bottom")

        # Chase cam constants
        self.CHASE_CAM_ZOOM = 2.0
        self.CHASE_CAM_LERP_POS = 0.35
        self.CHASE_CAM_LERP_ANGLE = 0.04   # very slow rotation to minimise visual shimmer

        # Pre-rotate world track points for chase cam (reduced density for performance)
        self._rotated_inner = [self._rotate_world(x, y) for x, y in self.world_inner_points[::3]]
        self._rotated_outer = [self._rotate_world(x, y) for x, y in self.world_outer_points[::3]]

        # Pre-rotate DRS zone points
        self._rotated_drs_zones = []
        if hasattr(self, 'drs_zones') and self.drs_zones:
            for zone in self.drs_zones:
                start_idx = zone["start"]["index"]
                end_idx = zone["end"]["index"]
                pts = []
                for i in range(start_idx, min(end_idx + 1, len(self.x_outer))):
                    rx, ry = self._rotate_world(float(self.x_outer.iloc[i]), float(self.y_outer.iloc[i]))
                    pts.append((rx, ry))
                self._rotated_drs_zones.append(pts)

        # Heading smoothing buffer (stores last N heading values)
        self._heading_buffer = []
        self._heading_buffer_size = 20  # heavy smoothing to reduce rotation jitter

        # Interpolation state (shared between _update and _draw)
        self._chase_frac = 0.0
        self._chase_frame_idx = 0
        self._chase_next_idx = 0

    def _interpolate_points(self, xs, ys, interp_points=2000):
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def _project_to_reference(self, x, y):
        if self._ref_total_length == 0.0:
            return 0.0

        # Vectorized nearest-point lookup using KD-Tree (O(log N))
        _, idx = self.track_tree.query([x, y])
        idx = int(idx)

        # For a slightly better estimate, optionally project onto the adjacent segment
        if idx < len(self._ref_xs) - 1:

            x1, y1 = self._ref_xs[idx], self._ref_ys[idx]
            x2, y2 = self._ref_xs[idx+1], self._ref_ys[idx+1]
            vx, vy = x2 - x1, y2 - y1
            seg_len2 = vx*vx + vy*vy
            if seg_len2 > 0:
                t = ((x - x1) * vx + (y - y1) * vy) / seg_len2
                t_clamped = max(0.0, min(1.0, t))
                proj_x = x1 + t_clamped * vx
                proj_y = y1 + t_clamped * vy
                # distance along segment from x1,y1
                seg_dist = np.sqrt((proj_x - x1)**2 + (proj_y - y1)**2)
                return float(self._ref_cumdist[idx] + seg_dist)

        # Fallback: return the cumulative distance at the closest dense sample
        return float(self._ref_cumdist[idx])

    def update_scaling(self, screen_w, screen_h):
        """
        Recalculates the scale and translation to fit the track 
        perfectly within the new screen dimensions while maintaining aspect ratio.
        """
        padding = 0.05
        # If a rotation is applied, we must compute the rotated bounds
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2

        def _rotate_about_center(x, y):
            # Translate to centre, rotate, translate back
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            return rx + world_cx, ry + world_cy

        # Build rotated extents from inner/outer world points
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
        
        # Reserve left/right UI margins before applying padding so the track
        # never overlaps side UI elements (leaderboard, telemetry, legends).
        inner_w = max(1.0, screen_w - self.left_ui_margin - self.right_ui_margin)
        usable_w = inner_w * (1 - 2 * padding)
        usable_h = screen_h * (1 - 2 * padding)

        # Calculate scale to fit whichever dimension is the limiting factor
        scale_x = usable_w / world_w
        scale_y = usable_h / world_h
        self.world_scale = min(scale_x, scale_y)

        # Center the world in the screen (rotation done about original centre)
        # world_cx/world_cy are unchanged by rotation about centre
        # Center within the available inner area (left_ui_margin .. screen_w - right_ui_margin)
        screen_cx = self.left_ui_margin + inner_w / 2
        screen_cy = screen_h / 2

        self.tx = screen_cx - self.world_scale * world_cx
        self.ty = screen_cy - self.world_scale * world_cy

        # Update the polyline screen coordinates based on new scale
        self.screen_inner_points = [self.world_to_screen(x, y) for x, y in self.world_inner_points]
        self.screen_outer_points = [self.world_to_screen(x, y) for x, y in self.world_outer_points]

    def on_resize(self, width, height):
        """Called automatically by Arcade when window is resized."""
        super().on_resize(width, height)
        self.update_scaling(width, height)
        # notify components
        self.leaderboard_comp.x = max(20, self.width - self.right_ui_margin + 12)
        for c in (self.leaderboard_comp, self.weather_comp, self.legend_comp, self.driver_info_comp, self.progress_bar_comp, self.race_controls_comp, self.tyre_strategy_comp, self.chase_cam_hud):
            c.on_resize(self)
        if self.chase_cam:
            self.chase_cam.match_window()
        
        # update persistent text positions
        self.lap_text.x = 20
        self.lap_text.y = self.height - 40
        self.time_text.x = 20
        self.time_text.y = self.height - 80
        self.status_text.x = 20
        self.status_text.y = self.height - 120

    def world_to_screen(self, x, y):
        # Rotate around the track centre (if rotation is set), then scale+translate
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

    def _format_wind_direction(self, degrees):
        if degrees is None:
            return "N/A"
        deg_norm = degrees % 360
        dirs = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
        ]
        idx = int((deg_norm / 22.5) + 0.5) % len(dirs)
        return dirs[idx]

    def on_draw(self):
        self.clear()

        # 1. Draw Background (stretched to fit new window size)
        if self.bg_texture:
            arcade.draw_lrbt_rectangle_textured(
                left=0, right=self.width,
                bottom=0, top=self.height,
                texture=self.bg_texture
            )

        # --- Chase Cam Rendering ---
        if self.chase_cam_active and self.chase_cam:
            # Use the exact same frame indices that _update_chase_cam computed
            # to guarantee camera position and car rendering are perfectly in sync.
            frame = self.frames[self._chase_frame_idx]

            # Update leaderboard order + compute real-time intervals
            self._update_chase_leaderboard(frame)

            # World pass: position camera and draw track + cars
            self.chase_cam.position = (self._chase_cam_x, self._chase_cam_y)
            self.chase_cam.zoom = self.CHASE_CAM_ZOOM
            self.chase_cam.angle = self._chase_cam_angle
            self.chase_cam.use()

            self._draw_chase_cam_world(frame)

            # HUD pass: switch to screen-space camera for dashboard overlay
            self.default_camera.use()
            self.chase_cam_hud.draw(self)

            # Progress bar still usable for seeking
            self.progress_bar_comp.draw(self)
            self.progress_bar_comp.draw_overlays(self)

            # Controls popup still accessible
            self.controls_popup_comp.draw(self)
            return

        # 2. Draw Track (using pre-calculated screen points)
        idx = min(int(self.frame_index), self.n_frames - 1)
        frame = self.frames[idx]
        current_time = frame["t"]
        current_track_status = "GREEN"
        for status in self.track_statuses:
            if status['start_time'] <= current_time and (status['end_time'] is None or current_time < status['end_time']):
                current_track_status = status['status']
                break

        # Map track status -> colour (R,G,B)
        STATUS_COLORS = {
            "GREEN": (150, 150, 150),    # normal grey
            "YELLOW": (220, 180,   0),   # caution
            "RED": (200,  30,  30),      # red-flag
            "VSC": (200, 130,  50),      # virtual safety car / amber-brown
            "SC": (180, 100,  30),       # safety car (darker brown)
        }
        track_color = STATUS_COLORS.get("GREEN", (150, 150, 150))

        if current_track_status == "2":
            track_color = STATUS_COLORS.get("YELLOW")
        elif current_track_status == "4":
            track_color = STATUS_COLORS.get("SC")
        elif current_track_status == "5":
            track_color = STATUS_COLORS.get("RED")
        elif current_track_status == "6" or current_track_status == "7":
            track_color = STATUS_COLORS.get("VSC")
            
        if len(self.screen_inner_points) > 1:
            arcade.draw_line_strip(self.screen_inner_points, track_color, 4)
        if len(self.screen_outer_points) > 1:
            arcade.draw_line_strip(self.screen_outer_points, track_color, 4)
        
        # 2.5 Draw DRS Zones (green segments on outer track edge)
        if hasattr(self, 'drs_zones') and self.drs_zones and self.toggle_drs_zones:
            drs_color = (0, 255, 0)  # Bright green for DRS zones
            
            for _, zone in enumerate(self.drs_zones):
                start_idx = zone["start"]["index"]
                end_idx = zone["end"]["index"]
                
                # Extract the outer track points for this DRS zone segment
                drs_outer_points = []
                for i in range(start_idx, min(end_idx + 1, len(self.x_outer))):
                    x = self.x_outer.iloc[i]
                    y = self.y_outer.iloc[i]
                    sx, sy = self.world_to_screen(x, y)
                    drs_outer_points.append((sx, sy))
                
                # Draw the DRS zone segment
                if len(drs_outer_points) > 1:
                    arcade.draw_line_strip(drs_outer_points, drs_color, 6)

        draw_finish_line(self)
        # 3. Draw Cars
        frame = self.frames[idx]
        
        # Get selected drivers list safely
        selected_drivers = getattr(self, "selected_drivers", [])
        if not selected_drivers and getattr(self, "selected_driver", None):
            selected_drivers = [self.selected_driver]

        for i, (code, pos) in enumerate(frame["drivers"].items()):
            sx, sy = self.world_to_screen(pos["x"], pos["y"])
            color = self.driver_colors.get(code, arcade.color.WHITE)
            
            is_selected = code in selected_drivers
            
            if self.show_driver_labels or is_selected:
                # Find closest point index on reference track (Optimized KD-Tree)
                _, idx = self.track_tree.query([pos["x"], pos["y"]])
                idx = int(idx)
                
                # Get normal vector in world space
                nx = self._ref_nx[idx]

                ny = self._ref_ny[idx]
                
                # Rotate normal to screen space
                if self._rot_rad:
                    snx = nx * self._cos_rot - ny * self._sin_rot
                    sny = nx * self._sin_rot + ny * self._cos_rot
                else:
                    snx, sny = nx, ny
                
                offset_dist = 45 if i % 2 == 0 else 75
                
                lx = sx + snx * offset_dist
                ly = sy + sny * offset_dist
                
                arcade.draw_line(sx, sy, lx, ly, color, 1)
                
                anchor_x = "left" if snx >= 0 else "right"
                text_padding = 3 if snx >= 0 else -3
                arcade.draw_text(code, lx + text_padding, ly, color, 10, anchor_x=anchor_x, anchor_y="center", bold=True)

            arcade.draw_circle_filled(sx, sy, 6, color)
        
        # --- UI ELEMENTS (Dynamic Positioning) ---
        
        # Determine Leader info using projected along-track distance (more robust than dist)
        # Use the progress metric in metres for each driver and use that to order the leaderboard.
        driver_progress = {}
        for code, pos in frame["drivers"].items():
            # parse lap defensively
            lap_raw = pos.get("lap", 1)
            try:
                lap = int(lap_raw)
            except Exception:
                lap = 1

            # Project (x,y) to reference and combine with lap count
            projected_m = self._project_to_reference(pos.get("x", 0.0), pos.get("y", 0.0))

            # progress in metres since race start: (lap-1) * lap_length + projected_m
            progress_m = float((max(lap, 1) - 1) * self._ref_total_length + projected_m)

            driver_progress[code] = progress_m

        # Leader is the one with greatest progress_m
        if driver_progress:
            leader_code = max(driver_progress, key=lambda c: driver_progress[c])
            leader_lap = frame["drivers"][leader_code].get("lap", 1)
        else:
            leader_code = None
            leader_lap = 1

        # Time Calculation
        t = frame["t"]
        hours = int(t // 3600)
        minutes = int((t % 3600) // 60)
        seconds = int(t % 60)
        time_str = f"{hours:02}:{minutes:02}:{seconds:02}"

        # Format Lap String 
        lap_str = f"Lap: {leader_lap}"
        if self.total_laps is not None:
            lap_str += f"/{self.total_laps}"

        # Draw HUD - Top Left
        if self.visible_hud:
            self.lap_text.text = lap_str
            self.time_text.text = f"Race Time: {time_str} (x{self.playback_speed})"
            # default no status text
            self.status_text.text = ""
            # update status color and text if required
            if current_track_status == "2":
                self.status_text.text = "YELLOW FLAG"
                self.status_text.color = arcade.color.YELLOW
            elif current_track_status == "5":
                self.status_text.text = "RED FLAG"
                self.status_text.color = arcade.color.RED
            elif current_track_status == "6":
                self.status_text.text = "VIRTUAL SAFETY CAR"
                self.status_text.color = arcade.color.ORANGE
            elif current_track_status == "4":
                self.status_text.text = "SAFETY CAR"
                self.status_text.color = arcade.color.BROWN

            self.lap_text.draw()
            self.time_text.draw()
            if self.status_text.text:
                self.status_text.draw()

        # Weather component (set info then draw)
        weather_info = frame.get("weather") if frame else None
        self.weather_comp.set_info(weather_info)
        self.weather_comp.draw(self)
        # optionally expose weather_bottom for driver info layout
        self.weather_bottom = self.height - 170 - 130 if (weather_info or self.has_weather) else None

        # Draw leaderboard via component
        driver_list = []
        for code, pos in frame["drivers"].items():
            color = self.driver_colors.get(code, arcade.color.WHITE)
            progress_m = driver_progress.get(code, float(pos.get("dist", 0.0)))
            driver_list.append((code, color, pos, progress_m))
        driver_list.sort(key=lambda x: x[3], reverse=True)

        self.last_leaderboard_order = [c for c, _, _, _ in driver_list]
        self.leaderboard_comp.set_entries(driver_list)
        self.leaderboard_comp.draw(self)
        # expose rects for existing hit test compatibility if needed
        self.leaderboard_rects = self.leaderboard_comp.rects

        # Controls Legend - Bottom Left (keeps small offset from left UI edge)
        self.legend_comp.draw(self)
        
        # Selected driver info component
        self.driver_info_comp.draw(self)
        
        # Race Progress Bar with event markers (DNF, flags, leader changes)
        self.progress_bar_comp.draw(self)
        
        # Race playback control buttons
        self.race_controls_comp.draw(self)
        
        # Session info banner (top of screen)
        self.session_info_comp.draw(self)

        # Tyre strategy timeline overlay
        self.tyre_strategy_comp.draw(self)

        # Draw Controls popup box
        self.controls_popup_comp.draw(self)
        
        # Draw tooltips and overlays on top of everything
        self.progress_bar_comp.draw_overlays(self)
                    
    def on_update(self, delta_time: float):
        self.race_controls_comp.on_update(delta_time)

        seek_speed = 3.0 * max(1.0, self.playback_speed) # Multiplier for seeking speed, scales with current playback speed
        if self.is_rewinding:
            self.frame_index = max(0.0, self.frame_index - delta_time * FPS * seek_speed)
            self.race_controls_comp.flash_button('rewind')
        elif self.is_forwarding:
            self.frame_index = min(self.n_frames - 1, self.frame_index + delta_time * FPS * seek_speed)
            self.race_controls_comp.flash_button('forward')

        if self.paused:
            self._update_chase_cam(delta_time)
            return

        self.frame_index += delta_time * FPS * self.playback_speed

        if self.frame_index >= self.n_frames:
            self.frame_index = float(self.n_frames - 1)

        # Update chase cam AFTER frame_index is finalized so camera and
        # rendered cars use the exact same frame data (no 1-frame desync).
        self._update_chase_cam(delta_time)

    def on_key_press(self, symbol: int, modifiers: int):
        # Allow ESC to close window at any time (exit chase cam first)
        if symbol == arcade.key.ESCAPE:
            if self.chase_cam_active:
                self._deactivate_chase_cam()
                return
            arcade.close_window()
            return
        # V: toggle chase cam
        if symbol == arcade.key.V:
            if self.chase_cam_active:
                self._deactivate_chase_cam()
            else:
                driver = getattr(self, 'selected_driver', None)
                if driver:
                    self._activate_chase_cam(driver)
            return
        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
            self.race_controls_comp.flash_button('play_pause')
        elif symbol == arcade.key.RIGHT:
            if self.chase_cam_active:
                self._cycle_chase_driver(1)
                return
            self.was_paused_before_hold = self.paused
            self.is_forwarding = True
            self.paused = True
        elif symbol == arcade.key.LEFT:
            if self.chase_cam_active:
                self._cycle_chase_driver(-1)
                return
            self.was_paused_before_hold = self.paused
            self.is_rewinding = True
            self.paused = True
        elif symbol == arcade.key.UP:
            if self.playback_speed < PLAYBACK_SPEEDS[-1]:
                # Increase to next higher speed
                for spd in PLAYBACK_SPEEDS:
                    if spd > self.playback_speed:
                        self.playback_speed = spd
                        break
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.DOWN:
            if self.playback_speed > PLAYBACK_SPEEDS[0]:
                # Decrease to next lower speed
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
            # Clear degradation cache on restart
            if self.degradation_integrator:
                self.degradation_integrator.clear_cache()
            self.race_controls_comp.flash_button('rewind')
        elif symbol == arcade.key.D:
            self.toggle_drs_zones = not self.toggle_drs_zones
        elif symbol == arcade.key.L:
            self.show_driver_labels = not self.show_driver_labels
        elif symbol == arcade.key.H:
            # Toggle Controls popup with 'H' key — show anchored to bottom-left with 20px margin
            margin_x = 20
            margin_y = 20
            left_pos = float(margin_x)
            top_pos = float(margin_y + self.controls_popup_comp.height)
            if self.controls_popup_comp.visible:
                self.controls_popup_comp.hide()
            else:
                self.controls_popup_comp.show_over(left_pos, top_pos)
        elif symbol == arcade.key.B:
            self.progress_bar_comp.toggle_visibility() # toggle progress bar visibility
        elif symbol == arcade.key.I:
            self.session_info_comp.toggle_visibility() # toggle session info banner
        elif symbol == arcade.key.T:
            self.tyre_strategy_comp.toggle_visibility()

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
        # forward to components; stop at first that handled it
        if self.controls_popup_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.tyre_strategy_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.race_controls_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.progress_bar_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.leaderboard_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.legend_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        # default: clear selection if clicked elsewhere
        self.selected_driver = None
        
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """Handle mouse motion for hover effects on progress bar and controls."""
        self.progress_bar_comp.on_mouse_motion(self, x, y, dx, dy)
        self.race_controls_comp.on_mouse_motion(self, x, y, dx, dy)

    # ------------------------------------------------------------------
    #  Chase Cam helpers
    # ------------------------------------------------------------------

    def _rotate_world(self, x, y):
        """Apply circuit rotation to a world coordinate (no scale/translate)."""
        if not self._rot_rad:
            return x, y
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2
        tx = x - world_cx
        ty = y - world_cy
        rx = tx * self._cos_rot - ty * self._sin_rot
        ry = tx * self._sin_rot + ty * self._cos_rot
        return rx + world_cx, ry + world_cy

    def _compute_heading(self, code, rx, ry):
        """Compute smoothed heading in degrees from position delta.

        Uses a rolling buffer of recent headings to prevent jitter.
        """
        prev = self._prev_driver_pos.get(code)
        if prev is None:
            return self._chase_cam_angle

        px, py = prev
        dx = rx - px
        dy = ry - py
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 1.5:
            # Too close - use buffered average or current angle
            if self._heading_buffer:
                return sum(self._heading_buffer) / len(self._heading_buffer)
            return self._chase_cam_angle

        raw_heading = math.degrees(math.atan2(dy, dx))

        # Add to rolling buffer
        self._heading_buffer.append(raw_heading)
        if len(self._heading_buffer) > self._heading_buffer_size:
            self._heading_buffer.pop(0)

        # Return average heading (smoothed)
        # Use circular mean to handle wrap-around (e.g. 359° and 1°)
        sin_sum = sum(math.sin(math.radians(h)) for h in self._heading_buffer)
        cos_sum = sum(math.cos(math.radians(h)) for h in self._heading_buffer)
        return math.degrees(math.atan2(sin_sum, cos_sum))

    def _update_chase_cam(self, delta_time):
        """Lerp the chase camera toward the target driver each frame.

        Uses sub-frame interpolation between data frames (25 FPS data at 60 Hz
        display rate) to eliminate the ~21-pixel position jumps that are visible
        at 6x zoom.
        """
        if not self.chase_cam_active or not self.chase_cam_driver:
            return

        idx = min(int(self.frame_index), self.n_frames - 1)
        frac = self.frame_index - int(self.frame_index)
        next_idx = min(idx + 1, self.n_frames - 1)
        frame = self.frames[idx]
        code = self.chase_cam_driver

        if code not in frame["drivers"]:
            return

        d = frame["drivers"][code]
        x, y = d["x"], d["y"]

        # Interpolate position between consecutive data frames
        if next_idx != idx and code in self.frames[next_idx]["drivers"]:
            nd = self.frames[next_idx]["drivers"][code]
            x = x + (nd["x"] - x) * frac
            y = y + (nd["y"] - y) * frac

        rx, ry = self._rotate_world(x, y)

        # Store interpolation state for _draw_chase_cam_world and HUD
        self._chase_frac = frac
        self._chase_frame_idx = idx
        self._chase_next_idx = next_idx

        # Heading from position delta in rotated space
        heading_deg = self._compute_heading(code, rx, ry)
        self._prev_driver_pos[code] = (rx, ry)

        # Target camera angle: make heading point up on screen
        target_angle = 90.0 - heading_deg

        # Shortest-path angle interpolation
        angle_diff = ((target_angle - self._chase_cam_angle + 180) % 360) - 180

        # Position: track directly (no lerp) — interpolation already provides
        # smooth sub-frame positions, and any camera lag makes the driver dot
        # oscillate visibly around screen centre at 6x zoom.
        self._chase_cam_x = rx
        self._chase_cam_y = ry

        # Angle: still lerp for smooth rotation feel
        lerp_ang = min(1.0, self.CHASE_CAM_LERP_ANGLE * 60 * delta_time)
        self._chase_cam_angle += angle_diff * lerp_ang

    def _activate_chase_cam(self, driver_code):
        """Enter chase cam mode for the given driver."""
        if self.chase_cam is None:
            self.chase_cam = Camera2D()

        self.chase_cam_active = True
        self.chase_cam_driver = driver_code
        self.chase_cam_hud.visible = True

        # Initialize camera position immediately (no lerp jump)
        idx = min(int(self.frame_index), self.n_frames - 1)
        frame = self.frames[idx]
        if driver_code in frame["drivers"]:
            pos = frame["drivers"][driver_code]
            rx, ry = self._rotate_world(pos["x"], pos["y"])
            self._chase_cam_x = rx
            self._chase_cam_y = ry
            self._chase_cam_angle = 0.0

        self._prev_driver_pos.clear()
        self._heading_buffer.clear()

    def _deactivate_chase_cam(self):
        """Exit chase cam and return to normal view."""
        self.chase_cam_active = False
        self.chase_cam_hud.visible = False
        self.default_camera.use()

    def _cycle_chase_driver(self, direction):
        """Cycle to next/prev driver by leaderboard position."""
        if not self.last_leaderboard_order:
            return

        order = self.last_leaderboard_order
        try:
            current_idx = order.index(self.chase_cam_driver)
        except ValueError:
            current_idx = 0

        new_idx = (current_idx + direction) % len(order)
        new_driver = order[new_idx]

        self.chase_cam_driver = new_driver
        self.selected_driver = new_driver
        self._prev_driver_pos.clear()
        self._heading_buffer.clear()

    def _update_chase_leaderboard(self, frame):
        """Recompute leaderboard order and store sorted entries for the HUD."""
        driver_progress = {}
        for code, pos in frame["drivers"].items():
            lap_raw = pos.get("lap", 1)
            try:
                lap = int(lap_raw)
            except Exception:
                lap = 1
            projected_m = self._project_to_reference(pos.get("x", 0.0), pos.get("y", 0.0))
            progress_m = float((max(lap, 1) - 1) * self._ref_total_length + projected_m)
            driver_progress[code] = progress_m

        # Sort by distance travelled (leader first) — same format as leaderboard_comp.entries
        sorted_entries = []
        for code, prog in sorted(driver_progress.items(), key=lambda x: x[1], reverse=True):
            color = self.driver_colors.get(code, arcade.color.WHITE)
            pos = frame["drivers"][code]
            sorted_entries.append((code, color, pos, prog))

        self.last_leaderboard_order = [c for c, _, _, _ in sorted_entries]

        # Expose entries so the HUD can compute gaps using the same formula
        # as DriverInfoComponent (distance / 10 / 55.56 m/s reference speed)
        self._chase_leaderboard_entries = sorted_entries

    def _draw_chase_cam_world(self, frame):
        """Draw the track and cars in rotated-world coordinates under the chase camera."""

        # Determine track color from status
        current_time = frame["t"]
        current_track_status = "GREEN"
        for status in self.track_statuses:
            if status['start_time'] <= current_time and (status['end_time'] is None or current_time < status['end_time']):
                current_track_status = status['status']
                break

        STATUS_COLORS = {
            "GREEN": (150, 150, 150),
            "YELLOW": (220, 180, 0),
            "RED": (200, 30, 30),
            "VSC": (200, 130, 50),
            "SC": (180, 100, 30),
        }
        track_color = STATUS_COLORS.get("GREEN")
        if current_track_status == "2":
            track_color = STATUS_COLORS.get("YELLOW")
        elif current_track_status == "4":
            track_color = STATUS_COLORS.get("SC")
        elif current_track_status == "5":
            track_color = STATUS_COLORS.get("RED")
        elif current_track_status in ("6", "7"):
            track_color = STATUS_COLORS.get("VSC")

        # Draw track edges (thicker lines reduce aliasing shimmer during rotation)
        if len(self._rotated_inner) > 1:
            arcade.draw_line_strip(self._rotated_inner, track_color, 6)
        if len(self._rotated_outer) > 1:
            arcade.draw_line_strip(self._rotated_outer, track_color, 6)

        # Draw DRS zones (pre-computed)
        if self.toggle_drs_zones and self._rotated_drs_zones:
            drs_color = (0, 255, 0)
            for pts in self._rotated_drs_zones:
                if len(pts) > 1:
                    arcade.draw_line_strip(pts, drs_color, 6)

        # Draw cars with sub-frame interpolation
        frac = self._chase_frac
        cur_idx = self._chase_frame_idx
        nxt_idx = self._chase_next_idx
        next_frame = self.frames[nxt_idx] if nxt_idx != cur_idx else frame

        for code, pos in frame["drivers"].items():
            x, y = pos["x"], pos["y"]

            # Interpolate between data frames for smooth motion at 6x zoom
            if nxt_idx != cur_idx and code in next_frame["drivers"]:
                nd = next_frame["drivers"][code]
                x = x + (nd["x"] - x) * frac
                y = y + (nd["y"] - y) * frac

            rx, ry = self._rotate_world(x, y)
            color = self.driver_colors.get(code, arcade.color.WHITE)

            if code == self.chase_cam_driver:
                # Highlighted chased driver with glow
                arcade.draw_circle_filled(rx, ry, 16, (*color[:3], 60))
                arcade.draw_circle_filled(rx, ry, 10, color)
            else:
                arcade.draw_circle_filled(rx, ry, 6, color)
                # Label other drivers with their code
                self._chase_label.text = code
                self._chase_label.color = color
                self._chase_label.x = rx
                self._chase_label.y = ry + 10
                self._chase_label.draw()