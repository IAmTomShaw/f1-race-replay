import os
import pickle
import sys
from datetime import timedelta, date
from multiprocessing import Pool, cpu_count

import fastf1
import fastf1.plotting
import numpy as np
import pandas as pd

from src.lib.settings import get_settings
from src.lib.time import parse_time_string
from src.lib.tyres import get_tyre_compound_int


def enable_cache():
    # Get cache location from settings
    settings = get_settings()
    cache_path = settings.cache_location

    # Check if cache folder exists
    if not os.path.exists(cache_path):
        os.makedirs(cache_path)

    # Enable local cache
    fastf1.Cache.enable_cache(cache_path)


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
    tyre_life_all = []
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
        tyre_life = lap.TyreLife if pd.notna(lap.TyreLife) else 0

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
        tyre_life_all.append(np.full_like(t_lap, tyre_life))
        speed_all.append(speed_kph_lap)
        gear_all.append(gear_lap)
        drs_all.append(drs_lap)
        throttle_all.append(throttle_lap)
        brake_all.append(brake_lap)

    if not t_all:
        return None

    # Concatenate all arrays at once for better performance
    all_arrays = [t_all, x_all, y_all, race_dist_all, rel_dist_all, 
                  lap_numbers, tyre_compounds, tyre_life_all, speed_all, gear_all, drs_all]
    
    t_all, x_all, y_all, race_dist_all, rel_dist_all, lap_numbers, \
    tyre_compounds, tyre_life_all, speed_all, gear_all, drs_all = [np.concatenate(arr) for arr in all_arrays]

    # Sort all arrays by time in one operation
    order = np.argsort(t_all)
    all_data = [t_all, x_all, y_all, race_dist_all, rel_dist_all, 
                lap_numbers, tyre_compounds, tyre_life_all, speed_all, gear_all, drs_all]
    
    t_all, x_all, y_all, race_dist_all, rel_dist_all, lap_numbers, \
    tyre_compounds, tyre_life_all, speed_all, gear_all, drs_all = [arr[order] for arr in all_data]

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
            "tyre_life": tyre_life_all,
            "speed": speed_all,
            "gear": gear_all,
            "drs": drs_all,
            "throttle": throttle_all,
            "brake": brake_all,
        },
        "t_min": t_all.min(),
        "t_max": t_all.max(),
        "max_lap": driver_max_lap,
    }


def load_session(year, round_number, session_type="R"):
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
        hex_color = hex_color.lstrip("#")
        rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        rgb_colors[driver] = rgb
    return rgb_colors


def get_circuit_rotation(session):
    circuit = session.get_circuit_info()
    return circuit.rotation


