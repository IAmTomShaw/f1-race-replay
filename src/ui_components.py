import arcade
from typing import List, Literal, Tuple, Optional
from typing import Sequence, Optional, Tuple
from src.lib.time import format_time
import numpy as np
import pandas as pd
import fastf1.plotting
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
        self._text = arcade.Text("", self.x, self.y, arcade.color.CYAN, 14)
    
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
        self.show_neighbor_gaps = True
        self.gap_toggle_rect = None
        self.neighbor_toggle_rect = None
        # Reuse text objects for gap rendering to avoid reallocating each frame
        self._gap_text = arcade.Text("", 0, 0, arcade.color.LIGHT_GRAY, 12, bold=False, anchor_x="right", anchor_y="top")
        self._gap_header_text = arcade.Text("", 0, 0, arcade.color.WHITE, 12, bold=True, anchor_x="right", anchor_y="top")
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
        self.computed_gaps = {}
        self.computed_neighbor_gaps = {}

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

    def cycle_gap_mode(self, window=None):
        """Cycle gap mode: Interval (I) -> Leader (L) -> Off -> Interval (I)."""
        if self.show_neighbor_gaps:
            self.show_neighbor_gaps = False
            self.show_gaps = True
        elif self.show_gaps:
            self.show_neighbor_gaps = False
            self.show_gaps = False
        else:
            self.show_neighbor_gaps = True
            self.show_gaps = False

        if window is not None:
            setattr(window, "leaderboard_show_neighbor_gaps", self.show_neighbor_gaps)
            setattr(window, "leaderboard_show_gaps", self.show_gaps)

    def set_entries(self, entries: List[Tuple[str, Tuple[int,int,int], dict, float]], track_length: float = 0.0, current_t: float = 0.0):
        # Sort entries consistently by race progress (descending)
        if any(e[3] > 0 for e in entries):
            self.entries = sorted(entries, key=lambda e: -e[3])
        else:
            self.entries = sorted(entries, key=lambda e: e[2].get("position", 99))
        self._calculate_gaps(track_length=track_length, current_t=current_t)

    def _calculate_gaps(self, track_length: float = 0.0, current_t: float = 0.0):
        if not hasattr(self, "_last_gap_update_t"):
            self._last_gap_update_t = -999.0

        # Broadcast timing delay: update timing gaps on ~2.0s cadence
        should_update = (
            not self.computed_gaps
            or (current_t - self._last_gap_update_t >= 2.0)
            or (current_t < self._last_gap_update_t)
        )
        if not should_update:
            return  # Keep current steady timing tower values

        self._last_gap_update_t = current_t
        self.computed_gaps = {}
        self.computed_neighbor_gaps = {}
        if not self.entries:
            return

        leader_code, _, leader_pos, leader_progress_val = self.entries[0]
        leader_lap = leader_pos.get("lap", 1)

        # Track length fallback: if not provided, estimate from max dist or default to 5000m
        if track_length <= 0.0:
            track_length = max((float(e[2].get("dist", 0.0) or 0.0) for e in self.entries), default=5000.0)
            if track_length <= 0.0:
                track_length = 5000.0

        REF_SPEED = 55.56  # 200 km/h reference speed in m/s

        for idx, (code, _, pos, progress_m) in enumerate(self.entries):
            is_out = (pos.get("rel_dist", 0) == 1) or pos.get("out", False)

            # --- 1. Leader Gap ---
            if idx == 0:
                self.computed_gaps[code] = "Leader"
            elif is_out:
                self.computed_gaps[code] = ""
            else:
                raw_to_leader = max(0.0, (leader_progress_val or 0.0) - (progress_m or 0.0))
                car_lap = pos.get("lap", 1)
                lap_diff = leader_lap - car_lap
                is_lapped = (track_length > 0.0 and raw_to_leader >= track_length) or (lap_diff >= 1 and raw_to_leader >= track_length * 0.85)
                if is_lapped and track_length > 0.0:
                    laps_behind = max(1, round(raw_to_leader / track_length))
                    self.computed_gaps[code] = "+1 LAP" if laps_behind == 1 else f"+{laps_behind} LAPS"
                else:
                    time_to_leader = raw_to_leader / REF_SPEED
                    self.computed_gaps[code] = f"+{time_to_leader:.3f}"

            # --- 2. Neighbor / Interval Gap ---
            if idx == 0:
                self.computed_neighbor_gaps[code] = "Interval"
            elif is_out:
                self.computed_neighbor_gaps[code] = ""
            else:
                code_ahead, _, pos_ahead, progress_ahead = self.entries[idx - 1]
                raw_to_ahead = max(0.0, (progress_ahead or 0.0) - (progress_m or 0.0))
                ahead_lap = pos_ahead.get("lap", 1)
                car_lap = pos.get("lap", 1)
                lap_diff = ahead_lap - car_lap
                is_lapped_ahead = (track_length > 0.0 and raw_to_ahead >= track_length) or (lap_diff >= 1 and raw_to_ahead >= track_length * 0.85)
                if is_lapped_ahead and track_length > 0.0:
                    laps_behind = max(1, round(raw_to_ahead / track_length))
                    self.computed_neighbor_gaps[code] = "+1 LAP" if laps_behind == 1 else f"+{laps_behind} LAPS"
                else:
                    time_to_ahead = raw_to_ahead / REF_SPEED
                    self.computed_neighbor_gaps[code] = f"+{time_to_ahead:.3f}"

    def draw(self, window):
        # Skip rendering entirely if hidden
        if not self._visible:
            return
        self.selected = getattr(window, "selected_drivers", [])
        leaderboard_y = getattr(self, "y_top", None) or (window.height - 40)
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

            text = f"{current_pos}. {code}" 
            if pos.get("rel_dist",0) != 1:
                out_text=""
            else:
                out_text="  OUT"

            if pos.get("in_pit"):
                driver_text = text
                pit_text="  PIT"
            else:
                driver_text = text
                pit_text = ""

            arcade.Text(driver_text,left_x,top_y,text_color,16,anchor_x="left",anchor_y="top").draw()
            
            #PIT indicator in white
            if pit_text:arcade.Text(pit_text, left_x + 80, top_y,arcade.color.WHITE,16,anchor_x="left",anchor_y="top").draw()

            #OUT indicator in red
            if out_text: arcade.Text(out_text, left_x + 80, top_y, (155,17,30), 16, anchor_x="left", anchor_y="top",bold=True).draw()

            # Gap display (if enabled)
            gap_text = ""
            is_header_row = (i == 0)
            if self.show_neighbor_gaps:
                gap_text = self.computed_neighbor_gaps.get(code, "")
            elif self.show_gaps:
                gap_text = self.computed_gaps.get(code, "")

            # if either leader or neighbor gaps are enabled, draw the gap text
            if gap_text and (self.show_neighbor_gaps or self.show_gaps):
                gap_x = right_x - 38
                if code in self.selected:
                    gap_color = arcade.color.BLACK
                elif is_header_row:
                    gap_color = arcade.color.WHITE
                elif "LAP" in gap_text:
                    gap_color = (200, 200, 200)
                else:
                    gap_color = arcade.color.LIGHT_GRAY

                target_text_obj = self._gap_header_text if is_header_row else self._gap_text
                target_text_obj.text = gap_text
                target_text_obj.x = gap_x
                target_text_obj.y = top_y - 2
                target_text_obj.color = gap_color
                target_text_obj.draw()

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

                # 2026+ Overtake / Boost Indicator Dot
                drs_val = pos.get("drs", 0)
                is_overtake_on = drs_val and int(drs_val) >= 10
                
                # Check if overtake is available (gap to car ahead <= 1.0s)
                nb_info = self.computed_neighbor_gaps.get(code, "")
                is_avail = False
                if nb_info and nb_info.startswith("+") and "LAP" not in nb_info:
                    try:
                        s_val = float(nb_info.replace("+", ""))
                        if s_val <= 1.0:
                            is_avail = True
                    except Exception:
                        pass

                if is_overtake_on:
                    drs_color = arcade.color.GREEN   # Active
                elif is_avail:
                    drs_color = arcade.color.YELLOW  # Available within 1s MOM
                else:
                    drs_color = (90, 95, 105)        # Standby / Charging
                
                # Position dot to the left of the tyre icon
                drs_dot_x = tyre_icon_x - icon_size - 4 
                drs_dot_y = tyre_icon_y

                arcade.draw_circle_filled(drs_dot_x, drs_dot_y, 4, drs_color)

        

        # Add text at the bottom of the leaderboard during lap 1 to alert the user to potential mis-ordering
        if new_entries and new_entries[0][2].get("lap", 0) == 1:
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
        self.title = "Lap Times"

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
        arcade.Text(self.title, self.x, leaderboard_y, arcade.color.WHITE, 20, bold=True, anchor_x="left", anchor_y="top").draw()
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

            # Draw position and driver name on left, time on right with more padding
            driver_name = entry.get('driver_name', code)
            arcade.Text(f"{pos}. {driver_name}", left_x + 12, top_y, text_color, 16, anchor_x="left", anchor_y="top").draw()
            if time_str:
                arcade.Text(time_str, right_x - 12, top_y, text_color, 14, anchor_x="right", anchor_y="top").draw()

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

        # Dynamic horizontal position to avoid overlapping championship standings if open
        if getattr(window, "show_drivers_championship", False) or getattr(window, "show_constructors_championship", False):
            self.left = 605
        else:
            self.left = 275

        box_width, box_height, gap = self.width, 225, 10
        # Align with top of Leaderboard to stay in the upper layout area
        leaderboard_top = getattr(getattr(window, "leaderboard_comp", None), "y_top", None)
        current_top = leaderboard_top if leaderboard_top else (window.height - 95)

        # Dynamic floor to prevent overlapping the live telemetry graph
        if hasattr(window, "telemetry_graph_comp") and window.telemetry_graph_comp.visible:
            self.min_top = window.telemetry_graph_comp.bottom + window.telemetry_graph_comp.height + 15
        else:
            self.min_top = 100

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
        arcade.draw_rect_filled(rect, (18, 20, 28, 230))

        team_color = window.driver_colors.get(code, arcade.color.GRAY)
        arcade.draw_rect_outline(rect, team_color, 2)

        header_height = 28
        header_cy = top - (header_height / 2)
        arcade.draw_rect_filled(arcade.XYWH(center_x, header_cy, box_width, header_height), team_color)
        arcade.Text(f"Driver: {code}", left + 10, header_cy, arcade.color.BLACK, 13, anchor_y="center",
                    bold=True).draw()

        left_text_x = left + 12

        # Telemetry Text (Speed, Gear, Overtake/DRS, Gaps)
        speed = driver_pos.get('speed', 0)
        arcade.Text(f"Speed: {speed:.0f} km/h", left_text_x, top - header_height - 16, arcade.color.WHITE, 11, anchor_y="center").draw()
        arcade.Text(f"Gear: {driver_pos.get('gear', '-')}", left_text_x, top - header_height - 34, arcade.color.WHITE, 11, anchor_y="center").draw()

        drs_val = driver_pos.get('drs', 0)
        session_year = getattr(window, "year", 2026) or (getattr(window, "session_info", {}) or {}).get("year", 2026)
        if session_year >= 2026:
            drs_str, drs_color = ("OVERTAKE: ACTIVE", arcade.color.GREEN) if (drs_val in [10, 12, 14] or (drs_val and int(drs_val) >= 10)) else \
                ("OVERTAKE: AVAIL", arcade.color.YELLOW) if drs_val == 8 else ("OVERTAKE: OFF", arcade.color.GRAY)
        else:
            drs_str, drs_color = ("DRS: ON", arcade.color.GREEN) if drs_val in [10, 12, 14] else \
                ("DRS: AVAIL", arcade.color.YELLOW) if drs_val == 8 else ("DRS: OFF", arcade.color.GRAY)
        arcade.Text(drs_str, left_text_x, top - header_height - 52, drs_color, 11, anchor_y="center", bold=True).draw()

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

        if lb and hasattr(lb, "entries") and lb.entries:
            try:
                idx = next(i for i, e in enumerate(lb.entries) if e[0] == code)
                curr_pos = lb.entries[idx][3]

                def get_gap_str(neighbor_idx, prefix, sign):
                    n_code, _, _, n_pos = lb.entries[neighbor_idx]
                    dist = abs(curr_pos - n_pos)
                    time = dist / 55.56  # 200 km/h reference speed
                    return f"{prefix} ({n_code}): {sign}{time:.2f}s ({dist:.0f}m)"

                if idx > 0:
                    gap_ahead = get_gap_str(idx - 1, "Ahead", "+")
                if idx < len(lb.entries) - 1:
                    gap_behind = get_gap_str(idx + 1, "Behind", "-")

            except (StopIteration, IndexError):
                pass

        arcade.Text(gap_ahead, left_text_x, top - header_height - 70, arcade.color.LIGHT_GRAY, 10, anchor_y="center").draw()
        arcade.Text(gap_behind, left_text_x, top - header_height - 88, arcade.color.LIGHT_GRAY, 10, anchor_y="center").draw()

        # Throttle & Brake Gauges (Top right, clear of text)
        thr, brk = driver_pos.get('throttle', 0), driver_pos.get('brake', 0)
        t_r, b_r = max(0.0, min(1.0, thr / 100.0)), max(0.0, min(1.0, brk / 100.0 if brk > 1.0 else brk))
        bar_w, bar_h = 16, 68
        gauge_top = top - header_height - 10
        gauge_bottom = gauge_top - bar_h
        r_center = right - 42

        # Throttle meter
        arcade.draw_rect_filled(arcade.XYWH(r_center - 13, gauge_bottom + bar_h / 2, bar_w, bar_h), (40, 44, 52))
        if t_r > 0:
            arcade.draw_rect_filled(arcade.XYWH(r_center - 13, gauge_bottom + (bar_h * t_r) / 2, bar_w, bar_h * t_r), arcade.color.GREEN)
        arcade.Text("THR", r_center - 13, gauge_bottom - 10, arcade.color.LIGHT_GRAY, 9, bold=True, anchor_x="center", anchor_y="center").draw()

        # Brake meter
        arcade.draw_rect_filled(arcade.XYWH(r_center + 13, gauge_bottom + bar_h / 2, bar_w, bar_h), (40, 44, 52))
        if b_r > 0:
            arcade.draw_rect_filled(arcade.XYWH(r_center + 13, gauge_bottom + (bar_h * b_r) / 2, bar_w, bar_h * b_r), arcade.color.RED)
        arcade.Text("BRK", r_center + 13, gauge_bottom - 10, arcade.color.LIGHT_GRAY, 9, bold=True, anchor_x="center", anchor_y="center").draw()

        # Lower Section: Divider and Tyre Health info
        arcade.draw_line(left + 10, top - header_height - 114, right - 10, top - header_height - 114, (55, 60, 75), 1)

        has_tyre_rendered = False
        if self.degradation_integrator and hasattr(window, 'frames'):
            try:
                idx = min(int(window.frame_index), window.n_frames - 1)
                frame = window.frames[idx]
                health_data = self.degradation_integrator.get_health_for_frame(code, frame)
                
                if health_data:
                    tyre_bar_w = box_width - 24
                    bar_params = format_tyre_health_bar(health_data['health'], width=tyre_bar_w, height=12)
                    bar_cx = left + 12 + tyre_bar_w / 2
                    bar_y = top - header_height - 134
                    
                    # Background bar
                    arcade.draw_rect_filled(arcade.XYWH(bar_cx, bar_y, bar_params['width'], bar_params['height']), (45, 48, 56))
                    # Health fill bar
                    if bar_params['fill_width'] > 0:
                        arcade.draw_rect_filled(
                            arcade.XYWH(left + 12 + bar_params['fill_width']/2, bar_y, 
                                       bar_params['fill_width'], bar_params['height']),
                            bar_params['color']
                        )
                    # Border
                    arcade.draw_rect_outline(arcade.XYWH(bar_cx, bar_y, bar_params['width'], bar_params['height']), (120, 125, 140), 1)
                    
                    # Tyre info text below bar
                    tyre_text = format_degradation_text(health_data)
                    arcade.Text(tyre_text, left_text_x, top - header_height - 158, arcade.color.LIGHT_GRAY, 10, anchor_y="center").draw()
                    has_tyre_rendered = True
            except (KeyError, AttributeError, TypeError) as e:
                pass

        if not has_tyre_rendered:
            arcade.Text("Tyre Status: Normal", left_text_x, top - header_height - 140, (140, 145, 160), 10, anchor_y="center").draw()

    def _get_driver_color(self, window, code):
        return window.driver_colors.get(code, arcade.color.GRAY)

    def _get_team_color(self, window, code):
        return window.team_colors.get(code, arcade.color.GRAY)


