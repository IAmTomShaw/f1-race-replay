import os
import arcade
import numpy as np
from src.f1_data import FPS

# Kept these as "default" starting sizes, but they are no longer hard limits
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1200
SCREEN_TITLE = "F1 Replay"

def build_track_from_example_lap(example_lap, track_width=200):
    plot_x_ref = example_lap["X"].to_numpy()
    plot_y_ref = example_lap["Y"].to_numpy()

    # compute tangents
    dx = np.gradient(plot_x_ref)
    dy = np.gradient(plot_y_ref)

    norm = np.sqrt(dx**2 + dy**2)
    norm[norm == 0] = 1.0
    dx /= norm
    dy /= norm

    nx = -dy
    ny = dx

    x_outer = plot_x_ref + nx * (track_width / 2)
    y_outer = plot_y_ref + ny * (track_width / 2)
    x_inner = plot_x_ref - nx * (track_width / 2)
    y_inner = plot_y_ref - ny * (track_width / 2)

    # world bounds
    x_min = min(plot_x_ref.min(), x_inner.min(), x_outer.min())
    x_max = max(plot_x_ref.max(), x_inner.max(), x_outer.max())
    y_min = min(plot_y_ref.min(), y_inner.min(), y_outer.min())
    y_max = max(plot_y_ref.max(), y_inner.max(), y_outer.max())

    return (plot_x_ref, plot_y_ref, x_inner, y_inner, x_outer, y_outer,
            x_min, x_max, y_min, y_max)


