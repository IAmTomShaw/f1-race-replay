import arcade
from .base import BaseComponent

class SessionInfoComponent(BaseComponent):
    """
    Displays session information banner at the top-center of the screen.
    Shows: Circuit name, Country, Event name, Year, Round, Date, Total laps
    """
    def __init__(self, visible=True):
        self.visible = visible
        self.session_info = {}
        self._text = arcade.Text("", 0, 0, arcade.color.WHITE, 14)
        
    def set_info(self, event_name: str = "", circuit_name: str = "", country: str = "",
                 year: int = None, round_num: int = None, date: str = "", total_laps: int = None):
        """Set session information to display"""
        self.session_info = {
            'event_name': event_name,
            'circuit_name': circuit_name,
            'country': country,
            'year': year,
            'round': round_num,
            'date': date,
            'total_laps': total_laps
        }
    
    def toggle_visibility(self) -> bool:
        """Toggle visibility of session info banner"""
        self.visible = not self.visible
        return self.visible
    
    def draw(self, window):
        if not self.visible or not self.session_info:
            return
        
        # Banner dimensions
        banner_height = 60
        banner_width = min(900, window.width - 40)
        center_x = window.width / 2
        top_y = window.height - 10
        bottom_y = top_y - banner_height
        
        # Draw semi-transparent background
        rect = arcade.XYWH(center_x, top_y - banner_height/2, banner_width, banner_height)
        arcade.draw_rect_filled(rect, (20, 20, 20, 220))
        arcade.draw_rect_outline(rect, arcade.color.GRAY, 2)
        
        # Get info
        event = self.session_info.get('event_name', '')
        circuit = self.session_info.get('circuit_name', '')
        country = self.session_info.get('country', '')
        year = self.session_info.get('year', '')
        round_num = self.session_info.get('round', '')
        date = self.session_info.get('date', '')
        total_laps = self.session_info.get('total_laps', '')
        
        # Line 1: Event Name | Circuit | Country
        line1_parts = []
        if event:
            line1_parts.append(f"🏁 {event}")
        if circuit:
            line1_parts.append(circuit)
        if country:
            line1_parts.append(f"🌍 {country}")
        
        line1 = " | ".join(line1_parts)
        
        # Line 2: Year Round X | Date | X Laps
        line2_parts = []
        if year and round_num:
            line2_parts.append(f"📅 {year} Round {round_num}")
        elif year:
            line2_parts.append(f"📅 {year}")
        if date:
            line2_parts.append(date)
        if total_laps:
            line2_parts.append(f"{total_laps} Laps")
        
        line2 = " | ".join(line2_parts)
        
        # Draw text lines
        self._text.font_size = 16
        self._text.bold = True
        self._text.color = arcade.color.WHITE
        self._text.text = line1
        self._text.x = center_x
        self._text.y = top_y - 18
        self._text.anchor_x = "center"
        self._text.anchor_y = "center"
        self._text.draw()
        
        self._text.font_size = 13
        self._text.bold = False
        self._text.color = arcade.color.LIGHT_GRAY
        self._text.text = line2
        self._text.y = top_y - 40
        self._text.draw()
