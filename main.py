from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.run_session import run_arcade_replay, launch_insights_menu, run_live_arcade_replay
from src.interfaces.qualifying import run_qualifying_replay
import sys
from src.cli.race_selection import cli_load
from src.gui.race_selection import RaceSelectionWindow
from PySide6.QtWidgets import QApplication
from src.lib.season import get_season
import logging

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

def live_main(ready_file=None):
  """Entry point for live race viewing via OpenF1."""
  import datetime
  import time as _time
  import fastf1
  from src.live_f1_data import (
      get_current_session, is_session_live,
      get_session_drivers, get_driver_colors_from_openf1,
      find_round_number, load_circuit_layout, LiveDataFeed,
  )

  print("Checking for a live F1 session via OpenF1…")
  session_info = get_current_session()

  if not session_info:
    print("Error: Could not reach the OpenF1 API. Check your internet connection.")
    return

  location     = session_info.get("location", "Unknown")
  session_name = session_info.get("session_name", "Unknown")
  year         = int(session_info.get("year", get_season()))
  session_key  = int(session_info["session_key"])

  if not is_session_live(session_info):
    date_start = session_info.get("date_start", "")
    print(f"No live session right now.")
    print(f"Most recent: {location} — {session_name}  ({date_start})")
    print("Run with --live again when a session is in progress.")
    return

  print(f"Live session: {location} — {session_name}  (session key {session_key})")

  # ---- Drivers --------------------------------------------------------
  print("Fetching driver list…")
  drivers_info  = get_session_drivers(session_key)
  driver_colors = get_driver_colors_from_openf1(drivers_info)
  drivers       = [info.get("name_acronym", num) for num, info in drivers_info.items()]
  print(f"  {len(drivers_info)} drivers found")

  # ---- Circuit layout from FastF1 -------------------------------------
  enable_cache()
  circuit_short = session_info.get("circuit_short_name", "")

  print("Finding round number from FastF1 schedule…")
  round_number = find_round_number(year, location, circuit_short)

  example_lap      = None
  circuit_rotation = 0.0
  fastf1_session   = None

  if round_number:
    print(f"  Round {round_number} — loading circuit layout from FastF1…")
    example_lap, fastf1_session = load_circuit_layout(year, round_number)
    if example_lap is not None and fastf1_session is not None:
      circuit_rotation = get_circuit_rotation(fastf1_session)
      # Refine driver colours from FastF1 where possible
      try:
        from src.f1_data import get_driver_colors as _gdc
        ff1_colors = _gdc(fastf1_session)
        driver_colors.update(ff1_colors)
      except Exception:
        pass
  else:
    print("  Could not find round number — trying previous-year layout…")
    for prev_year in range(year - 1, max(year - 4, 2018), -1):
      rn = find_round_number(prev_year, location, circuit_short)
      if rn:
        example_lap, _ = load_circuit_layout(prev_year, rn)
        if example_lap is not None:
          print(f"  Using circuit layout from {prev_year} Round {rn}")
          break

  if example_lap is None:
    print("Error: Could not load circuit layout. Cannot open the visualiser.")
    return

  # ---- Live data feed -------------------------------------------------
  date_start_str = session_info.get("date_start", "")
  try:
    session_start = datetime.datetime.fromisoformat(date_start_str.replace("Z", "+00:00"))
  except Exception:
    session_start = datetime.datetime.now(datetime.timezone.utc)

  print("Prefetching live data from OpenF1…")
  live_feed = LiveDataFeed(session_key, drivers_info, session_start)
  live_feed.prefetch()

  # Retry briefly if no positions arrived yet (session may have just started)
  retries = 0
  while live_feed.frame_count() == 0 and retries < 5:
    print(f"  Waiting for position data… ({retries + 1}/5)")
    _time.sleep(2)
    live_feed.prefetch()
    retries += 1

  if live_feed.frame_count() == 0:
    print("Warning: No position data received — the session may not have started yet.")
    print("The viewer will open and wait for data.")

  # Start background polling
  live_feed.start()

  # ---- Session info banner --------------------------------------------
  circuit_length = None
  if "Distance" in example_lap.columns:
    circuit_length = float(example_lap["Distance"].max())

  session_display_info = {
    "event_name":      location,
    "circuit_name":    location,
    "country":         session_info.get("country_name", ""),
    "year":            year,
    "round":           round_number,
    "date":            "LIVE",
    "total_laps":      None,
    "circuit_length_m": circuit_length,
  }

  # ---- Launch insights menu and visualiser ----------------------------
  launch_insights_menu()

  title = f"[LIVE] {location} — {session_name}"
  print(f"Launching live viewer: {title}")

  run_live_arcade_replay(
    live_feed=live_feed,
    example_lap=example_lap,
    drivers=drivers,
    driver_colors=driver_colors,
    title=title,
    circuit_rotation=circuit_rotation,
    session_info=session_display_info,
    session=fastf1_session,
    ready_file=ready_file,
  )


if __name__ == "__main__":

  if "--verbose" not in sys.argv:# fastf1 logging is disabled by default
    logging.getLogger("fastf1").setLevel(logging.CRITICAL)

  if "--cli" in sys.argv:
    # Run the CLI
    cli_load()
    sys.exit(0)

  if "--live" in sys.argv:
    ready_file = None
    if "--ready-file" in sys.argv:
      idx = sys.argv.index("--ready-file") + 1
      if idx < len(sys.argv):
        ready_file = sys.argv[idx]
    live_main(ready_file=ready_file)
    sys.exit(0)

  if "--year" in sys.argv:
    year_index = sys.argv.index("--year") + 1
    year = int(sys.argv[year_index])
  else:
    year = get_season()  # Default year

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