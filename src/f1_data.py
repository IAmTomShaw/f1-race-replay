import os
import fastf1
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

def load_race_session(year, round_number):
    session = fastf1.get_session(year, round_number, 'R')
    session.load(telemetry=True)
    return session


def get_driver_colors(session):
    """
    Get driver colors with fallback if matplotlib/plotting import fails.
    """
    # Try to use fastf1.plotting if available
    try:
        import fastf1.plotting
        color_mapping = fastf1.plotting.get_driver_color_mapping(session)
        
        # Convert hex colors to RGB tuples
        rgb_colors = {}
        for driver, hex_color in color_mapping.items():
            hex_color = hex_color.lstrip('#')
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            rgb_colors[driver] = rgb
        return rgb_colors
    except (ImportError, AttributeError):
        # Fallback: Get colors from team data if plotting fails
        print("Warning: Could not import fastf1.plotting, using fallback color scheme.")
        rgb_colors = {}
        
        # Default color palette for F1 teams (fallback)
        default_colors = [
            (220, 20, 60),    # Red (Ferrari-like)
            (0, 210, 190),    # Cyan (Aston Martin-like)
            (255, 135, 0),    # Orange (McLaren-like)
            (0, 111, 98),     # Dark Teal (Mercedes-like)
            (237, 28, 36),    # Bright Red
            (6, 0, 239),      # Blue
            (255, 245, 0),    # Yellow
            (255, 255, 255),  # White
            (150, 150, 150),  # Gray
            (50, 50, 50),     # Dark Gray
            (255, 0, 255),    # Magenta
            (0, 255, 0),      # Green
            (255, 165, 0),    # Orange
            (0, 0, 255),      # Blue
            (128, 0, 128),    # Purple
            (255, 192, 203),  # Pink
            (0, 255, 255),    # Cyan
            (128, 128, 0),    # Olive
            (255, 0, 0),      # Red
            (0, 128, 0),      # Dark Green
        ]
        
        # Try to get driver codes from session
        drivers = session.drivers
        for idx, driver_no in enumerate(sorted(drivers)):
            try:
                driver_info = session.get_driver(driver_no)
                code = driver_info["Abbreviation"]
                # Use team name to get a more appropriate color if available
                if "TeamName" in driver_info:
                    team = driver_info["TeamName"].upper()
                    # Simple color mapping based on team names
                    if "FERRARI" in team:
                        rgb_colors[code] = (220, 20, 60)
                    elif "MERCEDES" in team:
                        rgb_colors[code] = (0, 111, 98)
                    elif "RED BULL" in team or "REDBULL" in team:
                        rgb_colors[code] = (6, 0, 239)
                    elif "MCLAREN" in team:
                        rgb_colors[code] = (255, 135, 0)
                    elif "ASTON" in team:
                        rgb_colors[code] = (0, 210, 190)
                    else:
                        rgb_colors[code] = default_colors[idx % len(default_colors)]
                else:
                    rgb_colors[code] = default_colors[idx % len(default_colors)]
            except (KeyError, AttributeError, TypeError):
                # If we can't get driver info, skip this driver
                pass
        
        return rgb_colors


def get_race_telemetry(session):

    event_name = str(session).replace(' ', '_')

    # Check if this data has already been computed

    try:
        if "--refresh-data" not in os.sys.argv:
            with open(f"computed_data/{event_name}_race_telemetry.json", "r") as f:
                frames = json.load(f)
                print("Loaded precomputed race telemetry data.")
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
                "rel_dist": round(car["rel_dist"], 6),
                "tyre": car["tyre"],
                "position": position,
                "speed": car['speed'],
                "gear": car['gear'],
                "drs": car['drs'],
            }

        frames.append({
            "t": float(t),
            "lap": leader_lap,   # leader’s lap at this time
            "drivers": frame_data,
        })
    print("completed telemetry extraction...")
    print("Saving to JSON file...")
    # If computed_data/ directory doesn't exist, create it
    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    # Save to file
    with open(f"computed_data/{event_name}_race_telemetry.json", "w") as f:
        json.dump({
            "frames": frames,
            "driver_colors": get_driver_colors(session),
            "track_statuses": formatted_track_statuses,
        }, f, indent=2)

    print("Saved Successfully!")
    print("The replay should begin in a new window shortly")
    return {
        "frames": frames,
        "driver_colors": get_driver_colors(session),
        "track_statuses": formatted_track_statuses,
    }
