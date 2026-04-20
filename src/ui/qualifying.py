import arcade
import os
from .base import BaseComponent
from src.lib.time import format_time

class QualifyingLapTimeComponent(BaseComponent):
    """
    A component to display the qualifying lap time with sector times and current tyre info.
    """
    def __init__(self, x: int = 150, y: int = 60):
        self.x = x
        self.y = y
        self.fastest_driver = None
        self.fastest_driver_sector_times = None
        self._tyre_textures = {}
        self._time_elapsed = 0.0
        self._delta_sector = None
        self._last_completed_sector = -1
        # Import the tyre textures from the images/tyres folder (all files)
        tyres_folder = os.path.join("images", "tyres")
        if os.path.exists(tyres_folder):
            for filename in os.listdir(tyres_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(tyres_folder, filename)
                    self._tyre_textures[texture_name] = arcade.load_texture(texture_path)

    def on_update(self, delta_time: float):
        """
        Update logic for time difference in fastest driver and current driver (Delta sector time)
        """
        if self._delta_sector is not None:
            self._time_elapsed += delta_time
            if self._time_elapsed >= 1.0:
                # Reset delta display after 1 second (but keep sector completion tracking)
                self._delta_sector = None
                self._time_elapsed = 0.0

    def reset(self):
        self._delta_sector = None
        self._time_elapsed = 0.0
        self._last_completed_sector = -1

    def draw(self, window):
        if not hasattr(window, 'loaded_telemetry') or not window.loaded_telemetry:
            return
        sector_times = window.loaded_telemetry.get("sector_times") if isinstance(window.loaded_telemetry, dict) else {}
        if not sector_times:
            sector_times = {}
        compound = window.loaded_telemetry.get("compound", "?")
        
        # Get driver info
        driver_full_name = None
        fastest_driver_full_name = None
        driver_color = arcade.color.ANTI_FLASH_WHITE
        driver_code = getattr(window, 'loaded_driver_code', None)
        if driver_code:
            telemetry = window.data.get("telemetry")
            if telemetry:
                driver_full_name = telemetry.get(driver_code, {}).get("full_name")
                if self.fastest_driver:
                    fastest_driver_full_name = telemetry.get(self.fastest_driver.get("code"), {}).get("full_name")
                # Get color from results
                for result in window.data.get("results", []):
                    if result.get("code") == driver_code:
                        driver_color = tuple(result.get("color", arcade.color.ANTI_FLASH_WHITE))
                        break

        # Get current time from window
        frames = window.loaded_telemetry.get("frames") if isinstance(window.loaded_telemetry, dict) else None
        if not frames:
            return
        current_frame = frames[window.frame_index]
        current_t = current_frame.get("t", 0.0)
        formatted_time = format_time(current_t)
        
        rect = arcade.XYWH(self.x + 125, self.y - 65, 250, 120)
        
        arcade.draw_rect_filled(rect, (20, 20, 20, 255))

        arcade.Text(f"{driver_full_name}", self.x + 10, self.y - 30, driver_color, 16, bold=True).draw()
        
        #Display tyre compound texture
        rect = arcade.XYWH(self.x + 220, self.y - 22, 24, 24)
        texture_key = f"{compound}.0" if isinstance(compound, (int, float)) else None
        tyre_texture = self._tyre_textures.get(texture_key) if texture_key else None
        
        if tyre_texture:
            arcade.draw_texture_rect(
                rect=rect,
                texture=tyre_texture,
                angle=0,
                alpha=255
            )

        arcade.draw_line(self.x, self.y - 40, self.x + 250, self.y - 40, arcade.color.ANTI_FLASH_WHITE, 3)

        arcade.Text(f"{formatted_time}", self.x + 10, self.y - 70, arcade.color.ANTI_FLASH_WHITE, 18, anchor_x="left", bold=True).draw()

        if self.fastest_driver_sector_times and fastest_driver_full_name and fastest_driver_full_name != driver_full_name:
            fastest_last_name = fastest_driver_full_name.split(" ")[-1]
            arcade.Text(f"{fastest_last_name}", self.x + 150, self.y - 85, arcade.color.LIGHT_GRAY, 13, anchor_x="left").draw()

        #show sector times over the labels
        sector_configs = [
            ("sector1", self.x + 45, 0),
            ("sector2", self.x + 125, 1),
            ("sector3", self.x + 205, 2)
        ]
        
        cumulative_time = 0
        cumulative_fastest_time = 0
        epsilon = 0.01  # Small tolerance for floating-point comparison
        
        for sector_key, x_pos, sector_idx in sector_configs:
            sector_time = sector_times.get(sector_key)
            fastest_sector_time = None
            delta_sector_time = None
            if self.fastest_driver_sector_times:
                fastest_sector_time = self.fastest_driver_sector_times.get(sector_key)
                cumulative_fastest_time += fastest_sector_time if fastest_sector_time is not None else 0
                delta_sector_time = sector_time - fastest_sector_time if sector_time is not None and fastest_sector_time is not None else None
            
            formatted_fastest_sector_time = format_time(cumulative_fastest_time)
            text_color = arcade.color.ANTI_FLASH_WHITE
            
            # Calculate elapsed time in current sector
            # Sector 1 uses absolute time, others use time relative to cumulative
            elapsed_in_sector = current_t if sector_idx == 0 else current_t - cumulative_time

            # Check if sector has started (only applicable for sectors 2 and 3)
            if sector_idx > 0 and current_t < cumulative_time - epsilon:
                text = "-"

            # Check if sector is completed
            elif sector_time and sector_time <= elapsed_in_sector + epsilon:
                text, text_color = self.show_delta_sector_times(sector_idx, sector_time, delta_sector_time, text_color)
                # Draw green bar below completed sector
                bar_width = 40 if sector_idx == 0 else 45
                arcade.draw_line(x_pos - 45, self.y - 125, x_pos + bar_width, self.y - 125, arcade.color.GREEN, 3)
                if sector_idx == 2 and fastest_sector_time is not None:
                    arcade.Text(f"{formatted_fastest_sector_time}s", self.x + 150, self.y - 65, arcade.color.LIGHT_GRAY, 13, anchor_x="left").draw()

            # Sector in progress - show current elapsed time
            else:
                text = f"{elapsed_in_sector:.1f}s"
                if fastest_sector_time is not None:
                    arcade.Text(f"{formatted_fastest_sector_time}s", self.x + 150, self.y - 65, arcade.color.LIGHT_GRAY, 13, anchor_x="left").draw()
            
            # Always draw the sector time text
            arcade.Text(text, x_pos, self.y - 105, text_color, 12, anchor_x="center", bold=True).draw()
            
            # Always update cumulative time for next sector
            if sector_time is not None:
                cumulative_time += sector_time
        
        # Draw sector labels once after processing all sectors
        self.draw_sector_labels(sector_times, current_t)

    def draw_sector_labels(self, sector_times, current_t):
        s1_time = sector_times.get("sector1") or 0
        s1_color = arcade.color.GREEN if s1_time > 0 and current_t >= s1_time else arcade.color.LIGHT_GRAY
        arcade.Text("S1", self.x + 35, self.y - 120, s1_color, 9, bold=True).draw()

        s2_val = sector_times.get("sector2") or 0
        s2_time = s1_time + s2_val
        s2_color = arcade.color.GREEN if s2_time > 0 and current_t >= s2_time else arcade.color.LIGHT_GRAY
        arcade.Text("S2", self.x + 115, self.y - 120, s2_color, 9, bold=True).draw()
        
        s3_val = sector_times.get("sector3") or 0
        s3_time = s2_time + s3_val
        s3_color = arcade.color.GREEN if s3_time > 0 and current_t >= s3_time else arcade.color.LIGHT_GRAY
        arcade.Text("S3", self.x + 200, self.y - 120, s3_color, 9, bold=True).draw()      
    
    def show_delta_sector_times(self, sector_idx: int, sector_time: float, delta_sector_time: float | None, text_color: tuple):
        if self._delta_sector == sector_idx and self._time_elapsed < 1.0 and delta_sector_time is not None:
            # Show delta for 1 second
            if delta_sector_time < 0:
                text = f"-{abs(delta_sector_time):.3f}s"
                text_color = arcade.color.GREEN
            else:
                text = f"+{delta_sector_time:.3f}s"
                text_color = arcade.color.YELLOW
        else:
            text = f"{sector_time:.1f}s"
            # Detect if sector just completed to trigger delta display (only once)
            if self._last_completed_sector < sector_idx and delta_sector_time is not None:
                self._delta_sector = sector_idx
                self._time_elapsed = 0.0
                self._last_completed_sector = sector_idx
        return text, text_color
