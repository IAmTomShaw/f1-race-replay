import arcade
import numpy as np
from src.f1_data import FPS
from src.ui_components import build_track_from_example_lap
import fastf1.plotting


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080


class TrackBattleWindow(arcade.Window):
    def __init__(self, session, driver1, driver2, playback_speed=1.0):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT,
                         f"{session.event['EventName']} - {driver1} vs {driver2} Battle",
                         resizable=True)

        self.session = session
        self.driver1 = driver1
        self.driver2 = driver2
        self.playback_speed = playback_speed

        # Get fastest laps
        lap1 = session.laps.pick_driver(driver1).pick_fastest()
        lap2 = session.laps.pick_driver(driver2).pick_fastest()

        if lap1 is None or lap2 is None:
            raise ValueError(
                f"Could not find valid laps for {driver1} or {driver2}")

        self.lap1 = lap1
        self.lap2 = lap2

        # Get telemetry
        tel1 = lap1.get_telemetry().add_distance()
        tel2 = lap2.get_telemetry().add_distance()

        # Get driver info
        driver1_info = session.get_driver(driver1)
        driver2_info = session.get_driver(driver2)

        self.driver1_name = f"{driver1_info['FirstName']} {driver1_info['LastName']}"
        self.driver2_name = f"{driver2_info['FirstName']} {driver2_info['LastName']}"

        # Get driver colors
        color1_hex = fastf1.plotting.get_driver_color(driver1, session)
        color2_hex = fastf1.plotting.get_driver_color(driver2, session)
        self.color1 = self._hex_to_rgb(color1_hex)
        self.color2 = self._hex_to_rgb(color2_hex)

        # Get sector times
        self.sector1_time1 = lap1['Sector1Time'].total_seconds(
        ) if lap1['Sector1Time'] is not None else None
        self.sector2_time1 = lap1['Sector2Time'].total_seconds(
        ) if lap1['Sector2Time'] is not None else None
        self.sector3_time1 = lap1['Sector3Time'].total_seconds(
        ) if lap1['Sector3Time'] is not None else None

        self.sector1_time2 = lap2['Sector1Time'].total_seconds(
        ) if lap2['Sector1Time'] is not None else None
        self.sector2_time2 = lap2['Sector2Time'].total_seconds(
        ) if lap2['Sector2Time'] is not None else None
        self.sector3_time2 = lap2['Sector3Time'].total_seconds(
        ) if lap2['Sector3Time'] is not None else None

        # Interpolate telemetry to same number of points
        self.num_points = min(len(tel1), len(tel2))

        idx1 = np.linspace(0, len(tel1) - 1, self.num_points, dtype=int)
        idx2 = np.linspace(0, len(tel2) - 1, self.num_points, dtype=int)

        # Store positions in world coordinates
        self.positions1_world = [
            (tel1['X'].iloc[i], tel1['Y'].iloc[i]) for i in idx1]
        self.positions2_world = [
            (tel2['X'].iloc[i], tel2['Y'].iloc[i]) for i in idx2]

        # Store distance for sector markers
        self.distances1 = [tel1['Distance'].iloc[i] for i in idx1]
        self.distances2 = [tel2['Distance'].iloc[i] for i in idx2]

        # Time arrays
        self.time1 = np.linspace(
            0, lap1['LapTime'].total_seconds(), self.num_points)
        self.time2 = np.linspace(
            0, lap2['LapTime'].total_seconds(), self.num_points)

        # Calculate time difference
        self.time_diff = abs(
            lap1['LapTime'].total_seconds() - lap2['LapTime'].total_seconds())
        self.faster_driver = driver1 if lap1['LapTime'] < lap2['LapTime'] else driver2

        # Build track from telemetry (use driver1's full telemetry as example)
        example_lap = tel1
        (self.plot_x_ref, self.plot_y_ref,
         self.x_inner, self.y_inner,
         self.x_outer, self.y_outer,
         self.x_min, self.x_max,
         self.y_min, self.y_max) = build_track_from_example_lap(example_lap)

        # Find sector marker positions from telemetry
        self.sector_markers = self._find_sector_markers(tel1)

        # Interpolate track boundaries
        self.world_inner_points = self._interpolate_points(
            self.x_inner, self.y_inner)
        self.world_outer_points = self._interpolate_points(
            self.x_outer, self.y_outer)

        # Screen coordinates (calculated in update_scaling)
        self.screen_inner_points = []
        self.screen_outer_points = []
        self.positions1_screen = []
        self.positions2_screen = []
        self.sector_markers_screen = []

        # Scaling parameters
        self.world_scale = 1.0
        self.tx = 0
        self.ty = 0

        # Animation state
        self.frame_index = 0.0
        self.paused = False
        self.trail_length = 150

        arcade.set_background_color(arcade.color.BLACK)

        # Initial scaling
        self.update_scaling(self.width, self.height)

    def _hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _interpolate_points(self, xs, ys, interp_points=2000):
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def _find_sector_markers(self, telemetry):
        """Find the positions of sector boundaries on the track."""
        markers = []

        # Get distances where sectors change
        # Sector 1 ends where Sector 2 starts
        # Sector 2 ends where Sector 3 starts

        # Find approximate sector boundaries (typically at 1/3 and 2/3 of track)
        total_distance = telemetry['Distance'].max()

        # Sector 1 -> 2 boundary (around 1/3 of track)
        sector1_end_dist = total_distance / 3
        idx1 = (telemetry['Distance'] - sector1_end_dist).abs().idxmin()
        markers.append({
            'sector': 1,
            'x': telemetry.loc[idx1, 'X'],
            'y': telemetry.loc[idx1, 'Y'],
            'distance': telemetry.loc[idx1, 'Distance']
        })

        # Sector 2 -> 3 boundary (around 2/3 of track)
        sector2_end_dist = 2 * total_distance / 3
        idx2 = (telemetry['Distance'] - sector2_end_dist).abs().idxmin()
        markers.append({
            'sector': 2,
            'x': telemetry.loc[idx2, 'X'],
            'y': telemetry.loc[idx2, 'Y'],
            'distance': telemetry.loc[idx2, 'Distance']
        })

        return markers

    def update_scaling(self, screen_w, screen_h):
        """Calculate scaling to fit track in window."""
        padding = 0.1

        world_w = max(1.0, self.x_max - self.x_min)
        world_h = max(1.0, self.y_max - self.y_min)

        usable_w = screen_w * (1 - 2 * padding)
        usable_h = screen_h * (1 - 2 * padding)

        scale_x = usable_w / world_w
        scale_y = usable_h / world_h
        self.world_scale = min(scale_x, scale_y)

        # Center the track
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2
        screen_cx = screen_w / 2
        screen_cy = screen_h / 2

        self.tx = screen_cx - self.world_scale * world_cx
        self.ty = screen_cy - self.world_scale * world_cy

        # Update screen coordinates
        self.screen_inner_points = [self.world_to_screen(
            x, y) for x, y in self.world_inner_points]
        self.screen_outer_points = [self.world_to_screen(
            x, y) for x, y in self.world_outer_points]
        self.positions1_screen = [self.world_to_screen(
            x, y) for x, y in self.positions1_world]
        self.positions2_screen = [self.world_to_screen(
            x, y) for x, y in self.positions2_world]

        # Update sector marker screen positions
        self.sector_markers_screen = []
        for marker in self.sector_markers:
            sx, sy = self.world_to_screen(marker['x'], marker['y'])
            self.sector_markers_screen.append({
                'sector': marker['sector'],
                'x': sx,
                'y': sy,
                'distance': marker['distance']
            })

    def on_resize(self, width, height):
        super().on_resize(width, height)
        self.update_scaling(width, height)

    def world_to_screen(self, x, y):
        sx = self.world_scale * x + self.tx
        sy = self.world_scale * y + self.ty
        return sx, sy

    def _get_current_sector(self, distance):
        """Determine which sector the car is in based on distance."""
        if len(self.sector_markers) < 2:
            return 1

        if distance < self.sector_markers[0]['distance']:
            return 1
        elif distance < self.sector_markers[1]['distance']:
            return 2
        else:
            return 3

    def on_draw(self):
        self.clear()

        # Draw track outline
        if len(self.screen_inner_points) > 1:
            arcade.draw_line_strip(self.screen_inner_points, (80, 80, 80), 3)
        if len(self.screen_outer_points) > 1:
            arcade.draw_line_strip(self.screen_outer_points, (80, 80, 80), 3)

        # Draw sector markers
        for marker in self.sector_markers_screen:
            # Draw vertical line across track
            arcade.draw_circle_filled(
                marker['x'], marker['y'], 6, arcade.color.YELLOW)
            arcade.draw_circle_outline(
                marker['x'], marker['y'], 8, arcade.color.WHITE, 2)

            # Draw sector label
            label = f"S{marker['sector']}"
            arcade.Text(label, marker['x'], marker['y'] + 15,
                        arcade.color.YELLOW, 14, anchor_x="center", bold=True).draw()

        # Current frame
        frame = min(int(self.frame_index), self.num_points - 1)

        # Draw trails
        if frame > 0:
            trail_start = max(0, frame - self.trail_length)

            # Driver 1 trail
            if frame > 1:
                trail1 = self.positions1_screen[trail_start:frame+1]
                if len(trail1) > 1:
                    arcade.draw_line_strip(trail1, self.color1, 4)

            # Driver 2 trail
            if frame > 1:
                trail2 = self.positions2_screen[trail_start:frame+1]
                if len(trail2) > 1:
                    arcade.draw_line_strip(trail2, self.color2, 4)

        # Draw current positions
        if frame < self.num_points:
            # Driver 1
            arcade.draw_circle_filled(
                *self.positions1_screen[frame], 8, self.color1)
            arcade.draw_circle_outline(
                *self.positions1_screen[frame], 10, arcade.color.WHITE, 2)

            # Driver 2
            arcade.draw_circle_filled(
                *self.positions2_screen[frame], 8, self.color2)
            arcade.draw_circle_outline(
                *self.positions2_screen[frame], 10, arcade.color.WHITE, 2)

        # Draw HUD
        # Title
        title = f"{self.session.event['EventName']} - Fastest Lap Battle"
        arcade.Text(title, self.width / 2, self.height - 30,
                    arcade.color.WHITE, 28, anchor_x="center", bold=True).draw()

        # Format lap times as MM:SS.mmm
        def format_laptime(td):
            total_seconds = td.total_seconds()
            minutes = int(total_seconds // 60)
            seconds = total_seconds % 60
            return f"{minutes}:{seconds:06.3f}"

        # Driver 1 info (left side)
        y_offset = self.height - 80
        arcade.Text(f"{self.driver1} - {self.driver1_name}", 20, y_offset,
                    self.color1, 22, bold=True).draw()
        arcade.Text(f"Lap Time: {format_laptime(self.lap1['LapTime'])}", 20, y_offset - 35,
                    arcade.color.WHITE, 18).draw()

        if frame < self.num_points:
            arcade.Text(f"Current: {self.time1[frame]:.3f}s", 20, y_offset - 65,
                        (200, 200, 200), 16).draw()

            # Current sector
            current_sector1 = self._get_current_sector(self.distances1[frame])
            arcade.Text(f"Sector {current_sector1}", 20, y_offset - 95,
                        (150, 150, 150), 14).draw()

        # Sector times for driver 1
        sector_y = y_offset - 130
        if self.sector1_time1 is not None:
            color = arcade.color.GREEN if self.sector1_time1 < (
                self.sector1_time2 or float('inf')) else arcade.color.WHITE
            arcade.Text(f"S1: {self.sector1_time1:.3f}s", 20, sector_y,
                        color, 16).draw()
        if self.sector2_time1 is not None:
            color = arcade.color.GREEN if self.sector2_time1 < (
                self.sector2_time2 or float('inf')) else arcade.color.WHITE
            arcade.Text(f"S2: {self.sector2_time1:.3f}s", 20, sector_y - 30,
                        color, 16).draw()
        if self.sector3_time1 is not None:
            color = arcade.color.GREEN if self.sector3_time1 < (
                self.sector3_time2 or float('inf')) else arcade.color.WHITE
            arcade.Text(f"S3: {self.sector3_time1:.3f}s", 20, sector_y - 60,
                        color, 16).draw()

        # Driver 2 info (right side)
        arcade.Text(f"{self.driver2} - {self.driver2_name}", self.width - 20, y_offset,
                    self.color2, 22, bold=True, anchor_x="right").draw()
        arcade.Text(f"Lap Time: {format_laptime(self.lap2['LapTime'])}", self.width - 20, y_offset - 35,
                    arcade.color.WHITE, 18, anchor_x="right").draw()

        if frame < self.num_points:
            arcade.Text(f"Current: {self.time2[frame]:.3f}s", self.width - 20, y_offset - 65,
                        (200, 200, 200), 16, anchor_x="right").draw()

            # Current sector
            current_sector2 = self._get_current_sector(self.distances2[frame])
            arcade.Text(f"Sector {current_sector2}", self.width - 20, y_offset - 95,
                        (150, 150, 150), 14, anchor_x="right").draw()

        # Sector times for driver 2
        if self.sector1_time2 is not None:
            color = arcade.color.GREEN if self.sector1_time2 < (
                self.sector1_time1 or float('inf')) else arcade.color.WHITE
            arcade.Text(f"S1: {self.sector1_time2:.3f}s", self.width - 20, sector_y,
                        color, 16, anchor_x="right").draw()
        if self.sector2_time2 is not None:
            color = arcade.color.GREEN if self.sector2_time2 < (
                self.sector2_time1 or float('inf')) else arcade.color.WHITE
            arcade.Text(f"S2: {self.sector2_time2:.3f}s", self.width - 20, sector_y - 30,
                        color, 16, anchor_x="right").draw()
        if self.sector3_time2 is not None:
            color = arcade.color.GREEN if self.sector3_time2 < (
                self.sector3_time1 or float('inf')) else arcade.color.WHITE
            arcade.Text(f"S3: {self.sector3_time2:.3f}s", self.width - 20, sector_y - 60,
                        color, 16, anchor_x="right").draw()

        # Time difference (center)
        diff_text = f"{self.faster_driver} faster by {self.time_diff:.3f}s"
        arcade.Text(diff_text, self.width / 2, y_offset - 35,
                    arcade.color.WHITE, 20, anchor_x="center").draw()

        # Controls (bottom center)
        controls = "SPACE: Pause | R: Restart | ↑/↓: Speed | ESC: Exit"
        arcade.Text(controls, self.width / 2, 30,
                    (150, 150, 150), 16, anchor_x="center").draw()

        # Playback speed indicator
        speed_text = f"Speed: {self.playback_speed:.1f}x"
        arcade.Text(speed_text, self.width / 2, 60,
                    arcade.color.LIGHT_GRAY, 18, anchor_x="center").draw()

        # Paused indicator
        if self.paused:
            arcade.Text("PAUSED", self.width / 2, self.height / 2,
                        arcade.color.YELLOW, 48, anchor_x="center", bold=True).draw()

    def on_update(self, delta_time: float):
        if self.paused:
            return

        self.frame_index += delta_time * FPS * self.playback_speed
        if self.frame_index >= self.num_points:
            self.frame_index = 0.0  # Loop

    def on_key_press(self, symbol: int, modifiers: int):
        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
        elif symbol == arcade.key.R:
            self.frame_index = 0.0
        elif symbol == arcade.key.UP:
            self.playback_speed = min(4.0, self.playback_speed * 2.0)
        elif symbol == arcade.key.DOWN:
            self.playback_speed = max(0.25, self.playback_speed / 2.0)
        elif symbol == arcade.key.KEY_1:
            self.playback_speed = 0.5
        elif symbol == arcade.key.KEY_2:
            self.playback_speed = 1.0
        elif symbol == arcade.key.KEY_3:
            self.playback_speed = 2.0
        elif symbol == arcade.key.KEY_4:
            self.playback_speed = 4.0
        elif symbol == arcade.key.ESCAPE:
            self.close()


def run_track_battle(session, driver1, driver2, playback_speed=1.0):
    """
    Run the track battle visualization.

    Args:
        session: FastF1 session object (already loaded)
        driver1: First driver abbreviation (e.g., 'VER')
        driver2: Second driver abbreviation (e.g., 'LEC')
        playback_speed: Initial playback speed (default: 1.0)
    """
    try:
        window = TrackBattleWindow(session, driver1, driver2, playback_speed)
        arcade.run()
    except ValueError as e:
        print(f"Error: {e}")
