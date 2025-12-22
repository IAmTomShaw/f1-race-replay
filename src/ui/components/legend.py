import os
import arcade
from src.ui.base import BaseComponent

class LegendComponent(BaseComponent):
    """
    Displays the control legend/help overlay.
    """
    
    def __init__(self, x: int = 20, y: int = 220):
        self.x = x
        self.y = y
        self._control_icons_textures: dict[str, arcade.Texture] = {}
        self._load_textures()
        
        self.lines = [
            "Controls:",
            "[SPACE]  Pause/Resume",
            "[←/→]    Rewind / FastForward",
            "[↑/↓]    Speed +/- (0.5x, 1x, 2x, 4x)",
            "[R]       Restart",
            "[D]       Toggle DRS Zones",
            "[Shift + Click] Select Multiple Drivers"
        ]

    def _load_textures(self):
        """Load control icons from images/icons folder."""
        # Note: This assumes the CWD is the project root
        icons_folder = os.path.join("images", "controls")
        if os.path.exists(icons_folder):
            for filename in os.listdir(icons_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    texture_name = os.path.splitext(filename)[0]
                    texture_path = os.path.join(icons_folder, filename)
                    self._control_icons_textures[texture_name] = arcade.load_texture(texture_path)

    def draw(self, window):
        for i, line in enumerate(self.lines):
            arcade.Text(
                line,
                self.x,
                self.y - (i * 25),
                arcade.color.LIGHT_GRAY if i > 0 else arcade.color.WHITE,
                14,
                bold=(i == 0)
            ).draw()
