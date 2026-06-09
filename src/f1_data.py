import os
import fastf1
import fastf1.plotting
import numpy as np
import json
import pandas as pd
from datetime import timedelta, datetime

# --- CONFIGURATION ---
FPS = 25  # Lower FPS slightly to reduce calculation load if needed
DT = 1 / FPS
CACHE_FILE_PATH = "computed_data/BAHRAIN_2024_RACE_CACHE.json"

class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (pd.Timestamp, datetime, np.datetime64)):
            return str(obj)
        if isinstance(obj, (pd.Timedelta, timedelta, np.timedelta64)):
            if hasattr(obj, 'total_seconds'):
                return obj.total_seconds()
            return float(obj) / 1e9
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        return super().default(obj)

def get_tyre_compound_int(compound):
    if compound == 'SOFT': return 0
    if compound == 'MEDIUM': return 1
    if compound == 'HARD': return 2
    return 0

def enable_cache():
    if not os.path.exists('.fastf1-cache'):
        os.makedirs('.fastf1-cache')
    fastf1.Cache.enable_cache('.fastf1-cache')

def load_race_session(year, round_number):
    enable_cache()
    print(f"[DATA] Loading Session {year} Round {round_number}...")
    session = fastf1.get_session(year, round_number, 'R')
    session.load(telemetry=True, laps=True, weather=True) # Ensure weather=True
    return session

def get_driver_colors(session):
    color_mapping = fastf1.plotting.get_driver_color_mapping(session)
    rgb_colors = {}
    for driver, hex_color in color_mapping.items():
        if not hex_color:
            rgb_colors[driver] = (255, 255, 255)
            continue
        hex_color = hex_color.lstrip('#')
        try:
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            rgb_colors[driver] = rgb
        except:
            rgb_colors[driver] = (255, 255, 255)
    return rgb_colors

def get_race_telemetry(session):
    print("[DATA] Processing Telemetry (Throttle, Brake, Weather enabled)...")
    
    drivers = session.drivers
    driver_codes = {num: session.get_driver(num)["Abbreviation"] for num in drivers}
    driver_data = {}

    global_t_min = None
    global_t_max = None
    
    # 1. WEATHER EXTRACTION
    weather_df = session.weather_data
    
    # 2. DRIVER TELEMETRY
    for driver_no in drivers:
        code = driver_codes[driver_no]
        laps_driver = session.laps.pick_drivers(driver_no)
        if laps_driver.empty: continue

        t_all, x_all, y_all = [], [], []
        race_dist_all, rel_dist_all = [], []
        lap_numbers, tyre_compounds = [], []
        speed_all, gear_all, drs_all = [], [], []
        throttle_all, brake_all = [], [] # NEW

        total_dist_so_far = 0.0

        for _, lap in laps_driver.iterlaps():
            lap_tel = lap.get_telemetry()
            if lap_tel.empty: continue

            lap_number = lap.LapNumber
            tyre_comp = get_tyre_compound_int(lap.Compound)

            t_lap = lap_tel["SessionTime"].dt.total_seconds().to_numpy()
            x_lap = lap_tel["X"].to_numpy()
            y_lap = lap_tel["Y"].to_numpy()
            d_lap = lap_tel["Distance"].to_numpy()          
            rd_lap = lap_tel["RelativeDistance"].to_numpy()
            speed_lap = lap_tel["Speed"].to_numpy()
            gear_lap = lap_tel["nGear"].to_numpy()
            drs_lap = lap_tel["DRS"].to_numpy()
            thr_lap = lap_tel["Throttle"].to_numpy() # NEW
            brk_lap = lap_tel["Brake"].to_numpy()    # NEW

            d_lap = d_lap - d_lap.min()
            lap_length = d_lap.max()
            race_d_lap = total_dist_so_far + d_lap
            total_dist_so_far += lap_length

            t_all.append(t_lap)
            x_all.append(x_lap)
            y_all.append(y_lap)
            race_dist_all.append(race_d_lap)
            rel_dist_all.append(rd_lap)
            lap_numbers.append(np.full_like(t_lap, lap_number))
            tyre_compounds.append(np.full_like(t_lap, tyre_comp))
            speed_all.append(speed_lap)
            gear_all.append(gear_lap)
            drs_all.append(drs_lap)
            throttle_all.append(thr_lap) # NEW
            brake_all.append(brk_lap)    # NEW

        if not t_all: continue

        driver_data[code] = {
            "t": np.concatenate(t_all),
            "x": np.concatenate(x_all),
            "y": np.concatenate(y_all),
            "dist": np.concatenate(race_dist_all),
            "rel_dist": np.concatenate(rel_dist_all),                   
            "lap": np.concatenate(lap_numbers),
            "tyre": np.concatenate(tyre_compounds),
            "speed": np.concatenate(speed_all),
            "gear": np.concatenate(gear_all),
            "drs": np.concatenate(drs_all),
            "throttle": np.concatenate(throttle_all), # NEW
            "brake": np.concatenate(brake_all)        # NEW
        }

        t_min = driver_data[code]["t"].min()
        t_max = driver_data[code]["t"].max()
        global_t_min = t_min if global_t_min is None else min(global_t_min, t_min)
        global_t_max = t_max if global_t_max is None else max(global_t_max, t_max)

    # 3. RESAMPLING
    timeline = np.arange(global_t_min, global_t_max, DT)
    resampled_data = {}

    for code, data in driver_data.items():
        resampled_data[code] = {
            "x": np.interp(timeline, data["t"], data["x"]),
            "y": np.interp(timeline, data["t"], data["y"]),
            "dist": np.interp(timeline, data["t"], data["dist"]),
            "rel_dist": np.interp(timeline, data["t"], data["rel_dist"]),
            "lap": np.interp(timeline, data["t"], data["lap"]),
            "tyre": np.interp(timeline, data["t"], data["tyre"]),
            "speed": np.interp(timeline, data["t"], data["speed"]),
            "gear": np.interp(timeline, data["t"], data["gear"]),
            "drs": np.interp(timeline, data["t"], data["drs"]),
            "throttle": np.interp(timeline, data["t"], data["throttle"]), # NEW
            "brake": np.interp(timeline, data["t"], data["brake"]),       # NEW
        }

    # 4. TRACK STATUS
    formatted_track_statuses = []
    if hasattr(session, 'track_status'):
        for status in session.track_status.to_dict('records'):
            seconds = timedelta.total_seconds(status['Time'])
            formatted_track_statuses.append({
                'status': status['Status'], 
                'start_time': seconds, 
                'end_time': None
            })
            if len(formatted_track_statuses) > 1:
                formatted_track_statuses[-2]['end_time'] = seconds

    # 5. WEATHER INTERPOLATION
    weather_interp = {}
    if weather_df is not None and not weather_df.empty:
        w_time = weather_df["Time"].dt.total_seconds().to_numpy()
        for col in ["AirTemp", "TrackTemp", "Humidity", "Rainfall", "WindSpeed", "WindDirection"]:
            if col in weather_df:
                weather_interp[col] = (w_time, weather_df[col].to_numpy())

    # 6. FRAME BUILDING
    frames = []
    for i, t in enumerate(timeline):
        snapshot = []
        for code, d in resampled_data.items():
            snapshot.append({
                "code": code,
                "dist": float(d["dist"][i]),
                "x": float(d["x"][i]),
                "y": float(d["y"][i]),
                "lap": int(round(d["lap"][i])),
                "rel_dist": float(d["rel_dist"][i]),
                "tyre": d["tyre"][i],
                "speed": d["speed"][i],
                "gear": int(d["gear"][i]),
                "drs": int(d["drs"][i]),
                "throttle": float(d["throttle"][i]), # NEW
                "brake": float(d["brake"][i])        # NEW
            })

        if not snapshot: continue
        
        snapshot.sort(key=lambda r: r["dist"], reverse=True)
        leader_lap = snapshot[0]["lap"]

        frame_drivers = {}
        for idx, car in enumerate(snapshot):
            frame_drivers[car["code"]] = {
                "x": car["x"], "y": car["y"], "dist": car["dist"], "lap": car["lap"],
                "rel_dist": car["rel_dist"], "tyre": car["tyre"], "position": idx + 1,
                "speed": car["speed"], "gear": car["gear"], "drs": car["drs"],
                "throttle": car["throttle"], "brake": car["brake"]
            }
        
        # Add Weather to Frame
        frame_weather = {}
        if weather_interp:
            for key, (wt, wv) in weather_interp.items():
                val = np.interp(t, wt, wv)
                if key == "Rainfall": frame_weather["rain_state"] = "WET" if val > 0 else "DRY"
                elif key == "AirTemp": frame_weather["air_temp"] = val
                elif key == "TrackTemp": frame_weather["track_temp"] = val
                elif key == "Humidity": frame_weather["humidity"] = val
                elif key == "WindSpeed": frame_weather["wind_speed"] = val
                elif key == "WindDirection": frame_weather["wind_direction"] = val
        
        frames.append({
            "t": float(t), 
            "lap": leader_lap, 
            "drivers": frame_drivers,
            "weather": frame_weather
        })

    return {
        "frames": frames,
        "driver_colors": get_driver_colors(session),
        "track_statuses": formatted_track_statuses
    }

