import argparse
import sys

from .arcade_replay import run_arcade_replay
from .f1_data import (
    enable_cache,
    get_circuit_rotation,
    get_quali_telemetry,
    get_race_telemetry,
    list_rounds,
    list_sprints,
    load_session,
)
from .interfaces.qualifying import run_qualifying_replay


def run(
    year: int,
    round_number: int,
    playback_speed: float = 1.0,
    session_type: str = "R",
    refresh_data: bool = False,
    chart: bool = False,
    max_chunksize: int = sys.maxsize,
):
    print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
    session = load_session(year, round_number, session_type)
    if session is None:
        print(f"No session found for year {year}, round {round_number} and session {session_type}")
        return

    print(f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']} - {session_type}")

    # Enable cache for fastf1
    enable_cache()

    if session_type in ("Q", "SQ"):
        # Get the drivers who participated and their lap times
        qualifying_session_data = get_quali_telemetry(
            session, session_type=session_type, refresh_data=refresh_data, max_chunksize=max_chunksize
        )

        # Run the arcade screen showing qualifying results
        title = (
            f"{session.event['EventName']} - {'Sprint Qualifying' if session_type == 'SQ' else 'Qualifying Results'}"
        )
        run_qualifying_replay(
            session=session,
            data=qualifying_session_data,
            title=title,
        )
    else:
        # Get the drivers who participated in the race
        race_telemetry = get_race_telemetry(
            session, session_type=session_type, refresh_data=refresh_data, max_chunksize=max_chunksize
        )

        # Get example lap for track layout
        example_lap = None

        try:
            print("Attempting to load qualifying session for track layout...")
            quali_session = load_session(year, round_number, "Q")
            if quali_session is not None and len(quali_session.laps) > 0:
                fastest_quali = quali_session.laps.pick_fastest()
                if fastest_quali is not None:
                    quali_telemetry = fastest_quali.get_telemetry()
                    if "DRS" in quali_telemetry.columns:
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
            frames=race_telemetry["frames"],
            track_statuses=race_telemetry["track_statuses"],
            example_lap=example_lap,
            drivers=drivers,
            playback_speed=playback_speed,
            driver_colors=race_telemetry["driver_colors"],
            title=f"{session.event['EventName']} - {'Sprint' if session_type == 'S' else 'Race'}",
            total_laps=race_telemetry["total_laps"],
            circuit_rotation=circuit_rotation,
            chart=chart,
        )


def main():
    # Get the year and round number from user input
    parser = argparse.ArgumentParser(prog="f1-race-replay")
    parser.add_argument("-y", "--year", type=int, default=2025, help="Set the sprint races year (default=%(default)s)")
    parser.add_argument("-r", "--round", type=int, default=12, help="Set the sprint race round (default=%(default)s)")
    parser.add_argument("-c", "--chart", action="store_true", help="Set the chart flag")
    parser.add_argument("--refresh-data", action="store_true", help="Reload the data from server.")
    parser.add_argument(
        "--max-chunksize", type=int, default=20, help="Maximum concurrent data to process (default=%(default)s)."
    )

    session_type_group = parser.add_argument_group(title="Session type")
    g1 = session_type_group.add_mutually_exclusive_group()
    g1.add_argument("--sprint-qualifying", action="store_true")
    g1.add_argument("--sprint", action="store_true")
    g1.add_argument("--qualifying", action="store_true")

    listing_group = parser.add_argument_group(title="Listings")
    g2 = listing_group.add_mutually_exclusive_group()
    g2.add_argument("--list-rounds", action="store_true", help="List the available rounds for selected year.")
    g2.add_argument("--list-sprints", action="store_true", help="List the available sprints for the selected year.")

    args = parser.parse_args()

    year = args.year
    round = args.round
    chart = args.chart
    refresh_data = args.refresh_data
    max_chunksize = args.max_chunksize

    if args.list_rounds:
        list_rounds(year)
        parser.exit(0)

    if args.list_sprints:
        list_sprints(year)
        parser.exit(0)

    playback_speed = 1.0

    # Session type selection
    session_type = "SQ" if args.sprint_qualifying else ("S" if args.sprint else ("Q" if args.qualifying else "R"))

    run(
        year,
        round,
        playback_speed,
        session_type=session_type,
        refresh_data=refresh_data,
        chart=chart,
        max_chunksize=max_chunksize,
    )


if __name__ == "__main__":
    main()
