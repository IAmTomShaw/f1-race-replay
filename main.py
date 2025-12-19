from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.arcade_replay import run_arcade_replay
from src.interfaces.qualifying import run_qualifying_replay
import argparse
import sys

def main(year=None, round_number=None, playback_speed=1, session_type='R', chart=False):
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
        playback_speed=1.0,
        driver_colors=race_telemetry['driver_colors'],
        title=f"{session.event['EventName']} - {'Sprint' if session_type == 'S' else 'Race'}",
        total_laps=race_telemetry['total_laps'],
        circuit_rotation=circuit_rotation,
        chart=chart,
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 Race Replay")
    parser.add_argument("--year", type=int, default=2025, help="Year of the race")
    parser.add_argument("--round", type=int, default=12, help="Round number of the race")
    parser.add_argument("--list-rounds", action="store_true", help="List all rounds for a given year")
    parser.add_argument("--list-sprints", action="store_true", help="List all sprints for a given year")
    parser.add_argument("--sprint-qualifying", action="store_true", help="Select sprint qualifying session")
    parser.add_argument("--sprint", action="store_true", help="Select sprint session")
    parser.add_argument("--qualifying", action="store_true", help="Select qualifying session")
    parser.add_argument("--chart", action="store_true", help="Show chart")

    args = parser.parse_args()

    if args.list_rounds:
        list_rounds(args.year)
    elif args.list_sprints:
        list_sprints(args.year)
    else:
        session_type = 'R'
        if args.sprint_qualifying:
            session_type = 'SQ'
        elif args.sprint:
            session_type = 'S'
        elif args.qualifying:
            session_type = 'Q'
        
        main(args.year, args.round, 1, session_type, args.chart)