def _compute_fastest_lap_holders(frames, session, global_t_min):
    """
    Compute which driver holds the fastest lap at each frame.

    Iterates through all driver laps ordered by completion time.
    For each frame, sets 'fastest_lap_holder' to the driver code that
    held the overall fastest lap at that point in the race, along with
    the formatted lap time.
    """
    # Build a list of (completion_time_seconds, driver_code, lap_time_seconds, lap_number)
    # lap["Time"] is the session-elapsed Timedelta when the lap was completed
    lap_completions = []
    for driver_no in session.drivers:
        driver_code = session.get_driver(driver_no)["Abbreviation"]
        laps = session.laps.pick_drivers(driver_no)
        for _, lap in laps.iterlaps():
            lap_time = lap["LapTime"]
            completion_time = lap["Time"]
            if pd.isna(lap_time) or pd.isna(completion_time):
                continue
            lap_completions.append((
                completion_time.total_seconds() - global_t_min,
                driver_code,
                lap_time.total_seconds(),
                int(lap["LapNumber"]),
            ))

    # Sort by completion time
    lap_completions.sort(key=lambda x: x[0])

    # Walk through frames and lap completions together
    current_fastest_code = None
    current_fastest_time = float("inf")
    current_fastest_lap_num = 0
    lc_idx = 0

    for frame in frames:
        frame_t = frame["t"]
        # Process any laps completed up to this frame time
        while lc_idx < len(lap_completions) and lap_completions[lc_idx][0] <= frame_t:
            _, code, lap_time_s, lap_num = lap_completions[lc_idx]
            if lap_time_s < current_fastest_time:
                current_fastest_time = lap_time_s
                current_fastest_code = code
                current_fastest_lap_num = lap_num
            lc_idx += 1

        if current_fastest_code:
            mins = int(current_fastest_time // 60)
            secs = current_fastest_time % 60
            frame["fastest_lap"] = {
                "driver": current_fastest_code,
                "time": f"{mins}:{secs:06.3f}",
                "lap": current_fastest_lap_num,
            }


def _compute_safety_car_positions(frames, track_statuses, session):
    """
    Simulate safety car (SC) positions for each frame based on track status.
    
    The F1 API does not provide SC GPS data, so we simulate it:
    - SC appears when track status is "4" (Safety Car deployed)
    - SC enters from pitlane, travels along the track until the first car catches up
    - SC leads the pack while on track
    - When the SC period ends, SC accelerates away and enters the pitlane
    
    Handles edge cases:
    - The first car behind the SC may be a lapped car, not the race leader
    - Lapped cars can be let through (e.g. Abu Dhabi 2021 scenario)
    
    Each frame gets a 'safety_car' key with:
      - x, y: world coordinates of the SC
      - phase: 'deploying' | 'on_track' | 'returning' | None
      - alpha: 0.0-1.0 for fade in/out animation
    """
    if not frames or not track_statuses:
        return

    # Build reference polyline from the first driver's telemetry to get track shape
    try:
        fastest_lap = session.laps.pick_fastest()
        if fastest_lap is None:
            print("Safety Car: No fastest lap found, skipping SC position computation")
            return
        tel = fastest_lap.get_telemetry()
        if tel is None or tel.empty:
            print("Safety Car: No telemetry data, skipping SC position computation")
            return
        
        ref_xs = tel["X"].to_numpy().astype(float)
        ref_ys = tel["Y"].to_numpy().astype(float)
        ref_dist = tel["Distance"].to_numpy().astype(float)
        
        if len(ref_xs) < 10:
            print("Safety Car: Insufficient reference points, skipping")
            return
        
        # Interpolate reference to high density for smooth positioning
        from scipy.spatial import cKDTree
        t_old = np.linspace(0, 1, len(ref_xs))
        t_new = np.linspace(0, 1, 4000)
        ref_xs_dense = np.interp(t_new, t_old, ref_xs)
        ref_ys_dense = np.interp(t_new, t_old, ref_ys)
        ref_dist_dense = np.interp(t_new, t_old, ref_dist)
        
        # Build KD-Tree for fast position lookups
        ref_tree = cKDTree(np.column_stack((ref_xs_dense, ref_ys_dense)))
        
        # Cumulative distance along reference
        diffs = np.sqrt(np.diff(ref_xs_dense)**2 + np.diff(ref_ys_dense)**2)
        ref_cumdist = np.concatenate(([0.0], np.cumsum(diffs)))
        ref_total = float(ref_cumdist[-1])
        
        # Compute normals (for pit lane offset)
        dx = np.gradient(ref_xs_dense)
        dy = np.gradient(ref_ys_dense)
        norm = np.sqrt(dx**2 + dy**2)
        norm[norm == 0] = 1.0
        ref_nx = -dy / norm
        ref_ny = dx / norm
        
    except Exception as e:
        print(f"Safety Car: Failed to build reference polyline: {e}")
        return

    # Identify SC deployment periods from track_statuses
    sc_periods = []
    for status in track_statuses:
        if str(status.get("status", "")) == "4":
            sc_periods.append({
                "start_time": status["start_time"],
                "end_time": status.get("end_time"),
            })
    
    if not sc_periods:
        print("Safety Car: No SC periods found in this session")
        return

    print(f"Safety Car: Found {len(sc_periods)} SC deployment period(s)")
    
    # ---- Constants ----
    # Deployment: SC exits pit, cruises on track at realistic SC speed, waits for leader
    DEPLOY_PIT_EXIT_DURATION = 4.0   # seconds to transition from pitlane to track surface
    DEPLOY_CRUISE_SPEED = 55.0       # m/s (~200 km/h, realistic safety car speed)
    DEPLOY_TOTAL_MAX = 120.0         # max seconds for deploying phase before forcing on_track
    
    # On track
    SC_OFFSET_METERS = 150           # how far ahead of the first car the SC drives
    
    # Returning: SC accelerates away, then enters pitlane
    RETURN_ACCEL_DURATION = 5.0      # seconds SC accelerates ahead of the field
    RETURN_ACCEL_SPEED = 400.0       # m/s (fast, to pull away from field)
    RETURN_PIT_ENTER_DURATION = 3.0  # seconds to transition from track into pitlane
    RETURN_TOTAL = RETURN_ACCEL_DURATION + RETURN_PIT_ENTER_DURATION  # total return phase
    
    # Pit lane entry/exit positions
    # Use a point ~10% of track ahead of start/finish as pit exit, and
    # a point ~90% as pit entry (approximates most circuits)
    PIT_OFFSET_INWARD = 400  # metres offset inward from track to simulate pitlane
    
    def _pos_at_dist(dist_m):
        """Get (x, y) on the reference line at a given cumulative distance (wraps around)."""
        d = dist_m % ref_total
        idx = int(np.searchsorted(ref_cumdist, d))
        idx = min(idx, len(ref_xs_dense) - 1)
        return float(ref_xs_dense[idx]), float(ref_ys_dense[idx])
    
    def _idx_at_dist(dist_m):
        """Get the reference index at a given cumulative distance (wraps around)."""
        d = dist_m % ref_total
        idx = int(np.searchsorted(ref_cumdist, d))
        return min(idx, len(ref_xs_dense) - 1)
    
    def _dist_of_point(x, y):
        """Project a point onto the reference line and return cumulative distance."""
        _, idx = ref_tree.query([x, y])
        return float(ref_cumdist[int(idx)])

    # Pit exit position: ~5% of track from start, offset inward
    pit_exit_track_dist = ref_total * 0.05
    pit_exit_idx = _idx_at_dist(pit_exit_track_dist)
    pit_exit_track_x, pit_exit_track_y = _pos_at_dist(pit_exit_track_dist)
    pit_exit_pit_x = float(ref_xs_dense[pit_exit_idx] + ref_nx[pit_exit_idx] * PIT_OFFSET_INWARD)
    pit_exit_pit_y = float(ref_ys_dense[pit_exit_idx] + ref_ny[pit_exit_idx] * PIT_OFFSET_INWARD)
    
    # Pit entry position: ~95% of track from start, offset inward
    pit_entry_track_dist = ref_total * 0.95
    pit_entry_idx = _idx_at_dist(pit_entry_track_dist)
    pit_entry_track_x, pit_entry_track_y = _pos_at_dist(pit_entry_track_dist)
    pit_entry_pit_x = float(ref_xs_dense[pit_entry_idx] + ref_nx[pit_entry_idx] * PIT_OFFSET_INWARD)
    pit_entry_pit_y = float(ref_ys_dense[pit_entry_idx] + ref_ny[pit_entry_idx] * PIT_OFFSET_INWARD)

    def get_first_car_behind_sc(frame, sc_dist_on_track):
        """
        Find the car that is closest behind the SC on the track.
        This might be a lapped car, not necessarily the race leader.
        Returns (code, x, y, track_dist) or (None, None, None, None).
        """
        drivers = frame.get("drivers", {})
        if not drivers:
            return None, None, None, None
        
        best_code = None
        best_gap = float('inf')  # smallest positive gap = closest behind
        best_x, best_y, best_dist = None, None, None
        
        for code, pos in drivers.items():
            dx, dy = pos.get("x", 0.0), pos.get("y", 0.0)
            d_track = _dist_of_point(dx, dy)
            
            # Gap = how far behind the SC this car is (on track, wrapping)
            gap = (sc_dist_on_track - d_track) % ref_total
            
            # We want the car with the smallest positive gap (closest behind SC)
            # Ignore cars that are essentially at the same position (< 10m)
            if 10.0 < gap < best_gap:
                best_gap = gap
                best_code = code
                best_x = dx
                best_y = dy
                best_dist = d_track
        
        return best_code, best_x, best_y, best_dist

    def get_leader_info(frame):
        """Get the race leader's (code, x, y, track_dist, total_progress)."""
        drivers = frame.get("drivers", {})
        if not drivers:
            return None, None, None, None, None
        best_code = None
        best_progress = -1
        for code, pos in drivers.items():
            lap = pos.get("lap", 1)
            dist = pos.get("dist", 0)
            progress = (max(lap, 1) - 1) * ref_total + dist
            if progress > best_progress:
                best_progress = progress
                best_code = code
        if best_code:
            px = drivers[best_code]["x"]
            py = drivers[best_code]["y"]
            return best_code, px, py, _dist_of_point(px, py), best_progress
        return None, None, None, None, None

    # ---- Per-SC-period state tracking ----
    # We process frames sequentially so we can accumulate SC position state
    
    # For each SC period, track the SC's cumulative position on the track
    sc_state = {}  # keyed by sc_period index
    
    for fi, frame in enumerate(frames):
        t = frame["t"]
        
        # Check if current time falls in any SC period
        active_sc = None
        active_sc_idx = None
        for sci, sc in enumerate(sc_periods):
            sc_start = sc["start_time"]
            sc_end = sc.get("end_time")
            effective_end = (sc_end + RETURN_TOTAL) if sc_end else None
            
            if t >= sc_start and (effective_end is None or t < effective_end):
                active_sc = sc
                active_sc_idx = sci
                break
        
        if active_sc is None:
            frame["safety_car"] = None
            continue
        
        sc_start = active_sc["start_time"]
        sc_end = active_sc.get("end_time")
        elapsed = t - sc_start
        
        # Initialize state for this SC period if not already done
        if active_sc_idx not in sc_state:
            sc_state[active_sc_idx] = {
                "track_dist": pit_exit_track_dist,  # SC starts at pit exit on track
                "caught_up": False,                  # has the leader caught the SC?
                "last_t": t,
                "return_start_dist": None,           # track dist when return phase begins
                "prev_leader_dist": None,            # for tracking leader speed
            }
        
        state = sc_state[active_sc_idx]
        dt_frame = max(0.0, t - state["last_t"])
        state["last_t"] = t
        
        # ========================
        # PHASE 1: DEPLOYING
        # ========================
        if elapsed < DEPLOY_PIT_EXIT_DURATION:
            # Sub-phase 1a: SC transitioning from pitlane onto the track surface
            phase = "deploying"
            progress = elapsed / DEPLOY_PIT_EXIT_DURATION  # 0 -> 1
            alpha = progress
            
            # Smooth interpolation from pit exit (off-track) to pit exit (on-track)
            # Use ease-in-out for smooth animation
            smooth_t = 0.5 - 0.5 * np.cos(progress * np.pi)  # smoothstep
            sc_x = pit_exit_pit_x + smooth_t * (pit_exit_track_x - pit_exit_pit_x)
            sc_y = pit_exit_pit_y + smooth_t * (pit_exit_track_y - pit_exit_pit_y)
            
        elif elapsed < DEPLOY_PIT_EXIT_DURATION + DEPLOY_TOTAL_MAX and not state["caught_up"]:
            # Sub-phase 1b: SC cruises on track at a realistic pace,
            # slightly slower than the field so the leader catches up naturally.
            phase = "deploying"
            alpha = 1.0
            
            # Estimate the leader's actual speed from telemetry position changes
            leader_code, _, _, leader_dist, _ = get_leader_info(frame)
            
            if leader_code is not None:
                # Track leader speed by comparing consecutive positions
                if state["prev_leader_dist"] is not None and dt_frame > 0:
                    leader_moved = leader_dist - state["prev_leader_dist"]
                    # Handle wrapping around start/finish line
                    if leader_moved > ref_total / 2:
                        leader_moved -= ref_total
                    elif leader_moved < -ref_total / 2:
                        leader_moved += ref_total
                    leader_speed = abs(leader_moved) / dt_frame
                else:
                    leader_speed = 55.0  # default ~200 km/h on first frame
                state["prev_leader_dist"] = leader_dist
                
                # SC cruises at 80% of the leader's speed
                # This guarantees the leader always catches up, but SC is still moving
                sc_speed = max(20.0, min(leader_speed * 0.8, 60.0))  # clamp 20-60 m/s
            else:
                sc_speed = DEPLOY_CRUISE_SPEED  # fallback
            
            # Advance SC along the track
            state["track_dist"] += sc_speed * dt_frame
            state["track_dist"] = state["track_dist"] % ref_total
            
            sc_x, sc_y = _pos_at_dist(state["track_dist"])
            
            # Check if the LEADER has caught up behind the SC
            if leader_code is not None:
                # How far ahead is the SC of the leader? (forward direction on track)
                gap_ahead = (state["track_dist"] - leader_dist) % ref_total
                
                # Leader is close behind the SC -> transition to on_track
                if gap_ahead <= SC_OFFSET_METERS + 50:
                    state["caught_up"] = True
                    
        elif sc_end is not None and t >= sc_end:
            # ========================  
            # PHASE 3: RETURNING
            # ========================
            return_elapsed = t - sc_end
            
            if state["return_start_dist"] is None:
                state["return_start_dist"] = state["track_dist"]
            
            if return_elapsed < RETURN_ACCEL_DURATION:
                # Sub-phase 3a: SC accelerates away from the field
                phase = "returning"
                alpha = 1.0
                
                # SC speeds up along the track, pulling away from the pack
                state["track_dist"] += RETURN_ACCEL_SPEED * dt_frame
                state["track_dist"] = state["track_dist"] % ref_total
                
                sc_x, sc_y = _pos_at_dist(state["track_dist"])
                
            else:
                # Sub-phase 3b: SC transitions from track surface into the pitlane
                phase = "returning"
                pit_enter_elapsed = return_elapsed - RETURN_ACCEL_DURATION
                progress = min(1.0, pit_enter_elapsed / RETURN_PIT_ENTER_DURATION)
                alpha = max(0.0, 1.0 - progress)
                
                # Get SC's current track position (frozen at end of accel phase)
                # and interpolate toward pit entry point
                track_x, track_y = _pos_at_dist(state["track_dist"])
                
                smooth_t = 0.5 - 0.5 * np.cos(progress * np.pi)  # smoothstep
                sc_x = track_x + smooth_t * (pit_entry_pit_x - track_x)
                sc_y = track_y + smooth_t * (pit_entry_pit_y - track_y)
        else:
            # ========================
            # PHASE 2: ON TRACK
            # ========================
            # SC leads the race, positioned ahead of the race leader.
            # Uses total race progress (laps + distance) to find the leader,
            # which avoids the start/finish line wrapping bug.
            phase = "on_track"
            alpha = 1.0
            state["caught_up"] = True  # ensure we mark as caught up
            
            # Find the RACE LEADER (by total progress: laps * track_length + distance)
            # This is robust across the start/finish line because it uses lap count.
            leader_code, leader_x, leader_y, leader_dist, _ = get_leader_info(frame)
            
            if leader_code is not None:
                # Position SC directly at a fixed offset ahead of the leader.
                # Since the leader moves smoothly frame-by-frame, the SC follows
                # smoothly as well — like a shadow but ahead.
                target_dist = (leader_dist + SC_OFFSET_METERS) % ref_total
                state["track_dist"] = target_dist
            else:
                # Fallback: no leader found, advance slowly
                state["track_dist"] += 100.0 * dt_frame
                state["track_dist"] = state["track_dist"] % ref_total
            
            sc_x, sc_y = _pos_at_dist(state["track_dist"])
        
        frame["safety_car"] = {
            "x": round(sc_x, 2),
            "y": round(sc_y, 2),
            "phase": phase,
            "alpha": round(alpha, 3),
        }

    # Count frames with SC data
    sc_frame_count = sum(1 for f in frames if f.get("safety_car") is not None)
    print(f"Safety Car: Computed positions for {sc_frame_count} frames")


def get_race_telemetry(session, session_type="R"):
    event_name = str(session).replace(" ", "_")
    cache_suffix = "sprint" if session_type == "S" else "race"

    # Check if this data has already been computed

    try:
        if "--refresh-data" not in sys.argv:
            with open(
                f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "rb"
            ) as f:
                frames = pickle.load(f)
                print(f"Loaded precomputed {cache_suffix} telemetry data.")
                print("The replay should begin in a new window shortly!")
                return frames
    except FileNotFoundError:
        pass  # Need to compute from scratch

    drivers = session.drivers

    driver_codes = {num: session.get_driver(num)["Abbreviation"] for num in drivers}

    driver_data = {}

    global_t_min = None
    global_t_max = None

    max_lap_number = 0

    # 1. Get all of the drivers telemetry data using multiprocessing
    # Prepare arguments for parallel processing
    print(f"Processing {len(drivers)} drivers in parallel...")
    driver_args = [
        (driver_no, session, driver_codes[driver_no]) for driver_no in drivers
    ]

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
    max_tyre_life_map = {}

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
            data["tyre_life"][order],
            data["speed"][order],
            data["gear"][order],
            data["drs"][order],
            data["throttle"][order],
            data["brake"][order],
        ]

        resampled = [np.interp(timeline, t_sorted, arr) for arr in arrays_to_resample]
        x_resampled, y_resampled, dist_resampled, rel_dist_resampled, lap_resampled, \
        tyre_resampled, tyre_life_resampled, speed_resampled, gear_resampled, drs_resampled, throttle_resampled, brake_resampled = resampled
 
        resampled_data[code] = {
            "t": timeline,
            "x": x_resampled,
            "y": y_resampled,
            "dist": dist_resampled,  # race distance (metres since Lap 1 start)
            "rel_dist": rel_dist_resampled,
            "lap": lap_resampled,
            "tyre": tyre_resampled,
            "tyre_life": tyre_life_resampled,
            "speed": speed_resampled,
            "gear": gear_resampled,
            "drs": drs_resampled,
            "throttle": throttle_resampled,
            "brake": brake_resampled,
        }

        for t_int in np.unique(tyre_resampled):
            mask = tyre_resampled == t_int
            c_max = np.nanmax(tyre_life_resampled[mask])
            if not np.isnan(c_max):
                max_tyre_life_map[int(t_int)] = max(max_tyre_life_map.get(int(t_int), 1), int(c_max))

    # 4. Incorporate track status data into the timeline (for safety car, VSC, etc.)

    track_status = session.track_status

    formatted_track_statuses = []

    for status in track_status.to_dict("records"):
        seconds = timedelta.total_seconds(status["Time"])

        start_time = seconds - global_t_min  # Shift to match timeline
        end_time = None

        # Set the end time of the previous status

        if formatted_track_statuses:
            formatted_track_statuses[-1]["end_time"] = start_time

        formatted_track_statuses.append(
            {
                "status": status["Status"],
                "start_time": start_time,
                "end_time": end_time,
            }
        )

    # 4.1. Resample weather data onto the same timeline for playback
    weather_resampled = None
    weather_df = getattr(session, "weather_data", None)
    if weather_df is not None and not weather_df.empty:
        try:
            weather_times = (
                weather_df["Time"].dt.total_seconds().to_numpy() - global_t_min
            )
            if len(weather_times) > 0:
                order = np.argsort(weather_times)
                weather_times = weather_times[order]

                def _maybe_get(name):
                    return (
                        weather_df[name].to_numpy()[order]
                        if name in weather_df
                        else None
                    )

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
                rainfall = (
                    _resample(rainfall_raw.astype(float))
                    if rainfall_raw is not None
                    else None
                )

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
                "tyre_life": float(d["tyre_life"][i]),
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
        snapshot.sort(key=lambda r: (r.get("lap", 0), r["dist"]), reverse=True)

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
                "tyre_life": car["tyre_life"],
                "position": position,
                "speed": car["speed"],
                "gear": car["gear"],
                "drs": car["drs"],
                "throttle": car["throttle"],
                "brake": car["brake"],
            }

        weather_snapshot = {}
        if weather_resampled:
            try:
                wt = weather_resampled
                rain_val = wt["rainfall"][i] if wt.get("rainfall") is not None else 0.0
                weather_snapshot = {
                    "track_temp": float(wt["track_temp"][i])
                    if wt.get("track_temp") is not None
                    else None,
                    "air_temp": float(wt["air_temp"][i])
                    if wt.get("air_temp") is not None
                    else None,
                    "humidity": float(wt["humidity"][i])
                    if wt.get("humidity") is not None
                    else None,
                    "wind_speed": float(wt["wind_speed"][i])
                    if wt.get("wind_speed") is not None
                    else None,
                    "wind_direction": float(wt["wind_direction"][i])
                    if wt.get("wind_direction") is not None
                    else None,
                    "rain_state": "RAINING" if rain_val and rain_val >= 0.5 else "DRY",
                }
            except Exception as e:
                print(f"Failed to attach weather data to frame {i}: {e}")

        frame_payload = {
            "t": round(t, 3),
            "lap": leader_lap,  # leader's lap at this time
            "drivers": frame_data,
        }
        if weather_snapshot:
            frame_payload["weather"] = weather_snapshot

        frames.append(frame_payload)

    # 5d. Compute Safety Car positions for each frame
    _compute_safety_car_positions(frames, formatted_track_statuses, session)

    # 5e. Compute fastest lap holder for each frame
    _compute_fastest_lap_holders(frames, session, global_t_min)

    print("completed telemetry extraction...")
    print("Saving to cache file...")
    # If computed_data/ directory doesn't exist, create it
    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    # Save using pickle (10-100x faster than JSON)
    with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "wb") as f:
        pickle.dump({
            "frames": frames,
            "driver_colors": get_driver_colors(session),
            "track_statuses": formatted_track_statuses,
            "total_laps": int(max_lap_number),
            "max_tyre_life": max_tyre_life_map,
        }, f, protocol=pickle.HIGHEST_PROTOCOL)

    print("Saved Successfully!")
    print("The replay should begin in a new window shortly")
    return {
        "frames": frames,
        "driver_colors": get_driver_colors(session),
        "track_statuses": formatted_track_statuses,
        "total_laps": int(max_lap_number),
        "max_tyre_life": max_tyre_life_map,
    }


