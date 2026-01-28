from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.arcade_replay import run_arcade_replay
from src.race_comparison import RaceComparison, RaceData, SyncMode

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
      session_info=session_info
    )

def comparison_mode(year_a, round_a, year_b, round_b, session_type='R'):
    """Load and compare two races"""
    enable_cache()
    
    print(f"\n{'='*60}")
    print(f"RACE COMPARISON MODE")
    print(f"{'='*60}")
    print(f"\nLoading Race A: {year_a} Round {round_a}")
    session_a = load_session(year_a, round_a, session_type)
    data_a = get_race_telemetry(session_a, session_type)
    
    race_a = RaceData(
        frames=data_a['frames'],
        driver_colors=data_a['driver_colors'],
        track_statuses=data_a['track_statuses'],
        total_laps=data_a['total_laps'],
        year=year_a,
        round_number=round_a,
        event_name=session_a.event['EventName'],
        session_type=session_type
    )
    print(f"✓ Loaded: {session_a.event['EventName']}")
    
    print(f"\nLoading Race B: {year_b} Round {round_b}")
    session_b = load_session(year_b, round_b, session_type)
    data_b = get_race_telemetry(session_b, session_type)
    
    race_b = RaceData(
        frames=data_b['frames'],
        driver_colors=data_b['driver_colors'],
        track_statuses=data_b['track_statuses'],
        total_laps=data_b['total_laps'],
        year=year_b,
        round_number=round_b,
        event_name=session_b.event['EventName'],
        session_type=session_type
    )
    print(f"✓ Loaded: {session_b.event['EventName']}")
    
    print(f"\nBuilding race comparison...")
    comparison = RaceComparison(race_a, race_b, SyncMode.LAP)
    print(f"✓ Synchronized {comparison.get_total_frames()} frames")
    
    # Get circuit info and example laps from BOTH races
    print(f"\nLoading track layouts...")
    
    # Load track A
    try:
        quali_session_a = load_session(year_a, round_a, 'Q')
        fastest_quali_a = quali_session_a.laps.pick_fastest()
        example_lap_a = fastest_quali_a.get_telemetry()
        print("✓ Using qualifying lap for Race A track layout")
    except:
        fastest_lap_a = session_a.laps.pick_fastest()
        example_lap_a = fastest_lap_a.get_telemetry()
        print("✓ Using race lap for Race A track layout")
    
    circuit_rotation_a = get_circuit_rotation(session_a)
    
    # Load track B
    try:
        quali_session_b = load_session(year_b, round_b, 'Q')
        fastest_quali_b = quali_session_b.laps.pick_fastest()
        example_lap_b = fastest_quali_b.get_telemetry()
        print("✓ Using qualifying lap for Race B track layout")
    except:
        fastest_lap_b = session_b.laps.pick_fastest()
        example_lap_b = fastest_lap_b.get_telemetry()
        print("✓ Using race lap for Race B track layout")
    
    circuit_rotation_b = get_circuit_rotation(session_b)
    
    print(f"\n{'='*60}")
    print(f"Starting comparison viewer...")
    print(f"{'='*60}\n")
    
    from src.interfaces.comparison_viewer import run_comparison_viewer
    run_comparison_viewer(comparison, example_lap_a, example_lap_b, 
                         circuit_rotation_a, circuit_rotation_b)

if __name__ == "__main__":

  if "--cli" in sys.argv:
    # Run the CLI
    cli_load()
    sys.exit(0)

  # Handle comparison mode FIRST (before other argument parsing)
  if "--compare" in sys.argv:
    if "--year" not in sys.argv or "--round" not in sys.argv:
      print("Error: --compare requires --year, --round, --year-b, and --round-b")
      sys.exit(1)
    
    if "--year-b" not in sys.argv or "--round-b" not in sys.argv:
      print("Error: --compare requires both --year-b and --round-b")
      sys.exit(1)
    
    year_a = int(sys.argv[sys.argv.index("--year") + 1])
    round_a = int(sys.argv[sys.argv.index("--round") + 1])
    year_b = int(sys.argv[sys.argv.index("--year-b") + 1])
    round_b = int(sys.argv[sys.argv.index("--round-b") + 1])
    
    session_type = 'S' if "--sprint" in sys.argv else 'R'
    
    comparison_mode(year_a, round_a, year_b, round_b, session_type)
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
  

  # Run the GUI (only if not in viewer or compare mode)
  app = QApplication(sys.argv)
  win = RaceSelectionWindow()
  win.show()
  sys.exit(app.exec())