class ControlsPopupComponent(BaseComponent):
    def __init__(
        self,
        width: int = 430,
        height: int = 260,
        header_font_size: int = 18,
        body_font_size: int = 16,
        lines: Optional[list[str]] = None,
    ):

        self.width = width
        self.height = height
        self.visible = False
        
        self.cx: Optional[float] = None
        self.cy: Optional[float] = None
        
        self.header_font_size = header_font_size
        self.body_font_size = body_font_size
        self.lines = lines
        
        self._header_text = arcade.Text("", 0, 0, arcade.color.BLACK, self.header_font_size, anchor_x="left", anchor_y="center")
        self._body_text = arcade.Text("", 0, 0, arcade.color.LIGHT_GRAY, self.body_font_size, anchor_x="left", anchor_y="center")

    def _default_lines(self) -> list[str]:
        return [
            ("SPACE", "Pause/Resume"),
            ("← / →", "Jump back/forward"),
            ("↑ / ↓", "Speed +/-"),
            ("1-4", "Set speed: 0.5x / 1x / 2x / 4x"),
            ("R", "Restart"),
            ("D", "Toggle DRS Zones"),
            ("B", "Toggle Progress Bar"),
            ("L", "Toggle Driver Labels"),
            ("G", "Toggle Gap Mode (Interval/Leader)"),
            ("H", "Toggle Help Popup"),
            ("C", "Toggle Drivers points table"),
            ("A", "Toggle Constructors points table")
        ]

    def set_lines(self, lines: Optional[list[str]]):
        self.lines = lines

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
        controls = self.lines if self.lines is not None else self._default_lines()
        
        # Calculate layout and required height dynamically to prevent contents from leaving window
        header_height = 28
        line_spacing = 18
        body_font_size = min(self.body_font_size, 11)
        needed_height = header_height + 20 + len(controls) * line_spacing + 12
        box_height = max(self.height, needed_height)

        cx = self.cx if self.cx is not None else window.width / 2
        cy = self.cy if self.cy is not None else window.height / 2
        
        # Clamp cy so popup box never leaves screen edges
        if cy - box_height / 2 < 20:
            cy = 20 + box_height / 2
        if cy + box_height / 2 > window.height - 20:
            cy = window.height - 20 - box_height / 2

        rect = arcade.XYWH(cx, cy, self.width, box_height)
        arcade.draw_rect_filled(rect, (14, 18, 26, 245))
        arcade.draw_rect_outline(rect, (70, 85, 115, 230), 1.5)

        header_cy = cy + box_height / 2 - header_height / 2
        arcade.draw_rect_filled(arcade.XYWH(cx, header_cy, self.width, header_height), (35, 45, 65, 240))
        
        self._header_text.font_size = min(self.header_font_size, 13)
        self._header_text.bold = True
        self._header_text.color = arcade.color.WHITE
        self._header_text.text = "CONTROLS & SHORTCUTS"
        self._header_text.x = cx - self.width / 2 + 14
        self._header_text.y = header_cy
        self._header_text.draw()

        left_x = cx - self.width / 2 + 16
        desc_x = cx - self.width / 2 + 115
        y = header_cy - header_height / 2 - 14

        for key, desc in controls:
            # Draw key
            self._body_text.font_size = body_font_size
            self._body_text.bold = True
            self._body_text.color = (130, 200, 255)
            self._body_text.text = key
            self._body_text.x = left_x
            self._body_text.y = y
            self._body_text.draw()

            # Draw description
            self._body_text.bold = False
            self._body_text.color = (210, 220, 230)
            self._body_text.text = desc
            self._body_text.x = desc_x
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
    
