"""
import os
import arcade
import numpy as np
from src.f1_data import FPS

# Kept these as "default" starting sizes, but they are no longer hard limits
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 900
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

    def _interpolate_points(self, xs, ys, interp_points=2000):
        # Generates smooth points in WORLD coordinates.
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def update_scaling(self, screen_w, screen_h):

        # Recalculates the scale and translation to fit the track
        # perfectly within the new screen dimensions while maintaining aspect ratio.

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
        # Called automatically by Arcade when window is resized.
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
            "VSC": (200, 130,  50),      # virtual safety car / amber-brown
            "SC": (180, 100,  30),       # safety car (darker brown)
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

        # Sort by distance
        driver_list.sort(key=lambda x: x[2].get("dist", 999), reverse=True)

        row_height = 25
        for i, (code, color, pos) in enumerate(driver_list):
            current_pos = i + 1
            if pos.get("rel_dist", 0) == 1:
                text = f"{current_pos}. {code}   OUT"
            else:
                tyre = pos.get("tyre", "?")
                text = f"{current_pos}. {code}"

            arcade.Text(
                text,
                leaderboard_x,
                leaderboard_y - 30 - (i * row_height),
                color,
                16,
                anchor_x="left", anchor_y="top"
            ).draw()

            # Tyre Icons

            tyre_texture = self._tyre_textures.get(str(tyre).upper())
            if tyre_texture:
                tyre_icon_x = self.width - 30
                tyre_icon_y = leaderboard_y - 30 - (i * row_height) - 12
                icon_size = 16

                rect = arcade.XYWH(tyre_icon_x, tyre_icon_y, icon_size, icon_size)

                # Draw the textured rect
                arcade.draw_texture_rect(
                    rect=rect,
                    texture=tyre_texture,
                    angle=0,   # rotation in degrees from original orientation (keep the same)
                    alpha=255  # transparency (255 = fully opaque)
                )

        # Controls Legend - Bottom Left
        legend_x = 20
        legend_y = 150 # Height of legend block
        legend_lines = [
            "Controls:",
            "[SPACE]  Pause/Resume",
            "[←/→]    Rewind / FastForward",
            "[↑/↓]    Speed +/- (0.5x, 1x, 2x, 4x)",
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
    
"""

import os
import arcade
import arcade.gui
import numpy as np
import fastf1
import threading
from functools import partial
from src.f1_data import FPS, load_race_session, get_race_telemetry

SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 900
SCREEN_TITLE = "F1 Replay - Visual Dashboard"


def build_track_from_example_lap(example_lap, track_width=200):
    plot_x_ref = example_lap["X"].to_numpy()
    plot_y_ref = example_lap["Y"].to_numpy()

    dx = np.gradient(plot_x_ref)
    dy = np.gradient(plot_y_ref)

    norm = np.sqrt(dx ** 2 + dy ** 2)
    norm[norm == 0] = 1.0
    dx /= norm
    dy /= norm

    nx = -dy
    ny = dx

    x_outer = plot_x_ref + nx * (track_width / 2)
    y_outer = plot_y_ref + ny * (track_width / 2)
    x_inner = plot_x_ref - nx * (track_width / 2)
    y_inner = plot_y_ref - ny * (track_width / 2)

    x_min = min(plot_x_ref.min(), x_inner.min(), x_outer.min())
    x_max = max(plot_x_ref.max(), x_inner.max(), x_outer.max())
    y_min = min(plot_y_ref.min(), y_inner.min(), y_outer.min())
    y_max = max(plot_y_ref.max(), y_inner.max(), y_outer.max())

    return (plot_x_ref, plot_y_ref, x_inner, y_inner, x_outer, y_outer,
            x_min, x_max, y_min, y_max)


