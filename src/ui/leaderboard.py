import arcade
import os
import pandas as pd
from typing import List, Tuple
from .base import BaseComponent

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

    def set_entries(self, entries: List[Tuple[str, Tuple[int,int,int], dict, float]]):
        # entries sorted as expected
        self.entries = entries
        self._calculate_gaps()

    def _calculate_gaps(self):
        self.computed_gaps = {}
        self.computed_neighbor_gaps = {}
        if not self.entries:
            return

        leader_progress_val = self.entries[0][3]

        for idx, (code, _, pos, progress_m) in enumerate(self.entries):
            # Leader gap
            try:
                raw_to_leader = abs(leader_progress_val - (progress_m or 0.0))
                dist_to_leader = raw_to_leader / 10.0
                time_to_leader = dist_to_leader / 55.56
                self.computed_gaps[code] = 0.0 if idx == 0 else time_to_leader
            except Exception:
                self.computed_gaps[code] = None

            # Neighbor gap
            ahead_info = None
            try:
                if idx > 0:
                    code_ahead, _, _, progress_ahead = self.entries[idx - 1]
                    raw = abs((progress_m or 0.0) - (progress_ahead or 0.0))
                    dist_m = raw / 10.0
                    time_s = dist_m / 55.56
                    ahead_info = (code_ahead, dist_m, time_s)
            except Exception:
                ahead_info = None
            
            self.computed_neighbor_gaps[code] = {"ahead": ahead_info}

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
                neighbor_info = self.computed_neighbor_gaps.get(code)

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
                gap_val = self.computed_gaps.get(code)
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
