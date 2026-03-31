import arcade
import os
from typing import Optional, dict
from .base import BaseComponent

def _format_wind_direction(degrees: Optional[float]) -> str:
  if degrees is None:
      return "N/A"
  deg_norm = degrees % 360
  dirs = [
      "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
      "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
  ]
  idx = int((deg_norm / 22.5) + 0.5) % len(dirs)
  return dirs[idx]

class WeatherComponent(BaseComponent):
    def __init__(self, left=20, width=280, height=130, top_offset=170, visible=True):
        self.left = left
        self.width = width
        self.height = height
        self.top_offset = top_offset
        self.info = None
        self._weather_icon_textures = {}
        self._visible: bool = visible
        # Load weather icons from images/weather folder (all files)
        weather_folder = os.path.join("images", "weather")
        if os.path.exists(weather_folder):
            for filename in os.listdir(weather_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(weather_folder, filename)
                    self._weather_icon_textures[texture_name] = arcade.load_texture(texture_path)

        self._text = arcade.Text("", self.left + 12, 0, arcade.color.LIGHT_GRAY, 14, anchor_y="top")

    def set_info(self, info: Optional[dict]):
        self.info = info
    
    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the weather
        """
        self._visible = not self._visible
        return self._visible
    
    def set_visible(self):
        """
        Set visibility of weather to True
        """
        self._visible = True

    def draw(self, window):
        # Skip rendering entirely if hidden
        if not self._visible:
            return
        panel_top = window.height - self.top_offset
        if not self.info and not getattr(window, "has_weather", False):
            return
        arcade.Text("Weather", self.left + 12, panel_top - 10, arcade.color.WHITE, 18, bold=True, anchor_y="top").draw()
        def _fmt(val, suffix="", precision=1):
            return f"{val:.{precision}f}{suffix}" if val is not None else "N/A"
        info = self.info or {}
        # Map each weather line to its corresponding icon
        weather_lines = [
            ("Track", f"{_fmt(info.get('track_temp'), '°C')}", "thermometer"),
            ("Air", f"{_fmt(info.get('air_temp'), '°C')}", "thermometer"),
            ("Humidity", f"{_fmt(info.get('humidity'), '%', precision=0)}", "drop"),
            ("Wind", f"{_fmt(info.get('wind_speed'), ' km/h')} {_format_wind_direction(info.get('wind_direction'))}", "wind"),
            ("Rain", f"{info.get('rain_state','N/A')}", "rain"),
        ]
        
        start_y = panel_top - 36
        last_y = start_y

        self._text.font_size = 18; self._text.bold = True; self._text.color = arcade.color.WHITE
        self._text.text = "Weather"
        self._text.x = self.left + 12; self._text.y = panel_top - 10
        self._text.draw()

        for idx, (label, value, icon_key) in enumerate(weather_lines):
            line_y = start_y - idx * 22
            last_y = line_y
            # Draw weather icon
            weather_texture = self._weather_icon_textures.get(icon_key)
            if weather_texture:
                weather_icon_x = self.left + 24
                weather_icon_y = line_y - 15
                icon_size = 16
                rect = arcade.XYWH(weather_icon_x, weather_icon_y, icon_size, icon_size)
                arcade.draw_texture_rect(
                    rect=rect,
                    texture=weather_texture,
                    angle=0,
                    alpha=255
                )
            
            # Draw text

            line_text = f"{label}: {value}"
            
            self._text.font_size = 14; self._text.bold = False; self._text.color = arcade.color.LIGHT_GRAY
            self._text.text = line_text
            self._text.x = self.left + 38; self._text.y = line_y
            self._text.draw()

        # Track the bottom of the weather panel so info boxes can stack below it
        window.weather_bottom = last_y - 20