class F1ReplayWindow(arcade.Window):
    def __init__(self):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, resizable=True)

        self.frames = []
        self.track_statuses = []
        self.drivers = {}
        self.driver_colors = {}
        self.n_frames = 0
        self.frame_index = 0.0
        self.paused = True
        self.playback_speed = 1.0
        self.is_loaded = False
        self.menu_mode = True

        self.selected_driver = None

        self.is_loading = False
        self.loading_progress = 0.0
        self.loading_text = ""
        self.temp_loaded_data = None
        self.load_error_msg = None

        self.world_scale = 1.0
        self.tx = 0.0
        self.ty = 0.0

        self.x_min = self.x_max = self.y_min = self.y_max = 0
        self.screen_inner_points = []
        self.screen_outer_points = []

        self.bg_texture = None
        self._tyre_textures = {}
        self._load_textures()

        self.ui_manager = arcade.gui.UIManager()
        self.ui_manager.enable()

        self.selected_year = 2023
        self.schedule_cache = {}

        self.setup_menu_ui()
        self.refresh_schedule()

        arcade.set_background_color(arcade.color.BLACK)

    def _load_textures(self):
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    name = os.path.splitext(filename)[0]
                    path = os.path.join(tyres_folder, filename)
                    self._tyre_textures[name] = arcade.load_texture(path)

        bg_path = os.path.join("resources", "background.png")
        if os.path.exists(bg_path):
            self.bg_texture = arcade.load_texture(bg_path)

    def setup_menu_ui(self):
        self.ui_manager.clear()
        self.anchor_layout = arcade.gui.UIAnchorLayout()
        self.main_menu_box = arcade.gui.UIBoxLayout(vertical=True, space_between=20)

        year_control_box = arcade.gui.UIBoxLayout(vertical=False, space_between=20)

        prev_btn = arcade.gui.UIFlatButton(text="<", width=50)
        next_btn = arcade.gui.UIFlatButton(text=">", width=50)
        self.year_label = arcade.gui.UILabel(
            text=f"Season {self.selected_year}",
            font_size=24,
            text_color=arcade.color.WHITE,
            width=200,
            align="center"
        )

        @prev_btn.event("on_click")
        def on_prev(event):
            if self.is_loading: return
            self.selected_year -= 1
            self.year_label.text = f"Season {self.selected_year}"
            self.refresh_schedule()

        @next_btn.event("on_click")
        def on_next(event):
            if self.is_loading: return
            self.selected_year += 1
            self.year_label.text = f"Season {self.selected_year}"
            self.refresh_schedule()

        year_control_box.add(prev_btn)
        year_control_box.add(self.year_label)
        year_control_box.add(next_btn)
        self.main_menu_box.add(year_control_box)

        instruction_label = arcade.gui.UILabel(
            text="Select a Grand Prix to Start",
            font_size=14,
            text_color=arcade.color.LIGHT_GRAY,
            align="center"
        )
        self.main_menu_box.add(instruction_label)

        self.grid_container = arcade.gui.UIBoxLayout(vertical=True, space_between=10)
        self.main_menu_box.add(self.grid_container)

        self.anchor_layout.add(self.main_menu_box, anchor_x="center", anchor_y="center")
        self.ui_manager.add(self.anchor_layout)

    def refresh_schedule(self):
        print(f"Fetching schedule for {self.selected_year}...")
        self.grid_container.clear()

        try:
            if self.selected_year in self.schedule_cache:
                schedule = self.schedule_cache[self.selected_year]
            else:
                schedule = fastf1.get_event_schedule(self.selected_year, include_testing=False)
                self.schedule_cache[self.selected_year] = schedule

            events = schedule.to_dict('records')

            if not events:
                no_data_label = arcade.gui.UILabel(text="No Data Found", text_color=arcade.color.RED)
                self.grid_container.add(no_data_label)
                return

            max_cols = 6
            events = events[:24]
            num_rows = (len(events) + max_cols - 1) // max_cols

            for r in range(num_rows):
                row_box = arcade.gui.UIBoxLayout(vertical=False, space_between=10)
                row_events = events[r * max_cols: (r + 1) * max_cols]

                for event in row_events:
                    round_num = event['RoundNumber']
                    country = event['Country']
                    btn_text = f"R{round_num} {country}"

                    btn = arcade.gui.UIFlatButton(text=btn_text, width=140, height=70)
                    btn.on_click = partial(self.on_gp_clicked, year=self.selected_year, round_num=round_num)

                    row_box.add(btn)

                self.grid_container.add(row_box)

        except Exception as e:
            print(f"Error fetching schedule: {e}")
            error_label = arcade.gui.UILabel(text="Failed to load schedule.", text_color=arcade.color.RED)
            self.grid_container.add(error_label)

    def on_gp_clicked(self, event, year, round_num):
        print(f"Selected: {year} Round {round_num}")
        self.is_loading = True
        self.loading_progress = 0.0
        self.loading_text = "Connecting to F1 Server..."
        self.ui_manager.clear()

        thread = threading.Thread(target=self._load_data_thread, args=(year, round_num))
        thread.start()

    def _load_data_thread(self, year, round_num):
        try:
            self.loading_text = "Downloading Session Data..."
            self.loading_progress = 0.1

            session = load_race_session(year, round_num)

            self.loading_progress = 0.2
            self.loading_text = "Session Loaded. Processing Telemetry..."

            def update_progress(p, msg):
                self.loading_progress = 0.2 + (p * 0.8)
                self.loading_text = msg

            data = get_race_telemetry(session, progress_callback=update_progress)

            self.temp_loaded_data = {
                "session": session,
                "data": data
            }
        except Exception as e:
            print(f"Loading Thread Error: {e}")
            self.load_error_msg = str(e)

    def setup_ingame_ui(self):
        self.ui_manager.clear()
        anchor = arcade.gui.UIAnchorLayout()

        back_btn = arcade.gui.UIFlatButton(text="Back to Menu", width=150)

        @back_btn.event("on_click")
        def on_back(event):
            self.menu_mode = True
            self.is_loaded = False
            self.selected_driver = None
            self.setup_menu_ui()
            self.refresh_schedule()

        anchor.add(back_btn, anchor_x="left", anchor_y="top", align_x=20, align_y=-20)
        self.ui_manager.add(anchor)

    def _interpolate_points(self, xs, ys, interp_points=2000):
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def fit_track_to_screen(self, screen_w, screen_h):
        if not self.is_loaded: return

        LEFT_MARGIN = 300
        RIGHT_MARGIN = 250
        TOP_MARGIN = 50
        BOTTOM_MARGIN = 50

        usable_w = screen_w - LEFT_MARGIN - RIGHT_MARGIN
        usable_h = screen_h - TOP_MARGIN - BOTTOM_MARGIN

        if usable_w < 100: usable_w = 100
        if usable_h < 100: usable_h = 100

        world_w = max(1.0, self.x_max - self.x_min)
        world_h = max(1.0, self.y_max - self.y_min)

        scale_x = usable_w / world_w
        scale_y = usable_h / world_h

        self.world_scale = min(scale_x, scale_y) * 0.9

        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2

        screen_cx = LEFT_MARGIN + (usable_w / 2)
        screen_cy = BOTTOM_MARGIN + (usable_h / 2)

        self.tx = screen_cx - (self.world_scale * world_cx)
        self.ty = screen_cy - (self.world_scale * world_cy)

        self.update_track_points()

    def update_track_points(self):
        self.screen_inner_points = [self.world_to_screen(x, y) for x, y in self.world_inner_points]
        self.screen_outer_points = [self.world_to_screen(x, y) for x, y in self.world_outer_points]

    def world_to_screen(self, x, y):
        sx = self.world_scale * x + self.tx
        sy = self.world_scale * y + self.ty
        return sx, sy

    def on_resize(self, width, height):
        super().on_resize(width, height)
        if self.is_loaded:
            self.fit_track_to_screen(width, height)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if self.menu_mode or not self.is_loaded: return
        zoom_factor = 1.1
        if scroll_y > 0:
            self.world_scale *= zoom_factor
        elif scroll_y < 0:
            self.world_scale /= zoom_factor
        self.update_track_points()

    def on_mouse_press(self, x, y, button, modifiers):
        if self.menu_mode or not self.is_loaded: return

        # 리더보드 영역 클릭
        leaderboard_x_start = self.width - 220
        leaderboard_y_start = self.height - 40

        if x > leaderboard_x_start:
            idx = min(int(self.frame_index), self.n_frames - 1)
            frame = self.frames[idx]

            driver_list = []
            for code, pos in frame["drivers"].items():
                driver_list.append((code, pos))
            driver_list.sort(key=lambda x: x[1].get("dist", -1), reverse=True)

            click_offset = leaderboard_y_start - 30 - y
            if click_offset > 0:
                row_index = int(click_offset // 25)
                if 0 <= row_index < len(driver_list):
                    clicked_code = driver_list[row_index][0]
                    self.selected_driver = clicked_code
                    print(f"Driver Selected: {self.selected_driver}")

    def on_key_press(self, symbol, modifiers):
        if self.menu_mode: return
        if not self.is_loaded: return

        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
        elif symbol == arcade.key.RIGHT:
            self.frame_index = min(self.frame_index + 10.0, self.n_frames - 1)
        elif symbol == arcade.key.LEFT:
            self.frame_index = max(self.frame_index - 10.0, 0.0)
        elif symbol == arcade.key.UP:
            self.playback_speed *= 2
        elif symbol == arcade.key.DOWN:
            self.playback_speed /= 2

    def on_update(self, delta_time):
        if self.is_loading:
            if self.temp_loaded_data:
                session = self.temp_loaded_data['session']
                data = self.temp_loaded_data['data']

                self.frames = data["frames"]
                self.track_statuses = data["track_statuses"]
                self.driver_colors = data["driver_colors"]
                self.n_frames = len(self.frames)

                if self.frames:
                    self.drivers = list(self.frames[0]["drivers"].keys())
                    # [수정] KeyError 해결: drivers 리스트의 첫 번째 요소를 직접 사용
                    self.selected_driver = self.drivers[0] if self.drivers else None

                fastest_lap = session.laps.pick_fastest()
                tel = fastest_lap.get_telemetry()

                (self.x_ref, self.y_ref, self.x_inner, self.y_inner,
                 self.x_outer, self.y_outer, self.x_min, self.x_max,
                 self.y_min, self.y_max) = build_track_from_example_lap(tel)

                self.world_inner_points = self._interpolate_points(self.x_inner, self.y_inner)
                self.world_outer_points = self._interpolate_points(self.x_outer, self.y_outer)

                self.is_loaded = True
                self.fit_track_to_screen(self.width, self.height)
                self.paused = False
                self.frame_index = 0

                self.setup_ingame_ui()
                self.is_loading = False
                self.menu_mode = False
                self.temp_loaded_data = None
                print("Race Loaded via Thread!")

            elif self.load_error_msg:
                self.is_loading = False
                self.menu_mode = True
                self.setup_menu_ui()
                self.refresh_schedule()
                self.load_error_msg = None

            return

        if self.menu_mode: return
        if not self.is_loaded or self.paused: return

        self.frame_index += delta_time * FPS * self.playback_speed
        if self.frame_index >= self.n_frames:
            self.frame_index = float(self.n_frames - 1)

    def on_draw(self):
        self.clear()

        if self.bg_texture:
            arcade.draw_lrbt_rectangle_textured(0, self.width, 0, self.height, self.bg_texture)

        if self.is_loading:
            arcade.Text(self.loading_text, self.width / 2, self.height / 2 + 30,
                        arcade.color.WHITE, 16, anchor_x="center").draw()

            bar_w = 400
            bar_h = 10
            cx, cy = self.width / 2, self.height / 2
            bg_rect = arcade.XYWH(cx, cy, bar_w, bar_h)
            arcade.draw_rect_filled(bg_rect, arcade.color.DARK_GRAY)

            fill_w = bar_w * self.loading_progress
            if fill_w > bar_w: fill_w = bar_w

            left_edge = cx - (bar_w / 2)
            fill_cx = left_edge + (fill_w / 2)

            fg_rect = arcade.XYWH(fill_cx, cy, fill_w, bar_h)
            arcade.draw_rect_filled(fg_rect, arcade.color.RED)
            return

        self.ui_manager.draw()

        if self.menu_mode: return
        if not self.frames: return

        idx = min(int(self.frame_index), self.n_frames - 1)
        frame = self.frames[idx]
        current_time = frame["t"]

        current_track_status = "GREEN"
        for status in self.track_statuses:
            if status['start_time'] <= current_time and (
                    status['end_time'] is None or current_time < status['end_time']):
                current_track_status = status['status']
                break

        STATUS_COLORS = {
            "GREEN": (150, 150, 150),
            "YELLOW": (220, 180, 0),
            "RED": (200, 30, 30),
            "VSC": (180, 100, 30),
            "SC": (220, 180, 0),
        }
        track_color = STATUS_COLORS.get("GREEN")
        if current_track_status in ["2", "SC"]:
            track_color = STATUS_COLORS.get("SC")
        elif current_track_status == "5":
            track_color = STATUS_COLORS.get("RED")
        elif current_track_status in ["6", "7"]:
            track_color = STATUS_COLORS.get("VSC")

        if len(self.screen_inner_points) > 1:
            arcade.draw_line_strip(self.screen_inner_points, track_color, 4)
        if len(self.screen_outer_points) > 1:
            arcade.draw_line_strip(self.screen_outer_points, track_color, 4)

        for code, pos in frame["drivers"].items():
            if pos.get("rel_dist", 0) == 1: continue
            sx, sy = self.world_to_screen(pos["x"], pos["y"])
            color = self.driver_colors.get(code, arcade.color.WHITE)
            arcade.draw_circle_filled(sx, sy, 6, color)

            if self.selected_driver == code:
                arcade.draw_circle_outline(sx, sy, 10, arcade.color.YELLOW, 2)

        # HUD
        leader_code = max(frame["drivers"],
                          key=lambda c: (frame["drivers"][c].get("lap", 1), frame["drivers"][c].get("dist", 0)))
        leader_lap = frame["drivers"][leader_code].get("lap", 1)

        t = frame["t"]
        time_str = f"{int(t // 3600):02}:{int((t % 3600) // 60):02}:{int(t % 60):02}"

        arcade.Text(f"Lap: {leader_lap}", 20, self.height - 100, arcade.color.WHITE, 24, anchor_y="top").draw()
        arcade.Text(f"Time: {time_str}", 20, self.height - 140, arcade.color.WHITE, 20, anchor_y="top").draw()

        if self.paused:
            arcade.Text("PAUSED", self.width / 2, self.height - 100, arcade.color.YELLOW, 30, bold=True,
                        anchor_x="center").draw()

        leaderboard_x = self.width - 220
        leaderboard_y = self.height - 40
        arcade.Text("Leaderboard", leaderboard_x, leaderboard_y, arcade.color.WHITE, 20, bold=True,
                    anchor_y="top").draw()

        driver_list = []
        for code, pos in frame["drivers"].items():
            driver_list.append((code, self.driver_colors.get(code, arcade.color.WHITE), pos))

        driver_list.sort(key=lambda x: x[2].get("dist", -1), reverse=True)

        for i, (code, color, pos) in enumerate(driver_list):
            y_pos = leaderboard_y - 30 - (i * 25)
            text = f"{i + 1}. {code}"
            if pos.get("rel_dist", 0) == 1: text += " OUT"

            if self.selected_driver == code:
                arcade.Text(text, leaderboard_x, y_pos, arcade.color.YELLOW, 16, anchor_y="top", bold=True).draw()
            else:
                arcade.Text(text, leaderboard_x, y_pos, color, 16, anchor_y="top").draw()

            tyre = str(pos.get("tyre", "")).upper()
            if tyre in self._tyre_textures:
                rect = arcade.XYWH(self.width - 30, y_pos - 12, 16, 16)
                arcade.draw_texture_rect(self._tyre_textures[tyre], rect)

        # 정보 패널 (우측 하단)
        if self.selected_driver and self.selected_driver in frame["drivers"]:
            d_data = frame["drivers"][self.selected_driver]

            panel_w = 220
            panel_h = 120
            # 위치 조정
            panel_x = self.width - 20 - (panel_w / 2)
            panel_y = 20 + (panel_h / 2) + 120

            center_x = panel_x
            center_y = panel_y

            # 헤더
            header_h = 30
            header_rect = arcade.XYWH(center_x, center_y + (panel_h / 2) - (header_h / 2), panel_w, header_h)
            team_color = self.driver_colors.get(self.selected_driver, arcade.color.GRAY)
            arcade.draw_rect_filled(header_rect, team_color)

            arcade.Text(f"Driver: {self.selected_driver}", center_x - (panel_w / 2) + 10, center_y + (panel_h / 2) - 22,
                        arcade.color.BLACK, 14, bold=True).draw()

            # 바디
            body_h = panel_h - header_h
            body_rect = arcade.XYWH(center_x, center_y - (header_h / 2), panel_w, body_h)
            arcade.draw_rect_filled(body_rect, (0, 0, 0, 200))

            info_y_start = center_y + (panel_h / 2) - header_h - 20
            left_align = center_x - (panel_w / 2) + 10

            arcade.Text(f"Speed: {d_data.get('speed', 0):.1f} km/h", left_align, info_y_start, arcade.color.WHITE,
                        12).draw()
            arcade.Text(f"Gear: {d_data.get('gear', '-')}", left_align, info_y_start - 20, arcade.color.WHITE,
                        12).draw()

            drs_on = d_data.get('drs', 0)
            drs_text = "DRS: On" if drs_on in [10, 12, 14] else "DRS: Off"
            drs_color = arcade.color.GREEN if drs_on in [10, 12, 14] else arcade.color.WHITE
            arcade.Text(drs_text, left_align, info_y_start - 40, drs_color, 12).draw()

            arcade.Text(f"Lap: {d_data.get('lap', '-')}", left_align, info_y_start - 60, arcade.color.WHITE, 12).draw()

        # Controls Legend
        legend_x = 20
        legend_y = 150
        legend_lines = [
            "Controls:",
            "[SPACE]  Pause/Resume",
            "[←/→]    Rewind / FastForward",
            "[↑/↓]    Speed +/- (0.5x, 1x, 2x, 4x)",
            "[Scroll] Zoom In/Out"
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


def run_arcade_replay():
    window = F1ReplayWindow()
    arcade.run()


if __name__ == "__main__":
    run_arcade_replay()