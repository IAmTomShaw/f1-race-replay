import os
import subprocess
import sys
import threading
import time
from typing import List, Dict, Optional, Any, Tuple
import arcade
from src.lib.logging import get_logger
from src.interfaces.race_replay import F1RaceReplayWindow

logger = get_logger(__name__)
from src.insights.telemetry_stream_viewer import main as telemetry_viewer_main

def run_arcade_replay(
    frames: List[Dict[str, Any]],
    track_statuses: List[Dict[str, Any]],
    example_lap: Any,
    drivers: List[str],
    title: str,
    playback_speed: float = 1.0,
    driver_colors: Optional[Dict[str, Tuple[int, int, int]]] = None,
    circuit_rotation: float = 0.0,
    total_laps: Optional[int] = None,
    visible_hud: bool = True,
    ready_file: Optional[str] = None,
    session_info: Optional[Dict[str, Any]] = None,
    session: Optional[Any] = None,
    enable_telemetry: bool = True,
) -> None:
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


def launch_telemetry_viewer() -> None:
  # Launch the telemetry stream viewer in a separate process.
  def start_viewer() -> None:
    try:
      # Give the main application a moment to start the telemetry server
      time.sleep(3)
      subprocess.run([sys.executable, "-m", "src.insights.telemetry_stream_viewer"], check=False)
    except Exception as e:
      logger.error("Failed to launch telemetry viewer: %s", e)
  
  viewer_thread = threading.Thread(target=start_viewer, daemon=True)
  viewer_thread.start()


def launch_insights_menu() -> None:
  def start_menu() -> None:
    try:
      # Give the main application a moment to start
      time.sleep(1)
      subprocess.run([sys.executable, "-m", "src.gui.insights_menu"], check=False)
    except Exception as e:
      logger.error("Failed to launch insights menu: %s", e)
  
  menu_thread = threading.Thread(target=start_menu, daemon=True)
  menu_thread.start()