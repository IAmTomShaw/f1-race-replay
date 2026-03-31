import arcade
import os
from .base import BaseComponent

class RaceControlsComponent(BaseComponent):
    """
    A visual component with playback control buttons:
    - Rewind button (left)
    - Play/Pause button (center)
    - Forward button (right)
    """
    
    PLAYBACK_SPEEDS = [0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]

    def __init__(self, center_x: int = 100, center_y: int = 60, button_size: int = 40, visible=True):
        self.center_x = center_x
        self.center_y = center_y
        self.button_size = button_size
        self.button_spacing = 70
        self.speed_container_offset = 200
        self._hide_speed_text = False
        self._control_textures = {}
        self._visible = visible
        
        # Button rectangles for hit testing
        self.rewind_rect = None
        self.play_pause_rect = None
        self.forward_rect = None
        self.speed_increase_rect = None
        self.speed_decrease_rect = None
        
        # Hover state
        self.hover_button = None  # 'rewind/forward', 'play/pause', 'speed_increase', 'speed_decrease'
        # Flash feedback state for keyboard shortcuts
        self._flash_button = None
        self._flash_timer = 0.0
        self._flash_duration = 0.3  # seconds
        self._flash_timer = 0.0

        _controls_folder = os.path.join("images", "controls")
        if os.path.exists(_controls_folder):
            for filename in os.listdir(_controls_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(_controls_folder, filename)
                    self._control_textures[texture_name] = arcade.load_texture(texture_path)

    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the controls
        """
        self._visible = not self._visible
        return self._visible

    def set_visible(self):
        """
        Set visibility of controls to True
        """
        self._visible = True

    def on_resize(self, window):
        """Recalculate control positions on window resize."""
        self.center_x = window.width / 2
        # Scale spacing and offset proportionally to window width (based on 1920px reference)
        self.button_spacing = window.width * (70 / 1920)
        self.speed_container_offset = window.width * (200 / 1920)
        self._hide_speed_text = window.width < 1000
    
    def on_update(self, delta_time: float):
        """Update flash timer for keyboard feedback animation."""
        if self._flash_timer > 0:
            self._flash_timer = max(0, self._flash_timer - delta_time)
            if self._flash_timer == 0:
                self._flash_button = None
    
    def flash_button(self, button_name: str):
        """Trigger a visual flash effect for a button (used for keyboard feedback)."""
        self._flash_button = button_name
        self._flash_timer = self._flash_duration

    def draw(self, window):
        # Skip rendering entirely if hidden
        if not self._visible:
            return
        """Draw the three playback control buttons."""
        is_paused = getattr(window, 'paused', False)
        
        # Button positions
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
        """Draw hover outline effect for a button if it's currently hovered."""
        if self.hover_button == button_name and getattr(self, f"{button_name}_rect", None):
            arcade.draw_circle_outline(x, y, self.button_size // 2 + radius_offset, arcade.color.WHITE, border_width)
        
        # Show flash effect for keyboard feedback
        if self._flash_button == button_name and self._flash_timer > 0:
            # Pulsing ring effect based on timer
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
            arcade.draw_texture_rect(
                    rect=rect,
                    texture=texture,
                    angle=0,
                    alpha = 255
                )
    def _draw_pause_icon(self, x: float, y: float):
        self.draw_hover_effect('play_pause', x, self.center_y)
        if 'pause' in self._control_textures:
            texture = self._control_textures['pause']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.play_pause_rect = (x - self.button_size//2, y - self.button_size//2,
                                   x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(
                    rect=rect,
                    texture=texture,
                    angle=0,
                    alpha = 255
                )
    def _draw_forward_icon(self, x: float, y: float):
        self.draw_hover_effect('forward', x, self.center_y)
        if 'rewind' in self._control_textures:
            texture = self._control_textures['rewind']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.forward_rect = (x - self.button_size//2, y - self.button_size//2,
                                x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(
                    rect=rect,
                    texture=texture,
                    angle=180,
                    alpha = 255
                )
    def _draw_rewind_icon(self, x: float, y: float):
        self.draw_hover_effect('rewind', x, self.center_y)
        if 'rewind' in self._control_textures:
            texture = self._control_textures['rewind']
            rect = arcade.XYWH(x, y, self.button_size, self.button_size)
            self.rewind_rect = (x - self.button_size//2, y - self.button_size//2,
                               x + self.button_size//2, y + self.button_size//2)
            arcade.draw_texture_rect(
                    rect=rect,
                    texture=texture,
                    angle=0,
                    alpha = 255
                )
    def _draw_speed_comp(self, x: float, y: float, speed: float):
        """Draw speed multiplier text."""
        if 'speed+' and 'speed-' in self._control_textures:
            texture_plus = self._control_textures['speed+']
            texture_minus = self._control_textures['speed-']
            
            # Container dimensions
            if self._hide_speed_text:
                container_width = self.button_size * 2.4
            else:
                container_width = self.button_size * 3.6
            container_height = self.button_size * 1.2
            
            # Draw container background box
            rect_container = arcade.XYWH(x, y, container_width, container_height)
            arcade.draw_rect_filled(rect_container, (40, 40, 40, 200))

            # Button positions inside container
            button_offset = (container_width / 2) - (self.button_size / 2) - 5
            
            rect_minus = arcade.XYWH(x - button_offset, y, self.button_size, self.button_size)
            rect_plus = arcade.XYWH(x + button_offset, y, self.button_size, self.button_size)
            
            self.speed_decrease_rect = (x - button_offset - self.button_size//2, y - self.button_size//2,
                                       x - button_offset + self.button_size//2, y + self.button_size//2)
            self.speed_increase_rect = (x + button_offset - self.button_size//2, y - self.button_size//2,
                                       x + button_offset + self.button_size//2, y + self.button_size//2)
            
            # Draw minus button
            arcade.draw_texture_rect(
                    rect=rect_minus,
                    texture=texture_minus,
                    angle=0,
                    alpha=255
                )
            
            # Draw speed text in center
            if not self._hide_speed_text:
                arcade.Text(f"{speed}x", x, y - 5,
                            arcade.color.WHITE, 11,
                            anchor_x="center",
                            bold=True).draw()
            
            # Draw plus button
            arcade.draw_texture_rect(
                    rect=rect_plus,
                    texture=texture_plus,
                    angle=0,
                    alpha=255
                )

            # Draw hover highlights for speed buttons
            self.draw_hover_effect('speed_increase', rect_plus.center_x, rect_plus.center_y, radius_offset=1, border_width=2)
            self.draw_hover_effect('speed_decrease', rect_minus.center_x, rect_minus.center_y, radius_offset=1, border_width=2)
            

    def on_mouse_motion(self, window, x: float, y: float, dx: float, dy: float):
        """Handle mouse hover effects."""
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
        return False
    
    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        """Handle button clicks."""
        if self._point_in_rect(x, y, self.rewind_rect):
            # Update: Support hold-to-rewind
            if hasattr(window, 'is_rewinding'):
                window.was_paused_before_hold = window.paused
                window.is_rewinding = True
                window.paused = True
            elif hasattr(window, 'frame_index'):
                window.frame_index = int(max(0, window.frame_index - 10))
            return True
        elif self._point_in_rect(x, y, self.play_pause_rect):
            if hasattr(window, 'paused'):
                window.paused = not window.paused
            return True
        elif self._point_in_rect(x, y, self.forward_rect):
            # Update: Support hold-to-forward
            if hasattr(window, 'is_forwarding'):
                window.was_paused_before_hold = window.paused
                window.is_forwarding = True
                window.paused = True
            elif hasattr(window, 'frame_index') and hasattr(window, 'n_frames'):
                window.frame_index = int(min(window.n_frames - 1, window.frame_index + 10))
            return True
        elif self._point_in_rect(x, y, self.speed_increase_rect):
            if hasattr(window, 'playback_speed'):
                # FIX: Use index lookup to increment speed.
                if window.playback_speed < max(self.PLAYBACK_SPEEDS):
                    current_index = self.PLAYBACK_SPEEDS.index(window.playback_speed)
                    window.playback_speed = self.PLAYBACK_SPEEDS[min(current_index + 1, len(self.PLAYBACK_SPEEDS) - 1)]
                    self.flash_button('speed_increase')
            return True
        elif self._point_in_rect(x, y, self.speed_decrease_rect):
            if hasattr(window, 'playback_speed'):
                # FIX: Use index lookup to decrement speed safely within defined PLAYBACK_SPEEDS.
                if window.playback_speed > min(self.PLAYBACK_SPEEDS):
                    current_index = self.PLAYBACK_SPEEDS.index(window.playback_speed)
                    window.playback_speed = self.PLAYBACK_SPEEDS[max(0, current_index - 1)]
                    self.flash_button('speed_decrease')
            return True
        return False
    
    def _point_in_rect(self, x: float, y: float, rect: tuple[float, float, float, float] | None) -> bool:
        """Check if point is inside rectangle."""
        if rect is None:
            return False
        left, bottom, right, top = rect
        return left <= x <= right and bottom <= y <= top
