"""
Incidents Panel UI Component

Displays a list of detected race incidents (overtakes, near misses, pit stops)
with the ability to jump to incidents via keyboard navigation.
"""

import arcade
from typing import List, Optional
from src.incident_detection import Incident


class IncidentsPanelComponent:
    """UI component for displaying and navigating race incidents"""
    
    def __init__(self, left: float = 20, top: float = 600, width: float = 310, visible: bool = True):
        """
        Initialize incidents panel
        
        Args:
            left: Left edge x-coordinate
            top: Top edge y-coordinate  
            width: Panel width
            visible: Whether panel is initially visible
        """
        self.left = left
        self.top = top
        self.width = width
        self.visible = visible
        
        self.incidents: List[Incident] = []
        self.filtered_incidents: List[Incident] = []
        self.selected_incident_idx = -1
        self.scroll_offset = 0  # Track which incident is at top of visible list
        self.filter_type = None  # None = all, 'overtake', 'near_miss', 'pit_stop'
        
        # Visual params
        self.font_size = 11
        self.header_height = 30
        self.item_height = 22
        self.panel_height = 180
        self.bg_color = (30, 30, 30, 200)
        self.border_color = arcade.color.ORANGE
        self.text_color = arcade.color.WHITE
        self.selected_color = arcade.color.ORANGE
        self.accent_colors = {
            'overtake': arcade.color.YELLOW,
            'near_miss': arcade.color.ORANGE,
            'pit_stop': arcade.color.LIGHT_BLUE,
        }
        
    def set_incidents(self, incidents: List[Incident]):
        """Update the incidents list"""
        self.incidents = incidents
        self.filter_incidents()
        self.selected_incident_idx = -1
        self.scroll_offset = 0  # Reset scroll when incidents change
        
    def filter_incidents(self):
        """Apply current filter to incidents"""
        if self.filter_type is None:
            self.filtered_incidents = self.incidents
        else:
            self.filtered_incidents = [i for i in self.incidents if i.incident_type == self.filter_type]
    
    def toggle_filter(self):
        """Cycle through incident type filters"""
        filters = [None, 'overtake', 'near_miss', 'pit_stop']
        current_idx = filters.index(self.filter_type) if self.filter_type in filters else 0
        self.filter_type = filters[(current_idx + 1) % len(filters)]
        self.filter_incidents()
        self.selected_incident_idx = min(self.selected_incident_idx, len(self.filtered_incidents) - 1)
        self.scroll_offset = 0  # Reset scroll when filter changes
        
    def select_next_incident(self) -> Optional[int]:
        """Select next incident, return frame number or None"""
        if not self.filtered_incidents:
            return None
        self.selected_incident_idx = min(self.selected_incident_idx + 1, len(self.filtered_incidents) - 1)
        self._update_scroll_offset()
        return self.filtered_incidents[self.selected_incident_idx].frame_number
    
    def select_prev_incident(self) -> Optional[int]:
        """Select previous incident, return frame number or None"""
        if not self.filtered_incidents:
            return None
        self.selected_incident_idx = max(self.selected_incident_idx - 1, 0)
        self._update_scroll_offset()
        return self.filtered_incidents[self.selected_incident_idx].frame_number
    
    def _update_scroll_offset(self):
        """Update scroll offset to keep selected incident visible"""
        max_visible = (self.panel_height - self.header_height) // self.item_height
        # If selected is before visible window, scroll to show it at top
        if self.selected_incident_idx < self.scroll_offset:
            self.scroll_offset = self.selected_incident_idx
        # If selected is after visible window, scroll to show it at bottom
        elif self.selected_incident_idx >= self.scroll_offset + max_visible:
            self.scroll_offset = self.selected_incident_idx - max_visible + 1
        # Clamp scroll offset to valid range
        self.scroll_offset = max(0, min(self.scroll_offset, max(0, len(self.filtered_incidents) - max_visible)))
    
    def get_selected_incident(self) -> Optional[Incident]:
        """Get currently selected incident"""
        if 0 <= self.selected_incident_idx < len(self.filtered_incidents):
            return self.filtered_incidents[self.selected_incident_idx]
        return None
    
    def toggle_visibility(self):
        """Toggle panel visibility"""
        self.visible = not self.visible
    
    def on_resize(self, window):
        """Handle window resize - no-op but required for consistency with other components"""
        pass
    
    def draw(self, viewport_width: float, viewport_height: float):
        """Draw the incidents panel"""
        if not self.visible:
            return
        
        # Draw semi-transparent background
        arcade.draw_rectangle_filled(
            self.left + self.width // 2,
            self.top - self.panel_height // 2,
            self.width,
            self.panel_height,
            self.bg_color
        )
        
        # Draw border
        arcade.draw_rectangle_outline(
            self.left + self.width // 2,
            self.top - self.panel_height // 2,
            self.width,
            self.panel_height,
            self.border_color,
            border_width=2
        )
        
        # Draw header
        header_text = f"Incidents ({len(self.filtered_incidents)})"
        filter_label = f" [{self.filter_type.upper()}]" if self.filter_type else ""
        arcade.draw_text(
            header_text + filter_label,
            self.left + 8,
            self.top - 8,
            self.text_color,
            font_size=self.font_size + 1,
            bold=True
        )
        
        # Draw incidents list
        start_y = self.top - self.header_height - 5
        max_visible = (self.panel_height - self.header_height) // self.item_height
        
        # Clamp scroll offset to valid range
        self.scroll_offset = max(0, min(self.scroll_offset, max(0, len(self.filtered_incidents) - max_visible)))
        
        for list_idx, incident in enumerate(self.filtered_incidents[self.scroll_offset:self.scroll_offset + max_visible]):
            y = start_y - (list_idx * self.item_height)
            # Check if this item is selected (compare absolute index)
            absolute_idx = self.scroll_offset + list_idx
            is_selected = (absolute_idx == self.selected_incident_idx)
            
            # Highlight selected incident
            if is_selected:
                arcade.draw_rectangle_filled(
                    self.left + self.width // 2,
                    y - self.item_height // 2,
                    self.width - 4,
                    self.item_height - 2,
                    (50, 50, 50, 180)
                )
                arcade.draw_rectangle_outline(
                    self.left + self.width // 2,
                    y - self.item_height // 2,
                    self.width - 4,
                    self.item_height - 2,
                    self.selected_color,
                    border_width=1
                )
            
            # Incident text with color coding
            incident_type_color = self.accent_colors.get(incident.incident_type, self.text_color)
            
            text = f"L{int(incident.lap_number)} "
            arcade.draw_text(
                text,
                self.left + 8,
                y - 7,
                self.text_color,
                font_size=self.font_size
            )
            
            # Type and drivers
            detail = f"{incident.incident_type[:4].upper()}"
            if incident.secondary_driver:
                detail += f": {incident.primary_driver} vs {incident.secondary_driver}"
            else:
                detail += f": {incident.primary_driver}"
            
            arcade.draw_text(
                detail,
                self.left + 35,
                y - 7,
                incident_type_color,
                font_size=self.font_size - 1
            )
