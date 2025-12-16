import arcade
from typing import List, Tuple, Optional
from typing import Sequence, Optional, Tuple
import numpy as np
import os

def _format_wind_direction(degrees: Optional[float]) -> str:
  if degrees is None:
      return "N/A"
  deg_norm = degrees % 360
  dirs = [
      "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
      "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
  ]
  idx = int((deg_norm / 22.5) + 0.5) % len(dirs)
  return dirs[idx]

class BaseComponent:
    def on_resize(self, window): pass
    def draw(self, window): pass
    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int): return False

class LegendComponent(BaseComponent):
    def __init__(self, x: int = 20, y: int = 150):
        self.x = x
        self.y = y
        self.lines = [
            "Controls:",
            "[SPACE]  Pause/Resume",
            "[←/→]    Rewind / FastForward",
            "[↑/↓]    Speed +/- (0.5x, 1x, 2x, 4x)",
            "[R]       Restart",
        ]
    def draw(self, window):
        for i, line in enumerate(self.lines):
            arcade.Text(
                line,
                self.x,
                self.y - (i * 25),
                arcade.color.LIGHT_GRAY if i > 0 else arcade.color.WHITE,
                14,
                bold=(i == 0)
            ).draw()

class WeatherComponent(BaseComponent):
    def __init__(self, left=20, width=280, height=130, top_offset=170):
        self.left = left
        self.width = width
        self.height = height
        self.top_offset = top_offset
        self.info = None
    def set_info(self, info: Optional[dict]):
        self.info = info
    def draw(self, window):
        panel_top = window.height - self.top_offset
        if not self.info and not getattr(window, "has_weather", False):
            return
        arcade.Text("Weather", self.left + 12, panel_top - 10, arcade.color.WHITE, 18, bold=True, anchor_y="top").draw()
        def _fmt(val, suffix="", precision=1):
            return f"{val:.{precision}f}{suffix}" if val is not None else "N/A"
        info = self.info or {}
        weather_lines = [
            f"🌡️ Track: {_fmt(info.get('track_temp'), '°C')}",
            f"🌡️ Air: {_fmt(info.get('air_temp'), '°C')}",
            f"💧 Humidity: {_fmt(info.get('humidity'), '%', precision=0)}",
            f" 🌬️ Wind: {_fmt(info.get('wind_speed'), ' km/h')} {_format_wind_direction(info.get('wind_direction'))}",
            f"🌧️ Rain: {info.get('rain_state','N/A')}",
        ]
        start_y = panel_top - 36
        for idx, line in enumerate(weather_lines):
            arcade.Text(line, self.left + 12, start_y - idx * 22, arcade.color.LIGHT_GRAY, 14, anchor_y="top").draw()

class LeaderboardComponent(BaseComponent):
    def __init__(self, x: int, right_margin: int = 260, width: int = 240):
        self.x = x
        self.width = width
        self.entries = []  # list of tuples (code, color, pos, progress_m)
        self.rects = []    # clickable rects per entry
        self.selected = None
        self.row_height = 25
        self._tyre_textures = {}
        # Import the tyre textures from the images/tyres folder (all files)
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(tyres_folder, filename)
                    self._tyre_textures[texture_name] = arcade.load_texture(texture_path)

    def set_entries(self, entries: List[Tuple[str, Tuple[int,int,int], dict, float]]):
        # entries sorted as expected
        self.entries = entries
    def draw(self, window):
        leaderboard_y = window.height - 40
        arcade.Text("Leaderboard", self.x, leaderboard_y, arcade.color.WHITE, 20, bold=True, anchor_x="left", anchor_y="top").draw()
        self.rects = []
        for i, (code, color, pos, progress_m) in enumerate(self.entries):
            current_pos = i + 1
            top_y = leaderboard_y - 30 - ((current_pos - 1) * self.row_height)
            bottom_y = top_y - self.row_height
            left_x = self.x
            right_x = self.x + self.width
            self.rects.append((code, left_x, bottom_y, right_x, top_y))
            if code == self.selected:
                rect = arcade.XYWH((left_x + right_x)/2, (top_y + bottom_y)/2, right_x - left_x, top_y - bottom_y)
                arcade.draw_rect_filled(rect, arcade.color.LIGHT_GRAY)
                text_color = arcade.color.BLACK
            else:
                text_color = color
            text = f"{current_pos}. {code}" if pos.get("rel_dist",0) != 1 else f"{current_pos}. {code}   OUT"
            arcade.Text(text, left_x, top_y, text_color, 16, anchor_x="left", anchor_y="top").draw()

             # Tyre Icons
            tyre_texture = self._tyre_textures.get(str(pos.get("tyre", "?")).upper())
            if tyre_texture:
                # position tyre icon inside the leaderboard area so it doesn't collide with track
                tyre_icon_x = left_x + self.width - 10
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


    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        for code, left, bottom, right, top in self.rects:
            if left <= x <= right and bottom <= y <= top:
                if self.selected == code:
                    self.selected = None
                else:
                    self.selected = code
                # propagate selection to window for compatibility
                window.selected_driver = self.selected
                return True
        return False

