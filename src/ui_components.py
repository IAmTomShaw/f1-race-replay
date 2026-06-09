import arcade
from typing import List, Literal, Tuple, Optional
from typing import Sequence, Optional, Tuple
from src.lib.time import format_time
import numpy as np
import os

# --- 1. CRASH-PROOF DRAWING HELPER ---
def draw_icon_safe(center_x, center_y, width, height, texture, angle=0, alpha=255):
    """
    Robustly draws a texture regardless of Arcade version (2.6 vs 3.0).
    """
    if texture is None:
        return

    # Attempt 1: Arcade 3.0+ (texture, rect)
    if hasattr(arcade, "draw_texture_rect") and hasattr(arcade, "XYWH"):
        try:
            rect = arcade.XYWH(center_x, center_y, width, height)
            arcade.draw_texture_rect(texture, rect, angle=angle, alpha=alpha)
            return
        except Exception:
            pass 

    # Attempt 2: Arcade 2.6+ (x, y, w, h, texture)
    if hasattr(arcade, "draw_texture_rectangle"):
        try:
            arcade.draw_texture_rectangle(center_x, center_y, width, height, texture, angle=angle, alpha=alpha)
            return
        except Exception:
            pass

    # Fallback: Colored Square
    arcade.draw_rectangle_filled(center_x, center_y, width, height, arcade.color.GRAY)

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
    def on_mouse_motion(self, window, x: float, y: float, dx: float, dy: float): pass
    def on_update(self, delta_time): pass

class LegendComponent(BaseComponent):
    def __init__(self, x: int = 20, y: int = 150): # FIX: Moved DOWN from 220 to 150
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
            "[↑/↓]    Speed +/-",
            "[R]       Restart"
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
                # FIX: Use safe wrapper
                draw_icon_safe(self.left + 24, line_y - 15, 16, 16, weather_texture)
            
            # Draw text
            line_text = f"{label}: {value}"
            arcade.Text(line_text, self.left + 38, line_y, arcade.color.LIGHT_GRAY, 14, anchor_y="top").draw()

        # Track the bottom of the weather panel so info boxes can stack below it
        window.weather_bottom = last_y - 20

