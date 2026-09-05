import arcade
import threading
import numpy as np
from src.ui_components import (
    build_track_from_example_lap,
    LapTimeLeaderboardComponent,
    RaceControlsComponent,
    draw_finish_line,
    LegendComponent,
    ControlsPopupComponent,
    QualifyingLapTimeComponent,
)
from src.f1_data import get_driver_practice_telemetry
from src.f1_data import FPS
from src.lib.time import format_time

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "F1 Practice Telemetry"

H_ROW = 38
HEADER_H = 56
LEFT_MARGIN = 40
RIGHT_MARGIN = 40
TOP_MARGIN = 40
BOTTOM_MARGIN = 40


class PracticeReplay(arcade.Window):
    def __init__(self, session, data, circuit_rotation=0, left_ui_margin=340, right_ui_margin=0, title="Practice Results"):
        super().__init__(width=SCREEN_WIDTH, height=SCREEN_HEIGHT, title=title, resizable=True)
        self.maximize()

        self.session = session
        self.data = data

        # Use the lap time leaderboard for practice - show driver names AND times
        self.leaderboard = LapTimeLeaderboardComponent(
            x=LEFT_MARGIN,
            width=300
        )
        self.leaderboard.title = "Practice Times"

        self.race_controls_comp = RaceControlsComponent(
            center_x= self.width // 2 + 100,
            center_y= 40
        )
        self.qualifying_lap_time_comp = QualifyingLapTimeComponent()

        # Convert practice results to leaderboard format - show name and time
        practice_results = self.data.get("results", [])
        transformed_results = []
        for res in practice_results:
            transformed = dict(res)
            transformed['pos'] = transformed.pop('position', 0)
            # Show full name in driver_name (for display)
            full_name = transformed.get('full_name', transformed.get('code', ''))
            if len(full_name) > 15:
                full_name = full_name[:12] + "..."
            transformed['driver_name'] = full_name
            # Format time nicely
            time_val = transformed.get('time')
            if time_val:
                try:
                    seconds = float(time_val)
                    transformed['time'] = format_time(seconds)
                except (ValueError, TypeError):
                    pass
            transformed_results.append(transformed)
        self.leaderboard.set_entries(transformed_results)

        # Track comparison driver (separate from primary driver selection)
        self.comparison_driver = None

        self.drs_zones = []
        self.drs_zones_xy = []
        self.toggle_drs_zones = True
        self.n_frames = 0
        self.min_speed = 0.0
        self.max_speed = 0.0

        self.th_min = 0
        self.th_max = 100

        self.br_min = 0
        self.br_max = 100

        self.g_min = 0
        self.g_max = 8

        # cached arrays for fast indexing/interpolation when telemetry loaded
        self._times = None   # numpy array of frame times
        self._xs = None      # numpy array of telemetry x
        self._ys = None      # numpy array of telemetry y
        self._speeds = None  # optional cached speeds

        # Playback / animation state for the chart
        self.play_time = 0.0          # current play time (seconds)
        self.play_start_t = 0.0       # first-frame timestamp (seconds)
        self.frame_index = 0          # current frame index (int)
        self.paused = True            # start paused by default
        self.playback_speed = 1.0     # 1.0 = realtime
        self.loading_telemetry = False

        # Rotation (degrees) to apply to the whole circuit around its centre
        self.circuit_rotation = circuit_rotation
        self._rot_rad = float(np.deg2rad(self.circuit_rotation)) if self.circuit_rotation else 0.0
        self._cos_rot = float(np.cos(self._rot_rad))
        self._sin_rot = float(np.sin(self._rot_rad))
        self.left_ui_margin = left_ui_margin
        self.right_ui_margin = right_ui_margin

        self.chart_active = False
        self.show_comparison_telemetry = True

        self.loaded_driver_code = None
        self.loaded_driver_segment = None

        # Store telemetry for multiple drivers (for comparison)
        self.loaded_telemetry = {}  # driver_code -> telemetry data
        self.comparison_drivers = []  # list of driver codes to compare

        # Track selected drivers from leaderboard clicks
        self.selected_drivers = []
        self._previous_selected = []

        # Legend + controls popup (same behavior as race replay)
        self.legend_comp = LegendComponent(x=max(12, self.left_ui_margin - 320))
        self.controls_popup_comp = ControlsPopupComponent(lines=[
            ("SPACE", "Pause/Resume"),
            ("← / →", "Jump back/forward"),
            ("↑ / ↓", "Speed +/-"),
            ("1-4", "Set speed: 0.5x / 1x / 2x / 4x"),
            ("R", "Restart"),
            ("D", "Toggle DRS Zones"),
            ("C", "Toggle/Cycle Comparison"),
            ("V", "Clear Comparison"),
            ("Click", "Select Primary Driver"),
            ("Shift+Click", "Select Multiple"),
            ("H", "Toggle Help Popup"),
            ("ESC", "Close Window"),
        ])
        self.controls_popup_comp.set_size(340, 250)
        self.controls_popup_comp.set_font_sizes(header_font_size=16, body_font_size=13)

        # Build the track layout from an example lap
        example_lap = None
        for res in self.data.get("results", []):
            code = res.get("code")
            if code:
                try:
                    driver_laps = session.laps.pick_drivers(code)
                    if driver_laps is not None and len(driver_laps) > 0:
                        fastest = driver_laps.pick_fastest()
                        if fastest is not None:
                            example_lap = fastest.get_telemetry()
                            break
                except Exception:
                    continue

        self.world_scale = 1.0
        self.tx = 0
        self.ty = 0

        if example_lap is not None:
            (self.plot_x_ref, self.plot_y_ref,
             self.x_inner, self.y_inner,
             self.x_outer, self.y_outer,
             self.x_min, self.x_max,
             self.y_min, self.y_max, self.drs_zones_xy) = build_track_from_example_lap(example_lap)

            ref_points = self._interpolate_points(self.plot_x_ref, self.plot_y_ref, interp_points=4000)
            self._ref_xs = np.array([p[0] for p in ref_points])
            self._ref_ys = np.array([p[1] for p in ref_points])

            diffs = np.sqrt(np.diff(self._ref_xs)**2 + np.diff(self._ref_ys)**2)
            self._ref_seg_len = diffs
            self._ref_cumdist = np.concatenate(([0.0], np.cumsum(diffs)))
            self._ref_total_length = float(self._ref_cumdist[-1]) if len(self._ref_cumdist) > 0 else 0.0

            self.world_inner_points = self._interpolate_points(self.x_inner, self.y_inner)
            self.world_outer_points = self._interpolate_points(self.x_outer, self.y_outer)

            self.screen_inner_points = [self.world_to_screen(x, y) for x, y in self.world_inner_points]
            self.screen_outer_points = [self.world_to_screen(x, y) for x, y in self.world_outer_points]
        else:
            # Set defaults if no example lap
            self.plot_x_ref = []
            self.plot_y_ref = []
            self.x_inner = []
            self.y_inner = []
            self.x_outer = []
            self.y_outer = []
            self.x_min = 0
            self.x_max = 1
            self.y_min = 0
            self.y_max = 1
            self.drs_zones_xy = []
            self._ref_xs = []
            self._ref_ys = []
            self._ref_cumdist = []
            self._ref_total_length = 0.0
            self.world_inner_points = []
            self.world_outer_points = []
            self.screen_inner_points = []
            self.screen_outer_points = []

        self.selected_driver = None

        arcade.set_background_color(arcade.color.BLACK)

        self.update_scaling(self.width, self.height)

        self.is_rewinding = False
        self.is_forwarding = False
        self.was_paused_before_hold = False

        # Auto-load the first driver to show track with driver position
        practice_results = self.data.get("results", [])
        if practice_results:
            first_driver = practice_results[0].get("code")
            if first_driver:
                # Check if telemetry is already in the data
                telemetry_store = self.data.get("telemetry") if isinstance(self.data, dict) else None
                if telemetry_store and first_driver in telemetry_store:
                    # Pre-loaded - select this driver
                    self.selected_drivers = [first_driver]
                    self._previous_selected = [first_driver]
                    self.load_driver_telemetry(first_driver, "best_lap")

    def update_scaling(self, screen_w, screen_h):
        """
        Recalculates the scale and translation to fit the track
        perfectly within the new screen dimensions while maintaining aspect ratio.
        """
        padding = 0.05
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2

        def _rotate_about_center(x, y):
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            return rx + world_cx, ry + world_cy

        rotated_points = []
        for x, y in self.world_inner_points:
            rotated_points.append(_rotate_about_center(x, y))
        for x, y in self.world_outer_points:
            rotated_points.append(_rotate_about_center(x, y))

        xs = [p[0] for p in rotated_points]
        ys = [p[1] for p in rotated_points]
        world_x_min = min(xs) if xs else self.x_min
        world_x_max = max(xs) if xs else self.x_max
        world_y_min = min(ys) if ys else self.y_min
        world_y_max = max(ys) if ys else self.y_max

        world_w = max(1.0, world_x_max - world_x_min)
        world_h = max(1.0, world_y_max - world_y_min)

        inner_w = max(1.0, screen_w - self.left_ui_margin - self.right_ui_margin)
        usable_w = inner_w * (1 - 2 * padding)
        usable_h = screen_h * (1 - 2 * padding)

        scale_x = usable_w / world_w
        scale_y = usable_h / world_h
        self.world_scale = min(scale_x, scale_y)

        screen_cx = self.left_ui_margin + inner_w / 2
        screen_cy = screen_h / 2

        self.tx = screen_cx - self.world_scale * world_cx
        self.ty = screen_cy - self.world_scale * world_cy

        self.screen_inner_points = [self.world_to_screen(x, y) for x, y in self.world_inner_points]
        self.screen_outer_points = [self.world_to_screen(x, y) for x, y in self.world_outer_points]

    def on_draw(self):
        self.clear()

        # Draw simple line chart if telemetry is loaded
        # loaded_telemetry is now a dict: {driver_code: telemetry_data}
        primary_telemetry = None
        if isinstance(self.loaded_telemetry, dict) and self.loaded_driver_code:
            primary_telemetry = self.loaded_telemetry.get(self.loaded_driver_code)

        if self.chart_active and primary_telemetry:
            frames = primary_telemetry.get("frames") if isinstance(primary_telemetry, dict) else None
            if frames:
                fastest_driver = self.data.get("results", [])[0] if isinstance(self.data.get("results", []), list) and len(self.data.get("results", [])) > 0 else None

                # Get all comparison drivers from selected_drivers (excluding the primary)
                current_selected = getattr(self, "selected_drivers", [])
                comparison_drivers = []
                if len(current_selected) > 1:
                    # All selected drivers except the first one are comparison drivers
                    comparison_drivers = [d for d in current_selected[1:] if d != self.loaded_driver_code]
                elif hasattr(self, "comparison_driver") and self.comparison_driver:
                    # Fallback to single comparison driver set by 'C' key
                    comparison_drivers = [self.comparison_driver]

                # Load telemetry for all comparison drivers
                comparison_telemetries = []
                if self.show_comparison_telemetry and comparison_drivers:
                    for comp_code in comparison_drivers:
                        # Skip the current driver to avoid comparing with oneself
                        if comp_code == self.loaded_driver_code:
                            continue
                        comp_data = self.data.get("telemetry", {}).get(comp_code)
                        if comp_data:
                            comp_tel = comp_data.get("best_lap", {}).get("frames", [])
                            if comp_tel:
                                comparison_telemetries.append({
                                    "code": comp_code,
                                    "frames": comp_tel,
                                    "color": self._get_driver_color(comp_code),
                                    "data": comp_data
                                })

                # right-hand area (to the right of leaderboard)
                area_left = self.leaderboard.x + getattr(self.leaderboard, "width", 240) + 40
                area_right = self.width - RIGHT_MARGIN
                area_top = self.height - TOP_MARGIN
                area_bottom = BOTTOM_MARGIN
                area_w = max(10, area_right - area_left)
                area_h = max(10, area_top - area_bottom)

                # Split vertically: top half = chart, bottom half = circuit map
                top_half_h = int(area_h * 0.5)
                chart_top = area_top
                chart_bottom = area_top - top_half_h
                chart_left = area_left
                chart_right = area_right
                chart_w = max(10, chart_right - chart_left)
                chart_h = max(10, chart_top - chart_bottom)

                # Divide chart area into 3 sub-areas
                M = 30
                VP = 5
                total_margin = 2 * M
                effective_h = max(0, chart_h - total_margin)

                speed_h = int(effective_h * 0.5)
                gear_h = int(effective_h * 0.25)
                ctrl_h = effective_h - speed_h - gear_h

                speed_top = chart_top
                speed_bottom = speed_top - speed_h
                gear_top = speed_bottom - M
                gear_bottom = gear_top - gear_h
                ctrl_top = gear_bottom - M
                ctrl_bottom = ctrl_top - ctrl_h

                map_top = ctrl_bottom - 8
                map_bottom = area_bottom
                map_left = area_left
                map_right = area_right
                map_w = max(10, map_right - map_left)
                map_h = max(10, map_top - map_bottom)

                # Backgrounds for the charts
                speed_bg = arcade.XYWH(chart_left + chart_w * 0.5, speed_bottom + speed_h * 0.5, chart_w, speed_h)
                gear_bg = arcade.XYWH(chart_left + chart_w * 0.5, gear_bottom + gear_h * 0.5, chart_w, gear_h)
                ctrl_bg = arcade.XYWH(chart_left + chart_w * 0.5, ctrl_bottom + ctrl_h * 0.5, chart_w, ctrl_h)

                arcade.draw_rect_filled(speed_bg, (40, 40, 40, 230))
                arcade.draw_rect_filled(gear_bg, (40, 40, 40, 230))
                arcade.draw_rect_filled(ctrl_bg, (40, 40, 40, 230))

                # Add Subtitles to the charts
                arcade.Text("Speed (km/h)", chart_left + 10, speed_top + 10, arcade.color.ANTI_FLASH_WHITE, 14).draw()
                arcade.Text("Gear", chart_left + 10, gear_top + 10, arcade.color.ANTI_FLASH_WHITE, 14).draw()
                arcade.Text("Throttle / Brake (%)", chart_left + 10, ctrl_top + 10, arcade.color.ANTI_FLASH_WHITE, 14).draw()

                # DRS key at right of the speed subtitle
                key_size = 12
                key_padding_right = 100
                key_y = speed_top + 10 + (key_size * 0.5)
                square_x = chart_right - key_padding_right - (key_size / 2)

                drs_key_rect = arcade.XYWH(square_x, key_y, key_size, key_size)
                arcade.draw_rect_filled(drs_key_rect, arcade.color.GREEN)
                arcade.Text(
                    "DRS active",
                    square_x + (key_size * 0.5) + 6,
                    key_y,
                    arcade.color.ANTI_FLASH_WHITE,
                    12,
                    anchor_y="center"
                ).draw()

                # Comparison driver keys - show all comparison drivers in a single row next to the speed subtitle
                if comparison_telemetries and self.show_comparison_telemetry:
                    comp_key_size = 12
                    comp_key_horizontal_spacing = 80  # Fixed spacing between keys
                    key_label_padding = 8   # Padding between square and text
                    text_width_est = 100    # Estimated width of "Comparison: XXX"

                    # Position keys exactly on the same line as "Speed (km/h)" subtitle
                    # Subtitle is at: chart_left + 10, speed_top + 10
                    row_y = speed_top + 10
                    row_start_x = chart_left + 160  # Fixed start position next to "Speed (km/h)" text

                    # Calculate max keys that can fit from row_start_x to the right margin
                    available_width = (self.width - RIGHT_MARGIN) - row_start_x
                    width_per_key = comp_key_size + key_label_padding + text_width_est + comp_key_horizontal_spacing
                    max_keys = max(1, available_width // width_per_key)

                    num_comparison = len(comparison_telemetries)

                    # Error message if too many drivers
                    if num_comparison > max_keys:
                        error_text = f"Too many comparison drivers ({num_comparison}). Maximum: {max_keys}"
                        arcade.Text(
                            error_text,
                            self.width // 2,
                            row_y,
                            arcade.color.RED_ORANGE,
                            14,
                            anchor_x="center",
                            anchor_y="center"
                        ).draw()
                        return

                    for idx, comp_tel_data in enumerate(comparison_telemetries):
                        # X position is fixed start + index * width per key
                        comp_key_x = row_start_x + idx * (comp_key_size + key_label_padding + text_width_est + comp_key_horizontal_spacing)
                        comp_square_x = comp_key_x

                        comp_driver_code = comp_tel_data["code"]
                        comp_color = comp_tel_data["color"]

                        # Draw colored square
                        comp_key_rect = arcade.XYWH(comp_square_x, row_y, comp_key_size, 3)
                        arcade.draw_rect_filled(comp_key_rect, comp_color)

                        # Draw text label
                        arcade.Text(
                            f"Comparison   {comp_driver_code}",
                            comp_square_x + comp_key_size + key_label_padding,
                            row_y,
                            arcade.color.ANTI_FLASH_WHITE,
                            12,
                            anchor_y="center"
                        ).draw()

                all_dists = [ self._pick_telemetry_value(f.get("telemetry", {}), "rel_dist") for f in frames ]
                all_dists = [d for d in all_dists if d is not None]
                if not all_dists:
                    return

                full_d_min, full_d_max = min(all_dists), max(all_dists)
                full_s_min, full_s_max = self.min_speed, self.max_speed

                if full_d_max == full_d_min:
                    full_d_max = full_d_min + 1.0
                if full_s_max == full_s_min:
                    full_s_max = full_s_min + 1.0

                self.frame_index = max(0, min(self.frame_index, len(frames) - 1))
                draw_pos = []
                draw_speeds = []
                draw_throttle = []
                draw_brake = []
                draw_gears = []

                # Initialize arrays for each comparison driver
                comparison_draw_data = []
                for comp_tel_data in comparison_telemetries:
                    comparison_draw_data.append({
                        "code": comp_tel_data["code"],
                        "color": comp_tel_data["color"],
                        "frames": comp_tel_data["frames"],
                        "pos": [],
                        "speeds": [],
                        "throttle": [],
                        "brake": [],
                        "gears": []
                    })

                # DRS zones
                drs_zones_to_show = []

                current_frame = frames[self.frame_index]
                current_tel = current_frame.get("telemetry", {}) if isinstance(current_frame.get("telemetry", {}), dict) else {}
                current_comparison_tel = {}
                current_dist = self._pick_telemetry_value(current_tel, "dist")

                for dz in self.drs_zones:
                    zone_start = dz.get("zone_start")
                    zone_end = dz.get("zone_end")
                    if zone_start is None or zone_end is None:
                        continue
                    if current_dist >= zone_start:
                        shade_end = min(zone_end, current_dist)
                        drs_zones_to_show.append({
                            "zone_start": zone_start,
                            "zone_end": shade_end
                        })

                for dz in drs_zones_to_show:
                    try:
                        zone_start = float(dz['zone_start'])
                        shade_end = float(dz['zone_end'])
                    except (ValueError, TypeError):
                        continue

                    all_abs_dists = [self._pick_telemetry_value(f.get("telemetry", {}), "dist") for f in frames]
                    all_abs_dists = [d for d in all_abs_dists if d is not None]
                    if not all_abs_dists:
                        continue

                    full_abs_d_min, full_abs_d_max = min(all_abs_dists), max(all_abs_dists)
                    if full_abs_d_max == full_abs_d_min:
                        continue

                    nx1 = (zone_start - full_abs_d_min) / (full_abs_d_max - full_abs_d_min)
                    nx2 = (shade_end - full_abs_d_min) / (full_abs_d_max - full_abs_d_min)
                    x1pix = chart_left + nx1 * chart_w
                    x2pix = chart_left + nx2 * chart_w
                    drs_rect = arcade.XYWH((x1pix + x2pix) * 0.5, speed_bottom + speed_h * 0.5, x2pix - x1pix, speed_h)
                    arcade.draw_rect_filled(drs_rect, (0, 100, 0, 100))

                # Collect values frame-by-frame
                for f_i, f in enumerate(frames[:self.frame_index + 1]):
                    tel = f.get("telemetry", {}) if isinstance(f.get("telemetry", {}), dict) else {}
                    d = self._pick_telemetry_value(tel, "rel_dist")
                    s = self._pick_telemetry_value(tel, "speed")
                    if d is None or s is None:
                        continue
                    th = self._pick_telemetry_value(tel, "throttle")
                    br = self._pick_telemetry_value(tel, "brake")
                    gr = self._pick_telemetry_value(tel, "gear")

                    draw_pos.append(float(d))
                    draw_speeds.append(float(s))
                    draw_throttle.append(float(th) if th is not None else None)
                    if isinstance(br, (bool, int)):
                        draw_brake.append(1.0 if br else 0.0)
                    else:
                        draw_brake.append(float(br) if br is not None else None)
                    draw_gears.append(int(gr) if gr is not None else None)

                    # Collect telemetry for all comparison drivers
                    for comp_data in comparison_draw_data:
                        comp_frames = comp_data["frames"]
                        if f_i < len(comp_frames):
                            frame_comp_tel = comp_frames[f_i]
                            if frame_comp_tel is not None:
                                frame_comp_tel = frame_comp_tel.get("telemetry", {}) if isinstance(frame_comp_tel.get("telemetry", {}), dict) else {}
                                c_d = self._pick_telemetry_value(frame_comp_tel, "rel_dist")
                                c_s = self._pick_telemetry_value(frame_comp_tel, "speed")
                                c_th = self._pick_telemetry_value(frame_comp_tel, "throttle")
                                c_br = self._pick_telemetry_value(frame_comp_tel, "brake")
                                c_gr = self._pick_telemetry_value(frame_comp_tel, "gear")
                                comp_data["pos"].append(float(c_d) if c_d is not None else None)
                                comp_data["speeds"].append(float(c_s) if c_s is not None else None)
                                comp_data["throttle"].append(float(c_th) if c_th is not None else None)
                                if isinstance(c_br, (bool, int)):
                                    comp_data["brake"].append(1.0 if c_br else 0.0)
                                else:
                                    comp_data["brake"].append(float(c_br) if c_br is not None else None)
                                comp_data["gears"].append(int(c_gr) if c_gr is not None else None)

                # Draw comparison drivers' speed lines
                if self.show_comparison_telemetry and comparison_draw_data:
                    for comp_data in comparison_draw_data:
                        draw_comparison_pos = comp_data["pos"]
                        draw_comparison_speeds = comp_data["speeds"]
                        comp_color = comp_data["color"]

                        if draw_comparison_pos and draw_comparison_speeds:
                            pts = []
                            for d, s in zip(draw_comparison_pos, draw_comparison_speeds):
                                if s is None:
                                    continue
                                nx = (d - full_d_min) / (full_d_max - full_d_min)
                                ny = (s - full_s_min) / (full_s_max - full_s_min)
                                xpix = chart_left + nx * chart_w
                                ypix = speed_bottom + VP + ny * (speed_h - 2 * VP)
                                pts.append((xpix, ypix))
                            try:
                                arcade.draw_line_strip(pts, comp_color, 2)
                                current_speed = draw_comparison_speeds[-1] if draw_comparison_speeds else 0
                                arcade.Text(f"{current_speed:.0f} km/h", pts[-1][0] + 10, pts[-1][1] - 15, comp_color, 12).draw()
                            except Exception as e:
                                print(f"Chart draw error (comparison speed for {comp_data['code']}):", e)

                # Draw speed
                if draw_pos and draw_speeds:
                    pts = []
                    for d, s in zip(draw_pos, draw_speeds):
                        nx = (d - full_d_min) / (full_d_max - full_d_min)
                        ny = (s - full_s_min) / (full_s_max - full_s_min)
                        xpix = chart_left + nx * chart_w
                        ypix = speed_bottom + VP + ny * (speed_h - 2 * VP)
                        pts.append((xpix, ypix))
                    try:
                        arcade.draw_line_strip(pts, arcade.color.ANTI_FLASH_WHITE, 2)
                        current_speed = draw_speeds[-1] if draw_speeds else 0
                        arcade.Text(f"{current_speed:.0f} km/h", pts[-1][0] + 10, pts[-1][1] + 5, arcade.color.ANTI_FLASH_WHITE, 12).draw()
                    except Exception as e:
                        print("Chart draw error (speed):", e)

                # Draw gears
                gear_pts = []
                for d, g in zip(draw_pos, draw_gears):
                    if g is None:
                        continue
                    nx = (d - full_d_min) / (full_d_max - full_d_min)
                    xpix = chart_left + nx * chart_w
                    gy = (g - self.g_min) / (self.g_max - self.g_min)
                    ypix = gear_bottom + VP + gy * (gear_h - 2 * VP)
                    gear_pts.append((xpix, ypix))

                # Draw comparison drivers' gear lines
                comparison_gear_lines = []
                if self.show_comparison_telemetry and comparison_draw_data:
                    for comp_data in comparison_draw_data:
                        draw_comparison_pos = comp_data["pos"]
                        draw_comparison_gears = comp_data["gears"]
                        comp_color = comp_data["color"]
                        comp_gear_pts = []

                        for d, g in zip(draw_comparison_pos, draw_comparison_gears):
                            if g is None:
                                continue
                            nx = (d - full_d_min) / (full_d_max - full_d_min)
                            xpix = chart_left + nx * chart_w
                            gy = (g - self.g_min) / (self.g_max - self.g_min)
                            ypix = gear_bottom + VP + gy * (gear_h - 2 * VP)
                            comp_gear_pts.append((xpix, ypix))

                        if comp_gear_pts:
                            comparison_gear_lines.append((comp_gear_pts, comp_color))

                try:
                    # Draw comparison gear lines first (so primary is on top)
                    for comp_gear_pts, comp_color in comparison_gear_lines:
                        arcade.draw_line_strip(comp_gear_pts, comp_color, 2)

                    if gear_pts:
                        arcade.draw_line_strip(gear_pts, arcade.color.LIGHT_GRAY, 2)

                        current_gear = draw_gears[-1] if draw_gears else 0
                        arcade.Text(f"Gear: {int(current_gear)}", gear_pts[-1][0] + 10, gear_pts[-1][1] + 5, arcade.color.LIGHT_GRAY, 12).draw()

                except Exception as e:
                    print("Chart draw error (gear):", e)

                th_min = self.th_min
                th_max = self.th_max
                br_min = self.br_min
                br_max = self.br_max

                throttle_pts = []
                brake_pts = []
                for d, th, br in zip(draw_pos, draw_throttle, draw_brake):
                    nx = (d - full_d_min) / (full_d_max - full_d_min)
                    xpix = chart_left + nx * chart_w
                    if th is not None:
                        ny = (th - th_min) / (th_max - th_min)
                        ypix = ctrl_bottom + VP + ny * (ctrl_h - 2 * VP)
                        throttle_pts.append((xpix, ypix))
                    if br is not None:
                        ny = (br - br_min) / (br_max - br_min)
                        ypix = ctrl_bottom + VP + ny * (ctrl_h - 2 * VP)
                        brake_pts.append((xpix, ypix))

                try:
                    if throttle_pts:
                        arcade.draw_line_strip(throttle_pts, arcade.color.GREEN, 2)
                    if brake_pts:
                        arcade.draw_line_strip(brake_pts, arcade.color.RED, 2)
                except Exception as e:
                    print("Chart draw error (controls):", e)

                # Draw practice lap time component
                self.qualifying_lap_time_comp.x = map_left
                self.qualifying_lap_time_comp.y = map_top
                self.qualifying_lap_time_comp.fastest_driver = fastest_driver
                self.qualifying_lap_time_comp.fastest_driver_sector_times = (
                    comparison_telemetries[0].get("data", {}).get("best_lap", {}).get("sector_times", {})
                    if comparison_telemetries and self.show_comparison_telemetry and fastest_driver
                    else None
                )
                self.qualifying_lap_time_comp.draw(self)

                y_offset = map_top - 48
                arcade.Text(f"Playback Speed: {self.playback_speed:.1f}x", map_left + 10, y_offset - 130, arcade.color.ANTI_FLASH_WHITE, 14).draw()

                # Draw circuit map in bottom half
                if getattr(self, "x_min", None) is not None and getattr(self, "x_max", None) is not None:
                    world_x_min = float(self.x_min)
                    world_x_max = float(self.x_max)
                    world_y_min = float(self.y_min)
                    world_y_max = float(self.y_max)

                    world_w = max(1.0, world_x_max - world_x_min)
                    world_h = max(1.0, world_y_max - world_y_min)

                    pad = 0.06
                    usable_w = map_w * (1 - 2 * pad)
                    usable_h = map_h * (1 - 2 * pad)

                    scale_x = usable_w / world_w
                    scale_y = usable_h / world_h
                    world_scale = min(scale_x, scale_y)

                    world_cx = (world_x_min + world_x_max) / 2
                    world_cy = (world_y_min + world_y_max) / 2

                    screen_cx = map_left + map_w / 2
                    screen_cy = map_bottom + map_h / 2

                    tx = screen_cx - world_scale * world_cx
                    ty = screen_cy - world_scale * world_cy

                    def world_to_map(x, y):
                        sx = world_scale * x + tx
                        sy = world_scale * y + ty
                        return sx, sy

                    inner_world = getattr(self, "world_inner_points", None) or list(zip(self.x_inner, self.y_inner))
                    outer_world = getattr(self, "world_outer_points", None) or list(zip(self.x_outer, self.y_outer))

                    self.inner_pts = [world_to_map(x, y) for x, y in inner_world if x is not None and y is not None]
                    self.outer_pts = [world_to_map(x, y) for x, y in outer_world if x is not None and y is not None]
                    try:
                        if len(self.inner_pts) > 1:
                            arcade.draw_line_strip(self.inner_pts, arcade.color.GRAY, 2)
                        if len(self.outer_pts) > 1:
                            arcade.draw_line_strip(self.outer_pts, arcade.color.GRAY, 2)
                        draw_finish_line(self, 'Q')
                    except Exception as e:
                        print("Circuit draw error:", e)

                    # Draw all comparison drivers' positions
                    if self.show_comparison_telemetry and comparison_telemetries:
                        for comp_tel_data in comparison_telemetries:
                            comp_frames = comp_tel_data["frames"]
                            comp_color = comp_tel_data["color"]
                            if self.frame_index < len(comp_frames):
                                comp_frame = comp_frames[self.frame_index]
                                comp_tel = comp_frame.get("telemetry", {}) if isinstance(comp_frame.get("telemetry", {}), dict) else {}
                                c_px = comp_tel.get("x")
                                c_py = comp_tel.get("y")
                                if c_px is not None and c_py is not None:
                                    c_sx, c_sy = world_to_map(c_px, c_py)
                                    arcade.draw_circle_filled(c_sx, c_sy, 6, comp_color)

                    # Draw DRS zones on track map
                    if self.drs_zones_xy and self.toggle_drs_zones:
                        drs_color = (0, 255, 0)
                        original_length = len(self.x_inner)
                        interpolated_length = len(inner_world)

                        for dz in self.drs_zones_xy:
                            orig_start_idx = dz["start"]["index"]
                            orig_end_idx = dz["end"]["index"]

                            if orig_start_idx is None or orig_end_idx is None:
                                continue
                            try:
                                interp_start_idx = int((orig_start_idx / original_length) * interpolated_length)
                                interp_end_idx = int((orig_end_idx / original_length) * interpolated_length)

                                interp_start_idx = max(0, min(interp_start_idx, interpolated_length - 1))
                                interp_end_idx = max(0, min(interp_end_idx, interpolated_length - 1))

                                if interp_start_idx < interp_end_idx:
                                    outer_zone = [world_to_map(x, y) for x, y in outer_world[interp_start_idx:interp_end_idx+1]
                                                  if x is not None and y is not None]
                                    if len(outer_zone) > 1:
                                        arcade.draw_line_strip(outer_zone, drs_color, 3)

                            except Exception as e:
                                print(f"DRS zone draw error: {e}")

                    # Draw current driver's position marker
                    current_frame = frames[self.frame_index]
                    tel = current_frame.get("telemetry", {}) if isinstance(current_frame.get("telemetry", {}), dict) else {}
                    px = tel.get("x")
                    py = tel.get("y")
                    sx, sy = world_to_map(px, py)
                    drv_color = (255, 255, 255)
                    if getattr(self, "loaded_driver_code", None):
                        for r in self.data.get("results", []):
                            if r.get("code") == self.loaded_driver_code and r.get("color"):
                                drv_color = tuple(r.get("color"))
                                break
                    arcade.draw_circle_filled(sx, sy, 6, drv_color)

                    # Overlay current gear near the position marker
                    cur_gear = tel.get("gear") or tel.get("nGear") or tel.get("Gear")
                    if cur_gear is None:
                        cur_gear = draw_gears[-1] if draw_gears else None
                    arcade.Text(self.loaded_driver_code or "", sx + 10, sy + 4, arcade.color.WHITE, 12).draw()
                    if cur_gear is not None:
                        arcade.Text(f"G:{int(cur_gear)}", sx + 10, sy - 10, arcade.color.LIGHT_GRAY, 12).draw()

        else:
            # Add "click a driver to view their practice lap" text
            info_text = "Click a driver on the left to load their practice lap telemetry."
            arcade.Text(
                info_text,
                self.width / 2, self.height / 2,
                arcade.color.LIGHT_GRAY, 18,
                anchor_x="center", anchor_y="center"
            ).draw()

        self.leaderboard.draw(self)

        # Controls Legend - Bottom Left
        self.legend_comp.x = max(12, self.left_ui_margin - 320) if hasattr(self, "left_ui_margin") else 20
        self.legend_comp.draw(self)

        # Show race controls only when telemetry is loaded
        if self.chart_active and self.loaded_driver_code and self.frame_index < self.n_frames:
            self.race_controls_comp.draw(self)
        # Controls popup (Help)
        self.controls_popup_comp.draw(self)

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Pass mouse motion events to UI components."""
        self.race_controls_comp.on_mouse_motion(self, x, y, dx, dy)

    def on_resize(self, width: int, height: int):
        """Handle the window being resized."""
        super().on_resize(width, height)
        self.update_scaling(width, height)
        self.race_controls_comp.on_resize(self)

    def _interpolate_points(self, xs, ys, interp_points=2000):
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def world_to_screen(self, x, y):
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2

        if self._rot_rad:
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            x, y = rx + world_cx, ry + world_cy

        sx = self.world_scale * x + self.tx
        sy = self.world_scale * y + self.ty
        return sx, sy

    def _pick_telemetry_value(self, tel: dict, *keys):
        """Return the first value for keys that exists in tel and is not None."""
        if not isinstance(tel, dict):
            return None
        for k in keys:
            if k in tel and tel[k] is not None:
                return tel[k]
        return None

    def _get_driver_color(self, driver_code: str):
        """Get the color for a driver from the results data."""
        results = self.data.get("results", [])
        for driver in results:
            if driver.get("code") == driver_code:
                color = driver.get("color")
                if color:
                    return color
        # Default to yellow if not found
        return arcade.color.YELLOW

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        if self.controls_popup_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.legend_comp.on_mouse_press(self, x, y, button, modifiers):
            return

        # Let the leaderboard handle the click (select drivers)
        self.leaderboard.on_mouse_press(self, x, y, button, modifiers)


        # Only allow race controls interaction if lap is not complete
        if not self.is_lap_complete():
            self.race_controls_comp.on_mouse_press(self, x, y, button, modifiers)

    def is_lap_complete(self):
        """Check if the current lap has finished playing."""
        return self.chart_active and self.n_frames > 0 and self.frame_index >= self.n_frames - 1

    def on_key_press(self, symbol: int, modifiers: int):
        # Allow ESC to close window at any time
        if symbol == arcade.key.ESCAPE:
            arcade.close_window()
            return
        # Allow restart (R), comparison toggle (C), and DRS toggle (D) even when lap is complete
        if symbol == arcade.key.R:
            self.frame_index = 0
            self.play_time = self.play_start_t
            self.playback_speed = 1.0
            self.paused = True
            self.race_controls_comp.flash_button('rewind')
            return
        elif symbol == arcade.key.C:
            # Toggle comparison on/off or cycle to next driver
            practice_results = self.data.get("results", [])
            if not practice_results:
                return
            codes = [r.get('code') for r in practice_results if r.get('code')]
            if not codes:
                return

            current_comp = getattr(self, "comparison_driver", None)
            primary = self.loaded_driver_code

            # Remove the current driver from the list of possible comparisons
            comparison_codes = [c for c in codes if c != primary]

            if not comparison_codes:
                # Only one driver, can't compare
                return

            # If no comparison driver, start from the first available
            if current_comp is None:
                new_comp = comparison_codes[0]
            else:
                # Find current comparison driver and move to next
                if current_comp not in comparison_codes:
                    new_comp = comparison_codes[0]
                else:
                    idx = comparison_codes.index(current_comp)
                    idx = (idx + 1) % len(comparison_codes)
                    # If we've cycled back to the start, turn off
                    if idx == 0:
                        self.comparison_driver = None
                        self.show_comparison_telemetry = False
                        return
                    new_comp = comparison_codes[idx]

            # Load comparison driver telemetry if not loaded
            if new_comp not in self.loaded_telemetry:
                self.load_driver_telemetry(new_comp, "best_lap")

            self.comparison_driver = new_comp
            self.show_comparison_telemetry = True
            return
        elif symbol == arcade.key.V:
            # Clear comparison driver
            self.comparison_driver = None
            self.show_comparison_telemetry = False
            return
        elif symbol == arcade.key.D:
            self.toggle_drs_zones = not self.toggle_drs_zones
            return
        elif symbol == arcade.key.H:
            margin_x = 20
            margin_y = 20
            left_pos = float(margin_x)
            top_pos = float(margin_y + self.controls_popup_comp.height)
            if self.controls_popup_comp.visible:
                self.controls_popup_comp.hide()
            else:
                self.controls_popup_comp.show_over(left_pos, top_pos)
            return

        # Disable other controls when lap is complete
        if self.is_lap_complete():
            return

        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
            self.race_controls_comp.flash_button('play_pause')
        elif symbol == arcade.key.RIGHT:
            self.was_paused_before_hold = self.paused
            self.is_forwarding = True
            self.paused = True
        elif symbol == arcade.key.LEFT:
            self.was_paused_before_hold = self.paused
            self.is_rewinding = True
            self.paused = True
        elif symbol == arcade.key.UP:
            if self.playback_speed < 1024.0:
                self.playback_speed *= 2.0
                self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.DOWN:
            self.playback_speed = max(0.1, self.playback_speed / 2.0)
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_1:
            self.playback_speed = 0.5
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_2:
            self.playback_speed = 1.0
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_3:
            self.playback_speed = 2.0
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.KEY_4:
            self.playback_speed = 4.0
            self.race_controls_comp.flash_button('speed_increase')

    def load_driver_telemetry(self, driver_code: str, segment_name: str = "best_lap"):
        # Already loaded?
        if driver_code in self.loaded_telemetry:
            # Use first selected driver's telemetry for primary display
            current_selected = getattr(self, "selected_drivers", [])
            if current_selected and current_selected[0] == driver_code:
                self._update_primary_telemetry(driver_code)
            return

        self.qualifying_lap_time_comp.reset()

        # Try to find telemetry already provided in the window's data object
        telemetry_store = self.data.get("telemetry") if isinstance(self.data, dict) else None
        if telemetry_store:
            driver_block = telemetry_store.get(driver_code) if isinstance(telemetry_store, dict) else None
            if driver_block:
                seg = driver_block.get(segment_name)
                if seg and isinstance(seg, dict) and seg.get("frames"):
                    # Store telemetry for this driver
                    self.loaded_telemetry[driver_code] = seg
                    self.chart_active = True
                    # Use first selected driver's telemetry for primary display
                    current_selected = getattr(self, "selected_drivers", [])
                    if current_selected and current_selected[0] == driver_code:
                        self._update_primary_telemetry(driver_code)
                    return

        # Otherwise proceed with background loading
        self.loading_telemetry = True
        self.loading_message = f"Loading telemetry {driver_code}..."

        threading.Thread(
            target=self._bg_load_telemetry,
            args=(driver_code, segment_name),
            daemon=True
        ).start()

    def _update_primary_telemetry(self, driver_code: str):
        """Update primary telemetry references for the given driver."""
        seg = self.loaded_telemetry.get(driver_code)
        if not seg:
            return
        self.loaded_driver_code = driver_code
        self.loaded_driver_segment = "best_lap"
        frames = seg.get("frames", [])
        drs_zones = seg.get("drs_zones", [])
        times = [float(f.get("t")) for f in frames if f.get("t") is not None]
        xs = [ (f.get("telemetry") or {}).get("x") for f in frames ]
        ys = [ (f.get("telemetry") or {}).get("y") for f in frames ]
        speeds = [ (f.get("telemetry") or {}).get("speed") for f in frames ]
        self._times = np.array(times) if times else None
        self._xs = np.array(xs) if xs else None
        self._ys = np.array(ys) if ys else None
        self._speeds = np.array([float(s) for s in speeds if s is not None]) if speeds else None
        self.frames = frames
        self.drs_zones = drs_zones
        self.n_frames = len(frames)
        if self._speeds is not None and self._speeds.size > 0:
            self.min_speed = float(np.min(self._speeds))
            self.max_speed = float(np.max(self._speeds))
        else:
            self.min_speed = 0.0
            self.max_speed = 0.0
        if frames:
            start_t = frames[0].get("t", 0.0)
            self.play_start_t = float(start_t)
            self.play_time = float(start_t)
            self.frame_index = 0
            self.paused = False
            self.playback_speed = 1.0
        self.loading_telemetry = False
        self.loading_message = ""

    def _bg_load_telemetry(self, driver_code: str, segment_name: str):
        """Background loader that fetches telemetry if not present locally."""
        try:
            telemetry = None
            telemetry_store = self.data.get("telemetry") if isinstance(self.data, dict) else None
            if telemetry_store:
                driver_block = telemetry_store.get(driver_code) if isinstance(telemetry_store, dict) else None
                if driver_block:
                    seg = driver_block.get(segment_name)
                    if seg and isinstance(seg, dict) and seg.get("frames"):
                        telemetry = seg

            if telemetry is None and getattr(self, "session", None) is not None:
                telemetry_by_driver = get_driver_practice_telemetry(self.session, driver_code)
                driver_block = telemetry_by_driver.get(driver_code)
                telemetry = driver_block.get("best_lap") if driver_block else None

            if telemetry is None:
                pass  # Just don't add to loaded_telemetry
            else:
                # Store telemetry for this driver
                self.loaded_telemetry[driver_code] = telemetry
                self.chart_active = True

                # Update primary telemetry if this is the first selected driver
                current_selected = getattr(self, "selected_drivers", [])
                if current_selected and current_selected[0] == driver_code:
                    self._update_primary_telemetry(driver_code)
        except Exception as e:
            print("Telemetry load failed:", e)
        finally:
            self.loading_telemetry = False
            self.loading_message = ""

    def on_update(self, delta_time: float):
        # Check for driver selection changes and load telemetry for all selected drivers
        current_selected = getattr(self, "selected_drivers", [])
        # Only load when selection actually changes
        if current_selected != getattr(self, "_previous_selected", []):
            self._previous_selected = list(current_selected)
            # Load telemetry for all newly selected drivers
            for driver_code in current_selected:
                if driver_code not in self.loaded_telemetry:
                    self.load_driver_telemetry(driver_code, "best_lap")

        # Update loaded telemetry reference for first selected driver
        if current_selected and len(current_selected) > 0:
            first_driver = current_selected[0]
            if first_driver in self.loaded_telemetry:
                self.loaded_driver_code = first_driver

            # Handle comparison driver selection (when multiple drivers selected)
            if len(current_selected) >= 2:
                # Second driver becomes comparison driver
                comparison_candidate = current_selected[1]
                if comparison_candidate != self.loaded_driver_code:
                    if comparison_candidate not in self.loaded_telemetry:
                        self.load_driver_telemetry(comparison_candidate, "best_lap")
                    self.comparison_driver = comparison_candidate
                    self.show_comparison_telemetry = True
            elif len(current_selected) == 1:
                # Only one driver selected, turn off comparison
                # But only if we haven't manually set a comparison with 'C' key
                # Check if current comparison is still valid
                if hasattr(self, 'comparison_driver') and self.comparison_driver:
                    # Keep the comparison if it was manually set
                    pass
                else:
                    self.comparison_driver = None
                    self.show_comparison_telemetry = False

        if not self.loaded_telemetry or len(self.loaded_telemetry) == 0:
            return
        self.race_controls_comp.on_update(delta_time)
        self.qualifying_lap_time_comp.on_update(delta_time)

        seek_speed = 3.0 * max(1.0, self.playback_speed)

        if self.is_rewinding:
            self.play_time -= delta_time * seek_speed
            self.race_controls_comp.flash_button('rewind')
        elif self.is_forwarding:
            self.play_time += delta_time * seek_speed
            self.race_controls_comp.flash_button('forward')
        else:
            if self.paused:
                return
            self.play_time += delta_time * self.playback_speed

        if self._times is not None and len(self._times) > 0:
            clamped = min(max(self.play_time, float(self._times[0])), float(self._times[-1]))
            idx = int(np.searchsorted(self._times, clamped, side="right") - 1)
            self.frame_index = max(0, min(idx, len(self._times) - 1))

            if self.frame_index >= self.n_frames - 1:
                self.paused = True
        else:
            self.frame_index = int(min(self.n_frames - 1, self.frame_index + int(round(delta_time * FPS * self.playback_speed))))

            if self.frame_index >= self.n_frames - 1:
                self.paused = True

    def on_key_release(self, symbol: int, modifiers: int):
        if symbol == arcade.key.RIGHT:
            self.is_forwarding = False
            self.paused = self.was_paused_before_hold
        elif symbol == arcade.key.LEFT:
            self.is_rewinding = False
            self.paused = self.was_paused_before_hold

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int):
        if self.is_forwarding or self.is_rewinding:
            self.is_forwarding = False
            self.is_rewinding = False
            self.paused = self.was_paused_before_hold


def run_practice_replay(session, data, title="Practice Results", ready_file=None):
    window = PracticeReplay(session=session, data=data, title=title)
    if ready_file:
        try:
            with open(ready_file, 'w') as f:
                f.write('ready')
        except Exception:
            pass
    arcade.run()
