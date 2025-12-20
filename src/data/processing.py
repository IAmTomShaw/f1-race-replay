import os
import sys
import pickle
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from multiprocessing import Pool, cpu_count
from datetime import timedelta
from src.data.telemetry import process_driver_telemetry
from src.data.session import get_driver_colors
from src.lib.time import parse_time_string

FPS = 25
DT = 1 / FPS

def get_race_telemetry(session, session_type='R'):
    """
    Get processed race telemetry data, either from cache or by computing it.
    """
    event_name = str(session).replace(' ', '_')
    cache_suffix = 'sprint' if session_type == 'S' else 'race'

    # Check if this data has already been computed
    try:
        if "--refresh-data" not in sys.argv:
            with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "rb") as f:
                frames = pickle.load(f)
                print(f"Loaded precomputed {cache_suffix} telemetry data.")
                print("The replay should begin in a new window shortly!")
                return frames
    except FileNotFoundError:
        pass  # Need to compute from scratch

    drivers = session.drivers
    driver_codes = {
        num: session.get_driver(num)["Abbreviation"]
        for num in drivers
    }

    driver_data = {}
    global_t_min = None
    global_t_max = None
    max_lap_number = 0

    # 1. Get all of the drivers telemetry data using multiprocessing
    print(f"Processing {len(drivers)} drivers in parallel...")
    driver_args = [(driver_no, session, driver_codes[driver_no]) for driver_no in drivers]
    
    num_processes = min(cpu_count(), len(drivers))
    
    with Pool(processes=num_processes) as pool:
        results = pool.map(process_driver_telemetry, driver_args)
    
    # Process results
    for result in results:
        if result is None:
            continue
        
        code = result["code"]
        data = result["data"]
        driver_data[code] = data
        
        t_min = data["t"].min() if len(data["t"]) > 0 else None
        t_max = data["t"].max() if len(data["t"]) > 0 else None
        max_lap = data["lap"].max() if len(data["lap"]) > 0 else 0
        
        max_lap_number = max(max_lap_number, max_lap)
        
        if t_min is not None:
            global_t_min = t_min if global_t_min is None else min(global_t_min, t_min)
        if t_max is not None:
            global_t_max = t_max if global_t_max is None else max(global_t_max, t_max)

    # Ensure we have valid time bounds
    if global_t_min is None or global_t_max is None:
        raise ValueError("No valid telemetry data found for any driver")

    # 2. Create a timeline (start from zero)
    timeline = np.arange(global_t_min, global_t_max, DT) - global_t_min

    # 3. Resample each driver's telemetry onto the common timeline
    resampled_data = {}

    for code, data in driver_data.items():
        t = data["t"] - global_t_min  # Shift

        # ensure sorted by time
        order = np.argsort(t)
        t_sorted = t[order]
        
        # Vectorize all resampling in one operation for speed
        arrays_to_resample = [
            data["x"][order],
            data["y"][order],
            data["dist"][order],
            data["rel_dist"][order],
            data["lap"][order],
            data["tyre"][order],
            data["speed"][order],
            data["gear"][order],
            data["drs"][order],
            data["throttle"][order],
            data["brake"][order],
        ]
        
        resampled = [np.interp(timeline, t_sorted, arr) for arr in arrays_to_resample]
        x_resampled, y_resampled, dist_resampled, rel_dist_resampled, lap_resampled, \
        tyre_resampled, speed_resampled, gear_resampled, drs_resampled, throttle_resampled, brake_resampled = resampled
 
        resampled_data[code] = {
            "t": timeline,
            "x": x_resampled,
            "y": y_resampled,
            "dist": dist_resampled,
            "rel_dist": rel_dist_resampled,
            "lap": lap_resampled,
            "tyre": tyre_resampled,
            "speed": speed_resampled,
            "gear": gear_resampled,
            "drs": drs_resampled,
            "throttle": throttle_resampled,
            "brake": brake_resampled
        }

    # 4. Incorporate track status data
    track_status = session.track_status
    formatted_track_statuses = []

    for status in track_status.to_dict('records'):
        seconds = timedelta.total_seconds(status['Time'])
        start_time = seconds - global_t_min # Shift to match timeline
        end_time = None

        if formatted_track_statuses:
            formatted_track_statuses[-1]['end_time'] = start_time

        formatted_track_statuses.append({
            'status': status['Status'],
            'start_time': start_time,
            'end_time': end_time, 
        })

    # 4.1. Resample weather data
    weather_resampled = _process_weather_data(session, timeline, global_t_min)

    # 5. Build the frames
    frames = []
    num_frames = len(timeline)
    
    driver_codes = list(resampled_data.keys())
    driver_arrays = {code: resampled_data[code] for code in driver_codes}

    for i in range(num_frames):
        t = timeline[i]
        snapshot = []
        for code in driver_codes:
            d = driver_arrays[code]
            snapshot.append({
                "code": code,
                "dist": float(d["dist"][i]),
                "x": float(d["x"][i]),
                "y": float(d["y"][i]),
                "lap": int(round(d["lap"][i])),
                "rel_dist": float(d["rel_dist"][i]),
                "tyre": float(d["tyre"][i]),
                "speed": float(d['speed'][i]),
                "gear": int(d['gear'][i]),
                "drs": int(d['drs'][i]),
                "throttle": float(d['throttle'][i]),
                "brake": float(d['brake'][i]),
            })

        if not snapshot:
            continue

        # Sort by race distance to get POSITIONS
        snapshot.sort(key=lambda r: r["dist"], reverse=True)
        leader_lap = snapshot[0]["lap"]

        frame_data = {}
        for idx, car in enumerate(snapshot):
            code = car["code"]
            position = idx + 1
            frame_data[code] = {
                "x": car["x"],
                "y": car["y"],
                "dist": car["dist"],    
                "lap": car["lap"],
                "rel_dist": round(car["rel_dist"], 4),
                "tyre": car["tyre"],
                "position": position,
                "speed": car['speed'],
                "gear": car['gear'],
                "drs": car['drs'],
                "throttle": car['throttle'],
                "brake": car['brake'],
            }

        weather_snapshot = _get_weather_snapshot(weather_resampled, i)
        
        frame_payload = {
            "t": round(t, 3),
            "lap": leader_lap,
            "drivers": frame_data,
        }
        if weather_snapshot:
            frame_payload["weather"] = weather_snapshot

        frames.append(frame_payload)

    print("completed telemetry extraction...")
    print("Saving to cache file...")
    
    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "wb") as f:
        pickle.dump({
            "frames": frames,
            "driver_colors": get_driver_colors(session),
            "track_statuses": formatted_track_statuses,
            "total_laps": int(max_lap_number),
        }, f, protocol=pickle.HIGHEST_PROTOCOL)

    print("Saved Successfully!")
    return {
        "frames": frames,
        "driver_colors": get_driver_colors(session),
        "track_statuses": formatted_track_statuses,
        "total_laps": int(max_lap_number),
    }

