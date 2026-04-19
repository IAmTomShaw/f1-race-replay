from .base import Command

class StopForwardCommand(Command):
    
    def execute(self, window) -> None:
        window.is_forwarding = False
        window.paused = window.was_paused_before_hold

class StopRewindCommand(Command):
    
    def execute(self, window) -> None:
        window.is_rewinding = False
        window.paused = window.was_paused_before_hold
