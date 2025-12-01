import os
import fastf1
import fastf1.plotting
import numpy as np
import pickle
import pandas as pd
from datetime import timedelta

try:
    from src.lib.tyres import get_tyre_compound_int
except ImportError:
    def get_tyre_compound_int(compound):
        return 0

    # 1. FastF1 원본 데이터 캐시
fastf1.Cache.enable_cache('.fastf1-cache')

# 2. 가공된 데이터 캐시 경로
PROCESSED_CACHE_DIR = '.processed_cache'
if not os.path.exists(PROCESSED_CACHE_DIR):
    os.makedirs(PROCESSED_CACHE_DIR)

FPS = 25
DT = 1 / FPS


def load_race_session(year, round_number):
    session = fastf1.get_session(year, round_number, 'R')
    session.load(telemetry=True, laps=True, weather=False, messages=True)
    return session


def get_driver_colors(session):
    try:
        color_mapping = fastf1.plotting.get_driver_color_mapping(session)
        rgb_colors = {}
        for driver, hex_color in color_mapping.items():
            hex_color = hex_color.lstrip('#')
            rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
            rgb_colors[driver] = rgb
        return rgb_colors
    except:
        return {}


def get_race_telemetry(session, progress_callback=None):
    event_name = f"{session.event.year}_{session.event.RoundNumber}_{session.event.EventName.replace(' ', '_')}"
    # 로직 변경 반영 (v5)
    cache_file_path = os.path.join(PROCESSED_CACHE_DIR, f"{event_name}_v5.pkl")

    # 캐시 확인
    if os.path.exists(cache_file_path):
        print(f"Found processed cache: {cache_file_path}")
        if progress_callback:
            progress_callback(0.5, "Loading from local cache (Fast)...")
        try:
            with open(cache_file_path, 'rb') as f:
                data = pickle.load(f)
            if progress_callback:
                progress_callback(1.0, "Done!")
            return data
        except Exception as e:
            print(f"Cache load failed: {e}")

    # --- 데이터 처리 ---
    drivers = session.drivers
    total_drivers = len(drivers)
    driver_codes = {num: session.get_driver(num)["Abbreviation"] for num in drivers}

    # 그리드 정보 가져오기
    driver_grids = {}
    try:
        for driver_no in drivers:
            grid_pos = session.results.loc[session.results['DriverNumber'] == driver_no, 'GridPosition'].values
            if len(grid_pos) > 0 and grid_pos[0] > 0:
                driver_grids[driver_no] = grid_pos[0]
            else:
                driver_grids[driver_no] = 20.0
    except:
        for i, d in enumerate(drivers): driver_grids[d] = i + 1

    driver_data = {}
    global_t_min = None
    global_t_max = None

    # GapToLeader 안전 처리
    if 'GapToLeader' not in session.laps.columns:
        session.laps['GapToLeader'] = pd.Timedelta(seconds=0)
    else:
        session.laps['GapToLeader'] = session.laps['GapToLeader'].fillna(pd.Timedelta(seconds=0))

    # 표준 랩 길이 (GPS 보정용)
    try:
        fastest_lap = session.laps.pick_fastest()
        if fastest_lap is not None:
            telemetry = fastest_lap.get_telemetry()
            REF_LAP_LENGTH = telemetry['Distance'].max()
        else:
            REF_LAP_LENGTH = 5300.0
    except:
        REF_LAP_LENGTH = 5300.0

    for i, driver_no in enumerate(drivers):
        code = driver_codes[driver_no]
        current_count = i + 1
        grid_pos = driver_grids.get(driver_no, 20.0)

        if progress_callback:
            percent = (current_count / total_drivers)
            progress_callback(percent, f"Processing {code} ({current_count}/{total_drivers})")

        print(f"Getting telemetry for {code}")

        laps_driver = session.laps.pick_drivers(driver_no)
        if laps_driver.empty: continue

        t_all = []
        x_all = []
        y_all = []
        speed_all = []
        gear_all = []
        drs_all = []
        throttle_all = []
        brake_all = []
        gap_all = []
        tyre_life_all = []

        race_dist_all = []
        rel_dist_all = []
        lap_numbers = []
        tyre_compounds = []

        for _, lap in laps_driver.iterlaps():
            lap_tel = lap.get_telemetry()
            if lap_tel.empty: continue

            t_lap = lap_tel["SessionTime"].dt.total_seconds().to_numpy()
            x_lap = lap_tel["X"].to_numpy()
            y_lap = lap_tel["Y"].to_numpy()
            speed_lap = lap_tel["Speed"].to_numpy()
            gear_lap = lap_tel["nGear"].to_numpy()
            drs_lap = lap_tel["DRS"].to_numpy()
            throttle_lap = lap_tel["Throttle"].to_numpy()
            brake_lap = lap_tel["Brake"].to_numpy().astype(float)

            try:
                gap_val = lap.GapToLeader
                gap_seconds = 0.0 if pd.isna(gap_val) else gap_val.total_seconds()
            except:
                gap_seconds = 0.0

            gap_lap = np.full_like(t_lap, gap_seconds)
            tyre_life_lap = np.full_like(t_lap, lap.TyreLife if not pd.isna(lap.TyreLife) else 0)

            # GPS 보정 거리 계산
            rel_dist = lap_tel["RelativeDistance"].to_numpy()
            corrected_dist_lap = (lap.LapNumber - 1) * REF_LAP_LENGTH + (rel_dist * REF_LAP_LENGTH)

            t_all.append(t_lap)
            x_all.append(x_lap)
            y_all.append(y_lap)
            speed_all.append(speed_lap)
            gear_all.append(gear_lap)
            drs_all.append(drs_lap)
            throttle_all.append(throttle_lap)
            brake_all.append(brake_lap)
            gap_all.append(gap_lap)
            tyre_life_all.append(tyre_life_lap)

            race_dist_all.append(corrected_dist_lap)
            rel_dist_all.append(rel_dist)
            lap_numbers.append(np.full_like(t_lap, lap.LapNumber))
            tyre_compounds.append(np.full_like(t_lap, get_tyre_compound_int(lap.Compound)))

        if not t_all: continue

        t_all = np.concatenate(t_all)
        x_all = np.concatenate(x_all)
        y_all = np.concatenate(y_all)
        speed_all = np.concatenate(speed_all)
        gear_all = np.concatenate(gear_all)
        drs_all = np.concatenate(drs_all)
        throttle_all = np.concatenate(throttle_all)
        brake_all = np.concatenate(brake_all)
        gap_all = np.concatenate(gap_all)
        tyre_life_all = np.concatenate(tyre_life_all)
        race_dist_all = np.concatenate(race_dist_all)
        rel_dist_all = np.concatenate(rel_dist_all)
        lap_numbers = np.concatenate(lap_numbers)
        tyre_compounds = np.concatenate(tyre_compounds)

        order = np.argsort(t_all)
        driver_data[code] = {
            "t": t_all[order],
            "x": x_all[order],
            "y": y_all[order],
            "speed": speed_all[order],
            "gear": gear_all[order],
            "drs": drs_all[order],
            "throttle": throttle_all[order],
            "brake": brake_all[order],
            "gap": gap_all[order],
            "tyre_life": tyre_life_all[order],
            "dist": race_dist_all[order],
            "rel_dist": rel_dist_all[order],
            "lap": lap_numbers[order],
            "tyre": tyre_compounds[order],
            "grid": grid_pos
        }

        t_min = t_all.min()
        t_max = t_all.max()
        global_t_min = t_min if global_t_min is None else min(global_t_min, t_min)
        global_t_max = t_max if global_t_max is None else max(global_t_max, t_max)

    if progress_callback:
        progress_callback(1.0, "Finalizing Data...")

    timeline = np.arange(global_t_min, global_t_max, DT) - global_t_min
    resampled_data = {}

    for code, data in driver_data.items():
        t = data["t"] - global_t_min
        resampled_data[code] = {
            "t": timeline,
            "x": np.interp(timeline, t, data["x"]),
            "y": np.interp(timeline, t, data["y"]),
            "speed": np.interp(timeline, t, data["speed"]),
            "gear": np.interp(timeline, t, data["gear"]),
            "drs": np.interp(timeline, t, data["drs"]),
            "throttle": np.interp(timeline, t, data["throttle"]),
            "brake": np.interp(timeline, t, data["brake"]),
            "gap": np.interp(timeline, t, data["gap"]),
            "tyre_life": np.interp(timeline, t, data["tyre_life"]),
            "dist": np.interp(timeline, t, data["dist"]),
            "rel_dist": np.interp(timeline, t, data["rel_dist"]),
            "lap": np.interp(timeline, t, data["lap"]),
            "tyre": np.interp(timeline, t, data["tyre"]),
            "grid": data["grid"]
        }

    race_control_messages = []
    if hasattr(session, 'race_control_messages') and session.race_control_messages is not None:
        rcm = session.race_control_messages
        for _, row in rcm.iterrows():
            msg_time = (row['Time'].total_seconds() if isinstance(row['Time'], timedelta) else 0) - global_t_min
            race_control_messages.append({
                'time': msg_time,
                'category': row['Category'],
                'message': row['Message'],
                'flag': row['Flag'] if 'Flag' in row else None
            })

    track_status = session.track_status
    formatted_track_statuses = []
    if track_status is not None and not track_status.empty:
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

    frames = []
    for i, t in enumerate(timeline):
        # 선두 거리 계산
        current_dists = [d["dist"][i] for d in resampled_data.values()]
        leader_dist = max(current_dists) if current_dists else 0

        snapshot = []
        for code, d in resampled_data.items():
            dist = float(d["dist"][i])
            speed = float(d["speed"][i])

            dist_diff = leader_dist - dist
            speed_ms = speed / 3.6
            if speed_ms < 10: speed_ms = 10
            gap_seconds = dist_diff / speed_ms

            snapshot.append({
                "code": code,
                "dist": dist,
                "x": float(d["x"][i]),
                "y": float(d["y"][i]),
                "speed": speed,
                "gear": int(round(d["gear"][i])),
                "drs": int(round(d["drs"][i])),
                "throttle": float(d["throttle"][i]),
                "brake": float(d["brake"][i]),
                "gap": gap_seconds,
                "tyre_life": int(round(d["tyre_life"][i])),
                "lap": int(round(d["lap"][i])),
                "rel_dist": float(d["rel_dist"][i]),
                "tyre": d["tyre"][i],
                "grid": d["grid"]
            })

        if not snapshot: continue

        # 정렬 로직 (초반 그리드, 이후 거리)
        if leader_dist < 300:
            snapshot.sort(key=lambda r: r["grid"])
        else:
            snapshot.sort(key=lambda r: r["dist"], reverse=True)

        leader_lap = snapshot[0]["lap"]

        frame_data = {}
        for idx, car in enumerate(snapshot):
            frame_data[car["code"]] = {
                "x": car["x"],
                "y": car["y"],
                "speed": car["speed"],
                "gear": car["gear"],
                "drs": car["drs"],
                "throttle": car["throttle"],
                "brake": car["brake"],
                "gap": car["gap"],
                "tyre_life": car["tyre_life"],
                "dist": car["dist"],
                "lap": car["lap"],
                "rel_dist": car["rel_dist"],
                "tyre": car["tyre"],
                "position": idx + 1,
                "grid": car["grid"]
            }

        frames.append({
            "t": float(t),
            "lap": leader_lap,
            "drivers": frame_data,
        })

    result_data = {
        "frames": frames,
        "driver_colors": get_driver_colors(session),
        "track_statuses": formatted_track_statuses,
        "race_control_messages": race_control_messages
    }

    try:
        with open(cache_file_path, 'wb') as f:
            pickle.dump(result_data, f)
        print(f"Processed data cached to: {cache_file_path}")
    except Exception as e:
        print(f"Failed to save cache: {e}")

    return result_data


def get_event_schedule(year):
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        return schedule[['RoundNumber', 'EventName', 'Country', 'Location']].to_dict('records')
    except Exception as e:
        print(f"스케줄 가져오기 실패: {e}")
        return []