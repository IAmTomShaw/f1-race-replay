import sys
import logging
import os

# Enable DPI awareness on Windows for crisp rendering on high-DPI displays
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

from src.lib.season import get_season
from src.lib.logging_setup import configure_logging
# PHASE J: argparse-based CLI parser. The legacy ``main.py``
# did manual ``if "--flag" in sys.argv`` chains; the new
# ``parse_args`` is the single source of truth. Public
# behaviour (no-arg = GUI, --cli = CLI menu, --viewer =
# viewer, --list-rounds/--list-sprints = list, --diagnostics =
# print report and exit) is preserved.
from src.cli.args import parse_args, session_type as _resolve_session_type


def main(year=None, round_number=None, playback_speed=1, session_type='R', visible_hud=True, ready_file=None, show_telemetry_viewer=True):
    import fastf1
    from src.f1_data import (
        get_race_telemetry,
        enable_cache,
        get_circuit_rotation,
        load_session,
        get_quali_telemetry,
        has_cached_telemetry_payload,
        extract_example_lap_telemetry,
        enrich_example_lap_drs_from_frames,
    )
    from src.interfaces.qualifying import run_qualifying_replay
    from src.run_session import run_arcade_replay, launch_insights_menu

    # Enable cache for fastf1 BEFORE loading session so downloads are cached
    enable_cache()

    print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
    cached_payload = None
    try:
        probe_sess = fastf1.get_session(year, round_number, session_type)
        cached_payload = has_cached_telemetry_payload(probe_sess, session_type=session_type)
    except Exception:
        cached_payload = None

    # When precomputed telemetry + example_lap already exist in cache, skip
    # loading raw 25Hz telemetry/weather/messages for all 20 drivers (~10x faster startup).
    can_skip_raw_tel = (
        cached_payload is not None
        and (
            (session_type in ('Q', 'SQ') and bool(cached_payload.get('telemetry')))
            or (session_type not in ('Q', 'SQ') and cached_payload.get('example_lap') is not None)
        )
    )
    if can_skip_raw_tel:
        session = load_session(
            year, round_number, session_type,
            load_telemetry=False, load_weather=False, load_messages=False,
        )
    else:
        session = load_session(year, round_number, session_type)

    print(f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']} - {session_type}")

    if session_type == 'Q' or session_type == 'SQ':

        # Get the drivers who participated and their lap times

        qualifying_session_data = cached_payload if cached_payload is not None else get_quali_telemetry(session, session_type=session_type)

        # Run the arcade screen showing qualifying results

        title = f"{session.event['EventName']} - {'Sprint Qualifying' if session_type == 'SQ' else 'Qualifying Results'}"
        try:
            circuit_rotation = get_circuit_rotation(session)
        except Exception:
            circuit_rotation = 0.0

        run_qualifying_replay(
          session=session,
          data=qualifying_session_data,
          title=title,
          ready_file=ready_file,
          circuit_rotation=circuit_rotation,
        )

    else:

        # Get the drivers who participated in the race

        race_telemetry = cached_payload if cached_payload is not None else get_race_telemetry(session, session_type=session_type)

        # Prefer cached example_lap (enriched with all race DRS activations) or extract fresh
        example_lap = race_telemetry.get("example_lap")
        if example_lap is None:
            example_lap = extract_example_lap_telemetry(
                session, year=year, round_number=round_number, frames=race_telemetry.get("frames")
            )
        else:
            example_lap = enrich_example_lap_drs_from_frames(
                example_lap, race_telemetry.get("frames")
            )
        if example_lap is None:
            print("Error: No valid laps found in session")
            return

        drivers = race_telemetry.get("drivers") or session.drivers

        # Get circuit rotation
        circuit_rotation = race_telemetry.get("circuit_rotation")
        if circuit_rotation is None:
            try:
                circuit_rotation = get_circuit_rotation(session)
            except Exception:
                circuit_rotation = 0.0

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
          enable_telemetry=True,
          race_control_messages=race_telemetry.get('race_control_messages', [])
        )

if __name__ == "__main__":

    # PHASE J: delegate argv parsing to the argparse-based
    # ``parse_args``. The dispatch below preserves the legacy
    # behaviour exactly.
    args = parse_args()

    configure_logging(level="DEBUG" if args.verbose else "WARNING")
    if not args.verbose:
        # fastf1 logging is disabled by default
        logging.getLogger("fastf1").setLevel(logging.CRITICAL)

        # Early-exit branches: --diagnostics, --cli, --list-rounds,
        # --list-sprints.
    if args.diagnostics:
        from src.tools.diagnostics import collect_diagnostics
        print(collect_diagnostics())
        sys.exit(0)
    if args.cli:
        from src.cli.race_selection import cli_load
        cli_load()
        sys.exit(0)
    if args.list_rounds:
        from src.f1_data import list_rounds
        yr = args.year if args.year is not None else get_season()
        list_rounds(yr)
        sys.exit(0)
    if args.list_sprints:
        from src.f1_data import list_sprints
        yr = args.year if args.year is not None else get_season()
        list_sprints(yr)
        sys.exit(0)

        # If the user asked for the viewer explicitly, run the legacy
        # viewer path. If they passed --year without --viewer, fall
        # through to the GUI as before.
    if args.viewer:
        year = args.year if args.year is not None else get_season()
        round_number = args.round if args.round is not None else 12
        visible_hud = not args.no_hud
        main(year, round_number, 1,
              session_type=_resolve_session_type(args),
              visible_hud=visible_hud,
              ready_file=args.ready_file)
        sys.exit(0)

        # Run the GUI

    from PySide6.QtWidgets import QApplication
    from src.gui.race_selection import RaceSelectionWindow

    # Enable high-DPI scaling for sharp text/icons on modern displays
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    app = QApplication(sys.argv)
    win = RaceSelectionWindow()
    win.show()
    sys.exit(app.exec())
