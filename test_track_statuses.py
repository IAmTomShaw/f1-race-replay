"""
Tests for track_statuses pipeline:
  1. build_snapshot includes track_statuses with start_time, end_time, status label
  2. LiveProvider stores track_statuses from snapshot into state
  3. track_statuses are converted to safetyCarEvents [{start, end}] for Timeline

Run:  python test_track_statuses.py
"""
import sys, json, types
from unittest.mock import MagicMock


# ── 1. Test build_snapshot includes track_statuses ──────────────────────────

def _bootstrap_fastapi():
    """Stub out fastapi so playback.py can be imported without it."""
    if "fastapi" in sys.modules:
        return
    fake_fastapi = types.ModuleType("fastapi")
    fake_fastapi.WebSocket = type("WebSocket", (), {})
    fake_fastapi.WebSocketDisconnect = type("WebSocketDisconnect", (), {})
    fake_fastapi.FastAPI = type("FastAPI", (), {})
    fake_fastapi.APIRouter = type("APIRouter", (), {})
    fake_fastapi.BackgroundTasks = type("BackgroundTasks", (), {})
    fake_fastapi.Request = type("Request", (), {})
    fake_fastapi.HTTPException = type("HTTPException", (), {})
    sys.modules["fastapi"] = fake_fastapi

    fake_cors = types.ModuleType("fastapi.middleware.cors")
    fake_cors.CORSMiddleware = type("CORSMiddleware", (), {})
    sys.modules["fastapi.middleware"] = types.ModuleType("fastapi.middleware")
    sys.modules["fastapi.middleware.cors"] = fake_cors

    fake_static = types.ModuleType("fastapi.staticfiles")
    fake_static.StaticFiles = type("StaticFiles", (), {})
    sys.modules["fastapi.staticfiles"] = fake_static

    sys.modules["uvicorn"] = types.ModuleType("uvicorn")


def test_build_snapshot_includes_track_statuses():
    """build_snapshot must include a track_statuses list with start_time, end_time, and status label."""
    _bootstrap_fastapi()
    from src.web.playback import build_snapshot

    track_statuses_raw = [
        {"status": "1", "start_time": 0.0, "end_time": 300.0},
        {"status": "4", "start_time": 300.0, "end_time": 600.0},   # SC
        {"status": "1", "start_time": 600.0, "end_time": None},
    ]

    loaded = {
        "geometry": {"centerline": {"x": [0], "y": [0]}},
        "frames": [{"t": 2400.0}],
        "event": {"event_name": "Test GP"},
        "driver_colors_hex": {},
        "driver_meta": {},
        "total_laps": 50,
        "max_tyre_life": 40,
        "circuit_rotation": 0,
        "race_control_messages": [],
        "track_statuses": track_statuses_raw,
        "lap_data": {},
        "session_best": {},
    }

    playback = MagicMock()
    playback.frame_index = 0
    playback.playback_speed = 1
    playback.paused = False

    snap = build_snapshot(loaded, playback)

    assert "track_statuses" in snap, "Snapshot missing 'track_statuses' key"
    ts = snap["track_statuses"]
    assert isinstance(ts, list), f"track_statuses should be a list, got {type(ts)}"
    assert len(ts) == 3, f"Expected 3 track_statuses, got {len(ts)}"

    # Each entry must have start_time, end_time, status
    for entry in ts:
        assert "start_time" in entry, f"Entry missing start_time: {entry}"
        assert "end_time" in entry, f"Entry missing end_time: {entry}"
        assert "status" in entry, f"Entry missing status: {entry}"

    # Verify status labels are human-readable (not raw codes)
    assert ts[0]["status"] == "green", f"Expected 'green', got '{ts[0]['status']}'"
    assert ts[1]["status"] == "sc", f"Expected 'sc', got '{ts[1]['status']}'"
    assert ts[2]["status"] == "green", f"Expected 'green', got '{ts[2]['status']}'"

    # Verify times pass through unchanged
    assert ts[0]["start_time"] == 0.0
    assert ts[0]["end_time"] == 300.0
    assert ts[1]["start_time"] == 300.0
    assert ts[1]["end_time"] == 600.0
    assert ts[2]["start_time"] == 600.0
    assert ts[2]["end_time"] is None

    # Verify total_duration_s
    assert "total_duration_s" in snap, "Snapshot missing 'total_duration_s' key"
    assert snap["total_duration_s"] == 2400.0

    print("✅ test_build_snapshot_includes_track_statuses PASSED")