def _process_weather_data(session, timeline, global_t_min):
    weather_df = getattr(session, "weather_data", None)
    if weather_df is not None and not weather_df.empty:
        try:
            weather_times = weather_df["Time"].dt.total_seconds().to_numpy() - global_t_min
            if len(weather_times) > 0:
                order = np.argsort(weather_times)
                weather_times = weather_times[order]

                def _maybe_get(name):
                    return weather_df[name].to_numpy()[order] if name in weather_df else None

                def _resample(series):
                    if series is None:
                        return None
                    return np.interp(timeline, weather_times, series)

                rainfall_data = _maybe_get("Rainfall")
                return {
                    "track_temp": _resample(_maybe_get("TrackTemp")),
                    "air_temp": _resample(_maybe_get("AirTemp")),
                    "humidity": _resample(_maybe_get("Humidity")),
                    "wind_speed": _resample(_maybe_get("WindSpeed")),
                    "wind_direction": _resample(_maybe_get("WindDirection")),
                    "rainfall": _resample(rainfall_data.astype(float)) if rainfall_data is not None else None,
                }
        except Exception as e:
            print(f"Weather data could not be processed: {e}")
    return None

def _get_weather_snapshot(weather_resampled, i):
    if not weather_resampled:
        return {}
    try:
        wt = weather_resampled
        rain_val = wt["rainfall"][i] if wt.get("rainfall") is not None else 0.0
        return {
            "track_temp": float(wt["track_temp"][i]) if wt.get("track_temp") is not None else None,
            "air_temp": float(wt["air_temp"][i]) if wt.get("air_temp") is not None else None,
            "humidity": float(wt["humidity"][i]) if wt.get("humidity") is not None else None,
            "wind_speed": float(wt["wind_speed"][i]) if wt.get("wind_speed") is not None else None,
            "wind_direction": float(wt["wind_direction"][i]) if wt.get("wind_direction") is not None else None,
            "rain_state": "RAINING" if rain_val and rain_val >= 0.5 else "DRY",
        }
    except Exception:
        return {}

