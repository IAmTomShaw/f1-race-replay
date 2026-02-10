import os
import subprocess
import sys
import threading
import time
import arcade
from src.interfaces.race_replay import F1RaceReplayWindow
from src.gui.telemetry_stream_viewer import main as telemetry_viewer_main

def run_arcade_replay(frames, track_statuses, example_lap, drivers, title,
                      playback_speed=1.0, driver_colors=None, circuit_rotation=0.0, total_laps=None,
                      visible_hud=True, ready_file=None, session_info=None, session=None, enable_telemetry=False):
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
        visible_hud=visible_hud,
        session_info=session_info,
        session=session,
        enable_telemetry=enable_telemetry
    )
    # Signal readiness to parent process (if requested) after window created
    if ready_file:
        try:
            with open(ready_file, 'w') as f:
                f.write('ready')
        except Exception:
            pass
    arcade.run()


def launch_telemetry_viewer():
  # Launch the telemetry stream viewer in a separate process.
  def start_viewer():
    try:
      # Give the main application a moment to start the telemetry server
      time.sleep(3)
      subprocess.run([sys.executable, "-m", "src.gui.telemetry_stream_viewer"], check=False)
    except Exception as e:
      print(f"Failed to launch telemetry viewer: {e}")
  
  viewer_thread = threading.Thread(target=start_viewer, daemon=True)
  viewer_thread.start()