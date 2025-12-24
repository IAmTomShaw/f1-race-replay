import os
import sys
import fastf1
import fastf1.plotting
from multiprocessing import Pool, cpu_count
import numpy as np
import json
import pickle
from datetime import timedelta

from src.lib.tyres import get_tyre_compound_int
from src.lib.time import parse_time_string, format_time

import pandas as pd

def enable_cache():
    # Check if cache folder exists
    if not os.path.exists('.fastf1-cache'):
        os.makedirs('.fastf1-cache')

    # Enable local cache
    fastf1.Cache.enable_cache('.fastf1-cache')

FPS = 25
DT = 1 / FPS

def _process_single_driver(args):
    """Process telemetry data for a single driver - must be top-level for multiprocessing"""
    driver_no, session, driver_code = args
    
    print(f"Getting telemetry for driver: {driver_code}")

    laps_driver = session.laps.pick_drivers(driver_no)
    if laps_driver.empty:
        return None

    driver_max_lap = laps_driver.LapNumber.max() if not laps_driver.empty else 0

    t_all = []
    x_all = []
    y_all = []
    race_dist_all = []
    rel_dist_all = []
    lap_numbers = []
    tyre_compounds = []
    speed_all = []
    gear_all = []
    drs_all = []
    throttle_all = []
    brake_all = []

    total_dist_so_far = 0.0

    # iterate laps in order
    for _, lap in laps_driver.iterlaps():
        # get telemetry for THIS lap only
        lap_tel = lap.get_telemetry()
        lap_number = lap.LapNumber
        tyre_compund_as_int = get_tyre_compound_int(lap.Compound)

        if lap_tel.empty:
            continue

        t_lap = lap_tel["SessionTime"].dt.total_seconds().to_numpy()
        x_lap = lap_tel["X"].to_numpy()
        y_lap = lap_tel["Y"].to_numpy()
        d_lap = lap_tel["Distance"].to_numpy()          
        rd_lap = lap_tel["RelativeDistance"].to_numpy()
        speed_kph_lap = lap_tel["Speed"].to_numpy()
        gear_lap = lap_tel["nGear"].to_numpy()
        drs_lap = lap_tel["DRS"].to_numpy()
        throttle_lap = lap_tel["Throttle"].to_numpy()
        brake_lap = lap_tel["Brake"].to_numpy().astype(float)

        # race distance = distance before this lap + distance within this lap
        race_d_lap = total_dist_so_far + d_lap

        t_all.append(t_lap)
        x_all.append(x_lap)
        y_all.append(y_lap)
        race_dist_all.append(race_d_lap)
        rel_dist_all.append(rd_lap)
        lap_numbers.append(np.full_like(t_lap, lap_number))
        tyre_compounds.append(np.full_like(t_lap, tyre_compund_as_int))
        speed_all.append(speed_kph_lap)
        gear_all.append(gear_lap)
        drs_all.append(drs_lap)
        throttle_all.append(throttle_lap)
        brake_all.append(brake_lap)

    if not t_all:
        return None

    # Concatenate all arrays at once for better performance
    all_arrays = [t_all, x_all, y_all, race_dist_all, rel_dist_all, 
                  lap_numbers, tyre_compounds, speed_all, gear_all, drs_all]
    
    t_all, x_all, y_all, race_dist_all, rel_dist_all, lap_numbers, \
    tyre_compounds, speed_all, gear_all, drs_all = [np.concatenate(arr) for arr in all_arrays]

    # Sort all arrays by time in one operation
    order = np.argsort(t_all)
    all_data = [t_all, x_all, y_all, race_dist_all, rel_dist_all, 
                lap_numbers, tyre_compounds, speed_all, gear_all, drs_all]
    
    t_all, x_all, y_all, race_dist_all, rel_dist_all, lap_numbers, \
    tyre_compounds, speed_all, gear_all, drs_all = [arr[order] for arr in all_data]

    throttle_all = np.concatenate(throttle_all)[order]
    brake_all = np.concatenate(brake_all)[order]

    print(f"Completed telemetry for driver: {driver_code}")
    
    return {
        "code": driver_code,
        "data": {
            "t": t_all,
            "x": x_all,
            "y": y_all,
            "dist": race_dist_all,
            "rel_dist": rel_dist_all,                   
            "lap": lap_numbers,
            "tyre": tyre_compounds,
            "speed": speed_all,
            "gear": gear_all,
            "drs": drs_all,
            "throttle": throttle_all,
            "brake": brake_all,
        },
        "t_min": t_all.min(),
        "t_max": t_all.max(),
        "max_lap": driver_max_lap
    }

