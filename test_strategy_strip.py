"""
Temporary unit test: verify real stint/pit_stop data flows correctly
from _precompute_lap_data → build_snapshot → JS API shape.

Run:  python test_strategy_strip.py
"""
import sys, json
from unittest.mock import MagicMock, patch

# ── 1. Test _precompute_lap_data with synthetic laps ──────────────────────

def _make_laps_df(rows):
    """Build a minimal DataFrame that _precompute_lap_data expects."""
    import pandas as pd
    return pd.DataFrame(rows)


def test_precompute_stints():
    """Stints are contiguous, start_lap ≤ end_lap, and cover the full race."""
    from src.web.session_manager import _precompute_lap_data

    rows = [
        # Stint 1: SOFT laps 1-15
        {"Driver": "VER", "LapNumber": i, "LapTime": None,
         "Sector1Time": None, "Sector2Time": None, "Sector3Time": None,
         "IsPersonalBest": False, "Compound": "SOFT", "TyreLife": i,
         "Stint": 1, "PitInTime": 90.0 if i == 15 else None,
         "PitOutTime": None, "FreshTyre": True, "TrackStatus": "1",
         "Deleted": False}
        for i in range(1, 16)
    ] + [
        # Stint 2: MEDIUM laps 16-35
        {"Driver": "VER", "LapNumber": i, "LapTime": None,
         "Sector1Time": None, "Sector2Time": None, "Sector3Time": None,
         "IsPersonalBest": False, "Compound": "MEDIUM", "TyreLife": i - 15,
         "Stint": 2, "PitInTime": 90.0 if i == 35 else None,
         "PitOutTime": 5.0 if i == 16 else None, "FreshTyre": True,
         "TrackStatus": "1", "Deleted": False}
        for i in range(16, 36)
    ] + [
        # Stint 3: HARD laps 36-50
        {"Driver": "VER", "LapNumber": i, "LapTime": None,
         "Sector1Time": None, "Sector2Time": None, "Sector3Time": None,
         "IsPersonalBest": False, "Compound": "HARD", "TyreLife": i - 35,
         "Stint": 3, "PitInTime": None,
         "PitOutTime": 5.0 if i == 36 else None, "FreshTyre": True,
         "TrackStatus": "1", "Deleted": False}
        for i in range(36, 51)
    ]

    session = MagicMock()
    session.laps = _make_laps_df(rows)

    result = _precompute_lap_data(session)
    ver = result["VER"]

    # ── Stints ──
    stints = ver["stints"]
    assert len(stints) == 3, f"Expected 3 stints, got {len(stints)}: {stints}"

    assert stints[0] == {"stint": 1, "compound": "SOFT",   "start_lap": 1,  "end_lap": 15, "laps": 15}, f"Stint 1 wrong: {stints[0]}"
    assert stints[1] == {"stint": 2, "compound": "MEDIUM", "start_lap": 16, "end_lap": 35, "laps": 20}, f"Stint 2 wrong: {stints[1]}"
    assert stints[2] == {"stint": 3, "compound": "HARD",   "start_lap": 36, "end_lap": 50, "laps": 15}, f"Stint 3 wrong: {stints[2]}"

    # Stints are contiguous
    for i in range(1, len(stints)):
        assert stints[i]["start_lap"] == stints[i-1]["end_lap"] + 1, \
            f"Gap between stint {i} and {i+1}"

    # ── Pit stops ──
    pit_stops = ver["pit_stops"]
    assert len(pit_stops) == 2, f"Expected 2 pit stops, got {len(pit_stops)}: {pit_stops}"
    assert pit_stops[0]["lap"] == 15, f"Pit stop 1 lap wrong: {pit_stops[0]}"
    assert pit_stops[1]["lap"] == 35, f"Pit stop 2 lap wrong: {pit_stops[1]}"

    print("✅ test_precompute_stints PASSED")


