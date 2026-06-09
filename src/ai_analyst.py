import arcade
import numpy as np
import os
from src.f1_data import FPS

# IMPORT AI BRIDGE
try:
    from src.backend.ai_engine import AIEngine
    AI_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] AI Engine not found: {e}")
    AI_AVAILABLE = False

SCREEN_WIDTH = 1400  # Made slightly wider for 3 panels
SCREEN_HEIGHT = 800
TITLE = "AI ANALYST: NEURO-SYMBOLIC COMMAND CENTER"

# --- LAYOUT CONFIG ---
SIDEBAR_WIDTH = 300
TRACK_WIDTH = SCREEN_WIDTH - (SIDEBAR_WIDTH * 2)

class AIAnalystWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, assets_root_path=None):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, TITLE, resizable=True)
        
        # --- DATA SETUP ---
        self.frames = frames
        self.example_lap = example_lap
        self.drivers = drivers
        self.driver_colors = driver_colors or {}
        
        # Default driver
        self.selected_driver = "VER" if "VER" in drivers else drivers[0]
        
        # Playback
        self.frame_index = 0.0
        self.playback_speed = playback_speed
        self.paused = False
        
        # --- AI ENGINE ---
        self.ai_engine = None
        self.current_logic_state = {
            "strategy": "WAITING...",
            "tire_health": "ANALYZING",
            "tire_reason": "...",
            "active_facts": []
        }
        
        if AI_AVAILABLE:
            self.ai_engine = AIEngine(self.example_lap)

        # --- TRACK GEOMETRY ---
        self.plot_x = example_lap["X"].to_numpy()
        self.plot_y = example_lap["Y"].to_numpy()
        self.x_min, self.x_max = min(self.plot_x), max(self.plot_x)
        self.y_min, self.y_max = min(self.plot_y), max(self.plot_y)
        
        self.update_scaling()

    def update_scaling(self):
        # Scale track to fit strictly in the CENTER panel
        world_w = self.x_max - self.x_min
        world_h = self.y_max - self.y_min
        
        # 90% of the center panel width
        scale_x = (TRACK_WIDTH * 0.9) / world_w
        scale_y = (SCREEN_HEIGHT * 0.9) / world_h
        self.world_scale = min(scale_x, scale_y)
        
        # Center coordinates relative to the MIDDLE of the screen
        center_x_offset = SIDEBAR_WIDTH + (TRACK_WIDTH / 2)
        center_y_offset = SCREEN_HEIGHT / 2
        
        self.tx = center_x_offset - (self.world_scale * (self.x_min + self.x_max) / 2)
        self.ty = center_y_offset - (self.world_scale * (self.y_min + self.y_max) / 2)

    def w2s(self, x, y):
        return (self.world_scale * x + self.tx, self.world_scale * y + self.ty)

    def on_update(self, delta_time):
        if self.paused: return
        
        self.frame_index += delta_time * FPS * self.playback_speed
        if self.frame_index >= len(self.frames):
            self.frame_index = 0
            
        # --- AI UPDATE ---
        if self.ai_engine:
            idx = int(self.frame_index)
            frame = self.frames[idx]
            d_data = frame["drivers"].get(self.selected_driver)
            
            if d_data:
                # Create a rich snapshot for the "Sensors"
                snapshot = {
                    'tyre_compound': 'soft',
                    'tyre_age': idx // 100,
                    'tyre_temp': int(100 + (np.sin(idx/50) * 15)),
                    'rain': 0,
                    'track_status': 1,
                    'gap_to_leader': d_data.get('gap', 0)
                }
                self.current_logic_state = self.ai_engine.update_telemetry(self.selected_driver, snapshot)

    def on_draw(self):
        self.clear()
        
        # --- 1. LEFT PANEL: SENSORS (Raw Data) ---
        self.draw_left_panel()

        # --- 2. CENTER PANEL: THE BATTLE (Track + Ghost) ---
        self.draw_center_panel()

        # --- 3. RIGHT PANEL: THE BRAIN (Logic + Strategy) ---
        self.draw_right_panel()

    def draw_left_panel(self):
        # Background
        arcade.draw_rect_filled(arcade.XYWH(0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT), (10, 10, 15))
        arcade.draw_line(SIDEBAR_WIDTH, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT, arcade.color.GRAY, 1)
        
        # Header
        arcade.draw_rect_filled(arcade.XYWH(0, SCREEN_HEIGHT-40, SIDEBAR_WIDTH, 40), (20, 20, 25))
        arcade.draw_text("SENSOR FEED", 10, SCREEN_HEIGHT-28, arcade.color.CYAN, 12, bold=True)
        
        # Content (Scrolling Matrix Text)
        y = SCREEN_HEIGHT - 60
        facts = self.current_logic_state['active_facts']
        
        arcade.draw_text(f"DRIVER: {self.selected_driver}", 10, y, arcade.color.WHITE, 12, bold=True)
        y -= 30
        
        arcade.draw_text(">> RAW TELEMETRY STREAM:", 10, y, arcade.color.GRAY, 9)
        y -= 20
        
        for fact in facts:
            # Draw "assert(...)" in green monospace
            arcade.draw_text(f"assert({fact}).", 10, y, arcade.color.NEON_GREEN, 10, font_name="Consolas")
            y -= 20
        
        # Static Noise / Filler to look busy
        y -= 20
        arcade.draw_text(">> SYSTEM STATUS:", 10, y, arcade.color.GRAY, 9)
        y -= 20
        arcade.draw_text("LINK: STABLE", 10, y, arcade.color.NEON_GREEN, 10, font_name="Consolas")
        y -= 15
        arcade.draw_text("LATENCY: 12ms", 10, y, arcade.color.NEON_GREEN, 10, font_name="Consolas")

    def draw_center_panel(self):
        # Background (Darker for contrast)
        x_start = SIDEBAR_WIDTH
        arcade.draw_rect_filled(arcade.XYWH(x_start, 0, TRACK_WIDTH, SCREEN_HEIGHT), (5, 5, 8))
        
        # Draw Track
        points = [self.w2s(x, y) for x, y in zip(self.plot_x, self.plot_y)]
        arcade.draw_line_strip(points, arcade.color.DARK_GRAY, 3)
        
        idx = int(self.frame_index)
        frame = self.frames[idx]
        
        # --- THE GHOST CAR (Cyan) ---
        ghost_idx = idx % len(self.plot_x)
        gx, gy = self.w2s(self.plot_x[ghost_idx], self.plot_y[ghost_idx])
        arcade.draw_circle_filled(gx, gy, 8, (0, 255, 255, 150)) # Transparent Cyan
        arcade.draw_text("GHOST", gx+10, gy, arcade.color.CYAN, 9)

        # --- THE DRIVER (White) ---
        d_data = frame["drivers"].get(self.selected_driver)
        if d_data:
            dx, dy = self.w2s(d_data['x'], d_data['y'])
            arcade.draw_circle_filled(dx, dy, 8, arcade.color.WHITE)
            arcade.draw_circle_outline(dx, dy, 12, arcade.color.WHITE, 2)
            arcade.draw_text(self.selected_driver, dx+12, dy, arcade.color.WHITE, 10, bold=True)
            
            # Draw a line between them to visualize the gap
            arcade.draw_line(dx, dy, gx, gy, (255, 255, 255, 50), 1)

    def draw_right_panel(self):
        x_start = SIDEBAR_WIDTH + TRACK_WIDTH
        
        # Background
        arcade.draw_rect_filled(arcade.XYWH(x_start, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT), (10, 10, 15))
        arcade.draw_line(x_start, 0, x_start, SCREEN_HEIGHT, arcade.color.GRAY, 1)
        
        # Header
        arcade.draw_rect_filled(arcade.XYWH(x_start, SCREEN_HEIGHT-40, SIDEBAR_WIDTH, 40), (20, 20, 25))
        arcade.draw_text("LOGIC CORE OUTPUT", x_start+10, SCREEN_HEIGHT-28, arcade.color.MAGENTA, 12, bold=True)
        
        # --- STRATEGY ALERT BOX ---
        y = SCREEN_HEIGHT - 80
        strat = self.current_logic_state['strategy']
        
        # Color Coding the Alert
        box_color = arcade.color.DARK_BLUE_GRAY
        border_color = arcade.color.CYAN
        if "BOX" in strat:
            box_color = (50, 0, 0)
            border_color = arcade.color.RED
        
        # Draw the "LED Screen" box
        arcade.draw_rect_filled(arcade.XYWH(x_start+15, y-50, SIDEBAR_WIDTH-30, 60), box_color)
        arcade.draw_rect_outline(arcade.XYWH(x_start+15, y-50, SIDEBAR_WIDTH-30, 60), border_color, 2)
        
        arcade.draw_text("ENGINEER RADIO:", x_start+20, y-10, border_color, 10, bold=True)
        arcade.draw_text(strat, x_start+20, y-40, arcade.color.WHITE, 11, bold=True, width=SIDEBAR_WIDTH-40, multiline=True)
        
        # --- TIRE HEALTH DIAGNOSIS ---
        y -= 100
        arcade.draw_text(">> COMPONENT DIAGNOSTICS:", x_start+10, y, arcade.color.GRAY, 9)
        y -= 20
        
        health = self.current_logic_state['tire_health']
        reason = self.current_logic_state['tire_reason']
        
        h_color = arcade.color.GREEN
        if health != "OPTIMAL": h_color = arcade.color.YELLOW
        if health == "CRITICAL": h_color = arcade.color.RED
        
        arcade.draw_text(f"TIRES: {health}", x_start+10, y, h_color, 12, bold=True, font_name="Consolas")
        y -= 20
        arcade.draw_text(f"REASON: {reason}", x_start+10, y, arcade.color.WHITE, 9, font_name="Consolas")
        
        # --- PROLOG TRACE (Fake Visual) ---
        y -= 60
        arcade.draw_text(">> INFERENCE TRACE:", x_start+10, y, arcade.color.GRAY, 9)
        y -= 20
        
        # List rules that 'fired' based on the output
        trace_lines = []
        if "BOX" in strat:
            trace_lines = ["Check: tire_life_limit", "-> EXCEEDED", "Check: pit_window", "-> OPEN", ">> TRIGGER: BOX NOW"]
        elif "OVERTAKE" in strat:
             trace_lines = ["Check: drs_zone", "-> TRUE", "Check: gap < 1.0", "-> TRUE", ">> TRIGGER: ATTACK"]
        else:
             trace_lines = ["Scanning sensors...", "Monitoring gaps...", "No critical alerts."]
             
        for line in trace_lines:
            color = arcade.color.NEON_GREEN if "TRIGGER" in line else arcade.color.GRAY
            arcade.draw_text(line, x_start+10, y, color, 10, font_name="Consolas")
            y -= 15

def run_ai_analyst(frames, track_statuses, example_lap, drivers, title, 
                   playback_speed=1.0, driver_colors=None, assets_root_path=None):
    window = AIAnalystWindow(frames, track_statuses, example_lap, drivers, title, 
                             playback_speed, driver_colors, assets_root_path)
    arcade.run()