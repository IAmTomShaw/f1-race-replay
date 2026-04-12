import arcade
from .base import BaseComponent
from .leaderboard import LeaderboardComponent
from src.tyre_degradation_integration import (
    format_tyre_health_bar, 
    format_degradation_text
)

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

        if lb and hasattr(lb, "entries") and lb.entries:
            try:
                idx = next(i for i, e in enumerate(lb.entries) if e[0] == code)
                curr_pos = lb.entries[idx][3]

                def get_gap_str(neighbor_idx, prefix, sign):
                    n_code, _, _, n_pos = lb.entries[neighbor_idx]
                    dist = abs(curr_pos - n_pos) / 10.0
                    time = dist / 55.56  # 200 km/h reference speed
                    return f"{prefix} ({n_code}): {sign}{time:.2f}s ({dist:.1f}m)"

                if idx > 0:
                    gap_ahead = get_gap_str(idx - 1, "Ahead", "+")
                if idx < len(lb.entries) - 1:
                    gap_behind = get_gap_str(idx + 1, "Behind", "-")

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
