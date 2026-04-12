import arcade
from typing import List, Optional
from .base import BaseComponent

class RaceProgressBarComponent(BaseComponent):
    """
    A visual progress bar showing race timeline with event markers:
    - DNF markers (red X)
    - Lap transition markers (vertical lines)
    - Flag markers (red/yellow rectangles)
    
    Uses best practices:
    - Single responsibility: only handles progress bar rendering
    - Efficient rendering with cached markers
    - Clear separation of concerns for event detection
    """
    
    # Event type constants for clear identification
    EVENT_DNF = "dnf"
    EVENT_LAP = "lap"
    EVENT_YELLOW_FLAG = "yellow_flag"
    EVENT_RED_FLAG = "red_flag"
    EVENT_SAFETY_CAR = "safety_car"
    EVENT_VSC = "vsc"
    
    # Color palette following F1 conventions
    COLORS = {
        "background": (30, 30, 30, 200),
        "progress_fill": (0, 180, 0),
        "progress_border": (100, 100, 100),
        "dnf": (220, 50, 50),
        "lap_marker": (80, 80, 80),
        "yellow_flag": (255, 220, 0),
        "red_flag": (220, 30, 30),
        "safety_car": (255, 140, 0),
        "vsc": (255, 165, 0),
        "text": (220, 220, 220),
        "current_position": (255, 255, 255),
    }
    
    def __init__(self, 
                 left_margin: int = 340, 
                 right_margin: int = 260,
                 bottom: int = 30,
                 height: int = 24,
                 marker_height: int = 16):
        """
        Initialize the progress bar component.
        
        Args:
            left_margin: Left margin from window edge
            right_margin: Right margin from window edge
            bottom: Distance from bottom of window
            height: Height of the progress bar
            marker_height: Height of event markers
        """
        self.left_margin = left_margin
        self.right_margin = right_margin
        self.bottom = bottom
        self.height = height
        self.marker_height = marker_height
        
        self._visible: bool = False
        
        # Cached data
        self._events: List[dict] = []
        self._total_frames: int = 0
        self._total_laps: int = 0
        self._bar_left: float = 0
        self._bar_width: float = 0
        
        # Hover state for tooltips
        self._hover_event: Optional[dict] = None
        self._mouse_x: float = 0
        self._mouse_y: float = 0
        
    def set_race_data(self, 
                      total_frames: int, 
                      total_laps: int,
                      events: List[dict]):
        """
        set the race data for the progress bar so the calc for markers can be done once time
        
        - total_frames: Total number of frames in the race
        - total_laps: Total number of laps in the race
        - events: List of event dictionaries with keys
        """
        self._total_frames = max(1, total_frames)
        self._total_laps = total_laps or 1
        self._events = sorted(events, key=lambda e: e.get("frame", 0))
    
    @property
    def visible(self) -> bool:
        return self._visible
    
    @visible.setter
    def visible(self, value: bool):
        self._visible = value
    
    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility of the progress bar
        """
        self._visible = not self._visible
        
        # Also hide/show related components
        for comp in getattr(self, "_related_components", []):
            if isinstance(comp, BaseComponent):
                comp.visible = self._visible
                
        return self._visible
        
    def _calculate_bar_dimensions(self, window):
        self._bar_left = self.left_margin
        self._bar_width = max(100, window.width - self.left_margin - self.right_margin)
        
    def _frame_to_x(self, frame: int, clamp: bool = True) -> float:
        """
        well here convert a frame number to an X position on the bar
        this must receive clamp=True to prevent out-of-bounds rendering
        Args:
            frame: Frame number to convert
            clamp: Whether to clamp frame to valid range [0, total_frames]
        """
        if self._total_frames <= 0:
            return self._bar_left
        
        # here we use Clamp frame to valid range to prevent rendering outside bar bounds
        if clamp:
            frame = max(0, min(frame, self._total_frames))
        
        progress = frame / self._total_frames
        return self._bar_left + (progress * self._bar_width)
    
    def _x_to_frame(self, x: float) -> int:
        # reverse of _frame_to_x
        if self._bar_width <= 0:
            return 0
        progress = (x - self._bar_left) / self._bar_width
        return int(progress * self._total_frames)
        
    def on_resize(self, window):
        self._calculate_bar_dimensions(window)
        
    def draw(self, window):
        """Render the progress bar with all markers"""
        # Skip rendering entirely if hidden
        if not self._visible:
            return
            
        self._calculate_bar_dimensions(window)
        
        current_frame = int(getattr(window, 'frame_index', 0))
        
        bar_center_y = self.bottom + self.height / 2
        
        # 1. Draw background bar
        bg_rect = arcade.XYWH(
            self._bar_left + self._bar_width / 2,
            bar_center_y,
            self._bar_width,
            self.height
        )
        arcade.draw_rect_filled(bg_rect, self.COLORS["background"])
        arcade.draw_rect_outline(bg_rect, self.COLORS["progress_border"], 2)
        
        # 2. Draw progress fill
        if self._total_frames > 0:
            progress_ratio = min(1.0, current_frame / self._total_frames)
            progress_width = progress_ratio * self._bar_width
            if progress_width > 0:
                progress_rect = arcade.XYWH(
                    self._bar_left + progress_width / 2,
                    bar_center_y,
                    progress_width,
                    self.height - 4
                )
                arcade.draw_rect_filled(progress_rect, self.COLORS["progress_fill"])
        
        # 3. Draw lap markers (vertical lines)
        if self._total_laps > 1:
            for lap in range(1, self._total_laps + 1):
                # Approximate frame for lap transition
                lap_frame = int((lap / self._total_laps) * self._total_frames)
                lap_x = self._frame_to_x(lap_frame)
                
                # Draw subtle vertical line
                arcade.draw_line(
                    lap_x, self.bottom + 2,
                    lap_x, self.bottom + self.height - 2,
                    self.COLORS["lap_marker"], 1
                )
                
                # Draw lap number below for major laps (every 5 laps or first/last)
                if lap == 1 or lap == self._total_laps or lap % 10 == 0:
                    arcade.Text(
                        str(lap),
                        lap_x, self.bottom - 4,
                        self.COLORS["text"], 9,
                        anchor_x="center", anchor_y="top"
                    ).draw()
        
        # 4. Draw event markers
        for event in self._events:
            event_x = self._frame_to_x(event.get("frame", 0))
            self._draw_event_marker(event, event_x, bar_center_y)
        
        # 5. Draw current position indicator (playhead)
        current_x = self._frame_to_x(current_frame)
        arcade.draw_line(
            current_x, self.bottom - 2,
            current_x, self.bottom + self.height + 2,
            self.COLORS["current_position"], 3
        )
        
        # 6. Draw legend
        self._draw_legend(window)
    
    # 7. Draw tooltips and overlays after the main draw to prevent them being occluded
    def draw_overlays(self, window):
        """Draw tooltips and other overlays that should appear on top of all UI elements."""
        if not self._visible:
            return
        # Draw hover tooltip if applicable
        if self._hover_event:
            self._draw_tooltip(window, self._hover_event)
            
    def _draw_event_marker(self, event: dict, x: float, center_y: float):
        """Draw a single event marker based on type."""
        event_type = event.get("type", "")
        marker_top = self.bottom + self.height + self.marker_height
        marker_bottom = self.bottom + self.height
        
        if event_type == self.EVENT_DNF:
            # Draw red X marker above the bar
            size = 6
            color = self.COLORS["dnf"]
            y = marker_top - size
            arcade.draw_line(x - size, y - size, x + size, y + size, color, 2)
            arcade.draw_line(x - size, y + size, x + size, y - size, color, 2)
            
        elif event_type == self.EVENT_YELLOW_FLAG:
            # Draw yellow flag indicator on the bar
            self._draw_flag_segment(event, self.COLORS["yellow_flag"])
            
        elif event_type == self.EVENT_RED_FLAG:
            # Draw red flag indicator on the bar
            self._draw_flag_segment(event, self.COLORS["red_flag"])
            
        elif event_type == self.EVENT_SAFETY_CAR:
            # Draw orange segment for safety car
            self._draw_flag_segment(event, self.COLORS["safety_car"])
            
        elif event_type == self.EVENT_VSC:
            # Draw amber segment for VSC
            self._draw_flag_segment(event, self.COLORS["vsc"])
            
    def _draw_flag_segment(self, event: dict, color: tuple):
        start_frame = event.get("frame", 0)
        end_frame = event.get("end_frame", start_frame + 100)  # default duration
        
        clamped_start = max(0, min(start_frame, self._total_frames))
        clamped_end = max(0, min(end_frame, self._total_frames))
        
        if clamped_start >= clamped_end:
            # after clamping, if start >= end, the segment is fully outside the
            # visible race window (e.g., flag ended before frame 0)
            return
        
        # Convert clamped frames to X positions
        start_x = self._frame_to_x(clamped_start)
        end_x = self._frame_to_x(clamped_end)
        
        # Additional safety: clamp X positions to bar boundaries.
        # This provides defense-in-depth against floating-point edge cases
        # that might otherwise cause slight visual overflow on some platforms
        bar_right = self._bar_left + self._bar_width
        start_x = max(self._bar_left, min(start_x, bar_right))
        end_x = max(self._bar_left, min(end_x, bar_right))
        
        # Calculate segment width with minimum visibility threshold
        segment_width = end_x - start_x
        
        # Skip segments with zero or negative visible width after clamping
        if segment_width <= 0:
            return
        
        # Ensure minimum width for visibility (thin flags are hard to see)
        segment_width = max(4, segment_width)
        
        # Draw as a thin bar above the main progress bar
        segment_rect = arcade.XYWH(
            start_x + segment_width / 2,
            self.bottom + self.height + 4,
            segment_width,
            6
        )
        arcade.draw_rect_filled(segment_rect, color)
        
    def _draw_tooltip(self, window, event: dict):
        event_type = event.get("type", "")
        label = event.get("label", "")
        lap = event.get("lap", "")
        
        # Build tooltip text
        type_names = {
            self.EVENT_DNF: "DNF",
            self.EVENT_YELLOW_FLAG: "Yellow Flag",
            self.EVENT_RED_FLAG: "Red Flag",
            self.EVENT_SAFETY_CAR: "Safety Car",
            self.EVENT_VSC: "Virtual SC",
        }
        
        tooltip_text = type_names.get(event_type, "Event")
        if label:
            tooltip_text = f"{tooltip_text}: {label}"
        if lap:
            tooltip_text = f"{tooltip_text} (Lap {lap})"
            
        # Calculate position
        event_x = self._frame_to_x(event.get("frame", 0))
        tooltip_x = min(max(event_x, 100), window.width - 100)
        tooltip_y = self.bottom + self.height + self.marker_height + 20
        
        # Draw tooltip background
        padding = 8
        text_obj = arcade.Text(tooltip_text, 0, 0, (255, 255, 255), 12)
        text_width = text_obj.content_width
        
        bg_rect = arcade.XYWH(
            tooltip_x,
            tooltip_y,
            text_width + padding * 2,
            20
        )
        arcade.draw_rect_filled(bg_rect, (40, 40, 40, 230))
        arcade.draw_rect_outline(bg_rect, (100, 100, 100), 1)
        
        # Draw text
        arcade.Text(
            tooltip_text,
            tooltip_x, tooltip_y,
            (255, 255, 255), 12,
            anchor_x="center", anchor_y="center"
        ).draw()
        
    def _draw_legend(self, window):
        """Draw a small legend explaining the markers."""
        legend_items = [
            (self.COLORS["yellow_flag"], "■", "Yellow"),
            (self.COLORS["red_flag"], "■", "Red"),
            (self.COLORS["safety_car"], "■", "SC"),
            (self.COLORS["vsc"], "■", "VSC"),
        ]
        
        legend_x = self._bar_left + self._bar_width + 50
        legend_y = self.bottom + self.height / 2
        
        for i, (color, symbol, label) in enumerate(legend_items):
            x = legend_x + (i * 45)
            arcade.Text(
                symbol,
                x, legend_y + 2,
                color, 10, bold=True,
                anchor_x="center", anchor_y="center"
            ).draw()
            arcade.Text(
                label,
                x, legend_y - 10,
                self.COLORS["text"], 8,
                anchor_x="center", anchor_y="top"
            ).draw()
        
    def on_mouse_motion(self, window, x: float, y: float, dx: float, dy: float):
        """Handle mouse motion for hover effects."""
        if not self._visible:
            return
            
        self._mouse_x = x
        self._mouse_y = y
        
        # Check if mouse is over the progress bar area
        if (self._bar_left <= x <= self._bar_left + self._bar_width and
            self.bottom <= y <= self.bottom + self.height + self.marker_height + 10):
            
            # Find nearest event
            mouse_frame = self._x_to_frame(x)
            nearest_event = None
            min_dist = float('inf')
            
            for event in self._events:
                event_frame = event.get("frame", 0)
                dist = abs(event_frame - mouse_frame)
                
                # Close enough to show tooltip
                if dist < 50 and dist < min_dist:
                    min_dist = dist
                    nearest_event = event
            
            self._hover_event = nearest_event
        else:
            self._hover_event = None

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int):
        """Handle mouse clicks on the progress bar for seeking."""
        if not self._visible:
            return False
            
        # If click is on the progress bar area
        if (self._bar_left <= x <= self._bar_left + self._bar_width and
            self.bottom <= y <= self.bottom + self.height):
            
            # Seek to the clicked frame
            target_frame = self._x_to_frame(x)
            if hasattr(window, 'frame_index'):
                window.frame_index = float(max(0, min(target_frame, self._total_frames - 1)))
            return True
            
        return False
