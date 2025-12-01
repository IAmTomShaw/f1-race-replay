from src.f1_data import get_race_telemetry, load_race_session, enable_cache, get_circuit_rotation
from src.arcade_replay import run_arcade_replay
import sys

def main(year=None, round_number=None, playback_speed=1, session_type='R'):

  session = load_race_session(year, round_number, session_type)
  print(f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']}")

  # Enable cache for fastf1
  enable_cache()

  # Get the drivers who participated in the race

  race_telemetry = get_race_telemetry(session, session_type=session_type)

  # Get example lap for track layout

  example_lap = session.laps.pick_fastest().get_telemetry()

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
    circuit_rotation=circuit_rotation,
  )

if __name__ == "__main__":

  # Get the year and round number from user input

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

  playback_speed = 1

# Session type selection
  session_type = 'S' if "--sprint" in sys.argv else 'R'
  
  main(year, round_number, playback_speed, session_type=session_type)