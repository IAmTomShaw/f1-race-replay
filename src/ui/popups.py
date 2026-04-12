import arcade
from typing import Optional
from src.lib.time import format_time
from .base import BaseComponent

class QualifyingSegmentSelectorComponent(BaseComponent):
    def __init__(self, width=400, height=300):
        self.width = width
        self.height = height
        self.driver_result = None
        self.selected_segment = None
        
    def draw(self, window):
        if not getattr(window, "selected_driver", None):
            return
        
        code = window.selected_driver
        results = window.data['results']
        driver_result = next((res for res in results if res['code'] == code), None)
        # Calculate modal position (centered)
        center_x = window.width // 2
        center_y = window.height // 2
        left = center_x - self.width // 2
        right = center_x + self.width // 2
        top = center_y + self.height // 2
        bottom = center_y - self.height // 2
        
        # Draw modal background
        modal_rect = arcade.XYWH(center_x, center_y, self.width, self.height)
        arcade.draw_rect_filled(modal_rect, (40, 40, 40, 230))
        arcade.draw_rect_outline(modal_rect, arcade.color.WHITE, 2)
        
        # Draw title
        title = f"Qualifying Sessions - {driver_result.get('code','')}"
        arcade.Text(title, left + 20, top - 30, arcade.color.WHITE, 18, 
               bold=True, anchor_x="left", anchor_y="center").draw()
        
        # Draw segments
        segment_height = 50
        start_y = top - 80

        segments = []

        if driver_result.get('Q1') is not None:
            segments.append({
                'time': driver_result['Q1'],
                'segment': 1
            })
        if driver_result.get('Q2') is not None:
            segments.append({
                'time': driver_result['Q2'],
                'segment': 2
            })
        if driver_result.get('Q3') is not None:
            segments.append({
                'time': driver_result['Q3'],
                'segment': 3
            })
        
        for i, data in enumerate(segments):
            segment = f"Q{data['segment']}"
            segment_top = start_y - (i * (segment_height + 10))
            segment_bottom = segment_top - segment_height
            
            # Highlight if selected
            segment_rect = arcade.XYWH(center_x, segment_top - segment_height//2, 
                                     self.width - 40, segment_height)
            
            if segment == self.selected_segment:
                arcade.draw_rect_filled(segment_rect, arcade.color.LIGHT_GRAY)
                text_color = arcade.color.BLACK
            else:
                arcade.draw_rect_filled(segment_rect, (60, 60, 60))
                text_color = arcade.color.WHITE
                
            arcade.draw_rect_outline(segment_rect, arcade.color.WHITE, 1)
            
            # Draw segment info
            segment_text = f"{segment.upper()}"
            time_text = format_time(float(data.get('time', 'No Time')))
            
            arcade.Text(segment_text, left + 30, segment_top - 20, 
                       text_color, 16, bold=True, anchor_x="left", anchor_y="center").draw()
            arcade.Text(time_text, right - 30, segment_top - 20, 
                       text_color, 14, anchor_x="right", anchor_y="center").draw()
        
        # Draw close button
        close_btn_rect = arcade.XYWH(right - 30, top - 30, 20, 20)
        arcade.draw_rect_filled(close_btn_rect, arcade.color.RED)
        arcade.Text("×", right - 30, top - 30, arcade.color.WHITE, 16, 
               bold=True, anchor_x="center", anchor_y="center").draw()

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):        
        if not getattr(window, "selected_driver", None):
            return False
        
        # Calculate modal position (same as in draw)
        center_x = window.width // 2
        center_y = window.height // 2
        left = center_x - self.width // 2
        right = center_x + self.width // 2
        top = center_y + self.height // 2
        bottom = center_y - self.height // 2
        
        # Check close button (match the rect from draw method)
        close_btn_left = right - 30 - 10  # center - half width
        close_btn_right = right - 30 + 10  # center + half width
        close_btn_bottom = top - 30 - 10  # center - half height
        close_btn_top = top - 30 + 10     # center + half height
        
        if close_btn_left <= x <= close_btn_right and close_btn_bottom <= y <= close_btn_top:
            window.selected_driver = None
            window.selected_drivers = []
            # Also clear leaderboard selection state so UI highlight is removed
            if hasattr(window, "leaderboard"):
                window.leaderboard.selected = []
            self.selected_segment = None
            return True

        # Check segment clicks
        code = window.selected_driver
        results = window.data['results']
        driver_result = next((res for res in results if res['code'] == code), None)
        
        if driver_result:
            segments = []
            if driver_result.get('Q1') is not None:
                segments.append({'time': driver_result['Q1'], 'segment': 1})
            if driver_result.get('Q2') is not None:
                segments.append({'time': driver_result['Q2'], 'segment': 2})
            if driver_result.get('Q3') is not None:
                segments.append({'time': driver_result['Q3'], 'segment': 3})

            segment_height, start_y = 50, top - 80
            left, right = center_x - self.width // 2, center_x + self.width // 2

            for i, data in enumerate(segments):
                s_top = start_y - (i * (segment_height + 10))
                s_bottom = s_top - segment_height
                if left + 20 <= x <= right - 20 and s_bottom <= y <= s_top:
                    try:
                        if hasattr(window, "load_driver_telemetry"):
                            window.load_driver_telemetry(code, f"Q{data['segment']}")
                        window.selected_driver = None
                        window.selected_drivers = []
                        if hasattr(window, "leaderboard"):
                            window.leaderboard.selected = []
                    except Exception as e:
                        print("Error starting telemetry load:", e)
                    return True
        return True # Consume all clicks when visible