def get_qualifying_results(session):
    results = session.results
    qualifying_data = []

    for _, row in results.iterrows():
        driver_code = row["Abbreviation"]
        position = int(row["Position"])
        
        def convert_time_to_seconds(time_val) -> Optional[str]:
            if pd.isna(time_val):
                return None
            return str(time_val.total_seconds())    

        qualifying_data.append({
            "code": driver_code,
            "position": position,
            "color": get_driver_colors(session).get(driver_code, (128,128,128)),
            "Q1": convert_time_to_seconds(row["Q1"]),
            "Q2": convert_time_to_seconds(row["Q2"]),
            "Q3": convert_time_to_seconds(row["Q3"]),
        })
    return qualifying_data

def get_driver_quali_telemetry(session, driver_code: str, quali_segment: str):
    q1, q2, q3 = session.laps.split_qualifying_sessions()
    segments = {"Q1": q1, "Q2": q2, "Q3": q3}

    if quali_segment not in segments:
        raise ValueError("quali_segment must be 'Q1', 'Q2', or 'Q3'")

    segment_laps = segments[quali_segment]
    if segment_laps is None:
        raise ValueError(f"{quali_segment} does not exist for this session.")

    driver_laps = segment_laps.pick_drivers(driver_code)
    if driver_laps.empty:
        raise ValueError(f"No laps found for driver '{driver_code}' in {quali_segment}")

    fastest_lap = driver_laps.pick_fastest()
    if fastest_lap is None:
        raise ValueError(f"No valid laps for driver '{driver_code}' in {quali_segment}")

    telemetry = fastest_lap.get_telemetry()
    if telemetry is None or telemetry.empty or 'Time' not in telemetry or len(telemetry) == 0:
        return {"frames": [], "track_statuses": [], "max_speed": 0.0, "min_speed": 0.0}

    # Build arrays directly from dataframes
    t_arr = telemetry["Time"].dt.total_seconds().to_numpy()
    global_t_min = float(t_arr.min())
    global_t_max = float(t_arr.max())
    
    timeline = np.arange(global_t_min, global_t_max + DT/2, DT) - global_t_min
    t_rel = t_arr - global_t_min

    # Sort & deduplicate
    order = np.argsort(t_rel)
    t_sorted = t_rel[order]
    t_sorted_unique, unique_idx = np.unique(t_sorted, return_index=True)
    idx_map = order[unique_idx]

    # Resample data
    def _interp(arr):
        return np.interp(timeline, t_sorted_unique, arr[idx_map])

    x_resampled = _interp(telemetry["X"].to_numpy())
    y_resampled = _interp(telemetry["Y"].to_numpy())
    dist_resampled = _interp(telemetry["Distance"].to_numpy())
    rel_dist_resampled = _interp(telemetry["RelativeDistance"].to_numpy())
    speed_resampled = np.round(_interp(telemetry["Speed"].to_numpy()), 1)
    throttle_resampled = np.round(_interp(telemetry["Throttle"].to_numpy()), 1)
    brake_resampled = np.round(_interp(telemetry["Brake"].to_numpy()), 1) * 100.0
    drs_resampled = _interp(telemetry["DRS"].to_numpy())
    
    # Gear resampling (nearest)
    idxs = np.searchsorted(t_sorted_unique, timeline, side='right') - 1
    idxs = np.clip(idxs, 0, len(t_sorted_unique) - 1)
    gear_resampled = telemetry["nGear"].to_numpy()[idx_map][idxs].astype(int)

    resampled_data = {
        "t": timeline,
        "x": x_resampled,
        "y": y_resampled,
        "dist": dist_resampled,
        "rel_dist": rel_dist_resampled,
        "speed": speed_resampled,
        "gear": gear_resampled,
        "throttle": throttle_resampled,
        "brake": brake_resampled,
        "drs": drs_resampled,
    }

    # Process track status
    track_status = session.track_status
    formatted_track_statuses: List[Dict[str, Any]] = []
    for status in track_status.to_dict('records'):
        seconds = timedelta.total_seconds(status['Time'])
        start_time = seconds - global_t_min
        if formatted_track_statuses:
            formatted_track_statuses[-1]['end_time'] = start_time
        formatted_track_statuses.append({
            'status': status['Status'],
            'start_time': start_time,
            'end_time': None, 
        })

    # Process weather
    weather_resampled = _process_weather_data(session, timeline, global_t_min)

    # Build frames
    frames = []
    lap_drs_zones = []
    
    for i in range(len(timeline)):
        t = timeline[i]
        weather_snapshot = _get_weather_snapshot(weather_resampled, i)

        # DRS zones detection
        if i > 0:
            drs_prev = resampled_data["drs"][i - 1]
            drs_curr = resampled_data["drs"][i]
            if (drs_curr >= 10) and (drs_prev < 10):
                lap_drs_zones.append({"zone_start": float(resampled_data["dist"][i]), "zone_end": None})
            elif (drs_curr < 10) and (drs_prev >= 10):
                if lap_drs_zones and lap_drs_zones[-1]["zone_end"] is None:
                    lap_drs_zones[-1]["zone_end"] = float(resampled_data["dist"][i])

        frame_payload = {
            "t": round(t, 3),
            "telemetry": {
                "x": float(resampled_data["x"][i]),
                "y": float(resampled_data["y"][i]),
                "dist": float(resampled_data["dist"][i]),
                "rel_dist": float(resampled_data["rel_dist"][i]),
                "speed": float(resampled_data["speed"][i]),
                "gear": int(resampled_data["gear"][i]),
                "throttle": float(resampled_data["throttle"][i]),
                "brake": float(resampled_data["brake"][i]),
                "drs": int(resampled_data["drs"][i]),
            }
        }
        if weather_snapshot:
            frame_payload["weather"] = weather_snapshot
        frames.append(frame_payload)

    lap_time_val = parse_time_string(str(fastest_lap["LapTime"]))
    if lap_time_val is not None:
        frames[-1]["t"] = round(lap_time_val, 3)

    return {
        "frames": frames,
        "track_statuses": formatted_track_statuses,
        "drs_zones": lap_drs_zones,
        "max_speed": telemetry["Speed"].max(),
        "min_speed": telemetry["Speed"].min(),
    }