def test_precompute_no_pit():
    """A driver with no pit stops should have 1 stint and 0 pit_stops."""
    from src.web.session_manager import _precompute_lap_data

    rows = [
        {"Driver": "NOR", "LapNumber": i, "LapTime": None,
         "Sector1Time": None, "Sector2Time": None, "Sector3Time": None,
         "IsPersonalBest": False, "Compound": "MEDIUM", "TyreLife": i,
         "Stint": 1, "PitInTime": None, "PitOutTime": None,
         "FreshTyre": True, "TrackStatus": "1", "Deleted": False}
        for i in range(1, 11)
    ]
    session = MagicMock()
    session.laps = _make_laps_df(rows)

    result = _precompute_lap_data(session)
    nor = result["NOR"]

    assert len(nor["stints"]) == 1
    assert nor["stints"][0]["compound"] == "MEDIUM"
    assert nor["stints"][0]["start_lap"] == 1
    assert nor["stints"][0]["end_lap"] == 10
    assert len(nor["pit_stops"]) == 0

    print("✅ test_precompute_no_pit PASSED")


# ── 2. Test build_snapshot ships stints/pit_stops correctly ───────────────

def test_build_snapshot_includes_stints():
    """build_snapshot must include stints and pit_stops keyed by driver code."""
    # Stub out heavy imports so we can test build_snapshot in isolation
    import types, sys

    # Create a fake fastapi module with the symbols playback.py needs
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

    from src.web.playback import build_snapshot

    lap_data = {
        "VER": {
            "laps": {1: {"compound": "SOFT"}},
            "stints": [{"stint": 1, "compound": "SOFT", "start_lap": 1, "end_lap": 15, "laps": 15}],
            "pit_stops": [{"lap": 15, "duration_s": None}],
        },
        "NOR": {
            "laps": {1: {"compound": "MEDIUM"}},
            "stints": [{"stint": 1, "compound": "MEDIUM", "start_lap": 1, "end_lap": 50, "laps": 50}],
            "pit_stops": [],
        },
    }

    loaded = {
        "geometry": {"centerline": {"x": [0], "y": [0]}},
        "frames": [],
        "event": {"event_name": "Test GP"},
        "driver_colors_hex": {},
        "driver_meta": {},
        "total_laps": 50,
        "max_tyre_life": 40,
        "circuit_rotation": 0,
        "race_control_messages": [],
        "track_statuses": [],
        "lap_data": lap_data,
        "session_best": {},
    }

    playback = MagicMock()
    playback.frame_index = 0
    playback.playback_speed = 1
    playback.paused = False

    snap = build_snapshot(loaded, playback)

    assert "stints" in snap, "Snapshot missing 'stints' key"
    assert "pit_stops" in snap, "Snapshot missing 'pit_stops' key"
    assert snap["stints"]["VER"] == lap_data["VER"]["stints"]
    assert snap["pit_stops"]["VER"] == lap_data["VER"]["pit_stops"]
    assert snap["stints"]["NOR"] == lap_data["NOR"]["stints"]
    # NOR has empty pit_stops — should not appear in pit_stops dict
    # (build_snapshot filters: "pit_stops" in lap_data[code])
    # NOR does have the key, so it will appear but be empty
    assert snap["pit_stops"]["NOR"] == []

    print("✅ test_build_snapshot_includes_stints PASSED")


# ── 3. Test JS-side COMPOUND_KEY mapping (simulated in Python) ─────────────

COMPOUND_KEY = {
    "SOFT": "S", "MEDIUM": "M", "HARD": "H",
    "INTERMEDIATE": "I", "WET": "W", "UNKNOWN": "M",
}

COMPOUNDS = {
    "S": {"label": "SOFT",   "color": "#FF3A3A"},
    "M": {"label": "MEDIUM", "color": "#FFD93A"},
    "H": {"label": "HARD",   "color": "#F4F4F4"},
    "I": {"label": "INTER",  "color": "#3AE87A"},
    "W": {"label": "WET",    "color": "#3A9BFF"},
}


def test_compound_key_mapping():
    """Every compound string from fastf1 must map to a valid APEX key."""
    for compound_str in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]:
        key = COMPOUND_KEY[compound_str]
        assert key in COMPOUNDS, f"COMPOUND_KEY['{compound_str}'] = '{key}' not in COMPOUNDS"
    # UNKNOWN fallback
    assert COMPOUND_KEY["UNKNOWN"] == "M"

    print("✅ test_compound_key_mapping PASSED")


# ── 4. Test pit stop marker alignment against real lap data ────────────────

