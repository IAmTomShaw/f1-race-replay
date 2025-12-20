from typing import Optional, Tuple, Dict
import os
import arcade
from src.ui.base import BaseComponent

class RaceControlsComponent(BaseComponent):
    """
    A visual component with playback control buttons:
    - Rewind button (left)
    - Play/Pause button (center)
    - Forward button (right)
    """
    def __init__(self, center_x: int = 100, center_y: int = 60, button_size: int = 40):
        self.center_x = center_x
        self.center_y = center_y
        self.button_size = button_size
        self.button_spacing = 70
        self.speed_container_offset = 200
        self._hide_speed_text = False
        self._control_textures: Dict[str, arcade.Texture] = {}
        
        # Button rectangles for hit testing
        self.rewind_rect: Optional[Tuple[float, float, float, float]] = None
        self.play_pause_rect: Optional[Tuple[float, float, float, float]] = None
        self.forward_rect: Optional[Tuple[float, float, float, float]] = None
        self.speed_increase_rect: Optional[Tuple[float, float, float, float]] = None
        self.speed_decrease_rect: Optional[Tuple[float, float, float, float]] = None
        
        # Hover state
        self.hover_button: Optional[str] = None
        self._flash_button: Optional[str] = None
        self._flash_timer = 0.0
        self._flash_duration = 0.3

        self._load_textures()

    def _load_textures(self):
        _controls_folder = os.path.join("images", "controls")
        if os.path.exists(_controls_folder):
            for filename in os.listdir(_controls_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(_controls_folder, filename)
                    self._control_textures[texture_name] = arcade.load_texture(texture_path)

    def on_resize(self, window):
        self.center_x = window.width / 2
        self.button_spacing = window.width * (70 / 1920)
        self.speed_container_offset = window.width * (200 / 1920)
        self._hide_speed_text = window.width < 1000
    
    def on_update(self, delta_time: float):
        if self._flash_timer > 0:
            self._flash_timer = max(0, self._flash_timer - delta_time)
            if self._flash_timer == 0:
                self._flash_button = None
    
    def flash_button(self, button_name: str):
        self._flash_button = button_name
        self._flash_timer = self._flash_duration

    def draw(self, window):
        is_paused = getattr(window, 'paused', False)
        
        rewind_x = self.center_x - self.button_spacing
        play_x = self.center_x
        forward_x = self.center_x + self.button_spacing
    
        self._draw_rewind_icon(rewind_x, self.center_y)
        
        if is_paused:
            self._draw_play_icon(play_x, self.center_y)
        else:
            self._draw_pause_icon(play_x, self.center_y)

        self._draw_forward_icon(forward_x, self.center_y)

        self._draw_speed_comp(forward_x + self.speed_container_offset, self.center_y, getattr(window, 'playback_speed', 1.0))

    def draw_hover_effect(self, button_name: str, x: float, y: float, radius_offset: int = 2, border_width: int = 4):
        if self.hover_button == button_name and getattr(self, f"{button_name}_rect", None):
            arcade.draw_circle_outline(x, y, self.button_size // 2 + radius_offset, arcade.color.WHITE, border_width)
        
        if self._flash_button == button_name and self._flash_timer > 0:
            alpha = int(255 * (self._flash_timer / self._flash_duration))
            flash_color = (*arcade.color.DIM_GRAY[:3], alpha)
            arcade.draw_circle_outline(x, y, self.button_size // 2 + radius_offset + 2, flash_color, border_width + 1)

    def _draw_play_icon(self, x: float, y: float):
        self.draw_hover_effect('play_pause', x, self.center_y)
        if 'play' in self._control_textures:
            texture = self._control_textures['play']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.play_pause_rect = (x - self.button_size//2, y - self.button_size//2,
                                   x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(rect=rect, texture=texture, angle=0, alpha=255)

    def _draw_pause_icon(self, x: float, y: float):
        self.draw_hover_effect('play_pause', x, self.center_y)
        if 'pause' in self._control_textures:
            texture = self._control_textures['pause']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.play_pause_rect = (x - self.button_size//2, y - self.button_size//2,
                                   x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(rect=rect, texture=texture, angle=0, alpha=255)

    def _draw_forward_icon(self, x: float, y: float):
        self.draw_hover_effect('forward', x, self.center_y)
        if 'rewind' in self._control_textures:
            texture = self._control_textures['rewind']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.forward_rect = (x - self.button_size//2, y - self.button_size//2,
                                x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(rect=rect, texture=texture, angle=180, alpha=255)

    def _draw_rewind_icon(self, x: float, y: float):
        self.draw_hover_effect('rewind', x, self.center_y)
        if 'rewind' in self._control_textures:
            texture = self._control_textures['rewind']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.rewind_rect = (x - self.button_size//2, y - self.button_size//2,
                               x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(rect=rect, texture=texture, angle=0, alpha=255)

    def _draw_speed_comp(self, x: float, y: float, speed: float):
        if 'speed+' and 'speed-' in self._control_textures:
            texture_plus = self._control_textures['speed+']
            texture_minus = self._control_textures['speed-']
            
            if self._hide_speed_text:
                container_width = self.button_size * 2.4
            else:
                container_width = self.button_size * 3.6
            container_height = self.button_size * 1.2
            
            rect_container = arcade.XYWH(x, y, container_width, container_height)
            arcade.draw_rect_filled(rect_container, (40, 40, 40, 200))

            button_offset = (container_width / 2) - (self.button_size / 2) - 5
            
            rect_minus = arcade.XYWH(x - button_offset, y, self.button_size, self.button_size)
            rect_plus = arcade.XYWH(x + button_offset, y, self.button_size, self.button_size)
            
            self.speed_decrease_rect = (x - button_offset - self.button_size//2, y - self.button_size//2,
                                       x - button_offset + self.button_size//2, y + self.button_size//2)
            self.speed_increase_rect = (x + button_offset - self.button_size//2, y - self.button_size//2,
                                       x + button_offset + self.button_size//2, y + self.button_size//2)
            
            arcade.draw_texture_rect(rect=rect_minus, texture=texture_minus, angle=0, alpha=255)
            
            if not self._hide_speed_text:
                arcade.Text(f"{speed:.1f}x", x, y - 5, arcade.color.WHITE, 14, anchor_x="center", bold=True).draw()
            
            arcade.draw_texture_rect(rect=rect_plus, texture=texture_plus, angle=0, alpha=255)

            self.draw_hover_effect('speed_increase', rect_plus.center_x, rect_plus.center_y, radius_offset=1, border_width=2)
            self.draw_hover_effect('speed_decrease', rect_minus.center_x, rect_minus.center_y, radius_offset=1, border_width=2)
            

    def on_mouse_motion(self, window, x: float, y: float, dx: float, dy: float):
        if self._point_in_rect(x, y, self.rewind_rect):
            self.hover_button = 'rewind'
        elif self._point_in_rect(x, y, self.play_pause_rect):
            self.hover_button = 'play_pause'
        elif self._point_in_rect(x, y, self.forward_rect):
            self.hover_button = 'forward'
        elif self._point_in_rect(x, y, self.speed_increase_rect):
            self.hover_button = 'speed_increase'
        elif self._point_in_rect(x, y, self.speed_decrease_rect):
            self.hover_button = 'speed_decrease'
        else:
            self.hover_button = None
    
    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        if self._point_in_rect(x, y, self.rewind_rect):
            if hasattr(window, 'frame_index'):
                window.frame_index = int(max(0, window.frame_index - 10))
            return True
        elif self._point_in_rect(x, y, self.play_pause_rect):
            if hasattr(window, 'paused'):
                window.paused = not window.paused
            return True
        elif self._point_in_rect(x, y, self.forward_rect):
            if hasattr(window, 'frame_index') and hasattr(window, 'n_frames'):
                window.frame_index = int(min(window.n_frames - 1, window.frame_index + 10))
            return True
        elif self._point_in_rect(x, y,self.speed_increase_rect):
            if hasattr(window, 'playback_speed'):
                window.playback_speed = window.playback_speed * 2
            return True
        elif self._point_in_rect(x, y,self.speed_decrease_rect):
            if hasattr(window, 'playback_speed'):
                window.playback_speed = max(0.1, window.playback_speed / 2)
            return True
        return False
    
    def _point_in_rect(self, x: float, y: float, rect: tuple[float, float, float, float] | None) -> bool:
        if rect is None:
            return False
        left, bottom, right, top = rect
        return left <= x <= right and bottom <= y <= top