def _process_quali_driver(args):
    session, driver_code = args
    print(f"Getting qualifying telemetry for driver: {driver_code}")
    
    driver_telemetry_data = {}
    max_speed = 0.0
    min_speed = 0.0

    for segment in ["Q1", "Q2", "Q3"]:
        try:
            segment_telemetry = get_driver_quali_telemetry(session, driver_code, segment)
            driver_telemetry_data[segment] = segment_telemetry
            
            if float(segment_telemetry["max_speed"]) > max_speed:
                max_speed = float(segment_telemetry["max_speed"])
            if float(segment_telemetry["min_speed"]) < min_speed or min_speed == 0.0:
                min_speed = float(segment_telemetry["min_speed"])
        except ValueError:
            driver_telemetry_data[segment] = {"frames": [], "track_statuses": []}

    return {
        "driver_code": driver_code,
        "driver_telemetry_data": driver_telemetry_data,
        "max_speed": max_speed,
        "min_speed": min_speed,
    }

def get_quali_telemetry(session, session_type='Q'):
    event_name = str(session).replace(' ', '_')
    cache_suffix = 'sprintquali' if session_type == 'SQ' else 'quali'

    try:
        if "--refresh-data" not in sys.argv:
            with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "rb") as f:
                data = pickle.load(f)
                print(f"Loaded precomputed {cache_suffix} telemetry data.")
                return data
    except FileNotFoundError:
        pass

    qualifying_results = get_qualifying_results(session)
    
    driver_codes = {num: session.get_driver(num)["Abbreviation"] for num in session.drivers}
    driver_args = [(session, driver_codes[driver_no]) for driver_no in session.drivers]

    print(f"Processing {len(session.drivers)} drivers in parallel...")
    num_processes = min(cpu_count(), len(session.drivers))
    
    telemetry_data = {}
    max_speed = 0.0
    min_speed = 0.0
    
    with Pool(processes=num_processes) as pool:
        results = pool.map(_process_quali_driver, driver_args)
        
    for result in results:
        telemetry_data[result["driver_code"]] = result["driver_telemetry_data"]
        max_speed = max(max_speed, result["max_speed"])
        if result["min_speed"] < min_speed or min_speed == 0.0:
            min_speed = result["min_speed"]

    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "wb") as f:
        pickle.dump({
            "results": qualifying_results,
            "telemetry": telemetry_data,
            "max_speed": max_speed,
            "min_speed": min_speed,
        }, f, protocol=pickle.HIGHEST_PROTOCOL)

    return {
        "results": qualifying_results,
        "telemetry": telemetry_data,
        "max_speed": max_speed,
        "min_speed": min_speed,
    }
