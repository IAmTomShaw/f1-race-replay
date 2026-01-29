import arcade
import numpy as np
from typing import Dict, Tuple, Optional
from src.race_comparison import RaceComparison, ViewMode, SyncMode

# Constants
TRACK_COLOR = (200, 200, 200)
TRACK_WIDTH = 8
CAR_SIZE = 10

class ComparisonViewer(arcade.Window):
    def __init__(self, comparison: RaceComparison, example_lap_a, example_lap_b, circuit_rotation_a: float, circuit_rotation_b: float):
        super().__init__(1920, 1080, "F1 Race Comparison", resizable=True)
        
        self.comparison = comparison
        self.example_lap_a = example_lap_a
        self.example_lap_b = example_lap_b
        self.circuit_rotation_a = circuit_rotation_a
        self.circuit_rotation_b = circuit_rotation_b
        
        # Playback state
        self.current_frame = 0
        self.total_frames = comparison.get_total_frames()
        self.paused = False
        self.playback_speed = 1.0
        self.time_accumulator = 0.0
        
        # View settings
        self.show_deltas = True
        self.show_labels = True
        self.selected_driver = None
        
        # Track rendering data for both races
        self._setup_track_rendering()
        
        # UI colors
        self.ui_bg_color = (20, 20, 25)
        self.text_color = (255, 255, 255)
        self.delta_positive_color = (0, 255, 0)  # Race A faster
        self.delta_negative_color = (255, 0, 0)  # Race B faster
        
        arcade.set_background_color(self.ui_bg_color)
    
    def _setup_track_rendering(self):
        """Extract and normalize track coordinates for both races"""
        # Track A
        x_coords_a = self.example_lap_a['X'].to_numpy()
        y_coords_a = self.example_lap_a['Y'].to_numpy()
        
        self.track_a = {
            'x_min': x_coords_a.min(),
            'x_max': x_coords_a.max(),
            'y_min': y_coords_a.min(),
            'y_max': y_coords_a.max(),
            'width': x_coords_a.max() - x_coords_a.min(),
            'height': y_coords_a.max() - y_coords_a.min(),
            'points': list(zip(x_coords_a, y_coords_a))
        }
        
        # Track B
        x_coords_b = self.example_lap_b['X'].to_numpy()
        y_coords_b = self.example_lap_b['Y'].to_numpy()
        
        self.track_b = {
            'x_min': x_coords_b.min(),
            'x_max': x_coords_b.max(),
            'y_min': y_coords_b.min(),
            'y_max': y_coords_b.max(),
            'width': x_coords_b.max() - x_coords_b.min(),
            'height': y_coords_b.max() - y_coords_b.min(),
            'points': list(zip(x_coords_b, y_coords_b))
        }
    
    def track_to_screen(self, x: float, y: float, viewport_rect: Tuple[float, float, float, float], 
                       track_data: dict, rotation: float) -> Tuple[float, float]:
        """Convert track coordinates to screen coordinates within a viewport"""
        vp_x, vp_y, vp_width, vp_height = viewport_rect
        
        # Apply circuit rotation
        angle = np.radians(rotation)
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        
        # Center the track
        centered_x = x - (track_data['x_min'] + track_data['width'] / 2)
        centered_y = y - (track_data['y_min'] + track_data['height'] / 2)
        
        # Rotate
        rotated_x = centered_x * cos_a - centered_y * sin_a
        rotated_y = centered_x * sin_a + centered_y * cos_a
        
        # Scale to fit viewport with padding - adaptive based on viewport size
        padding = min(vp_width, vp_height) * 0.1  # 10% padding
        available_width = vp_width - 2 * padding
        available_height = vp_height - 2 * padding
        
        # Calculate scale to fit track in viewport while maintaining aspect ratio
        scale_x = available_width / track_data['width']
        scale_y = available_height / track_data['height']
        scale = min(scale_x, scale_y) * 0.85  # Use 85% of available space
        
        screen_x = vp_x + vp_width / 2 + rotated_x * scale
        screen_y = vp_y + vp_height / 2 + rotated_y * scale
        
        return screen_x, screen_y
    
    def draw_track(self, viewport_rect: Tuple[float, float, float, float], track_data: dict, 
                   rotation: float, color: Tuple[int, int, int] = TRACK_COLOR):
        """Draw track outline in specified viewport"""
        if len(track_data['points']) < 2:
            return
        
        screen_points = [self.track_to_screen(x, y, viewport_rect, track_data, rotation) 
                        for x, y in track_data['points']]
        
        # Draw track as line strip
        for i in range(len(screen_points) - 1):
            arcade.draw_line(
                screen_points[i][0], screen_points[i][1],
                screen_points[i+1][0], screen_points[i+1][1],
                color, TRACK_WIDTH
            )
        
        # Close the loop
        arcade.draw_line(
            screen_points[-1][0], screen_points[-1][1],
            screen_points[0][0], screen_points[0][1],
            color, TRACK_WIDTH
        )
    
    def draw_car(self, x: float, y: float, color: Tuple[int, int, int], viewport_rect: Tuple[float, float, float, float], 
                 track_data: dict, rotation: float, alpha: int = 255, label: str = None):
        """Draw a car at track coordinates"""
        screen_x, screen_y = self.track_to_screen(x, y, viewport_rect, track_data, rotation)
        
        # Draw car as circle
        arcade.draw_circle_filled(screen_x, screen_y, CAR_SIZE, (*color, alpha))
        arcade.draw_circle_outline(screen_x, screen_y, CAR_SIZE, (255, 255, 255), 2)
        
        # Draw label if provided
        if label and self.show_labels:
            arcade.draw_text(
                label,
                screen_x, screen_y + CAR_SIZE + 5,
                (255, 255, 255),
                10,
                anchor_x="center"
            )
    
    def draw_split_view(self):
        """Draw two tracks side-by-side"""
        # Get current screen dimensions
        screen_width = self.width
        screen_height = self.height
        hud_height = 150
        
        # Split screen vertically
        left_viewport = (0, 0, screen_width // 2, screen_height - hud_height)
        right_viewport = (screen_width // 2, 0, screen_width // 2, screen_height - hud_height)
        
        frame_a, frame_b = self.comparison.get_synchronized_frames(self.current_frame)
        
        # Draw Race A (left) with its own track
        self.draw_track(left_viewport, self.track_a, self.circuit_rotation_a)
        for driver_code, driver_data in frame_a['drivers'].items():
            color = self.comparison.race_a.driver_colors.get(driver_code, (128, 128, 128))
            self.draw_car(driver_data['x'], driver_data['y'], color, left_viewport, 
                         self.track_a, self.circuit_rotation_a, label=driver_code)
        
        # Draw Race B (right) with its own track
        self.draw_track(right_viewport, self.track_b, self.circuit_rotation_b)
        for driver_code, driver_data in frame_b['drivers'].items():
            color = self.comparison.race_b.driver_colors.get(driver_code, (128, 128, 128))
            self.draw_car(driver_data['x'], driver_data['y'], color, right_viewport, 
                         self.track_b, self.circuit_rotation_b, label=driver_code)
        
        # Draw divider line
        arcade.draw_line(screen_width // 2, 0, screen_width // 2, screen_height - hud_height, (100, 100, 100), 2)
        
        # Draw labels
        arcade.draw_text(
            f"{self.comparison.race_a.event_name} ({self.comparison.race_a.year})",
            screen_width // 4, screen_height - 130,
            self.text_color, 16, anchor_x="center", bold=True
        )
        arcade.draw_text(
            f"{self.comparison.race_b.event_name} ({self.comparison.race_b.year})",
            3 * screen_width // 4, screen_height - 130,
            self.text_color, 16, anchor_x="center", bold=True
        )
        
        # Draw leaderboards for both races
        self.draw_leaderboard(frame_a, 10, screen_height - 180, "Race A")
        self.draw_leaderboard(frame_b, screen_width // 2 + 10, screen_height - 180, "Race B")
    
    def draw_overlay_view(self):
        """Draw single track with both races overlaid - uses Race A track as base"""
        screen_width = self.width
        screen_height = self.height
        hud_height = 150
        
        viewport = (0, 0, screen_width, screen_height - hud_height)
        
        frame_a, frame_b = self.comparison.get_synchronized_frames(self.current_frame)
        
        # Draw Race A track
        self.draw_track(viewport, self.track_a, self.circuit_rotation_a)
        
        # Note: In overlay mode, we only show Race A track
        # If tracks are different, this mode won't make visual sense
        # Consider disabling overlay mode for different circuits
        
        # Draw Race A cars (solid)
        for driver_code, driver_data in frame_a['drivers'].items():
            color = self.comparison.race_a.driver_colors.get(driver_code, (128, 128, 128))
            self.draw_car(driver_data['x'], driver_data['y'], color, viewport, 
                         self.track_a, self.circuit_rotation_a, alpha=255, label=driver_code)
        
        # Legend
        legend_x = 20
        legend_y = screen_height - 180
        arcade.draw_text("Showing:", legend_x, legend_y, self.text_color, 12)
        arcade.draw_text(f"{self.comparison.race_a.event_name} ({self.comparison.race_a.year})", 
                        legend_x + 80, legend_y, self.text_color, 12, bold=True)
        
        # Warning if different circuits
        if self.comparison.race_a.event_name != self.comparison.race_b.event_name:
            arcade.draw_text(
                "⚠ Overlay mode only shows Race A track (different circuits)",
                screen_width // 2, screen_height - 200,
                (255, 200, 0), 11, anchor_x="center"
            )
    
    def draw_difference_view(self):
        """Draw position delta visualization - uses Race A track"""
        screen_width = self.width
        screen_height = self.height
        hud_height = 250
        
        viewport = (0, 0, screen_width, screen_height - hud_height)
        
        frame_a, frame_b = self.comparison.get_synchronized_frames(self.current_frame)
        metrics = self.comparison.get_comparison_metrics(self.current_frame)
        
        # Draw Race A track
        self.draw_track(viewport, self.track_a, self.circuit_rotation_a)
        
        # Draw cars colored by position delta
        position_deltas = metrics['position_deltas']
        
        for driver_code, driver_data in frame_a['drivers'].items():
            if driver_code in position_deltas:
                delta = position_deltas[driver_code]
                # Green if better in race A, red if worse
                if delta < 0:  # Better position in race A (lower position number)
                    color = self.delta_positive_color
                elif delta > 0:
                    color = self.delta_negative_color
                else:
                    color = (200, 200, 200)
            else:
                color = (128, 128, 128)
            
            label = f"{driver_code} ({delta:+d})" if driver_code in position_deltas else driver_code
            self.draw_car(driver_data['x'], driver_data['y'], color, viewport, 
                         self.track_a, self.circuit_rotation_a, label=label)
        
        # Draw delta explanation
        arcade.draw_text(
            "Green = Better position in Race A | Red = Better position in Race B",
            screen_width // 2, screen_height - 180,
            self.text_color, 14, anchor_x="center"
        )
    
    def draw_hud(self):
        """Draw HUD with comparison info"""
        screen_width = self.width
        screen_height = self.height
        
        frame_a, frame_b = self.comparison.get_synchronized_frames(self.current_frame)
        metrics = self.comparison.get_comparison_metrics(self.current_frame)
        
        # Race info
        y_pos = screen_height - 50
        
        # Lap info
        arcade.draw_text(
            f"Lap {metrics['lap_a']}/{self.comparison.race_a.total_laps}",
            20, y_pos,
            self.text_color, 14, bold=True
        )
        
        arcade.draw_text(
            f"Lap {metrics['lap_b']}/{self.comparison.race_b.total_laps}",
            20, y_pos - 25,
            (150, 150, 150), 12
        )
        
        # Time info
        arcade.draw_text(
            f"Time: {self._format_time(metrics['time_a'])}",
            200, y_pos,
            self.text_color, 14
        )
        
        arcade.draw_text(
            f"Time: {self._format_time(metrics['time_b'])}",
            200, y_pos - 25,
            (150, 150, 150), 12
        )
        
        # View mode
        view_mode_text = f"View: {self.comparison.current_view.value.upper()}"
        arcade.draw_text(
            view_mode_text,
            screen_width - 200, y_pos,
            self.text_color, 14, anchor_x="right"
        )
        
        # Sync mode
        sync_mode_text = f"Sync: {self.comparison.sync_mode.value.upper()}"
        arcade.draw_text(
            sync_mode_text,
            screen_width - 200, y_pos - 25,
            (150, 150, 150), 12, anchor_x="right"
        )
        
        # Controls hint
        controls_text = "V: View | S: Sync | SPACE: Pause | ←→: Seek | ↑↓: Speed"
        arcade.draw_text(
            controls_text,
            screen_width // 2, 20,
            (150, 150, 150), 10, anchor_x="center"
        )
        
        # Progress bar (simple line version)
        progress = self.current_frame / max(self.total_frames - 1, 1)
        bar_width = screen_width - 40
        bar_x = 20
        bar_y = 50
        
        # Background line
        arcade.draw_line(bar_x, bar_y, bar_x + bar_width, bar_y, (60, 60, 60), 6)
        # Progress line
        arcade.draw_line(bar_x, bar_y, bar_x + bar_width * progress, bar_y, (255, 24, 1), 6)
    
    def draw_leaderboard(self, frame: dict, x: int, y: int, title: str):
        """Draw a compact leaderboard for a race"""
        drivers = frame['drivers']
        
        # Sort drivers by position
        sorted_drivers = sorted(drivers.items(), key=lambda d: d[1]['position'])
        
        # Draw title
        arcade.draw_text(title, x, y, (150, 150, 150), 10, bold=True)
        
        # Draw top 10 drivers
        y_offset = y - 20
        for i, (driver_code, driver_data) in enumerate(sorted_drivers[:10]):
            position = driver_data['position']
            color = (255, 255, 255) if i < 3 else (180, 180, 180)  # Highlight top 3
            
            # Position and driver code
            text = f"{position}. {driver_code}"
            arcade.draw_text(text, x, y_offset, color, 9)
            
            y_offset -= 15
    
    def _format_time(self, seconds: float) -> str:
        """Format time in MM:SS.mmm"""
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes:02d}:{secs:06.3f}"
    
    def on_draw(self):
        """Main draw loop"""
        self.clear()
        
        # Draw based on current view mode
        if self.comparison.current_view == ViewMode.SPLIT:
            self.draw_split_view()
        elif self.comparison.current_view == ViewMode.OVERLAY:
            self.draw_overlay_view()
        elif self.comparison.current_view == ViewMode.DIFFERENCE:
            self.draw_difference_view()
        
        # Always draw HUD
        self.draw_hud()
    
    def on_update(self, delta_time: float):
        """Update playback"""
        if self.paused:
            return
        
        self.time_accumulator += delta_time * self.playback_speed
        
        # Advance frame at ~25 FPS
        frame_duration = 1.0 / 25.0
        
        while self.time_accumulator >= frame_duration:
            self.time_accumulator -= frame_duration
            self.current_frame += 1
            
            if self.current_frame >= self.total_frames:
                self.current_frame = 0  # Loop
    
    def on_resize(self, width: int, height: int):
        """Handle window resize"""
        super().on_resize(width, height)
        # Redraw will happen automatically on next frame
    
    def on_key_press(self, key, modifiers):
        """Handle keyboard input"""
        # Playback controls
        if key == arcade.key.SPACE:
            self.paused = not self.paused
        
        elif key == arcade.key.LEFT:
            self.current_frame = max(0, self.current_frame - 25)  # 1 second back
        
        elif key == arcade.key.RIGHT:
            self.current_frame = min(self.total_frames - 1, self.current_frame + 25)  # 1 second forward
        
        elif key == arcade.key.UP:
            self.playback_speed = min(4.0, self.playback_speed * 2)
        
        elif key == arcade.key.DOWN:
            self.playback_speed = max(0.25, self.playback_speed / 2)
        
        elif key == arcade.key.R:
            self.current_frame = 0
        
        # View controls
        elif key == arcade.key.V:
            self.comparison.toggle_view_mode()
        
        elif key == arcade.key.S:
            # Cycle sync modes
            modes = list(SyncMode)
            current_idx = modes.index(self.comparison.sync_mode)
            new_mode = modes[(current_idx + 1) % len(modes)]
            self.comparison.change_sync_mode(new_mode)
            # Reset to start when changing sync mode
            self.current_frame = 0
        
        elif key == arcade.key.L:
            self.show_labels = not self.show_labels
        
        elif key == arcade.key.D:
            self.show_deltas = not self.show_deltas
        
        elif key == arcade.key.ESCAPE:
            self.close()


def run_comparison_viewer(comparison: RaceComparison, example_lap_a, example_lap_b, 
                          circuit_rotation_a: float, circuit_rotation_b: float):
    """Entry point to launch comparison viewer"""
    window = ComparisonViewer(comparison, example_lap_a, example_lap_b, 
                              circuit_rotation_a, circuit_rotation_b)
    arcade.run()