class LapTimeLeaderboardComponent(BaseComponent):
    def __init__(self, x: int, right_margin: int = 260, width: int = 240):
        self.x = x
        self.width = width
        self.entries = []  # list of dicts: {'pos', 'code', 'color', 'time'}
        self.rects = []    # clickable rects per entry
        self.selected = None
        self.row_height = 25

    def set_entries(self, entries: List[dict]):
        """Accept a list of dicts with keys: pos, code, color, time"""
        self.entries = entries or []

    def draw(self, window):
        leaderboard_y = window.height - 40
        arcade.Text("Lap Times", self.x, leaderboard_y, arcade.color.WHITE, 20, bold=True, anchor_x="left", anchor_y="top").draw()
        self.rects = []
        for i, entry in enumerate(self.entries):
            pos = entry.get('pos', i + 1)
            code = entry.get('code', '')
            color = entry.get('color', arcade.color.WHITE)
            time_str = entry.get('time', '')
            current_pos = i + 1
            top_y = leaderboard_y - 30 - ((current_pos - 1) * self.row_height)
            bottom_y = top_y - self.row_height
            left_x = self.x
            right_x = self.x + self.width
            # store clickable rect (code, left, bottom, right, top)
            self.rects.append((code, left_x, bottom_y, right_x, top_y))

            # selection highlight
            if code == self.selected:
                rect = arcade.XYWH((left_x + right_x) / 2, (top_y + bottom_y) / 2, right_x - left_x, top_y - bottom_y)
                arcade.draw_rect_filled(rect, arcade.color.LIGHT_GRAY)
                text_color = arcade.color.BLACK
            else:
                # accept tuple rgb or fallback to white
                text_color = tuple(color) if isinstance(color, (list, tuple)) else arcade.color.WHITE

            # Draw code on left, time right-aligned
            arcade.Text(f"{pos}. {code}", left_x + 8, top_y, text_color, 16, anchor_x="left", anchor_y="top").draw()
            arcade.Text(time_str, right_x - 8, top_y, text_color, 14, anchor_x="right", anchor_y="top").draw()

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        for code, left, bottom, right, top in self.rects:
            if left <= x <= right and bottom <= y <= top:
                if self.selected == code:
                    self.selected = None
                else:
                    self.selected = code
                # propagate selection to window
                window.selected_driver = self.selected
                return True
        return False

