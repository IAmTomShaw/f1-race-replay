import arcade
from typing import List, Literal, Tuple, Optional
from typing import Sequence, Optional, Tuple
from src.lib.time import format_time
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
    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int) -> bool: return False

class LegendComponent(BaseComponent):
    def __init__(self, x: int = 20, y: int = 220): # Increased y to 220 to fit all lines
        self.x = x
        self.y = y
        self._control_icons_textures = {}
        # Load control icons from images/icons folder (all files)
        icons_folder = os.path.join("images", "controls")
        if os.path.exists(icons_folder):
            for filename in os.listdir(icons_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(icons_folder, filename)
                    self._control_icons_textures[texture_name] = arcade.load_texture(texture_path)
        self.lines = [
            "Controls:",
            "[SPACE]  Pause/Resume",
            "[←/→]    Rewind / FastForward",
            "[↑/↓]    Speed +/- (0.5x, 1x, 2x, 4x)",
            "[R]       Restart",
            "[D]       Toggle DRS Zones",
            "[Shift + Click] Select Multiple Drivers"
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
        self._weather_icon_textures = {}
        # Load weather icons from images/weather folder (all files)
        weather_folder = os.path.join("images", "weather")
        if os.path.exists(weather_folder):
            for filename in os.listdir(weather_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(weather_folder, filename)
                    self._weather_icon_textures[texture_name] = arcade.load_texture(texture_path)

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
        # Map each weather line to its corresponding icon
        weather_lines = [
            ("Track", f"{_fmt(info.get('track_temp'), '°C')}", "thermometer"),
            ("Air", f"{_fmt(info.get('air_temp'), '°C')}", "thermometer"),
            ("Humidity", f"{_fmt(info.get('humidity'), '%', precision=0)}", "drop"),
            ("Wind", f"{_fmt(info.get('wind_speed'), ' km/h')} {_format_wind_direction(info.get('wind_direction'))}", "wind"),
            ("Rain", f"{info.get('rain_state','N/A')}", "rain"),
        ]
        
        start_y = panel_top - 36
        last_y = start_y
        for idx, (label, value, icon_key) in enumerate(weather_lines):
            line_y = start_y - idx * 22
            last_y = line_y
            # Draw weather icon
            weather_texture = self._weather_icon_textures.get(icon_key)
            if weather_texture:
                weather_icon_x = self.left + 24
                weather_icon_y = line_y - 15
                icon_size = 16
                rect = arcade.XYWH(weather_icon_x, weather_icon_y, icon_size, icon_size)
                arcade.draw_texture_rect(
                    rect=rect,
                    texture=weather_texture,
                    angle=0,
                    alpha=255
                )
            
            # Draw text
            line_text = f"{label}: {value}"
            arcade.Text(line_text, self.left + 38, line_y, arcade.color.LIGHT_GRAY, 14, anchor_y="top").draw()

        # Track the bottom of the weather panel so info boxes can stack below it
        window.weather_bottom = last_y - 20

class LeaderboardComponent(BaseComponent):
    def __init__(self, x: int, right_margin: int = 260, width: int = 240):
        self.x = x
        self.width = width
        self.entries = []  # list of tuples (code, color, pos, progress_m)
        self.rects = []    # clickable rects per entry
        self.selected = []  # Changed to list for multiple selection
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
        self.selected = getattr(window, "selected_drivers", [])
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

            if code in self.selected:
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
                arcade.draw_texture_rect(rect=rect, texture=tyre_texture, angle=0, alpha=255)

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
                # Detect multi-select modifiers
                is_multi = (modifiers & arcade.key.MOD_SHIFT)

                if is_multi:
                    if code in self.selected:
                        self.selected.remove(code)
                    else:
                        self.selected.append(code)
                else:
                    # Single click: clear others and toggle selection
                    if len(self.selected) == 1 and self.selected[0] == code:
                        self.selected = []
                    else:
                        self.selected = [code]

                # Propagate both list and single reference for compatibility
                window.selected_drivers = self.selected
                window.selected_driver = self.selected[-1] if self.selected else None
                return True
        return False


class LapTimeLeaderboardComponent(BaseComponent):
    def __init__(self, x: int, right_margin: int = 260, width: int = 240):
        self.x = x
        self.width = width
        self.entries = []  # list of dicts: {'pos', 'code', 'color', 'time'}
        self.rects = []    # clickable rects per entry
        self.selected = []  # Changed to list
        self.row_height = 25

    def set_entries(self, entries: List[dict]):
        """Accept a list of dicts with keys: pos, code, color, time"""
        self.entries = entries or []

    def draw(self, window):
        self.selected = getattr(window, "selected_drivers", [])
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
            if code in self.selected:
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
                is_multi = (modifiers & arcade.key.MOD_SHIFT)

                if is_multi:
                    if code in self.selected:
                        self.selected.remove(code)
                    else:
                        self.selected.append(code)
                else:
                    if len(self.selected) == 1 and self.selected[0] == code:
                        self.selected = []
                    else:
                        self.selected = [code]

                window.selected_drivers = self.selected
                window.selected_driver = self.selected[-1] if self.selected else None
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
            time_text = format_time(float(data.get('time', 'No Time')))
            
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
            window.selected_drivers = []
            # Also clear leaderboard selection state so UI highlight is removed
            if hasattr(window, "leaderboard"):
                window.leaderboard.selected = []
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

            segment_height, start_y = 50, top - 80
            left, right = center_x - self.width // 2, center_x + self.width // 2

            for i, data in enumerate(segments):
                s_top = start_y - (i * (segment_height + 10))
                s_bottom = s_top - segment_height
                if left + 20 <= x <= right - 20 and s_bottom <= y <= s_top:
                    try:
                        if hasattr(window, "load_driver_telemetry"):
                            window.load_driver_telemetry(code, f"Q{data['segment']}")
                        window.selected_driver = None
                        window.selected_drivers = []
                        if hasattr(window, "leaderboard"):
                            window.leaderboard.selected = []
                    except Exception as e:
                        print("Error starting telemetry load:", e)
                    return True
        return True # Consume all clicks when visible


class DriverInfoComponent(BaseComponent):
    def __init__(self, left=20, width=220, min_top=220):
        self.left = left
        self.width = width
        self.min_top = min_top

    def draw(self, window):
        # Support multiple selection via window.selected_drivers
        codes = getattr(window, "selected_drivers", [])
        if not codes:
            # Fallback to single selection compatibility
            single = getattr(window, "selected_driver", None)
            codes = [single] if single else []

        if not codes or not window.frames:
            return

        idx = min(int(window.frame_index), window.n_frames - 1)
        frame = window.frames[idx]

        box_width, box_height, gap = self.width, 210, 10
        weather_bottom = getattr(window, "weather_bottom", None)
        current_top = weather_bottom - 20 if weather_bottom else window.height - 200

        for code in codes:
            if code not in frame["drivers"]: continue
            if current_top - box_height < self.min_top: break

            driver_pos = frame["drivers"][code]
            center_y = current_top - (box_height / 2)
            self._draw_info_box(window, code, driver_pos, center_y, box_width, box_height)
            current_top -= (box_height + gap)

    def _draw_info_box(self, window, code, driver_pos, center_y, box_width, box_height):
        center_x = self.left + box_width / 2
        top, bottom = center_y + box_height / 2, center_y - box_height / 2
        left, right = center_x - box_width / 2, center_x + box_width / 2

        rect = arcade.XYWH(center_x, center_y, box_width, box_height)
        arcade.draw_rect_filled(rect, (0, 0, 0, 200))

        team_color = window.driver_colors.get(code, arcade.color.GRAY)
        arcade.draw_rect_outline(rect, team_color, 2)

        header_height = 30
        header_cy = top - (header_height / 2)
        arcade.draw_rect_filled(arcade.XYWH(center_x, header_cy, box_width, header_height), team_color)
        arcade.Text(f"Driver: {code}", left + 10, header_cy, arcade.color.BLACK, 14, anchor_y="center",
                    bold=True).draw()

        cursor_y, row_gap = top - header_height - 25, 25
        left_text_x = left + 15

        # Telemetry Text
        speed = driver_pos.get('speed', 0)
        arcade.Text(f"Speed: {speed:.0f} km/h", left + 15, cursor_y, arcade.color.WHITE, 12, anchor_y="center").draw()
        cursor_y -= row_gap
        arcade.Text(f"Gear: {driver_pos.get('gear', '-')}", left + 15, cursor_y, arcade.color.WHITE, 12,
                    anchor_y="center").draw()
        cursor_y -= row_gap

        drs_val = driver_pos.get('drs', 0)
        drs_str, drs_color = ("DRS: ON", arcade.color.GREEN) if drs_val in [10, 12, 14] else \
            ("DRS: AVAIL", arcade.color.YELLOW) if drs_val == 8 else ("DRS: OFF", arcade.color.GRAY)
        arcade.Text(drs_str, left + 15, cursor_y, drs_color, 12, anchor_y="center", bold=True).draw()
        cursor_y -= row_gap

        # Gaps (Calculated from Leaderboard)
        gap_ahead, gap_behind = "Ahead: N/A", "Behind: N/A"
        lb = getattr(window, "leaderboard", None) or \
             getattr(window, "leaderboard_ui", None) or \
             getattr(window, "leaderboard_comp", None)

        if not lb and hasattr(window, "ui_components"):
            for comp in window.ui_components:
                if isinstance(comp, LeaderboardComponent):
                    lb = comp
                    break

        # A fixed reference speed for all gap calculations (200 km/h = 55.56 m/s)
        REFERENCE_SPEED_MS = 55.56

        def calculate_gap(pos1, pos2):
            # Calculate gap between two positions consistently
            raw_dist = abs(pos1 - pos2)
            dist = raw_dist / 10.0  # Convert to meters
            time = dist / REFERENCE_SPEED_MS
            return dist, time

        if lb and hasattr(lb, "entries") and lb.entries:
            try:
                idx = next(i for i, e in enumerate(lb.entries) if e[0] == code)

                if idx > 0:  # Car Ahead
                    code_ahead = lb.entries[idx - 1][0]
                    curr_pos = lb.entries[idx][3]
                    ahead_pos = lb.entries[idx - 1][3]

                    dist, time = calculate_gap(curr_pos, ahead_pos)
                    gap_ahead = f"Ahead ({code_ahead}): +{time:.2f}s ({dist:.1f}m)"

                if idx < len(lb.entries) - 1:  # Car Behind
                    code_behind = lb.entries[idx + 1][0]
                    curr_pos = lb.entries[idx][3]
                    behind_pos = lb.entries[idx + 1][3]

                    dist, time = calculate_gap(curr_pos, behind_pos)
                    gap_behind = f"Behind ({code_behind}): -{time:.2f}s ({dist:.1f}m)"

            except (StopIteration, IndexError):
                pass

        arcade.Text(gap_ahead, left_text_x, cursor_y, arcade.color.LIGHT_GRAY, 11, anchor_y="center").draw()
        cursor_y -= 22
        arcade.Text(gap_behind, left_text_x, cursor_y, arcade.color.LIGHT_GRAY, 11, anchor_y="center").draw()

        # Graphs
        thr, brk = driver_pos.get('throttle', 0), driver_pos.get('brake', 0)
        t_r, b_r = max(0.0, min(1.0, thr / 100.0)), max(0.0, min(1.0, brk / 100.0 if brk > 1.0 else brk))
        bar_w, bar_h, b_y = 20, 80, bottom + 35
        r_center = right - 50

        # Throttle
        arcade.Text("THR", r_center - 15, b_y - 20, arcade.color.WHITE, 10, anchor_x="center").draw()
        arcade.draw_rect_filled(arcade.XYWH(r_center - 15, b_y + bar_h / 2, bar_w, bar_h), arcade.color.DARK_GRAY)
        if t_r > 0: arcade.draw_rect_filled(arcade.XYWH(r_center - 15, b_y + (bar_h * t_r) / 2, bar_w, bar_h * t_r),
                                            arcade.color.GREEN)
        # Brake
        arcade.Text("BRK", r_center + 15, b_y - 20, arcade.color.WHITE, 10, anchor_x="center").draw()
        arcade.draw_rect_filled(arcade.XYWH(r_center + 15, b_y + bar_h / 2, bar_w, bar_h), arcade.color.DARK_GRAY)
        if b_r > 0: arcade.draw_rect_filled(arcade.XYWH(r_center + 15, b_y + (bar_h * b_r) / 2, bar_w, bar_h * b_r),
                                            arcade.color.RED)

    def _get_driver_color(self, window, code):
        return window.driver_colors.get(code, arcade.color.GRAY)

# Feature: race progress bar with event markers
class RaceProgressBarComponent(BaseComponent):
    """
    A visual progress bar showing race timeline with event markers:
    - DNF markers (red X)
    - Lap transition markers (vertical lines)
    - Flag markers (red/yellow rectangles)
    
    Uses best practices:
    - Single responsibility: only handles progress bar rendering
    - Efficient rendering with cached markers
    - Clear separation of concerns for event detection
    """
    
    # Event type constants for clear identification
    EVENT_DNF = "dnf"
    EVENT_LAP = "lap"
    EVENT_YELLOW_FLAG = "yellow_flag"
    EVENT_RED_FLAG = "red_flag"
    EVENT_SAFETY_CAR = "safety_car"
    EVENT_VSC = "vsc"
    
    # Color palette following F1 conventions
    COLORS = {
        "background": (30, 30, 30, 200),
        "progress_fill": (0, 180, 0),
        "progress_border": (100, 100, 100),
        "dnf": (220, 50, 50),
        "lap_marker": (80, 80, 80),
        "yellow_flag": (255, 220, 0),
        "red_flag": (220, 30, 30),
        "safety_car": (255, 140, 0),
        "vsc": (255, 165, 0),
        "text": (220, 220, 220),
        "current_position": (255, 255, 255),
    }
    
    def __init__(self, 
                 left_margin: int = 340, 
                 right_margin: int = 260,
                 bottom: int = 30,
                 height: int = 24,
                 marker_height: int = 16):
        """
        Initialize the progress bar component.
        
        Args:
            left_margin: Left margin from window edge
            right_margin: Right margin from window edge
            bottom: Distance from bottom of window
            height: Height of the progress bar
            marker_height: Height of event markers
        """
        self.left_margin = left_margin
        self.right_margin = right_margin
        self.bottom = bottom
        self.height = height
        self.marker_height = marker_height
        
        self._visible: bool = False
        
        # Cached data
        self._events: List[dict] = []
        self._total_frames: int = 0
        self._total_laps: int = 0
        self._bar_left: float = 0
        self._bar_width: float = 0
        
        # Hover state for tooltips
        self._hover_event: Optional[dict] = None
        self._mouse_x: float = 0
        self._mouse_y: float = 0
        
    def set_race_data(self, 
                      total_frames: int, 
                      total_laps: int,
                      events: List[dict]):
        """
        set the race data for the progress bar so the calc for markers can be done once time
        
        - total_frames: Total number of frames in the race
        - total_laps: Total number of laps in the race
        - events: List of event dictionaries with keys
        """
        self._total_frames = max(1, total_frames)
        self._total_laps = total_laps or 1
        self._events = sorted(events, key=lambda e: e.get("frame", 0))
    
    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the progress bar
        """
        self._visible = not self._visible
        return self._visible
        
    def _calculate_bar_dimensions(self, window):
        self._bar_left = self.left_margin
        self._bar_width = max(100, window.width - self.left_margin - self.right_margin)
        
    def _frame_to_x(self, frame: int, clamp: bool = True) -> float:
        """
        well here convert a frame number to an X position on the bar
        this must receive clamp=True to prevent out-of-bounds rendering
        Args:
            frame: Frame number to convert
            clamp: Whether to clamp frame to valid range [0, total_frames]
        """
        if self._total_frames <= 0:
            return self._bar_left
        
        # here we use Clamp frame to valid range to prevent rendering outside bar bounds
        if clamp:
            frame = max(0, min(frame, self._total_frames))
        
        progress = frame / self._total_frames
        return self._bar_left + (progress * self._bar_width)
    
    def _x_to_frame(self, x: float) -> int:
        # reverse of _frame_to_x
        if self._bar_width <= 0:
            return 0
        progress = (x - self._bar_left) / self._bar_width
        return int(progress * self._total_frames)
        
    def on_resize(self, window):
        self._calculate_bar_dimensions(window)
        
    def draw(self, window):
        """Render the progress bar with all markers"""
        # Skip rendering entirely if hidden
        if not self._visible:
            return
            
        self._calculate_bar_dimensions(window)
        
        current_frame = int(getattr(window, 'frame_index', 0))
        
        bar_center_y = self.bottom + self.height / 2
        
        # 1. Draw background bar
        bg_rect = arcade.XYWH(
            self._bar_left + self._bar_width / 2,
            bar_center_y,
            self._bar_width,
            self.height
        )
        arcade.draw_rect_filled(bg_rect, self.COLORS["background"])
        arcade.draw_rect_outline(bg_rect, self.COLORS["progress_border"], 2)
        
        # 2. Draw progress fill
        if self._total_frames > 0:
            progress_ratio = min(1.0, current_frame / self._total_frames)
            progress_width = progress_ratio * self._bar_width
            if progress_width > 0:
                progress_rect = arcade.XYWH(
                    self._bar_left + progress_width / 2,
                    bar_center_y,
                    progress_width,
                    self.height - 4
                )
                arcade.draw_rect_filled(progress_rect, self.COLORS["progress_fill"])
        
        # 3. Draw lap markers (vertical lines)
        if self._total_laps > 1:
            for lap in range(1, self._total_laps + 1):
                # Approximate frame for lap transition
                lap_frame = int((lap / self._total_laps) * self._total_frames)
                lap_x = self._frame_to_x(lap_frame)
                
                # Draw subtle vertical line
                arcade.draw_line(
                    lap_x, self.bottom + 2,
                    lap_x, self.bottom + self.height - 2,
                    self.COLORS["lap_marker"], 1
                )
                
                # Draw lap number below for major laps (every 5 laps or first/last)
                if lap == 1 or lap == self._total_laps or lap % 10 == 0:
                    arcade.Text(
                        str(lap),
                        lap_x, self.bottom - 4,
                        self.COLORS["text"], 9,
                        anchor_x="center", anchor_y="top"
                    ).draw()
        
        # 4. Draw event markers
        for event in self._events:
            event_x = self._frame_to_x(event.get("frame", 0))
            self._draw_event_marker(event, event_x, bar_center_y)
        
        # 5. Draw current position indicator (playhead)
        current_x = self._frame_to_x(current_frame)
        arcade.draw_line(
            current_x, self.bottom - 2,
            current_x, self.bottom + self.height + 2,
            self.COLORS["current_position"], 3
        )
        
        # 6. Draw legend
        self._draw_legend(window)
    
    # 7. Draw tooltips and overlays after the main draw to prevent them being occluded
    def draw_overlays(self, window):
        """Draw tooltips and other overlays that should appear on top of all UI elements."""
        if not self._visible:
            return
        # Draw hover tooltip if applicable
        if self._hover_event:
            self._draw_tooltip(window, self._hover_event)
            
    def _draw_event_marker(self, event: dict, x: float, center_y: float):
        """Draw a single event marker based on type."""
        event_type = event.get("type", "")
        marker_top = self.bottom + self.height + self.marker_height
        marker_bottom = self.bottom + self.height
        
        if event_type == self.EVENT_DNF:
            # Draw red X marker above the bar
            size = 6
            color = self.COLORS["dnf"]
            y = marker_top - size
            arcade.draw_line(x - size, y - size, x + size, y + size, color, 2)
            arcade.draw_line(x - size, y + size, x + size, y - size, color, 2)
            
        elif event_type == self.EVENT_YELLOW_FLAG:
            # Draw yellow flag indicator on the bar
            self._draw_flag_segment(event, self.COLORS["yellow_flag"])
            
        elif event_type == self.EVENT_RED_FLAG:
            # Draw red flag indicator on the bar
            self._draw_flag_segment(event, self.COLORS["red_flag"])
            
        elif event_type == self.EVENT_SAFETY_CAR:
            # Draw orange segment for safety car
            self._draw_flag_segment(event, self.COLORS["safety_car"])
            
        elif event_type == self.EVENT_VSC:
            # Draw amber segment for VSC
            self._draw_flag_segment(event, self.COLORS["vsc"])
            
    def _draw_flag_segment(self, event: dict, color: tuple):
        start_frame = event.get("frame", 0)
        end_frame = event.get("end_frame", start_frame + 100)  # default duration
        
        clamped_start = max(0, min(start_frame, self._total_frames))
        clamped_end = max(0, min(end_frame, self._total_frames))
        
        if clamped_start >= clamped_end:
            # after clamping, if start >= end, the segment is fully outside the
            # visible race window (e.g., flag ended before frame 0)
            return
        
        # Convert clamped frames to X positions
        start_x = self._frame_to_x(clamped_start)
        end_x = self._frame_to_x(clamped_end)
        
        # Additional safety: clamp X positions to bar boundaries.
        # This provides defense-in-depth against floating-point edge cases
        # that might otherwise cause slight visual overflow on some platforms
        bar_right = self._bar_left + self._bar_width
        start_x = max(self._bar_left, min(start_x, bar_right))
        end_x = max(self._bar_left, min(end_x, bar_right))
        
        # Calculate segment width with minimum visibility threshold
        segment_width = end_x - start_x
        
        # Skip segments with zero or negative visible width after clamping
        if segment_width <= 0:
            return
        
        # Ensure minimum width for visibility (thin flags are hard to see)
        segment_width = max(4, segment_width)
        
        # Draw as a thin bar above the main progress bar
        segment_rect = arcade.XYWH(
            start_x + segment_width / 2,
            self.bottom + self.height + 4,
            segment_width,
            6
        )
        arcade.draw_rect_filled(segment_rect, color)
        
    def _draw_tooltip(self, window, event: dict):
        event_type = event.get("type", "")
        label = event.get("label", "")
        lap = event.get("lap", "")
        
        # Build tooltip text
        type_names = {
            self.EVENT_DNF: "DNF",
            self.EVENT_YELLOW_FLAG: "Yellow Flag",
            self.EVENT_RED_FLAG: "Red Flag",
            self.EVENT_SAFETY_CAR: "Safety Car",
            self.EVENT_VSC: "Virtual SC",
        }
        
        tooltip_text = type_names.get(event_type, "Event")
        if label:
            tooltip_text = f"{tooltip_text}: {label}"
        if lap:
            tooltip_text = f"{tooltip_text} (Lap {lap})"
            
        # Calculate position
        event_x = self._frame_to_x(event.get("frame", 0))
        tooltip_x = min(max(event_x, 100), window.width - 100)
        tooltip_y = self.bottom + self.height + self.marker_height + 20
        
        # Draw tooltip background
        padding = 8
        text_obj = arcade.Text(tooltip_text, 0, 0, (255, 255, 255), 12)
        text_width = text_obj.content_width
        
        bg_rect = arcade.XYWH(
            tooltip_x,
            tooltip_y,
            text_width + padding * 2,
            20
        )
        arcade.draw_rect_filled(bg_rect, (40, 40, 40, 230))
        arcade.draw_rect_outline(bg_rect, (100, 100, 100), 1)
        
        # Draw text
        arcade.Text(
            tooltip_text,
            tooltip_x, tooltip_y,
            (255, 255, 255), 12,
            anchor_x="center", anchor_y="center"
        ).draw()
        
    def _draw_legend(self, window):
        """Draw a small legend explaining the markers."""
        legend_items = [
            (self.COLORS["yellow_flag"], "■", "Yellow"),
            (self.COLORS["red_flag"], "■", "Red"),
            (self.COLORS["safety_car"], "■", "SC"),
            (self.COLORS["vsc"], "■", "VSC"),
        ]
        
        legend_x = self._bar_left + self._bar_width + 50
        legend_y = self.bottom + self.height / 2
        
        for i, (color, symbol, label) in enumerate(legend_items):
            x = legend_x + (i * 45)
            arcade.Text(
                symbol,
                x, legend_y + 2,
                color, 10, bold=True,
                anchor_x="center", anchor_y="center"
            ).draw()
            arcade.Text(
                label,
                x, legend_y - 10,
                self.COLORS["text"], 8,
                anchor_x="center", anchor_y="top"
            ).draw()
        
    def on_mouse_motion(self, window, x: float, y: float, dx: float, dy: float):
        """Handle mouse motion for hover effects."""
        if not self._visible:
            return
            
        self._mouse_x = x
        self._mouse_y = y
        
        # Check if mouse is over the progress bar area
        if (self._bar_left <= x <= self._bar_left + self._bar_width and
            self.bottom <= y <= self.bottom + self.height + self.marker_height + 10):
            
            # Find nearest event
            mouse_frame = self._x_to_frame(x)
            nearest_event = None
            min_dist = float('inf')
            
            for event in self._events:
                event_frame = event.get("frame", 0)
                dist = abs(event_frame - mouse_frame)
                if dist < min_dist and dist < self._total_frames * 0.02:  # Within 2% of timeline
                    min_dist = dist
                    nearest_event = event
                    
            self._hover_event = nearest_event
        else:
            self._hover_event = None
            
    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        """Handle mouse click to seek to position."""
        if not self._visible:
            return False
            
        if (self._bar_left <= x <= self._bar_left + self._bar_width and
            self.bottom - 5 <= y <= self.bottom + self.height + 5):
            
            # Seek to clicked position
            target_frame = self._x_to_frame(x)
            if hasattr(window, 'frame_index'):
                window.frame_index = float(max(0, min(target_frame, self._total_frames - 1)))
            return True
        return False

# Feature: control race playback (play/pause, speed control, rewind/fast-forward)
class RaceControlsComponent(BaseComponent):
    """
    A visual component with playback control buttons:
    - Rewind button (left)
    - Play/Pause button (center)
    - Forward button (right)
    """
    def __init__(self, center_x: int = 100, center_y: int = 60, button_size: int = 40):
        self.center_x = center_x
        self.center_y = center_y
        self.button_size = button_size
        self.button_spacing = 70
        self.speed_container_offset = 200
        self._hide_speed_text = False
        self._control_textures = {}
        
        # Button rectangles for hit testing
        self.rewind_rect = None
        self.play_pause_rect = None
        self.forward_rect = None
        self.speed_increase_rect = None
        self.speed_decrease_rect = None
        
        # Hover state
        self.hover_button = None  # 'rewind/forward', 'play/pause', 'speed_increase', 'speed_decrease'
        # Flash feedback state for keyboard shortcuts
        self._flash_button = None
        self._flash_timer = 0.0
        self._flash_duration = 0.3  # seconds

        _controls_folder = os.path.join("images", "controls")
        if os.path.exists(_controls_folder):
            for filename in os.listdir(_controls_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(_controls_folder, filename)
                    self._control_textures[texture_name] = arcade.load_texture(texture_path)

    def on_resize(self, window):
        """Recalculate control positions on window resize."""
        self.center_x = window.width / 2
        # Scale spacing and offset proportionally to window width (based on 1920px reference)
        self.button_spacing = window.width * (70 / 1920)
        self.speed_container_offset = window.width * (200 / 1920)
        self._hide_speed_text = window.width < 1000
    
    def on_update(self, delta_time: float):
        """Update flash timer for keyboard feedback animation."""
        if self._flash_timer > 0:
            self._flash_timer = max(0, self._flash_timer - delta_time)
            if self._flash_timer == 0:
                self._flash_button = None
    
    def flash_button(self, button_name: str):
        """Trigger a visual flash effect for a button (used for keyboard feedback)."""
        self._flash_button = button_name
        self._flash_timer = self._flash_duration

    def draw(self, window):
        """Draw the three playback control buttons."""
        is_paused = getattr(window, 'paused', False)
        
        # Button positions
        rewind_x = self.center_x - self.button_spacing
        play_x = self.center_x
        forward_x = self.center_x + self.button_spacing
    
        self._draw_rewind_icon(rewind_x, self.center_y)
        
        if is_paused:
            self._draw_play_icon(play_x, self.center_y)
        else:
            self._draw_pause_icon(play_x, self.center_y)

        self._draw_forward_icon(forward_x, self.center_y)

        self._draw_speed_comp(forward_x + self.speed_container_offset, self.center_y, getattr(window, 'playback_speed', 1.0))

    def draw_hover_effect(self, button_name: str, x: float, y: float, radius_offset: int = 2, border_width: int = 4):
        """Draw hover outline effect for a button if it's currently hovered."""
        if self.hover_button == button_name and getattr(self, f"{button_name}_rect", None):
            arcade.draw_circle_outline(x, y, self.button_size // 2 + radius_offset, arcade.color.WHITE, border_width)
        
        # Show flash effect for keyboard feedback
        if self._flash_button == button_name and self._flash_timer > 0:
            # Pulsing ring effect based on timer
            alpha = int(255 * (self._flash_timer / self._flash_duration))
            flash_color = (*arcade.color.DIM_GRAY[:3], alpha)
            arcade.draw_circle_outline(x, y, self.button_size // 2 + radius_offset + 2, flash_color, border_width + 1)

    def _draw_play_icon(self, x: float, y: float):
        self.draw_hover_effect('play_pause', x, self.center_y)
        if 'play' in self._control_textures:
            texture = self._control_textures['play']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.play_pause_rect = (x - self.button_size//2, y - self.button_size//2,
                                   x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(
                    rect=rect,
                    texture=texture,
                    angle=0,
                    alpha=255
                )
    def _draw_pause_icon(self, x: float, y: float):
        self.draw_hover_effect('play_pause', x, self.center_y)
        if 'pause' in self._control_textures:
            texture = self._control_textures['pause']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.play_pause_rect = (x - self.button_size//2, y - self.button_size//2,
                                   x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(
                    rect=rect,
                    texture=texture,
                    angle=0,
                    alpha=255
                )
    def _draw_forward_icon(self, x: float, y: float):
        self.draw_hover_effect('forward', x, self.center_y)
        if 'rewind' in self._control_textures:
            texture = self._control_textures['rewind']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.forward_rect = (x - self.button_size//2, y - self.button_size//2,
                                x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(
                    rect=rect,
                    texture=texture,
                    angle=180,
                    alpha=255
                )
    def _draw_rewind_icon(self, x: float, y: float):
        self.draw_hover_effect('rewind', x, self.center_y)
        if 'rewind' in self._control_textures:
            texture = self._control_textures['rewind']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.rewind_rect = (x - self.button_size//2, y - self.button_size//2,
                               x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(
                    rect=rect,
                    texture=texture,
                    angle=0,
                    alpha=255
                )
    def _draw_speed_comp(self, x: float, y: float, speed: float):
        """Draw speed multiplier text."""
        if 'speed+' and 'speed-' in self._control_textures:
            texture_plus = self._control_textures['speed+']
            texture_minus = self._control_textures['speed-']
            
            # Container dimensions
            if self._hide_speed_text:
                container_width = self.button_size * 2.4
            else:
                container_width = self.button_size * 3.6
            container_height = self.button_size * 1.2
            
            # Draw container background box
            rect_container = arcade.XYWH(x, y, container_width, container_height)
            arcade.draw_rect_filled(rect_container, (40, 40, 40, 200))

            # Button positions inside container
            button_offset = (container_width / 2) - (self.button_size / 2) - 5
            
            rect_minus = arcade.XYWH(x - button_offset, y, self.button_size, self.button_size)
            rect_plus = arcade.XYWH(x + button_offset, y, self.button_size, self.button_size)
            
            self.speed_decrease_rect = (x - button_offset - self.button_size//2, y - self.button_size//2,
                                       x - button_offset + self.button_size//2, y + self.button_size//2)
            self.speed_increase_rect = (x + button_offset - self.button_size//2, y - self.button_size//2,
                                       x + button_offset + self.button_size//2, y + self.button_size//2)
            
            # Draw minus button
            arcade.draw_texture_rect(
                    rect=rect_minus,
                    texture=texture_minus,
                    angle=0,
                    alpha=255
                )
            
            # Draw speed text in center
            if not self._hide_speed_text:
                arcade.Text(f"{speed:.1f}x", x, y - 5,
                            arcade.color.WHITE, 14,
                            anchor_x="center",
                            bold=True).draw()
            
            # Draw plus button
            arcade.draw_texture_rect(
                    rect=rect_plus,
                    texture=texture_plus,
                    angle=0,
                    alpha=255
                )

            # Draw hover highlights for speed buttons
            self.draw_hover_effect('speed_increase', rect_plus.center_x, rect_plus.center_y, radius_offset=1, border_width=2)
            self.draw_hover_effect('speed_decrease', rect_minus.center_x, rect_minus.center_y, radius_offset=1, border_width=2)
            

    def on_mouse_motion(self, window, x: float, y: float, dx: float, dy: float):
        """Handle mouse hover effects."""
        if self._point_in_rect(x, y, self.rewind_rect):
            self.hover_button = 'rewind'
        elif self._point_in_rect(x, y, self.play_pause_rect):
            self.hover_button = 'play_pause'
        elif self._point_in_rect(x, y, self.forward_rect):
            self.hover_button = 'forward'
        elif self._point_in_rect(x, y, self.speed_increase_rect):
            self.hover_button = 'speed_increase'
        elif self._point_in_rect(x, y, self.speed_decrease_rect):
            self.hover_button = 'speed_decrease'
        else:
            self.hover_button = None
    
    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        """Handle button clicks."""
        if self._point_in_rect(x, y, self.rewind_rect):
            # Rewind 10 frames
            if hasattr(window, 'frame_index'):
                window.frame_index = int(max(0, window.frame_index - 10))
            return True
        elif self._point_in_rect(x, y, self.play_pause_rect):
            # Toggle pause
            if hasattr(window, 'paused'):
                window.paused = not window.paused
            return True
        elif self._point_in_rect(x, y, self.forward_rect):
            # Forward 10 frames
            if hasattr(window, 'frame_index') and hasattr(window, 'n_frames'):
                window.frame_index = int(min(window.n_frames - 1, window.frame_index + 10))
            return True
        elif self._point_in_rect(x, y,self.speed_increase_rect):
            # Increase speed
            if hasattr(window, 'playback_speed'):
                window.playback_speed = window.playback_speed * 2
            return True
        elif self._point_in_rect(x, y,self.speed_decrease_rect):
            # Decrease speed
            if hasattr(window, 'playback_speed'):
                window.playback_speed = max(0.1, window.playback_speed / 2)
            return True
        return False
    
    def _point_in_rect(self, x: float, y: float, rect: tuple[float, float, float, float] | None) -> bool:
        """Check if point is inside rectangle."""
        if rect is None:
            return False
        left, bottom, right, top = rect
        return left <= x <= right and bottom <= y <= top

def extract_race_events(frames: List[dict], track_statuses: List[dict], total_laps: int) -> List[dict]:
    """
    Extract race events from frame data for the progress bar.
    
    This function analyzes the telemetry frames to identify:
    - DNF events (when a driver stops appearing)
    - Leader changes (when the P1 position changes hands)
    - Flag events (from track_statuses)
    
    Args:
        frames: List of frame dictionaries from telemetry
        track_statuses: List of track status events
        total_laps: Total number of laps in the race
        
    Returns:
        List of event dictionaries for the progress bar
    """
    events = []
    
    if not frames:
        return events
        
    n_frames = len(frames)
    
    # Track drivers present in each frame
    prev_drivers = set()
    
    # Sample frames at regular intervals for performance (every 25 frames = 1 second)
    sample_rate = 25
    
    for i in range(0, n_frames, sample_rate):
        frame = frames[i]
        drivers_data = frame.get("drivers", {})
        current_drivers = set(drivers_data.keys())
        
        # Detect DNFs (drivers who disappeared)
        if prev_drivers:
            dnf_drivers = prev_drivers - current_drivers
            for driver_code in dnf_drivers:
                # Get the lap from previous frame if available
                prev_frame = frames[max(0, i - sample_rate)]
                driver_info = prev_frame.get("drivers", {}).get(driver_code, {})
                lap = driver_info.get("lap", "?")
                
                events.append({
                    "type": RaceProgressBarComponent.EVENT_DNF,
                    "frame": i,
                    "label": driver_code,
                    "lap": lap,
                })
        
        prev_drivers = current_drivers
    
    # Add flag events from track_statuses
    for status in track_statuses:
        status_code = str(status.get("status", ""))
        start_time = status.get("start_time", 0)
        end_time = status.get("end_time")
        
        # Convert time to frame (assuming 25 FPS)
        fps = 25
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps) if end_time else start_frame + 250  # Default 10 seconds
        
        # This prevents rendering artifacts from pre-race track status events
        # that shouldn't appear on the timeline... Events that span frame 0
        # (start < 0 but end > 0) are kept; the drawing code will clamp them
        if end_frame <= 0:
            continue
        
        # Note: The drawing code also clamps, but normalizing here improves data quality
        if n_frames > 0:
            end_frame = min(end_frame, n_frames)
        
        event_type = None
        if status_code == "2":  # Yellow flag
            event_type = RaceProgressBarComponent.EVENT_YELLOW_FLAG
        elif status_code == "4":  # Safety Car
            event_type = RaceProgressBarComponent.EVENT_SAFETY_CAR
        elif status_code == "5":  # Red flag
            event_type = RaceProgressBarComponent.EVENT_RED_FLAG
        elif status_code in ("6", "7"):  # VSC
            event_type = RaceProgressBarComponent.EVENT_VSC
            
        if event_type:
            events.append({
                "type": event_type,
                "frame": start_frame,
                "end_frame": end_frame,
                "label": "",
                "lap": None,
            })
    
    return events


# Build track geometry from example lap telemetry

def build_track_from_example_lap(example_lap, track_width=200):
    drs_zones = plotDRSzones(example_lap)
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
            x_min, x_max, y_min, y_max, drs_zones)

# Plot DRS Zones along the track sides to show DRS Zones on the track
def plotDRSzones(example_lap):
   x_val = example_lap["X"]
   y_val = example_lap["Y"]
   drs_zones = []
   drs_start = None
   
   for i, val in enumerate(example_lap["DRS"]):
       if val in [10, 12, 14]:
           if drs_start is None:
               drs_start = i
       else:
           if drs_start is not None:
               drs_end = i - 1
               zone = {
                   "start": {"x": x_val.iloc[drs_start], "y": y_val.iloc[drs_start], "index": drs_start},
                   "end": {"x": x_val.iloc[drs_end], "y": y_val.iloc[drs_end], "index": drs_end}
               }
               drs_zones.append(zone)
               drs_start = None
   
   # Handle case where DRS zone extends to end of lap
   if drs_start is not None:
       drs_end = len(example_lap["DRS"]) - 1
       zone = {
           "start": {"x": x_val.iloc[drs_start], "y": y_val.iloc[drs_start], "index": drs_start},
           "end": {"x": x_val.iloc[drs_end], "y": y_val.iloc[drs_end], "index": drs_end}
       }
       drs_zones.append(zone)
   
   return drs_zones