def load_cached_session_data(session_year=2024, session_round=1):
    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    # TRY LOADING CACHE
    if os.path.exists(CACHE_FILE_PATH):
        print(f"[CACHE] Loading cached data from {CACHE_FILE_PATH}...")
        try:
            with open(CACHE_FILE_PATH, "r") as f:
                cached_data = json.load(f)
            
            example_lap_df = pd.DataFrame(cached_data['example_lap'])
            print("[CACHE] Load successful.")
            return (
                cached_data['frames'],
                cached_data['track_statuses'],
                example_lap_df,
                cached_data['drivers'],
                cached_data['title'],
                cached_data['driver_colors']
            )
        except Exception as e:
            print(f"[CACHE ERROR] Corrupt cache: {e}. Recomputing...")

    # NO CACHE? COMPUTE.
    print("[DATA] Starting FRESH computation...")
    session = load_race_session(session_year, session_round) 
    data_bundle = get_race_telemetry(session)
    
    print("[DATA] Extracting Track Geometry...")
    fastest_lap = session.laps.pick_fastest()
    example_lap_telemetry = fastest_lap.get_telemetry()
    
    drivers_list = list(data_bundle['driver_colors'].keys())
    session_title = f"{session.event['EventName']} {session.session_info} {session.date.year}"
    
    final_data_tuple = (
        data_bundle['frames'],
        data_bundle['track_statuses'],
        example_lap_telemetry,
        drivers_list,
        session_title,
        data_bundle['driver_colors']
    )

    # Save
    cache_to_save = {
        'frames': data_bundle['frames'],
        'track_statuses': data_bundle['track_statuses'],
        'drivers': drivers_list,
        'title': session_title,
        'driver_colors': final_data_tuple[5],
        'example_lap': example_lap_telemetry.to_dict('list') 
    }
    
    with open(CACHE_FILE_PATH, "w") as f:
        json.dump(cache_to_save, f, indent=2, cls=CustomJsonEncoder)
    
    print(f"[CACHE] Data saved successfully to {CACHE_FILE_PATH}")
    return final_data_tuple

def get_session_data():
    return load_cached_session_data(session_year=2024, session_round=1)