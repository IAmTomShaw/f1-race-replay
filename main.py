import argparse
import sys

from src.cli.race_selection import cli_load
from src.f1_data import (
    enable_cache,
    get_circuit_rotation,
    get_quali_telemetry,
    get_race_telemetry,
    list_rounds,
    list_sprints,
    load_session,
)
from src.gui.race_selection import RaceSelectionWindow
from src.interfaces.qualifying import run_qualifying_replay
from src.lib.season import get_season
import logging
from src.run_session import launch_insights_menu, run_arcade_replay

def main(
    year=None,
    round_number=None,
    playback_speed=1,
    session_type="R",
    visible_hud=True,
    ready_file=None,
    show_insights_menu=True,
    show_telemetry_viewer=True,
):
    print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
    session = load_session(year, round_number, session_type)

    print(f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']} - {session_type}")

    # Enable cache for fastf1
    enable_cache()

    if session_type == "Q" or session_type == "SQ":

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

        # Prepare session info for display banner
        session_info = {
            "event_name": session.event.get("EventName", ""),
            "circuit_name": session.event.get("Location", ""),  # Circuit location/name
            "country": session.event.get("Country", ""),
            "year": year,
            "round": round_number,
            "date": session.event.get("EventDate", "").strftime("%B %d, %Y") if session.event.get("EventDate") else "",
            "total_laps": race_telemetry["total_laps"],
            "circuit_length_m": float(example_lap["Distance"].max())
            if example_lap is not None and "Distance" in example_lap
            else None,
        }

        if show_insights_menu:
            launch_insights_menu()
            print("Launching insights menu...")

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
            visible_hud=visible_hud,
            ready_file=ready_file,
            session_info=session_info,
            session=session,
            # Permanently enabled so telemetry insights always have data if opened.
            enable_telemetry=True,
        )


def build_parser():
    parser = argparse.ArgumentParser(
        description="F1 Race Replay launcher (GUI, CLI, or direct viewer mode)."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose FastF1 logging output.",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run the terminal race selection menu and exit.",
    )
    parser.add_argument(
        "--viewer",
        action="store_true",
        help="Run the replay viewer directly using selected session options.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=get_season(),
        help="Season year to load (default: current season).",
    )
    parser.add_argument(
        "--round",
        dest="round_number",
        type=int,
        default=12,
        help="Round number in the selected season (default: 12).",
    )
    parser.add_argument(
        "--playback-speed",
        type=float,
        choices=[0.5, 1.0, 2.0, 4.0],
        default=1.0,
        help="Initial playback speed for viewer mode.",
    )
    parser.add_argument(
        "--list-rounds",
        action="store_true",
        help="Print available rounds for --year and exit.",
    )
    parser.add_argument(
        "--list-sprints",
        action="store_true",
        help="Print sprint rounds for --year and exit.",
    )
    parser.add_argument(
        "--no-hud",
        action="store_true",
        help="Hide HUD in viewer mode.",
    )
    parser.add_argument(
        "--no-insights-menu",
        action="store_true",
        help="Do not auto-open the Insights Menu when viewer starts.",
    )
    parser.add_argument(
        "--qualifying",
        action="store_true",
        help="Load qualifying replay session.",
    )
    parser.add_argument(
        "--sprint",
        action="store_true",
        help="Load sprint session. With --qualifying, this becomes Sprint Qualifying.",
    )
    parser.add_argument(
        "--sprint-qualifying",
        action="store_true",
        help="Shortcut for loading Sprint Qualifying session.",
    )
    parser.add_argument(
        "--ready-file",
        default=None,
        help="Path to a ready-signal file used by GUI-spawned viewer processes.",
    )
    return parser


def resolve_session_type(args):
    if args.sprint_qualifying or (args.qualifying and args.sprint):
        return "SQ"
    if args.qualifying:
        return "Q"
    if args.sprint:
        return "S"
    return "R"


def run_from_args(args):
    if args.cli:
        cli_load()
        return 0

    if args.list_rounds:
        list_rounds(args.year)
        return 0

    if args.list_sprints:
        list_sprints(args.year)
        return 0

    if args.viewer:
        main(
            args.year,
            args.round_number,
            args.playback_speed,
            session_type=resolve_session_type(args),
            visible_hud=not args.no_hud,
            ready_file=args.ready_file,
            show_insights_menu=not args.no_insights_menu,
        )
        return 0

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    win = RaceSelectionWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    parser = build_parser()
    parsed_args = parser.parse_args()

    # Keep FastF1 logs quiet by default.
    if not parsed_args.verbose:
        logging.getLogger("fastf1").setLevel(logging.CRITICAL)

    sys.exit(run_from_args(parsed_args))
