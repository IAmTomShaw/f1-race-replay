import sys
import logging
import os

# Enable DPI awareness on Windows for crisp rendering on high-DPI displays
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.lib.season import get_season
# PHASE J: argparse-based CLI parser. The legacy ``main.py``
# did manual ``if "--flag" in sys.argv`` chains; the new
# ``parse_args`` is the single source of truth. Public
# behaviour (no-arg = GUI, --cli = CLI menu, --viewer =
# viewer, --list-rounds/--list-sprints = list, --diagnostics =
# print report and exit) is preserved.
from src.cli.args import parse_args, session_type as _resolve_session_type

def main(year=None, round_number=None, playback_speed=1, session_type='R', visible_hud=True, ready_file=None, show_telemetry_viewer=True):
  from src.interfaces.qualifying import run_qualifying_replay
  from src.run_session import run_arcade_replay, launch_insights_menu

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
    
    # Prepare session info for display banner
    session_info = {
        'event_name': session.event.get('EventName', ''),
        'circuit_name': session.event.get('Location', ''),  # Circuit location/name
        'country': session.event.get('Country', ''),
        'year': year,
        'round': round_number,
        'date': session.event.get('EventDate', '').strftime('%B %d, %Y') if session.event.get('EventDate') else '',
        'total_laps': race_telemetry['total_laps'],
        'circuit_length_m': float(example_lap["Distance"].max()) if example_lap is not None and "Distance" in example_lap else None,
    }

    # Launch insights menu (always shown with replay)
    launch_insights_menu()
    print("Launching insights menu...")

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
      enable_telemetry=True,
      race_control_messages=race_telemetry.get('race_control_messages', [])
    )

if __name__ == "__main__":

  if "--verbose" not in sys.argv:# fastf1 logging is disabled by default
    logging.getLogger("fastf1").setLevel(logging.CRITICAL)

  # PHASE J: delegate argv parsing to the argparse-based
  # ``parse_args``. The dispatch below preserves the legacy
  # behaviour exactly.
  args = parse_args()

  # Early-exit branches: --diagnostics, --cli, --list-rounds,
  # --list-sprints.
  if args.diagnostics:
    from src.tools.diagnostics import collect_diagnostics
    print(collect_diagnostics())
    sys.exit(0)
  if args.cli:
    from src.cli.race_selection import cli_load
    cli_load()
    sys.exit(0)
  if args.list_rounds:
    yr = args.year if args.year is not None else get_season()
    list_rounds(yr)
    sys.exit(0)
  if args.list_sprints:
    yr = args.year if args.year is not None else get_season()
    list_sprints(yr)
    sys.exit(0)

  # If the user asked for the viewer explicitly, run the legacy
  # viewer path. If they passed --year without --viewer, fall
  # through to the GUI as before.
  if args.viewer:
    year = args.year if args.year is not None else get_season()
    round_number = args.round if args.round is not None else 12
    visible_hud = not args.no_hud
    main(year, round_number, 1,
          session_type=_resolve_session_type(args),
          visible_hud=visible_hud,
          ready_file=args.ready_file)
    sys.exit(0)

  # Run the GUI

  from PySide6.QtWidgets import QApplication
  from src.gui.race_selection import RaceSelectionWindow

  # Enable high-DPI scaling for sharp text/icons on modern displays
  os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

  app = QApplication(sys.argv)
  win = RaceSelectionWindow()
  win.show()
  sys.exit(app.exec())
