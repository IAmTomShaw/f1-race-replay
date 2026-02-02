import os
import arcade
import arcade.gui
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


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "F1 Race Replay"
PLAYBACK_SPEEDS = [0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]





class MovableSection(arcade.gui.UIDraggableMixin, arcade.gui.UIWidget):
    def __init__(self, component, x, y, width, height, **kwargs):
        # Initialize the base UIWidget with the correct size and position
        super().__init__(x=x, y=y, width=width, height=height, **kwargs)
        self.component = component
        self.is_editing = False 

    def on_draw(self):
        # Sync the leaderboard's coordinates to this widget's current x, y
        # We use self.y as the 'top' of the leaderboard
        self.component.x = self.x
        self.component.y = self.y 
        
        # Draw the actual dashboard data
        self.component.draw(arcade.get_window())

        # If we are in Edit Mode, draw a bright cyan box so we can see the grab area
        if self.is_editing:
            # In Arcade 3.0, draw_rect_outline uses a center-based rect (XYWH)
            # We center the outline on the widget
            rect = arcade.XYWH(
                self.x + self.width / 2, 
                self.y - self.height / 2, 
                self.width, 
                self.height
            )
            arcade.draw_rect_outline(rect, arcade.color.CYAN, 2)
            
            # Label the box
            arcade.draw_text("GRAB HERE", self.x + 5, self.y - 15, arcade.color.CYAN, 8)




