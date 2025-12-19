from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.arcade_replay import run_arcade_replay

from src.interfaces.qualifying import run_qualifying_replay
import argparse

def main(year=None, round_number=None, playback_speed=1, session_type='R', chart=False, refresh_data=False):
  print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
  session = load_session(year, round_number, session_type)

  print(f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']} - {session_type}")

  # Enable cache for fastf1
  enable_cache()

  if session_type == 'Q' or session_type == 'SQ':

    # Get the drivers who participated and their lap times

    qualifying_session_data = get_quali_telemetry(session, session_type=session_type, refresh_data=refresh_data)

    # Run the arcade screen showing qualifying results

    title = f"{session.event['EventName']} - {'Sprint Qualifying' if session_type == 'SQ' else 'Qualifying Results'}"
    
    run_qualifying_replay(
      session=session,
      data=qualifying_session_data,
      title=title,
    )

  else:

    # Get the drivers who participated in the race

    race_telemetry = get_race_telemetry(session, session_type=session_type, refresh_data=refresh_data)

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
        chart=chart,
    )

if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description="F1 Arcade Replay Tool - Replay races, sprints, and qualifying sessions",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  )

  # Get the year and round number from user input
  parser.add_argument("--year", type=int, default=2025, help="F1 season year")
  parser.add_argument("--round", type=int, default=12, help="Race round number")  

  session_group = parser.add_mutually_exclusive_group()
  session_group.add_argument("--qualifying", action="store_true", help="Run qualifying replay")
  session_group.add_argument("--sprint-qualifying", action="store_true", help="Run sprint qualifying replay")
  session_group.add_argument("--sprint", action="store_true", help="Run sprint race replay")

  parser.add_argument("--list-rounds", action="store_true", help="List all rounds for a season")
  parser.add_argument("--list-sprints", action="store_true", help="List sprint rounds for a season")
  parser.add_argument("--chart", action="store_true", help="Show telemetry charts during replay")
  parser.add_argument("--refresh-data", action="store_true", help="Refresh data from source instead of using cached data")

  args = parser.parse_args()
  
  if args.list_rounds:
    list_rounds(args.year)
    exit(0)
    
  if args.list_sprints:
    list_sprints(args.year)
    exit(0)
    
  if args.qualifying:
    session_type = 'Q'
  elif args.sprint_qualifying:
    session_type = 'SQ'
  elif args.sprint:
    session_type = 'S'
  else:
    session_type = 'R'
  
  playback_speed = 1
  
  year = args.year
  round_number = args.round
  chart = args.chart
  refresh_data = args.refresh_data
  main(year, round_number, playback_speed, session_type=session_type, chart=chart, refresh_data=refresh_data)