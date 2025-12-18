import arcade
import threading
import time
import numpy as np
from src.ui_components import build_track_from_example_lap, LapTimeLeaderboardComponent, QualifyingSegmentSelectorComponent, RaceControlsComponent
from src.ui_components import build_track_from_example_lap, LapTimeLeaderboardComponent, QualifyingSegmentSelectorComponent, LegendComponent
from src.f1_data import get_driver_quali_telemetry
from src.f1_data import FPS
from src.lib.time import format_time

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
SCREEN_TITLE = "F1 Qualifying Telemetry"

H_ROW = 38
HEADER_H = 56
LEFT_MARGIN = 40
RIGHT_MARGIN = 40
TOP_MARGIN = 40
BOTTOM_MARGIN = 40

class QualifyingReplay(arcade.Window):
    def __init__(self, session, data, circuit_rotation=0, left_ui_margin=340, right_ui_margin=0, title="Qualifying Results"):
        super().__init__(width=SCREEN_WIDTH, height=SCREEN_HEIGHT, title=title, resizable=True)
        self.session = session
        self.data = data
        self.leaderboard = LapTimeLeaderboardComponent(
            x=LEFT_MARGIN,
        )
        self.race_controls_comp = RaceControlsComponent(
            center_x= self.width // 2 + 100,
            center_y= 40
        )
        self.leaderboard.set_entries(self.data.get("results", []))
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

        # Legend component for control icons
        self.legend_comp = LegendComponent()

        # Build the track layout from an example lap

        example_lap = None
        for res in self.data['results']:
            if res['Q3'] is not None:
                example_lap = self.session.laps.pick_drivers(res['code']).pick_fastest()
                break
            elif res['Q2'] is not None:
                example_lap = self.session.laps.pick_drivers(res['code']).pick_fastest()
                break
            elif res['Q1'] is not None:
                example_lap = self.session.laps.pick_drivers(res['code']).pick_fastest()
                break

        self.world_scale = 1.0
        self.tx = 0
        self.ty = 0

        (self.plot_x_ref, self.plot_y_ref,
         self.x_inner, self.y_inner,
         self.x_outer, self.y_outer,
         self.x_min, self.x_max,
         self.y_min, self.y_max, self.drs_zones_xy) = build_track_from_example_lap(example_lap.get_telemetry())
         
        ref_points = self._interpolate_points(self.plot_x_ref, self.plot_y_ref, interp_points=4000)
        self._ref_xs = np.array([p[0] for p in ref_points])
        self._ref_ys = np.array([p[1] for p in ref_points])

        # cumulative distances along the reference polyline (metres)
        diffs = np.sqrt(np.diff(self._ref_xs)**2 + np.diff(self._ref_ys)**2)
        self._ref_seg_len = diffs
        self._ref_cumdist = np.concatenate(([0.0], np.cumsum(diffs)))
        self._ref_total_length = float(self._ref_cumdist[-1]) if len(self._ref_cumdist) > 0 else 0.0

        # Pre-calculate interpolated world points ONCE (optimization)
        self.world_inner_points = self._interpolate_points(self.x_inner, self.y_inner)
        self.world_outer_points = self._interpolate_points(self.x_outer, self.y_outer)

        # These will hold the actual screen coordinates to draw
        self.screen_inner_points = [self.world_to_screen(x, y) for x, y in self.world_inner_points]
        self.screen_outer_points = [self.world_to_screen(x, y) for x, y in self.world_outer_points]

        # Qualifying segment selector modal
        self.selected_driver = None
        self.qualifying_segment_selector_modal = QualifyingSegmentSelectorComponent()

        arcade.set_background_color(arcade.color.BLACK)

        self.update_scaling(self.width, self.height)

    def update_scaling(self, screen_w, screen_h):
        """
        Recalculates the scale and translation to fit the track 
        perfectly within the new screen dimensions while maintaining aspect ratio.
        """
        padding = 0.05
        # If a rotation is applied, we must compute the rotated bounds
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2

        def _rotate_about_center(x, y):
            # Translate to centre, rotate, translate back
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            return rx + world_cx, ry + world_cy

        # Build rotated extents from inner/outer world points
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
        
        # Reserve left/right UI margins before applying padding so the track
        # never overlaps side UI elements (leaderboard, telemetry, legends).
        inner_w = max(1.0, screen_w - self.left_ui_margin - self.right_ui_margin)
        usable_w = inner_w * (1 - 2 * padding)
        usable_h = screen_h * (1 - 2 * padding)

        # Calculate scale to fit whichever dimension is the limiting factor
        scale_x = usable_w / world_w
        scale_y = usable_h / world_h
        self.world_scale = min(scale_x, scale_y)

        # Center the world in the screen (rotation done about original centre)
        # world_cx/world_cy are unchanged by rotation about centre
        # Center within the available inner area (left_ui_margin .. screen_w - right_ui_margin)
        screen_cx = self.left_ui_margin + inner_w / 2
        screen_cy = screen_h / 2

        self.tx = screen_cx - self.world_scale * world_cx
        self.ty = screen_cy - self.world_scale * world_cy

        # Update the polyline screen coordinates based on new scale
        self.screen_inner_points = [self.world_to_screen(x, y) for x, y in self.world_inner_points]
        self.screen_outer_points = [self.world_to_screen(x, y) for x, y in self.world_outer_points]

    def on_draw(self):
        self.clear()

        # Draw simple line chart if telemetry is loaded
        if self.chart_active and self.loaded_telemetry:
            frames = self.loaded_telemetry.get("frames") if isinstance(self.loaded_telemetry, dict) else None
            if frames:
                fastest_driver = self.data.get("results", [])[0] if isinstance(self.data.get("results", []), list) and len(self.data.get("results", [])) > 0 else None
                # Get comparison telemetry if available
                comparison_telemetry = self.data.get("telemetry", {}).get(fastest_driver.get("code")).get("Q3").get("frames", []) if self.show_comparison_telemetry and fastest_driver and ((fastest_driver.get("code") != self.loaded_driver_code) or (fastest_driver.get("code") == self.loaded_driver_code and self.loaded_driver_segment != "Q3")) else None

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

                # Divide chart area into 3 sub-areas:
                # - Top 50% of the chart area: Speed
                # - Next 25%: Gears
                # - Bottom 25%: Brake + Throttle

                M = 30 # margin between charts
                VP = 5 # vertical padding between charts
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

                # DRS key at right of the speed subtitle (green square + label)
                key_size = 12
                key_padding_right = 100
                # Align vertically with the subtitle (use same y offset, center the square)
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

                # Comparison driver key (yellow line + label)

                if comparison_telemetry:
                    comp_key_size = 12
                    comp_key_padding_right = 350
                    comp_key_y = speed_top + 10 + (comp_key_size * 0.5)
                    comp_square_x = chart_right - comp_key_padding_right - (comp_key_size / 2)

                    comp_driver_code = fastest_driver.get("code") if fastest_driver else "N/A"

                    comp_key_rect = arcade.XYWH(comp_square_x, comp_key_y, comp_key_size, 3)
                    arcade.draw_rect_filled(comp_key_rect, arcade.color.YELLOW)
                    arcade.Text(
                        f"Comparison Driver: {comp_driver_code} - Q3",
                        comp_square_x + (comp_key_size * 0.5) + 6,
                        comp_key_y,
                        arcade.color.ANTI_FLASH_WHITE,
                        12,
                        anchor_y="center"
                    ).draw()

                # compute global ranges from all frames (use distance for x-axis) - Should be max of 1.0 rel_dist, but just in case

                all_dists = [ self._pick_telemetry_value(f.get("telemetry", {}), "rel_dist") for f in frames ]
                
                # filter out None
                all_dists = [d for d in all_dists if d is not None]
                if not all_dists:
                    return

                full_d_min, full_d_max = min(all_dists), max(all_dists)
                full_s_min, full_s_max = self.min_speed, self.max_speed

                # avoid zero-range
                if full_d_max == full_d_min:
                    full_d_max = full_d_min + 1.0
                if full_s_max == full_s_min:
                    full_s_max = full_s_min + 1.0

                # Prepare arrays for drawing up to current frame index (animate)
                self.frame_index = max(0, min(self.frame_index, len(frames) - 1))
                draw_pos = []         # along-track distance used as x-axis
                draw_speeds = []
                draw_throttle = []
                draw_brake = []
                draw_gears = []
                
                draw_comparison_pos = []
                draw_comparison_speeds = []
                draw_comparison_throttle = []
                draw_comparison_brake = []
                draw_comparison_gears = []
                # The speed chart background will have sections of it shaded green to indicate where DRS was active

                # find the drs zones for this lap that the driver has already passed.
                # If they have partially passed a zone, shade up to their current distance only.

                drs_zones_to_show = []

                current_frame = frames[self.frame_index]
                current_tel = current_frame.get("telemetry", {}) if isinstance(current_frame.get("telemetry", {}), dict) else {}
                current_comparison_tel = comparison_telemetry[self.frame_index].get("telemetry") if comparison_telemetry and self.frame_index < len(comparison_telemetry) else {}
                current_dist = self._pick_telemetry_value(current_tel, "dist")
                
                for dz in self.drs_zones:
                    zone_start = dz.get("zone_start")
                    zone_end = dz.get("zone_end")
                    if zone_start is None or zone_end is None:
                        continue
                    if current_dist >= zone_start:
                        # driver has passed at least the start of this zone
                        shade_end = min(zone_end, current_dist)
                        drs_zones_to_show.append({
                            "zone_start": zone_start,
                            "zone_end": shade_end
                        })

                for dz in drs_zones_to_show:
                    # Convert to float to handle string values
                    try:
                        zone_start = float(dz['zone_start'])
                        shade_end = float(dz['zone_end'])
                    except (ValueError, TypeError):
                        continue  # Skip invalid zones
                    
                    # Get the full distance range from all frames
                    all_abs_dists = [self._pick_telemetry_value(f.get("telemetry", {}), "dist") for f in frames]
                    all_abs_dists = [d for d in all_abs_dists if d is not None]
                    if not all_abs_dists:
                        continue
                    
                    full_abs_d_min, full_abs_d_max = min(all_abs_dists), max(all_abs_dists)
                    if full_abs_d_max == full_abs_d_min:
                        continue
                    
                    # map to screen coords using absolute distances
                    nx1 = (zone_start - full_abs_d_min) / (full_abs_d_max - full_abs_d_min)
                    nx2 = (shade_end - full_abs_d_min) / (full_abs_d_max - full_abs_d_min)
                    x1pix = chart_left + nx1 * chart_w
                    x2pix = chart_left + nx2 * chart_w
                    drs_rect = arcade.XYWH((x1pix + x2pix) * 0.5, speed_bottom + speed_h * 0.5, x2pix - x1pix, speed_h)
                    arcade.draw_rect_filled(drs_rect, (0, 100, 0, 100)) # semi-transparent green

                # Collect values frame-by-frame (safe for mixed datasets)
                for f_i, f in enumerate(frames[:self.frame_index + 1]):
                    tel = f.get("telemetry", {}) if isinstance(f.get("telemetry", {}), dict) else {}
                    d = self._pick_telemetry_value(tel, "rel_dist")
                    s = self._pick_telemetry_value(tel, "speed")
                    if d is None or s is None:
                        continue
                    # throttle
                    th = self._pick_telemetry_value(tel, "throttle")
                    # brake
                    br = self._pick_telemetry_value(tel, "brake")
                    # gear
                    gr = self._pick_telemetry_value(tel, "gear")

                    draw_pos.append(float(d))
                    draw_speeds.append(float(s))
                    draw_throttle.append(float(th) if th is not None else None)
                    if isinstance(br, (bool, int)):
                        draw_brake.append(1.0 if br else 0.0)
                    else:
                        draw_brake.append(float(br) if br is not None else None)
                    draw_gears.append(int(gr) if gr is not None else None)

                    # Comparison Driver telemetry

                    if comparison_telemetry and f_i < len(comparison_telemetry):

                        frame_comparison_telemetry = comparison_telemetry[f_i]

                        if frame_comparison_telemetry is not None:
                            frame_comparison_telemetry = frame_comparison_telemetry.get("telemetry", {}) if isinstance(frame_comparison_telemetry.get("telemetry", {}), dict) else {}
                            c_d = self._pick_telemetry_value(frame_comparison_telemetry, "rel_dist")
                            c_s= self._pick_telemetry_value(frame_comparison_telemetry, "speed")
                            c_th = self._pick_telemetry_value(frame_comparison_telemetry, "throttle")
                            c_br = self._pick_telemetry_value(frame_comparison_telemetry, "brake")
                            c_gr = self._pick_telemetry_value(frame_comparison_telemetry, "gear")
                            draw_comparison_pos.append(float(c_d) if c_d is not None else None)
                            draw_comparison_speeds.append(float(c_s) if c_s is not None else None)
                            draw_comparison_throttle.append(float(c_th) if c_th is not None else None)
                            if isinstance(c_br, (bool, int)):
                                draw_comparison_brake.append(1.0 if c_br else 0.0)
                            else:
                                draw_comparison_brake.append(float(c_br) if c_br is not None else None)
                            draw_comparison_gears.append(int(c_gr) if c_gr is not None else None)

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
                        arcade.draw_line_strip(pts, arcade.color.YELLOW, 2)
                        # Show current speed in km/h
                        current_speed = draw_comparison_speeds[-1] if draw_comparison_speeds else 0
                        arcade.Text(f"{current_speed:.0f} km/h", pts[-1][0] + 10, pts[-1][1] - 15, arcade.color.YELLOW, 12).draw()
                    except Exception as e:
                        print("Chart draw error (comparison speed):", e)

                # Draw speed in the top sub-area (x-axis = distance)
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
                        # Show current speed in km/h
                        current_speed = draw_speeds[-1] if draw_speeds else 0
                        arcade.Text(f"{current_speed:.0f} km/h", pts[-1][0] + 10, pts[-1][1] + 5, arcade.color.ANTI_FLASH_WHITE, 12).draw()
                    except Exception as e:
                        print("Chart draw error (speed):", e)

                # Draw gears in the middle sub-area
                gear_pts = []
                comparison_gear_pts = []
                for d, g in zip(draw_pos, draw_gears):
                    if g is None:
                        continue
                    nx = (d - full_d_min) / (full_d_max - full_d_min)
                    xpix = chart_left + nx * chart_w
                    # map gear to vertical within gear box (higher gears near top of gear area)
                    gy = (g - self.g_min) / (self.g_max - self.g_min)
                    ypix = gear_bottom + VP + gy * (gear_h - 2 * VP)
                    gear_pts.append((xpix, ypix))

                # Add comparison driver's gears
                for d, g in zip(draw_comparison_pos, draw_comparison_gears):
                    if g is None:
                        continue
                    nx = (d - full_d_min) / (full_d_max - full_d_min)
                    xpix = chart_left + nx * chart_w
                    gy = (g - self.g_min) / (self.g_max - self.g_min)
                    ypix = gear_bottom + VP + gy * (gear_h - 2 * VP)
                    comparison_gear_pts.append((xpix, ypix))

                try:
                    if comparison_gear_pts:
                        arcade.draw_line_strip(comparison_gear_pts, arcade.color.YELLOW, 2)
                        
                    if gear_pts:
                        arcade.draw_line_strip(gear_pts, arcade.color.LIGHT_GRAY, 2)
                        
                        # Show current gear next to the line

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
                
                # Add lap time to the left of the track map

                current_frame = frames[self.frame_index]
                current_t = current_frame.get("t", 0.0)
                    
                formatted_time = format_time(current_t)

                arcade.Text(f"Lap Time: {formatted_time}", map_left + 10, map_top - 30, arcade.color.ANTI_FLASH_WHITE, 16).draw()

                arcade.Text(f"Playback Speed: {self.playback_speed:.1f}x", map_left + 10, map_top - 50, arcade.color.ANTI_FLASH_WHITE, 14).draw()

                # Legends
                legend_x = chart_right - 100
                legend_y = ctrl_top - int(ctrl_h * 0.2)

                # Draw circuit map in bottom half (fit inner/outer polylines into map area)
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

                    # Use the interpolated world points if available, fallback to raw arrays
                    inner_world = getattr(self, "world_inner_points", None) or list(zip(self.x_inner, self.y_inner))
                    outer_world = getattr(self, "world_outer_points", None) or list(zip(self.x_outer, self.y_outer))

                    inner_pts = [world_to_map(x, y) for x, y in inner_world if x is not None and y is not None]
                    outer_pts = [world_to_map(x, y) for x, y in outer_world if x is not None and y is not None]

                    try:
                        if len(inner_pts) > 1:
                            arcade.draw_line_strip(inner_pts, arcade.color.GRAY, 2)
                        if len(outer_pts) > 1:
                            arcade.draw_line_strip(outer_pts, arcade.color.GRAY, 2)
                    except Exception as e:
                        print("Circuit draw error:", e)

                    # Draw the comparison driver's position (if available - doing this first so that the current driver is on top visually)

                    if comparison_telemetry and self.frame_index < len(comparison_telemetry):
                        comp_frame = comparison_telemetry[self.frame_index]
                        comp_tel = comp_frame.get("telemetry", {}) if isinstance(comp_frame.get("telemetry", {}), dict) else {}
                        c_px = comp_tel.get("x")
                        c_py = comp_tel.get("y")
                        c_sx, c_sy = world_to_map(c_px, c_py)
                        arcade.draw_circle_filled(c_sx, c_sy, 6, arcade.color.YELLOW)

                    # Draw DRS zones on track map as green highlights
                    if self.drs_zones_xy and self.toggle_drs_zones:
                        drs_color = (0, 255, 0)
                        original_length = len(self.x_inner)
                        # Interpolated world points length
                        interpolated_length = len(inner_world)
                        
                        for dz in self.drs_zones_xy:
                            orig_start_idx = dz["start"]["index"]
                            orig_end_idx = dz["end"]["index"]

                            if orig_start_idx is None or orig_end_idx is None:
                                continue
                            try:
                                # Map original indices to interpolated array indices
                                interp_start_idx = int((orig_start_idx / original_length) * interpolated_length)
                                interp_end_idx = int((orig_end_idx / original_length) * interpolated_length)
                                
                                # Clamp to valid range
                                interp_start_idx = max(0, min(interp_start_idx, interpolated_length - 1))
                                interp_end_idx = max(0, min(interp_end_idx, interpolated_length - 1))
                                
                                if interp_start_idx < interp_end_idx:
                                    # Extract segments for this DRS zone using mapped indices
                                    outer_zone = [world_to_map(x, y) for x, y in outer_world[interp_start_idx:interp_end_idx+1] 
                                                  if x is not None and y is not None]
                                    if len(outer_zone) > 1:
                                        arcade.draw_line_strip(outer_zone, drs_color, 3)

                            except Exception as e:
                                print(f"DRS zone draw error: {e}")

                    # Draw current driver's position marker (sync with frame_index)
                    current_frame = frames[self.frame_index]
                    tel = current_frame.get("telemetry", {}) if isinstance(current_frame.get("telemetry", {}), dict) else {}
                    px = tel.get("x")
                    py = tel.get("y")
                    sx, sy = world_to_map(px, py)
                    # driver colour lookup (fallback to white)
                    drv_color = (255, 255, 255)
                    if getattr(self, "loaded_driver_code", None):
                        for r in self.data.get("results", []):
                            if r.get("code") == self.loaded_driver_code and r.get("color"):
                                drv_color = tuple(r.get("color"))
                                break
                    arcade.draw_circle_filled(sx, sy, 6, drv_color)

                    # Overlay current gear near the position marker on the track
                    cur_gear = tel.get("gear") or tel.get("nGear") or tel.get("Gear")
                    if cur_gear is None:
                        cur_gear = draw_gears[-1] if draw_gears else None
                    arcade.Text(self.loaded_driver_code or "", sx + 10, sy + 4, arcade.color.WHITE, 12).draw()
                    if cur_gear is not None:
                        arcade.Text(f"G:{int(cur_gear)}", sx + 10, sy - 10, arcade.color.LIGHT_GRAY, 12).draw()

            # Controls Legend - Bottom Left (keeps small offset from left UI edge)
            legend_x = max(12, self.left_ui_margin - 320) if hasattr(self, "left_ui_margin") else 20
            legend_y = 180 # Height of legend block
            legend_icons = self.legend_comp._control_icons_textures # icons
            legend_lines = [
                ("Controls:"),
                ("[SPACE]  Pause/Resume"),
                ("Rewind / FastForward", ("[", "/", "]"),("arrow-left", "arrow-right")), # text, brackets, icons
                ("Speed +/- (0.5x, 1x, 2x, 4x)", ("[", "/", "]"), ("arrow-up", "arrow-down")), # text, brackets, icons
                ("[R]       Restart"),
                ("[D]       Toggle DRS zones on track map"),
                ("[C]       Toggle comparison driver telemetry")
            ]
            for i, lines in enumerate(legend_lines):
                line = lines[0] if isinstance(lines, tuple) else lines
                brackets = lines[1] if isinstance(lines, tuple) and len(lines) > 2 else None # brackets only if icons exist
                icon_keys = lines[2] if isinstance(lines, tuple) and len(lines) > 2 else None
            
                icon_size = 14
                # Draw icons if any
                if icon_keys:
                    control_icon_x = legend_x + 12
                    for key in icon_keys:
                        icon_texture = legend_icons.get(key)
                        if icon_texture:
                            control_icon_y = legend_y - (i * 25) + 5
                            rect = arcade.XYWH(control_icon_x, control_icon_y, icon_size, icon_size)
                            arcade.draw_texture_rect(
                                rect = rect,
                                texture = icon_texture,
                                angle = 0,
                                alpha = 255
                            )
                            control_icon_x += icon_size + 6  # spacing between icons                
                # Draw brackets if any
                if brackets:
                    for j in range(len(brackets)):
                        arcade.Text(
                            brackets[j],
                            legend_x + (j * (icon_size + 5)),
                            legend_y - (i * 25),
                            arcade.color.LIGHT_GRAY if i > 0 else arcade.color.WHITE,
                            14,
                        ).draw()
                # Draw the text line
                arcade.Text(
                    line,
                    legend_x + (60 if icon_keys else 0),
                    legend_y - (i * 25),
                    arcade.color.LIGHT_GRAY if i > 0 else arcade.color.WHITE,
                    14,
                    bold=(i == 0),
                ).draw()
        else:
            # Add "click a driver to view their qualifying lap" text in the center of the chart area

            info_text = "Click a driver on the left to load their qualifying lap telemetry."
            arcade.Text(
                info_text,
                self.width / 2, self.height / 2,
                arcade.color.LIGHT_GRAY, 18,
                anchor_x="center", anchor_y="center"
            ).draw()

        self.leaderboard.draw(self)
        self.qualifying_segment_selector_modal.draw(self)
        
        # Show race controls only when telemetry is loaded (driver + session selected)
        if self.chart_active and self.loaded_telemetry and self.frame_index < self.n_frames:
            self.race_controls_comp.draw(self)

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
        # Rotate around the track centre (if rotation is set), then scale+translate
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
        """Return the first value for keys that exists in tel and is not None.
        Preserves falsy-but-valid values like 0.0."""
        if not isinstance(tel, dict):
            return None
        for k in keys:
            if k in tel and tel[k] is not None:
                return tel[k]
        return None

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        # If the segment-selector modal is visible (a driver selected), give it first chance
        # to handle the click (so its close button can work). If it handled the click,
        # stop further processing so the leaderboard doesn't re-select the driver.
        if getattr(self, "selected_driver", None):
            try:
                handled = self.qualifying_segment_selector_modal.on_mouse_press(self, x, y, button, modifiers)
                if handled:
                    return
            except Exception as e:
                print("Segment selector click error:", e)

        # Fallback: let the leaderboard handle the click (select drivers)
        self.leaderboard.on_mouse_press(self, x, y, button, modifiers)
        
        # Only allow race controls interaction if lap is not complete
        if not self.is_lap_complete():
            self.race_controls_comp.on_mouse_press(self, x, y, button, modifiers)

    def is_lap_complete(self):
        """Check if the current lap has finished playing."""
        return self.chart_active and self.n_frames > 0 and self.frame_index >= self.n_frames - 1

    def on_key_press(self, symbol: int, modifiers: int):
        # Allow restart (R), comparison toggle (C), and DRS toggle (D) even when lap is complete
        if symbol == arcade.key.R:
            self.frame_index = 0
            self.play_time = self.play_start_t
            self.playback_speed = 1.0
            self.paused = True
            self.race_controls_comp.flash_button('rewind')
            return
        elif symbol == arcade.key.C:
            # Toggle the ability to see the comparison driver's telemetry
            self.show_comparison_telemetry = not self.show_comparison_telemetry
            return
        elif symbol == arcade.key.D:
            # Toggle DRS zones on track map
            self.toggle_drs_zones = not self.toggle_drs_zones
            return
        
        # Disable other controls when lap is complete
        if self.is_lap_complete():
            return
        
        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
            self.race_controls_comp.flash_button('play_pause')
        elif symbol == arcade.key.RIGHT:
            # step forward by 10 frames (keep integer)
            self.frame_index = int(min(self.frame_index + 10, max(0, self.n_frames - 1)))
            self.race_controls_comp.flash_button('forward')
        elif symbol == arcade.key.LEFT:
            # step backward by 10 frames (keep integer)
            self.frame_index = int(max(self.frame_index - 10, 0))
            self.race_controls_comp.flash_button('rewind')
        elif symbol == arcade.key.UP:
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

    def load_driver_telemetry(self, driver_code: str, segment_name: str):

        # If already loading, ignore
        if self.loading_telemetry:
            return

        # Try to find telemetry already provided in the window's data object
        telemetry_store = self.data.get("telemetry") if isinstance(self.data, dict) else None
        if telemetry_store:
            driver_block = telemetry_store.get(driver_code) if isinstance(telemetry_store, dict) else None
            if driver_block:
                seg = driver_block.get(segment_name)
                if seg and isinstance(seg, dict) and seg.get("frames"):
                    # Use local telemetry immediately (no background fetch required)
                    self.loaded_telemetry = seg
                    self.loaded_driver_code = driver_code
                    self.loaded_driver_segment = segment_name
                    self.chart_active = True
                    # cache arrays for fast access and search
                    frames = seg.get("frames", [])
                    drs_zones = seg.get("drs_zones", [])
                    times = [float(f.get("t")) for f in frames if f.get("t") is not None]
                    xs = [ (f.get("telemetry") or {}).get("x") for f in frames ]
                    ys = [ (f.get("telemetry") or {}).get("y") for f in frames ]
                    speeds = [ (f.get("telemetry") or {}).get("speed") for f in frames ]
                    # convert to numpy arrays (keep None if any; searchsorted expects numeric times)
                    self._times = np.array(times) if times else None
                    self._xs = np.array(xs) if xs else None
                    self._ys = np.array(ys) if ys else None
                    self._speeds = np.array([float(s) for s in speeds if s is not None]) if speeds else None
                    # populate top-level frames/n_frames and min/max speeds for chart scaling
                    self.frames = frames
                    self.drs_zones = drs_zones
                    print("DRS zones loaded:", self.drs_zones)
                    self.n_frames = len(frames)
                    if self._speeds is not None and self._speeds.size > 0:
                        self.min_speed = float(np.min(self._speeds))
                        self.max_speed = float(np.max(self._speeds))
                    else:
                        self.min_speed = 0.0
                        self.max_speed = 0.0
                     # initialize playback state based on frames' timestamps
                    frames = seg.get("frames", [])
                    if frames:
                        start_t = frames[0].get("t", 0.0)
                        self.play_start_t = float(start_t)
                        self.play_time = float(start_t)
                        self.frame_index = 0
                        self.paused = False
                        self.playback_speed = 1.0
                    self.loading_telemetry = False
                    self.loading_message = ""
                    return

        # Otherwise proceed with background loading as before
        self.loading_telemetry = True
        self.loading_message = f"Loading telemetry {driver_code} {segment_name}..."
        self.loaded_telemetry = None
        self.chart_active = False

        threading.Thread(
            target=self._bg_load_telemetry,
            args=(driver_code, segment_name),
            daemon=True
        ).start()

    def _bg_load_telemetry(self, driver_code: str, segment_name: str):
        """Background loader that fetches telemetry if not present locally."""
        try:
            telemetry = None
            # First double-check local store in background thread (race-safe)
            telemetry_store = self.data.get("telemetry") if isinstance(self.data, dict) else None
            if telemetry_store:
                driver_block = telemetry_store.get(driver_code) if isinstance(telemetry_store, dict) else None
                if driver_block:
                    seg = driver_block.get(segment_name)
                    if seg and isinstance(seg, dict) and seg.get("frames"):
                        telemetry = seg

            # If not found locally, attempt to fetch via API if a session is available
            if telemetry is None and getattr(self, "session", None) is not None:
                telemetry = get_driver_quali_telemetry(self.session, driver_code, segment_name)
            elif telemetry is None:
                # demo fallback: sleep briefly and leave telemetry None
                time.sleep(1.0)
                telemetry = None

            if telemetry is None:
                self.loaded_telemetry = None
                self.chart_active = False
            else:
                self.loaded_telemetry = telemetry
                self.loaded_driver_code = driver_code
                self.loaded_driver_segment = segment_name
                self.chart_active = True
                # cache arrays for fast indexing/interpolation
                frames = telemetry.get("frames", [])
                times = [float(f.get("t")) for f in frames if f.get("t") is not None]
                xs = [ (f.get("telemetry") or {}).get("x") for f in frames ]
                ys = [ (f.get("telemetry") or {}).get("y") for f in frames ]
                speeds = [ (f.get("telemetry") or {}).get("speed") for f in frames ]
                self._times = np.array(times) if times else None
                self._xs = np.array(xs) if xs else None
                self._ys = np.array(ys) if ys else None
                self._speeds = np.array([float(s) for s in speeds if s is not None]) if speeds else None
                self.frames = frames
                self.n_frames = len(frames)
                if self._speeds is not None and self._speeds.size > 0:
                    self.min_speed = float(np.min(self._speeds))
                    self.max_speed = float(np.max(self._speeds))
                else:
                    self.min_speed = 0.0
                    self.max_speed = 0.0
                # initialize playback state for the newly loaded telemetry
                frames = telemetry.get("frames", [])
                if frames:
                    start_t = frames[0].get("t", 0.0)
                    self.play_start_t = float(start_t)
                    self.play_time = float(start_t)
                    self.frame_index = 0
                    self.paused = False
                    self.playback_speed = 1.0
        except Exception as e:
            print("Telemetry load failed:", e)
            self.loaded_telemetry = None
            self.chart_active = False
        finally:
            self.loading_telemetry = False
            self.loading_message = ""

    def on_update(self, delta_time: float):
        # time-based playback synced to telemetry timestamps
        if not self.chart_active or self.loaded_telemetry is None:
            return
        if self.paused:
            self.race_controls_comp.on_update(delta_time)
            return
        self.race_controls_comp.on_update(delta_time)
        # advance play_time by delta_time scaled by playback_speed
        self.play_time += delta_time * self.playback_speed
        # compute integer frame index from cached times (fast, robust)
        if self._times is not None and len(self._times) > 0:
            # clamp play_time into available range
            clamped = min(max(self.play_time, float(self._times[0])), float(self._times[-1]))
            idx = int(np.searchsorted(self._times, clamped, side="right") - 1)
            self.frame_index = max(0, min(idx, len(self._times) - 1))

            # Auto-pause when lap completes to prevent errors
            if self.frame_index >= self.n_frames - 1:
                self.paused = True
        else:
            # fallback: step frame index at FPS if no timestamps available
            self.frame_index = int(min(self.n_frames - 1, self.frame_index + int(round(delta_time * FPS * self.playback_speed))))

            # Auto-pause when lap completes to prevent errors
            if self.frame_index >= self.n_frames - 1:
                self.paused = True

def run_qualifying_replay(session, data, title="Qualifying Results"):
    window = QualifyingReplay(session=session, data=data, title=title)
    arcade.run()