class QualifyingSegmentSelectorComponent(BaseComponent):
    def __init__(self, width=400, height=300):
        self.width = width
        self.height = height
        self.driver_result = None
        self.selected_segment = None
        
    def draw(self, window):
        if not getattr(window, "selected_driver", None):
            return
        
        code = window.selected_driver
        results = window.data['results']
        driver_result = next((res for res in results if res['code'] == code), None)
        # Calculate modal position (centered)
        center_x = window.width // 2
        center_y = window.height // 2
        left = center_x - self.width // 2
        right = center_x + self.width // 2
        top = center_y + self.height // 2
        bottom = center_y - self.height // 2
        
        # Draw modal background
        modal_rect = arcade.XYWH(center_x, center_y, self.width, self.height)
        arcade.draw_rect_filled(modal_rect, (40, 40, 40, 230))
        arcade.draw_rect_outline(modal_rect, arcade.color.WHITE, 2)
        
        # Draw title
        title = f"Qualifying Sessions - {driver_result.get('code','')}"
        arcade.Text(title, left + 20, top - 30, arcade.color.WHITE, 18, 
               bold=True, anchor_x="left", anchor_y="center").draw()
        
        # Draw segments
        segment_height = 50
        start_y = top - 80

        segments = []

        if driver_result.get('Q1') is not None:
            segments.append({
                'time': driver_result['Q1'],
                'segment': 1
            })
        if driver_result.get('Q2') is not None:
            segments.append({
                'time': driver_result['Q2'],
                'segment': 2
            })
        if driver_result.get('Q3') is not None:
            segments.append({
                'time': driver_result['Q3'],
                'segment': 3
            })
        
        for i, data in enumerate(segments):
            segment = f"Q{data['segment']}"
            segment_top = start_y - (i * (segment_height + 10))
            segment_bottom = segment_top - segment_height
            
            # Highlight if selected
            segment_rect = arcade.XYWH(center_x, segment_top - segment_height//2, 
                                     self.width - 40, segment_height)
            
            if segment == self.selected_segment:
                arcade.draw_rect_filled(segment_rect, arcade.color.LIGHT_GRAY)
                text_color = arcade.color.BLACK
            else:
                arcade.draw_rect_filled(segment_rect, (60, 60, 60))
                text_color = arcade.color.WHITE
                
            arcade.draw_rect_outline(segment_rect, arcade.color.WHITE, 1)
            
            # Draw segment info
            segment_text = f"{segment.upper()}"
            time_text = data.get('time', 'No Time')
            
            arcade.Text(segment_text, left + 30, segment_top - 20, 
                       text_color, 16, bold=True, anchor_x="left", anchor_y="center").draw()
            arcade.Text(time_text, right - 30, segment_top - 20, 
                       text_color, 14, anchor_x="right", anchor_y="center").draw()
        
        # Draw close button
        close_btn_rect = arcade.XYWH(right - 30, top - 30, 20, 20)
        arcade.draw_rect_filled(close_btn_rect, arcade.color.RED)
        arcade.Text("×", right - 30, top - 30, arcade.color.WHITE, 16, 
               bold=True, anchor_x="center", anchor_y="center").draw()

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):        
        if not getattr(window, "selected_driver", None):
            return False
        
        # Calculate modal position (same as in draw)
        center_x = window.width // 2
        center_y = window.height // 2
        left = center_x - self.width // 2
        right = center_x + self.width // 2
        top = center_y + self.height // 2
        bottom = center_y - self.height // 2
        
        # Check close button (match the rect from draw method)
        close_btn_left = right - 30 - 10  # center - half width
        close_btn_right = right - 30 + 10  # center + half width
        close_btn_bottom = top - 30 - 10  # center - half height
        close_btn_top = top - 30 + 10     # center + half height
        
        if close_btn_left <= x <= close_btn_right and close_btn_bottom <= y <= close_btn_top:
            window.selected_driver = None
            # Also clear leaderboard selection state so UI highlight is removed
            if hasattr(window, "leaderboard") and getattr(window.leaderboard, "selected", None):
                window.leaderboard.selected = None
            self.selected_segment = None
            return True
        
        # Check segment clicks
        code = window.selected_driver
        results = window.data['results']
        driver_result = next((res for res in results if res['code'] == code), None)
        
        if driver_result:
            segments = []
            if driver_result.get('Q1') is not None:
                segments.append({'time': driver_result['Q1'], 'segment': 1})
            if driver_result.get('Q2') is not None:
                segments.append({'time': driver_result['Q2'], 'segment': 2})
            if driver_result.get('Q3') is not None:
                segments.append({'time': driver_result['Q3'], 'segment': 3})
            
            segment_height = 50
            start_y = top - 80
            
            for i, data in enumerate(segments):
                segment_top = start_y - (i * (segment_height + 10))
                segment_bottom = segment_top - segment_height
                segment_left = left + 20
                segment_right = right - 20
            
                # If click falls inside this segment rect, toggle selection and start telemetry load
                if segment_left <= x <= segment_right and segment_bottom <= y <= segment_top:
                    segment = f"Q{data['segment']}"
                    # call window API to load telemetry and hide modal/selection
                    try:
                        # start loading telemetry on the main window
                        if hasattr(window, "load_driver_telemetry"):
                            window.load_driver_telemetry(code, segment)
                        # hide selector/modal and clear leaderboard highlight
                        window.selected_driver = None
                        if hasattr(window, "leaderboard"):
                            window.leaderboard.selected = None
                    except Exception as e:
                        print("Error starting telemetry load:", e)

                    return True
        
        return True  # Consume all clicks when visible


