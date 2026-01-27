import arcade
import arcade.gui

class MovableSection(arcade.gui.UIDraggableWidget):
    """
    A wrapper that makes any existing component movable.
    """
    def __init__(self, component, x, y, width, height, **kwargs):
        super().__init__(x=x, y=y, width=width, height=height, **kwargs)
        self.component = component
        self.is_editing = False # Shows border when True

    def on_draw(self):
        # 1. Update the component's internal position to match the widget
        # This ensures the component draws where the user dragged it
        if hasattr(self.component, 'left'):
            self.component.left = self.x
        
        # 2. Tell the component to draw itself
        # We pass the 'self' as the window reference if the component needs it
        # Or you can pass the actual window object stored during init
        self.component.draw(arcade.get_window())

        # 3. Draw an 'Edit Border' if we are in Edit Mode
        if self.is_editing:
            arcade.draw_rect_outline(
                arcade.XYWH(self.x + self.width/2, self.y - self.height/2, self.width, self.height),
                arcade.color.WHITE, 2
            )
            arcade.draw_text("MOVE", self.x, self.y, arcade.color.BLACK, 10, 
                             anchor_x="left", anchor_y="bottom", bg_color=arcade.color.WHITE)