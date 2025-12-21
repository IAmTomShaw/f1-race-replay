from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.arcade_replay import run_arcade_replay

from src.interfaces.qualifying import run_qualifying_replay
import sys
import arcade

def main(year=None, round_number=None, playback_speed=1, session_type='R', refresh_data=False, enable_chart=False):
    print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
    session = load_session(year, round_number, session_type)
    if session is None:
        print("Replay not started due to invalid session selection.")
        return
    
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
            chart=enable_chart,
        )


def start_replay_from_menu(year, round_number, session_type, refresh_data, enable_chart):
    """Callback function called from menu to start the replay"""
    print("\n" + "="*50)
    print(f"Starting replay with parameters:")
    print(f"  Year: {year}")
    print(f"  Round: {round_number}")
    print(f"  Session: {session_type}")
    print(f"  Refresh Data: {refresh_data}")
    print(f"  Enable Chart: {enable_chart}")
    print("="*50 + "\n")
    
    # Store parameters for later use
    global pending_replay_params
    pending_replay_params = {
        'year': year,
        'round_number': round_number,
        'session_type': session_type,
        'refresh_data': refresh_data,
        'enable_chart': enable_chart
    }
    
    # Close the menu window - this will trigger the replay to start
    window = arcade.get_window()
    window.close()


if __name__ == "__main__":
    
    # Check if GUI mode is requested (default) or CLI mode
    use_gui = "--no-gui" not in sys.argv
    
    # Global variable to store replay parameters from menu
    pending_replay_params = None
    
    if use_gui:
        # Use GUI menu system
        print("Starting F1 Race Replay Menu...")
        print("Use --no-gui flag to use command-line interface instead.\n")
        
        from src.interfaces.menu import show_menu
        
        # Create arcade window
        window = arcade.Window(1000, 700, "F1 Race Replay - Menu")
        
        # Show menu and pass callback
        show_menu(start_replay_from_menu)
        
        # Run arcade (this blocks until window closes)
        arcade.run()
        
        # After menu closes, check if we have replay parameters
        if pending_replay_params:
            print("Menu closed, starting replay...\n")
            
            # Start the replay with selected parameters
            main(
                year=pending_replay_params['year'],
                round_number=pending_replay_params['round_number'],
                playback_speed=1,
                session_type=pending_replay_params['session_type'],
                refresh_data=pending_replay_params['refresh_data'],
                enable_chart=pending_replay_params['enable_chart']
            )
        else:
            print("Menu closed without starting replay.")
        
    else:
        # Use original CLI argument parsing
        print("Using command-line interface mode.\n")
        
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

        if "--list-rounds" in sys.argv:
            list_rounds(year)
        elif "--list-sprints" in sys.argv:
            list_sprints(year)
        else:
            playback_speed = 1

            # Session type selection
            session_type = 'SQ' if "--sprint-qualifying" in sys.argv else ('S' if "--sprint" in sys.argv else ('Q' if "--qualifying" in sys.argv else 'R'))
            
            # Check for optional flags
            refresh_data = "--refresh-data" in sys.argv
            enable_chart = "--chart" in sys.argv
            
            main(year, round_number, playback_speed, session_type, refresh_data, enable_chart)