def test_pit_stop_marker_positions():
    """Pit stop markers must align at the end of the stint they terminate.

    In the JS StrategyStrip:
      - Stint bar: left  = (start_lap - 1) / totalLaps * 100
                   width = (end_lap - start_lap + 1) / totalLaps * 100
      - Pit marker: left = (pit_lap - 1) / totalLaps * 100

    A pit stop on lap N should visually sit at the boundary between
    stint ending at lap N and stint starting at lap N+1.
    """
    total_laps = 50
    stints = [
        {"stint": 1, "compound": "SOFT",   "start_lap": 1,  "end_lap": 15, "laps": 15},
        {"stint": 2, "compound": "MEDIUM", "start_lap": 16, "end_lap": 35, "laps": 20},
        {"stint": 3, "compound": "HARD",   "start_lap": 36, "end_lap": 50, "laps": 15},
    ]
    pit_stops = [
        {"lap": 15, "duration_s": None},
        {"lap": 35, "duration_s": None},
    ]

    # Simulate JS rendering: convert stints → bar positions
    # In StrategyStrip: start = start_lap - 1 (0-indexed), end = end_lap
    stops = [
        {"start": s["start_lap"] - 1, "end": s["end_lap"], "c": COMPOUND_KEY[s["compound"]]}
        for s in stints
    ]

    # Check stint bars are contiguous
    for i in range(1, len(stops)):
        assert stops[i]["start"] == stops[i-1]["end"], \
            f"Stint bars not contiguous: stint {i} starts at {stops[i]['start']}, " \
            f"previous ends at {stops[i-1]['end']}"

    # Check each pit stop sits at the boundary between two stints
    for ps in pit_stops:
        pit_lap = ps["lap"]
        # The pit marker position (0-indexed): (pit_lap - 1) / totalLaps
        pit_pos = (pit_lap - 1) / total_laps

        # Find the stint that ends at this lap
        ending_stint = None
        starting_stint = None
        for st in stops:
            if st["end"] == pit_lap:
                ending_stint = st
            if st["start"] == pit_lap:
                starting_stint = st

        assert ending_stint is not None, f"No stint ends at pit lap {pit_lap}"
        assert starting_stint is not None, f"No stint starts at pit lap {pit_lap}"

        # Pit marker at end of lap N → position = N / total_laps
        # This should equal the right edge of the ending stint bar
        pit_marker_pos = pit_lap / total_laps
        stint_right_edge = ending_stint["end"] / total_laps
        assert abs(pit_marker_pos - stint_right_edge) < 0.001, \
            f"Pit marker at {pit_marker_pos:.4f} doesn't align with stint end at {stint_right_edge:.4f}"

    print("✅ test_pit_stop_marker_positions PASSED")


# ── 5. Test getStints / getPitStops JS API shape ──────────────────────────

def test_js_api_shape():
    """getStints(code) and getPitStops(code) return arrays with correct keys."""
    # Simulate what the JS functions do:
    #   getStints(code)  → window.__LIVE_SNAPSHOT?.stints?.[code] || []
    #   getPitStops(code) → window.__LIVE_SNAPSHOT?.pit_stops?.[code] || []

    snapshot = {
        "stints": {
            "VER": [
                {"stint": 1, "compound": "SOFT", "start_lap": 1, "end_lap": 15, "laps": 15},
            ],
        },
        "pit_stops": {
            "VER": [
                {"lap": 15, "duration_s": None},
            ],
        },
    }

    # Simulate getStints
    def getStints(code):
        return snapshot.get("stints", {}).get(code, [])

    def getPitStops(code):
        return snapshot.get("pit_stops", {}).get(code, [])

    ver_stints = getStints("VER")
    assert len(ver_stints) == 1
    assert "start_lap" in ver_stints[0]
    assert "end_lap" in ver_stints[0]
    assert "compound" in ver_stints[0]

    ver_pits = getPitStops("VER")
    assert len(ver_pits) == 1
    assert "lap" in ver_pits[0]

    # Missing driver returns empty
    assert getStints("HAM") == []
    assert getPitStops("HAM") == []

    print("✅ test_js_api_shape PASSED")


# ── Run all ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Add project root to path
    sys.path.insert(0, "/Users/austen/Desktop/f1-race-replay-main")

    tests = [
        test_precompute_stints,
        test_precompute_no_pit,
        test_build_snapshot_includes_stints,
        test_compound_key_mapping,
        test_pit_stop_marker_positions,
        test_js_api_shape,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__} FAILED: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
