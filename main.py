import sys
import os
import eel
import time
import threading
import json
import numpy as np
import pandas as pd

# Setup Paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

# Import Replay
from src.arcade_replay import run_arcade_replay
from src.backend.ai_engine import AIEngine
# Import Data Loader
from src.f1_data import get_session_data 

# --- FIX START: Point to the 'dist' folder containing the compiled JS ---
web_dir = os.path.join(PROJECT_ROOT, 'web', 'dist')
eel.init(web_dir)
# --- FIX END ---

DATA_CACHE = None
AI_RUNNING = False

def load_data_auto():
    """
    Automatically handles data loading:
    1. Checks if f1_data.py has cached the data.
    2. If not, it runs the download/processing logic.
    3. Returns the formatted data for the UI.
    """
    print("[LOADER] Initializing Data Pipeline...")
    
    # This calls the function in f1_data.py which handles the JSON check and Download
    # It returns a tuple: (frames, track_statuses, example_lap, drivers, title, driver_colors)
    try:
        data_tuple = get_session_data()
        
        if not data_tuple:
            print("[ERROR] Failed to retrieve session data.")
            return None
            
        frames, track_statuses, example_lap, drivers, title, driver_colors = data_tuple
        
        # Calculate total laps from frames if possible
        total_laps = 57
        if frames:
            # Find max lap in the last frame
            last_frame = frames[-1]
            max_lap = 0
            for d in last_frame['drivers'].values():
                if d['lap'] > max_lap: max_lap = d['lap']
            if max_lap > 0: total_laps = int(max_lap)

        return {
            "frames": frames,
            "track_statuses": track_statuses,
            "example_lap": example_lap,
            "drivers": drivers,
            "title": title,
            "driver_colors": driver_colors,
            "total_laps": total_laps
        }
    except Exception as e:
        print(f"[CRITICAL ERROR] Data Pipeline Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- AI MODULE ---
def ai_loop():
    global AI_RUNNING
    try:
        ai_engine = AIEngine()
    except: return

    frame_idx = 0
    driver = "VER"
    while AI_RUNNING:
        cycle = np.sin(frame_idx * 0.1)
        temp = int(100 + (cycle * 15))
        gap = abs(cycle * 2.0)
        
        snapshot = {
            'tyre_compound': 'soft', 'tyre_age': 10, 'tyre_temp': temp,
            'rain': 0, 'track_status': 1, 'gap_to_leader': gap
        }
        result = ai_engine.update_telemetry(driver, snapshot)
        try:
            eel.update_ai_dashboard({
                'driver': driver, 'temp': temp, 'gap': round(gap, 2),
                'strategy': result['strategy'], 'reason': result['tire_reason'],
                'logs': result['logs']
            })()
        except: pass
        frame_idx += 1
        time.sleep(0.2)

@eel.expose
def launch_dsa_module():
    global DATA_CACHE
    if not DATA_CACHE:
        DATA_CACHE = load_data_auto()
    
    if DATA_CACHE:
        print("[LAUNCH] Starting Arcade Replay...")
        run_arcade_replay(
            frames=DATA_CACHE["frames"],
            track_statuses=DATA_CACHE["track_statuses"],
            example_lap=DATA_CACHE["example_lap"],
            drivers=DATA_CACHE["drivers"],
            title=DATA_CACHE["title"],
            driver_colors=DATA_CACHE["driver_colors"],
            total_laps=DATA_CACHE["total_laps"]
        )
        return "SUCCESS"
    else:
        print("Failed to launch: Data missing.")
        return "FAIL"

@eel.expose
def launch_ai_module():
    global AI_RUNNING
    if not AI_RUNNING:
        AI_RUNNING = True
        threading.Thread(target=ai_loop, daemon=True).start()
    return "OK"

if __name__ == '__main__':
    eel.start('index.html', size=(1300, 800))