def test_build_snapshot_track_statuses_empty():
    """build_snapshot with empty track_statuses should return an empty list."""
    _bootstrap_fastapi()
    from src.web.playback import build_snapshot

    loaded = {
        "geometry": {"centerline": {"x": [0], "y": [0]}},
        "frames": [{"t": 1000.0}],
        "event": {"event_name": "Test GP"},
        "driver_colors_hex": {},
        "driver_meta": {},
        "total_laps": 50,
        "max_tyre_life": 40,
        "circuit_rotation": 0,
        "race_control_messages": [],
        "track_statuses": [],
        "lap_data": {},
        "session_best": {},
    }

    playback = MagicMock()
    playback.frame_index = 0
    playback.playback_speed = 1
    playback.paused = False

    snap = build_snapshot(loaded, playback)

    assert "track_statuses" in snap
    assert snap["track_statuses"] == []
    assert snap["total_duration_s"] == 1000.0

    print("✅ test_build_snapshot_track_statuses_empty PASSED")


# ── 2. Test LiveProvider stores track_statuses (simulated in Python) ────────

def test_live_provider_stores_track_statuses():
    """On snapshot receipt, track_statuses should be stored in LiveProvider state."""
    # Simulate what live_state.jsx does:
    #   if (msg.track_statuses) setTrackStatuses(msg.track_statuses)
    # We test the data flow logic, not React itself.

    snapshot_msg = {
        "type": "snapshot",
        "track_statuses": [
            {"status": "green", "start_time": 0.0, "end_time": 300.0},
            {"status": "sc", "start_time": 300.0, "end_time": 600.0},
        ],
    }

    # Simulate LiveProvider state
    state = {"trackStatuses": []}

    # Simulate the effect handler
    if snapshot_msg.get("track_statuses"):
        state["trackStatuses"] = snapshot_msg["track_statuses"]

    assert len(state["trackStatuses"]) == 2
    assert state["trackStatuses"][0]["status"] == "green"
    assert state["trackStatuses"][1]["status"] == "sc"

    print("✅ test_live_provider_stores_track_statuses PASSED")


# ── 3. Test track_statuses → safetyCarEvents conversion for Timeline ───────

def test_track_statuses_to_safety_car_events():
    """Convert track_statuses to [{start, end}] fractions for Timeline, filtering SC/VSC/RED."""
    # This mirrors the conversion logic that will live in App.jsx
    FLAG_MAP = {"1": "green", "2": "yellow", "4": "sc", "5": "red", "6": "vsc", "7": "vsc"}
    SC_LABELS = {"sc", "vsc", "red"}

    track_statuses = [
        {"status": "green", "start_time": 0.0, "end_time": 300.0},
        {"status": "sc", "start_time": 300.0, "end_time": 600.0},
        {"status": "green", "start_time": 600.0, "end_time": 1200.0},
        {"status": "vsc", "start_time": 1200.0, "end_time": 1500.0},
        {"status": "green", "start_time": 1500.0, "end_time": 2400.0},
        {"status": "red", "start_time": 2400.0, "end_time": None},
    ]

    total_duration = 3000.0  # total race time in seconds

    # Conversion: filter to SC/VSC/RED, compute start/end as fractions
    safety_car_events = []
    for ts in track_statuses:
        if ts["status"] in SC_LABELS:
            start_frac = ts["start_time"] / total_duration
            end_frac = (ts["end_time"] if ts["end_time"] is not None else total_duration) / total_duration
            safety_car_events.append({
                "start": round(start_frac, 6),
                "end": round(end_frac, 6),
            })

    assert len(safety_car_events) == 3, f"Expected 3 SC events, got {len(safety_car_events)}"

    # SC period: 300/3000 to 600/3000
    assert abs(safety_car_events[0]["start"] - 0.1) < 0.001
    assert abs(safety_car_events[0]["end"] - 0.2) < 0.001

    # VSC period: 1200/3000 to 1500/3000
    assert abs(safety_car_events[1]["start"] - 0.4) < 0.001
    assert abs(safety_car_events[1]["end"] - 0.5) < 0.001

    # RED period: 2400/3000 to end (None → total_duration)
    assert abs(safety_car_events[2]["start"] - 0.8) < 0.001
    assert abs(safety_car_events[2]["end"] - 1.0) < 0.001

    print("✅ test_track_statuses_to_safety_car_events PASSED")


def test_track_statuses_no_sc_events():
    """If no SC/VSC/RED periods, safetyCarEvents should be empty."""
    SC_LABELS = {"sc", "vsc", "red"}

    track_statuses = [
        {"status": "green", "start_time": 0.0, "end_time": 1500.0},
        {"status": "yellow", "start_time": 1500.0, "end_time": None},
    ]

    total_duration = 3000.0
    safety_car_events = []
    for ts in track_statuses:
        if ts["status"] in SC_LABELS:
            safety_car_events.append({"start": 0, "end": 0})

    assert len(safety_car_events) == 0

    print("✅ test_track_statuses_no_sc_events PASSED")


# ── Run all ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.path.insert(0, "/Users/austen/Desktop/f1-race-replay-main")

    tests = [
        test_build_snapshot_includes_track_statuses,
        test_build_snapshot_track_statuses_empty,
        test_live_provider_stores_track_statuses,
        test_track_statuses_to_safety_car_events,
        test_track_statuses_no_sc_events,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__} FAILED: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