def load_session(year, round_number, session_type='R'):
    # session_type: 'R' (Race), 'S' (Sprint) etc.
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=True, weather=True)
    return session

# The following functions require a loaded session object

def get_driver_colors(session):
    color_mapping = fastf1.plotting.get_driver_color_mapping(session)
    
    # Convert hex colors to RGB tuples
    rgb_colors = {}
    for driver, hex_color in color_mapping.items():
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        rgb_colors[driver] = rgb
    return rgb_colors

def get_circuit_rotation(session):
    circuit = session.get_circuit_info()
    return circuit.rotation

def get_starting_grid(session):
    """
    Extract starting grid positions for each driver.
    Returns a dict mapping driver code (e.g., 'VER') to their grid position (1-20).
    """
    results = session.results
    grid_positions = {}
    
    for _, row in results.iterrows():
        driver_code = row["Abbreviation"]
        grid_pos = row.get("GridPosition")
        
        # Handle NaN or missing grid positions (e.g., pit lane starts)
        if pd.notna(grid_pos):
            grid_positions[driver_code] = int(grid_pos)
        else:
            # If no grid position, use their qualifying position or default to 20
            grid_positions[driver_code] = 20
    
    return grid_positions

def get_race_telemetry(session, session_type='R'):

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
    # Prepare arguments for parallel processing
    print(f"Processing {len(drivers)} drivers in parallel...")
    driver_args = [(driver_no, session, driver_codes[driver_no]) for driver_no in drivers]
    
    num_processes = min(cpu_count(), len(drivers))
    
    with Pool(processes=num_processes) as pool:
        results = pool.map(_process_single_driver, driver_args)
    
    # Process results
    for result in results:
        if result is None:
            continue
        
        code = result["code"]
        driver_data[code] = result["data"]
        
        t_min = result["t_min"]
        t_max = result["t_max"]
        max_lap_number = max(max_lap_number, result["max_lap"])
        
        global_t_min = t_min if global_t_min is None else min(global_t_min, t_min)
        global_t_max = t_max if global_t_max is None else max(global_t_max, t_max)

    # Ensure we have valid time bounds
    if global_t_min is None or global_t_max is None:
        raise ValueError("No valid telemetry data found for any driver")

    # 2. Create a timeline (start from zero)
    timeline = np.arange(global_t_min, global_t_max, DT) - global_t_min

    # 3. Resample each driver's telemetry (x, y, gap) onto the common timeline
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
            "dist": dist_resampled,   # race distance (metres since Lap 1 start)
            "rel_dist": rel_dist_resampled,
            "lap": lap_resampled,
            "tyre": tyre_resampled,
            "speed": speed_resampled,
            "gear": gear_resampled,
            "drs": drs_resampled,
            "throttle": throttle_resampled,
            "brake": brake_resampled
        }

    # 4. Incorporate track status data into the timeline (for safety car, VSC, etc.)

    track_status = session.track_status

    formatted_track_statuses = []

    for status in track_status.to_dict('records'):
        seconds = timedelta.total_seconds(status['Time'])

        start_time = seconds - global_t_min # Shift to match timeline
        end_time = None

        # Set the end time of the previous status

        if formatted_track_statuses:
            formatted_track_statuses[-1]['end_time'] = start_time

        formatted_track_statuses.append({
            'status': status['Status'],
            'start_time': start_time,
            'end_time': end_time, 
        })

    # 4.1. Resample weather data onto the same timeline for playback
    weather_resampled = None
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

                track_temp = _resample(_maybe_get("TrackTemp"))
                air_temp = _resample(_maybe_get("AirTemp"))
                humidity = _resample(_maybe_get("Humidity"))
                wind_speed = _resample(_maybe_get("WindSpeed"))
                wind_direction = _resample(_maybe_get("WindDirection"))
                rainfall_raw = _maybe_get("Rainfall")
                rainfall = _resample(rainfall_raw.astype(float)) if rainfall_raw is not None else None

                weather_resampled = {
                    "track_temp": track_temp,
                    "air_temp": air_temp,
                    "humidity": humidity,
                    "wind_speed": wind_speed,
                    "wind_direction": wind_direction,
                    "rainfall": rainfall,
                }
        except Exception as e:
            print(f"Weather data could not be processed: {e}")

    # 5. Build the frames + LIVE LEADERBOARD
    frames = []
    num_frames = len(timeline)
    
    # Pre-extract data references for faster access
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

        # If for some reason we have no drivers at this instant
        if not snapshot:
            continue

        # 5b. Sort by race distance to get POSITIONS (1–20)
        # Leader = largest race distance covered
        snapshot.sort(key=lambda r: r["dist"], reverse=True)

        leader = snapshot[0]
        leader_lap = leader["lap"]

        # TODO: This 5c. step seems futile currently as we are not using gaps anywhere, and it doesn't even comput the gaps. I think I left this in when removing the "gaps" feature that was half-finished during the initial development.

        # 5c. Compute gap to car in front in SECONDS
        frame_data = {}

        for idx, car in enumerate(snapshot):
            code = car["code"]
            position = idx + 1

            # include speed, gear, drs_active in frame driver dict
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

        weather_snapshot = {}
        if weather_resampled:
            try:
                wt = weather_resampled
                rain_val = wt["rainfall"][i] if wt.get("rainfall") is not None else 0.0
                weather_snapshot = {
                    "track_temp": float(wt["track_temp"][i]) if wt.get("track_temp") is not None else None,
                    "air_temp": float(wt["air_temp"][i]) if wt.get("air_temp") is not None else None,
                    "humidity": float(wt["humidity"][i]) if wt.get("humidity") is not None else None,
                    "wind_speed": float(wt["wind_speed"][i]) if wt.get("wind_speed") is not None else None,
                    "wind_direction": float(wt["wind_direction"][i]) if wt.get("wind_direction") is not None else None,
                    "rain_state": "RAINING" if rain_val and rain_val >= 0.5 else "DRY",
                }
            except Exception as e:
                print(f"Failed to attach weather data to frame {i}: {e}")

        frame_payload = {
            "t": round(t, 3),
            "lap": leader_lap,   # leader's lap at this time
            "drivers": frame_data,
        }
        if weather_snapshot:
            frame_payload["weather"] = weather_snapshot

        frames.append(frame_payload)
    print("completed telemetry extraction...")
    print("Saving to cache file...")
    # If computed_data/ directory doesn't exist, create it
    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    # Get starting grid positions
    grid_positions = get_starting_grid(session)

    # Save using pickle (10-100x faster than JSON)
    with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "wb") as f:
        pickle.dump({
            "frames": frames,
            "driver_colors": get_driver_colors(session),
            "track_statuses": formatted_track_statuses,
            "total_laps": int(max_lap_number),
            "grid_positions": grid_positions,
        }, f, protocol=pickle.HIGHEST_PROTOCOL)

    print("Saved Successfully!")
    print("The replay should begin in a new window shortly")
    return {
        "frames": frames,
        "driver_colors": get_driver_colors(session),
        "track_statuses": formatted_track_statuses,
        "total_laps": int(max_lap_number),
        "grid_positions": grid_positions,
    }