class ConstructorsChampionshipOverlay:

    def __init__(self, live_constructors_standings=None, current_constructors_standings=None,
                 x=20, y=300, visible=True, session=None):

        self.live_constructors_standings = live_constructors_standings or {}
        self.current_constructors_standings = current_constructors_standings or {}
        self.team_colors = {}
        self.visible = visible
        self.session = session

        self.x = x
        self.y = y
        self.current_lap = 1
        self.cached_lap_standings = {}

        if self.session is not None and hasattr(self.session, "drivers"):
            try:
                for driver in self.session.drivers:
                    team = self.session.get_driver(driver)["TeamName"]
                    if team not in self.team_colors:
                        try:
                            color_hex = fastf1.plotting.get_team_color(team, self.session)
                            hex_color = color_hex.lstrip("#")
                            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                            self.team_colors[team] = rgb
                        except Exception:
                            self.team_colors[team] = (200, 200, 200)
            except Exception:
                pass

    def update(self, lap):
        """Update standings for current lap"""
        self.current_lap = lap
        self.cached_lap_standings = self.live_constructors_standings.get(lap, {})

    def draw(self):

        if not self.visible:
            return

        card_w, card_h = 320, 275
        card_cx = self.x + card_w / 2 - 10
        card_cy = self.y - card_h / 2 + 10
        arcade.draw_rect_filled(arcade.XYWH(card_cx, card_cy, card_w, card_h), (18, 20, 28, 235))
        arcade.draw_rect_outline(arcade.XYWH(card_cx, card_cy, card_w, card_h), (60, 75, 95, 255), 1.5)

        y = self.y

        arcade.draw_text(
            "Constructors Championship Standings",
            self.x,
            y,
            arcade.color.WHITE,
            13,
            bold=True
        )

        y -= 25

        for pos, (team, pts) in enumerate(self.cached_lap_standings.items(), start=1):

            base_pts = self.current_constructors_standings.get(team, 0)
            gained = pts - base_pts

            color = self.team_colors.get(team, (200,200,200))

            # team bar
            arcade.draw_rect_filled(
            arcade.XYWH(self.x - 6, y+6, 4, 16),
            color
            )

            # position
            arcade.draw_text(
                f"{pos}",
                self.x,
                y,
                arcade.color.WHITE,
                11
            )

            # team
            arcade.draw_text(
                team,
                self.x + 20,
                y,
                arcade.color.WHITE,
                11
            )

            # points
            arcade.draw_text(
                f"{pts:.0f}",
                self.x + 180,
                y,
                arcade.color.WHITE,
                11
            )

            # gained points
            if gained > 0:
                arcade.draw_text(
                    f"+{gained:.0f}",
                    self.x + 220,
                    y,
                    arcade.color.LIME_GREEN,
                    11
                )

            y -= 20

            if pos >= 11:
                break

            previous_pos = list(self.current_constructors_standings.keys()).index(team) + 1 if team in self.current_constructors_standings else pos
            delta = previous_pos - pos

            if delta > 0:
                arrow = "▲"
                arrow_color = arcade.color.LIME_GREEN
            elif delta < 0:
                arrow = "▼"
                arrow_color = arcade.color.RED
            else:
                arrow = "•"
                arrow_color = arcade.color.GRAY

            arcade.draw_text(
            arrow,
            self.x + 280,
            y,
            arrow_color,
            11
        )
        
