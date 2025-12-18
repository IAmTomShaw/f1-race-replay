from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.arcade_replay import run_arcade_replay

from src.interfaces.qualifying import run_qualifying_replay
from datetime import date
import argparse
import sys

def main(year=None, round_number=None, playback_speed=1, session_type='R'):
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

    example_lap = session.laps.pick_fastest().get_telemetry()

    drivers = session.drivers

    # Get circuit rotation

    circuit_rotation = get_circuit_rotation(session)

    # Run the arcade replay

    # Check for optional chart flag
    chart = "--chart" in sys.argv

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
  
  # Grab the current year as a default for --year option (so we don't have to pass it in every time)
  current_year = date.today().year
  
  # Set up the argument parser
  parser = argparse.ArgumentParser(description='A Python application for visualizing Formula 1 race telemetry and replaying race events with interactive controls and a graphical interface.', 
                                   epilog='Follow the project at: https://github.com/IAmTomShaw/f1-race-replay')

  parser.add_argument('-y', '--year', type=int, default=current_year,
                      help=f"Specify race year (default - {current_year})")
  parser.add_argument('-r', '--round', type=int, default=12,
                      help='Specify race round (default - 12)')
  parser.add_argument('--version', action='version', version="%(prog)s 0.1.0")
  
  sessions = parser.add_argument_group('Sessions other than the main race')
  sessions.add_argument('-s', '--sprint', dest='session_type', action='store_const', const='S', default='R',
                        help='Look at the sprint race')
  sessions.add_argument('-q', '--quali', dest='session_type', action='store_const', const='Q', default='R',
                        help='Look at qualifying')
  sessions.add_argument('-sq', '--sprint-quali', dest='session_type', action='store_const', const='SQ', default='R',
                        help='Look at sprint race quialifying')
  
  lists=parser.add_argument_group('List available data')
  lists.add_argument('-lr', '--list-rounds', action='store_true', default=False,
                     help='List rounds for a given race year')
  lists.add_argument('-ls', '--list-sprints', action='store_true', default=False,
                     help='List sprint races for a given year')

  args=parser.parse_args()

#  print(args)

  if args.list_rounds:
    list_rounds(args.year)
  elif args.list_sprints:
    list_sprints(args.year)
  else:
    playback_speed = 1
    
    main(args.year, args.round, playback_speed, session_type=args.session_type)