class ControlsPopupComponent(BaseComponent):
    def __init__(
        self,
        width: int = 430,
        height: int = 260,
        header_font_size: int = 18,
        body_font_size: int = 16,
        lines: Optional[list[str]] = None,
    ):

        self.width = width
        self.height = height
        self.visible = False
        
        self.cx: Optional[float] = None
        self.cy: Optional[float] = None
        
        self.header_font_size = header_font_size
        self.body_font_size = body_font_size
        self.lines = lines
        
        self._header_text = arcade.Text("", 0, 0, arcade.color.BLACK, self.header_font_size, anchor_x="left", anchor_y="center")
        self._body_text = arcade.Text("", 0, 0, arcade.color.LIGHT_GRAY, self.body_font_size, anchor_x="left", anchor_y="center")

    def _default_lines(self) -> list[str]:
        return [
            ("SPACE", "Pause/Resume"),
            ("← / →", "Jump back/forward"),
            ("↑ / ↓", "Speed +/-"),
            ("1-4", "Set speed: 0.5x / 1x / 2x / 4x"),
            ("R", "Restart"),
            ("D", "Toggle DRS Zones"),
            ("B", "Toggle Progress Bar"),
            ("L", "Toggle Driver Labels"),
            ("H", "Toggle Help Popup"),
        ]

    def set_lines(self, lines: Optional[list[str]]):
        self.lines = lines

    def set_size(self, width: int, height: int):
        
        self.width = width
        self.height = height

    def set_font_sizes(self, header_font_size: int = None, body_font_size: int = None):
        
        if header_font_size is not None:
            self.header_font_size = header_font_size
            self._header_text.font_size = header_font_size
        if body_font_size is not None:
            self.body_font_size = body_font_size
            self._body_text.font_size = body_font_size

    def show_center(self):
        """Show popup centered in the window."""
        self.cx = None
        self.cy = None
        self.visible = True

    def show_over(self, left: float, top: float):
        
        self.cx = float(left + self.width / 2)
        self.cy = float(top - self.height / 2)
        self.visible = True

    def hide(self):
        self.visible = False
        self.cx = None
        self.cy = None

    def draw(self, window):
        if not self.visible:
            return
        cx = self.cx if self.cx is not None else window.width / 2
        cy = self.cy if self.cy is not None else window.height / 2
        rect = arcade.XYWH(cx, cy, self.width, self.height)
        arcade.draw_rect_filled(rect, (0, 0, 0, 255))
        arcade.draw_rect_outline(rect, arcade.color.GRAY, 2)

        header_height = max(28, int(self.header_font_size * 2))
        header_cy = cy + self.height / 2 - header_height / 2
        arcade.draw_rect_filled(arcade.XYWH(cx, header_cy, self.width, header_height), arcade.color.GRAY)
        
        self._header_text.font_size = self.header_font_size
        self._header_text.bold = True
        self._header_text.color = arcade.color.BLACK
        self._header_text.text = "Controls"
        self._header_text.x = cx - self.width / 2 + 12
        self._header_text.y = header_cy
        self._header_text.draw()

        controls = self.lines if self.lines is not None else self._default_lines()
        
        line_spacing = max(18, int(self.body_font_size + 8))
        left_x = cx - self.width / 2 + 16
        desc_x = cx - self.width / 2 + 100  # Fixed position for descriptions
        y = header_cy - 35  # More space below header

        for key, desc in controls:
            # Draw key
            self._body_text.font_size = self.body_font_size
            self._body_text.bold = True
            self._body_text.color = arcade.color.WHITE
            self._body_text.text = key
            self._body_text.x = left_x
            self._body_text.y = y
            self._body_text.draw()

            # Draw description
            self._body_text.bold = False
            self._body_text.color = arcade.color.LIGHT_GRAY
            self._body_text.text = desc
            self._body_text.x = desc_x
            self._body_text.y = y
            self._body_text.draw()

            y -= line_spacing

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        
        if not self.visible:
            return False
        cx = self.cx if self.cx is not None else window.width / 2
        cy = self.cy if self.cy is not None else window.height / 2
        left = cx - self.width / 2
        right = cx + self.width / 2
        bottom = cy - self.height / 2
        top = cy + self.height / 2

        # If click inside the box, do nothing
        if left <= x <= right and bottom <= y <= top:
            return True

        # Click outside closes popup
        self.hide()
        return True