class DriversChampionshipOverlay:

    def __init__(self, live_standings=None, current_driver_standings=None,driver_colors=None,
                 x=20, y=300, visible=True):

        self.live_standings = live_standings or {}
        self.current_driver_standings = current_driver_standings or {}
        self.driver_colors = driver_colors or {}
        self.visible = visible

        self.x = x
        self.y = y
        self.current_lap = 1
        self.cached_lap_standings = {}

    def update(self, lap):
        """Update standings for current lap"""
        self.current_lap = lap
        self.cached_lap_standings = self.live_standings.get(lap, {})

    def draw(self):

        if not self.visible:
            return

        card_w, card_h = 270, 275
        card_cx = self.x + card_w / 2 - 10
        card_cy = self.y - card_h / 2 + 10
        arcade.draw_rect_filled(arcade.XYWH(card_cx, card_cy, card_w, card_h), (18, 20, 28, 235))
        arcade.draw_rect_outline(arcade.XYWH(card_cx, card_cy, card_w, card_h), (60, 75, 95, 255), 1.5)

        y = self.y

        arcade.draw_text(
            "Driver Championship Standings",
            self.x,
            y,
            arcade.color.WHITE,
            13,
            bold=True
        )

        y -= 25

        for pos, (driver, pts) in enumerate(self.cached_lap_standings.items(), start=1):

            base_pts = self.current_driver_standings.get(driver, 0)
            gained = pts - base_pts

            # team color
            color = self.driver_colors.get(driver, (200,200,200))

            # team bar
            arcade.draw_rect_filled(
            arcade.XYWH(self.x - 6, y+6, 4, 16),
            color
            )

            # position
            arcade.draw_text(
                f"{pos}",
                self.x,
                y,
                arcade.color.WHITE,
                11
            )

            # driver
            arcade.draw_text(
                driver,
                self.x + 20,
                y,
                arcade.color.WHITE,
                11
            )

            # points
            arcade.draw_text(
                f"{pts:.0f}",
                self.x + 80,
                y,
                arcade.color.WHITE,
                11
            )

            # gained points
            if gained > 0:
                arcade.draw_text(
                    f"+{gained:.0f}",
                    self.x + 120,
                    y,
                    arcade.color.LIME_GREEN,
                    11
                )

            y -= 20

            if pos >= 12:
                break

            previous_pos = list(self.current_driver_standings.keys()).index(driver) + 1 if driver in self.current_driver_standings else pos
            delta = previous_pos - pos

            if delta > 0:
                arrow = "▲"
                arrow_color = arcade.color.LIME_GREEN
            elif delta < 0:
                arrow = "▼"
                arrow_color = arcade.color.RED
            else:
                arrow = "•"
                arrow_color = arcade.color.GRAY

            arcade.draw_text(
            arrow,
            self.x + 200,
            y,
            arrow_color,
            11
        )

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
   if example_lap is None or "DRS" not in example_lap or "X" not in example_lap or "Y" not in example_lap:
       return []
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


