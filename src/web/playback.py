import asyncio
import numpy as np

from src.f1_data import FPS
from src.web.ws_hub import WSHub
from src.web.flags import FlagBisectByTime, FLAG_MAP
from src.web.serialization import safe_jsonable

PUSH_HZ = 60
MIN_PUSH_INTERVAL = 1.0 / PUSH_HZ


class Playback:
    def __init__(self, session_mgr, ws_hub: WSHub):
        self.session_mgr = session_mgr
        self.ws_hub = ws_hub
        self.frame_index: float = 0.0
        self.playback_speed: float = 1.0
        self.paused: bool = True  # start paused until session is ready
        self._task: asyncio.Task | None = None
        self._last_push = 0.0
        self._last_broadcast_t_s: float = 0.0
        self._flag_bisect: FlagBisectByTime | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        if self._task:
            return
        self._loop = asyncio.get_event_loop()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def _schedule_push(self):
        """Schedule _push_now on the event loop — safe from any thread."""
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._push_now(), self._loop)
        else:
            asyncio.create_task(self._push_now())

    def set_speed(self, s: float):
        self.playback_speed = max(0.1, min(256.0, float(s)))
        self._schedule_push()

    def toggle_pause(self, value: bool | None = None):
        self.paused = (not self.paused) if value is None else bool(value)
        self._schedule_push()

    def seek(self, t_fraction: float):
        n = self._n_frames()
        self.frame_index = max(0.0, min(float(t_fraction), 1.0)) * (n - 1)
        self._schedule_push()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _n_frames(self) -> int:
        loaded = self.session_mgr.current()
        return len(loaded["frames"]) if loaded else 1

    async def _run(self):
        loop = asyncio.get_event_loop()
        prev = loop.time()
        while True:
            await asyncio.sleep(1 / FPS)
            now = loop.time()
            dt = now - prev
            prev = now

            loaded = self.session_mgr.current()
            if loaded is None:
                # Session not loaded yet — push loading state
                if now - self._last_push >= 1.0:
                    from src.web.session_manager import loading_state
                    await self.ws_hub.broadcast({"type": "loading", **loading_state()})
                    self._last_push = now
                continue

            # Auto-unpause when session first becomes ready
            if self.paused and self._flag_bisect is None:
                self._flag_bisect = FlagBisectByTime(loaded["track_statuses"])
                self.paused = False
                # Send snapshot to all clients
                snap = build_snapshot(loaded, self)
                await self.ws_hub.broadcast(snap)
                self._last_push = now
                continue

            if not self.paused:
                self.frame_index = min(
                    self.frame_index + dt * FPS * self.playback_speed,
                    self._n_frames() - 1,
                )

            if now - self._last_push >= MIN_PUSH_INTERVAL:
                await self._push_now(loop_time=now)

    async def _push_now(self, loop_time: float | None = None):
        payload = self._build_frame_payload()
        if payload is not None:
            await self.ws_hub.broadcast(payload)
        self._last_push = loop_time or asyncio.get_event_loop().time()
        if payload:
            self._last_broadcast_t_s = payload.get("t_seconds", self._last_broadcast_t_s)

    def _build_frame_payload(self) -> dict | None:
        loaded = self.session_mgr.current()
        if loaded is None:
            return None

        frames = loaded["frames"]
        if not frames:
            return None

        fi = int(self.frame_index)
        fi = min(fi, len(frames) - 1)
        frame = frames[fi]

        # Clock string
        t = frame.get("t", 0)
        hours = int(t // 3600)
        minutes = int((t % 3600) // 60)
        seconds = int(t % 60)
        clock = f"{hours:02}:{minutes:02}:{seconds:02}"

        # Flag state
        flag_state = "green"
        if self._flag_bisect is not None:
            flag_state = self._flag_bisect.at(t)

        # Track status raw code
        track_status = "1"
        for entry in loaded["track_statuses"]:
            if t >= entry["start_time"] and (
                entry.get("end_time") is None or t <= entry["end_time"]
            ):
                track_status = entry["status"]

        # Safety car
        sc = frame.get("safety_car")

        # Weather
        weather = frame.get("weather", {})

        # New race control events since last broadcast
        new_rc = []
        for msg in loaded["race_control_messages"]:
            if msg["time"] > self._last_broadcast_t_s and msg["time"] <= t:
                new_rc.append(msg)

        # Standings
        geo = loaded["geometry"]
        prev_frame = frames[fi - 1] if fi > 0 else None
        standings = standings_from_frame(frame, loaded, geo, prev_frame)

        return {
            "type": "frame",
            "frame_index": fi,
            "total_frames": len(frames),
            "t": round(t, 3),
            "t_seconds": round(t, 3),
            "lap": frame.get("lap", 1),
            "total_laps": loaded["total_laps"],
            "clock": clock,
            "track_status": track_status,
            "flag_state": flag_state,
            "playback_speed": self.playback_speed,
            "is_paused": self.paused,
            "weather": weather,
            "safety_car": sc,
            "standings": standings,
            "new_rc_events": new_rc,
        }


# ---------------------------------------------------------------------------
# Public helpers (used by pit_wall_server.py too)
# ---------------------------------------------------------------------------

def build_snapshot(loaded: dict, playback: "Playback") -> dict:
    """Full snapshot sent on WS connect or after session load."""
    geo = loaded["geometry"]
    public_geo = {k: v for k, v in geo.items() if not k.startswith("_")}

    fi = int(playback.frame_index)
    frames = loaded["frames"]
    fi = min(fi, len(frames) - 1) if frames else 0
    frame = frames[fi] if frames else None
    prev_frame = frames[fi - 1] if frames and fi > 0 else None

    standings = []
    if frame:
        standings = standings_from_frame(frame, loaded, geo, prev_frame)

    flag_state = "green"
    if frame:
        flag_state = FlagBisectByTime(loaded["track_statuses"]).at(frame["t"])

    lap_data = loaded.get("lap_data", {})
    total_frames = len(frames) if frames else 1
    return {
        "type": "snapshot",
        "frame_index": fi,
        "total_frames": total_frames,
        "event": loaded["event"],
        "driver_colors": loaded.get("driver_colors_hex", {}),
        "driver_meta": loaded["driver_meta"],
        "geometry": public_geo,
        "total_laps": loaded["total_laps"],
        "max_tyre_life": loaded["max_tyre_life"],
        "circuit_rotation": loaded["circuit_rotation"],
        "race_control_history": loaded["race_control_messages"],
        "standings": standings,
        "flag_state": flag_state,
        "playback": {
            "speed": playback.playback_speed,
            "is_paused": playback.paused,
        },
        "session_best": loaded.get("session_best", {}),
        "fastest_qual_lap_s": loaded.get("fastest_qual_lap_s"),
        "stints": {code: lap_data[code]["stints"] for code in lap_data if "stints" in lap_data[code]},
        "pit_stops": {code: lap_data[code]["pit_stops"] for code in lap_data if "pit_stops" in lap_data[code]},
        "track_statuses": [
            {
                "status": FLAG_MAP.get(e["status"], e["status"]),
                "start_time": e["start_time"],
                "end_time": e["end_time"],
            }
            for e in loaded["track_statuses"]
        ],
        "total_duration_s": frames[-1]["t"] if frames else 0,
    }


def _brake_intensity_pct(code: str, d: dict, prev_drivers: dict, dt: float, decel_full: float) -> float:
    brake_on = bool(d.get("brake", 0.0))
    if not brake_on:
        return 0.0
    prev = prev_drivers.get(code)
    if not prev or dt <= 0:
        return 100.0  # brake pressed but no delta available — show full
    v0 = float(prev.get("speed", 0.0)) / 3.6  # kph -> m/s
    v1 = float(d.get("speed", 0.0)) / 3.6
    decel = (v0 - v1) / dt
    if decel <= 0:
        return 15.0  # brake applied but not decelerating (e.g. trail braking mid-corner)
    return max(0.0, min(100.0, (decel / decel_full) * 100.0))


def standings_from_frame(frame: dict, loaded: dict, geo: dict, prev_frame: dict | None = None) -> list:
    """Build a standings list from a single frame dict."""
    drivers = frame.get("drivers", {})
    if not drivers:
        return []

    # FastF1's Brake channel is boolean (on/off), not analog pressure. Synthesize
    # an intensity 0-100 from deceleration between frames, gated by the brake
    # flag. ~8 m/s² deceleration maps to 100% (approximate F1 peak braking).
    prev_drivers = prev_frame.get("drivers", {}) if prev_frame else {}
    dt = 1.0 / FPS
    if prev_frame is not None:
        dt_actual = frame.get("t", 0.0) - prev_frame.get("t", 0.0)
        if dt_actual > 0:
            dt = dt_actual
    DECEL_FULL = 50.0  # m/s² ≈ 5g, F1 peak braking, maps to 100%

    ref_xs = geo.get("_ref_xs")
    ref_ys = geo.get("_ref_ys")
    ref_cumdist = geo.get("_ref_cumdist")
    ref_total_length = geo.get("_ref_total_length", 0.0)
    track_tree = geo.get("_track_tree")

    driver_progress = {}
    for code, d in drivers.items():
        x, y = d.get("x", 0.0), d.get("y", 0.0)
        lap = d.get("lap", 1)
        try:
            lap = int(lap)
        except (ValueError, TypeError):
            lap = 1

        projected_m = 0.0
        if track_tree is not None and ref_cumdist is not None:
            _, idx = track_tree.query([x, y])
            idx = int(idx)
            if idx < len(ref_xs) - 1:
                x1, y1 = ref_xs[idx], ref_ys[idx]
                x2, y2 = ref_xs[idx + 1], ref_ys[idx + 1]
                vx, vy = x2 - x1, y2 - y1
                seg_len2 = vx * vx + vy * vy
                if seg_len2 > 0:
                    t = ((x - x1) * vx + (y - y1) * vy) / seg_len2
                    t_clamped = max(0.0, min(1.0, t))
                    proj_x = x1 + t_clamped * vx
                    proj_y = y1 + t_clamped * vy
                    seg_dist = float(np.sqrt((proj_x - x1) ** 2 + (proj_y - y1) ** 2))
                    projected_m = float(ref_cumdist[idx] + seg_dist)
                else:
                    projected_m = float(ref_cumdist[idx])
            else:
                projected_m = float(ref_cumdist[idx])

        progress_m = float((max(lap, 1) - 1) * ref_total_length + projected_m)
        driver_progress[code] = progress_m

    sorted_codes = sorted(driver_progress.keys(), key=lambda c: driver_progress[c], reverse=True)
    pos_by_code = {code: i + 1 for i, code in enumerate(sorted_codes)}

    lap_data = loaded.get("lap_data", {})
    driver_meta = loaded.get("driver_meta", {})
    all_codes = list(driver_meta.keys())

    standings = []
    for code in all_codes:
        if code not in drivers:
            standings.append({
                "pos": 99,
                "code": code,
                "gap_s": None,
                "interval_s": None,
                "last_lap_s": None,
                "best_lap_s": None,
                "last_s1_s": None,
                "last_s2_s": None,
                "last_s3_s": None,
                "personal_best_lap_s": None,
                "personal_best_s1_s": None,
                "personal_best_s2_s": None,
                "personal_best_s3_s": None,
                "compound_int": 0,
                "tyre_age_laps": 0,
                "status": "OUT",
                "in_pit": False,
                "in_drs": False,
                "x": None,
                "y": None,
                "lap": 1,
                "rel_dist": 0.0,
                "fraction": 0.0,
                "speed_kph": 0.0,
                "gear": 0,
                "drs_raw": 0,
                "throttle_pct": 0.0,
                "brake_pct": 0.0,
                "rpm": 0.0,
                "stint": 1,
            })
            continue

        pos = pos_by_code[code]
        d = drivers[code]
        progress_m = driver_progress[code]
        leader_progress = driver_progress[sorted_codes[0]]
        gap_s = None
        interval_s = None
        if pos > 1:
            gap_dist = abs(leader_progress - progress_m)
            gap_s = round(gap_dist / 10.0 / 55.56, 3)
            ahead_progress = driver_progress[sorted_codes[pos - 2]]
            int_dist = abs(ahead_progress - progress_m)
            interval_s = round(int_dist / 10.0 / 55.56, 3)

        driver_laps_data = lap_data.get(code, {}).get("laps", {})
        current_lap = d.get("lap", 1)
        prev_lap_no = current_lap - 1
        last_lap_s = None
        best_lap_s = None
        last_s1_s = None
        last_s2_s = None
        last_s3_s = None
        if prev_lap_no in driver_laps_data:
            prev_lap = driver_laps_data[prev_lap_no]
            last_lap_s = round(prev_lap["lap_time_s"], 3) if prev_lap.get("lap_time_s") is not None else None
            last_s1_s = round(prev_lap["s1_s"], 3) if prev_lap.get("s1_s") is not None else None
            last_s2_s = round(prev_lap["s2_s"], 3) if prev_lap.get("s2_s") is not None else None
            last_s3_s = round(prev_lap["s3_s"], 3) if prev_lap.get("s3_s") is not None else None

        if driver_laps_data:
            lap_times_vals = [lap["lap_time_s"] for lap in driver_laps_data.values() if lap.get("lap_time_s") is not None]
            if lap_times_vals:
                best_lap_s = round(min(lap_times_vals), 3)
            s1_vals = [lap["s1_s"] for lap in driver_laps_data.values() if lap.get("s1_s") is not None]
            s2_vals = [lap["s2_s"] for lap in driver_laps_data.values() if lap.get("s2_s") is not None]
            s3_vals = [lap["s3_s"] for lap in driver_laps_data.values() if lap.get("s3_s") is not None]
            personal_best_lap_s = round(min(lap_times_vals), 3) if lap_times_vals else None
            personal_best_s1_s = round(min(s1_vals), 3) if s1_vals else None
            personal_best_s2_s = round(min(s2_vals), 3) if s2_vals else None
            personal_best_s3_s = round(min(s3_vals), 3) if s3_vals else None
        else:
            personal_best_lap_s = None
            personal_best_s1_s = None
            personal_best_s2_s = None
            personal_best_s3_s = None

        drs_raw = d.get("drs", 0)
        in_drs = drs_raw in (10, 12, 14)

        fraction = progress_m / ref_total_length if ref_total_length > 0 else 0.0

        # Live branch: fallback based on lap-level PitInTime/PitOutTime and lap fraction (frame does not set in_pit)
        current_lap_info = driver_laps_data.get(current_lap)
        in_pit = False
        if current_lap_info:
            if (current_lap_info.get("pit_in") and fraction > 0.9) or (current_lap_info.get("pit_out") and fraction < 0.1):
                in_pit = True

        status = "PIT" if in_pit else "RUN"

        standings.append({
            "pos": pos,
            "code": code,
            "gap_s": gap_s,
            "interval_s": interval_s,
            "last_lap_s": last_lap_s,
            "best_lap_s": best_lap_s,
            "last_s1_s": last_s1_s,
            "last_s2_s": last_s2_s,
            "last_s3_s": last_s3_s,
            "personal_best_lap_s": personal_best_lap_s,
            "personal_best_s1_s": personal_best_s1_s,
            "personal_best_s2_s": personal_best_s2_s,
            "personal_best_s3_s": personal_best_s3_s,
            "compound_int": int(d.get("tyre", 0)),
            "tyre_age_laps": int(d.get("tyre_life", 0)),
            "status": status,
            "in_pit": in_pit,
            "in_drs": in_drs,
            "x": float(d.get("x", 0.0)),
            "y": float(d.get("y", 0.0)),
            "lap": int(d.get("lap", 1)),
            "rel_dist": float(d.get("rel_dist", 0.0)),
            "fraction": round(fraction, 6),
            "speed_kph": float(d.get("speed", 0.0)),
            "gear": int(d.get("gear", 0)),
            "drs_raw": drs_raw,
            "throttle_pct": float(d.get("throttle", 0.0)),
            "brake_pct": _brake_intensity_pct(code, d, prev_drivers, dt, DECEL_FULL),
            "rpm": float(d.get("rpm", 0.0)),
            "stint": current_lap_info.get("stint", 1) if current_lap_info else 1,
        })

    standings.sort(key=lambda s: s.get("pos", 99))
    return standings
