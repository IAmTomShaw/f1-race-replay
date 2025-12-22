from abc import ABC, abstractmethod

class BaseComponent(ABC):
    """
    Abstract base class for all UI components.
    Enforces a consistent interface for drawing and event handling.
    """
    
    def on_resize(self, window):
        """Handle window resize events."""
        pass

    @abstractmethod
    def draw(self, window):
        """Draw the component."""
        pass

    def on_mouse_press(self, window, x: float, y: float, button: int, modifiers: int) -> bool:
        """
        Handle mouse press events.
        Returns True if the event was consumed.
        """
        return False