class LeaderboardComponent(BaseComponent):
    def __init__(self, x: int, right_margin: int = 260, width: int = 240):
        self.x = x
        self.width = width
        self.entries = [] 
        self.rects = []    
        self.selected = []  
        self.row_height = 25
        self._tyre_textures = {}
        # Import the tyre textures from the images/tyres folder (all files)
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0].upper()
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

            # Strip battle icon for highlight check
            clean_code = code.split(' ')[0]
            if clean_code in self.selected:
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
                # FIX: Use safe wrapper
                tyre_icon_x = left_x + self.width - 10
                tyre_icon_y = top_y - 12
                draw_icon_safe(tyre_icon_x, tyre_icon_y, 16, 16, tyre_texture)

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        for code, left, bottom, right, top in self.rects:
            if left <= x <= right and bottom <= y <= top:
                # Detect multi-select modifiers
                is_multi = (modifiers & arcade.key.MOD_SHIFT)
                
                clean_code = code.split(' ')[0]

                if is_multi:
                    if clean_code in self.selected:
                        self.selected.remove(clean_code)
                    else:
                        self.selected.append(clean_code)
                else:
                    # Single click: clear others and toggle selection
                    if len(self.selected) == 1 and self.selected[0] == clean_code:
                        self.selected = []
                    else:
                        self.selected = [clean_code]

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
    def __init__(self, left=20, width=270, min_top=220): # Increased width to 270
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

        # ... inside draw method ...
        idx = min(int(window.frame_index), window.n_frames - 1)
        frame = window.frames[idx]

        box_width, box_height, gap = self.width, 150, 10  # Changed height to 150
        weather_bottom = getattr(window, "weather_bottom", None)
        # ...
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

        # 1. Main Background (Solid Black)
        rect = arcade.XYWH(center_x, center_y, box_width, box_height)
        arcade.draw_rect_filled(rect, (0, 0, 0, 255)) 

        # Border Matches Team Color
        team_color = window.driver_colors.get(code, arcade.color.GRAY)
        arcade.draw_rect_outline(rect, team_color, 2)

        # 2. Header Bar (Team Color)
        header_height = 24
        header_cy = top - (header_height / 2)
        arcade.draw_rect_filled(arcade.XYWH(center_x, header_cy, box_width, header_height), team_color)
        
        # Name in Black on Header
        arcade.Text(f"Driver: {code}", left + 10, header_cy, arcade.color.BLACK, 14, anchor_y="center",
                    bold=True).draw()

        # ADJUSTED: Normalized spacing for larger box
        cursor_y, row_gap = top - header_height - 30, 22 
        
        # 3. Stats (Left Side)
        speed = driver_pos.get('speed', 0)
        arcade.Text(f"Speed: {speed:.0f} km/h", left + 15, cursor_y, arcade.color.WHITE, 11, anchor_y="center").draw()
        cursor_y -= row_gap
        arcade.Text(f"Gear: {driver_pos.get('gear', '-')}", left + 15, cursor_y, arcade.color.WHITE, 11,
                    anchor_y="center").draw()
        cursor_y -= row_gap

        drs_val = driver_pos.get('drs', 0)
        drs_str, drs_color = ("DRS: ON", arcade.color.GREEN) if drs_val in [10, 12, 14] else \
            ("DRS: AVAIL", arcade.color.YELLOW) if drs_val == 8 else ("DRS: OFF", arcade.color.GRAY)
        arcade.Text(drs_str, left + 15, cursor_y, drs_color, 11, anchor_y="center", bold=True).draw()
        cursor_y -= row_gap
        
        # Gaps logic
        gap_ahead = "Ahead: N/A"
        gap_behind = "Behind: N/A"
        
        # Attempt simple gap calc
        lb = getattr(window, "leaderboard_comp", None)
        if lb and hasattr(lb, "entries"):
            try:
                # Find index of this driver
                clean_entries = [e[0].split(' ')[0] for e in lb.entries]
                if code in clean_entries:
                    idx = clean_entries.index(code)
                    if idx > 0:
                        ahead = lb.entries[idx-1]
                        # FIX: Use int() to stop meter fluctuation and :.1f for time stability
                        dist = int(abs(ahead[2].get('dist',0) - driver_pos.get('dist',0)))
                        time = dist / 60.0
                        gap_ahead = f"Ahead ({ahead[0].split(' ')[0]}): +{time:.1f}s ({dist}m)"
                    if idx < len(clean_entries) - 1:
                        behind = lb.entries[idx+1]
                        dist = int(abs(behind[2].get('dist',0) - driver_pos.get('dist',0)))
                        time = dist / 60.0
                        gap_behind = f"Behind ({behind[0].split(' ')[0]}): -{time:.1f}s ({dist}m)"
            except: pass

        # ADJUSTED: Increased font size to 10 and spacing to 18
        arcade.Text(gap_ahead, left + 15, cursor_y, arcade.color.LIGHT_GRAY, 10, anchor_y="center").draw()
        cursor_y -= 18
        arcade.Text(gap_behind, left + 15, cursor_y, arcade.color.LIGHT_GRAY, 10, anchor_y="center").draw()

        # 4. Meters (Right Side - Thick Pillars)
        thr, brk = driver_pos.get('throttle', 0), driver_pos.get('brake', 0)
        t_r, b_r = max(0.0, min(1.0, thr / 100.0)), max(0.0, min(1.0, brk / 100.0 if brk > 1.0 else brk))
        
        bar_w, bar_h_max = 20, 60
        meter_x = right - 40
        # ADJUSTED: Lifted pillar base for better layout
        meter_base = bottom + 30

        # Throttle (Green)
        arcade.draw_rect_filled(arcade.XYWH(meter_x - 15, meter_base + bar_h_max / 2, bar_w, bar_h_max), arcade.color.DARK_GRAY)
        if t_r > 0: 
            t_h = t_r * bar_h_max
            arcade.draw_rect_filled(arcade.XYWH(meter_x - 15, meter_base + t_h / 2, bar_w, t_h), arcade.color.GREEN)
        
        # Brake (Red)
        arcade.draw_rect_filled(arcade.XYWH(meter_x + 10, meter_base + bar_h_max / 2, bar_w, bar_h_max), arcade.color.DARK_GRAY)
        if b_r > 0: 
            b_h = b_r * bar_h_max
            arcade.draw_rect_filled(arcade.XYWH(meter_x + 10, meter_base + b_h / 2, bar_w, b_h), arcade.color.RED)
        
        # Labels
        arcade.Text("THR", meter_x - 15, meter_base - 15, arcade.color.WHITE, 9, anchor_x="center").draw()
        arcade.Text("BRK", meter_x + 10, meter_base - 15, arcade.color.WHITE, 9, anchor_x="center").draw()

    def _get_driver_color(self, window, code):
        return window.driver_colors.get(code, arcade.color.GRAY)

