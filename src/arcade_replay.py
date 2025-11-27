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
                 playback_speed=1.0, driver_colors=None):
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
        self._tyre_textures = {}

        # Import the tyre textures from the images/tyres folder (all files)
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(tyres_folder, filename)
                    self._tyre_textures[texture_name] = arcade.load_texture(texture_path)

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
            "VSC": (180, 100,  30),      # virtual safety car / amber-brown
            "SC": (220, 180,   0),       # safety car (treat like yellow)
        }
        track_color = STATUS_COLORS.get("GREEN")

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

        # 3. Draw Cars
        frame = self.frames[idx]
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
        
        arcade.Text(f"Race Time: {time_str}", 
                         20, self.height - 80, 
                         arcade.color.WHITE, 20, anchor_y="top").draw()

        # --- NEW: Playback status & speed (Top-left, under Race Time) ---
        # Use a small label showing Pause/Play and the playback multiplier
        status_text = "⏸ Paused" if self.paused else f"▶ Playing  ×{self.playback_speed:.2f}"
        # Draw a subtle background box for readability
        box_x = 18
        box_y = self.height - 120
        arcade.draw_text(status_text, box_x + 10, box_y - 8, arcade.color.WHITE, 14, anchor_y="top")

        # Draw Leaderboard - Top Right
        leaderboard_x = self.width - 220
        leaderboard_y = self.height - 40
        
        arcade.Text("Leaderboard", leaderboard_x, leaderboard_y, 
                         arcade.color.WHITE, 20, bold=True, anchor_x="left", anchor_y="top").draw()

        driver_list = []
        for code, pos in frame["drivers"].items():
            color = self.driver_colors.get(code, arcade.color.WHITE)
            driver_list.append((code, color, pos))
        
        # Sort by distance
        driver_list.sort(key=lambda x: x[2].get("dist", 999), reverse=True)

        # Reset recorded rects each frame
        self.leaderboard_rects = []

        row_height = 25
        entry_width = 240  # clickable width for each entry
        for i, (code, color, pos) in enumerate(driver_list):
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

            # Tyre Icons
            tyre_texture = self._tyre_textures.get(str(pos.get("tyre", "?")).upper())
            if tyre_texture:
                tyre_icon_x = self.width - 30
                tyre_icon_y = top_y - 12
                icon_size = 16

                rect = arcade.XYWH(tyre_icon_x, tyre_icon_y, icon_size, icon_size)

                # Draw the textured rect
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
            "[SPACE]      Pause/Resume",
            "[←/→]        Rewind / FastForward",
            "[ENTER]      Jump to Start",
            "[↑/↓]        Speed +/- (0.5x, 1x, 2x, 4x)",
            "[BACKSPACE]  Reset speed",
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

            # Driver Stats from Telemetry
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
        elif symbol == arcade.key.BACKSPACE:
            self.playback_speed = 1.0
        elif symbol == arcade.key.ENTER:
            self.frame_index = 0.0

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

def run_arcade_replay(frames, track_statuses, example_lap, drivers, title, playback_speed=1.0, driver_colors=None):
    window = F1ReplayWindow(
        frames=frames,
        track_statuses=track_statuses,
        example_lap=example_lap,
        drivers=drivers,
        playback_speed=playback_speed,
        driver_colors=driver_colors,
        title=title
    )
    arcade.run()