class DriverInfoComponent(BaseComponent):
    def __init__(self, left=20, width=220, min_top=220):
        self.left = left
        self.width = width
        self.min_top = min_top

    def draw(self, window):
        if not getattr(window, "selected_driver", None):
            return

        code = window.selected_driver
        if not window.frames: return

        idx = min(int(window.frame_index), window.n_frames - 1)
        frame = window.frames[idx]

        if code not in frame["drivers"]: return
        driver_pos = frame["drivers"][code]

        box_width = self.width
        box_height = 160

        center_x = self.left + box_width / 2

        default_y = window.height / 2
        weather_bottom = getattr(window, "weather_bottom", None)

        if weather_bottom:
            top_limit = weather_bottom - 20
            center_y = top_limit - (box_height / 2)
        else:
            center_y = default_y

        center_y -= 30

        # driver box height limit
        center_y = max(center_y, self.min_top + box_height / 2)

        # actual drawing area  (Top / Bottom / Left / Right)
        top = center_y + box_height / 2
        bottom = center_y - box_height / 2
        left = center_x - box_width / 2
        right = center_x + box_width / 2

        rect = arcade.XYWH(center_x, center_y, box_width, box_height)
        arcade.draw_rect_filled(rect, (0, 0, 0, 200))

        team_color = window.driver_colors.get(code, arcade.color.GRAY)
        arcade.draw_rect_outline(rect, team_color, 2)

        header_height = 30
        header_cy = top - (header_height / 2)
        header_rect = arcade.XYWH(center_x, header_cy, box_width, header_height)
        arcade.draw_rect_filled(header_rect, team_color)

        arcade.Text(f"Driver: {code}", left + 10, header_cy,
                    arcade.color.BLACK, 14, anchor_y="center", bold=True).draw()

        header_bottom = top - header_height
        cursor_y = header_bottom - 25
        left_text_x = left + 15
        row_gap = 25

        # (A) Speed
        speed = driver_pos.get('speed', 0)
        arcade.Text(f"Speed: {speed:.0f} km/h", left_text_x, cursor_y, arcade.color.WHITE, 12, anchor_y="center").draw()
        cursor_y -= row_gap

        # (B) Gear
        gear = driver_pos.get('gear', '-')
        arcade.Text(f"Gear: {gear}", left_text_x, cursor_y, arcade.color.WHITE, 12, anchor_y="center").draw()
        cursor_y -= row_gap

        # (C) DRS
        drs_val = driver_pos.get('drs', 0)
        drs_str = "DRS: OFF"
        drs_color = arcade.color.GRAY

        if drs_val in [10, 12, 14]:
            drs_str = "DRS: ON"
            drs_color = arcade.color.GREEN
        elif drs_val == 8:
            drs_str = "DRS: AVAIL"
            drs_color = arcade.color.YELLOW

        arcade.Text(drs_str, left_text_x, cursor_y, drs_color, 12, anchor_y="center", bold=True).draw()
        cursor_y -= (row_gap + 5)

        # ---------------------------------------------------
        # [4] vertical stick graph (right side)
        # ---------------------------------------------------
        # get data
        throttle = driver_pos.get('throttle', 0)
        brake = driver_pos.get('brake', 0)

        # 0~100 range normalization (preparing if the data has 0~1 range)
        t_ratio = max(0.0, min(1.0, throttle / 100.0))
        if brake > 1.0:
            b_ratio = max(0.0, min(1.0, brake / 100.0))
        else:
            b_ratio = max(0.0, min(1.0, brake))

        # set graph location
        bar_width = 20
        bar_max_height = 80
        bar_bottom_y = bottom + 35  # 바닥에서 약간 위

        # center value of right section
        right_section_center = right - 50

        # (D) Throttle Bar
        th_x = right_section_center - 15

        # throttle label
        arcade.Text("THR", th_x, bar_bottom_y - 20, arcade.color.WHITE, 10, anchor_x="center").draw()

        # throttle bg_color (grey) - XYWH는 중심점 기준이므로 계산 주의
        # center Y = bottom Y + (height / 2)
        bg_cy = bar_bottom_y + (bar_max_height / 2)
        arcade.draw_rect_filled(arcade.XYWH(th_x, bg_cy, bar_width, bar_max_height), arcade.color.DARK_GRAY)

        # throttle value (green) - filled from bottom to top
        if t_ratio > 0:
            val_height = bar_max_height * t_ratio
            val_cy = bar_bottom_y + (val_height / 2)
            arcade.draw_rect_filled(arcade.XYWH(th_x, val_cy, bar_width, val_height), arcade.color.GREEN)

        # (E) Brake Bar
        br_x = right_section_center + 15

        # brake label
        arcade.Text("BRK", br_x, bar_bottom_y - 20, arcade.color.WHITE, 10, anchor_x="center").draw()

        # brake bg_color (grey)
        arcade.draw_rect_filled(arcade.XYWH(br_x, bg_cy, bar_width, bar_max_height), arcade.color.DARK_GRAY)

        # brake value (red)
        if b_ratio > 0:
            val_height = bar_max_height * b_ratio
            val_cy = bar_bottom_y + (val_height / 2)
            arcade.draw_rect_filled(arcade.XYWH(br_x, val_cy, bar_width, val_height), arcade.color.RED)

    def _get_driver_color(self, window, code):
        return window.driver_colors.get(code, arcade.color.GRAY)

