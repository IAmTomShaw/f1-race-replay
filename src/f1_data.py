import os
import fastf1
import fastf1.plotting
import numpy as np
import pickle  # [추가] 데이터를 파일로 저장/로드하기 위해 필요
from datetime import timedelta

# 타이어 데이터 처리를 위한 로컬 임포트
try:
    from src.lib.tyres import get_tyre_compound_int
except ImportError:
    def get_tyre_compound_int(compound):
        return 0

    # 1. FastF1 원본 데이터 캐시 (다운로드 시간 절약)
fastf1.Cache.enable_cache('.fastf1-cache')

# 2. [추가] 가공된 데이터 캐시 경로 (계산 시간 절약)
PROCESSED_CACHE_DIR = '.processed_cache'
if not os.path.exists(PROCESSED_CACHE_DIR):
    os.makedirs(PROCESSED_CACHE_DIR)

FPS = 25
DT = 1 / FPS


def load_race_session(year, round_number):
    session = fastf1.get_session(year, round_number, 'R')
    session.load(telemetry=True, laps=True, weather=False)
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
    """
    이중 캐싱 적용: 가공된 데이터가 있으면 바로 파일에서 읽어옵니다.
    """
    event_name = f"{session.event.year}_{session.event.RoundNumber}_{session.event.EventName.replace(' ', '_')}"
    cache_file_path = os.path.join(PROCESSED_CACHE_DIR, f"{event_name}.pkl")

    # [핵심] 가공된 캐시 파일이 존재하는지 확인
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
            print(f"Cache load failed, reprocessing: {e}")

    # --- 캐시가 없으면 아래 원본 계산 로직 실행 ---

    drivers = session.drivers
    total_drivers = len(drivers)

    driver_codes = {num: session.get_driver(num)["Abbreviation"] for num in drivers}
    driver_data = {}
    global_t_min = None
    global_t_max = None

    for i, driver_no in enumerate(drivers):
        code = driver_codes[driver_no]
        current_count = i + 1

        if progress_callback:
            percent = (current_count / total_drivers)
            message = f"Processing {code} ({current_count}/{total_drivers})"
            progress_callback(percent, message)

        print(f"Getting telemetry for driver: {code} ({current_count}/{total_drivers})")

        laps_driver = session.laps.pick_drivers(driver_no)
        if laps_driver.empty: continue

        t_all = []
        x_all = []
        y_all = []
        speed_all = []
        gear_all = []
        drs_all = []
        race_dist_all = []
        rel_dist_all = []
        lap_numbers = []
        tyre_compounds = []

        total_dist_so_far = 0.0

        for _, lap in laps_driver.iterlaps():
            lap_tel = lap.get_telemetry()
            lap_number = lap.LapNumber
            tyre_int = get_tyre_compound_int(lap.Compound)

            if lap_tel.empty: continue

            t_lap = lap_tel["SessionTime"].dt.total_seconds().to_numpy()
            x_lap = lap_tel["X"].to_numpy()
            y_lap = lap_tel["Y"].to_numpy()

            speed_lap = lap_tel["Speed"].to_numpy()
            gear_lap = lap_tel["nGear"].to_numpy()
            drs_lap = lap_tel["DRS"].to_numpy()

            d_lap = lap_tel["Distance"].to_numpy()
            rd_lap = lap_tel["RelativeDistance"].to_numpy()

            d_lap = d_lap - d_lap.min()
            lap_length = d_lap.max()
            race_d_lap = total_dist_so_far + d_lap
            total_dist_so_far += lap_length

            t_all.append(t_lap)
            x_all.append(x_lap)
            y_all.append(y_lap)
            speed_all.append(speed_lap)
            gear_all.append(gear_lap)
            drs_all.append(drs_lap)
            race_dist_all.append(race_d_lap)
            rel_dist_all.append(rd_lap)
            lap_numbers.append(np.full_like(t_lap, lap_number))
            tyre_compounds.append(np.full_like(t_lap, tyre_int))

        if not t_all: continue

        t_all = np.concatenate(t_all)
        x_all = np.concatenate(x_all)
        y_all = np.concatenate(y_all)
        speed_all = np.concatenate(speed_all)
        gear_all = np.concatenate(gear_all)
        drs_all = np.concatenate(drs_all)
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
            "dist": race_dist_all[order],
            "rel_dist": rel_dist_all[order],
            "lap": lap_numbers[order],
            "tyre": tyre_compounds[order],
        }

        t_min = t_all.min()
        t_max = t_all.max()
        global_t_min = t_min if global_t_min is None else min(global_t_min, t_min)
        global_t_max = t_max if global_t_max is None else max(global_t_max, t_max)

    if progress_callback:
        progress_callback(1.0, "Finalizing Data... (Syncing Timeline)")

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
            "dist": np.interp(timeline, t, data["dist"]),
            "rel_dist": np.interp(timeline, t, data["rel_dist"]),
            "lap": np.interp(timeline, t, data["lap"]),
            "tyre": np.interp(timeline, t, data["tyre"]),
        }

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
        snapshot = []
        for code, d in resampled_data.items():
            snapshot.append({
                "code": code,
                "dist": float(d["dist"][i]),
                "x": float(d["x"][i]),
                "y": float(d["y"][i]),
                "speed": float(d["speed"][i]),
                "gear": int(round(d["gear"][i])),
                "drs": int(round(d["drs"][i])),
                "lap": int(round(d["lap"][i])),
                "rel_dist": float(d["rel_dist"][i]),
                "tyre": d["tyre"][i],
            })

        if not snapshot: continue

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
                "dist": car["dist"],
                "lap": car["lap"],
                "rel_dist": car["rel_dist"],
                "tyre": car["tyre"],
                "position": idx + 1,
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
    }

    # [핵심] 가공 완료된 데이터를 파일로 저장 (다음 실행 시 로딩 단축)
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