class LapSelectorComponent(BaseComponent):
    """Clickable lap selector and quick-jump navigation tool."""
    def __init__(self, x: int = 140, y: int = 40, total_laps: int = 55):
        self.x = x
        self.y = y
        self.total_laps = total_laps or 55
        self.popup_open = False
        self.prev_rect = None
        self.next_rect = None
        self.select_btn_rect = None
        self.lap_button_rects = []
        self.scroll_index = 0
        self.max_visible = 10
        self.mouse_x = -1
        self.mouse_y = -1

    def draw(self, window):
        current_lap = 1
        if hasattr(window, "frames") and window.frames and hasattr(window, "frame_index"):
            idx = min(int(window.frame_index), len(window.frames) - 1)
            current_lap = int(window.frames[idx].get("lap", 1))

        btn_y = self.y
        btn_h = 24
        
        # Mouse hover detection
        mx = self.mouse_x
        my = self.mouse_y

        # Prev Button
        prev_w = 26
        self.prev_rect = (self.x, btn_y - btn_h/2, self.x + prev_w, btn_y + btn_h/2)
        prev_hover = (self.prev_rect[0] <= mx <= self.prev_rect[2] and self.prev_rect[1] <= my <= self.prev_rect[3])
        prev_bg = (50, 62, 85) if prev_hover else (30, 36, 48)
        prev_border = (100, 130, 180) if prev_hover else (55, 68, 88)
        arcade.draw_rect_filled(arcade.XYWH(self.x + prev_w/2, btn_y, prev_w, btn_h), prev_bg)
        arcade.draw_rect_outline(arcade.XYWH(self.x + prev_w/2, btn_y, prev_w, btn_h), prev_border, 1.2)
        # Styled left triangle arrow
        cx = self.x + prev_w/2
        arcade.draw_triangle_filled(cx - 4, btn_y, cx + 3, btn_y + 4.5, cx + 3, btn_y - 4.5, (230, 240, 255))

        # Select Lap Button
        sel_x = self.x + prev_w + 6
        sel_w = 105
        self.select_btn_rect = (sel_x, btn_y - btn_h/2, sel_x + sel_w, btn_y + btn_h/2)
        sel_hover = (self.select_btn_rect[0] <= mx <= self.select_btn_rect[2] and self.select_btn_rect[1] <= my <= self.select_btn_rect[3])
        if self.popup_open:
            bg_col = (45, 95, 160)
            border_col = (90, 160, 240)
        elif sel_hover:
            bg_col = (50, 65, 90)
            border_col = (100, 130, 180)
        else:
            bg_col = (30, 36, 48)
            border_col = (55, 68, 88)
        arcade.draw_rect_filled(arcade.XYWH(sel_x + sel_w/2, btn_y, sel_w, btn_h), bg_col)
        arcade.draw_rect_outline(arcade.XYWH(sel_x + sel_w/2, btn_y, sel_w, btn_h), border_col, 1.2)
        arcade.Text("Select Lap", sel_x + 42, btn_y, arcade.color.WHITE, 10, bold=True, anchor_x="center", anchor_y="center").draw()
        # Styled down triangle arrow
        tx = sel_x + sel_w - 16
        arcade.draw_triangle_filled(tx, btn_y - 3, tx - 4, btn_y + 3, tx + 4, btn_y + 3, (210, 225, 245))

        # Next Button
        next_x = sel_x + sel_w + 6
        next_w = 26
        self.next_rect = (next_x, btn_y - btn_h/2, next_x + next_w, btn_y + btn_h/2)
        next_hover = (self.next_rect[0] <= mx <= self.next_rect[2] and self.next_rect[1] <= my <= self.next_rect[3])
        next_bg = (50, 62, 85) if next_hover else (30, 36, 48)
        next_border = (100, 130, 180) if next_hover else (55, 68, 88)
        arcade.draw_rect_filled(arcade.XYWH(next_x + next_w/2, btn_y, next_w, btn_h), next_bg)
        arcade.draw_rect_outline(arcade.XYWH(next_x + next_w/2, btn_y, next_w, btn_h), next_border, 1.2)
        # Styled right triangle arrow
        cx_n = next_x + next_w/2
        arcade.draw_triangle_filled(cx_n + 4, btn_y, cx_n - 3, btn_y + 4.5, cx_n - 3, btn_y - 4.5, (230, 240, 255))

        if self.popup_open:
            self._draw_dropdown_list(window, current_lap, sel_x, btn_y, btn_h, sel_w)

    def on_mouse_motion(self, window, x: float, y: float, dx: float, dy: float):
        self.mouse_x = x
        self.mouse_y = y

    def on_mouse_scroll(self, window, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
        if not self.popup_open:
            return False
        if scroll_y > 0:
            self.scroll_index = max(0, self.scroll_index - 1)
            return True
        elif scroll_y < 0:
            max_scroll = max(0, self.total_laps - self.max_visible)
            self.scroll_index = min(max_scroll, self.scroll_index + 1)
            return True
        return False

    def _draw_dropdown_list(self, window, current_lap: int, sel_x: float, btn_y: float, btn_h: float, sel_w: float):
        list_w = max(sel_w, 115)
        item_h = 24
        visible_count = min(self.total_laps, self.max_visible)
        list_h = visible_count * item_h + 8

        list_left = sel_x
        list_top = btn_y - btn_h / 2 - 3
        list_cx = list_left + list_w / 2
        list_cy = list_top - list_h / 2

        # Dropdown container background & border (attached beneath the button)
        arcade.draw_rect_filled(arcade.XYWH(list_cx, list_cy, list_w, list_h), (20, 24, 34, 245))
        arcade.draw_rect_outline(arcade.XYWH(list_cx, list_cy, list_w, list_h), (60, 80, 110, 255), 1.5)

        self.lap_button_rects = []
        mx = self.mouse_x
        my = self.mouse_y

        # Clamp scroll index
        max_scroll = max(0, self.total_laps - visible_count)
        self.scroll_index = max(0, min(self.scroll_index, max_scroll))

        for row in range(visible_count):
            lap_num = self.scroll_index + row + 1
            if lap_num > self.total_laps:
                break

            item_cy = list_top - 4 - row * item_h - item_h / 2
            item_left = list_left + 4
            item_w = list_w - 8
            item_cx = item_left + item_w / 2

            is_curr = (lap_num == current_lap)
            is_hover = (item_left <= mx <= item_left + item_w and item_cy - item_h/2 <= my <= item_cy + item_h/2)

            if is_curr:
                bg = (35, 120, 55)
                text_col = arcade.color.YELLOW
            elif is_hover:
                bg = (45, 60, 85)
                text_col = arcade.color.WHITE
            else:
                bg = (24, 30, 42) if row % 2 == 0 else (20, 25, 36)
                text_col = (210, 220, 235)

            arcade.draw_rect_filled(arcade.XYWH(item_cx, item_cy, item_w, item_h - 2), bg)
            if is_curr:
                arcade.draw_rect_outline(arcade.XYWH(item_cx, item_cy, item_w, item_h - 2), (80, 210, 100), 1)

            arcade.Text(f"Lap {lap_num}", item_left + 10, item_cy, text_col, 10, bold=is_curr, anchor_y="center").draw()
            self.lap_button_rects.append((lap_num, item_left, item_cy - item_h/2, item_left + item_w, item_cy + item_h/2))

        # Scrollbar track & thumb if scrollable
        if self.total_laps > visible_count:
            sb_x = list_left + list_w - 4
            sb_h = list_h - 8
            arcade.draw_line(sb_x, list_top - 4, sb_x, list_top - 4 - sb_h, (40, 50, 70), 2)
            thumb_ratio = visible_count / self.total_laps
            thumb_h = max(12, sb_h * thumb_ratio)
            scroll_ratio = self.scroll_index / max(1, self.total_laps - visible_count)
            thumb_top = (list_top - 4) - scroll_ratio * (sb_h - thumb_h)
            arcade.draw_line(sb_x, thumb_top, sb_x, thumb_top - thumb_h, (100, 140, 190), 3)

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int) -> bool:
        if self.popup_open:
            # Check click on lap items
            for lap_num, x1, y1, x2, y2 in self.lap_button_rects:
                if x1 <= x <= x2 and y1 <= y <= y2:
                    self.jump_to_lap(window, lap_num)
                    self.popup_open = False
                    return True

            # Clicking the toggle button again closes the popup
            if self.select_btn_rect:
                x1, y1, x2, y2 = self.select_btn_rect
                if x1 <= x <= x2 and y1 <= y <= y2:
                    self.popup_open = False
                    return True

            # Any click outside closes the dropdown list
            self.popup_open = False
            return True

        if self.prev_rect:
            x1, y1, x2, y2 = self.prev_rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                curr_lap = int(window.frames[int(window.frame_index)].get("lap", 1))
                self.jump_to_lap(window, max(1, curr_lap - 1))
                return True

        if self.next_rect:
            x1, y1, x2, y2 = self.next_rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                curr_lap = int(window.frames[int(window.frame_index)].get("lap", 1))
                self.jump_to_lap(window, min(self.total_laps, curr_lap + 1))
                return True

        if self.select_btn_rect:
            x1, y1, x2, y2 = self.select_btn_rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                self.popup_open = not self.popup_open
                if self.popup_open:
                    curr_lap = 1
                    if hasattr(window, "frames") and window.frames and hasattr(window, "frame_index"):
                        idx = min(int(window.frame_index), len(window.frames) - 1)
                        curr_lap = int(window.frames[idx].get("lap", 1))
                    # Center scroll around current lap
                    max_scroll = max(0, self.total_laps - self.max_visible)
                    self.scroll_index = max(0, min(max_scroll, curr_lap - self.max_visible // 2))
                return True

        return False

    def jump_to_lap(self, window, target_lap: int):
        if hasattr(window, "lap_start_frames") and window.lap_start_frames:
            target_frame = window.lap_start_frames.get(target_lap)
            if target_frame is not None:
                window.frame_index = float(target_frame)
                if hasattr(window, "_broadcast_telemetry_state"):
                    window._broadcast_telemetry_state()

    def prev_lap(self, window):
        if not hasattr(window, "frames") or not window.frames:
            return
        idx = min(int(window.frame_index), len(window.frames) - 1)
        curr_lap = int(window.frames[idx].get("lap", 1))
        self.jump_to_lap(window, max(1, curr_lap - 1))

    def next_lap(self, window):
        if not hasattr(window, "frames") or not window.frames:
            return
        idx = min(int(window.frame_index), len(window.frames) - 1)
        curr_lap = int(window.frames[idx].get("lap", 1))
        self.jump_to_lap(window, min(self.total_laps, curr_lap + 1))


class LiveTelemetryGraphComponent(BaseComponent):
    """
    Renders live F1 telemetry graph matching qualifying style:
    - Speed (km/h) with 2026 Overtake / Straight Mode active zones
    - Gear (1 to 8)
    - Throttle (Green) & Brake (Red) (%)
    - Real-time vertical playback needle tracking current car position!
    """
    def __init__(self, left: int = 300, bottom: int = 120, width: int = 1500, height: int = 380, visible: bool = True):
        self.left = left
        self.bottom = bottom
        self.width = width
        self.height = height
        self._visible = visible
        self._cached_lap_data = None
        self._cached_key = None

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, val: bool):
        self._visible = val

    def toggle_visibility(self):
        self._visible = not self._visible
        return self._visible

    def draw(self, window):
        if not self._visible or not hasattr(window, "frames") or not window.frames:
            return

        frame_idx = min(int(window.frame_index), len(window.frames) - 1)
        curr_frame = window.frames[frame_idx]

        chart_left = self.left
        chart_right = self.left + self.width
        chart_top = self.bottom + self.height
        chart_bottom = self.bottom
        chart_w = self.width
        chart_h = self.height

        driver_code = getattr(window, "selected_driver", None)
        if not driver_code and getattr(window, "selected_drivers", None):
            driver_code = window.selected_drivers[-1]

        # Requirement 2: Telemetry must be displayed for user-selected driver, NOT default race leader
        if not driver_code or driver_code not in curr_frame.get("drivers", {}):
            # Render empty state placeholder container when no driver is currently selected
            arcade.draw_rect_filled(arcade.XYWH(chart_left + chart_w * 0.5, chart_bottom + chart_h * 0.5, chart_w, chart_h), (14, 18, 26, 215))
            arcade.draw_rect_outline(arcade.XYWH(chart_left + chart_w * 0.5, chart_bottom + chart_h * 0.5, chart_w, chart_h), (45, 55, 75, 200), 1)
            arcade.Text("LIVE TELEMETRY", chart_left + 15, chart_top - 18, (160, 180, 205), 11, bold=True, anchor_y="center").draw()
            arcade.Text("Select a driver from the leaderboard to view live telemetry", chart_left + chart_w * 0.5, chart_bottom + chart_h * 0.5, (140, 160, 185), 12, bold=True, anchor_x="center", anchor_y="center").draw()
            return

        driver_pos = curr_frame["drivers"][driver_code]
        driver_lap = int(driver_pos.get("lap", 1))

        fs = window.frames
        if not hasattr(fs, "codes") or driver_code not in fs.codes:
            return

        d_idx = fs.codes.index(driver_code)
        cache_key = (driver_code, driver_lap)

        if self._cached_key != cache_key:
            ch_lap = fs.channels["lap"][:, d_idx]
            lap_mask = np.where(ch_lap == driver_lap)[0]
            if len(lap_mask) < 2:
                start_f = max(0, frame_idx - 300)
                end_f = min(len(fs), start_f + 1500)
            else:
                start_f = lap_mask[0]
                end_f = lap_mask[-1]

            length = max(1, end_f - start_f)
            step = max(1, length // 350)

            sub_speed = fs.channels["speed"][start_f:end_f:step, d_idx]
            sub_gear = fs.channels["gear"][start_f:end_f:step, d_idx]
            sub_thr = fs.channels["throttle"][start_f:end_f:step, d_idx]
            sub_brk = fs.channels["brake"][start_f:end_f:step, d_idx]
            sub_drs = fs.channels["drs"][start_f:end_f:step, d_idx]

            self._cached_lap_data = {
                "start_f": start_f,
                "end_f": end_f,
                "speed": sub_speed,
                "gear": sub_gear,
                "throttle": sub_thr,
                "brake": sub_brk,
                "drs": sub_drs,
                "n_pts": len(sub_speed)
            }
            self._cached_key = cache_key

        data = self._cached_lap_data
        if not data or data["n_pts"] < 2:
            return

        chart_left = self.left
        chart_right = self.left + self.width
        chart_top = self.bottom + self.height
        chart_bottom = self.bottom
        chart_w = self.width
        chart_h = self.height

        M = 20
        effective_h = max(0, chart_h - 2 * M)
        speed_h = int(effective_h * 0.50)
        gear_h = int(effective_h * 0.25)
        ctrl_h = effective_h - speed_h - gear_h

        speed_top = chart_top
        speed_bottom = speed_top - speed_h
        gear_top = speed_bottom - M
        gear_bottom = gear_top - gear_h
        ctrl_top = gear_bottom - M
        ctrl_bottom = ctrl_top - ctrl_h

        # Background cards
        arcade.draw_rect_filled(arcade.XYWH(chart_left + chart_w * 0.5, speed_bottom + speed_h * 0.5, chart_w, speed_h), (16, 20, 28, 230))
        arcade.draw_rect_outline(arcade.XYWH(chart_left + chart_w * 0.5, speed_bottom + speed_h * 0.5, chart_w, speed_h), (45, 55, 75, 200), 1)

        arcade.draw_rect_filled(arcade.XYWH(chart_left + chart_w * 0.5, gear_bottom + gear_h * 0.5, chart_w, gear_h), (16, 20, 28, 230))
        arcade.draw_rect_outline(arcade.XYWH(chart_left + chart_w * 0.5, gear_bottom + gear_h * 0.5, chart_w, gear_h), (45, 55, 75, 200), 1)

        arcade.draw_rect_filled(arcade.XYWH(chart_left + chart_w * 0.5, ctrl_bottom + ctrl_h * 0.5, chart_w, ctrl_h), (16, 20, 28, 230))
        arcade.draw_rect_outline(arcade.XYWH(chart_left + chart_w * 0.5, ctrl_bottom + ctrl_h * 0.5, chart_w, ctrl_h), (45, 55, 75, 200), 1)

        curr_spd = driver_pos.get("speed", 0.0)
        curr_gr = driver_pos.get("gear", 1)
        curr_th = driver_pos.get("throttle", 0.0)
        curr_drs = driver_pos.get("drs", 0)
        is_overtake_on = curr_drs and int(curr_drs) >= 10

        driver_col = getattr(window, "driver_colors", {}).get(driver_code, arcade.color.WHITE)
        arcade.Text(f"LIVE TELEMETRY: {driver_code}  (Lap {driver_lap})", chart_left + 10, speed_top + 8, driver_col, 13, bold=True).draw()

        # 2026 Boost / Overtake Badge
        badge_x = chart_right - 100
        badge_y = speed_top + 16
        if is_overtake_on:
            arcade.draw_rect_filled(arcade.XYWH(badge_x, badge_y, 140, 20), (30, 140, 50))
            arcade.Text("OVERTAKE: ACTIVE", badge_x, badge_y, arcade.color.WHITE, 10, bold=True, anchor_x="center", anchor_y="center").draw()
        else:
            arcade.draw_rect_filled(arcade.XYWH(badge_x, badge_y, 140, 20), (45, 52, 65))
            arcade.Text("BOOST: STANDBY", badge_x, badge_y, (180, 190, 200), 10, bold=True, anchor_x="center", anchor_y="center").draw()

        arcade.Text("Speed (km/h)", chart_left + 260, speed_top + 8, arcade.color.LIGHT_GRAY, 11).draw()
        arcade.Text("Gear (1 - 8)", chart_left + 10, gear_top + 6, arcade.color.LIGHT_GRAY, 11).draw()
        arcade.Text("Throttle (Green) / Brake (Red) (%)", chart_left + 10, ctrl_top + 6, arcade.color.LIGHT_GRAY, 11).draw()

        n_pts = data["n_pts"]
        start_f = data["start_f"]
        end_f = data["end_f"]

        # Overtake active shaded zones in speed chart
        drs_arr = data["drs"]
        in_zone = False
        zone_start_x = 0
        for i in range(n_pts):
            active = drs_arr[i] and int(drs_arr[i]) >= 10
            x_norm = i / max(1, n_pts - 1)
            px = chart_left + x_norm * chart_w
            if active and not in_zone:
                in_zone = True
                zone_start_x = px
            elif not active and in_zone:
                in_zone = False
                arcade.draw_rect_filled(arcade.XYWH((zone_start_x + px)/2, speed_bottom + speed_h/2, max(2, px - zone_start_x), speed_h), (40, 160, 60, 45))
        if in_zone:
            arcade.draw_rect_filled(arcade.XYWH((zone_start_x + chart_right)/2, speed_bottom + speed_h/2, max(2, chart_right - zone_start_x), speed_h), (40, 160, 60, 45))

        # 1. Speed line
        speed_pts = []
        max_s = 360.0
        for i, s in enumerate(data["speed"]):
            x_norm = i / max(1, n_pts - 1)
            px = chart_left + x_norm * chart_w
            py = speed_bottom + 4 + (min(max_s, max(0.0, float(s))) / max_s) * (speed_h - 8)
            speed_pts.append((px, py))
        if len(speed_pts) > 1:
            arcade.draw_line_strip(speed_pts, (220, 235, 255), 2)

        # 2. Gear line
        gear_pts = []
        for i, g in enumerate(data["gear"]):
            x_norm = i / max(1, n_pts - 1)
            px = chart_left + x_norm * chart_w
            py = gear_bottom + 4 + (min(8, max(1, int(g))) / 8.0) * (gear_h - 8)
            gear_pts.append((px, py))
        if len(gear_pts) > 1:
            arcade.draw_line_strip(gear_pts, (255, 170, 50), 2)

        # 3. Throttle & Brake lines
        thr_pts = []
        brk_pts = []
        for i in range(n_pts):
            x_norm = i / max(1, n_pts - 1)
            px = chart_left + x_norm * chart_w
            th = min(100.0, max(0.0, float(data["throttle"][i])))
            br = float(data["brake"][i])
            if br <= 1.0: br *= 100.0
            py_th = ctrl_bottom + 4 + (th / 100.0) * (ctrl_h - 8)
            py_br = ctrl_bottom + 4 + (min(100.0, br) / 100.0) * (ctrl_h - 8)
            thr_pts.append((px, py_th))
            brk_pts.append((px, py_br))
        if len(thr_pts) > 1:
            arcade.draw_line_strip(thr_pts, (50, 220, 90), 2)
        if len(brk_pts) > 1:
            arcade.draw_line_strip(brk_pts, (240, 60, 60), 2)

        # Live Playback Needle
        if start_f <= frame_idx <= end_f:
            cur_norm = (frame_idx - start_f) / max(1, end_f - start_f)
        else:
            cur_norm = (frame_idx % max(1, end_f - start_f)) / max(1, end_f - start_f)

        needle_x = chart_left + cur_norm * chart_w
        arcade.draw_line(needle_x, ctrl_bottom, needle_x, speed_top, (255, 255, 255, 220), 2)

        readout = f"{curr_spd:.0f} km/h | G{curr_gr} | THR {curr_th:.0f}%"
        readout_x = min(chart_right - 100, max(chart_left + 100, needle_x))
        arcade.draw_rect_filled(arcade.XYWH(readout_x, speed_top - 16, 210, 20), (10, 14, 20, 230))
        arcade.Text(readout, readout_x, speed_top - 16, arcade.color.WHITE, 10, bold=True, anchor_x="center", anchor_y="center").draw()

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int) -> bool:
        if not self._visible:
            return False
        if self.left <= x <= self.left + self.width and self.bottom <= y <= self.bottom + self.height:
            return True
        return False
