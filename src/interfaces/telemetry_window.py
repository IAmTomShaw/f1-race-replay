import arcade
import numpy as np
from src.lib.sync import TelemetryListener

class TelemetryWindow(arcade.Window):
    def __init__(self, frames, driver_colors, title="Telemetry Monitor"):
        super().__init__(1000, 800, title, resizable=True)
        
        self.frames = frames
        self.driver_colors = driver_colors
        self.listener = TelemetryListener()
        
        self.selected_driver = None
        self.cursor_frame_index = 0
        
        # --- Colors ---
        self.bg_color = (10, 10, 15, 255)
        self.chart_bg_color = (25, 25, 30, 255)
        self.grid_color = (60, 60, 70, 255)
        self.text_color = (220, 220, 220, 255)
        
        # Graph Lines
        self.col_speed = (0, 255, 255, 255)   # Cyan
        self.col_gear = (255, 165, 0, 255)    # Orange
        self.col_throt = (0, 255, 0, 255)     # Green
        self.col_brake = (255, 50, 50, 255)   # Red
        self.col_drs_zone = (0, 100, 0, 80)   # Transparent Green
        
        self.background_color = self.bg_color
        
        # Data Cache
        self.cache = {
            "speeds": [], "throttles": [], "brakes": [], 
            "gears": [], "drs": [], "t": [],
            "tyres": [], "tyre_life": []
        }
        self.max_speed = 360

    def set_driver(self, driver_code):
        if self.selected_driver == driver_code: return
        self.selected_driver = driver_code
        self.set_caption(f"Telemetry Analysis - {driver_code}")
        
        speeds, throttles, brakes, gears, drs, times = [], [], [], [], [], []
        tyres, tyre_life = [], []
        
        for f in self.frames:
            t = float(f.get("t", 0))
            d_data = f.get("drivers", {}).get(driver_code)
            if d_data:
                speeds.append(float(d_data.get("speed", 0) or 0))
                throttles.append(float(d_data.get("throttle", 0) or 0))
                
                # Handle Brake (Boolean/Float/None)
                b_raw = d_data.get("brake", 0)
                if isinstance(b_raw, bool):
                    b_val = 100.0 if b_raw else 0.0
                elif b_raw is None:
                    b_val = 0.0
                else:
                    b_val = float(b_raw)
                brakes.append(b_val)
                
                gears.append(int(d_data.get("gear", 0) or 0))
                drs.append(int(d_data.get("drs", 0) or 0))
                
                # Tyre Data (Raw from feed)
                tyre_char = str(d_data.get("tyre", "S")) # Default to Soft if missing
                # Map char to int ID for consistency
                t_map = {"S": 0, "M": 1, "H": 2, "I": 3, "W": 4}
                tyres.append(t_map.get(tyre_char, 0))
                
                # Tyre Life (Raw from feed)
                # If your feed doesn't have 'tyre_life', this defaults to 0
                tyre_life.append(int(d_data.get("tyre_life", 0) or 0))
            else:
                speeds.append(0); throttles.append(0); brakes.append(0); 
                gears.append(0); drs.append(0); tyres.append(0); tyre_life.append(0)
            times.append(t)

        # Smart Scaling for Brake
        max_b = max(brakes) if brakes else 0
        if 0 < max_b <= 1.0:
            brakes = [b * 100.0 for b in brakes]

        self.cache = {
            "speeds": np.array(speeds),
            "throttles": np.array(throttles),
            "brakes": np.array(brakes),
            "gears": np.array(gears),
            "drs": np.array(drs),
            "t": np.array(times),
            "tyres": np.array(tyres),
            "tyre_life": np.array(tyre_life)
        }
        if speeds: self.max_speed = max(340, max(speeds) + 20)

    def on_update(self, delta_time):
        data = self.listener.get_latest()
        if data:
            self.cursor_frame_index = int(data.get("f", 0))
            new_driver = data.get("d")
            if new_driver and new_driver != self.selected_driver:
                self.set_driver(new_driver)

    def draw_graph_bg(self, x, y, w, h, label):
        arcade.draw_rect_filled(arcade.XYWH(x + w/2, y + h/2, w, h), self.chart_bg_color)
        arcade.draw_rect_outline(arcade.XYWH(x + w/2, y + h/2, w, h), self.grid_color, 1)
        arcade.draw_text(label, x + 10, y + h - 20, self.text_color, 12, bold=True)

    def draw_cursor_bubble(self, cx, cy, text, color):
        text_w = len(text) * 8 + 14
        arcade.draw_rect_filled(arcade.XYWH(cx, cy + 20, text_w, 22), (20, 20, 20, 220))
        arcade.draw_rect_outline(arcade.XYWH(cx, cy + 20, text_w, 22), color, 1)
        arcade.draw_text(text, cx, cy + 20, arcade.color.WHITE, 10, anchor_x="center", anchor_y="center", bold=True)
        arcade.draw_circle_filled(cx, cy, 4, color)
        arcade.draw_circle_outline(cx, cy, 4, arcade.color.WHITE, 1)

    def draw_mini_dashboard(self, x, y, width, height, current_vals):
        """Dashboard with Name, Tyre Info (Simplified)"""
        
        # 1. Background
        arcade.draw_rect_filled(arcade.XYWH(x + width/2, y + height/2, width, height), (15, 15, 20, 255))
        arcade.draw_rect_outline(arcade.XYWH(x + width/2, y + height/2, width, height), (60, 60, 60), 2)
        
        # 2. Driver Header
        team_color = self.driver_colors.get(self.selected_driver, arcade.color.GRAY)
        header_h = 30
        arcade.draw_rect_filled(arcade.XYWH(x + width/2, y + height - header_h/2, width, header_h), (30, 30, 35))
        arcade.draw_rect_filled(arcade.XYWH(x + 3, y + height - header_h/2, 6, header_h), team_color)
        
        name = self.selected_driver if self.selected_driver else "SELECT"
        arcade.draw_text(name, x + 15, y + height - 15, team_color, 14, bold=True, anchor_y="center")
        
        # 3. Tyre Data (Simplified)
        tyre_map = {0: ("SOFT", 25, arcade.color.RED), 
                    1: ("MEDIUM", 35, arcade.color.YELLOW), 
                    2: ("HARD", 55, arcade.color.WHITE), 
                    3: ("INTER", 30, arcade.color.GREEN), 
                    4: ("WET", 30, arcade.color.BLUE)}
        
        t_id = current_vals.get('tyre', 0)
        t_life = current_vals.get('tyre_life', 0)
        t_name, t_max, t_col = tyre_map.get(t_id, ("SOFT", 25, arcade.color.RED))
        
        # Tyre Icon
        arcade.draw_circle_outline(x + width - 20, y + height - 15, 10, t_col, 2)
        arcade.draw_text(t_name[0], x + width - 20, y + height - 15, t_col, 9, anchor_x="center", anchor_y="center", bold=True)
        
        # 4. Tyre Bar (Raw Calculation)
        # Simple linear wear based on hardcoded max life estimates
        health_pct = max(0.0, min(1.0, 1.0 - (t_life / t_max)))
        health_int = int(health_pct * 100)
        
        bar_x = x + 15
        bar_y = y + 45
        bar_w = width - 30
        bar_h = 14
        
        # Background
        arcade.draw_rect_filled(arcade.XYWH(bar_x + bar_w/2, bar_y, bar_w, bar_h), (50, 50, 50))
        
        # Fill Color
        if health_pct >= 0.75: fill_col = (0, 220, 0)
        elif health_pct >= 0.50: fill_col = (200, 220, 0)
        elif health_pct >= 0.25: fill_col = (220, 180, 0)
        else: fill_col = (220, 50, 0)
        
        # Draw Fill
        fill_w = bar_w * health_pct
        if fill_w > 0:
            arcade.draw_rect_filled(arcade.XYWH(bar_x + fill_w/2, bar_y, fill_w, bar_h), fill_col)
            
        # Outline
        arcade.draw_rect_outline(arcade.XYWH(bar_x + bar_w/2, bar_y, bar_w, bar_h), arcade.color.WHITE, 1)
        
        # Text
        label_text = f"{t_name} (L{int(t_life)}): {health_int}%"
        arcade.draw_text(label_text, bar_x, bar_y - 20, arcade.color.LIGHT_GRAY, 11, bold=True)

    def draw_cockpit_gauge(self, center_x, center_y, current_vals):
        speed = current_vals.get('speed', 0)
        gear = current_vals.get('gear', 0)
        throttle = current_vals.get('throttle', 0)
        brake = current_vals.get('brake', 0)
        drs = current_vals.get('drs', 0)
        
        gauge_radius = 100
        
        # Speedometer
        arcade.draw_arc_outline(center_x, center_y, gauge_radius * 2, gauge_radius * 2, (40, 40, 40), 0, 180, 12)
        ratio = min(1.0, speed / 360)
        angle = 180 - (ratio * 180)
        arcade.draw_arc_outline(center_x, center_y, gauge_radius * 2, gauge_radius * 2, self.col_speed, angle, 180, 12)
        
        arcade.draw_text(f"{int(speed)}", center_x, center_y + 15, arcade.color.WHITE, 42, anchor_x="center", bold=True)
        arcade.draw_text("km/h", center_x, center_y - 15, arcade.color.GRAY, 12, anchor_x="center")
        
        # Gear
        gear_str = str(gear) if gear > 0 else "N"
        col = self.col_gear if gear > 0 else arcade.color.GRAY
        arcade.draw_text(gear_str, center_x, center_y - 60, col, 30, anchor_x="center", bold=True)
        arcade.draw_text("GEAR", center_x, center_y - 80, arcade.color.GRAY, 10, anchor_x="center")

        # DRS
        drs_active = drs >= 10
        drs_bg = (0, 180, 0) if drs_active else (25, 25, 30)
        drs_fg = arcade.color.WHITE if drs_active else (80, 80, 80)
        arcade.draw_rect_filled(arcade.XYWH(center_x, center_y - 110, 50, 22), drs_bg)
        arcade.draw_rect_outline(arcade.XYWH(center_x, center_y - 110, 50, 22), (60, 60, 60), 1)
        arcade.draw_text("DRS", center_x, center_y - 110, drs_fg, 11, anchor_x="center", anchor_y="center", bold=True)

        # Pedal Bars
        bar_w, bar_h = 25, 140
        bar_y_center = center_y - 20
        
        # Brake (Left)
        bk_x = center_x - 160
        arcade.draw_rect_filled(arcade.XYWH(bk_x, bar_y_center, bar_w, bar_h), (30, 30, 30))
        b_h_fill = bar_h * (brake / 100.0)
        if b_h_fill > 0:
            arcade.draw_rect_filled(arcade.XYWH(bk_x, bar_y_center - (bar_h/2) + (b_h_fill/2), bar_w, b_h_fill), self.col_brake)
        arcade.draw_text("BRK", bk_x, bar_y_center - bar_h/2 - 15, arcade.color.GRAY, 10, anchor_x="center")

        # Throttle (Right)
        th_x = center_x + 160
        arcade.draw_rect_filled(arcade.XYWH(th_x, bar_y_center, bar_w, bar_h), (30, 30, 30))
        t_h_fill = bar_h * (throttle / 100.0)
        if t_h_fill > 0:
            arcade.draw_rect_filled(arcade.XYWH(th_x, bar_y_center - (bar_h/2) + (t_h_fill/2), bar_w, t_h_fill), self.col_throt)
        arcade.draw_text("THR", th_x, bar_y_center - bar_h/2 - 15, arcade.color.GRAY, 10, anchor_x="center")

    def on_draw(self):
        self.clear()
        
        if not self.selected_driver or not self.frames:
            arcade.draw_text("Select Driver", self.width/2, self.height/2, arcade.color.GRAY, 20, anchor_x="center", anchor_y="center")
            return

        margin = 40
        w = self.width - (margin * 2)
        bottom_h = 240
        graphs_h = self.height - bottom_h - margin
        
        speed_h, gear_h, input_h = graphs_h * 0.45, graphs_h * 0.20, graphs_h * 0.25
        gap = 10
        speed_y = self.height - margin - speed_h
        gear_y = speed_y - gap - gear_h
        input_y = gear_y - gap - input_h
        
        window_size = 600
        start = max(0, self.cursor_frame_index - window_size // 2)
        end = min(len(self.frames), start + window_size)
        if end - start < window_size and start > 0: start = max(0, end - window_size)
        
        cursor_rel = self.cursor_frame_index - start
        cursor_x = margin + (cursor_rel / (window_size - 1)) * w if window_size > 1 else margin

        idx = self.cursor_frame_index
        c_vals = {}
        if idx < len(self.cache["speeds"]):
            c_vals = {
                'speed': self.cache["speeds"][idx],
                'gear': self.cache["gears"][idx],
                'throttle': self.cache["throttles"][idx],
                'brake': self.cache["brakes"][idx],
                'drs': self.cache["drs"][idx],
                'time': self.cache["t"][idx],
                'tyre': self.cache["tyres"][idx],
                'tyre_life': self.cache["tyre_life"][idx]
            }

        # 1. Speed Graph
        self.draw_graph_bg(margin, speed_y, w, speed_h, "Speed")
        drs_slice = self.cache["drs"][start:end]
        if len(drs_slice) > 0:
            in_zone, z_start = False, 0
            for i, val in enumerate(drs_slice):
                active = val >= 10
                px = margin + (i / (window_size - 1)) * w
                if active and not in_zone: in_zone, z_start = True, px
                elif not active and in_zone:
                    in_zone = False
                    arcade.draw_rect_filled(arcade.XYWH((z_start+px)/2, speed_y + speed_h/2, px-z_start, speed_h-2), self.col_drs_zone)
            if in_zone:
                px = margin + w
                arcade.draw_rect_filled(arcade.XYWH((z_start+px)/2, speed_y + speed_h/2, px-z_start, speed_h-2), self.col_drs_zone)

        pts = []
        for i, val in enumerate(self.cache["speeds"][start:end]):
            px = margin + (i / (window_size - 1)) * w
            py = speed_y + (val / self.max_speed) * speed_h
            pts.append((px, py))
        if len(pts) > 1: arcade.draw_line_strip(pts, self.col_speed, 2)
        if 0 <= cursor_rel < len(pts):
            self.draw_cursor_bubble(cursor_x, speed_y + (c_vals.get('speed',0) / self.max_speed) * speed_h, f"{int(c_vals.get('speed',0))}", self.col_speed)

        # 2. Gear Graph
        self.draw_graph_bg(margin, gear_y, w, gear_h, "Gear")
        pts_g = []
        for i, val in enumerate(self.cache["gears"][start:end]):
            px = margin + (i / (window_size - 1)) * w
            py = gear_y + (val / 8) * gear_h
            pts_g.append((px, py))
        if len(pts_g) > 1: arcade.draw_line_strip(pts_g, self.col_gear, 2)
        if 0 <= cursor_rel < len(pts_g):
            self.draw_cursor_bubble(cursor_x, gear_y + (c_vals.get('gear',0) / 8) * gear_h, f"{c_vals.get('gear',0)}", self.col_gear)

        # 3. Input Graph
        self.draw_graph_bg(margin, input_y, w, input_h, "Inputs")
        pts_t, pts_b = [], []
        th_slice = self.cache["throttles"][start:end]
        br_slice = self.cache["brakes"][start:end]
        for i in range(len(th_slice)):
            px = margin + (i / (window_size - 1)) * w
            pts_t.append((px, input_y + (th_slice[i] / 100) * input_h))
            pts_b.append((px, input_y + (br_slice[i] / 100) * input_h))
        if len(pts_t) > 1: arcade.draw_line_strip(pts_t, self.col_throt, 2)
        if len(pts_b) > 1: arcade.draw_line_strip(pts_b, self.col_brake, 2)
        
        if 0 <= cursor_rel < len(th_slice):
            self.draw_cursor_bubble(cursor_x, input_y + (c_vals.get('throttle',0) / 100) * input_h, f"{int(c_vals.get('throttle',0))}%", self.col_throt)
            if c_vals.get('brake',0) > 1:
                by = input_y + (c_vals.get('brake',0) / 100) * input_h
                if abs(by - (input_y + (c_vals.get('throttle',0)/100)*input_h)) < 25: by -= 25
                self.draw_cursor_bubble(cursor_x, by, f"{int(c_vals.get('brake',0))}%", self.col_brake)

        arcade.draw_line(cursor_x, input_y, cursor_x, speed_y + speed_h, (255, 255, 255, 80), 1)

        # 4. Dashboard
        dash_y = margin
        self.draw_mini_dashboard(margin, dash_y + 50, 220, 100, c_vals)
        self.draw_cockpit_gauge(self.width/2, dash_y + 100, c_vals)

def run_telemetry_monitor(frames, driver_colors):
    win = TelemetryWindow(frames, driver_colors)
    arcade.run()