def get_qualifying_results(session):

    # Extract the qualifying results and return a list of the drivers, their positions and their lap times in each qualifying segment

    results = session.results

    qualifying_data = []

    for _, row in results.iterrows():
        driver_code = row["Abbreviation"]
        position = int(row["Position"])
        q1_time = row["Q1"]
        q2_time = row["Q2"]
        q3_time = row["Q3"]

        # Convert pandas Timedelta objects to seconds (or None if NaT)
        def convert_time_to_seconds(time_val) -> str:
            if pd.isna(time_val):
                return None
            return str(time_val.total_seconds())    

        qualifying_data.append({
            "code": driver_code,
            "position": position,
            "color": get_driver_colors(session).get(driver_code, (128,128,128)),
            "Q1": convert_time_to_seconds(q1_time),
            "Q2": convert_time_to_seconds(q2_time),
            "Q3": convert_time_to_seconds(q3_time),
        })
    return qualifying_data

def get_driver_quali_telemetry(session, driver_code: str, quali_segment: str):

    # Split Q1/Q2/Q3 sections
    q1, q2, q3 = session.laps.split_qualifying_sessions()

    segments = {
        "Q1": q1,
        "Q2": q2,
        "Q3": q3
    }

    # Validate the segment
    if quali_segment not in segments:
        raise ValueError("quali_segment must be 'Q1', 'Q2', or 'Q3'")

    segment_laps = segments[quali_segment]
    if segment_laps is None:
        raise ValueError(f"{quali_segment} does not exist for this session.")

    # Filter laps for the driver
    driver_laps = segment_laps.pick_drivers(driver_code)
    if driver_laps.empty:
        raise ValueError(f"No laps found for driver '{driver_code}' in {quali_segment}")

    # Pick fastest lap
    fastest_lap = driver_laps.pick_fastest()

    # Extract telemetry with xyz coordinates

    if fastest_lap is None:
        raise ValueError(f"No valid laps for driver '{driver_code}' in {quali_segment}")

    telemetry = fastest_lap.get_telemetry()

    # Guard: if telemetry has no time data, return empty
    if telemetry is None or telemetry.empty or 'Time' not in telemetry or len(telemetry) == 0:
        return {"frames": [], "track_statuses": []}

    global_t_min = telemetry["Time"].dt.total_seconds().min()
    global_t_max = telemetry["Time"].dt.total_seconds().max()

    max_speed = telemetry["Speed"].max()
    min_speed = telemetry["Speed"].min()

    # An array of objects containing the start and end disances of each time the driver used DRS during the lap
    lap_drs_zones = []

    # Build arrays directly from dataframes
    t_arr = telemetry["Time"].dt.total_seconds().to_numpy()
    x_arr = telemetry["X"].to_numpy()
    y_arr = telemetry["Y"].to_numpy()
    dist_arr = telemetry["Distance"].to_numpy()
    rel_dist_arr = telemetry["RelativeDistance"].to_numpy()
    speed_arr = telemetry["Speed"].to_numpy()
    gear_arr = telemetry["nGear"].to_numpy()
    throttle_arr = telemetry["Throttle"].to_numpy()
    brake_arr = telemetry["Brake"].to_numpy()
    drs_arr = telemetry["DRS"].to_numpy()

    # Recompute time bounds from the (possibly modified) telemetry times
    global_t_min = float(t_arr.min())
    global_t_max = float(t_arr.max())

    # Create timeline (relative times starting at zero) and include endpoint
    timeline = np.arange(global_t_min, global_t_max + DT/2, DT) - global_t_min

    # Ensure we have at least one sample
    if t_arr.size == 0:
        return {"frames": [], "track_statuses": []}

    # Shift telemetry times to same reference as timeline (relative to global_t_min)
    t_rel = t_arr - global_t_min

    # Sort & deduplicate times using the relative times
    order = np.argsort(t_rel)
    t_sorted = t_rel[order]
    t_sorted_unique, unique_idx = np.unique(t_sorted, return_index=True)
    idx_map = order[unique_idx]

    x_sorted = x_arr[idx_map]
    y_sorted = y_arr[idx_map]
    dist_sorted = dist_arr[idx_map]
    rel_dist_sorted = rel_dist_arr[idx_map]
    speed_sorted = speed_arr[idx_map]
    gear_sorted = gear_arr[idx_map]
    throttle_sorted = throttle_arr[idx_map]
    brake_sorted = brake_arr[idx_map]
    drs_sorted = drs_arr[idx_map]

    # Continuous interpolation
    x_resampled = np.interp(timeline, t_sorted_unique, x_sorted)
    y_resampled = np.interp(timeline, t_sorted_unique, y_sorted)
    dist_resampled = np.interp(timeline, t_sorted_unique, dist_sorted)
    rel_dist_resampled = np.interp(timeline, t_sorted_unique, rel_dist_sorted)
    speed_resampled = np.round(np.interp(timeline, t_sorted_unique, speed_sorted), 1)
    throttle_resampled = np.round(np.interp(timeline, t_sorted_unique, throttle_sorted), 1)
    brake_resampled = np.round(np.interp(timeline, t_sorted_unique, brake_sorted), 1)
    drs_resampled = np.interp(timeline, t_sorted_unique, drs_sorted)

    # Make sure that braking is between 0 and 100 so that it matches the throttle scale

    brake_resampled = brake_resampled * 100.0

    # Forward-fill / step sampling for discrete fields (gear)
    idxs = np.searchsorted(t_sorted_unique, timeline, side='right') - 1
    idxs = np.clip(idxs, 0, len(t_sorted_unique) - 1)
    gear_resampled = gear_sorted[idxs].astype(int)

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

    track_status = session.track_status

    formatted_track_statuses = []

    for status in track_status.to_dict('records'):
        seconds = timedelta.total_seconds(status['Time'])

        start_time = seconds - global_t_min # Shift to match timeline
        end_time = None

        # Set the end time of the previous status
        if formatted_track_statuses:
            formatted_track_statuses[-1]['end_time'] = start_time

        formatted_track_statuses.append({
            'status': status['Status'],
            'start_time': start_time,
            'end_time': end_time, 
        })

    # 4.1. Resample weather data onto the same timeline for playback
    weather_resampled = None
    weather_df = getattr(session, "weather_data", None)
    if weather_df is not None and not weather_df.empty:
        try:
            weather_times = weather_df["Time"].dt.total_seconds().to_numpy() - global_t_min
            if len(weather_times) > 0:
                order_w = np.argsort(weather_times)
                weather_times = weather_times[order_w]

                def _maybe_get(name):
                    return weather_df[name].to_numpy()[order_w] if name in weather_df else None

                def _resample(series):
                    if series is None:
                        return None
                    return np.interp(timeline, weather_times, series)

                track_temp = _resample(_maybe_get("TrackTemp"))
                air_temp = _resample(_maybe_get("AirTemp"))
                humidity = _resample(_maybe_get("Humidity"))
                wind_speed = _resample(_maybe_get("WindSpeed"))
                wind_direction = _resample(_maybe_get("WindDirection"))
                rainfall_raw = _maybe_get("Rainfall")
                rainfall = _resample(rainfall_raw.astype(float)) if rainfall_raw is not None else None

                weather_resampled = {
                    "track_temp": track_temp,
                    "air_temp": air_temp,
                    "humidity": humidity,
                    "wind_speed": wind_speed,
                    "wind_direction": wind_direction,
                    "rainfall": rainfall,
                }
        except Exception as e:
            print(f"Weather data could not be processed: {e}")

    # Build the frames
    frames = []
    num_frames = len(timeline)

    for i in range(num_frames):
        t = timeline[i]

        weather_snapshot = {}
        if weather_resampled:
            try:
                wt = weather_resampled
                rain_val = wt["rainfall"][i] if wt.get("rainfall") is not None else 0.0
                weather_snapshot = {
                    "track_temp": float(wt["track_temp"][i]) if wt.get("track_temp") is not None else None,
                    "air_temp": float(wt["air_temp"][i]) if wt.get("air_temp") is not None else None,
                    "humidity": float(wt["humidity"][i]) if wt.get("humidity") is not None else None,
                    "wind_speed": float(wt["wind_speed"][i]) if wt.get("wind_speed") is not None else None,
                    "wind_direction": float(wt["wind_direction"][i]) if wt.get("wind_direction") is not None else None,
                    "rain_state": "RAINING" if rain_val and rain_val >= 0.5 else "DRY",
                }
            except Exception as e:
                print(f"Failed to attach weather data to frame {i}: {e}")

        # Check if drs has changed from the previous frame

        if i > 0:
            drs_prev = resampled_data["drs"][i - 1]
            drs_curr = resampled_data["drs"][i]

            if (drs_curr >= 10) and (drs_prev < 10):
                # DRS activated
                lap_drs_zones.append({
                    "zone_start": float(resampled_data["dist"][i]),
                    "zone_end": None,
                })
            elif (drs_curr < 10) and (drs_prev >= 10):
                # DRS deactivated
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

    # Set the time of the final frame to the exact lap time
            
    frames[-1]["t"] = round(parse_time_string(str(fastest_lap["LapTime"])), 3)

    return {
        "frames": frames,
        "track_statuses": formatted_track_statuses,
        "drs_zones": lap_drs_zones,
        "max_speed": max_speed,
        "min_speed": min_speed,
    }


