import os
import fastf1
import fastf1.plotting
import numpy as np
import json
from datetime import timedelta

from src.lib.tyres import get_tyre_compound_int

def enable_cache():
    # Check if cache folder exists
    if not os.path.exists('.fastf1-cache'):
        os.makedirs('.fastf1-cache')

    # Enable local cache
    fastf1.Cache.enable_cache('.fastf1-cache')

FPS = 25
DT = 1 / FPS

def load_race_session(year, round_number, session_type='R'):
    # session_type: 'R' (Race), 'S' (Sprint) etc.
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=True)
    return session


def get_driver_colors(session):
    color_mapping = fastf1.plotting.get_driver_color_mapping(session)
    
    # Convert hex colors to RGB tuples
    rgb_colors = {}
    for driver, hex_color in color_mapping.items():
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        rgb_colors[driver] = rgb
    return rgb_colors


def get_race_telemetry(session, session_type='R'):

    event_name = str(session).replace(' ', '_')
    cache_suffix = 'sprint' if session_type == 'S' else 'race'

    # Check if this data has already been computed

    try:
        if "--refresh-data" not in os.sys.argv:
            with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.json", "r") as f:
                frames = json.load(f)
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

    # Extract race results and driver status from session
    print("Extracting race results and driver status...")
    results = session.results
    driver_status_map = {}  # {driver_code: {'status': str, 'classification': int/str, 'laps': int}}

    for _, driver_result in results.iterrows():
        code = driver_result.get('Abbreviation')
        if code:
            status = driver_result.get('Status', 'Unknown')
            classification = driver_result.get('ClassifiedPosition', 'N')
            laps_completed = driver_result.get('Laps', 0)

            # Determine if driver finished normally or DNF'd
            is_finished = 'Finished' in str(status) or '+' in str(status)
            is_dnf = classification in ['R', 'D', 'E', 'W', 'N'] or (not is_finished and laps_completed > 0)

            driver_status_map[code] = {
                'status': str(status),
                'classification': str(classification) if isinstance(classification, str) else int(classification),
                'laps_completed': int(laps_completed) if laps_completed else 0,
                'is_finished': is_finished,
                'is_dnf': is_dnf
            }

    print(f"Driver status extracted for {len(driver_status_map)} drivers")

    driver_data = {}

    global_t_min = None
    global_t_max = None
    

    # 1. Get all of the drivers telemetry data
    for driver_no in drivers:
        code = driver_codes[driver_no]

        print("Getting telemetry for driver:", code)

        laps_driver = session.laps.pick_drivers(driver_no)
        if laps_driver.empty:
            continue

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

            # normalise lap distance to start at 0
            d_lap = d_lap - d_lap.min()
            lap_length = d_lap.max()  # approx. circuit length for this lap

            # race distance = distance before this lap + distance within this lap
            race_d_lap = total_dist_so_far + d_lap

            total_dist_so_far += lap_length

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

        if not t_all:
            continue

        t_all = np.concatenate(t_all)
        x_all = np.concatenate(x_all)
        y_all = np.concatenate(y_all)
        race_dist_all = np.concatenate(race_dist_all)
        rel_dist_all = np.concatenate(rel_dist_all)
        lap_numbers = np.concatenate(lap_numbers)
        tyre_compounds = np.concatenate(tyre_compounds)
        speed_all = np.concatenate(speed_all)
        gear_all = np.concatenate(gear_all)
        drs_all = np.concatenate(drs_all)

        order = np.argsort(t_all)
        t_all = t_all[order]
        x_all = x_all[order]
        y_all = y_all[order]
        race_dist_all = race_dist_all[order]
        rel_dist_all = rel_dist_all[order]            
        lap_numbers = lap_numbers[order]
        tyre_compounds = tyre_compounds[order]
        speed_all = speed_all[order]
        gear_all = gear_all[order]
        drs_all = drs_all[order]

        driver_data[code] = {
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
        }

        t_min = t_all.min()
        t_max = t_all.max()
        global_t_min = t_min if global_t_min is None else min(global_t_min, t_min)
        global_t_max = t_max if global_t_max is None else max(global_t_max, t_max)

    # 2. Create a timeline (start from zero)
    timeline = np.arange(global_t_min, global_t_max, DT) - global_t_min

    # 3. Resample each driver's telemetry (x, y, gap) onto the common timeline
    resampled_data = {}

    for code, data in driver_data.items():
        t = data["t"] - global_t_min  # Shift
        x = data["x"]
        y = data["y"]
        dist = data["dist"]     
        rel_dist = data["rel_dist"]
        tyre = data["tyre"]
        speed = data['speed']
        gear = data['gear']
        drs = data['drs']

        # ensure sorted by time
        order = np.argsort(t)
        t_sorted = t[order]
        x_sorted = x[order]
        y_sorted = y[order]
        dist_sorted = dist[order]
        rel_dist_sorted = rel_dist[order]      
        lap_sorted = data["lap"][order]
        tyre_sorted = tyre[order]
        speed_sorted = speed[order]
        gear_sorted = gear[order]
        drs_sorted = drs[order]
 
        x_resampled = np.interp(timeline, t_sorted, x_sorted)
        y_resampled = np.interp(timeline, t_sorted, y_sorted)
        dist_resampled = np.interp(timeline, t_sorted, dist_sorted)
        rel_dist_resampled = np.interp(timeline, t_sorted, rel_dist_sorted)
        lap_resampled = np.interp(timeline, t_sorted, lap_sorted)
        tyre_resampled = np.interp(timeline, t_sorted, tyre_sorted)
        speed_resampled = np.interp(timeline, t_sorted, speed_sorted)
        gear_resampled = np.interp(timeline, t_sorted, gear_sorted)
        drs_resampled = np.interp(timeline, t_sorted, drs_sorted)
 
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

    # 5. Build the frames + LIVE LEADERBOARD
    frames = []

    # Track when each driver completes their final lap
    driver_last_seen_lap = {code: 0 for code in resampled_data.keys()}
    driver_finish_frame = {}  # {driver_code: frame_index}
    race_leader_finished_frame = None

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
            "speed": d['speed'][i],
            "gear": int(d['gear'][i]),
            "drs": int(d['drs'][i]),
          })

        # If for some reason we have no drivers at this instant
        if not snapshot:
            continue

        # 5b. Sort by race distance to get POSITIONS (1–20)
        # Leader = largest race distance covered
        snapshot.sort(key=lambda r: r["dist"], reverse=True)

        leader = snapshot[0]
        leader_lap = leader["lap"]
        leader_code = leader["code"]

        # Detect when leader finishes (crosses finish line AFTER completing final lap)
        if leader_code in driver_status_map:
            leader_final_laps = driver_status_map[leader_code]['laps_completed']
            # Mark as finished when they COMPLETE the final lap (i.e., start lap final_laps + 1)
            if leader_lap > leader_final_laps and race_leader_finished_frame is None:
                race_leader_finished_frame = i
                driver_finish_frame[leader_code] = i

        # 5c. Detect when each driver completes their final lap
        for car in snapshot:
            code = car["code"]
            current_lap = car["lap"]

            # Check if driver completed their final lap (based on session.results)
            if code in driver_status_map:
                final_laps = driver_status_map[code]['laps_completed']

                # Driver finished: crossed finish line AFTER completing all their laps
                # This happens when current_lap becomes final_laps + 1
                if current_lap > final_laps and code not in driver_finish_frame:
                    if driver_status_map[code]['is_finished']:
                        driver_finish_frame[code] = i

            driver_last_seen_lap[code] = current_lap

        # 5d. Build frame data
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
                "rel_dist": round(car["rel_dist"], 6),
                "tyre": car["tyre"],
                "position": position,
                "speed": car['speed'],
                "gear": car['gear'],
                "drs": car['drs'],
            }

        frames.append({
            "t": float(t),
            "lap": leader_lap,   # leader's lap at this time
            "drivers": frame_data,
            "race_finished": race_leader_finished_frame is not None,
            "leader_finished_frame": race_leader_finished_frame,
        })
    print("completed telemetry extraction...")
    print("Saving to JSON file...")
    # If computed_data/ directory doesn't exist, create it
    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    # Save to file
    with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.json", "w") as f:
        json.dump({
            "frames": frames,
            "driver_colors": get_driver_colors(session),
            "track_statuses": formatted_track_statuses,
            "driver_status": driver_status_map,
            "driver_finish_frames": driver_finish_frame,
        }, f, indent=2)

    print("Saved Successfully!")
    print("The replay should begin in a new window shortly")
    return {
        "frames": frames,
        "driver_colors": get_driver_colors(session),
        "track_statuses": formatted_track_statuses,
        "driver_status": driver_status_map,
        "driver_finish_frames": driver_finish_frame,
    }