class RaceProgressBarComponent(BaseComponent):
    EVENT_DNF = "dnf"
    EVENT_LAP = "lap"
    EVENT_YELLOW_FLAG = "yellow_flag"
    EVENT_RED_FLAG = "red_flag"
    EVENT_SAFETY_CAR = "safety_car"
    EVENT_VSC = "vsc"
    
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
    
    def __init__(self, left_margin=340, right_margin=260, bottom=30, height=24, marker_height=16):
        self.left_margin = left_margin
        self.right_margin = right_margin
        self.bottom = bottom
        self.height = height
        self.marker_height = marker_height
        self._visible = True
        self._events = []
        self._total_frames = 0
        self._total_laps = 0
        self._bar_left = 0
        self._bar_width = 0
        self._hover_event = None
        
    def set_race_data(self, total_frames, total_laps, events):
        self._total_frames = max(1, total_frames)
        self._total_laps = total_laps or 1
        self._events = sorted(events, key=lambda e: e.get("frame", 0))
    
    def _calculate_bar_dimensions(self, window):
        self._bar_left = self.left_margin
        self._bar_width = max(100, window.width - self.left_margin - self.right_margin)
        
    def _frame_to_x(self, frame, clamp=True):
        if self._total_frames <= 0: return self._bar_left
        if clamp: frame = max(0, min(frame, self._total_frames))
        progress = frame / self._total_frames
        return self._bar_left + (progress * self._bar_width)
    
    def _x_to_frame(self, x):
        if self._bar_width <= 0: return 0
        progress = (x - self._bar_left) / self._bar_width
        return int(progress * self._total_frames)
        
    def on_resize(self, window):
        self._calculate_bar_dimensions(window)
        
    def draw(self, window):
        if not self._visible: return
        self._calculate_bar_dimensions(window)
        current_frame = int(getattr(window, 'frame_index', 0))
        bar_center_y = self.bottom + self.height / 2
        
        bg_rect = arcade.XYWH(self._bar_left + self._bar_width / 2, bar_center_y, self._bar_width, self.height)
        arcade.draw_rect_filled(bg_rect, self.COLORS["background"])
        arcade.draw_rect_outline(bg_rect, self.COLORS["progress_border"], 2)
        
        if self._total_frames > 0:
            progress_ratio = min(1.0, current_frame / self._total_frames)
            progress_width = progress_ratio * self._bar_width
            if progress_width > 0:
                progress_rect = arcade.XYWH(self._bar_left + progress_width / 2, bar_center_y, progress_width, self.height - 4)
                arcade.draw_rect_filled(progress_rect, self.COLORS["progress_fill"])
        
        # Events
        for event in self._events:
            event_x = self._frame_to_x(event.get("frame", 0))
            col = self.COLORS["yellow_flag"] if event.get('type') == 'yellow_flag' else self.COLORS["red_flag"]
            arcade.draw_line(event_x, self.bottom, event_x, self.bottom+self.height, col, 2)

    def draw_overlays(self, window):
        if not self._visible or not self._hover_event: return
        event = self._hover_event
        tooltip_text = f"{event.get('type')} (Lap {event.get('lap', '?')})"
        event_x = self._frame_to_x(event.get("frame", 0))
        tooltip_x = min(max(event_x, 100), window.width - 100)
        tooltip_y = self.bottom + self.height + 30
        
        text_obj = arcade.Text(tooltip_text, 0, 0, (255, 255, 255), 12)
        bg_rect = arcade.XYWH(tooltip_x, tooltip_y, text_obj.content_width + 16, 20)
        arcade.draw_rect_filled(bg_rect, (40, 40, 40, 230))
        arcade.draw_rect_outline(bg_rect, (100, 100, 100), 1)
        arcade.Text(tooltip_text, tooltip_x, tooltip_y, (255,255,255), 12, anchor_x="center", anchor_y="center").draw()

    def on_mouse_motion(self, window, x, y, dx, dy):
        if not self._visible: return
        if (self._bar_left <= x <= self._bar_left + self._bar_width and 
            self.bottom <= y <= self.bottom + self.height + 20):
            mouse_frame = self._x_to_frame(x)
            best = None
            dist = float('inf')
            for e in self._events:
                d = abs(e.get('frame',0) - mouse_frame)
                if d < dist and d < self._total_frames * 0.02:
                    dist = d
                    best = e
            self._hover_event = best
        else:
            self._hover_event = None

    def on_mouse_press(self, window, x, y, button, modifiers):
        if not self._visible: return False
        if (self._bar_left <= x <= self._bar_left + self._bar_width and 
            self.bottom - 5 <= y <= self.bottom + self.height + 5):
            target_frame = self._x_to_frame(x)
            window.frame_index = float(max(0, min(target_frame, self._total_frames - 1)))
            return True
        return False

