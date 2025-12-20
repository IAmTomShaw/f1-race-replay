import fastf1
import fastf1.plotting
from src.data.cache import enable_cache

def load_session(year, round_number, session_type='R'):
    """
    Load a FastF1 session with telemetry and weather data.
    """
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=True, weather=True)
    return session

def get_driver_colors(session):
    """
    Get a mapping of driver codes to RGB color tuples.
    """
    color_mapping = fastf1.plotting.get_driver_color_mapping(session)
    
    # Convert hex colors to RGB tuples
    rgb_colors = {}
    for driver, hex_color in color_mapping.items():
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        rgb_colors[driver] = rgb
    return rgb_colors

def get_circuit_rotation(session):
    """
    Get the circuit rotation in degrees.
    """
    circuit = session.get_circuit_info()
    return circuit.rotation

def list_rounds(year):
    """Lists all rounds for a given year."""
    enable_cache()
    print(f"F1 Schedule {year}")
    schedule = fastf1.get_event_schedule(year)
    for _, event in schedule.iterrows():
        print(f"{event['RoundNumber']}: {event['EventName']}")

def list_sprints(year):
    """Lists all sprint rounds for a given year."""
    enable_cache()
    print(f"F1 Sprint Races {year}")
    schedule = fastf1.get_event_schedule(year)
    sprint_name = 'sprint_qualifying'
    if year == 2023:
        sprint_name = 'sprint_shootout'
    if year in [2021, 2022]:
        sprint_name = 'sprint'
    sprints = schedule[schedule['EventFormat'] == sprint_name]
    if sprints.empty:
        print(f"No sprint races found for {year}.")
    else:
        for _, event in sprints.iterrows():
            print(f"{event['RoundNumber']}: {event['EventName']}")
