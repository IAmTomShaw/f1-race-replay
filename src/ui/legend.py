import arcade
import os
from .base import BaseComponent

class LegendComponent(BaseComponent):
    def __init__(self, x: int = 20, y: int = 220, visible=True): # Increased y to 220 to fit all lines
        self.x = x
        self.y = y
        self._control_icons_textures = {}
        self._visible = visible
        # Load control icons from images/icons folder (all files)
        icons_folder = os.path.join("images", "controls")
        if os.path.exists(icons_folder):
            for filename in os.listdir(icons_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(icons_folder, filename)
                    self._control_icons_textures[texture_name] = arcade.load_texture(texture_path)
        self.lines = ["Help (Click or 'H')"]
        
        self.controls_text_offset = 180
        self._text = arcade.Text("", 0, 0, arcade.color.CYAN, 14)
    
    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the legend
        """
        self._visible = not self._visible
        return self._visible
    
    def set_visible(self):
        """
        Set visibility of legend to True
        """
        self._visible = True


    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):

        line_x = self.x
        line_y = self.y - getattr(self, "controls_text_offset", 0)
        left = line_x
        text_width = self._text.content_width or 120
        right = line_x + text_width + 8
        top = line_y + 8
        bottom = line_y - 18

        if left <= x <= right and bottom <= y <= top:
            popup = getattr(window, "controls_popup_comp", None)
            if popup:
                # popup anchored to bottom left, small margin (20px)
                margin_x = 20
                margin_y = 20
                left_pos = float(margin_x)
                top_pos = float(margin_y + popup.height)
                desired_cx = left_pos + popup.width / 2
                desired_cy = top_pos - popup.height / 2
                if popup.visible and popup.cx == desired_cx and popup.cy == desired_cy:
                    popup.hide()
                else:
                    popup.show_over(left_pos, top_pos)
            return True
        return False
    
    def draw(self, window):
        # Skip rendering entirely if hidden
        
        if not self._visible:
            return
        for i, lines in enumerate(self.lines):
            line = lines[0] if isinstance(lines, tuple) else lines # main text
            brackets = lines[1] if isinstance(lines, tuple) and len(lines) > 2 else None # brackets only if icons exist
            icon_keys = lines[2] if isinstance(lines, tuple) and len(lines) > 2 else None # icon keys
        
            icon_size = 14
            # Draw icons if any
            
            if icon_keys:
                control_icon_x = self.x + 12
                for key in icon_keys:
                    icon_texture = self._control_icons_textures.get(key)
                    if icon_texture:
                        control_icon_y = self.y - (i * 25) + 5 # slight vertical offset
                        rect = arcade.XYWH(control_icon_x, control_icon_y, icon_size, icon_size)
                        arcade.draw_texture_rect(
                            rect = rect,
                            texture = icon_texture,
                            angle = 0,
                            alpha = 255
                        )
                        control_icon_x += icon_size + 6 # spacing between icons
                        
            if brackets:
                for j in range(len(brackets)):
                    self._text.font_size = 14
                    self._text.bold = (i == 0)
                    self._text.color = arcade.color.LIGHT_GRAY
                    self._text.text = brackets[j]
                    self._text.x = self.x + (j * (icon_size + 5))
                    self._text.y = self.y - (i * 25)
                    self._text.draw()
            
            # Draw the text line
            self._text.text = line
            self._text.x = self.x + (60 if icon_keys else 0)
            base_y = self.y - (i * 25)
            
            if i == 0:
                base_y -= getattr(self, "controls_text_offset", 0)
            self._text.y = base_y
            self._text.draw()