class RaceControlsComponent(BaseComponent):
    def __init__(self, center_x, center_y):
        self.center_x = center_x
        self.center_y = center_y
        self.icons = {}
        # ADJUSTED LAYOUT: De-clustered
        self.btn_spacing = 80
        self.speed_offset = 300
        
        base = "images/controls"
        if os.path.exists(base):
            # FIX: Check for both jpg and png for all buttons
            file_map = {
                "play": ["play.png"], 
                "pause": ["pause.png"], 
                "rewind": ["rewind.png", "arrow-left.jpg"], 
                "forward": ["forward.png", "arrow-right.jpg"], 
                "speed+": ["speed+.png", "arrow-up.jpg"], 
                "speed-": ["speed-.png", "arrow-down.jpg"]
            }
            for k, files in file_map.items():
                for f in files:
                    try: 
                        path = os.path.join(base, f)
                        if os.path.exists(path):
                            self.icons[k] = arcade.load_texture(path)
                            break
                    except: pass

    def on_update(self, dt): pass

    def draw(self, window):
        rw_x = self.center_x - self.btn_spacing
        pp_x = self.center_x
        fw_x = self.center_x + self.btn_spacing
        
        self._btn(rw_x, "rewind")
        self._btn(pp_x, "pause" if not window.paused else "play")
        self._btn(fw_x, "forward")
        
        sp_center_x = self.center_x + self.speed_offset
        arcade.Text(f"{window.playback_speed:.1f}x", sp_center_x, self.center_y - 5, arcade.color.WHITE, 12, anchor_x="center").draw()
        
        self._btn(sp_center_x + 30, "speed+")
        self._btn(sp_center_x - 30, "speed-")

    def _btn(self, x, key):
        tex = self.icons.get(key)
        if tex: draw_icon_safe(x, self.center_y, 32, 32, tex)
        else: arcade.draw_circle_filled(x, self.center_y, 16, arcade.color.GRAY)

    def on_mouse_press(self, window, x, y, button, modifiers):
        cy = self.center_y
        if abs(y - cy) < 20:
            if abs(x - self.center_x) < 20: window.paused = not window.paused; return True
            if abs(x - (self.center_x - self.btn_spacing)) < 20: window.frame_index = max(0, window.frame_index - 200); return True
            if abs(x - (self.center_x + self.btn_spacing)) < 20: window.frame_index = min(window.n_frames, window.frame_index + 200); return True
            
            sp_center = self.center_x + self.speed_offset
            if abs(x - (sp_center + 30)) < 20: window.playback_speed *= 2; return True
            if abs(x - (sp_center - 30)) < 20: window.playback_speed /= 2; return True
        return False
    def on_resize(self, window): self.center_x = window.width // 2

def extract_race_events(frames, statuses, laps):
    events = []
    for s in statuses:
        events.append({'frame': int(s['start_time'] * 25), 'type': 'yellow_flag' if str(s['status']) == '2' else 'red_flag'})
    return events

# --- FUNCTIONS RESTORED ---
def plotDRSzones(example_lap):
    def get_vec(d, key):
        val = d.get(key)
        if hasattr(val, 'to_numpy'): return val.to_numpy()
        return np.array(val)
    
    x_val = get_vec(example_lap, "X")
    y_val = get_vec(example_lap, "Y")
    drs_data = get_vec(example_lap, "DRS")
    
    drs_zones = []
    drs_start = None
    
    for i, val in enumerate(drs_data):
        if val in [10, 12, 14]:
            if drs_start is None: drs_start = i
        else:
            if drs_start is not None:
                drs_end = i - 1
                drs_zones.append({
                    "start": {"x": x_val[drs_start], "y": y_val[drs_start], "index": drs_start},
                    "end": {"x": x_val[drs_end], "y": y_val[drs_end], "index": drs_end}
                })
                drs_start = None
    return drs_zones

def build_track_from_example_lap(example_lap, track_width=200):
    drs_zones = plotDRSzones(example_lap)
    
    def get_vec(d, key):
        val = d.get(key)
        if hasattr(val, 'to_numpy'): return val.to_numpy()
        return np.array(val)

    plot_x = get_vec(example_lap, "X")
    plot_y = get_vec(example_lap, "Y")

    dx = np.gradient(plot_x)
    dy = np.gradient(plot_y)
    norm = np.sqrt(dx**2 + dy**2)
    norm[norm == 0] = 1.0
    dx /= norm
    dy /= norm
    nx, ny = -dy, dx

    x_outer = plot_x + nx * (track_width / 2)
    y_outer = plot_y + ny * (track_width / 2)
    x_inner = plot_x - nx * (track_width / 2)
    y_inner = plot_y - ny * (track_width / 2)

    return (plot_x, plot_y, x_inner, y_inner, x_outer, y_outer,
            min(plot_x), max(plot_x), min(plot_y), max(plot_y), drs_zones)