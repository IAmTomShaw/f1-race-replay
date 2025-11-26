from src.f1_data import get_race_telemetry, get_driver_colors, load_race_session
from src.arcade_replay import run_arcade_replay
import sys

from src.lib.utils.arg_parser import parse_args


def main(year=None, round_number=None, playback_speed=1):

  session = load_race_session(year, round_number)
  print(f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']}")

  # Get the drivers who participated in the race

  race_telemetry = get_race_telemetry(session)

  # Get example lap for track layout

  example_lap = session.laps.pick_fastest().get_telemetry()

  drivers = session.drivers

  run_arcade_replay(
    frames=race_telemetry['frames'],
    track_statuses=race_telemetry['track_statuses'],
    example_lap=example_lap,
    drivers=drivers,
    playback_speed=playback_speed,
    driver_colors=race_telemetry['driver_colors'],
    title=f"{session.event['EventName']} - Race"
  )


if __name__ == "__main__":
  args = parse_args()

  main(
    year=args.year,
    round_number=args.round,
    playback_speed=args.speed
  )