from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.arcade_replay import run_arcade_replay

from src.interfaces.qualifying import run_qualifying_replay
import sys
import os
from src.cli.race_selection import cli_load
from src.gui.race_selection import RaceSelectionWindow
from PySide6.QtWidgets import QApplication

def main(year=None, round_number=None, playback_speed=1, session_type='R', visible_hud=True, ready_file=None):
  # Enable cache for fastf1
  enable_cache()

  # 1. Try to load precomputed data first (Near-instant startup)
  cache_suffix = 'sprintquali' if session_type == 'SQ' else ('quali' if session_type == 'Q' else ('sprint' if session_type == 'S' else 'race'))
  
  pickle_data = None
  if "--refresh-data" not in sys.argv:
    if os.path.exists("computed_data"):
      # Robust search for pickle matching year AND round AND suffix
      # Filenames are usually: {EventName}_{Suffix}_telemetry.pkl
      # We don't have EventName yet, so we scan for Year and Round_X
      for f in os.listdir("computed_data"):
        if f.endswith(f"{cache_suffix}_telemetry.pkl"):
          # Standardize check: look for year and round in filename or metadata
          # FastF1 session string usually contains year and name
          if str(year) in f:
             # Check for for round pattern like '_9_' or '_Round_9_' or similar
             # Actually, we can just try to open and check metadata if year matches
             try:
               with open(os.path.join("computed_data", f), "rb") as pf:
                 data = pickle.load(pf)
                 if data.get('round_number') == round_number:
                   # Ensure the cache is "complete" (has layout data)
                   if data.get('layout_telemetry') is not None:
                       pickle_data = data
                       print(f"Loaded precomputed data from {f}")
                       break
             except Exception: continue

  if pickle_data:
      # Run directly from cached data - No FastF1 loading needed!
      if session_type == 'Q' or session_type == 'SQ':
          run_qualifying_replay(
            session=None, # Replay interface updated to handle None session if metadata exists
            data=pickle_data,
            title=f"{pickle_data.get('event_name', 'F1 Replay')} - Qualifying Results",
            ready_file=ready_file,
          )
      else:
          run_arcade_replay(
            frames=pickle_data['frames'],
            track_statuses=pickle_data['track_statuses'],
            example_lap=pickle_data.get('layout_telemetry'),
            drivers=pickle_data.get('drivers', []),
            playback_speed=playback_speed,
            driver_colors=pickle_data['driver_colors'],
            title=f"{pickle_data.get('event_name', 'F1 Replay')} - {'Sprint' if session_type == 'S' else 'Race'}",
            total_laps=pickle_data['total_laps'],
            circuit_rotation=pickle_data.get('circuit_rotation', 0),
            visible_hud=visible_hud,
            ready_file=ready_file
          )
      return

  # 2. Fallback: Full data load (Heavy)
  print(f"No precomputed data found. Loading F1 {year} Round {round_number} Session '{session_type}'...")
  session = load_session(year, round_number, session_type)
  print(f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']}")

  if session_type == 'Q' or session_type == 'SQ':
    qualifying_session_data = get_quali_telemetry(session, session_type=session_type)
    run_qualifying_replay(
      session=session,
      data=qualifying_session_data,
      title=f"{session.event['EventName']} - Qualifying Results",
      ready_file=ready_file,
    )
  else:
    race_telemetry = get_race_telemetry(session, session_type=session_type)
    run_arcade_replay(
      frames=race_telemetry['frames'],
      track_statuses=race_telemetry['track_statuses'],
      example_lap=race_telemetry.get('layout_telemetry'),
      drivers=session.drivers,
      playback_speed=playback_speed,
      driver_colors=race_telemetry['driver_colors'],
      title=f"{session.event['EventName']} - {'Sprint' if session_type == 'S' else 'Race'}",
      total_laps=race_telemetry['total_laps'],
      circuit_rotation=race_telemetry.get('circuit_rotation', 0),
      visible_hud=visible_hud,
      ready_file=ready_file
    )

if __name__ == "__main__":
  # 1. Check for Replay Viewer mode (usually called as a subprocess)
  if "--viewer" in sys.argv:
    year = 2025
    if "--year" in sys.argv:
      year = int(sys.argv[sys.argv.index("--year") + 1])
    
    round_number = 1
    if "--round" in sys.argv:
      round_number = int(sys.argv[sys.argv.index("--round") + 1])
    
    visible_hud = "--no-hud" not in sys.argv
    session_type = 'SQ' if "--sprint-qualifying" in sys.argv else \
                   ('S' if "--sprint" in sys.argv else \
                   ('Q' if "--qualifying" in sys.argv else 'R'))
    
    ready_file = None
    if "--ready-file" in sys.argv:
      idx = sys.argv.index("--ready-file") + 1
      if idx < len(sys.argv):
        ready_file = sys.argv[idx]
    
    main(year, round_number, session_type=session_type, visible_hud=visible_hud, ready_file=ready_file)
    sys.exit(0)

  # 2. Check for explicit CLI request
  if "--cli" in sys.argv or "--terminal" in sys.argv:
    cli_load()
    sys.exit(0)

  # 3. Default: Launch GUI
  app = QApplication(sys.argv)
  win = RaceSelectionWindow()
  win.show()
  sys.exit(app.exec())