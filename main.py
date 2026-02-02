import sys
import os
import subprocess # Needed to spawn the second window
import arcade

from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.arcade_replay import run_arcade_replay
from src.interfaces.qualifying import run_qualifying_replay
from src.cli.race_selection import cli_load
from src.gui.race_selection import RaceSelectionWindow
from PySide6.QtWidgets import QApplication

# Import the new runner function for the telemetry window
# (Make sure you added 'def run_telemetry_monitor' to src/interfaces/telemetry_window.py)
from src.interfaces.telemetry_window import run_telemetry_monitor

    # Run the arcade screen showing qualifying results

    title = f"{session.event['EventName']} - {'Sprint Qualifying' if session_type == 'SQ' else 'Qualifying Results'}"
    
    run_qualifying_replay(
      session=session,
      data=qualifying_session_data,
      title=title,
      ready_file=ready_file,
    )

  else:

    # Get the drivers who participated in the race

    race_telemetry = get_race_telemetry(session, session_type=session_type)

    # Get example lap for track layout
    # Qualifying lap preferred for DRS zones (fallback to fastest race lap (no DRS data))
    example_lap = None
    
    try:
        print("Attempting to load qualifying session for track layout...")
        quali_session = load_session(year, round_number, 'Q')
        if quali_session is not None and len(quali_session.laps) > 0:
            fastest_quali = quali_session.laps.pick_fastest()
            if fastest_quali is not None:
                quali_telemetry = fastest_quali.get_telemetry()
                if 'DRS' in quali_telemetry.columns:
                    example_lap = quali_telemetry
                    print(f"Using qualifying lap from driver {fastest_quali['Driver']} for DRS Zones")
    except Exception as e:
        print(f"Could not load qualifying session: {e}")

    # fallback: Use fastest race lap
    if example_lap is None:
        fastest_lap = session.laps.pick_fastest()
        if fastest_lap is not None:
            example_lap = fastest_lap.get_telemetry()
            print("Using fastest race lap (DRS detection may use speed-based fallback)")
        else:
            print("Error: No valid laps found in session")
            return

    drivers = session.drivers

    # Get circuit rotation

    circuit_rotation = get_circuit_rotation(session)
    
    # Prepare session info for display banner
    session_info = {
        'event_name': session.event.get('EventName', ''),
        'circuit_name': session.event.get('Location', ''),  # Circuit location/name
        'country': session.event.get('Country', ''),
        'year': year,
        'round': round_number,
        'date': session.event.get('EventDate', '').strftime('%B %d, %Y') if session.event.get('EventDate') else '',
        'total_laps': race_telemetry['total_laps']
    }

    # Run the arcade replay

    run_arcade_replay(
      frames=race_telemetry['frames'],
      track_statuses=race_telemetry['track_statuses'],
      example_lap=example_lap,
      drivers=drivers,
      playback_speed=playback_speed,
      driver_colors=race_telemetry['driver_colors'],
      title=f"{session.event['EventName']} - {'Sprint' if session_type == 'S' else 'Race'}",
      total_laps=race_telemetry['total_laps'],
      circuit_rotation=circuit_rotation,
      visible_hud=visible_hud,
      ready_file=ready_file,
      session_info=session_info,
      session=session,
    )

if __name__ == "__main__":

    if "--cli" in sys.argv:
        # Run the CLI
        cli_load()
        sys.exit(0)

    if "--year" in sys.argv:
        try:
            year_index = sys.argv.index("--year") + 1
            year = int(sys.argv[year_index])
        except (ValueError, IndexError):
            year = 2025
    else:
        year = 2025  # Default year

    if "--round" in sys.argv:
        try:
            round_index = sys.argv.index("--round") + 1
            round_number = int(sys.argv[round_index])
        except (ValueError, IndexError):
            round_number = 12
    else:
        round_number = 12  # Default round number

    if "--list-rounds" in sys.argv:
        list_rounds(year)
    elif "--list-sprints" in sys.argv:
        list_sprints(year)
    else:
        playback_speed = 1

    if "--viewer" in sys.argv:
    
        visible_hud = True
        if "--no-hud" in sys.argv:
            visible_hud = False

        # Session type selection
        session_type = 'SQ' if "--sprint-qualifying" in sys.argv else ('S' if "--sprint" in sys.argv else ('Q' if "--qualifying" in sys.argv else 'R'))

        # Optional ready-file path used when spawned from the GUI to signal ready state
        ready_file = None
        if "--ready-file" in sys.argv:
            idx = sys.argv.index("--ready-file") + 1
            if idx < len(sys.argv):
                ready_file = sys.argv[idx]

        # NOTE: "--monitor" and "--telemetry-child" are checked inside main()
        # utilizing sys.argv directly.
        main(year, round_number, playback_speed, session_type=session_type, visible_hud=visible_hud, ready_file=ready_file)
        sys.exit(0)

    # Run the GUI
    app = QApplication(sys.argv)
    win = RaceSelectionWindow()
    win.show()
    sys.exit(app.exec())