import arcade
import numpy as np
from src.lib.sync import TelemetryListener

class TelemetryWindow(arcade.Window):
    def __init__(self, frames, driver_colors, title="Telemetry Monitor"):
        super().__init__(800, 600, title, resizable=True)
        
        self.frames = frames
        self.driver_colors = driver_colors
        self.listener = TelemetryListener()
        
        self.selected_driver = None
        self.cursor_frame_index = 0
        
        # Visual Styling
        self.bg_color = (10, 10, 15, 255)
        self.chart_bg_color = (40, 40, 40, 230)
        self.background_color = self.bg_color
        
        # Data Cache
        self.cache = {"speeds": [], "throttles": [], "brakes": [], "gears": []}
        self.min_speed = 0
        self.max_speed = 360

    def set_driver(self, driver_code):
        if self.selected_driver == driver_code: return
        self.selected_driver = driver_code
        self.set_caption(f"Telemetry Analysis - {driver_code}")
        
        # Pre-calculate data arrays
        speeds, throttles, brakes, gears = [], [], [], []
        
        for f in self.frames:
            d_data = f.get("drivers", {}).get(driver_code)
            if d_data:
                speeds.append(float(d_data.get("speed", 0) or 0))
                throttles.append(float(d_data.get("throttle", 0) or 0))
                brakes.append(float(d_data.get("brake", 0) or 0))
                gears.append(int(d_data.get("gear", 0) or 0))
            else:
                # Fill missing data with 0 (or hold last value)
                speeds.append(0)
                throttles.append(0)
                brakes.append(0)
                gears.append(0)

        self.cache = {
            "speeds": np.array(speeds),
            "throttles": np.array(throttles),
            "brakes": np.array(brakes),
            "gears": np.array(gears)
        }
        
        # Adjust scale dynamically
        if speeds: 
            self.max_speed = max(300, max(speeds) + 20)

    def on_update(self, delta_time):
        # Check for updates from the Main Window
        data = self.listener.get_latest()
        if data:
            self.cursor_frame_index = int(data.get("f", 0))
            new_driver = data.get("d")
            
            # Only update driver if it's a valid string (ignore None/Deselect)
            if new_driver and new_driver != self.selected_driver:
                self.set_driver(new_driver)

    def on_draw(self):
        self.clear()
        
        if not self.selected_driver or not self.frames:
            arcade.draw_text("Select a driver in the Main Window", self.width/2, self.height/2, 
                             arcade.color.GRAY, 20, anchor_x="center", anchor_y="center")
            return

        # Layout Dimensions
        margin = 40
        w = self.width - (margin * 2)
        h = self.height - (margin * 2)
        x_left = margin
        
        # Vertical Splits
        speed_h = h * 0.5
        gear_h = h * 0.2
        input_h = h * 0.3 - 20 
        
        speed_y = self.height - margin - speed_h
        gear_y = speed_y - 10 - gear_h
        input_y = gear_y - 10 - input_h
        
        # Draw Graph Backgrounds
        for y, ht, label in [(speed_y, speed_h, "Speed"), (gear_y, gear_h, "Gear"), (input_y, input_h, "Inputs")]:
            arcade.draw_rect_filled(arcade.XYWH(self.width/2, y + ht/2, w, ht), self.chart_bg_color)
            arcade.draw_text(label, margin + 5, y + ht - 20, arcade.color.WHITE, 12)

        # --- TIME WINDOW LOGIC (THE FIX) ---
        # We use a fixed window of 600 frames (approx 10-20 seconds depending on data rate)
        window_size = 600 
        total_frames = len(self.frames)
        
        # Center the view on the cursor
        start_idx = max(0, self.cursor_frame_index - window_size // 2)
        end_idx = min(total_frames, start_idx + window_size)
        
        # Clamp if near the end
        if end_idx - start_idx < window_size and start_idx > 0:
            start_idx = max(0, end_idx - window_size)

        # Helper to draw a line strip
        # Now uses INDEX (i) for X-axis, not Distance
        def draw_graph(values, y_base, y_scale, color):
            pts = []
            slice_data = values[start_idx:end_idx]
            count = len(slice_data)
            if count < 2: return

            for i, v in enumerate(slice_data):
                # X is simply percentage of the window width
                x = x_left + (i / (window_size - 1)) * w
                y = y_base + v * y_scale
                pts.append((x, y))
            
            arcade.draw_line_strip(pts, color, 2)

        # Draw the Data
        draw_graph(self.cache["speeds"], speed_y, speed_h / self.max_speed, arcade.color.CYAN)
        draw_graph(self.cache["gears"], gear_y, gear_h / 8, arcade.color.ORANGE)
        draw_graph(self.cache["throttles"], input_y, input_h / 100, arcade.color.GREEN)
        draw_graph(self.cache["brakes"], input_y, input_h / 100, arcade.color.RED)

        # Draw Cursor Line (Always in the center unless at edges)
        if start_idx <= self.cursor_frame_index < end_idx:
            # Calculate where the cursor falls in our current window (0.0 to 1.0)
            cursor_rel_pos = self.cursor_frame_index - start_idx
            cx = x_left + (cursor_rel_pos / (window_size - 1)) * w
            
            arcade.draw_line(cx, input_y, cx, speed_y + speed_h, arcade.color.WHITE, 2)
            
            # Draw Text Value
            spd = self.cache["speeds"][self.cursor_frame_index]
            arcade.draw_text(f"{int(spd)} kph", cx + 5, speed_y + speed_h - 20, arcade.color.WHITE, 12)

def run_telemetry_monitor(frames, driver_colors):
    """Entry point for the separate process."""
    win = TelemetryWindow(frames, driver_colors)
    arcade.run()