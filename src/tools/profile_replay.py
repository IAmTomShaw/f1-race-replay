"""
Performance baseline for the new pure-Python algorithms.

Measures the cost of:

* per-driver telemetry resampling (1 driver, 100 Hz, 5 s)
* per-frame leaderboard ranking (20 drivers, 1000 frames)
* replay clock tick at all 12 documented speeds
* stream broker publish/dispatch (1000 messages, 4 subscribers)
* cache atomic write (1 KB payload)

This is the "PHASE 17 measurement" the project specification
calls for. It is intentionally synthetic — we do NOT load real
FastF1 telemetry, since that is environment-dependent and
slow. The baseline here is *algorithm cost*, not end-to-end
replay cost.

Run::

    python -m src.tools.profile_replay

The output is a markdown table that can be pasted into a
release-note or a regression dashboard.
"""
from __future__ import annotations

import statistics
import time
from contextlib import contextmanager
from typing import Callable, Dict, List, Tuple

import numpy as np

from src.analytics.leaderboard import rank_frames
from src.data.cache import write_cache_atomic
from src.data.telemetry_resample import (
    DEFAULT_CONTINUOUS,
    DEFAULT_DISCRETE,
    build_frame_payload,
    resample_driver,
)
from src.replay.clock import PLAYBACK_SPEEDS, ReplayClock
from src.streaming.broker import StreamingBroker
from src.streaming.protocol import MessageType


@contextmanager
def _timed(label: str, results: List[Tuple[str, float, str]]):
    t0 = time.perf_counter()
    yield
    elapsed = time.perf_counter() - t0
    results.append((label, elapsed, "s"))


def _time_fn(fn: Callable[[], None], repeats: int = 5) -> Tuple[float, float]:
    samples: List[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples), max(samples)


def _bench_telemetry_resample() -> Tuple[float, float]:
    def _run() -> None:
        n = 500
        timeline = np.linspace(0.0, 5.0, n)
        t_obs = np.linspace(0.0, 5.0, n)
        x_obs = t_obs * 10.0
        speed_obs = np.full_like(t_obs, 200.0)
        res = resample_driver(
            "VER", timeline, t_obs,
            {"x": x_obs, "speed": speed_obs,
             "gear": np.full_like(t_obs, 5.0),
             "throttle": np.full_like(t_obs, 80.0),
             "brake": np.zeros_like(t_obs)},
            channel_kinds={"gear": "discrete"},
        )
        build_frame_payload(timeline, [res])
    return _time_fn(_run)


def _bench_leaderboard() -> Tuple[float, float]:
    n_frames = 1000
    drivers = [f"D{i:02d}" for i in range(20)]
    frames = []
    for i in range(n_frames):
        snap = {code: {"lap": 1, "dist": float(i + idx * 10)}
                 for idx, code in enumerate(drivers)}
        frames.append({"t": i * 0.04, "drivers": snap})
    def _run() -> None:
        rank_frames(frames, track_length=5000.0)
    return _time_fn(_run)


def _bench_clock_speeds() -> Dict[float, float]:
    out: Dict[float, float] = {}
    for speed in PLAYBACK_SPEEDS:
        def _run(s=speed) -> None:
            c = ReplayClock(total_seconds=10.0, fps=25.0, initial_speed=s)
            wall = (10.0 / s) * 1.2
            dt = 0.01
            n = int(wall / dt)
            for _ in range(n):
                c.tick(dt)
                if c.at_end:
                    break
        med, _ = _time_fn(_run, repeats=3)
        out[speed] = med
    return out


def _bench_broker() -> Tuple[float, float]:
    broker = StreamingBroker(session_id="bench", queue_capacity=128)
    delivered = [0]
    def _deliver(_env):
        delivered[0] += 1
    for i in range(4):
        broker.add_subscriber(f"sub-{i}", deliver=_deliver)
    def _run() -> None:
        for i in range(1000):
            broker.publish(MessageType.FRAME_UPDATE, {"i": i})
        # Drain.
        while broker.dispatch_once() > 0:
            pass
    return _time_fn(_run)


def _bench_cache_atomic(tmp_path: str = None) -> Tuple[float, float]:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path = f"{td}/x.pkl"
        payload = {"x": list(range(1000))}
        def _run() -> None:
            write_cache_atomic(path, payload,
                                metadata={"year": 2024, "round_number": 1})
        return _time_fn(_run, repeats=5)


def main() -> int:
    results: List[Tuple[str, float, str]] = []
    print("F1 Race Replay — algorithm performance baseline")
    print("=" * 50)
    print("Synthetic inputs (no FastF1 / Arcade dependency).")
    print()

    t_resample, _ = _bench_telemetry_resample()
    t_leaderboard, _ = _bench_leaderboard()
    t_broker, _ = _bench_broker()
    t_cache, _ = _bench_cache_atomic()
    clock_results = _bench_clock_speeds()

    rows = [
        ("Telemetry resample (1 driver, 500 samples, 5 channels)",
         t_resample),
        ("Leaderboard (20 drivers, 1000 frames)",
         t_leaderboard),
        ("Broker publish+dispatch (1000 msgs, 4 subs)",
         t_broker),
        ("Cache atomic write (1 KB payload)",
         t_cache),
    ]
    for label, t in rows:
        print(f"  {label}: {t*1000:.2f} ms")
    print()
    print("Replay-clock 10 s @ various speeds (median over 3 runs):")
    for speed, t in clock_results.items():
        print(f"  {speed:>6}x -> {t*1000:.2f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
