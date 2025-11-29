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

def load_race_session(year, round_number):
    session = fastf1.get_session(year, round_number, 'R')
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

    # Decide on the battle gap
    BATTLE_GAP_THRESHOLD = 1.0          # seconds to car ahead
    MIN_BATTLE_SPEED_KMH = 120.0        # only count as battle if both are above this

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
                "speed": d["speed"][i],
                "gear": int(d["gear"][i]),
                "drs": int(d["drs"][i]),
            })

        # If for some reason we have no drivers at this instant
        if not snapshot:
            continue

        # Sort by race distance to get POSITIONS (leader first)
        snapshot.sort(key=lambda r: r["dist"], reverse=True)

        leader = snapshot[0]
        leader_lap = leader["lap"]

        frame_data = {}

        # Pre-calc leader speed in m/s for gap_to_leader
        leader_speed_kmh = leader.get("speed", 0.0) or 0.0
        leader_speed_mps = leader_speed_kmh * (1000.0 / 3600.0) if leader_speed_kmh > 1 else None

        for idx, car in enumerate(snapshot):
            code = car["code"]
            position = idx + 1

            # Defaults
            gap_to_ahead = None
            gap_to_leader = 0.0 if idx == 0 else None
            in_battle = False
            battle_with = None

            # Current car speed
            speed_kmh = car.get("speed", 0.0) or 0.0
            speed_mps = speed_kmh * (1000.0 / 3600.0) if speed_kmh > 1 else None

            # ---- Gap to leader (for GAP column) ----
            if idx == 0:
                gap_to_leader = 0.0
            else:
                # approximate using this car's own speed; fall back to leader speed if needed
                ref_speed_mps = speed_mps or leader_speed_mps
                if ref_speed_mps and ref_speed_mps > 0:
                    dist_gap_leader = leader["dist"] - car["dist"]
                    gap_to_leader = dist_gap_leader / ref_speed_mps

            # ---- Gap to car ahead (for battle detection) ----
            if idx > 0:
                car_ahead = snapshot[idx - 1]
                dist_gap_ahead = car_ahead["dist"] - car["dist"]  # > 0 if behind

                speed_ahead_kmh = car_ahead.get("speed", 0.0) or 0.0
                speed_ahead_mps = speed_ahead_kmh * (1000.0 / 3600.0) if speed_ahead_kmh > 1 else None

                if speed_mps and speed_mps > 0:
                    gap_to_ahead = dist_gap_ahead / speed_mps

                # Only flag as battle if small gap and both are at racing speed
                if (
                    gap_to_ahead is not None
                    and gap_to_ahead <= BATTLE_GAP_THRESHOLD
                    and speed_kmh >= MIN_BATTLE_SPEED_KMH
                    and speed_ahead_kmh >= MIN_BATTLE_SPEED_KMH
                ):
                    in_battle = True
                    battle_with = car_ahead["code"]

            frame_data[code] = {
                "x": car["x"],
                "y": car["y"],
                "dist": car["dist"],
                "lap": car["lap"],
                "rel_dist": round(car["rel_dist"], 6),
                "tyre": car["tyre"],
                "position": position,
                "speed": car["speed"],
                "gear": car["gear"],
                "drs": car["drs"],
                "gap_to_leader": gap_to_leader,
                "gap_to_ahead": gap_to_ahead,
                "in_battle": in_battle,
                "battle_with": battle_with,
            }

        frames.append({
            "t": float(t),
            "lap": leader_lap,   # leader’s lap at this time
            "drivers": frame_data,
        })

    print("completed telemetry extraction...")
    print("Number of frames generated:", len(frames))
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