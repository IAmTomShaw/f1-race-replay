from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.arcade_replay import run_arcade_replay

from src.interfaces.qualifying import run_qualifying_replay
import sys
from src.cli.race_selection import cli_load
from src.gui.race_selection import RaceSelectionWindow
from PySide6.QtWidgets import QApplication

def main(year=None, round_number=None, playback_speed=1, session_type='R', visible_hud=True, ready_file=None):
  print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
  session = load_session(year, round_number, session_type)

  print(f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']} - {session_type}")

  # Enable cache for fastf1
  enable_cache()

  if session_type == 'Q' or session_type == 'SQ':

    # Get the drivers who participated and their lap times

    qualifying_session_data = get_quali_telemetry(session, session_type=session_type)

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
      visible_hud=visible_hud
      ,ready_file=ready_file
    )

if __name__ == "__main__":

    args = sys.argv

    # GUI mode
    if "--gui" in args:
        app = QApplication(args)
        win = RaceSelectionWindow()
        win.show()
        sys.exit(app.exec())

    # CLI loader
    if "--cli" in args:
        cli_load()
        sys.exit(0)

    # Defaults
    year = 2025
    round_number = 12
    playback_speed = 1
    visible_hud = True
    ready_file = None

    # Argument parsing
    if "--year" in args:
        idx = args.index("--year") + 1
        if idx < len(args):
            year = int(args[idx])

    if "--round" in args:
        idx = args.index("--round") + 1
        if idx < len(args):
            round_number = int(args[idx])

    # Listing modes
    if "--list-rounds" in args:
        list_rounds(year)
        sys.exit(0)

    if "--list-sprints" in args:
        list_sprints(year)
        sys.exit(0)

    # HUD
    if "--no-hud" in args:
        visible_hud = False

    # Session type selection
    if "--sprint-qualifying" in args:
        session_type = "SQ"
    elif "--sprint" in args:
        session_type = "S"
    elif "--qualifying" in args:
        session_type = "Q"
    else:
        session_type = "R"

    # Optional read-only path used when spawned from the GUI
    # to signal ready state
    if "--ready-file" in args:
        idx = args.index("--ready-file") + 1
        if idx < len(args):
            ready_file = args[idx]

    # Run main
    main(
        year,
        round_number,
        playback_speed,
        session_type=session_type,
        visible_hud=visible_hud,
        ready_file=ready_file,
    )