def _process_quali_driver(args):
    """Process qualifying telemetry data for a single driver - must be top-level for multiprocessing"""
    session, driver_code = args

    print(f"Getting qualifying telemetry for driver: {driver_code}")

    driver_telemetry_data = {}

    max_speed = 0.0
    min_speed = 0.0

    for segment in ["Q1", "Q2", "Q3"]:
        try:
            segment_telemetry = get_driver_quali_telemetry(session, driver_code, segment)
            driver_telemetry_data[segment] = segment_telemetry

            # Update global max/min speed
            if segment_telemetry["max_speed"] > max_speed:
                max_speed = segment_telemetry["max_speed"]
            if segment_telemetry["min_speed"] < min_speed or min_speed == 0.0:
                min_speed = segment_telemetry["min_speed"]

        except ValueError:
            driver_telemetry_data[segment] = {"frames": [], "track_statuses": []}

    print(f"Finished processing qualifying telemetry for driver: {driver_code}")
        
    return {
        "driver_code": driver_code,
        "driver_telemetry_data": driver_telemetry_data,
        "max_speed": max_speed,
        "min_speed": min_speed,
    }


def get_quali_telemetry(session, session_type='Q'):
    # This function is going to get the results from qualifying and the telemetry for each drivers' fastest laps in each qualifying segment

    # The structure of the returned data will be:
    # {
    #   "results": [ { "code": driver_code, "position": position, "Q1": time, "Q2": time, "Q3": time }, ... ],
    #   "telemetry": {
    #       "driver_code": {
    #           "Q1": { "frames": [ { "t": time, "x": x, "y": y, "dist": dist, "speed": speed, "gear": gear }, ... ] },
    #           "Q2": { ... },
    #           "Q3": { ... },
    #       },
    #       ...
    #   }
    # }

    event_name = str(session).replace(' ', '_')
    cache_suffix = 'sprintquali' if session_type == 'SQ' else 'quali'

    # Check if this data has already been computed
    try:
        if "--refresh-data" not in sys.argv:
            with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "rb") as f:
                data = pickle.load(f)
                print(f"Loaded precomputed {cache_suffix} telemetry data.")
                print("The replay should begin in a new window shortly!")
                return data
    except FileNotFoundError:
        pass  # Need to compute from scratch

    qualifying_results = get_qualifying_results(session)

    telemetry_data = {}

    max_speed = 0.0
    min_speed = 0.0

    driver_codes = {
        num: session.get_driver(num)["Abbreviation"]
        for num in session.drivers
    }

    telemetry_data = {}

    driver_args = [(session, driver_codes[driver_no]) for driver_no in session.drivers]

    print(f"Processing {len(session.drivers)} drivers in parallel...")
    
    num_processes = min(cpu_count(), len(session.drivers))
    
    with Pool(processes=num_processes) as pool:
        results = pool.map(_process_quali_driver, driver_args)
    for result in results:
        driver_code = result["driver_code"]
        telemetry_data[driver_code] = result["driver_telemetry_data"]

        if result["max_speed"] > max_speed:
            max_speed = result["max_speed"]
        if result["min_speed"] < min_speed or min_speed == 0.0:
            min_speed = result["min_speed"]

    # Save to the compute_data directory

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