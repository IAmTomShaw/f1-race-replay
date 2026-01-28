import arcade
from typing import List, Literal, Tuple, Optional
from typing import Sequence, Optional, Tuple
from src.lib.time import format_time
import numpy as np
import pandas as pd
import os
from src.tyre_degradation_integration import (
    format_tyre_health_bar, 
    format_degradation_text
)

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
    def __init__(self, x: int = 20, y: int = 220, visible=True): # Increased y to 220 to fit all lines
        self.x = x
        self.y = y
        self._control_icons_textures = {}
        self._visible = visible
        # Load control icons from images/icons folder (all files)
        icons_folder = os.path.join("images", "controls")
        if os.path.exists(icons_folder):
            for filename in os.listdir(icons_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(icons_folder, filename)
                    self._control_icons_textures[texture_name] = arcade.load_texture(texture_path)
        self.lines = ["Help (Click or 'H')"]
        
        self.controls_text_offset = 180
        self._text = arcade.Text("", 0, 0, arcade.color.CYAN, 14)
    
    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the legend
        """
        self._visible = not self._visible
        return self._visible
    
    def set_visible(self):
        """
        Set visibility of legend to True
        """
        self._visible = True


    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):

        line_x = self.x
        line_y = self.y - getattr(self, "controls_text_offset", 0)
        left = line_x
        text_width = self._text.content_width or 120
        right = line_x + text_width + 8
        top = line_y + 8
        bottom = line_y - 18

        if left <= x <= right and bottom <= y <= top:
            popup = getattr(window, "controls_popup_comp", None)
            if popup:
                # popup anchored to bottom left, small margin (20px)
                margin_x = 20
                margin_y = 20
                left_pos = float(margin_x)
                top_pos = float(margin_y + popup.height)
                desired_cx = left_pos + popup.width / 2
                desired_cy = top_pos - popup.height / 2
                if popup.visible and popup.cx == desired_cx and popup.cy == desired_cy:
                    popup.hide()
                else:
                    popup.show_over(left_pos, top_pos)
            return True
        return False
    
    def draw(self, window):
        # Skip rendering entirely if hidden
        
        if not self._visible:
            return
        for i, lines in enumerate(self.lines):
            line = lines[0] if isinstance(lines, tuple) else lines # main text
            brackets = lines[1] if isinstance(lines, tuple) and len(lines) > 2 else None # brackets only if icons exist
            icon_keys = lines[2] if isinstance(lines, tuple) and len(lines) > 2 else None # icon keys
        
            icon_size = 14
            # Draw icons if any
            
            if icon_keys:
                control_icon_x = self.x + 12
                for key in icon_keys:
                    icon_texture = self._control_icons_textures.get(key)
                    if icon_texture:
                        control_icon_y = self.y - (i * 25) + 5 # slight vertical offset
                        rect = arcade.XYWH(control_icon_x, control_icon_y, icon_size, icon_size)
                        arcade.draw_texture_rect(
                            rect = rect,
                            texture = icon_texture,
                            angle = 0,
                            alpha = 255
                        )
                        control_icon_x += icon_size + 6 # spacing between icons
                        
            if brackets:
                for j in range(len(brackets)):
                    self._text.font_size = 14
                    self._text.bold = (i == 0)
                    self._text.color = arcade.color.LIGHT_GRAY
                    self._text.text = brackets[j]
                    self._text.x = self.x + (j * (icon_size + 5))
                    self._text.y = self.y - (i * 25)
                    self._text.draw()
            
            # Draw the text line
            self._text.text = line
            self._text.x = self.x + (60 if icon_keys else 0)
            base_y = self.y - (i * 25)
            
            if i == 0:
                base_y -= getattr(self, "controls_text_offset", 0)
            self._text.y = base_y
            self._text.draw()

class WeatherComponent(BaseComponent):
    def __init__(self, left=20, width=280, height=130, top_offset=170, visible=True):
        self.left = left
        self.width = width
        self.height = height
        self.top_offset = top_offset
        self.info = None
        self._weather_icon_textures = {}
        self._visible: bool = visible
        # Load weather icons from images/weather folder (all files)
        weather_folder = os.path.join("images", "weather")
        if os.path.exists(weather_folder):
            for filename in os.listdir(weather_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(weather_folder, filename)
                    self._weather_icon_textures[texture_name] = arcade.load_texture(texture_path)

        self._text = arcade.Text("", self.left + 12, 0, arcade.color.LIGHT_GRAY, 14, anchor_y="top")

    def set_info(self, info: Optional[dict]):
        self.info = info
    
    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the weather
        """
        self._visible = not self._visible
        return self._visible
    
    def set_visible(self):
        """
        Set visibility of weather to True
        """
        self._visible = True

    def draw(self, window):
        # Skip rendering entirely if hidden
        if not self._visible:
            return
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

        self._text.font_size = 18; self._text.bold = True; self._text.color = arcade.color.WHITE
        self._text.text = "Weather"
        self._text.x = self.left + 12; self._text.y = panel_top - 10
        self._text.draw()

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
            
            self._text.font_size = 14; self._text.bold = False; self._text.color = arcade.color.LIGHT_GRAY
            self._text.text = line_text
            self._text.x = self.left + 38; self._text.y = line_y
            self._text.draw()

        # Track the bottom of the weather panel so info boxes can stack below it
        window.weather_bottom = last_y - 20

class LeaderboardComponent(BaseComponent):
    def __init__(self, x: int, right_margin: int = 260, width: int = 240, visible=True):
        self.x = x
        self.width = width
        self.entries = []  # list of tuples (code, color, pos, progress_m)
        self.rects = []    # clickable rects per entry
        self.selected = []  # Changed to list for multiple selection
        self.row_height = 25
        self.show_gaps = False
        self.show_neighbor_gaps = False
        self.gap_toggle_rect = None
        self.neighbor_toggle_rect = None
        # Reuse a single Text object for gap rendering to avoid reallocating each frame
        self._gap_text = arcade.Text("", 0, 0, arcade.color.LIGHT_GRAY, 12, anchor_x="right", anchor_y="top")
        self._tyre_textures = {}
        self._visible: bool = visible
        # Import the tyre textures from the images/tyres folder (all files)
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(tyres_folder, filename)
                    self._tyre_textures[texture_name] = arcade.load_texture(texture_path)

    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the leaderboard
        """
        self._visible = not self._visible
        return self._visible
    
    def set_visible(self):
        """
        Set visibility of leaderboard to True
        """
        self._visible = True

    def set_entries(self, entries: List[Tuple[str, Tuple[int,int,int], dict, float]]):
        # entries sorted as expected
        self.entries = entries
    def draw(self, window):
        # Skip rendering entirely if hidden
        if not self._visible:
            return
        self.selected = getattr(window, "selected_drivers", [])
        leaderboard_y = window.height - 40
        arcade.Text("Leaderboard", self.x, leaderboard_y, arcade.color.WHITE, 20, bold=True, anchor_x="left", anchor_y="top").draw()
        # sync with window state if present
        self.show_gaps = getattr(window, "leaderboard_show_gaps", self.show_gaps)
        self.show_neighbor_gaps = getattr(window, "leaderboard_show_neighbor_gaps", self.show_neighbor_gaps)

        # If both were set externally, prefer neighbor (interval) gaps and clear leader gaps.
        if self.show_gaps and self.show_neighbor_gaps:
            self.show_gaps = False

        # small radio btns to the right of the title: interval gaps and leader gaps
        toggle_radius = 10
        toggle_y = leaderboard_y - 15
        gap_between_toggles = 30
        
        # interval radio-btn (I)
        neighbor_x = self.x + self.width - gap_between_toggles - toggle_radius
        self.neighbor_toggle_rect = (neighbor_x - toggle_radius, toggle_y - toggle_radius, neighbor_x + toggle_radius, toggle_y + toggle_radius)
        nb_bg = (100, 100, 100) if not self.show_neighbor_gaps else (50, 150, 50)
        arcade.draw_circle_filled(neighbor_x, toggle_y, toggle_radius, nb_bg)
        nb_border = (150, 150, 150) if not self.show_neighbor_gaps else (80, 200, 80)
        arcade.draw_circle_outline(neighbor_x, toggle_y, toggle_radius, nb_border, 2)
        arcade.Text("I", neighbor_x, toggle_y, arcade.color.WHITE, 12, anchor_x="center", anchor_y="center", bold=True).draw()

        # leader radio-btn (L)
        toggle_x = self.x + self.width - toggle_radius
        self.gap_toggle_rect = (toggle_x - toggle_radius, toggle_y - toggle_radius, toggle_x + toggle_radius, toggle_y + toggle_radius)
        lg_bg = (100, 100, 100) if not self.show_gaps else (50, 150, 50)
        arcade.draw_circle_filled(toggle_x, toggle_y, toggle_radius, lg_bg)
        lg_border = (150, 150, 150) if not self.show_gaps else (80, 200, 80)
        arcade.draw_circle_outline(toggle_x, toggle_y, toggle_radius, lg_border, 2)
        arcade.Text("L", toggle_x, toggle_y, arcade.color.WHITE, 12, anchor_x="center", anchor_y="center", bold=True).draw()

        self.rects = []

        # Sort entries by lap number an distance progressed
        # If any of the entries have lap > 1, then sort

        if any(e[2].get("lap", 0) > 1 for e in self.entries):
            new_entries = sorted(
                self.entries,
                key=lambda e: (
                    -e[2].get("lap", 0),  # Descending lap number
                    -e[2].get("dist")                 # Descending distance progressed
                )
            )
        else:
            new_entries = self.entries

        for i, (code, color, pos, progress_m) in enumerate(new_entries):
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

            # Gap display (if enabled)
            if getattr(self, "show_neighbor_gaps", False):
                neighbor_info = None
                if hasattr(window, "leaderboard_neighbor_gaps"):
                    neighbor_info = window.leaderboard_neighbor_gaps.get(code)

                if i == 0:
                    gap_text = "-"
                else:
                    if neighbor_info:
                        if neighbor_info.get("ahead"):
                            _, dist_m, time_s = neighbor_info.get("ahead")
                            gap_text = f"+{time_s:.1f}s"
                        else:
                            gap_text = ""
                    else:
                        gap_text = ""

            elif getattr(self, "show_gaps", False):
                gap_text = ""
                gap_val = None
                # prefer window-provided precomputed gaps
                if hasattr(window, "leaderboard_gaps"):
                    gap_val = window.leaderboard_gaps.get(code)
                if gap_val is None:
                    gap_val = pos.get("gap") or pos.get("gap_to_leader")
                if gap_val is None:
                    gap_text = ""
                else:
                    try:
                        # expect seconds (float)
                        s = float(gap_val)
                        # leader (zero) gets dash
                        if abs(s) < 1e-6:
                            gap_text = "-"
                        else:
                            sign = "+" if s > 0 else "-"
                            gap_text = f"{sign}{abs(s):.1f}s"
                    except Exception:
                        gap_text = str(gap_val)

                pass

            # if either leader or neighbor gaps are enabled, draw the gap text
            if getattr(self, "show_neighbor_gaps", False) or getattr(self, "show_gaps", False):
                gap_x = right_x - 36
                if 'gap_text' in locals() and gap_text:
                    gap_color = arcade.color.BLACK if code in self.selected else arcade.color.LIGHT_GRAY
                    # Update and draw the reusable gap Text object
                    self._gap_text.text = gap_text
                    self._gap_text.x = gap_x
                    self._gap_text.y = top_y
                    self._gap_text.color = gap_color
                    self._gap_text.draw()

            # Tyre Icons
            tyre_val = pos.get("tyre", "?")
            tyre_texture = self._tyre_textures.get(str(tyre_val).upper())
            if tyre_texture:
                # position tyre icon inside the leaderboard area so it doesn't collide with track
                tyre_icon_x = left_x + self.width - 10
                tyre_icon_y = top_y - 12
                icon_size = 16
                rect = arcade.XYWH(tyre_icon_x, tyre_icon_y, icon_size, icon_size)

                current_life = pos.get("tyre_life", 0)
                tyre_health_ratio = 1.0
                if window.degradation_integrator:
                    idx = min(int(window.frame_index), len(window.frames) - 1)
                    health_data = window.degradation_integrator.get_health_for_frame(code, window.frames[idx])
                    if health_data:
                        tyre_health_ratio = health_data['health'] / 100.0
                else:
                    max_tyre_life = getattr(window, "max_tyre_life", {})
                    try:
                        tyre_key = int(tyre_val)
                    except (TypeError, ValueError):
                        max_life = 30
                    else:
                        max_life = max_tyre_life.get(tyre_key, 30)
                    if max_life > 0:
                        tyre_health_ratio = max(0.0, min(1.0, 1.0 - (current_life / max_life)))
                    else:
                        tyre_health_ratio = 1.0

                arcade.draw_texture_rect(rect=rect, texture=tyre_texture, alpha=80)
                bright_height = icon_size * tyre_health_ratio
                if bright_height > 0:
                    window.ctx.scissor = (int(tyre_icon_x - 8), int(tyre_icon_y - 8), int(icon_size), int(bright_height))
                    arcade.draw_texture_rect(rect=rect, texture=tyre_texture, alpha=255)
                    window.ctx.scissor = None
                    
                try:
                    life_display = str(int(current_life)) if pd.notna(current_life) else "0"
                except (ValueError, TypeError):
                    life_display = "0"
                arcade.Text(
                    life_display,
                    tyre_icon_x + 8,
                    tyre_icon_y - 8,
                    arcade.color.WHITE,
                    8,
                    bold=True,
                    anchor_x="center",
                    anchor_y="center"
                ).draw()

                # DRS Indicator
                drs_val = pos.get("drs", 0)
                # DRS is active if value >= 10
                is_drs_on = drs_val and int(drs_val) >= 10
                drs_color = arcade.color.GREEN if is_drs_on else arcade.color.GRAY
                
                # Position dot to the left of the tyre icon
                # tyre_icon_x is the center of the tyre icon
                drs_dot_x = tyre_icon_x - icon_size - 4 
                drs_dot_y = tyre_icon_y

                arcade.draw_circle_filled(drs_dot_x, drs_dot_y, 4, drs_color)

        # Add text at the bottom of the leaderboard during lap 1 to alert the user to potential mis-ordering
        if new_entries[0][2].get("lap", 0) == 1:
            arcade.Text("May be inaccurate during Lap 1",
                        self.x, leaderboard_y - 30 - (len(new_entries) * self.row_height) - 20,
                        arcade.color.YELLOW, 12, anchor_x="left", anchor_y="top").draw()

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        # interval toggle (radio type)
        if self.neighbor_toggle_rect:
            n_left, n_bottom, n_right, n_top = self.neighbor_toggle_rect
            if n_left <= x <= n_right and n_bottom <= y <= n_top:
                if self.show_neighbor_gaps:
                    # currently selected -> deselect
                    self.show_neighbor_gaps = False
                    setattr(window, "leaderboard_show_neighbor_gaps", False)
                else:
                    # select interval gaps and deselect leader gaps
                    self.show_neighbor_gaps = True
                    self.show_gaps = False
                    setattr(window, "leaderboard_show_neighbor_gaps", True)
                    setattr(window, "leaderboard_show_gaps", False)
                return True
        # leader toggle (radio type)
        if self.gap_toggle_rect:
            g_left, g_bottom, g_right, g_top = self.gap_toggle_rect
            if g_left <= x <= g_right and g_bottom <= y <= g_top:
                if self.show_gaps:
                    self.show_gaps = False
                    setattr(window, "leaderboard_show_gaps", False)
                else:
                    self.show_gaps = True
                    self.show_neighbor_gaps = False
                    setattr(window, "leaderboard_show_gaps", True)
                    setattr(window, "leaderboard_show_neighbor_gaps", False)
                return True

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
        self._visible = True

    def set_entries(self, entries: List[dict]):
        """Accept a list of dicts with keys: pos, code, color, time"""
        self.entries = entries or []
    
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

    def draw(self, window):
        # Skip rendering entirely if hidden
        if not self._visible:
            return
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
        self.degradation_integrator = None

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
        
        if self.degradation_integrator and hasattr(window, 'frames'):
            try:
                idx = min(int(window.frame_index), window.n_frames - 1)
                frame = window.frames[idx]
                health_data = self.degradation_integrator.get_health_for_frame(code, frame)
                
                if health_data:
                    cursor_y -= 28  # Space before health bar
                    
                    # Draw tyre health bar
                    bar_params = format_tyre_health_bar(health_data['health'], width=180, height=14)
                    bar_x = left + 15
                    bar_y = cursor_y
                    
                    # Background bar (dark gray)
                    arcade.draw_rect_filled(
                        arcade.XYWH(bar_x + bar_params['width']/2, bar_y, 
                                   bar_params['width'], bar_params['height']),
                        (50, 50, 50)
                    )
                    
                    # Health fill bar (colored)
                    if bar_params['fill_width'] > 0:
                        arcade.draw_rect_filled(
                            arcade.XYWH(bar_x + bar_params['fill_width']/2, bar_y, 
                                       bar_params['fill_width'], bar_params['height']),
                            bar_params['color']
                        )
                    
                    # Border
                    arcade.draw_rect_outline(
                        arcade.XYWH(bar_x + bar_params['width']/2, bar_y, 
                                   bar_params['width'], bar_params['height']),
                        arcade.color.WHITE, 1
                    )
                    
                    cursor_y -= 18
                    
                    # Tyre info text
                    tyre_text = format_degradation_text(health_data)
                    arcade.Text(tyre_text, left_text_x, cursor_y, 
                               arcade.color.LIGHT_GRAY, 10, anchor_y="center").draw()
                    
            except (KeyError, AttributeError, TypeError) as e:
                print(f"Error displaying driver info: {e}")

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



class ControlsPopupComponent(BaseComponent):
    def __init__(self, width: int = 420, height: int = 260, header_font_size: int = 18, body_font_size: int = 16):
        
        self.width = width
        self.height = height
        self.visible = False
        
        self.cx: Optional[float] = None
        self.cy: Optional[float] = None
        
        self.header_font_size = header_font_size
        self.body_font_size = body_font_size
        
        self._header_text = arcade.Text("", 0, 0, arcade.color.BLACK, self.header_font_size, anchor_x="left", anchor_y="center")
        self._body_text = arcade.Text("", 0, 0, arcade.color.LIGHT_GRAY, self.body_font_size, anchor_x="left", anchor_y="center")

    def set_size(self, width: int, height: int):
        
        self.width = width
        self.height = height

    def set_font_sizes(self, header_font_size: int = None, body_font_size: int = None):
        
        if header_font_size is not None:
            self.header_font_size = header_font_size
            self._header_text.font_size = header_font_size
        if body_font_size is not None:
            self.body_font_size = body_font_size
            self._body_text.font_size = body_font_size

    def show_center(self):
        """Show popup centered in the window."""
        self.cx = None
        self.cy = None
        self.visible = True

    def show_over(self, left: float, top: float):
        
        self.cx = float(left + self.width / 2)
        self.cy = float(top - self.height / 2)
        self.visible = True

    def hide(self):
        self.visible = False
        self.cx = None
        self.cy = None

    def draw(self, window):
        if not self.visible:
            return
        cx = self.cx if self.cx is not None else window.width / 2
        cy = self.cy if self.cy is not None else window.height / 2
        rect = arcade.XYWH(cx, cy, self.width, self.height)
        arcade.draw_rect_filled(rect, (0, 0, 0, 255))
        arcade.draw_rect_outline(rect, arcade.color.GRAY, 2)

        
        header_height = max(28, int(self.header_font_size * 2))
        header_cy = cy + self.height / 2 - header_height / 2
        arcade.draw_rect_filled(arcade.XYWH(cx, header_cy, self.width, header_height), arcade.color.GRAY)
        
        self._header_text.font_size = self.header_font_size
        self._header_text.bold = True
        self._header_text.color = arcade.color.BLACK
        self._header_text.text = "Controls"
        self._header_text.x = cx - self.width / 2 + 12
        self._header_text.y = header_cy
        self._header_text.draw()


        lines = [
            " ",
            "[SPACE] Pause/Resume",
            "← / →  Jump back/forward",
            "↑ / ↓  Speed +/-",
            "[1-4]  Set speed: 0.5x / 1x / 2x / 4x",
            "[R]    Restart",
            "[D]    Toggle DRS Zones",
            "[B]    Toggle Progress Bar",
            "[L]    Toggle Driver Labels",
            "[H]    Toggle Help Popup",
        ]
        
        line_spacing = max(18, int(self.body_font_size + 8))
        y = header_cy - 20
        for l in lines:
            self._body_text.font_size = self.body_font_size
            self._body_text.bold = False
            self._body_text.color = arcade.color.LIGHT_GRAY
            self._body_text.text = l
            self._body_text.x = cx - self.width / 2 + 16
            self._body_text.y = y
            self._body_text.draw()
            y -= line_spacing

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        
        if not self.visible:
            return False
        cx = self.cx if self.cx is not None else window.width / 2
        cy = self.cy if self.cy is not None else window.height / 2
        left = cx - self.width / 2
        right = cx + self.width / 2
        bottom = cy - self.height / 2
        top = cy + self.height / 2

        # If click inside the box, do nothing
        if left <= x <= right and bottom <= y <= top:
            return True

        # Click outside closes popup
        self.hide()
        return True


class SessionInfoComponent(BaseComponent):
    """
    Displays session information banner at the top-center of the screen.
    Shows: Circuit name, Country, Event name, Year, Round, Date, Total laps
    """
    def __init__(self, visible=True):
        self.visible = visible
        self.session_info = {}
        self._text = arcade.Text("", 0, 0, arcade.color.WHITE, 14)
        
    def set_info(self, event_name: str = "", circuit_name: str = "", country: str = "",
                 year: int = None, round_num: int = None, date: str = "", total_laps: int = None):
        """Set session information to display"""
        self.session_info = {
            'event_name': event_name,
            'circuit_name': circuit_name,
            'country': country,
            'year': year,
            'round': round_num,
            'date': date,
            'total_laps': total_laps
        }
    
    def toggle_visibility(self) -> bool:
        """Toggle visibility of session info banner"""
        self.visible = not self.visible
        return self.visible
    
    def draw(self, window):
        if not self.visible or not self.session_info:
            return
        
        # Banner dimensions
        banner_height = 60
        banner_width = min(900, window.width - 40)
        center_x = window.width / 2
        top_y = window.height - 10
        bottom_y = top_y - banner_height
        
        # Draw semi-transparent background
        rect = arcade.XYWH(center_x, top_y - banner_height/2, banner_width, banner_height)
        arcade.draw_rect_filled(rect, (20, 20, 20, 220))
        arcade.draw_rect_outline(rect, arcade.color.GRAY, 2)
        
        # Get info
        event = self.session_info.get('event_name', '')
        circuit = self.session_info.get('circuit_name', '')
        country = self.session_info.get('country', '')
        year = self.session_info.get('year', '')
        round_num = self.session_info.get('round', '')
        date = self.session_info.get('date', '')
        total_laps = self.session_info.get('total_laps', '')
        
        # Line 1: Event Name | Circuit | Country
        line1_parts = []
        if event:
            line1_parts.append(f"🏁 {event}")
        if circuit:
            line1_parts.append(circuit)
        if country:
            line1_parts.append(f"🌍 {country}")
        
        line1 = " | ".join(line1_parts)
        
        # Line 2: Year Round X | Date | X Laps
        line2_parts = []
        if year and round_num:
            line2_parts.append(f"📅 {year} Round {round_num}")
        elif year:
            line2_parts.append(f"📅 {year}")
        if date:
            line2_parts.append(date)
        if total_laps:
            line2_parts.append(f"{total_laps} Laps")
        
        line2 = " | ".join(line2_parts)
        
        # Draw text lines
        self._text.font_size = 16
        self._text.bold = True
        self._text.color = arcade.color.WHITE
        self._text.text = line1
        self._text.x = center_x
        self._text.y = top_y - 18
        self._text.anchor_x = "center"
        self._text.anchor_y = "center"
        self._text.draw()
        
        self._text.font_size = 13
        self._text.bold = False
        self._text.color = arcade.color.LIGHT_GRAY
        self._text.text = line2
        self._text.y = top_y - 40
        self._text.draw()


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
        
        # Also hide/show related components
        for comp in getattr(self, "_related_components", []):
            if isinstance(comp, BaseComponent):
                comp.visible = self._visible
                
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
    
    PLAYBACK_SPEEDS = [0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]

    def __init__(self, center_x: int = 100, center_y: int = 60, button_size: int = 40, visible=True):
        self.center_x = center_x
        self.center_y = center_y
        self.button_size = button_size
        self.button_spacing = 70
        self.speed_container_offset = 200
        self._hide_speed_text = False
        self._control_textures = {}
        self._visible = visible
        
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

    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the controls
        """
        self._visible = not self._visible

    def set_visible(self):
        """
        Set visibility of controls to True
        """
        self._visible = True

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
        # Skip rendering entirely if hidden
        if not self._visible:
            return
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
                    alpha = 255
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
                    alpha = 255
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
                    alpha = 255
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
                    alpha = 255
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
                arcade.Text(f"{speed}x", x, y - 5,
                            arcade.color.WHITE, 11,
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
        return False
    
    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        """Handle button clicks."""
        if self._point_in_rect(x, y, self.rewind_rect):
            # Update: Support hold-to-rewind
            if hasattr(window, 'is_rewinding'):
                window.was_paused_before_hold = window.paused
                window.is_rewinding = True
                window.paused = True
            elif hasattr(window, 'frame_index'):
                window.frame_index = int(max(0, window.frame_index - 10))
            return True
        elif self._point_in_rect(x, y, self.play_pause_rect):
            if hasattr(window, 'paused'):
                window.paused = not window.paused
            return True
        elif self._point_in_rect(x, y, self.forward_rect):
            # Update: Support hold-to-forward
            if hasattr(window, 'is_forwarding'):
                window.was_paused_before_hold = window.paused
                window.is_forwarding = True
                window.paused = True
            elif hasattr(window, 'frame_index') and hasattr(window, 'n_frames'):
                window.frame_index = int(min(window.n_frames - 1, window.frame_index + 10))
            return True
        elif self._point_in_rect(x, y, self.speed_increase_rect):
            if hasattr(window, 'playback_speed'):
                # FIX: Use index lookup to increment speed.
                if window.playback_speed < max(self.PLAYBACK_SPEEDS):
                    current_index = self.PLAYBACK_SPEEDS.index(window.playback_speed)
                    window.playback_speed = self.PLAYBACK_SPEEDS[min(current_index + 1, len(self.PLAYBACK_SPEEDS) - 1)]
                    self.flash_button('speed_increase')
            return True
        elif self._point_in_rect(x, y, self.speed_decrease_rect):
            if hasattr(window, 'playback_speed'):
                # FIX: Use index lookup to decrement speed safely within defined PLAYBACK_SPEEDS.
                if window.playback_speed > min(self.PLAYBACK_SPEEDS):
                    current_index = self.PLAYBACK_SPEEDS.index(window.playback_speed)
                    window.playback_speed = self.PLAYBACK_SPEEDS[max(0, current_index - 1)]
                    self.flash_button('speed_decrease')
            return True
        return False
    
    def _point_in_rect(self, x: float, y: float, rect: tuple[float, float, float, float] | None) -> bool:
        """Check if point is inside rectangle."""
        if rect is None:
            return False
        left, bottom, right, top = rect
        return left <= x <= right and bottom <= y <= top

class QualifyingLapTimeComponent(BaseComponent):
    """
    A component to display the qualifying lap time with sector times and current tyre info.
    """
    def __init__(self, x: int = 150, y: int = 60):
        self.x = x
        self.y = y
        self.fastest_driver = None
        self.fastest_driver_sector_times = None
        self._tyre_textures = {}
        self._time_elapsed = 0.0
        self._delta_sector = None
        self._last_completed_sector = -1
        # Import the tyre textures from the images/tyres folder (all files)
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(tyres_folder, filename)
                    self._tyre_textures[texture_name] = arcade.load_texture(texture_path)

    def on_update(self, delta_time: float):
        """
        Update logic for time difference in fastest driver and current driver (Delta sector time)
        """
        if self._delta_sector is not None:
            self._time_elapsed += delta_time
            if self._time_elapsed >= 1.0:
                # Reset delta display after 1 second (but keep sector completion tracking)
                self._delta_sector = None
                self._time_elapsed = 0.0

    def reset(self):
        self._delta_sector = None
        self._time_elapsed = 0.0
        self._last_completed_sector = -1

    def draw(self, window):
        if not hasattr(window, 'loaded_telemetry') or not window.loaded_telemetry:
            return
        sector_times = window.loaded_telemetry.get("sector_times") if isinstance(window.loaded_telemetry, dict) else {}
        if not sector_times:
            sector_times = {}
        compound = window.loaded_telemetry.get("compound", "?")
        
        # Get driver info
        driver_full_name = None
        fastest_driver_full_name = None
        driver_color = arcade.color.ANTI_FLASH_WHITE
        driver_code = getattr(window, 'loaded_driver_code', None)
        if driver_code:
            telemetry = window.data.get("telemetry")
            if telemetry:
                driver_full_name = telemetry.get(driver_code, {}).get("full_name")
                if self.fastest_driver:
                    fastest_driver_full_name = telemetry.get(self.fastest_driver.get("code"), {}).get("full_name")
                # Get color from results
                for result in window.data.get("results", []):
                    if result.get("code") == driver_code:
                        driver_color = tuple(result.get("color", arcade.color.ANTI_FLASH_WHITE))
                        break

        # Get current time from window
        frames = window.loaded_telemetry.get("frames") if isinstance(window.loaded_telemetry, dict) else None
        if not frames:
            return
        current_frame = frames[window.frame_index]
        current_t = current_frame.get("t", 0.0)
        formatted_time = format_time(current_t)
        
        rect = arcade.XYWH(self.x + 125, self.y - 65, 250, 120)
        
        arcade.draw_rect_filled(rect, (20, 20, 20, 255))

        arcade.Text(f"{driver_full_name}", self.x + 10, self.y - 30, driver_color, 16, bold=True).draw()
        
        #Display tyre compound texture
        rect = arcade.XYWH(self.x + 220, self.y - 22, 24, 24)
        texture_key = f"{compound}.0" if isinstance(compound, (int, float)) else None
        tyre_texture = self._tyre_textures.get(texture_key) if texture_key else None
        
        if tyre_texture:
            arcade.draw_texture_rect(
                rect=rect,
                texture=tyre_texture,
                angle=0,
                alpha=255
            )

        arcade.draw_line(self.x, self.y - 40, self.x + 250, self.y - 40, arcade.color.ANTI_FLASH_WHITE, 3)

        arcade.Text(f"{formatted_time}", self.x + 10, self.y - 70, arcade.color.ANTI_FLASH_WHITE, 18, anchor_x="left", bold=True).draw()

        if self.fastest_driver_sector_times and fastest_driver_full_name and fastest_driver_full_name != driver_full_name:
            fastest_last_name = fastest_driver_full_name.split(" ")[-1]
            arcade.Text(f"{fastest_last_name}", self.x + 150, self.y - 85, arcade.color.LIGHT_GRAY, 13, anchor_x="left").draw()

        #show sector times over the labels
        sector_configs = [
            ("sector1", self.x + 45, 0),
            ("sector2", self.x + 125, 1),
            ("sector3", self.x + 205, 2)
        ]
        
        cumulative_time = 0
        cumulative_fastest_time = 0
        epsilon = 0.01  # Small tolerance for floating-point comparison
        
        for sector_key, x_pos, sector_idx in sector_configs:
            sector_time = sector_times.get(sector_key)
            fastest_sector_time = None
            delta_sector_time = None
            if self.fastest_driver_sector_times:
                fastest_sector_time = self.fastest_driver_sector_times.get(sector_key)
                cumulative_fastest_time += fastest_sector_time if fastest_sector_time is not None else 0
                delta_sector_time = sector_time - fastest_sector_time if sector_time is not None and fastest_sector_time is not None else None
            
            formatted_fastest_sector_time = format_time(cumulative_fastest_time)
            text_color = arcade.color.ANTI_FLASH_WHITE
            
            # Calculate elapsed time in current sector
            # Sector 1 uses absolute time, others use time relative to cumulative
            elapsed_in_sector = current_t if sector_idx == 0 else current_t - cumulative_time

            # Check if sector has started (only applicable for sectors 2 and 3)
            if sector_idx > 0 and current_t < cumulative_time - epsilon:
                text = "-"

            # Check if sector is completed
            elif sector_time and sector_time <= elapsed_in_sector + epsilon:
                text, text_color = self.show_delta_sector_times(sector_idx, sector_time, delta_sector_time, text_color)
                # Draw green bar below completed sector
                bar_width = 40 if sector_idx == 0 else 45
                arcade.draw_line(x_pos - 45, self.y - 125, x_pos + bar_width, self.y - 125, arcade.color.GREEN, 3)
                if sector_idx == 2 and fastest_sector_time is not None:
                    arcade.Text(f"{formatted_fastest_sector_time}s", self.x + 150, self.y - 65, arcade.color.LIGHT_GRAY, 13, anchor_x="left").draw()

            # Sector in progress - show current elapsed time
            else:
                text = f"{elapsed_in_sector:.1f}s"
                if fastest_sector_time is not None:
                    arcade.Text(f"{formatted_fastest_sector_time}s", self.x + 150, self.y - 65, arcade.color.LIGHT_GRAY, 13, anchor_x="left").draw()
            
            # Always draw the sector time text
            arcade.Text(text, x_pos, self.y - 105, text_color, 12, anchor_x="center", bold=True).draw()
            
            # Always update cumulative time for next sector
            if sector_time is not None:
                cumulative_time += sector_time
        
        # Draw sector labels once after processing all sectors
        self.draw_sector_labels(sector_times, current_t)

    def draw_sector_labels(self, sector_times, current_t):
        s1_time = sector_times.get("sector1") or 0
        s1_color = arcade.color.GREEN if s1_time > 0 and current_t >= s1_time else arcade.color.LIGHT_GRAY
        arcade.Text("S1", self.x + 35, self.y - 120, s1_color, 9, bold=True).draw()

        s2_val = sector_times.get("sector2") or 0
        s2_time = s1_time + s2_val
        s2_color = arcade.color.GREEN if s2_time > 0 and current_t >= s2_time else arcade.color.LIGHT_GRAY
        arcade.Text("S2", self.x + 115, self.y - 120, s2_color, 9, bold=True).draw()
        
        s3_val = sector_times.get("sector3") or 0
        s3_time = s2_time + s3_val
        s3_color = arcade.color.GREEN if s3_time > 0 and current_t >= s3_time else arcade.color.LIGHT_GRAY
        arcade.Text("S3", self.x + 200, self.y - 120, s3_color, 9, bold=True).draw()      
    
    def show_delta_sector_times(self, sector_idx: int, sector_time: float, delta_sector_time: float | None, text_color: tuple):
        if self._delta_sector == sector_idx and self._time_elapsed < 1.0 and delta_sector_time is not None:
            # Show delta for 1 second
            if delta_sector_time < 0:
                text = f"-{abs(delta_sector_time):.3f}s"
                text_color = arcade.color.GREEN
            else:
                text = f"+{delta_sector_time:.3f}s"
                text_color = arcade.color.YELLOW
        else:
            text = f"{sector_time:.1f}s"
            # Detect if sector just completed to trigger delta display (only once)
            if self._last_completed_sector < sector_idx and delta_sector_time is not None:
                self._delta_sector = sector_idx
                self._time_elapsed = 0.0
                self._last_completed_sector = sector_idx
        return text, text_color

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

def draw_finish_line(self, session_type = 'R'):
    if(session_type not in ['R', 'Q']):
        print("Invalid session type for finish line drawing...")
        return

    start_inner = None
    start_outer = None

    if(session_type == 'Q' and len(self.inner_pts) > 0 and len(self.outer_pts) > 0):
        start_inner = self.inner_pts[0]
        start_outer = self.outer_pts[0]
    elif(session_type == 'R' and len(self.screen_inner_points) > 0 and len(self.screen_outer_points) > 0):
        start_inner = self.screen_inner_points[0]
        start_outer = self.screen_outer_points[0]
    else:
        return
    
    # Draw checkered finish line
    if start_inner and start_outer:
        num_squares = 20
        extension = 20
            
        # Calculate direction vector and normalize
        dx = start_outer[0] - start_inner[0]
        dy = start_outer[1] - start_inner[1]
        length = np.sqrt(dx**2 + dy**2)
            
        if length > 0:
            # Normalize direction (unit vector)
            dx_norm = dx / length
            dy_norm = dy / length
                
            # Extend line beyond track limits
            extended_inner = (start_inner[0] - extension * dx_norm, 
                             start_inner[1] - extension * dy_norm)
            extended_outer = (start_outer[0] + extension * dx_norm, 
                             start_outer[1] + extension * dy_norm)
            
            # Draw checkered pattern across extended line
            for i in range(num_squares):
                t1 = i / num_squares # start of segment
                t2 = (i + 1) / num_squares # end of segment
                
                x1 = extended_inner[0] + t1 * (extended_outer[0] - extended_inner[0])
                y1 = extended_inner[1] + t1 * (extended_outer[1] - extended_inner[1])
                x2 = extended_inner[0] + t2 * (extended_outer[0] - extended_inner[0])
                y2 = extended_inner[1] + t2 * (extended_outer[1] - extended_inner[1])
                
                color = arcade.color.WHITE if i % 2 == 0 else arcade.color.BLACK
                arcade.draw_line(x1, y1, x2, y2, color, 6)