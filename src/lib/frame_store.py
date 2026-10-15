"""
Columnar, memory-efficient storage for race replay frames.

A full race at 25 FPS has ~130k frames x ~20 drivers. Storing that as a list
of nested Python dicts costs ~2.3 GB of RAM (tens of millions of objects).
FrameStore keeps the same data in compact NumPy arrays (~120 MB) and builds
the familiar frame dict lazily, only for the frame that is actually requested:

    frames[i] -> {"t", "lap", "drivers": {code: {...}}, "weather"?, "safety_car"?}

so all existing consumers (``frames[idx]``, ``len(frames)``, iteration,
slicing) keep working unchanged.
"""

import json
import os
from collections import OrderedDict
from collections.abc import Sequence

import numpy as np

# Per-driver numeric channels, stored as (n_frames, n_drivers) arrays
FLOAT_FIELDS = ("x", "y", "dist", "rel_dist", "tyre", "tyre_life", "speed", "throttle", "brake")
INT_FIELDS = {"lap": np.int16, "position": np.int8, "gear": np.int8, "drs": np.int8}
WEATHER_FIELDS = ("track_temp", "air_temp", "humidity", "wind_speed", "wind_direction", "rainfall")

FORMAT_VERSION = 1


class FrameStore(Sequence):
    def __init__(self, codes, t, leader_lap, channels, in_pit, weather=None, safety_car=None):
        self.codes = list(codes)
        self.t = np.asarray(t, dtype=np.float64)
        self.leader_lap = np.asarray(leader_lap, dtype=np.int16)
        self.channels = channels          # field -> 2D array (n_frames, n_drivers)
        self.in_pit = in_pit              # bool 2D array
        self.weather = weather or {}      # field -> 1D array (n_frames,)
        self.safety_car = safety_car or {}  # frame index -> sc dict (sparse)
        self._cache = OrderedDict()
        self._cache_size = 8

    # ------------------------------------------------------------------ build
    @classmethod
    def from_arrays(cls, codes, t, data, in_pit, weather=None):
        """Build from float64 working arrays; computes positions and leader lap."""
        n_frames = len(t)
        lap = np.rint(data["lap"]).astype(np.int64)
        # Leader = most laps, then furthest race distance (same rule as before)
        key = lap.astype(np.float64) * 1e9 + data["dist"]
        order = np.argsort(-key, axis=1, kind="stable")
        position = np.empty_like(order)
        rows = np.arange(n_frames)[:, None]
        position[rows, order] = np.arange(1, len(codes) + 1)[None, :]
        leader_lap = lap[np.arange(n_frames), order[:, 0]] if len(codes) else np.ones(n_frames)

        channels = {f: np.asarray(data[f], dtype=np.float32) for f in FLOAT_FIELDS}
        channels["lap"] = lap.astype(np.int16)
        channels["position"] = position.astype(np.int8)
        channels["gear"] = np.asarray(data["gear"]).astype(np.int8)
        channels["drs"] = np.asarray(data["drs"]).astype(np.int8)

        w = {}
        if weather:
            for k in WEATHER_FIELDS:
                if weather.get(k) is not None:
                    w[k] = np.asarray(weather[k], dtype=np.float32)

        return cls(codes, np.round(t, 3), leader_lap, channels, np.asarray(in_pit, dtype=bool), w)

    # --------------------------------------------------------------- sequence
    def __len__(self):
        return len(self.t)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return [self._build(i) for i in range(*idx.indices(len(self)))]
        i = int(idx)
        if i < 0:
            i += len(self)
        if i < 0 or i >= len(self):
            raise IndexError("frame index out of range")
        cached = self._cache.get(i)
        if cached is not None:
            self._cache.move_to_end(i)
            return cached
        frame = self._build(i)
        self._cache[i] = frame
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return frame

    def __iter__(self):
        for i in range(len(self)):
            yield self._build(i)

    def _build(self, i):
        ch = self.channels
        pos_row = ch["position"][i]
        drivers = {}
        # Insert drivers in race order (P1 first) like the original frame dicts
        for j in np.argsort(pos_row, kind="stable"):
            drivers[self.codes[j]] = {
                "x": float(ch["x"][i, j]),
                "y": float(ch["y"][i, j]),
                "dist": float(ch["dist"][i, j]),
                "lap": int(ch["lap"][i, j]),
                "rel_dist": round(float(ch["rel_dist"][i, j]), 4),
                "tyre": float(ch["tyre"][i, j]),
                "tyre_life": float(ch["tyre_life"][i, j]),
                "position": int(pos_row[j]),
                "speed": float(ch["speed"][i, j]),
                "gear": int(ch["gear"][i, j]),
                "drs": int(ch["drs"][i, j]),
                "throttle": float(ch["throttle"][i, j]),
                "brake": float(ch["brake"][i, j]),
                "in_pit": bool(self.in_pit[i, j]),
            }
        frame = {"t": float(self.t[i]), "lap": int(self.leader_lap[i]), "drivers": drivers}
        if self.weather:
            w = self.weather

            def _w(k):
                return float(w[k][i]) if k in w else None

            rain = w["rainfall"][i] if "rainfall" in w else 0.0
            frame["weather"] = {
                "track_temp": _w("track_temp"),
                "air_temp": _w("air_temp"),
                "humidity": _w("humidity"),
                "wind_speed": _w("wind_speed"),
                "wind_direction": _w("wind_direction"),
                "rain_state": "RAINING" if rain and rain >= 0.5 else "DRY",
            }
        sc = self.safety_car.get(i)
        if sc is not None:
            frame["safety_car"] = sc
        return frame

    # -------------------------------------------------------------- fast paths
    def fallback_lap_times(self, min_lap_time_s=30.0, max_lap_time_s=7200.0):
        """Vectorised equivalent of scanning every frame for lap transitions."""
        result = {}
        lap = self.channels["lap"]
        order0 = np.argsort(self.channels["position"][0], kind="stable") if len(self) else []
        for j in order0:
            code = self.codes[j]
            result[code] = []
            L = lap[:, j].astype(np.int64)
            cm = np.maximum.accumulate(L)
            trig = np.nonzero(L[1:] > cm[:-1])[0] + 1
            start = 0
            for i in trig:
                prev_lap = int(cm[i - 1])
                lap_time = float(self.t[i] - self.t[start])
                if min_lap_time_s < lap_time < max_lap_time_s and prev_lap >= 2:
                    result[code].append({
                        "lap": prev_lap,
                        "time_s": lap_time,
                        "end_time_s": float(self.t[i]),
                        "tyre": int(round(float(self.channels["tyre"][i, j]))),
                        "tyre_life": int(round(float(self.channels["tyre_life"][i, j]))),
                        "start_time_s": float(self.t[start]),
                    })
                start = i
        return result

    # ---------------------------------------------------------------- persist
    def save(self, path):
        arrays = {
            "t": self.t,
            "leader_lap": self.leader_lap,
            "in_pit": self.in_pit,
        }
        for k, v in self.channels.items():
            arrays[f"ch_{k}"] = v
        for k, v in self.weather.items():
            arrays[f"w_{k}"] = v
        meta = {
            "version": FORMAT_VERSION,
            "codes": self.codes,
            "safety_car": {str(k): v for k, v in self.safety_car.items()},
        }
        arrays["meta"] = np.frombuffer(json.dumps(meta).encode("utf-8"), dtype=np.uint8)
        tmp = path + ".tmp.npz"
        np.savez(tmp, **arrays)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(bytes(z["meta"]).decode("utf-8"))
            if meta.get("version") != FORMAT_VERSION:
                raise ValueError("unsupported frame store version")
            channels = {k[3:]: z[k] for k in z.files if k.startswith("ch_")}
            weather = {k[2:]: z[k] for k in z.files if k.startswith("w_")}
            sc = {int(k): v for k, v in meta.get("safety_car", {}).items()}
            return cls(meta["codes"], z["t"], z["leader_lap"], channels, z["in_pit"], weather, sc)
