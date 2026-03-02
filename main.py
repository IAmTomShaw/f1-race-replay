from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints, get_previous_year_drs_data
from src.run_session import run_arcade_replay, launch_insights_menu
from src.interfaces.qualifying import run_qualifying_replay
import sys
from src.cli.race_selection import cli_load
from src.gui.race_selection import RaceSelectionWindow
from PySide6.QtWidgets import QApplication

def main(year=None, round_number=None, playback_speed=1, session_type='R', visible_hud=True, ready_file=None, show_telemetry_viewer=True):
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

    # If the example_lap has no meaningful DRS activations, try to borrow
    # DRS zone data from the previous year's qualifying for the same circuit.
    has_active_drs = (
        'DRS' in example_lap.columns
        and any(val in (10, 12, 14) for val in example_lap['DRS'])
    )
    if not has_active_drs:
        import numpy as np
        event_name = session.event['EventName']
        print(f"No DRS activations in example lap. Trying previous year's qualifying for '{event_name}'...")
        prev_drs = get_previous_year_drs_data(event_name, year)
        if prev_drs is not None:
            prev_rel_dist, prev_drs_vals = prev_drs
            order = np.argsort(prev_rel_dist)
            prev_rel_sorted = prev_rel_dist[order]
            prev_drs_sorted = prev_drs_vals[order]

            curr_rel_dist = example_lap['RelativeDistance'].to_numpy()
            idxs = np.searchsorted(prev_rel_sorted, curr_rel_dist, side='right') - 1
            idxs = np.clip(idxs, 0, len(prev_rel_sorted) - 1)

            example_lap = example_lap.copy()
            example_lap['DRS'] = prev_drs_sorted[idxs]
            print(f"DRS zones mapped from {year - 1} qualifying onto current track layout")
        else:
            print("No previous year DRS data available. DRS zones will not be shown.")

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
      enable_telemetry=True # This is now permanently enabled to support the telemetry insights menu if the user decides to use it
    )

if __name__ == "__main__":

  if "--cli" in sys.argv:
    # Run the CLI

    cli_load()
    sys.exit(0)

  if "--year" in sys.argv:
    year_index = sys.argv.index("--year") + 1
    year = int(sys.argv[year_index])
  else:
    year = 2025  # Default year

  if "--round" in sys.argv:
    round_index = sys.argv.index("--round") + 1
    round_number = int(sys.argv[round_index])
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

    main(year, round_number, playback_speed, session_type=session_type, visible_hud=visible_hud, ready_file=ready_file)
    sys.exit(0)

  # Run the GUI

  app = QApplication(sys.argv)
  win = RaceSelectionWindow()
  win.show()
  sys.exit(app.exec())