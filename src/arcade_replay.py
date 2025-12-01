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

        # [레이아웃] 여백 조정
        LEFT_MARGIN = 280
        RIGHT_MARGIN = 320
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

        # 리더보드 클릭 감지
        rc_h = 100
        rc_margin = 20
        top_margin = 20

        leaderboard_w = 300
        leaderboard_x_start = self.width - leaderboard_w - 10
        leaderboard_y_start = self.height - top_margin - rc_h - rc_margin

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
                self.race_control_messages = data.get("race_control_messages", [])
                self.n_frames = len(self.frames)

                if self.frames:
                    self.drivers = list(self.frames[0]["drivers"].keys())
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

        # ---------------------------------------------------------------------
        # [UI 배치]
        # ---------------------------------------------------------------------

        MARGIN = 20

        # 1. 레이스 컨트롤 (우측 최상단)
        rc_w = 300
        rc_h = 100
        rc_x_center = self.width - MARGIN - (rc_w / 2)
        rc_y_center = self.height - MARGIN - (rc_h / 2)

        rc_rect = arcade.XYWH(rc_x_center, rc_y_center, rc_w, rc_h)
        arcade.draw_rect_filled(rc_rect, (0,0,0,180))
        arcade.draw_rect_outline(rc_rect, arcade.color.WHITE, 1)

        arcade.Text("Race Control", rc_x_center, rc_y_center + rc_h/2 - 10, arcade.color.ORANGE, 12, bold=True, anchor_x="center", anchor_y="top").draw()

        rc_msgs = [m for m in self.race_control_messages if m['time'] <= current_time]
        rc_msgs.sort(key=lambda x: x['time'], reverse=True)
        recent_rcs = rc_msgs[:3]

        for i, msg in enumerate(recent_rcs):
            y_offset = (i * 25) + 30
            msg_text = msg['message']
            if len(msg_text) > 40: msg_text = msg_text[:37] + "..."
            arcade.Text(msg_text, rc_x_center, rc_y_center + rc_h/2 - y_offset, arcade.color.WHITE, 10, anchor_x="center", anchor_y="top").draw()

        # 2. 리더보드 (우측, 레이스 컨트롤 아래)
        rc_bottom = rc_y_center - (rc_h / 2)
        leaderboard_y_start = rc_bottom - MARGIN
        leaderboard_w = 300
        leaderboard_x = self.width - leaderboard_w - 10

        arcade.Text("Leaderboard", leaderboard_x, leaderboard_y_start, arcade.color.WHITE, 20, bold=True,
                    anchor_y="top").draw()

        driver_list = []
        for code, pos in frame["drivers"].items():
            driver_list.append((code, self.driver_colors.get(code, arcade.color.WHITE), pos))

        driver_list.sort(key=lambda x: x[2].get("dist", -1), reverse=True)

        for i, (code, color, pos) in enumerate(driver_list):
            y_pos = leaderboard_y_start - 30 - (i * 25)
            text = f"{i + 1}. {code}"
            if pos.get("rel_dist", 0) == 1: text += " OUT"

            if self.selected_driver == code:
                arcade.Text(text, leaderboard_x, y_pos, arcade.color.YELLOW, 16, anchor_y="top", bold=True).draw()
            else:
                arcade.Text(text, leaderboard_x, y_pos, color, 16, anchor_y="top").draw()

            gap_val = pos.get('gap', 0)
            if i > 0 and gap_val > 0:
                gap_text = f"+{gap_val:.1f}s"
                arcade.Text(gap_text, leaderboard_x + 160, y_pos, arcade.color.LIGHT_GRAY, 12, anchor_x="right", anchor_y="top").draw()

            tyre = str(pos.get("tyre", "")).upper()
            tyre_life = pos.get("tyre_life", 0)

            icon_x = self.width - 30
            if tyre in self._tyre_textures:
                rect = arcade.XYWH(icon_x, y_pos - 12, 16, 16)
                arcade.draw_texture_rect(self._tyre_textures[tyre], rect)

            arcade.Text(f"{tyre_life}L", icon_x - 15, y_pos - 12, arcade.color.LIGHT_GRAY, 10, anchor_x="right", anchor_y="center").draw()

        # 3. 드라이버 정보 패널 (좌측 중단)
        if self.selected_driver and self.selected_driver in frame["drivers"]:
            team_color = self.driver_colors.get(self.selected_driver, arcade.color.GRAY)

            d_data = frame["drivers"][self.selected_driver]

            panel_w = 220
            panel_h = 160
            panel_x = MARGIN + (panel_w / 2)
            panel_y = self.height / 2

            center_x = panel_x
            center_y = panel_y

            full_rect = arcade.XYWH(center_x, center_y, panel_w, panel_h)
            arcade.draw_rect_outline(full_rect, team_color, 1)

            header_h = 30
            header_rect = arcade.XYWH(center_x, center_y + (panel_h/2) - (header_h/2), panel_w, header_h)
            arcade.draw_rect_filled(header_rect, team_color)

            arcade.Text(f"Driver: {self.selected_driver}", center_x - (panel_w/2) + 10, center_y + (panel_h/2) - 22,
                        arcade.color.BLACK, 14, bold=True).draw()

            body_h = panel_h - header_h
            body_rect = arcade.XYWH(center_x, center_y - (header_h/2), panel_w, body_h)
            arcade.draw_rect_filled(body_rect, (0, 0, 0, 200))

            info_y_start = center_y + (panel_h/2) - header_h - 20
            left_align = center_x - (panel_w/2) + 10

            arcade.Text(f"Speed: {d_data.get('speed', 0):.0f} km/h", left_align, info_y_start, arcade.color.WHITE, 12).draw()
            arcade.Text(f"Gear: {d_data.get('gear', '-')}", left_align, info_y_start - 20, arcade.color.WHITE, 12).draw()

            drs_on = d_data.get('drs', 0)
            if drs_on in [10, 12, 14]:
                arcade.Text("DRS: ON", left_align, info_y_start - 40, arcade.color.GREEN, 12).draw()
            else:
                arcade.Text("DRS: OFF", left_align, info_y_start - 40, arcade.color.WHITE, 12).draw()

            throttle_val = d_data.get('throttle', 0)
            brake_val = d_data.get('brake', 0)

            bar_y = info_y_start - 70
            bar_w_max = 100
            bar_h_rect = 8

            arcade.Text("THR", left_align, bar_y, arcade.color.WHITE, 10).draw()
            arcade.draw_rect_filled(arcade.XYWH(left_align + 80, bar_y+5, bar_w_max, bar_h_rect), arcade.color.DARK_GRAY)
            th_w = (throttle_val / 100) * bar_w_max
            arcade.draw_rect_filled(arcade.XYWH(left_align + 30 + (th_w/2), bar_y+5, th_w, bar_h_rect), arcade.color.GREEN)

            arcade.Text("BRK", left_align, bar_y - 20, arcade.color.WHITE, 10).draw()
            arcade.draw_rect_filled(arcade.XYWH(left_align + 80, bar_y - 15, bar_w_max, bar_h_rect), arcade.color.DARK_GRAY)
            br_w = brake_val * bar_w_max
            if brake_val > 0:
                arcade.draw_rect_filled(arcade.XYWH(left_align + 30 + (br_w/2), bar_y - 15, br_w, bar_h_rect), arcade.color.RED)

        # 4. HUD
        hud_y_start = self.height - 80

        leader_code = max(frame["drivers"], key=lambda c: (frame["drivers"][c].get("lap", 1), frame["drivers"][c].get("dist", 0)))
        leader_lap = frame["drivers"][leader_code].get("lap", 1)

        t = frame["t"]
        time_str = f"{int(t // 3600):02}:{int((t % 3600) // 60):02}:{int(t % 60):02}"

        arcade.Text(f"Lap: {leader_lap}", 20, hud_y_start, arcade.color.WHITE, 24, anchor_y="top").draw()
        arcade.Text(f"Time: {time_str}", 20, hud_y_start - 40, arcade.color.WHITE, 20, anchor_y="top").draw()

        if self.paused:
            arcade.Text("PAUSED", self.width / 2, self.height - 100, arcade.color.YELLOW, 30, bold=True,
                        anchor_x="center").draw()

        # 5. Controls
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