def get_qualifying_results(session):
    # Extract the qualifying results and return a list of the drivers, their positions and their lap times in each qualifying segment

    results = session.results

    qualifying_data = []

    for _, row in results.iterrows():
        driver_code = row["Abbreviation"]
        # Skip drivers with no position (DNF/DNS/no lap data)
        if pd.isna(row["Position"]):
            continue
        position = int(row["Position"])
        q1_time = row["Q1"]
        q2_time = row["Q2"]
        q3_time = row["Q3"]
        full_name = row["FullName"]

        # Convert pandas Timedelta objects to seconds (or None if NaT)
        def convert_time_to_seconds(time_val) -> str:
            if pd.isna(time_val):
                return None
            return str(time_val.total_seconds())

        qualifying_data.append(
            {
                "code": driver_code,
                "full_name": full_name,
                "position": position,
                "color": get_driver_colors(session).get(driver_code, (128, 128, 128)),
                "Q1": convert_time_to_seconds(q1_time),
                "Q2": convert_time_to_seconds(q2_time),
                "Q3": convert_time_to_seconds(q3_time),
            }
        )
    return qualifying_data


def get_driver_quali_telemetry(session, driver_code: str, quali_segment: str):
    # Split Q1/Q2/Q3 sections
    q1, q2, q3 = session.laps.split_qualifying_sessions()

    segments = {"Q1": q1, "Q2": q2, "Q3": q3}

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
    if (
        telemetry is None
        or telemetry.empty
        or "Time" not in telemetry
        or len(telemetry) == 0
    ):
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
    timeline = np.arange(global_t_min, global_t_max + DT / 2, DT) - global_t_min

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
    throttle_resampled = np.round(
        np.interp(timeline, t_sorted_unique, throttle_sorted), 1
    )
    brake_resampled = np.round(np.interp(timeline, t_sorted_unique, brake_sorted), 1)
    drs_resampled = np.interp(timeline, t_sorted_unique, drs_sorted)

    # Make sure that braking is between 0 and 100 so that it matches the throttle scale

    brake_resampled = brake_resampled * 100.0

    # Forward-fill / step sampling for discrete fields (gear)
    idxs = np.searchsorted(t_sorted_unique, timeline, side="right") - 1
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

    for status in track_status.to_dict("records"):
        seconds = timedelta.total_seconds(status["Time"])

        start_time = seconds - global_t_min  # Shift to match timeline
        end_time = None

        # Set the end time of the previous status
        if formatted_track_statuses:
            formatted_track_statuses[-1]["end_time"] = start_time

        formatted_track_statuses.append(
            {
                "status": status["Status"],
                "start_time": start_time,
                "end_time": end_time,
            }
        )

    # 4.1. Resample weather data onto the same timeline for playback
    weather_resampled = None
    weather_df = getattr(session, "weather_data", None)
    if weather_df is not None and not weather_df.empty:
        try:
            weather_times = (
                weather_df["Time"].dt.total_seconds().to_numpy() - global_t_min
            )
            if len(weather_times) > 0:
                order_w = np.argsort(weather_times)
                weather_times = weather_times[order_w]

                def _maybe_get(name):
                    return (
                        weather_df[name].to_numpy()[order_w]
                        if name in weather_df
                        else None
                    )

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
                rainfall = (
                    _resample(rainfall_raw.astype(float))
                    if rainfall_raw is not None
                    else None
                )

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
                    "track_temp": float(wt["track_temp"][i])
                    if wt.get("track_temp") is not None
                    else None,
                    "air_temp": float(wt["air_temp"][i])
                    if wt.get("air_temp") is not None
                    else None,
                    "humidity": float(wt["humidity"][i])
                    if wt.get("humidity") is not None
                    else None,
                    "wind_speed": float(wt["wind_speed"][i])
                    if wt.get("wind_speed") is not None
                    else None,
                    "wind_direction": float(wt["wind_direction"][i])
                    if wt.get("wind_direction") is not None
                    else None,
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
                lap_drs_zones.append(
                    {
                        "zone_start": float(resampled_data["dist"][i]),
                        "zone_end": None,
                    }
                )
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
            },
        }
        if weather_snapshot:
            frame_payload["weather"] = weather_snapshot

        frames.append(frame_payload)

    # Set the time of the final frame to the exact lap time

    frames[-1]["t"] = round(parse_time_string(str(fastest_lap["LapTime"])), 3)

    sector_times = {
        "sector1": parse_time_string(str(fastest_lap.get("Sector1Time")))
        if pd.notna(fastest_lap.get("Sector1Time"))
        else None,
        "sector2": parse_time_string(str(fastest_lap.get("Sector2Time")))
        if pd.notna(fastest_lap.get("Sector2Time"))
        else None,
        "sector3": parse_time_string(str(fastest_lap.get("Sector3Time")))
        if pd.notna(fastest_lap.get("Sector3Time"))
        else None,
    }

    # Extract tyre compound from the lap
    compound = (
        str(fastest_lap.get("Compound", "UNKNOWN"))
        if pd.notna(fastest_lap.get("Compound"))
        else "UNKNOWN"
    )
    compound_number = get_tyre_compound_int(compound)
    return {
        "frames": frames,
        "track_statuses": formatted_track_statuses,
        "drs_zones": lap_drs_zones,
        "max_speed": max_speed,
        "min_speed": min_speed,
        "sector_times": sector_times,
        "compound": compound_number,
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
            segment_telemetry = get_driver_quali_telemetry(
                session, driver_code, segment
            )
            driver_telemetry_data[segment] = segment_telemetry

            # Update global max/min speed
            if segment_telemetry["max_speed"] > max_speed:
                max_speed = segment_telemetry["max_speed"]
            if segment_telemetry["min_speed"] < min_speed or min_speed == 0.0:
                min_speed = segment_telemetry["min_speed"]

        except ValueError:
            driver_telemetry_data[segment] = {"frames": [], "track_statuses": []}

    print(
        f"Finished processing qualifying telemetry for driver: {driver_code}, {session.get_driver(driver_code)['FullName']},"
    )
    return {
        "driver_code": driver_code,
        "driver_full_name": session.get_driver(driver_code)["FullName"],
        "driver_telemetry_data": driver_telemetry_data,
        "max_speed": max_speed,
        "min_speed": min_speed,
    }


def get_quali_telemetry(session, session_type="Q"):
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

    event_name = str(session).replace(" ", "_")
    cache_suffix = "sprintquali" if session_type == "SQ" else "quali"

    # Check if this data has already been computed
    try:
        if "--refresh-data" not in sys.argv:
            with open(
                f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "rb"
            ) as f:
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
        num: session.get_driver(num)["Abbreviation"] for num in session.drivers
    }

    telemetry_data = {}

    driver_args = [(session, driver_codes[driver_no]) for driver_no in session.drivers]

    print(f"Processing {len(session.drivers)} drivers in parallel...")

    num_processes = min(cpu_count(), len(session.drivers))

    with Pool(processes=num_processes) as pool:
        results = pool.map(_process_quali_driver, driver_args)
    for result in results:
        driver_code = result["driver_code"]
        telemetry_data[driver_code] = {
            "full_name": result["driver_full_name"],
            **result["driver_telemetry_data"],
        }

        if result["max_speed"] > max_speed:
            max_speed = result["max_speed"]
        if result["min_speed"] < min_speed or min_speed == 0.0:
            min_speed = result["min_speed"]

    # Save to the compute_data directory

    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "wb") as f:
        pickle.dump(
            {
                "results": qualifying_results,
                "telemetry": telemetry_data,
                "max_speed": max_speed,
                "min_speed": min_speed,
            },
            f,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    return {
        "results": qualifying_results,
        "telemetry": telemetry_data,
        "max_speed": max_speed,
        "min_speed": min_speed,
    }


def get_race_weekends_by_year(year):
    """Returns a list of race weekends for a given year."""
    enable_cache()
    schedule = fastf1.get_event_schedule(year)
    weekends = []
    for _, event in schedule.iterrows():
        if event.is_testing():
            continue

        session_dates = {}
        for i in range(1, 6):
            session_name = event.get(f"Session{i}")
            session_date = event.get(f"Session{i}Date")
            if session_name and pd.notna(session_date):
                session_dates[str(session_name)] = session_date.isoformat()

        weekends.append(
            {
                "round_number": event["RoundNumber"],
                "event_name": event["EventName"],
                "date": str(event["EventDate"].date()),
                "country": event["Country"],
                "type": event["EventFormat"],
                "session_dates": session_dates,
            }
        )
    return weekends

def get_race_weekends_by_place(place):
    """Returns a list of past n race weekends for a given place."""
    enable_cache()
    place=place.lower().strip()
    weekends=[]
    current_year=date.today().year

    for year in range(2018,current_year): #Edit according to data availability (current data till last year)
        try:
            schedule=fastf1.get_event_schedule(year)
        except Exception:
            continue

        for _, event in schedule.iterrows():
            if event.is_testing():
                continue

            event_name=str(event["EventName"]).strip().lower()
            
            if place==event_name:
                weekends.append({
                    "round_number": event["RoundNumber"],
                    "event_name": event["EventName"],
                    "date": str(event["EventDate"].date()),
                    "country": event["Country"],
                    "year": int(event["EventDate"].date().year),
                    "type": event["EventFormat"],
                })
    return weekends

def get_all_unique_race_names(start_year=2018, end_year=2025): #update as necessary
    "Return a list of all unique race locations"
    enable_cache()
    race_names=set()
    
    for year in range(start_year, end_year+1):
        try:
            schedule=fastf1.get_event_schedule(year)
        except Exception:
            continue

        for _,event in schedule.iterrows():
            if event.is_testing():
                continue

            name=str(event["EventName"]).strip()
            race_names.add(name)

    return sorted(race_names)

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
    sprint_name = "sprint_qualifying"
    if year == 2023:
        sprint_name = "sprint_shootout"
    if year in [2021, 2022]:
        sprint_name = "sprint"
    sprints = schedule[schedule["EventFormat"] == sprint_name]
    if sprints.empty:
        print(f"No sprint races found for {year}.")
    else:
        for _, event in sprints.iterrows():
            print(f"{event['RoundNumber']}: {event['EventName']}")
