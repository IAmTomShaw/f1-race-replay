"""
Live F1 race data via the OpenF1 REST API.

Polls OpenF1 (~1s interval) and builds frames in the same format used by
F1RaceReplayWindow so the live viewer reuses the existing visualization.
"""

import datetime
import threading
import time
from typing import Dict, List, Optional

import requests

OPENF1_BASE = "https://api.openf1.org/v1"

# Maps OpenF1 compound strings to the int used by the replay engine
TYRE_MAP = {
    "SOFT": 0,
    "MEDIUM": 1,
    "HARD": 2,
    "INTERMEDIATE": 3,
    "WET": 4,
    "UNKNOWN": 1,
}

# Maps OpenF1 race-control flag strings to the status codes used by the replay engine
FLAG_STATUS_MAP = {
    "GREEN": "1",
    "YELLOW": "2",
    "DOUBLE YELLOW": "2",
    "RED": "5",
    "SAFETY CAR": "4",
    "VIRTUAL SAFETY CAR": "6",
    "CHEQUERED": "1",
    "CLEAR": "1",
}


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (255, 255, 255)


def _get(endpoint: str, params: Dict = None, timeout: int = 10) -> Optional[List]:
    """GET request to OpenF1 API. Returns parsed JSON list or None on failure."""
    url = f"{OPENF1_BASE}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"[OpenF1] {endpoint} failed: {exc}")
        return None


def _parse_ts(date_str: Optional[str]) -> Optional[datetime.datetime]:
    if not date_str:
        return None
    try:
        return datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_current_session() -> Optional[Dict]:
    """
    Return the most recent session from OpenF1, or None if the API is unreachable.
    """
    data = _get("sessions", {"session_key": "latest"})
    if not data:
        return None
    return data[-1] if isinstance(data, list) else data


