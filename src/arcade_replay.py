import os
import arcade
from src.interfaces.race_replay import F1RaceReplayWindow

# Kept these as "default" starting sizes, but they are no longer hard limits
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1200
SCREEN_TITLE = "F1 Race Replay"

def run_arcade_replay(frames, track_statuses, example_lap, drivers, title,
                      playback_speed=1.0, driver_colors=None, circuit_rotation=0.0, total_laps=None, 
                      grid_positions=None,
                      visible_hud=True):
    window = F1RaceReplayWindow(
        frames=frames,
        track_statuses=track_statuses,
        example_lap=example_lap,
        drivers=drivers,
        playback_speed=playback_speed,
        driver_colors=driver_colors,
        title=title,
        total_laps=total_laps,
        circuit_rotation=circuit_rotation,
        grid_positions=grid_positions,
        visible_hud=visible_hud,
    )
    arcade.run()
