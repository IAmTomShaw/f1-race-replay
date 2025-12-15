import os
import arcade
from src.interfaces.race_replay import ReplayView, MainMenuView, run_main_menu

# Kept these as "default" starting sizes, but they are no longer hard limits
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
SCREEN_TITLE = "F1 Race Replay System"


def run_arcade_replay(frames=None, track_statuses=None, example_lap=None, drivers=None, title=None,
                      playback_speed=1.0, driver_colors=None, circuit_rotation=0.0, total_laps=None, chart=False):
    # 1. Create the single, main window for the entire application
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, resizable=True)

    # 2. Check for CLI Mode (Arguments provided)
    if frames is not None:
        # CLI Mode: Start directly in Replay View
        print("Running in CLI Mode. Launching Replay View...")

        # Instantiate the Replay View
        replay_view = ReplayView(
            window,  # Pass the window instance
            frames=frames,
            track_statuses=track_statuses,
            example_lap=example_lap,
            drivers=drivers,
            playback_speed=playback_speed,
            driver_colors=driver_colors,
            title=title,
            total_laps=total_laps,
            circuit_rotation=circuit_rotation,
        )
        # Set the initial view
        window.show_view(replay_view)
    else:
        # Launcher Mode: Start with Main Menu View
        print("No arguments provided. Launching Main Menu View...")

        # Start with the Main Menu View
        main_menu_view = MainMenuView(window)
        window.show_view(main_menu_view)

    # 3. Run the entire application loop ONCE.
    arcade.run()