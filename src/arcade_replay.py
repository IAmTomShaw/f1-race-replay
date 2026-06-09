import os
import arcade
import numpy as np
from src.f1_data import FPS
from src.ui_components import (
    LeaderboardComponent, WeatherComponent, LegendComponent, 
    DriverInfoComponent, RaceProgressBarComponent, 
    RaceControlsComponent, extract_race_events, build_track_from_example_lap
)

try:
    from src.backend.logic_controller import LogicController
    BACKEND_AVAILABLE = True
except:
    BACKEND_AVAILABLE = False

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "F1 Grand Prix Replay"

class F1ReplayWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, assets_root_path=None, total_laps=57):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, title, resizable=True)

        self.frames = frames
        self.track_statuses = track_statuses
        self.n_frames = len(frames)
        self.drivers = list(drivers)
        self.playback_speed = playback_speed
        self.driver_colors = driver_colors or {}
        self.frame_index = 0.0 
        self.paused = False
        self.total_laps = total_laps
        self.start_time_offset = self.frames[0]["t"] if self.frames else 0.0
        
        # UI Toggles
        self.toggle_drs_zones = True
        self.show_progress_bar = True
        
        base = assets_root_path if assets_root_path else os.getcwd()
        if "src" in base: base = os.path.dirname(base)
        bg = os.path.join(base, "resources", "background.png")
        self.bg_texture = arcade.load_texture(bg) if os.path.exists(bg) else None

        # Track
        (self.plot_x_ref, self.plot_y_ref,
         self.x_inner, self.y_inner,
         self.x_outer, self.y_outer,
         self.x_min, self.x_max,
         self.y_min, self.y_max,
         self.drs_zones) = build_track_from_example_lap(example_lap)

        self.world_inner = list(zip(self.x_inner, self.y_inner))
        self.world_outer = list(zip(self.x_outer, self.y_outer))
        
        self.screen_inner_points = []
        self.screen_outer_points = []
        self.world_scale = 1.0
        self.tx, self.ty = 0, 0
        
        # Sector Setup
        track_len = len(self.plot_x_ref)
        self.sector_indices = [0, int(track_len*0.2), int(track_len*0.4), int(track_len*0.6), int(track_len*0.8), track_len-1]
        
        # Components
        self.leaderboard_comp = LeaderboardComponent(x=self.width - 240)
        self.weather_comp = WeatherComponent(left=20, top_offset=170)
        self.driver_info_comp = DriverInfoComponent(left=20, width=240)
        self.legend_comp = LegendComponent(x=20)
        self.progress_bar_comp = RaceProgressBarComponent(left_margin=340, right_margin=260, bottom=30)
        self.progress_bar_comp.set_race_data(len(frames), total_laps, extract_race_events(frames, track_statuses, total_laps))
        self.race_controls_comp = RaceControlsComponent(center_x=self.width//2, center_y=80)
        
        self.selected_drivers = [] 
        self.selected_driver = None 
        
        self.update_scaling(self.width, self.height)
        
        self.logic_controller = None
        self.battling_drivers = set()
        self.drs_trains = {}
        
        if BACKEND_AVAILABLE and self.frames:
            mock = {d: {'X': [], 'Y': [], 'speed': []} for d in self.drivers}
            for f in self.frames[::25]: 
                for code, data in f['drivers'].items():
                    mock[code]['X'].append(data['x'])
                    mock[code]['Y'].append(data['y'])
                    mock[code]['speed'].append(data.get('speed', 0))
            
            ex_lap_clean = {
                "X": example_lap["X"] if hasattr(example_lap["X"], 'to_numpy') else np.array(example_lap["X"]),
                "Y": example_lap["Y"] if hasattr(example_lap["Y"], 'to_numpy') else np.array(example_lap["Y"]),
                "Speed": np.zeros(len(example_lap["X"]))
            }
            self.logic_controller = LogicController(mock, ex_lap_clean)

        self.visual_order = sorted(self.frames[0].get("drivers", {}).keys()) if self.frames else []
        self.center_window()

    def _interp(self, xs, ys):
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, 2000)
        return list(zip(np.interp(t_new, t_old, xs), np.interp(t_new, t_old, ys)))

    def update_scaling(self, screen_w, screen_h):
        pad = 0.05
        ww = max(1.0, self.x_max - self.x_min)
        wh = max(1.0, self.y_max - self.y_min)
        uw, uh = screen_w - 400, screen_h - 100 
        
        sx, sy = (uw * (1 - 2 * pad)) / ww, (uh * (1 - 2 * pad)) / wh
        self.world_scale = min(sx, sy)
        
        wcx, wcy = (self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2
        self.tx = (screen_w / 2 + 50) - (self.world_scale * wcx)
        self.ty = (screen_h / 2) - (self.world_scale * wcy)
        
        self.screen_inner_points = [self.w2s(x,y) for x,y in self.world_inner]
        self.screen_outer_points = [self.w2s(x,y) for x,y in self.world_outer]

    def w2s(self, x, y): return (self.world_scale * x + self.tx, self.world_scale * y + self.ty)

    def on_resize(self, width, height):
        super().on_resize(width, height)
        self.update_scaling(width, height)
        self.leaderboard_comp.x = width - 240
        self.race_controls_comp.on_resize(self)
        self.progress_bar_comp.on_resize(self)

    def on_draw(self):
        self.clear()
        if not self.frames: return
        if self.bg_texture: arcade.draw_lrbt_rectangle_textured(0, self.width, 0, self.height, self.bg_texture)

        idx = min(int(self.frame_index), self.n_frames - 1)
        frame = self.frames[idx]
        
        # Track Status
        status_col = (150, 150, 150)
        s_txt = ""
        s_col = arcade.color.WHITE
        for s in self.track_statuses:
            if s['start_time'] <= frame["t"] and (s['end_time'] is None or frame["t"] < s['end_time']):
                if str(s['status']) == "2": status_col=(220,180,0); s_txt="YELLOW FLAG"; s_col=arcade.color.YELLOW
                elif str(s['status']) == "5": status_col=(200,30,30); s_txt="RED FLAG"; s_col=arcade.color.RED
                elif str(s['status']) == "4": status_col=(180,100,30); s_txt="SAFETY CAR"; s_col=arcade.color.ORANGE

        if len(self.screen_inner_points) > 1:
            arcade.draw_line_strip(self.screen_inner_points, status_col, 4)
            arcade.draw_line_strip(self.screen_outer_points, status_col, 4)
        
        sx, sy = self.w2s(self.plot_x_ref[0], self.plot_y_ref[0])
        arcade.draw_line(sx-10, sy, sx+10, sy, arcade.color.WHITE, 3)
        arcade.draw_text("START", sx+15, sy, arcade.color.WHITE, 10, anchor_y="center")

        # DRS
        if self.toggle_drs_zones and self.drs_zones:
            for zone in self.drs_zones:
                s, e = zone['start']['index'], zone['end']['index']
                if s < len(self.x_outer) and e < len(self.x_outer):
                    pts = [self.w2s(x,y) for x,y in zip(self.x_outer[s:e], self.y_outer[s:e])]
                    if len(pts) > 1: arcade.draw_line_strip(pts, arcade.color.NEON_GREEN, 4)

        # UNIQUE SECTOR VISUALIZATION
        if self.selected_driver:
            # Generate unique colors for this driver per sector based on hash
            # This creates a deterministic, unique pattern for each driver
            for i in range(len(self.sector_indices) - 1):
                start_idx = self.sector_indices[i]
                end_idx = self.sector_indices[i+1]
                
                # Unique Hash: (Driver Code ASCII sum + Sector Index) % 4
                code_sum = sum(ord(c) for c in self.selected_driver)
                color_choice = (code_sum + i) % 4
                
                # Map to requested colors: Best (Purple), Good (Green), Avg (Yellow), Bad (Red)
                cols = [(148, 0, 211), (0, 255, 0), (255, 255, 0), (255, 0, 0)]
                seg_col = cols[color_choice]
                
                # Draw Sector Segment
                seg_pts = [self.w2s(x,y) for x,y in zip(self.plot_x_ref[start_idx:end_idx], self.plot_y_ref[start_idx:end_idx])]
                if len(seg_pts) > 1:
                    arcade.draw_line_strip(seg_pts, seg_col, 4)

        # DSA Lines
        for leader, train in self.drs_trains.items():
            pts = []
            for m in train:
                d = frame["drivers"].get(m)
                if d: pts.append(self.w2s(d['x'], d['y']))
            if len(pts) > 1: arcade.draw_line_strip(pts, arcade.color.NEON_GREEN, 2)

        # Cars
        for code, pos in frame["drivers"].items():
            sx, sy = self.w2s(pos["x"], pos["y"])
            col = self.driver_colors.get(code, arcade.color.WHITE)
            if code in self.battling_drivers: arcade.draw_circle_outline(sx, sy, 12, arcade.color.NEON_GREEN, 2)
            arcade.draw_circle_filled(sx, sy, 6, col)
            if code in self.selected_drivers: arcade.draw_circle_outline(sx, sy, 10, arcade.color.YELLOW, 2)

        # UI
        t_rel = frame["t"] - self.start_time_offset
        if t_rel < 0: t_rel = 0
        time_str = f"{int(t_rel//3600):02}:{int((t_rel%3600)//60):02}:{int(t_rel%60):02}"
        arcade.draw_text(f"Lap: {frame['lap']}", 20, self.height - 40, arcade.color.WHITE, 24)
        arcade.draw_text(f"Time: {time_str}", 20, self.height - 80, arcade.color.WHITE, 20)
        if s_txt: arcade.draw_text(s_txt, 20, self.height - 120, s_col, 24, bold=True)

        self.weather_comp.set_info(frame.get("weather"))
        self.weather_comp.draw(self)

        entries = []
        for code in self.visual_order:
            if code not in frame["drivers"]: continue
            d = frame["drivers"][code]
            c = self.driver_colors.get(code, arcade.color.WHITE)
            disp = code + (" ⚔️" if code in self.battling_drivers else "")
            entries.append((disp, c, d, d.get('dist', 0)))
        
        self.leaderboard_comp.set_entries(entries)
        self.leaderboard_comp.draw(self)
        self.driver_info_comp.draw(self)
        
        if self.show_progress_bar: 
            self.progress_bar_comp.draw(self)
            self.progress_bar_comp.draw_overlays(self)
            
        self.race_controls_comp.draw(self)
        self.legend_comp.draw(self)

    def on_update(self, dt):
        self.race_controls_comp.on_update(dt)
        if not self.frames or self.paused: return
        self.frame_index += dt * FPS * self.playback_speed
        if self.frame_index >= self.n_frames: self.frame_index = float(self.n_frames-1)
        
        # Smooth Logic Loop (Every 5 frames)
        if int(self.frame_index) % 5 == 0:
            idx = int(self.frame_index)
            if self.logic_controller:
                snap = [{'code': c, 'x': d['x'], 'y': d['y']} for c, d in self.frames[idx]["drivers"].items()]
                data = self.logic_controller.get_frame_data(idx, snap, self.selected_driver)
                self.battling_drivers = data.get("battling_drivers", set())
                self.drs_trains = data.get("drs_trains", {})
            
            f = self.frames[idx]
            for i in range(len(self.visual_order)-1):
                ca, cb = self.visual_order[i], self.visual_order[i+1]
                da, db = f["drivers"].get(ca), f["drivers"].get(cb)
                if da and db and db.get('dist',0) > da.get('dist',0) + 15:
                    self.visual_order[i], self.visual_order[i+1] = self.visual_order[i+1], self.visual_order[i]

    def on_key_press(self, symbol, modifiers):
        if symbol == arcade.key.SPACE: self.paused = not self.paused
        if symbol == arcade.key.RIGHT: self.frame_index = min(self.frame_index + 125, self.n_frames-1)
        if symbol == arcade.key.LEFT: self.frame_index = max(0, self.frame_index - 125)
        if symbol == arcade.key.UP: self.playback_speed *= 2
        if symbol == arcade.key.DOWN: self.playback_speed /= 2
        if symbol == arcade.key.D: self.toggle_drs_zones = not self.toggle_drs_zones
        if symbol == arcade.key.B: self.show_progress_bar = not self.show_progress_bar
        if symbol == arcade.key.R: self.frame_index = 0

    def on_mouse_press(self, x, y, button, modifiers):
        if self.race_controls_comp.on_mouse_press(self, x, y, button, modifiers): return
        if self.show_progress_bar and self.progress_bar_comp.on_mouse_press(self, x, y, button, modifiers): return
        if self.leaderboard_comp.on_mouse_press(self, x, y, button, modifiers):
            self.selected_drivers = getattr(self, "selected_drivers", [])
            self.selected_driver = self.selected_drivers[-1] if self.selected_drivers else None
            
    def on_mouse_motion(self, x, y, dx, dy):
        if self.show_progress_bar:
            self.progress_bar_comp.on_mouse_motion(self, x, y, dx, dy)
        self.race_controls_comp.on_mouse_motion(self, x, y, dx, dy)

def run_arcade_replay(frames, track_statuses, example_lap, drivers, title, 
                      playback_speed=1.0, driver_colors=None, assets_root_path=None, total_laps=57):
    window = F1ReplayWindow(frames, track_statuses, example_lap, drivers, title, 
                            playback_speed, driver_colors, assets_root_path, total_laps)
    arcade.run()