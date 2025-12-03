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
        mapping = {'SOFT': 0, 'MEDIUM': 1, 'HARD': 2, 'INTERMEDIATE': 3, 'WET': 4}
        return mapping.get(str(compound).upper(), 0)

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
    # 로직 최적화로 버전 업 (v7)
    cache_file_path = os.path.join(PROCESSED_CACHE_DIR, f"{event_name}_v14.pkl")

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

    # 그리드 정보
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

    # DNF(리타이어) 드라이버 식별
    dnf_drivers = set()
    try:
        results = session.results
        for _, row in results.iterrows():
            status = str(row['Status'])
            code = row['Abbreviation']
            # 'Finished'가 아니거나, '+1 Lap' 같은 랩다운이 아니면 리타이어로 간주
            if status == 'Finished' or status.startswith('+'):
                continue
            dnf_drivers.add(code)
    except Exception as e:
        print(f"DNF detection warning: {e}")

    driver_data = {}
    global_t_min = None
    global_t_max = None

    # GapToLeader 안전 처리
    if 'GapToLeader' not in session.laps.columns:
        session.laps['GapToLeader'] = pd.Timedelta(seconds=0)
    else:
        session.laps['GapToLeader'] = session.laps['GapToLeader'].fillna(pd.Timedelta(seconds=0))

    # 표준 랩 길이
    try:
        fastest_lap = session.laps.pick_fastest()
        if fastest_lap is not None:
            telemetry = fastest_lap.get_telemetry()
            REF_LAP_LENGTH = telemetry['Distance'].max()
        else:
            REF_LAP_LENGTH = 5300.0
    except:
        REF_LAP_LENGTH = 5300.0

    # ---------------------------------------------------------
    # 1. 드라이버별 원본 데이터 수집
    # ---------------------------------------------------------
    for i, driver_no in enumerate(drivers):
        code = driver_codes[driver_no]
        current_count = i + 1
        grid_pos = driver_grids.get(driver_no, 20.0)

        if progress_callback:
            percent = (current_count / total_drivers) * 0.5  # 전체 진행의 50%까지만 할당
            progress_callback(percent, f"Downloading & Processing {code} ({current_count}/{total_drivers})")

        print(f"Getting telemetry for {code}")

        laps_driver = session.laps.pick_drivers(driver_no)
        if laps_driver.empty: continue

        # 데이터 수집용 리스트
        t_all, x_all, y_all = [], [], []
        speed_all, gear_all, drs_all = [], [], []
        throttle_all, brake_all = [], []
        tyre_life_all, race_dist_all, rel_dist_all = [], [], []
        lap_numbers, tyre_compounds = [], []

        for _, lap in laps_driver.iterlaps():
            lap_tel = lap.get_telemetry()
            if lap_tel.empty: continue

            t_lap = lap_tel["SessionTime"].dt.total_seconds().to_numpy()

            # 빠른 연산을 위해 필요한 컬럼만 추출
            race_dist_all.append(
                (lap.LapNumber - 1) * REF_LAP_LENGTH + (lap_tel["RelativeDistance"].to_numpy() * REF_LAP_LENGTH))
            t_all.append(t_lap)
            x_all.append(lap_tel["X"].to_numpy())
            y_all.append(lap_tel["Y"].to_numpy())
            speed_all.append(lap_tel["Speed"].to_numpy())
            gear_all.append(lap_tel["nGear"].to_numpy())
            drs_all.append(lap_tel["DRS"].to_numpy())
            throttle_all.append(lap_tel["Throttle"].to_numpy())
            brake_all.append(lap_tel["Brake"].to_numpy().astype(float))
            tyre_life_all.append(np.full_like(t_lap, lap.TyreLife if not pd.isna(lap.TyreLife) else 0))
            rel_dist_all.append(lap_tel["RelativeDistance"].to_numpy())
            lap_numbers.append(np.full_like(t_lap, lap.LapNumber))
            tyre_compounds.append(np.full_like(t_lap, get_tyre_compound_int(lap.Compound)))

        if not t_all: continue

        # numpy 배열 병합
        t_all = np.concatenate(t_all)
        order = np.argsort(t_all)  # 시간 순 정렬

        driver_data[code] = {
            "t": t_all[order],
            "x": np.concatenate(x_all)[order],
            "y": np.concatenate(y_all)[order],
            "speed": np.concatenate(speed_all)[order],
            "gear": np.concatenate(gear_all)[order],
            "drs": np.concatenate(drs_all)[order],
            "throttle": np.concatenate(throttle_all)[order],
            "brake": np.concatenate(brake_all)[order],
            "tyre_life": np.concatenate(tyre_life_all)[order],
            "dist": np.concatenate(race_dist_all)[order],
            "rel_dist": np.concatenate(rel_dist_all)[order],
            "lap": np.concatenate(lap_numbers)[order],
            "tyre": np.concatenate(tyre_compounds)[order],
            "grid": grid_pos
        }

        t_min, t_max = t_all.min(), t_all.max()
        global_t_min = t_min if global_t_min is None else min(global_t_min, t_min)
        global_t_max = t_max if global_t_max is None else max(global_t_max, t_max)

    # ---------------------------------------------------------
    # 2. 리샘플링 (공통 시간축 만들기)
    # ---------------------------------------------------------
    if progress_callback:
        progress_callback(0.6, "Resampling Data...")

    timeline = np.arange(global_t_min, global_t_max, DT) - global_t_min
    resampled_data = {}

    for code, data in driver_data.items():
        t = data["t"] - global_t_min
        resampled_data[code] = {
            "t": timeline,
            # 모든 데이터를 공통 시간축(timeline)에 맞춰 보간
            "x": np.interp(timeline, t, data["x"]),
            "y": np.interp(timeline, t, data["y"]),
            "speed": np.interp(timeline, t, data["speed"]),
            "gear": np.interp(timeline, t, data["gear"]),
            "drs": np.interp(timeline, t, data["drs"]),
            "throttle": np.interp(timeline, t, data["throttle"]),
            "brake": np.interp(timeline, t, data["brake"]),
            "tyre_life": np.interp(timeline, t, data["tyre_life"]),
            "dist": np.interp(timeline, t, data["dist"]),
            "rel_dist": np.interp(timeline, t, data["rel_dist"]),
            "lap": np.interp(timeline, t, data["lap"]),
            "tyre": np.interp(timeline, t, data["tyre"]),
            "grid": data["grid"]
        }

    # ---------------------------------------------------------
    # [최적화 핵심] 3. Gap 미리 계산 (Vectorization)
    # 루프 안에서 interp를 하지 않고, 배열 전체를 한 번에 계산합니다.
    # ---------------------------------------------------------
    if progress_callback:
        progress_callback(0.7, "Calculating Time Gaps (Optimized)...")

    # (1) 레퍼런스(선두) 드라이버 찾기: 가장 멀리 간 드라이버
    best_driver = max(resampled_data.keys(), key=lambda c: resampled_data[c]["dist"][-1])
    leader_dist = resampled_data[best_driver]["dist"]
    leader_time = timeline

    # (2) 보간을 위해 거리는 엄격하게 증가(Monotonic Increasing)해야 함
    # 멈춰있거나 뒤로 가는(스핀) 데이터 노이즈 제거
    leader_dist_monotonic = np.maximum.accumulate(leader_dist)

    # (3) 모든 드라이버에 대해 한 방에 Gap 계산
    for code, data in resampled_data.items():
        my_dist = data["dist"]

        # "내 거리(my_dist)일 때 선두는 몇 초(leader_time)였나?"
        # 전체 배열에 대해 한 번만 실행 (속도 수천 배 향상)
        leader_time_at_my_pos = np.interp(my_dist, leader_dist_monotonic, leader_time)

        # Gap = 현재 내 시간 - 선두가 그 위치를 지났던 시간
        gaps = timeline - leader_time_at_my_pos

        # 음수(선두보다 앞에 있는 경우 등)는 0으로 처리
        gaps[gaps < 0] = 0.0

        # 결과 저장
        resampled_data[code]["gap"] = gaps

    # ---------------------------------------------------------
    # 4. 프레임 생성 (이제 단순 조회만 수행)
    # ---------------------------------------------------------
    if progress_callback:
        progress_callback(0.8, "Generating Frames...")

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

    # [수정] 레이스 컨트롤 메시지 처리 로직 강화
    if progress_callback:
        progress_callback(0.8, "Processing Race Control Messages...")

    race_control_messages = []
    if hasattr(session, 'race_control_messages') and session.race_control_messages is not None:
        rcm = session.race_control_messages

        for _, row in rcm.iterrows():
            try:
                # 1. 컬럼 찾기: 'SessionTime'이 있으면 그걸 쓰고, 없으면 'Time' 사용
                val = row.get('SessionTime', row.get('Time'))

                # 2. 값 유효성 체크 (NaT/NaN이면 스킵)
                if pd.isna(val): continue

                # 3. 초(Seconds) 단위로 변환
                #    Timedelta 객체, 문자열, 혹은 이미 실수형인 경우 모두 처리
                if isinstance(val, (int, float)):
                    seconds = float(val)
                else:
                    # pandas의 to_timedelta로 강제 변환 후 초 추출
                    seconds = pd.to_timedelta(val).total_seconds()

                # 4. 경기 시간 보정
                msg_time = seconds - global_t_min

                race_control_messages.append({
                    'time': msg_time,
                    'category': str(row['Category']),
                    'message': str(row['Message']),
                    'flag': row['Flag'] if 'Flag' in row else None
                })
            except Exception as e:
                # 에러가 나더라도 멈추지 않고 해당 메시지만 건너뜀
                # print(f"Msg error: {e}")
                pass

    frames = []

    # 최적화 덕분에 이 루프는 이제 단순 데이터 조립만 수행하므로 매우 빠릅니다.
    for i, t in enumerate(timeline):

        # 0.1초 단위로만 선두 거리 계산 (정렬용) - 매 프레임 할 필요 없음
        current_leader_dist = 0
        if i % 10 == 0:
            current_dists = [d["dist"][i] for d in resampled_data.values()]
            if current_dists: current_leader_dist = max(current_dists)

        snapshot = []
        for code, d in resampled_data.items():
            # 미리 계산해둔 값들을 인덱싱으로 가져오기만 함 (O(1))

            # [추가] 리타이어 판단 로직 (서류상 DNF + 실제 멈춤)
            is_dnf_driver = code in dnf_drivers
            # 현재 거리(i)가 이 드라이버의 최종 이동거리(마지막 값)와 거의 같으면 멈춘 것임
            has_stopped = float(d["dist"][i]) >= (float(d["dist"][-1]) - 0.5)

            is_out = is_dnf_driver and has_stopped

            snapshot.append({
                "code": code,
                "dist": float(d["dist"][i]),
                "x": float(d["x"][i]),
                "y": float(d["y"][i]),
                "speed": float(d["speed"][i]),
                "gear": int(round(d["gear"][i])),
                "drs": int(round(d["drs"][i])),
                "throttle": float(d["throttle"][i]),
                "brake": float(d["brake"][i]),
                "gap": float(d["gap"][i]),  # 미리 계산된 Gap 사용
                "tyre_life": int(round(d["tyre_life"][i])),
                "lap": int(round(d["lap"][i])),
                "rel_dist": float(d["rel_dist"][i]),
                "tyre": int(round(d["tyre"][i])),
                "grid": d["grid"],
                "is_out": is_out  # [추가] 상태 저장
            })

        if not snapshot: continue

        # [수정] 순위 정렬
        if current_leader_dist < 200 and i < 500:
            snapshot.sort(key=lambda r: r["grid"])
        else:
            snapshot.sort(key=lambda r: (r["lap"], r["rel_dist"]), reverse=True)

        # =========================================================
        # [추가됨] 앞차와의 인터벌(Interval) 계산 로직
        # 정렬이 끝난 후(순위가 결정된 후) 실행해야 합니다.
        # =========================================================
        for idx in range(len(snapshot)):
            if idx == 0:
                # 1등은 앞차가 없으므로 인터벌 0
                snapshot[idx]["interval"] = 0.0
            else:
                # 내 선두 갭 - 앞차 선두 갭 = 둘 사이의 인터벌
                my_gap = snapshot[idx]["gap"]
                car_ahead_gap = snapshot[idx - 1]["gap"]

                # 가끔 데이터 오차로 마이너스가 뜨는 것을 방지
                diff = my_gap - car_ahead_gap
                snapshot[idx]["interval"] = diff if diff > 0 else 0.0
        # =========================================================

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
                "gap": car["gap"],  # 선두와의 갭
                "interval": car["interval"],  # [추가됨] 앞차와의 갭
                "tyre_life": car["tyre_life"],
                "dist": car["dist"],
                "lap": car["lap"],
                "rel_dist": car["rel_dist"],
                "tyre": car["tyre"],
                "position": idx + 1,
                "grid": car["grid"],
                "is_out": car["is_out"]
            }

        frames.append({
            "t": float(t),
            "lap": leader_lap,
            "drivers": frame_data,
        })

    # --- 최종 저장 ---
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