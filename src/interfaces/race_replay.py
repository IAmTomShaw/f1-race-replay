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
    extract_race_events,
    build_track_from_example_lap
)


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1200
SCREEN_TITLE = "F1 Race Replay"

class F1RaceReplayWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, circuit_rotation=0.0,
                 left_ui_margin=340, right_ui_margin=260, total_laps=None):
        # Set resizable to True so the user can adjust mid-sim
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, title, resizable=True)

        self.frames = frames
        self.track_statuses = track_statuses
        self.n_frames = len(frames)
        self.drivers = list(drivers)
        self.playback_speed = playback_speed
        self.driver_colors = driver_colors or {}
        self.frame_index = 0.0  # use float for fractional-frame accumulation
        self.paused = False
        self.total_laps = total_laps
        self.has_weather = any("weather" in frame for frame in frames) if frames else False

        # Rotation (degrees) to apply to the whole circuit around its centre
        self.circuit_rotation = circuit_rotation
        self._rot_rad = float(np.deg2rad(self.circuit_rotation)) if self.circuit_rotation else 0.0
        self._cos_rot = float(np.cos(self._rot_rad))
        self._sin_rot = float(np.sin(self._rot_rad))
        self.finished_drivers = []
        self.left_ui_margin = left_ui_margin
        self.right_ui_margin = right_ui_margin
        self.toggle_drs_zones = True 
        # UI components
        leaderboard_x = max(20, self.width - self.right_ui_margin + 12)
        self.leaderboard_comp = LeaderboardComponent(x=leaderboard_x, width=240)
        self.weather_comp = WeatherComponent(left=20, top_offset=170)
        self.legend_comp = LegendComponent(x=max(12, self.left_ui_margin - 320))
        self.driver_info_comp = DriverInfoComponent(left=20, width=300)
        
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
            center_y=100
        )
        
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

        # Trigger initial scaling calculation
        self.update_scaling(self.width, self.height)

        # Selection & hit-testing state for leaderboard
        self.selected_driver = None
        self.leaderboard_rects = []  # list of tuples: (code, left, bottom, right, top)

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
        for c in (self.leaderboard_comp, self.weather_comp, self.legend_comp, self.driver_info_comp, self.progress_bar_comp, self.race_controls_comp):
            c.on_resize(self)

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

        # 3. Draw Cars
        frame = self.frames[idx]
        for code, pos in frame["drivers"].items():
            sx, sy = self.world_to_screen(pos["x"], pos["y"])
            color = self.driver_colors.get(code, arcade.color.WHITE)
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
        arcade.Text(lap_str,
                          20, self.height - 40, 
                          arcade.color.WHITE, 24, anchor_y="top").draw()
        
        arcade.Text(f"Race Time: {time_str} (x{self.playback_speed})", 
                         20, self.height - 80, 
                         arcade.color.WHITE, 20, anchor_y="top").draw()
        
        if current_track_status == "2":
            status_text = "YELLOW FLAG"
            arcade.Text(status_text, 
                             20, self.height - 120,
                             arcade.color.YELLOW, 24, bold=True, anchor_y="top").draw()
        elif current_track_status == "5":
            status_text = "RED FLAG"
            arcade.Text(status_text, 
                             20, self.height - 120, 
                             arcade.color.RED, 24, bold=True, anchor_y="top").draw()
        elif current_track_status == "6":
            status_text = "VIRTUAL SAFETY CAR"
            arcade.Text(status_text, 
                             20, self.height - 120, 
                             arcade.color.ORANGE, 24, bold=True, anchor_y="top").draw()
        elif current_track_status == "4":
            status_text = "SAFETY CAR"
            arcade.Text(status_text, 
                             20, self.height - 120, 
                             arcade.color.BROWN, 24, bold=True, anchor_y="top").draw()

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
        self.leaderboard_comp.set_entries(driver_list)
        self.leaderboard_comp.draw(self)
        # expose rects for existing hit test compatibility if needed
        self.leaderboard_rects = self.leaderboard_comp.rects

        # Controls Legend - Bottom Left (keeps small offset from left UI edge)
        legend_x = max(12, self.left_ui_margin - 320) if hasattr(self, "left_ui_margin") else 20
        legend_y = 200 # Height of legend block
        legend_icons = self.legend_comp._control_icons_textures # icons
        legend_lines = [
            ("Controls:"),
            ("[SPACE]  Pause/Resume"),
            ("Rewind / FastForward", ("[", "/", "]"),("arrow-left", "arrow-right")), # text, brackets, icons
            ("Speed +/- (0.5x, 1x, 2x, 4x)", ("[", "/", "]"), ("arrow-up", "arrow-down")), # text, brackets, icons
            ("[R]       Restart"),
            ("[D]       Toggle DRS Zones"),
            ("[B]       Toggle Progress Bar"),
            ("[Shift + Click] Select Multiple Drivers")

        ]
        
        for i, lines in enumerate(legend_lines):
            line = lines[0] if isinstance(lines, tuple) else lines # main text
            brackets = lines[1] if isinstance(lines, tuple) and len(lines) > 2 else None # brackets only if icons exist
            icon_keys = lines[2] if isinstance(lines, tuple) and len(lines) > 2 else None # icon keys
        
            icon_size = 14
            # Draw icons if any
            if icon_keys:
                control_icon_x = legend_x + 12
                for key in icon_keys:
                    icon_texture = legend_icons.get(key)
                    if icon_texture:
                        control_icon_y = legend_y - (i * 25) + 5 # slight vertical offset
                        rect = arcade.XYWH(control_icon_x, control_icon_y, icon_size, icon_size)
                        arcade.draw_texture_rect(
                            rect = rect,
                            texture = icon_texture,
                            angle = 0,
                            alpha = 255
                        )
                        control_icon_x += icon_size + 6  # spacing between icons  
            # Draw brackets if any              
            if brackets:
                for j in range(len(brackets)):
                    arcade.Text(
                        brackets[j],
                        legend_x + (j * (icon_size + 5)),
                        legend_y - (i * 25),
                        arcade.color.LIGHT_GRAY if i > 0 else arcade.color.WHITE,
                        14,
                    ).draw()
            # Draw the text line
            arcade.Text(
                line,
                legend_x + (60 if icon_keys else 0),
                legend_y - (i * 25),
                arcade.color.LIGHT_GRAY if i > 0 else arcade.color.WHITE,
                14,
                bold=(i == 0)
            ).draw()
        
        # Selected driver info component
        self.driver_info_comp.draw(self)
        
        # Race Progress Bar with event markers (DNF, flags, leader changes)
        self.progress_bar_comp.draw(self)
        
        # Race playback control buttons
        self.race_controls_comp.draw(self)
        
        # Draw tooltips and overlays on top of everything
        self.progress_bar_comp.draw_overlays(self)
                    
    def on_update(self, delta_time: float):
        # Update race controls component (for flash animations)
        self.race_controls_comp.on_update(delta_time)
        if self.paused:
            return
        self.frame_index += delta_time * FPS * self.playback_speed
        if self.frame_index >= self.n_frames:
            self.frame_index = float(self.n_frames - 1)

    def on_key_press(self, symbol: int, modifiers: int):
        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
            self.race_controls_comp.flash_button('play_pause')
        elif symbol == arcade.key.RIGHT:
            self.frame_index = min(self.frame_index + 10.0, self.n_frames - 1)
            self.race_controls_comp.flash_button('forward')
        elif symbol == arcade.key.LEFT:
            self.frame_index = max(self.frame_index - 10.0, 0.0)
            self.race_controls_comp.flash_button('rewind')
        elif symbol == arcade.key.UP:
            self.playback_speed *= 2.0
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.DOWN:
            self.playback_speed = max(0.1, self.playback_speed / 2.0)
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
            self.race_controls_comp.flash_button('rewind')
        elif symbol == arcade.key.D:
            self.toggle_drs_zones = not self.toggle_drs_zones
        elif symbol == arcade.key.B:
            self.progress_bar_comp.toggle_visibility() # toggle progress bar visibility

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        # forward to components; stop at first that handled it
        if self.race_controls_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.progress_bar_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.leaderboard_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        # default: clear selection if clicked elsewhere
        self.selected_driver = None
        
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """Handle mouse motion for hover effects on progress bar and controls."""
        self.progress_bar_comp.on_mouse_motion(self, x, y, dx, dy)
        self.race_controls_comp.on_mouse_motion(self, x, y, dx, dy)