class F1RaceReplayWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, circuit_rotation=0.0,
                 left_ui_margin=340, right_ui_margin=260, total_laps=None, visible_hud=True,
                 session_info=None, session=None):
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
        self.ui_manager = arcade.gui.UIManager()
        self.ui_manager.enable()
        self.use_custom_dashboard = False
        self.edit_mode = False
        self.use_custom_hud_enabled = use_custom_hud # From your Race Select menu
        self.analyzer_ui = AdvancedAnalyzer(self)
        self.use_custom_hud_enabled = False
        self.telemetry_window = telemetry_window  # Reference to the telemetry window if provided
        self.sender = TelemetrySender()
        

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
        self.legend_comp = LegendComponent(x=max(12, self.left_ui_margin - 320), visible=visible_hud)
        self.driver_info_comp = DriverInfoComponent(left=20, width=300)
        self.controls_popup_comp = ControlsPopupComponent()
        self.race_control_ui = RaceControlPanel(x=50, y=self.height - 150)
        self.session_info = session_info

        self.controls_popup_comp.set_size(340, 250) # width/height of the popup box
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

        self.movable_leaderboard = MovableSection(
            component=self.leaderboard_comp,
            x=500, # Initial X
            y=500, # Initial Y
            width=230, 
            height=400
        )

        self.movable_leaderboard.visible = False
        self.ui_manager.add(self.movable_leaderboard)
        



    def _interpolate_points(self, xs, ys, interp_points=2000):
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def _project_to_reference(self, x, y):
        if self._ref_total_length == 0.0:
            return 0.0

        # Vectorized nearest-point to dense polyline points (sufficient for our purposes)
        dx = self._ref_xs - x
        dy = self._ref_ys - y
        d2 = dx * dx + dy * dy
        idx = int(np.argmin(d2))

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
        for c in (self.leaderboard_comp, self.legend_comp, self.driver_info_comp, self.progress_bar_comp, self.race_controls_comp):
            c.on_resize(self)
        
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




    def draw_dashboard_header(self, session_info, current_lap, total_laps, race_time_str, weather_data):
        """
        Header with Red Flag Placeholder, Circuit Name, and Weather Gauges.
        """
        header_height = 90
        top_y = self.height
        bottom_y = self.height - header_height
        center_x = self.width // 2 
        
        # --- 1. Background ---
        arcade.draw_lrbt_rectangle_filled(
            left=0, right=self.width,
            top=top_y, bottom=bottom_y,
            color=(10, 10, 12, 255)
        )
        arcade.draw_line(0, bottom_y, self.width, bottom_y, (60, 60, 70), 2)

        # --- 2. Flag Placeholder (Red Box) ---
        # Position: Left side, vertically centered in header
        flag_width = 60
        flag_height = 40
        flag_x = 50  # Center X of the flag
        base_y = bottom_y + (header_height / 2) # Center Y of the header

        # DRAW THE RED PLACEHOLDER
        arcade.draw_rect_filled(
            arcade.XYWH(flag_x, base_y, flag_width, flag_height), 
            arcade.color.RED_DEVIL
        )

        # --- 3. Event & Circuit Info ---
        # Text starts to the right of the flag
        text_x = flag_x + (flag_width / 2) + 15 

        # A. Grand Prix Name (Large)
        e_name = session_info.get('event_name', 'Grand Prix')
        arcade.draw_text(e_name, text_x, base_y + 12, arcade.color.WHITE, 20, bold=True, anchor_y="bottom")
        
        # B. Circuit Name (Medium)
        c_name = session_info.get('circuit_name', 'Monaco') 
        arcade.draw_text(c_name, text_x, base_y + 2, arcade.color.GRAY, 12, bold=True, anchor_y="center")
        
        # C. Race Timer (Small)
        arcade.draw_text(race_time_str, text_x, base_y - 18, arcade.color.LIGHT_GRAY, 14, bold=True, anchor_y="top")

        # --- 4. Weather Gauges (Centered) ---
        track_temp = float(weather_data.get('TrackTemp', weather_data.get('track_temp', 0)))
        air_temp = float(weather_data.get('AirTemp', weather_data.get('air_temp', 0)))
        humidity = float(weather_data.get('Humidity', weather_data.get('humidity', 0)))
        wind_speed = float(weather_data.get('WindSpeed', weather_data.get('wind_speed', 0)))
        rainfall = int(weather_data.get('Rainfall', weather_data.get('rainfall', 0)))

        start_gauge_x = center_x - 160
        spacing = 70

        self.draw_gauge(start_gauge_x, base_y, track_temp, 60, "TRC", (255, 60, 0), "{:.1f}")
        self.draw_gauge(start_gauge_x + spacing, base_y, air_temp, 40, "AIR", (100, 255, 50), "{:.1f}")
        self.draw_gauge(start_gauge_x + spacing*2, base_y, humidity, 100, "HUM", (50, 150, 255), "{:.1f}")
        self.draw_gauge(start_gauge_x + spacing*3, base_y, wind_speed, 15, "WIND", (200, 200, 200), "{:.1f}")
        
        rain_color = (0, 100, 255) if rainfall > 0 else (80, 80, 80)
        rain_label = "YES" if rainfall > 0 else "NO"
        self.draw_gauge(start_gauge_x + spacing*4, base_y, 1 if rainfall > 0 else 0, 1, "RAIN", rain_color, rain_label, is_binary=True)
        
        # --- 5. Lap Counter (Right) ---
        arcade.draw_text("LAP", self.width - 160, base_y + 12, arcade.color.GRAY, 12, anchor_x="right", bold=True)
        lap_str = f"{int(current_lap)} / {total_laps}"
        arcade.draw_text(lap_str, self.width - 30, base_y - 12, arcade.color.WHITE, 30, bold=True, anchor_x="right")

        

    def draw_track_status_indicator(self, status_code):
        """
        Draws a sleek status bar just below the main header.
        Codes: 1=Green, 2=Yellow, 4=SC, 5=Red, 6/7=VSC
        """
        # 1. Define Visuals based on Status Code
        if status_code == "1":
            color = (0, 200, 50) # Green
            text = "TRACK CLEAR"
        elif status_code == "2":
            color = (255, 200, 0) # Yellow
            text = "YELLOW FLAG"
        elif status_code == "4":
            color = (255, 120, 0) # Orange
            text = "SAFETY CAR"
        elif status_code == "5":
            color = (200, 0, 0) # Red
            text = "RED FLAG"
        elif status_code in ["6", "7"]:
            color = (255, 160, 50) # Light Orange
            text = "VIRTUAL SAFETY CAR"
        else:
            color = (0, 200, 50) # Default Green
            text = "TRACK CLEAR"

        # 2. Position Code
        header_height = 90
        bar_height = 24
        bar_width = 200
        
        # Position: Centered X, Just below header (Y)
        center_x = self.width // 2
        # self.height is top. Minus header. Minus half bar height. Minus 1px padding.
        center_y = self.height - header_height - (bar_height / 2) - 1 

        # 3. Draw Background Box (Rounded)
        arcade.draw_rect_filled(
            arcade.XYWH(center_x, center_y, bar_width, bar_height),
            color
        )
        
        # Optional: Add a thin dark border for contrast
        arcade.draw_rect_outline(
            arcade.XYWH(center_x, center_y, bar_width, bar_height),
            (20, 20, 20), 2
        )

        # 4. Draw Text
        arcade.draw_text(
            text, 
            center_x, 
            center_y - 5, # slight offset for vertical centering
            arcade.color.BLACK if status_code != "5" else arcade.color.WHITE, 
            12, 
            bold=True, 
            anchor_x="center"
        )


    def draw_gauge(self, x, y, value, max_val, label, color, fmt="{}", is_binary=False):
        """Helper to draw circular gauges with flexible formatting."""
        radius = 24 # Slightly smaller to fit 5 gauges
        
        # Background ring
        arcade.draw_circle_outline(x, y, radius, (40, 40, 40), 3)
        
        # Value Arc
        if is_binary:
            # Full circle filled for binary (Rain)
            if value > 0:
                arcade.draw_circle_outline(x, y, radius, color, 3)
        else:
            # Standard Gauge
            start_angle = -90
            pct = max(0.0, min(1.0, float(value) / max_val))
            arcade.draw_arc_outline(x, y, radius*2, radius*2, color, start_angle, start_angle + (pct * 360), 3)
        
        # Text Value
        if is_binary:
            val_text = fmt # "YES" or "NO" passed in fmt
            font_size = 10
        else:
            val_text = fmt.format(value)
            font_size = 12

        arcade.draw_text(val_text, x, y, arcade.color.WHITE, font_size, bold=True, anchor_x="center", anchor_y="center")
        arcade.draw_text(label, x, y - radius - 10, color, 9, anchor_x="center", bold=True)





    def on_draw(self):
        arcade.set_window(self)
        self.clear()

        # 1. Draw Background
        if self.bg_texture:
            arcade.draw_lrbt_rectangle_textured(
                left=0, right=self.width,
                bottom=0, top=self.height,
                texture=self.bg_texture
            )

        # 2. Frame and Track Setup
        idx = min(int(self.frame_index), self.n_frames - 1)
        frame = self.frames[idx]
        current_time_val = frame["t"] 
        
        # Calculate Track Status
        current_track_status = "1" 
        for status in self.track_statuses:
            if status['start_time'] <= current_time_val and (status['end_time'] is None or current_time_val < status['end_time']):
                current_track_status = status['status']
                break

        # Track Colors logic
        STATUS_COLORS = {
            "GREEN": (150, 150, 150), "YELLOW": (220, 180, 0),
            "RED": (200, 30, 30), "VSC": (200, 130, 50), "SC": (180, 100, 30),
        }
        track_color = STATUS_COLORS.get("GREEN")
        if current_track_status == "2": track_color = STATUS_COLORS.get("YELLOW")
        elif current_track_status == "4": track_color = STATUS_COLORS.get("SC")
        elif current_track_status == "5": track_color = STATUS_COLORS.get("RED")
        elif current_track_status in ["6", "7"]: track_color = STATUS_COLORS.get("VSC")
            
        if len(self.screen_inner_points) > 1:
            arcade.draw_line_strip(self.screen_inner_points, track_color, 4)
        if len(self.screen_outer_points) > 1:
            arcade.draw_line_strip(self.screen_outer_points, track_color, 4)
        
        # Draw DRS Zones and Finish Line
        if hasattr(self, 'drs_zones') and self.drs_zones and self.toggle_drs_zones:
            drs_color = (0, 255, 0)
            for zone in self.drs_zones:
                drs_points = []
                for i in range(zone["start"]["index"], min(zone["end"]["index"] + 1, len(self.x_outer))):
                    sx, sy = self.world_to_screen(self.x_outer.iloc[i], self.y_outer.iloc[i])
                    drs_points.append((sx, sy))
                if len(drs_points) > 1:
                    arcade.draw_line_strip(drs_points, drs_color, 6)
        draw_finish_line(self)

        # 3. Draw Cars
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

        # --- 4. LEADERBOARD DATA PREPARATION ---
        driver_progress = {}
        for code, pos in frame["drivers"].items():
            lap = int(pos.get("lap", 1))
            proj_m = self._project_to_reference(pos.get("x", 0.0), pos.get("y", 0.0))
            driver_progress[code] = float((max(lap, 1) - 1) * self._ref_total_length + proj_m)

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
        # A fixed reference speed for all gap calculations (200 km/h = 55.56 m/s)
        REFERENCE_SPEED_MS = 55.56
        leaderboard_gaps = {}
        leaderboard_neighbor_gaps = {}

        leader_progress_val = driver_list[0][3] if driver_list else None

        if driver_list and leader_progress_val is not None:
            # precompute gaps to leader (time) and interval gaps (dist+time)
            for idx, (code, _, pos, progress_m) in enumerate(driver_list):
                try:
                    raw_to_leader = abs(leader_progress_val - (progress_m or 0.0))
                    dist_to_leader = raw_to_leader / 10.0
                    time_to_leader = dist_to_leader / REFERENCE_SPEED_MS
                    leaderboard_gaps[code] = 0.0 if idx == 0 else time_to_leader
                except Exception:
                    leaderboard_gaps[code] = None

                ahead_info = None
                try:
                    if idx > 0:
                        code_ahead, _, _, progress_ahead = driver_list[idx - 1]
                        raw = abs((progress_m or 0.0) - (progress_ahead or 0.0))
                        dist_m = raw / 10.0
                        time_s = dist_m / REFERENCE_SPEED_MS
                        ahead_info = (code_ahead, dist_m, time_s)
                except Exception:
                    ahead_info = None

                leaderboard_neighbor_gaps[code] = {"ahead": ahead_info}

        self.leaderboard_gaps = leaderboard_gaps
        self.leaderboard_neighbor_gaps = leaderboard_neighbor_gaps

        self.last_leaderboard_order = [c for c, _, _, _ in driver_list]
        self.leaderboard_comp.set_entries(driver_list)
        self.leaderboard_comp.draw(self)
        # expose rects for existing hit test compatibility if needed
        self.leaderboard_rects = self.leaderboard_comp.rects

        # Controls Legend - Bottom Left (keeps small offset from left UI edge)
        self.legend_comp.draw(self)
        
        # --- NEW MERGED LOGIC: Advanced Gap Calculation (From Other User) ---
        # We calculate specific gap times so the LeaderboardComponent can toggle between Interval/Leader
        leaderboard_gaps = {}
        leaderboard_neighbor_gaps = {}
        
        leader_progress_val = raw_list[0][3] if raw_list else None

        if raw_list and leader_progress_val is not None:
            for idx, (code, _, pos, progress_m) in enumerate(raw_list):
                # Gap to Leader
                try:
                    raw_to_leader = abs(leader_progress_val - (progress_m or 0.0))
                    dist_to_leader = raw_to_leader / 10.0
                    time_to_leader = dist_to_leader / REFERENCE_SPEED_MS
                    leaderboard_gaps[code] = 0.0 if idx == 0 else time_to_leader
                except Exception:
                    leaderboard_gaps[code] = None

                # Gap to Car Ahead (Neighbor)
                ahead_info = None
                try:
                    if idx > 0:
                        code_ahead, _, _, progress_ahead = raw_list[idx - 1]
                        raw = abs((progress_m or 0.0) - (progress_ahead or 0.0))
                        dist_m = raw / 10.0
                        time_s = dist_m / REFERENCE_SPEED_MS
                        ahead_info = (code_ahead, dist_m, time_s)
                except Exception:
                    ahead_info = None
                leaderboard_neighbor_gaps[code] = {"ahead": ahead_info}

        # Store these on the window so the component can access them
        self.leaderboard_gaps = leaderboard_gaps
        self.leaderboard_neighbor_gaps = leaderboard_neighbor_gaps
        
        # Prepare final list for component
        final_list = []
        for i, (code, color, pos, progress) in enumerate(raw_list):
            if i == 0:
                gap_str = "Interval"
            else:
                dist_m = (raw_list[i-1][3] - progress) / 10.0
                gap_str = f"+{(dist_m / REFERENCE_SPEED_MS):.2f}s"
            final_list.append((code, color, pos, progress, gap_str))

        self.leaderboard_comp.set_entries(final_list)
        
        # --- 5. DASHBOARD RENDERING ---
        if self.visible_hud:
            weather_info = frame.get("weather") if frame else {}
            
            # --- CUSTOM ANALYZER UI LOGIC (Your Feature) ---
            self.analyzer_ui.update_data(frame, final_list)
            
            if self.analyzer_ui.visible:
                self.analyzer_ui.draw()
            else:
                # Standard UI
                if not self.use_custom_dashboard:
                    self.leaderboard_comp.draw(self)
                    self.driver_info_comp.draw(self)
                else:
                    self.ui_manager.draw()
                
                self.leaderboard_rects = self.leaderboard_comp.rects

            # --- DRAW NEW HEADER (Your Feature) ---
            m, s = divmod(int(current_time_val), 60)
            h, m = divmod(m, 60)
            time_str = f"{h:02d}:{m:02d}:{s:02d}"

            s_info = getattr(self, 'session_info', {})

            self.draw_dashboard_header(
                session_info=s_info,
                current_lap=leader_lap,
                total_laps=self.total_laps,
                race_time_str=time_str,
                weather_data=weather_info
            )
            
            # --- TRACK STATUS BAR (Your Feature) ---
            self.draw_track_status_indicator(current_track_status)

        # 6. Global Static Overlays
        self.legend_comp.draw(self)
        self.progress_bar_comp.draw(self)
        self.race_controls_comp.draw(self)
        self.controls_popup_comp.draw(self)
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
            return

        self.frame_index += delta_time * FPS * self.playback_speed
        
        if self.frame_index >= self.n_frames:
            self.frame_index = float(self.n_frames - 1)

        # SYNC TELEMETRY WINDOW
        if self.telemetry_window:
            self.telemetry_window.update_cursor(self.frame_index)

        current_driver = self.selected_driver if hasattr(self, "selected_driver") else None
        self.sender.send_update(self.frame_index, current_driver)
            

    def on_key_press(self, symbol: int, modifiers: int):
        # Allow ESC to close window at any time
        if symbol == arcade.key.ESCAPE:
            arcade.close_window()
            return
        
        if symbol == arcade.key.M:
            self.analyzer_ui.visible = not self.analyzer_ui.visible
            print(f"Custom UI Visible: {self.analyzer_ui.visible}")

            
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


        if symbol == arcade.key.TAB:
            self.use_custom_dashboard = not self.use_custom_dashboard
            for widget in self.ui_manager.children:
                if isinstance(widget, MovableSection):
                    widget.visible = self.use_custom_dashboard
        
        # Toggle Edit Mode (Show borders for moving)
        if symbol == arcade.key.E:
            if self.use_custom_dashboard:
                self.edit_mode = not self.edit_mode
                for widget in self.ui_manager.children:
                    if isinstance(widget, MovableSection):
                        widget.is_editing = self.edit_mode

    def on_key_release(self, symbol: int, modifiers: int):
        if symbol == arcade.key.RIGHT:
            self.is_forwarding = False
            self.paused = self.was_paused_before_hold
        elif symbol == arcade.key.LEFT:
            self.is_rewinding = False
            self.paused = self.was_paused_before_hold

    

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        # 1. UI Manager
        if self.ui_manager.on_mouse_press(x, y, button, modifiers):
            return

        # 2. Components
        if self.controls_popup_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.race_controls_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.progress_bar_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.legend_comp.on_mouse_press(self, x, y, button, modifiers):
            return
            
        # 3. Leaderboard - FIX: Sync Telemetry BEFORE returning!
        if self.leaderboard_comp.on_mouse_press(self, x, y, button, modifiers):
            # If a driver was selected, sync it immediately
            if self.telemetry_window and self.selected_driver:
                self.telemetry_window.set_driver(self.selected_driver)
            return

        # 4. Clear selection if clicked elsewhere
        self.selected_driver = None
        if self.telemetry_window:
            self.telemetry_window.set_driver(None)


    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int):
        # This is the 'engine' that moves the box while you hold the mouse
        self.ui_manager.on_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int):
        # Notify the UI Manager that the drag is over
        self.ui_manager.on_mouse_release(x, y, button, modifiers)

        if self.is_forwarding or self.is_rewinding:
            self.is_forwarding = False
            self.is_rewinding = False
            self.paused = self.was_paused_before_hold

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        # Notify UI Manager (helps with hover/cursor states)
        self.ui_manager.on_mouse_motion(x, y, dx, dy)
        
        self.progress_bar_comp.on_mouse_motion(self, x, y, dx, dy)
        self.race_controls_comp.on_mouse_motion(self, x, y, dx, dy)