def is_session_live(session: Dict) -> bool:
    """
    Return True if the session appears to be currently in progress.
    Adds a 30-minute buffer after `date_end` to account for race overruns.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    start = _parse_ts(session.get("date_start"))
    end = _parse_ts(session.get("date_end"))
    if start is None:
        return False
    if end is None:
        # No end time recorded yet — live if start is within the last 4 hours
        return start <= now <= start + datetime.timedelta(hours=4)
    return start <= now <= end + datetime.timedelta(minutes=30)


def get_session_drivers(session_key: int) -> Dict[str, Dict]:
    """
    Return driver info keyed by driver number (string).
    e.g. {"1": {"name_acronym": "VER", "team_colour": "3671C6", ...}, ...}
    """
    data = _get("drivers", {"session_key": session_key}) or []
    return {str(d["driver_number"]): d for d in data if "driver_number" in d}


def get_driver_colors_from_openf1(drivers_info: Dict[str, Dict]) -> Dict[str, tuple]:
    """Return {acronym: (R, G, B)} from OpenF1 driver info."""
    colors = {}
    for num, info in drivers_info.items():
        code = info.get("name_acronym", num)
        colors[code] = _hex_to_rgb(info.get("team_colour") or "FFFFFF")
    return colors


def load_circuit_layout(year: int, round_number: int):
    """
    Load an example lap from FastF1 for the circuit track layout.

    Tries Qualifying first (best DRS data), then falls back to Race/Practice.
    Returns (example_lap_df, session) or (None, None) on failure.
    """
    import fastf1  # local import — heavy library

    for stype in ("Q", "R", "FP3", "FP2", "FP1"):
        try:
            session = fastf1.get_session(year, round_number, stype)
            # Only load laps+telemetry; skip weather/messages to be faster
            session.load(laps=True, telemetry=True, weather=False, messages=False)
            fastest = session.laps.pick_fastest()
            if fastest is not None:
                tel = fastest.get_telemetry()
                if not tel.empty and "X" in tel.columns:
                    print(f"[Live] Circuit layout from {stype} (Round {round_number})")
                    return tel, session
        except Exception as exc:
            print(f"[Live] Could not load {stype} for layout: {exc}")
    return None, None


def find_round_number(year: int, location: str, circuit_short: str) -> Optional[int]:
    """
    Try to find the FastF1 round number for a circuit given its name/location.
    Returns None if not found.
    """
    try:
        import fastf1
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        loc_lower = location.lower()
        circ_lower = circuit_short.lower()
        for _, row in schedule.iterrows():
            event_name = str(row.get("EventName", "")).lower()
            event_loc = str(row.get("Location", "")).lower()
            if circ_lower in event_name or circ_lower in event_loc or loc_lower in event_loc:
                return int(row["RoundNumber"])
    except Exception as exc:
        print(f"[Live] Could not find round number: {exc}")
    return None


# ---------------------------------------------------------------------------
# LiveDataFeed
# ---------------------------------------------------------------------------

class LiveDataFeed:
    """
    Background poller that fetches live F1 data from OpenF1 and builds frames
    compatible with F1RaceReplayWindow.

    Frame format (matches existing replay frame structure):
    {
        "t":       float,   # seconds since session start (wall-clock)
        "lap":     int,     # leader's current lap number
        "drivers": {
            "VER": {
                "x": float, "y": float,
                "position": int, "lap": int,
                "dist": float, "rel_dist": float,
                "tyre": int, "tyre_life": int,
                "speed": float, "gear": int,
                "drs": int, "throttle": float, "brake": float,
            }, ...
        },
        "weather": {...} | None,
    }
    """

    POLL_INTERVAL = 1.0  # seconds between polls

    def __init__(
        self,
        session_key: int,
        drivers_info: Dict[str, Dict],
        session_start: datetime.datetime,
    ):
        self.session_key = session_key
        self.drivers_info = drivers_info  # {driver_number_str: {name_acronym, ...}}
        self.session_start = session_start

        # Shared, lock-protected frame buffer (appended to by background thread)
        self.frames: List[Dict] = []
        self.track_statuses: List[Dict] = []  # live track status events
        self._lock = threading.Lock()
        self._running = False

        # Current best-known state per driver (keyed by driver number string)
        self._positions: Dict[str, Dict] = {}
        self._car_data: Dict[str, Dict] = {}
        self._race_pos: Dict[str, int] = {}
        self._laps: Dict[str, int] = {}
        self._stints: Dict[str, Dict] = {}
        self._weather: Optional[Dict] = None

        # Watermarks for incremental fetching
        self._ts_location: Optional[datetime.datetime] = None
        self._ts_car: Optional[datetime.datetime] = None
        self._ts_position: Optional[datetime.datetime] = None

        # Current track flag status code (matches replay engine codes)
        self._current_status_code: str = "1"  # GREEN

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def prefetch(self):
        """Synchronously load initial state and build the first frame."""
        self._fetch_stints()
        self._fetch_laps()
        self._fetch_positions_bulk()
        self._fetch_locations_bulk()
        self._fetch_car_data_bulk()
        self._fetch_weather()
        self._fetch_race_control()
        frame = self._build_frame()
        if frame:
            with self._lock:
                self.frames.append(frame)

    def start(self):
        """Start background polling thread."""
        self._running = True
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def get_frames(self) -> List[Dict]:
        with self._lock:
            return list(self.frames)

    def frame_count(self) -> int:
        with self._lock:
            return len(self.frames)

    def get_track_statuses(self) -> List[Dict]:
        with self._lock:
            return list(self.track_statuses)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _poll_loop(self):
        poll_count = 0
        while self._running:
            try:
                self._fetch_incremental()
                # Refresh stints / laps / weather less often
                if poll_count % 5 == 0:
                    self._fetch_stints()
                    self._fetch_laps()
                    self._fetch_weather()
                if poll_count % 10 == 0:
                    self._fetch_race_control()
                frame = self._build_frame()
                if frame:
                    with self._lock:
                        self.frames.append(frame)
            except Exception as exc:
                print(f"[LiveDataFeed] Poll error: {exc}")
            poll_count += 1
            time.sleep(self.POLL_INTERVAL)

    def _fetch_incremental(self):
        """Fetch only data newer than our watermarks."""
        # Locations
        loc_params = {"session_key": self.session_key}
        if self._ts_location:
            loc_params["date>"] = self._ts_location.isoformat()
        locs = _get("location", loc_params) or []
        for loc in locs:
            drv = str(loc.get("driver_number", ""))
            if drv:
                self._positions[drv] = {"x": loc.get("x", 0), "y": loc.get("y", 0)}
                ts = _parse_ts(loc.get("date"))
                if ts and (self._ts_location is None or ts > self._ts_location):
                    self._ts_location = ts

        # Car data
        car_params = {"session_key": self.session_key}
        if self._ts_car:
            car_params["date>"] = self._ts_car.isoformat()
        cars = _get("car_data", car_params) or []
        for c in cars:
            drv = str(c.get("driver_number", ""))
            if drv:
                self._car_data[drv] = {
                    "speed": c.get("speed", 0),
                    "gear": c.get("n_gear", 0),
                    "drs": 1 if (c.get("drs") or 0) >= 10 else 0,
                    "throttle": c.get("throttle", 0),
                    "brake": c.get("brake", 0),
                }
                ts = _parse_ts(c.get("date"))
                if ts and (self._ts_car is None or ts > self._ts_car):
                    self._ts_car = ts

        # Race positions
        pos_params = {"session_key": self.session_key}
        if self._ts_position:
            pos_params["date>"] = self._ts_position.isoformat()
        positions = _get("position", pos_params) or []
        for p in positions:
            drv = str(p.get("driver_number", ""))
            if drv:
                self._race_pos[drv] = p.get("position", 99)
                ts = _parse_ts(p.get("date"))
                if ts and (self._ts_position is None or ts > self._ts_position):
                    self._ts_position = ts

    # ------------------------------------------------------------------
    # Bulk fetches (called on startup / periodic refresh)
    # ------------------------------------------------------------------

    def _fetch_locations_bulk(self):
        locs = _get("location", {"session_key": self.session_key}) or []
        for loc in locs:
            drv = str(loc.get("driver_number", ""))
            if drv:
                self._positions[drv] = {"x": loc.get("x", 0), "y": loc.get("y", 0)}
                ts = _parse_ts(loc.get("date"))
                if ts and (self._ts_location is None or ts > self._ts_location):
                    self._ts_location = ts

    def _fetch_car_data_bulk(self):
        cars = _get("car_data", {"session_key": self.session_key}) or []
        for c in cars:
            drv = str(c.get("driver_number", ""))
            if drv:
                self._car_data[drv] = {
                    "speed": c.get("speed", 0),
                    "gear": c.get("n_gear", 0),
                    "drs": 1 if (c.get("drs") or 0) >= 10 else 0,
                    "throttle": c.get("throttle", 0),
                    "brake": c.get("brake", 0),
                }
                ts = _parse_ts(c.get("date"))
                if ts and (self._ts_car is None or ts > self._ts_car):
                    self._ts_car = ts

    def _fetch_positions_bulk(self):
        positions = _get("position", {"session_key": self.session_key}) or []
        for p in positions:
            drv = str(p.get("driver_number", ""))
            if drv:
                self._race_pos[drv] = p.get("position", 99)
                ts = _parse_ts(p.get("date"))
                if ts and (self._ts_position is None or ts > self._ts_position):
                    self._ts_position = ts

    def _fetch_stints(self):
        stints = _get("stints", {"session_key": self.session_key}) or []
        for s in stints:
            drv = str(s.get("driver_number", ""))
            if not drv:
                continue
            existing = self._stints.get(drv)
            snum = s.get("stint_number", 1)
            if not existing or snum >= existing.get("stint_number", 0):
                self._stints[drv] = {
                    "compound": (s.get("compound") or "UNKNOWN").upper(),
                    "age_at_start": s.get("tyre_age_at_start") or 0,
                    "lap_start": s.get("lap_start") or 1,
                    "stint_number": snum,
                }

    def _fetch_laps(self):
        laps = _get("laps", {"session_key": self.session_key}) or []
        for lap in laps:
            drv = str(lap.get("driver_number", ""))
            lap_num = lap.get("lap_number") or 1
            if drv and lap_num > self._laps.get(drv, 0):
                self._laps[drv] = lap_num

    def _fetch_weather(self):
        weather = _get("weather", {"session_key": self.session_key}) or []
        if weather:
            w = weather[-1]
            self._weather = {
                "track_temp": w.get("track_temperature"),
                "air_temp": w.get("air_temperature"),
                "humidity": w.get("humidity"),
                "wind_speed": w.get("wind_speed"),
                "wind_direction": w.get("wind_direction"),
                "rain_state": "RAINING" if w.get("rainfall") else "DRY",
            }

    def _fetch_race_control(self):
        """Pull race control messages and update track_statuses list."""
        msgs = _get("race_control", {"session_key": self.session_key}) or []
        now_t = (
            datetime.datetime.now(datetime.timezone.utc) - self.session_start
        ).total_seconds()

        new_statuses = []
        for msg in msgs:
            flag = (msg.get("flag") or "").upper()
            category = (msg.get("category") or "").upper()
            if category not in ("FLAG", "SAFETYCAR", "VIRTUALSC"):
                continue
            code = FLAG_STATUS_MAP.get(flag, "1")
            ts = _parse_ts(msg.get("date"))
            t = (
                (ts - self.session_start).total_seconds()
                if ts
                else now_t
            )
            new_statuses.append({"status": code, "start_time": t, "end_time": None})

        # Fill in end times: each status ends when the next begins
        for i, s in enumerate(new_statuses):
            if i + 1 < len(new_statuses):
                s["end_time"] = new_statuses[i + 1]["start_time"]

        with self._lock:
            self.track_statuses = new_statuses

        # Update current flag for quick reference
        if new_statuses:
            self._current_status_code = new_statuses[-1]["status"]

    # ------------------------------------------------------------------
    # Frame building
    # ------------------------------------------------------------------

    def _build_frame(self) -> Optional[Dict]:
        if not self._positions:
            return None

        drivers_data: Dict[str, Dict] = {}

        for drv_num, pos in self._positions.items():
            if drv_num not in self.drivers_info:
                continue

            info = self.drivers_info[drv_num]
            code = info.get("name_acronym") or drv_num
            car = self._car_data.get(drv_num, {})
            stint = self._stints.get(drv_num, {})
            lap = int(self._laps.get(drv_num) or 1)
            race_position = int(self._race_pos.get(drv_num) or 99)

            # Tyre compound → int
            compound = (stint.get("compound") or "UNKNOWN").upper()
            tyre_int = TYRE_MAP.get(compound, 1)

            # Tyre life: age at stint start + laps completed since stint start
            age_at_start = int(stint.get("age_at_start") or 0)
            lap_start = int(stint.get("lap_start") or 1)
            tyre_life = max(1, age_at_start + max(0, lap - lap_start + 1))

            drivers_data[code] = {
                "x": float(pos.get("x") or 0),
                "y": float(pos.get("y") or 0),
                "position": race_position,
                "lap": lap,
                "dist": 0.0,
                "rel_dist": 0.0,
                "tyre": tyre_int,
                "tyre_life": tyre_life,
                "speed": float(car.get("speed") or 0),
                "gear": int(car.get("gear") or 0),
                "drs": int(car.get("drs") or 0),
                "throttle": float(car.get("throttle") or 0),
                "brake": float(car.get("brake") or 0),
            }

        if not drivers_data:
            return None

        # Session time: seconds elapsed since session start
        now = datetime.datetime.now(datetime.timezone.utc)
        t = max(0.0, (now - self.session_start).total_seconds())

        # Leader = driver in P1
        leader = min(drivers_data.values(), key=lambda d: d["position"], default=None)
        leader_lap = leader["lap"] if leader else 1

        return {
            "t": t,
            "lap": leader_lap,
            "drivers": drivers_data,
            "weather": self._weather,
        }