# Build track geometry from example lap telemetry

def build_track_from_example_lap(example_lap, track_width=200):

    plot_x_ref = example_lap["X"]
    plot_y_ref = example_lap["Y"]

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


class RaceControlComponent(BaseComponent):
    def __init__(self, width=400, height=130, margin=20):
        self.width = width
        self.height = height
        self.margin = margin

    def draw(self, window):
        # didn't draw without data
        if not hasattr(window, 'race_control_messages') or not window.race_control_messages:
            return

        idx = min(int(window.frame_index), window.n_frames - 1)
        current_time = window.frames[idx]["t"]

        # [coordinate] Bottom Right
        rc_x_center = window.width - self.margin - (self.width / 2)
        rc_y_center = self.margin + (self.height / 2)

        # background
        rc_rect = arcade.XYWH(rc_x_center, rc_y_center, self.width, self.height)
        arcade.draw_rect_filled(rc_rect, (0, 0, 0, 180))
        arcade.draw_rect_outline(rc_rect, arcade.color.WHITE, 1)

        # header
        arcade.Text("Race Control",
                    rc_x_center, rc_y_center + self.height / 2 - 10,
                    arcade.color.ORANGE, 12, bold=True,
                    anchor_x="center", anchor_y="top").draw()

        # filtering messages & aligning
        valid_msgs = [m for m in window.race_control_messages if m['time'] <= current_time]
        valid_msgs.sort(key=lambda x: x['time'], reverse=True)
        display_msgs = valid_msgs[:5]

        start_y = rc_y_center + (self.height / 2) - 35
        line_height = 18

        if not display_msgs:
            arcade.Text("No messages yet", rc_x_center, rc_y_center,
                        arcade.color.GRAY, 10, anchor_x="center").draw()

        for i, msg in enumerate(display_msgs):
            m_time = msg['time']
            time_str = f"{int(m_time // 60):02}:{int(m_time % 60):02}" if m_time >= 0 else "PRE"
            full_text = f"[{time_str}] {msg['message']}"

            if len(full_text) > 55: full_text = full_text[:52] + "..."

            text_color = arcade.color.WHITE
            upper_text = full_text.upper()
            if 'YELLOW' in upper_text:
                text_color = arcade.color.YELLOW
            elif 'RED' in upper_text:
                text_color = arcade.color.RED
            elif 'SAFETY' in upper_text or 'VSC' in upper_text:
                text_color = arcade.color.ORANGE
            elif 'BLACK' in upper_text or 'PENALTY' in upper_text:
                text_color = (255, 100, 100)
            elif 'GREEN' in upper_text:
                text_color = arcade.color.GREEN
            elif 'CLEAR' in upper_text:
                text_color = arcade.color.LIGHT_BLUE

            draw_y = start_y - (i * line_height)
            arcade.Text(full_text, rc_x_center - (self.width / 2) + 10, draw_y,
                        text_color, 11, anchor_x="left", anchor_y="top").draw()