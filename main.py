"""CLI and GUI entrypoint for F1 Race Replay."""

import argparse
import logging
import sys


def main(
    year=None,
    round_number=None,
    playback_speed=1.0,
    session_type="R",
    visible_hud=True,
    ready_file=None,
    show_telemetry_viewer=True,
):
    from src.f1_data import (
        enable_cache,
        get_circuit_rotation,
        get_quali_telemetry,
        get_race_telemetry,
        load_session,
    )
    from src.interfaces.qualifying import run_qualifying_replay
    from src.run_session import launch_insights_menu, run_arcade_replay

    print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
    session = load_session(year, round_number, session_type)

    print(
        f"Loaded session: {session.event['EventName']} - "
        f"{session.event['RoundNumber']} - {session_type}"
    )

    # Enable cache for fastf1
    enable_cache()

    if session_type in ("Q", "SQ"):
        qualifying_session_data = get_quali_telemetry(
            session, session_type=session_type
        )
        title = (
            f"{session.event['EventName']} - "
            f"{'Sprint Qualifying' if session_type == 'SQ' else 'Qualifying Results'}"
        )

        run_qualifying_replay(
            session=session,
            data=qualifying_session_data,
            title=title,
            ready_file=ready_file,
        )
        return

    race_telemetry = get_race_telemetry(session, session_type=session_type)

    # Get example lap for track layout
    # Qualifying lap preferred for DRS zones (fallback to fastest race lap)
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
                    print(
                        f"Using qualifying lap from driver "
                        f"{fastest_quali['Driver']} for DRS Zones"
                    )
    except Exception as exc:  # pragma: no cover - upstream/IO variability
        print(f"Could not load qualifying session: {exc}")

    # fallback: use fastest race lap
    if example_lap is None:
        fastest_lap = session.laps.pick_fastest()
        if fastest_lap is not None:
            example_lap = fastest_lap.get_telemetry()
            print("Using fastest race lap (DRS detection may use speed-based fallback)")
        else:
            print("Error: No valid laps found in session")
            return

    drivers = session.drivers
    circuit_rotation = get_circuit_rotation(session)

    # Prepare session info for display banner
    session_info = {
        "event_name": session.event.get("EventName", ""),
        "circuit_name": session.event.get("Location", ""),
        "country": session.event.get("Country", ""),
        "year": year,
        "round": round_number,
        "date": (
            session.event.get("EventDate", "").strftime("%B %d, %Y")
            if session.event.get("EventDate")
            else ""
        ),
        "total_laps": race_telemetry["total_laps"],
        "circuit_length_m": (
            float(example_lap["Distance"].max())
            if example_lap is not None and "Distance" in example_lap
            else None
        ),
    }

    # Launch insights menu (always shown with replay)
    launch_insights_menu()
    print("Launching insights menu...")

    session_titles = {
        "R": "Race",
        "S": "Sprint",
        "FP1": "Practice 1",
        "FP2": "Practice 2",
        "FP3": "Practice 3",
    }

    run_arcade_replay(
        frames=race_telemetry["frames"],
        track_statuses=race_telemetry["track_statuses"],
        example_lap=example_lap,
        drivers=drivers,
        playback_speed=playback_speed,
        driver_colors=race_telemetry["driver_colors"],
        title=f"{session.event['EventName']} - {session_titles.get(session_type, 'Race')}",
        total_laps=race_telemetry["total_laps"],
        circuit_rotation=circuit_rotation,
        visible_hud=visible_hud,
        ready_file=ready_file,
        session_info=session_info,
        session=session,
        enable_telemetry=True,
        race_control_messages=race_telemetry.get("race_control_messages", []),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="F1 Race Replay")
    parser.add_argument("--cli", action="store_true", help="Run interactive CLI session selector")
    parser.add_argument("--viewer", action="store_true", help="Run viewer directly from CLI args")
    parser.add_argument("--year", type=int, help="Season year (for example 2025)")
    parser.add_argument("--round", dest="round_number", type=int, help="Round number for selected year")
    parser.add_argument("--list-rounds", action="store_true", help="List rounds for selected year")
    parser.add_argument("--list-sprints", action="store_true", help="List sprint rounds for selected year")
    parser.add_argument("--qualifying", action="store_true", help="Run qualifying replay")
    parser.add_argument("--sprint", action="store_true", help="Run sprint replay")
    parser.add_argument("--sprint-qualifying", action="store_true", help="Run sprint qualifying replay")
    parser.add_argument(
        "--practice",
        type=int,
        choices=[1, 2, 3],
        help="Run practice replay for FP1/FP2/FP3",
    )
    parser.add_argument("--fp1", action="store_true", help="Alias for --practice 1")
    parser.add_argument("--fp2", action="store_true", help="Alias for --practice 2")
    parser.add_argument("--fp3", action="store_true", help="Alias for --practice 3")
    parser.add_argument("--no-hud", action="store_true", help="Disable HUD in race/sprint viewer")
    parser.add_argument("--ready-file", help="Signal file path for GUI child process readiness")
    parser.add_argument(
        "--playback-speed",
        type=float,
        default=1.0,
        help="Initial replay speed multiplier (must be > 0)",
    )
    # Kept for compatibility: f1_data currently checks this in sys.argv.
    parser.add_argument(
        "--refresh-data",
        action="store_true",
        help="Force recomputing telemetry cache for selected session",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable FastF1 logging (default is silenced)",
    )
    return parser


def _resolve_session_type(args: argparse.Namespace) -> str:
    if args.practice:
        return f"FP{args.practice}"
    if args.fp1:
        return "FP1"
    if args.fp2:
        return "FP2"
    if args.fp3:
        return "FP3"
    if args.sprint_qualifying or (args.sprint and args.qualifying):
        return "SQ"
    if args.sprint:
        return "S"
    if args.qualifying:
        return "Q"
    return "R"


def _run_from_args(args: argparse.Namespace) -> int:
    from src.lib.season import get_season

    if not args.verbose:
        logging.getLogger("fastf1").setLevel(logging.CRITICAL)

    if args.playback_speed <= 0:
        raise ValueError("--playback-speed must be greater than 0.")

    if args.practice and (args.sprint or args.qualifying or args.sprint_qualifying):
        raise ValueError(
            "--practice cannot be combined with sprint/qualifying flags."
        )

    if args.cli:
        from src.cli.race_selection import cli_load

        cli_load()
        return 0

    year = args.year if args.year is not None else get_season()
    round_number = args.round_number if args.round_number is not None else 12

    if args.list_rounds:
        from src.f1_data import list_rounds

        list_rounds(year)
        return 0

    if args.list_sprints:
        from src.f1_data import list_sprints

        list_sprints(year)
        return 0

    if args.viewer:
        session_type = _resolve_session_type(args)
        main(
            year=year,
            round_number=round_number,
            playback_speed=args.playback_speed,
            session_type=session_type,
            visible_hud=not args.no_hud,
            ready_file=args.ready_file,
        )
        return 0

    # Lazy GUI imports so non-GUI commands (for example --help/list) work
    # even when desktop dependencies are not installed in the current env.
    from PySide6.QtWidgets import QApplication
    from src.gui.race_selection import RaceSelectionWindow

    app = QApplication(sys.argv)
    win = RaceSelectionWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    parser = _build_parser()
    parsed_args = parser.parse_args()
    try:
        sys.exit(_run_from_args(parsed_args))
    except ValueError as exc:
        parser.error(str(exc))
