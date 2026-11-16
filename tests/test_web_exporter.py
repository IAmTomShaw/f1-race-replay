import gzip
import json
import numpy as np

from src.core.replay_exporter import (
    build_demo_bundle,
    extract_circuit_name,
    pack_frames_columnar,
    serialize_track_geometry,
)
from src.core.track_geometry import (
    EVENT_DNF,
    EVENT_SAFETY_CAR,
    EVENT_VSC,
    build_track_from_example_lap,
    extract_race_events,
    plot_drs_zones,
)


def test_extract_circuit_name():
    assert extract_circuit_name("British Grand Prix") == "British"
    assert extract_circuit_name("Monaco GP") == "Monaco"
    assert extract_circuit_name("") == ""


def test_track_geometry_and_drs_zones():
    theta = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    x = 1000.0 * np.cos(theta)
    y = 800.0 * np.sin(theta)
    drs = np.zeros(200, dtype=int)
    drs[20:50] = 12
    drs[120:155] = 14

    lap = {"X": x, "Y": y, "DRS": drs}
    zones = plot_drs_zones(lap)
    assert len(zones) == 2
    assert zones[0]["start"]["index"] == 20
    assert zones[0]["end"]["index"] == 49

    geom = serialize_track_geometry(lap, circuit_rotation=35.0, max_points=100, track_width=200.0)
    assert len(geom["x_inner"]) == 100
    assert len(geom["x_outer"]) == 100
    assert geom["rotation_deg"] == 35.0
    assert len(geom["drs_zones"]) == 2
    assert geom["x_max"] > geom["x_min"]
    assert geom["y_max"] > geom["y_min"]


def test_pack_frames_columnar_and_dnf_backfill():
    raw_frames = []
    for i in range(12):
        drivers = {
            "VER": {
                "x": 100.0 + i * 10,
                "y": 200.0 + i * 5,
                "dist": i * 12.0,
                "rel_dist": round((i * 12.0) / 5000.0, 4),
                "lap": 1,
                "position": 1,
                "tyre": 1,
                "tyre_life": 3,
                "speed": 285.5,
                "gear": 7,
                "drs": 12,
                "throttle": 100.0,
                "brake": 0.0,
                "in_pit": False,
            }
        }
        if i < 6:
            drivers["GAS"] = {
                "x": 50.0 + i * 8,
                "y": 150.0 + i * 4,
                "dist": i * 10.0,
                "rel_dist": 0.25,
                "lap": 1,
                "position": 2,
                "tyre": 0,
                "tyre_life": 2,
                "speed": 260.0,
                "gear": 6,
                "drs": 0,
                "throttle": 95.0,
                "brake": 0.0,
                "in_pit": False,
            }
        raw_frames.append(
            {
                "t": i * 0.04,
                "lap": 1,
                "drivers": drivers,
                "weather": {
                    "track_temp": 30.2,
                    "air_temp": 21.5,
                    "humidity": 55.0,
                    "wind_speed": 2.1,
                    "wind_direction": 180.0,
                    "rain_state": "DRY",
                },
                "safety_car": (
                    {"x": 400.0, "y": 500.0, "phase": "on_track", "alpha": 1.0}
                    if i >= 5
                    else None
                ),
            }
        )

    packed = pack_frames_columnar(raw_frames, source_fps=25.0, stride=5)
    # Indices should be [0, 5, 10, 11]
    assert packed["fps"] == 5.0
    assert len(packed["t"]) == 4
    assert packed["drivers"]["VER"]["is_out"] == [0, 0, 0, 0]
    # GAS disappears at frame 6 -> marked out in indices 10 and 11
    assert packed["drivers"]["GAS"]["is_out"] == [0, 0, 1, 1]
    assert packed["safety_car"]["active"] == [0, 1, 1, 1]


def test_extract_race_events():
    frames = [
        {"t": i * 1.0, "drivers": {"VER": {"lap": 1, "rel_dist": 0.2}, "NOR": {"lap": 1, "rel_dist": 0.1}}}
        for i in range(5)
    ] + [
        {"t": 5.0 + i * 1.0, "drivers": {"VER": {"lap": 2, "rel_dist": 0.4}, "NOR": {"lap": 2, "rel_dist": 1.0}}}
        for i in range(5)
    ]
    statuses = [
        {"status": "4", "start_time": 2.0, "end_time": 6.0},
        {"status": "6", "start_time": 7.0, "end_time": 9.0},
    ]
    events = extract_race_events(frames, statuses, total_laps=10, fps=1.0)
    types = {e["type"] for e in events}
    assert EVENT_DNF in types
    assert EVENT_SAFETY_CAR in types
    assert EVENT_VSC in types


def test_demo_bundle_structure_and_size():
    manifest, frames = build_demo_bundle()
    assert manifest["session_id"] == "demo"
    assert len(manifest["drivers"]) == 20
    assert len(manifest["track"]["drs_zones"]) >= 1
    assert len(frames["t"]) > 500
    assert any(v == 1 for v in frames["safety_car"]["active"])
    assert any(v == 1 for v in frames["drivers"]["GAS"]["is_out"])

    gz_bytes = gzip.compress(json.dumps(frames, separators=(",", ":")).encode("utf-8"))
    # Demo race gzipped payload should be well under 2 MB
    assert len(gz_bytes) < 2 * 1024 * 1024
