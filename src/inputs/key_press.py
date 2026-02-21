from .base import Command

class CloseWindowCommand(Command):
    def execute(self, window) -> None:
        arcade.close_window()

class TogglePauseCommand(Command):
    def execute(self, window) -> None:
        window.paused = not window.paused
        window.race_controls_comp.flash_button('play_pause')


class StartForwardCommand(Command):
    
    def execute(self, window) -> None:
        window.was_paused_before_hold = window.paused
        window.is_forwarding = True
        window.paused = True

class StartRewindCommand(Command):
    
    def execute(self, window) -> None:
        window.was_paused_before_hold = window.paused
        window.is_rewinding = True
        window.paused = True


class BaseSpeedCommand(Command):
    STEP = 0.5
    MIN_SPEED = 0.1
    MAX_SPEED = 4

    def clamp(self, value: float) -> float:
        return max(self.MIN_SPEED, min(self.MAX_SPEED, value))

class IncreaseSpeedCommand(BaseSpeedCommand):
    def execute(self, window) -> None:
        speed = window.playback_speed

        if speed == self.MIN_SPEED:
            speed += 0.4  # jump from 0.1 → 0.5
        else:
            speed += self.STEP

        window.playback_speed = self.clamp(speed)
        window.race_controls_comp.flash_button('speed_increase')


class DecreaseSpeedCommand(BaseSpeedCommand):
    def execute(self, window) -> None:
        window.playback_speed = self.clamp(
            window.playback_speed - self.STEP
        )
        window.race_controls_comp.flash_button('speed_decrease')


class SetSpeedCommand(Command):
    
    def __init__(self, speed: float, button_name: str = 'speed_decrease'):
        self.speed = speed
        self.button_name = button_name
    
    def execute(self, window) -> None:
        window.playback_speed = self.speed
        window.race_controls_comp.flash_button(self.button_name)


class RestartCommand(Command):
    
    def execute(self, window) -> None:
        window.frame_index = 0.0
        window.playback_speed = 1.0
        if window.degradation_integrator:
            window.degradation_integrator.clear_cache()
        window.race_controls_comp.flash_button('rewind')


class ToggleDRSZonesCommand(Command):
    
    def execute(self, window) -> None:
        window.toggle_drs_zones = not window.toggle_drs_zones


class ToggleDriverLabelsCommand(Command):
    
    def execute(self, window) -> None:
        window.show_driver_labels = not window.show_driver_labels


class ToggleHelpPopupCommand(Command):
    
    def execute(self, window) -> None:
        margin_x = 20
        margin_y = 20
        left_pos = float(margin_x)
        top_pos = float(margin_y + window.controls_popup_comp.height)
        
        if window.controls_popup_comp.visible:
            window.controls_popup_comp.hide()
        else:
            window.controls_popup_comp.show_over(left_pos, top_pos)


class ToggleProgressBarCommand(Command):
    
    def execute(self, window) -> None:
        window.progress_bar_comp.toggle_visibility()


class ToggleSessionInfoCommand(Command):
    
    def execute(self, window) -> None:
        window.session_info_comp.toggle_visibility()