class F1ReplayWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, driver_status=None, driver_finish_frames=None):
        # Set resizable to True so the user can adjust mid-sim
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, title, resizable=True)

        self.frames = frames
        self.track_statuses = track_statuses
        self.n_frames = len(frames)
        self.drivers = list(drivers)
        self.playback_speed = playback_speed
        self.driver_colors = driver_colors or {}
        self.driver_status = driver_status or {}  # Pre-computed driver status from session.results
        self.driver_finish_frames = driver_finish_frames or {}  # Frame when each driver finished
        self.frame_index = 0.0  # use float for fractional-frame accumulation
        self.paused = False
        self._tyre_textures = {}

        # Debug: Print if we have pre-computed data
        if self.driver_status:
            print(f"✓ Loaded driver status data for {len(self.driver_status)} drivers")
            for code, info in list(self.driver_status.items())[:3]:
                print(f"  {code}: DNF={info.get('is_dnf')}, Finished={info.get('is_finished')}, Laps={info.get('laps_completed')}")
        else:
            print("⚠ WARNING: No driver status data found! Run with --refresh-data to regenerate cache.")

        if self.driver_finish_frames:
            print(f"✓ Loaded finish frames for {len(self.driver_finish_frames)} drivers")
        else:
            print("⚠ WARNING: No driver finish frames found! Run with --refresh-data to regenerate cache.")

        # Import the tyre textures from the images/tyres folder (all files)
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(tyres_folder, filename)
                    self._tyre_textures[texture_name] = arcade.load_texture(texture_path)

        # Load chequered flag icon for finished drivers
        self.chequered_flag_icon = None
        chequered_flag_path = os.path.join("images", "tyres", "5.0.png")
        if os.path.exists(chequered_flag_path):
            self.chequered_flag_icon = arcade.load_texture(chequered_flag_path)

        # Build track geometry (Raw World Coordinates)
        (self.plot_x_ref, self.plot_y_ref,
         self.x_inner, self.y_inner,
         self.x_outer, self.y_outer,
         self.x_min, self.x_max,
         self.y_min, self.y_max) = build_track_from_example_lap(example_lap)

        # Pre-calculate interpolated world points ONCE (optimization)
        # We store these as 'world' coordinates, not screen coordinates
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

        # Distance cache for DNF and finish detection
        self.driver_dist_cache = {}  # {driver_code: deque of last 10 dist values}
        self.driver_dnf_status = {}  # {driver_code: bool}
        self.driver_finished_status = {}  # {driver_code: bool}
        self.driver_finish_order = {}  # {driver_code: frame_index when they crossed finish line}
        self.race_finished = False  # Global flag for when leader finishes
        self.leader_dist_cache = []  # Track leader's recent dist values
        self.final_positions = {}  # {driver_code: final_position} - locked after race finish

    def _interpolate_points(self, xs, ys, interp_points=2000):
        """Generates smooth points in WORLD coordinates."""
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def update_scaling(self, screen_w, screen_h):
        """
        Recalculates the scale and translation to fit the track 
        perfectly within the new screen dimensions while maintaining aspect ratio.
        """
        padding = 0.05
        world_w = max(1.0, self.x_max - self.x_min)
        world_h = max(1.0, self.y_max - self.y_min)
        
        usable_w = screen_w * (1 - 2 * padding)
        usable_h = screen_h * (1 - 2 * padding)

        # Calculate scale to fit whichever dimension is the limiting factor
        scale_x = usable_w / world_w
        scale_y = usable_h / world_h
        self.world_scale = min(scale_x, scale_y)

        # Center the world in the screen
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2
        screen_cx = screen_w / 2
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

    def world_to_screen(self, x, y):
        sx = self.world_scale * x + self.tx
        sy = self.world_scale * y + self.ty
        return sx, sy

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

        # 2a. HYBRID APPROACH: Use API data for accuracy + distance deltas for timing

        # Update distance caches for all drivers
        for code, pos in frame["drivers"].items():
            current_dist = pos.get("dist", 0)

            # Initialize cache for new drivers
            if code not in self.driver_dist_cache:
                self.driver_dist_cache[code] = []

            # Add current distance to cache (keep last 10)
            self.driver_dist_cache[code].append(current_dist)
            if len(self.driver_dist_cache[code]) > 10:
                self.driver_dist_cache[code].pop(0)

        # Get driver info from API (if available)
        has_api_data = bool(self.driver_status)

        # DNF Detection (Hybrid):
        # - API tells us WHO will DNF
        # - Distance delta tells us WHEN their car stopped
        for code, pos in frame["drivers"].items():
            driver_info = self.driver_status.get(code, {})
            is_dnf_per_api = driver_info.get('is_dnf', False)

            # Only check distance for drivers the API says will DNF
            if is_dnf_per_api and code not in self.driver_dnf_status:
                if len(self.driver_dist_cache[code]) == 10:
                    dist_values = self.driver_dist_cache[code]
                    # Check if stopped moving (all 10 values within 1 meter)
                    if all(abs(d - dist_values[0]) < 1.0 for d in dist_values):
                        self.driver_dnf_status[code] = True

        # 2b. Race finish detection (Hybrid):
        # - API tells us WHICH lap the winner finished on
        # - Distance delta tells us WHEN the leader crossed the line
        leader_code = max(
            frame["drivers"],
            key=lambda c: (frame["drivers"][c].get("lap", 1), frame["drivers"][c].get("dist", 0))
        )
        leader_dist = frame["drivers"][leader_code].get("dist", 0)
        leader_lap = frame["drivers"][leader_code].get("lap", 1)
        self.leader_dist_cache.append(leader_dist)

        # Keep only last 10 values
        if len(self.leader_dist_cache) > 10:
            self.leader_dist_cache.pop(0)

        # Check if leader has finished based on API data
        if has_api_data and not self.race_finished:
            leader_info = self.driver_status.get(leader_code, {})
            leader_final_laps = leader_info.get('laps_completed', 999)

            # Leader has completed all laps - now wait for distance to stop increasing
            if leader_lap >= leader_final_laps:
                if len(self.leader_dist_cache) >= 2:
                    recent_dists = self.leader_dist_cache[-2:]
                    # Distance stopped = crossed finish line
                    if abs(recent_dists[1] - recent_dists[0]) < 1.0:
                        self.race_finished = True
                        self.driver_finished_status[leader_code] = True
                        self.driver_finish_order[leader_code] = int(self.frame_index)

        # 2c. Mark other drivers as finished when they cross the line
        if self.race_finished:
            for code, pos in frame["drivers"].items():
                driver_info = self.driver_status.get(code, {})
                is_finished_per_api = driver_info.get('is_finished', False)
                is_dnf = self.driver_dnf_status.get(code, False)

                # Only process drivers who finished according to API and haven't DNF'd
                if is_finished_per_api and not is_dnf:
                    if code not in self.driver_finished_status:
                        # Check if their distance stopped increasing (crossed finish line)
                        if len(self.driver_dist_cache[code]) >= 2:
                            recent_dists = self.driver_dist_cache[code][-2:]
                            if abs(recent_dists[-1] - recent_dists[-2]) < 1.0:
                                self.driver_finished_status[code] = True
                                self.driver_finish_order[code] = int(self.frame_index)

        # 2d. Calculate final positions using F1 rules (Hybrid API + Live data)
        if self.race_finished:
            classification_list = []
            for code, pos in frame["drivers"].items():
                # Use API lap count if available, otherwise use current lap
                driver_info = self.driver_status.get(code, {})
                laps_completed = driver_info.get('laps_completed', pos.get("lap", 1))

                crossing_order = self.driver_finish_order.get(code, 999999)
                is_dnf = self.driver_dnf_status.get(code, False)

                classification_list.append({
                    "code": code,
                    "laps": laps_completed,
                    "crossing_order": crossing_order,
                    "is_dnf": is_dnf,
                    "dist": pos.get("dist", 0)
                })

            # F1 Classification: Laps (desc), Crossing order (asc), Distance (desc)
            classification_list.sort(key=lambda x: (-x["laps"], x["crossing_order"], -x["dist"]))

            # Assign final positions
            self.final_positions = {}
            for idx, driver_data in enumerate(classification_list):
                self.final_positions[driver_data["code"]] = idx + 1
        # 3. Track Status and Drawing
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

        # 4. Draw Cars
        for code, pos in frame["drivers"].items():
            if pos.get("rel_dist", 0) == 1:
                continue 
            sx, sy = self.world_to_screen(pos["x"], pos["y"])
            color = self.driver_colors.get(code, arcade.color.WHITE)
            arcade.draw_circle_filled(sx, sy, 6, color)
        
        # --- UI ELEMENTS (Dynamic Positioning) ---
        
        # Determine Leader info
        leader_code = max(
            frame["drivers"],
            key=lambda c: (frame["drivers"][c].get("lap", 1), frame["drivers"][c].get("dist", 0))
        )
        leader_lap = frame["drivers"][leader_code].get("lap", 1)

        # Time Calculation
        t = frame["t"]
        hours = int(t // 3600)
        minutes = int((t % 3600) // 60)
        seconds = int(t % 60)
        time_str = f"{hours:02}:{minutes:02}:{seconds:02}"

        # Draw HUD - Top Left
        arcade.Text(f"Lap: {leader_lap}", 
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

        # Draw Leaderboard - Top Right
        leaderboard_x = self.width - 220
        leaderboard_y = self.height - 40
        
        arcade.Text("Leaderboard", leaderboard_x, leaderboard_y, 
                         arcade.color.WHITE, 20, bold=True, anchor_x="left", anchor_y="top").draw()

        driver_list = []
        for code, pos in frame["drivers"].items():
            color = self.driver_colors.get(code, arcade.color.WHITE)
            driver_list.append((code, color, pos))

        # Sort by distance or final positions if race is finished
        if self.race_finished and self.final_positions:
            # Sort by final positions to maintain accurate standings
            driver_list.sort(key=lambda x: self.final_positions.get(x[0], 999))
        else:
            # Sort by distance during the race
            driver_list.sort(key=lambda x: x[2].get("dist", 999), reverse=True)

        # Reset recorded rects each frame
        self.leaderboard_rects = []

        row_height = 25
        entry_width = 240  # clickable width for each entry
        for i, (code, color, pos) in enumerate(driver_list):
            # Use final positions if race is finished, otherwise use current position
            if self.race_finished and code in self.final_positions:
                current_pos = self.final_positions[code]
            else:
                current_pos = i + 1

            if pos.get("rel_dist", 0) == 1:
                text = f"{current_pos}. {code}   OUT"
            else:
                tyre = pos.get("tyre", "?")
                text = f"{current_pos}. {code}"

            # Compute bounding box for this entry (match how text is positioned)
            top_y = leaderboard_y - 30 - (i * row_height)
            bottom_y = top_y - row_height
            left_x = leaderboard_x
            right_x = leaderboard_x + entry_width

            # Save for mouse hit-testing
            self.leaderboard_rects.append((code, left_x, bottom_y, right_x, top_y))

            # Highlight if selected
            if code == self.selected_driver:
                # subtle highlight behind the text
                rect = arcade.XYWH((left_x + right_x) / 2,
                    (top_y + bottom_y) / 2,
                    right_x - left_x,
                    top_y - bottom_y,)
                arcade.draw_rect_filled(
                    rect,
                    arcade.color.LIGHT_GRAY,
                )
                text_color = arcade.color.BLACK
            else:
                text_color = color

            arcade.Text(
                text,
                left_x,
                top_y,
                text_color,
                16,
                anchor_x="left", anchor_y="top"
            ).draw()

            # DNF Status Indicator and Finish Status
            is_dnf = self.driver_dnf_status.get(code, False)
            is_finished = self.driver_finished_status.get(code, False)

            # Position for status indicators (right side where tire icon normally is)
            status_icon_x = self.width - 30
            status_icon_y = top_y - 12
            icon_size = 16

            if is_dnf:
                # Display DNF in red on the right side
                arcade.Text(
                    "DNF",
                    status_icon_x,
                    top_y,
                    arcade.color.RED,
                    14,
                    bold=True,
                    anchor_x="center", anchor_y="top"
                ).draw()
            elif is_finished and self.chequered_flag_icon:
                # Display chequered flag icon for finished drivers
                rect = arcade.XYWH(status_icon_x, status_icon_y, icon_size, icon_size)
                arcade.draw_texture_rect(
                    rect=rect,
                    texture=self.chequered_flag_icon,
                    angle=0,
                    alpha=255
                )
            else:
                # Display tyre icon for drivers still racing
                tyre_texture = self._tyre_textures.get(str(pos.get("tyre", "?")).upper())
                if tyre_texture:
                    rect = arcade.XYWH(status_icon_x, status_icon_y, icon_size, icon_size)
                    arcade.draw_texture_rect(
                        rect=rect,
                        texture=tyre_texture,
                        angle=0,
                        alpha=255
                    )

        # Controls Legend - Bottom Left
        legend_x = 20
        legend_y = 150 # Height of legend block
        legend_lines = [
            "Controls:",
            "[SPACE]  Pause/Resume",
            "[←/→]    Rewind / FastForward",
            "[↑/↓]    Speed +/- (0.5x, 1x, 2x, 4x)",
            "[R]       Restart",
        ]
        
        for i, line in enumerate(legend_lines):
            arcade.Text(
                line,
                legend_x,
                legend_y - (i * 25),
                arcade.color.LIGHT_GRAY if i > 0 else arcade.color.WHITE,
                14,
                bold=(i == 0)
            ).draw()
        
        # Selected Driver Info - Middle Left

        if self.selected_driver and self.selected_driver in frame["drivers"]:
            # Draw box, with the driver's name in another box at the top of the original box
            driver_pos = frame["drivers"][self.selected_driver]

            # Get DNF status
            is_dnf = self.driver_dnf_status.get(self.selected_driver, False)

            driver_color = self.driver_colors.get(self.selected_driver, arcade.color.GRAY)

            info_x = 20
            info_y = self.height / 2 + 100
            box_width = 300
            box_height = 150

            # Background box

            bg_rect = arcade.XYWH(
                info_x + box_width / 2,
                info_y - box_height / 2,
                box_width,
                box_height
            )

            arcade.draw_rect_outline(
                bg_rect,
                driver_color
            )

            # Driver Name box
            name_rect = arcade.XYWH(
                info_x + box_width / 2,
                info_y + 20,
                box_width,
                40
            )
            arcade.draw_rect_filled(
                name_rect,
                driver_color
            )
            arcade.Text(
                f"Driver: {self.selected_driver}",
                info_x + 10,
                info_y + 20,
                arcade.color.BLACK,
                16,
                anchor_x="left", anchor_y="center"
            ).draw()

            # DNF drivers show only status and last recorded lap
            if is_dnf:
                # Get detailed status from API if available
                driver_info = self.driver_status.get(self.selected_driver, {})
                status_detail = driver_info.get('status', 'DNF')
                laps_completed = driver_info.get('laps_completed', driver_pos.get("lap", 1))

                stats_lines = [
                    f"Status: {status_detail}",
                    f"Laps: {laps_completed}"
                ]
                for i, line in enumerate(stats_lines):
                    arcade.Text(
                        line,
                        info_x + 10,
                        info_y - 20 - (i * 25),
                        arcade.color.RED if i == 0 else arcade.color.WHITE,
                        14,
                        bold=(i == 0),
                        anchor_x="left", anchor_y="center"
                    ).draw()
            else:
                # Driver Stats from Telemetry (normal display)
                speed_text = f"Speed: {driver_pos.get('speed', 0):.1f} km/h"
                gear_text = f"Gear: {driver_pos.get('gear', 0)}"
                drs_status = "off"
                drs_value = driver_pos.get('drs', 0)
                if drs_value in [0, 1]:
                    drs_status = "Off"
                elif drs_value == 8:
                    drs_status = "Eligible"
                elif drs_value in [10, 12, 14]:
                    drs_status = "On"
                else:
                    drs_status = "Unknown"

                drs_active_text = f"DRS: {drs_status}"
                current_lap = driver_pos.get("lap", 1)

                lap_time_text = f"Current Lap: {current_lap}"
                stats_lines = [speed_text, gear_text, drs_active_text, lap_time_text]
                for i, line in enumerate(stats_lines):
                    arcade.Text(
                        line,
                        info_x + 10,
                        info_y - 20 - (i * 25),
                        arcade.color.WHITE,
                        14,
                        anchor_x="left", anchor_y="center"
                    ).draw()
                    
    def on_update(self, delta_time: float):
        if self.paused:
            return
        self.frame_index += delta_time * FPS * self.playback_speed
        if self.frame_index >= self.n_frames:
            self.frame_index = float(self.n_frames - 1)

    def on_key_press(self, symbol: int, modifiers: int):
        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
        elif symbol == arcade.key.RIGHT:
            self.frame_index = min(self.frame_index + 10.0, self.n_frames - 1)
        elif symbol == arcade.key.LEFT:
            self.frame_index = max(self.frame_index - 10.0, 0.0)
        elif symbol == arcade.key.UP:
            self.playback_speed *= 2.0
        elif symbol == arcade.key.DOWN:
            self.playback_speed = max(0.1, self.playback_speed / 2.0)
        elif symbol == arcade.key.KEY_1:
            self.playback_speed = 0.5
        elif symbol == arcade.key.KEY_2:
            self.playback_speed = 1.0
        elif symbol == arcade.key.KEY_3:
            self.playback_speed = 2.0
        elif symbol == arcade.key.KEY_4:
            self.playback_speed = 4.0
        elif symbol == arcade.key.R:
            self.frame_index = 0.0
            self.playback_speed = 1.0

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        # Default: clear selection
        new_selection = None
        for code, left, bottom, right, top in self.leaderboard_rects:
            if left <= x <= right and bottom <= y <= top:
                new_selection = code
                break

        # Toggle if clicking the same entry
        if new_selection == self.selected_driver:
            self.selected_driver = None
        else:
            self.selected_driver = new_selection

def run_arcade_replay(frames, track_statuses, example_lap, drivers, title, playback_speed=1.0, driver_colors=None, driver_status=None, driver_finish_frames=None):
    window = F1ReplayWindow(
        frames=frames,
        track_statuses=track_statuses,
        example_lap=example_lap,
        drivers=drivers,
        playback_speed=playback_speed,
        driver_colors=driver_colors,
        driver_status=driver_status,
        driver_finish_frames=driver_finish_frames,
        title=title
    )
    arcade.run()