"""
F1 Race Replay — Consolidated Test Suite.

This single test file covers all essential functionality:
  - Tyre compound mapping (lib/tyres)
  - Time parsing & formatting (lib/time)
  - Season detection (lib/season)
  - Settings manager (lib/settings)
  - Telemetry resampling & validity
  - Telemetry unit canonicalization
  - Qualifying helpers
  - Leaderboard ranking (8 F1 scenarios)
  - Replay clock state machine
  - Safety car extraction & attachment
  - Streaming protocol & broker
  - Cache versioning & atomic writes
  - Tyre model availability contract
  - Resource path resolution
  - Module import smoke tests
"""

import importlib
import json
import logging
import math
import os
import pickle
import shutil
import tempfile
import threading
import time as time_mod
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

# ==========================================================================
#  SECTION 1 — LIB: TYRES
# ==========================================================================
from src.lib.tyres import get_tyre_compound_int, get_tyre_compound_str


@pytest.mark.parametrize(
    ("compound", "expected"),
    [("SOFT", 0), ("MEDIUM", 1), ("HARD", 2),
     ("INTERMEDIATE", 3), ("WET", 4)],
)
def test_tyre_compound_int_known(compound, expected):
    assert get_tyre_compound_int(compound) == expected


@pytest.mark.parametrize(
    ("compound", "expected"),
    [("soft", 0), ("medium", 1), ("hard", 2),
     ("intermediate", 3), ("wet", 4)],
)
def test_tyre_compound_int_case_insensitive(compound, expected):
    assert get_tyre_compound_int(compound) == expected


@pytest.mark.parametrize("compound", ["UNKNOWN", "SUPERSOFT", ""])
def test_tyre_compound_int_unknown(compound):
    assert get_tyre_compound_int(compound) == -1


def test_tyre_compound_int_none():
    assert get_tyre_compound_int(None) == -1


@pytest.mark.parametrize(
    ("compound_id", "expected"),
    [(0, "SOFT"), (1, "MEDIUM"), (2, "HARD"),
     (3, "INTERMEDIATE"), (4, "WET")],
)
def test_tyre_compound_str_known(compound_id, expected):
    assert get_tyre_compound_str(compound_id) == expected


@pytest.mark.parametrize("compound_id", [-1, 5, 999])
def test_tyre_compound_str_unknown(compound_id):
    assert get_tyre_compound_str(compound_id) == "UNKNOWN"


# ==========================================================================
#  SECTION 2 — LIB: TIME
# ==========================================================================
from src.lib.time import format_time, parse_time_string


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00.000"), (1.234, "00:01.234"),
     (61.5, "01:01.500"), (3661.25, "61:01.250")],
)
def test_format_time_valid(seconds, expected):
    assert format_time(seconds) == expected


@pytest.mark.parametrize("seconds", [None, -1, -10.5])
def test_format_time_invalid(seconds):
    assert format_time(seconds) == "N/A"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("00:01:26:123000", 86.123), ("00:01:26.123000", 86.123),
     ("01:26.123", 86.123), ("01:26", 86.0),
     ("0 days 00:01:27.060000", 87.06),
     ("00:01:26.123000 extra text", 86.123)],
)
def test_parse_time_string_valid(value, expected):
    assert parse_time_string(value) == expected


@pytest.mark.parametrize("value", ["", "not-a-time", "1", "::::", None])
def test_parse_time_string_invalid(value):
    assert parse_time_string(value) is None


# ==========================================================================
#  SECTION 3 — LIB: SEASON
# ==========================================================================
import src.lib.season as season_mod


class _FixedDate(datetime):
    fixed_now = datetime(2025, 3, 1)
    @classmethod
    def now(cls):
        return cls.fixed_now


def test_season_returns_current_year_after_february(monkeypatch):
    _FixedDate.fixed_now = datetime(2025, 7, 15)
    monkeypatch.setattr(season_mod, "date", _FixedDate)
    assert season_mod.get_season() == 2025


def test_season_returns_previous_year_in_january(monkeypatch):
    _FixedDate.fixed_now = datetime(2025, 1, 15)
    monkeypatch.setattr(season_mod, "date", _FixedDate)
    assert season_mod.get_season() == 2024


# ==========================================================================
#  SECTION 4 — LIB: SETTINGS
# ==========================================================================
from src.lib.settings import SettingsManager


def _reset_settings():
    SettingsManager._instance = None


def test_settings_defaults(monkeypatch, tmp_path):
    _reset_settings()
    sf = tmp_path / "settings.json"
    monkeypatch.setattr(SettingsManager, "_get_settings_file_path", lambda self: sf)
    m = SettingsManager()
    assert m.cache_location.endswith(".fastf1-cache")
    assert Path(m.cache_location).is_absolute()


def test_settings_reads_json(monkeypatch, tmp_path):
    _reset_settings()
    sf = tmp_path / "settings.json"
    sf.write_text(json.dumps({"cache_location": "custom"}), encoding="utf-8")
    monkeypatch.setattr(SettingsManager, "_get_settings_file_path", lambda self: sf)
    assert SettingsManager().cache_location == "custom"


def test_settings_set_get(monkeypatch, tmp_path):
    _reset_settings()
    sf = tmp_path / "settings.json"
    monkeypatch.setattr(SettingsManager, "_get_settings_file_path", lambda self: sf)
    m = SettingsManager()
    m.set("key", "val")
    assert m.get("key") == "val"
    assert m.get("missing", "fb") == "fb"


def test_settings_save(monkeypatch, tmp_path):
    _reset_settings()
    sf = tmp_path / "settings.json"
    monkeypatch.setattr(SettingsManager, "_get_settings_file_path", lambda self: sf)
    m = SettingsManager()
    m.cache_location = "saved"
    m.save()
    assert json.loads(sf.read_text(encoding="utf-8"))["cache_location"] == "saved"


# ==========================================================================
#  SECTION 5 — TELEMETRY RESAMPLING & VALIDITY
# ==========================================================================
from src.data.telemetry_resample import (
    ChannelKind, Validity, resample_driver, build_frame_payload, channel_kind,
)


def _timeline(n, dt=0.04):
    return np.arange(n) * dt


def test_channel_kind_defaults():
    assert channel_kind("speed") is ChannelKind.CONTINUOUS
    assert channel_kind("gear") is ChannelKind.DISCRETE
    assert channel_kind("lap") is ChannelKind.DISCRETE


def test_driver_pre_valid_start_is_nan():
    timeline = _timeline(300)
    t_obs = np.array([10.0, 10.1, 10.2])
    x_obs = np.array([0.0, 1.0, 2.0])
    res = resample_driver("VER", timeline, t_obs, {"x": x_obs})
    for i in range(int(10.0 / 0.04)):
        assert res.validity[i] == Validity.PRE
        assert math.isnan(res.channels["x"][i])


def test_driver_post_valid_end_is_nan():
    timeline = np.linspace(0.0, 4.0, 201)
    t_obs = np.array([0.0, 1.0, 2.0, 3.0])
    x_obs = np.array([0.0, 100.0, 200.0, 300.0])
    res = resample_driver("VER", timeline, t_obs, {"x": x_obs})
    for i, t in enumerate(timeline):
        if t > 3.0 + 1e-9:
            assert math.isnan(res.channels["x"][i])
            assert res.validity[i] == Validity.POST


def test_gap_flagged_not_interpolated():
    timeline = np.linspace(0.0, 5.0, 251)
    t_obs = np.concatenate([np.arange(0.0, 1.5, 0.05),
                            np.arange(3.5, 5.0, 0.05)])
    x_obs = np.concatenate([np.arange(0.0, 1.5, 0.05),
                            np.arange(3.5, 5.0, 0.05)])
    res = resample_driver("VER", timeline, t_obs, {"x": x_obs})
    gap = [(i, t) for i, t in enumerate(timeline) if 1.6 < t < 3.4]
    for i, t in gap:
        assert res.validity[i] == Validity.GAP
        assert math.isnan(res.channels["x"][i])


def test_retired_driver_marked_dnf():
    timeline = np.linspace(0.0, 10.0, 501)
    t_ver = np.linspace(0.0, 1.0, 51)
    x_ver = t_ver * 10.0
    res = resample_driver("VER", timeline, t_ver, {"x": x_ver}, retired=True)
    for i, t in enumerate(timeline):
        if t > 1.0 + 1e-9:
            assert res.validity[i] in (Validity.DNF, Validity.POST)
            assert math.isnan(res.channels["x"][i])


def test_finished_driver_held():
    timeline = np.linspace(0.0, 5.0, 251)
    t_obs = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 4.5])
    x_obs = np.array([0.0, 100.0, 200.0, 300.0, 400.0, 450.0])
    res = resample_driver("VER", timeline, t_obs, {"x": x_obs}, finished=True)
    for i, t in enumerate(timeline):
        if t > 4.5 + 1e-9:
            assert res.validity[i] == Validity.FINISHED
    assert res.is_active(len(timeline) - 1)


def test_dns_driver():
    timeline = _timeline(100)
    res = resample_driver("XXX", timeline, np.array([]), {"x": np.array([])})
    assert not res.has_any_telemetry
    assert all(m == Validity.DNS for m in res.validity)


def test_discrete_step_sampling():
    timeline = np.linspace(0.0, 5.0, 51)
    t_obs = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    gear_obs = np.array([1, 2, 4, 6, 7])
    res = resample_driver("VER", timeline, t_obs, {"gear": gear_obs},
                          channel_kinds={"gear": ChannelKind.DISCRETE})
    for i, t in enumerate(timeline):
        if t < 1.0:
            assert res.channels["gear"][i] == 1
        elif t < 2.0:
            assert res.channels["gear"][i] == 2


def test_continuous_linear_inside_nan_outside():
    timeline = np.linspace(0.0, 6.0, 61)
    t_obs = np.array([1.0, 3.0, 5.0])
    x_obs = np.array([0.0, 100.0, 200.0])
    res = resample_driver("VER", timeline, t_obs, {"x": x_obs})
    idx_2 = int(2.0 / 0.1)
    assert res.channels["x"][idx_2] == pytest.approx(50.0, abs=1.0)
    assert math.isnan(res.channels["x"][int(0.5 / 0.1)])


# ==========================================================================
#  SECTION 6 — TELEMETRY UNITS
# ==========================================================================
from src.data.telemetry_units import (
    CANONICAL_UNITS, to_canonical, normalize_frame_entry, normalize_frame,
)


def test_canonical_units_has_required():
    for ch in ("speed", "throttle", "brake", "gear", "drs",
               "distance", "rel_dist", "lap", "tyre_life", "time"):
        assert ch in CANONICAL_UNITS


def test_brake_0_1_to_0_100():
    assert to_canonical("brake", 0) == 0.0
    assert to_canonical("brake", 1) == 100.0
    assert to_canonical("brake", 0.5) == 50.0


def test_brake_already_0_100():
    assert to_canonical("brake", 75.0) == 75.0


def test_brake_clamps():
    assert to_canonical("brake", 150.0) == 100.0
    assert to_canonical("brake", -5.0) == 0.0


def test_throttle_clamps():
    assert to_canonical("throttle", 150.0) == 100.0
    assert to_canonical("throttle", -10.0) == 0.0


def test_normalize_frame_entry_immutable():
    entry = {"brake": 1, "throttle": 80, "lap": 12.7, "speed": 250}
    out = normalize_frame_entry(entry)
    assert entry["brake"] == 1  # not mutated
    assert out["brake"] == 100.0
    assert out["lap"] == 13


def test_normalize_frame_each_driver():
    frame = {"t": 1.0, "drivers": {
        "VER": {"brake": 1, "throttle": 80, "lap": 12.7},
        "HAM": {"brake": 0, "throttle": 30, "lap": 12},
    }}
    out = normalize_frame(frame)
    assert out["drivers"]["VER"]["brake"] == 100.0
    assert out["drivers"]["HAM"]["brake"] == 0.0
    assert frame["drivers"]["VER"]["brake"] == 1  # immutable


def test_qualifying_race_brake_consistent():
    q = normalize_frame_entry({"brake": 1})
    r = normalize_frame_entry({"brake": 100.0})
    assert q == r


# ==========================================================================
#  SECTION 7 — QUALIFYING HELPERS
# ==========================================================================
from src.data.qualifying import (
    build_qualifying_frame, pick_fastest_lap, segment_lap_time,
    align_telemetry_arrays, set_final_frame_t,
)


class _Row:
    def __init__(self, **kw): self._d = kw
    def get(self, k, default=None): return self._d.get(k, default)

class _FakeLaps:
    def __init__(self, rows):
        self._rows = list(rows)
        self.empty = len(self._rows) == 0
    def pick_fastest(self):
        if not self._rows: return None
        return min(self._rows, key=lambda r: r.get("LapTime") or float("inf"))


def test_pick_fastest_none():
    assert pick_fastest_lap(None) is None
    assert pick_fastest_lap(_FakeLaps([])) is None


def test_segment_lap_time_valid():
    laps = _FakeLaps([_Row(LapTime="0 days 00:01:28.123000")])
    res = segment_lap_time(laps, "Q1")
    assert res.is_valid
    assert res.lap_time == pytest.approx(88.123, abs=1e-3)


def test_segment_lap_time_empty():
    res = segment_lap_time(_FakeLaps([]), "Q3")
    assert not res.available


def test_qualifying_frame_normalizes():
    row = {"brake": 1, "throttle": 80, "speed": 280}
    f = build_qualifying_frame(10.0, row)
    assert f["telemetry"]["brake"] == 100.0


def test_align_arrays_equal_length():
    rows = [{"x": 0.0, "y": 1.0}, {"x": 1.0, "y": 2.0}]
    arr = align_telemetry_arrays(rows)
    assert all(len(v) == 2 for v in arr.values())


def test_set_final_frame_t():
    frames = [{"t": 0.0}, {"t": 1.0}, {"t": 2.0}]
    set_final_frame_t(frames, 88.456)
    assert frames[-1]["t"] == 88.456
    assert frames[0]["t"] == 0.0


# ==========================================================================
#  SECTION 8 — LEADERBOARD (8 F1 scenarios)
# ==========================================================================
from src.analytics.leaderboard import (
    FrameLeaderboard, compute_progress, rank_frame, rank_frames,
)

TRACK = 5000.0

def _driver_lb(code, lap=1, dist=0.0, validity="active", in_pit=False,
               active=None, x=0.0, y=0.0, **extras):
    e = {"lap": lap, "dist": dist, "validity": validity, "in_pit": in_pit,
         "x": x, "y": y}
    if active is not None: e["active"] = active
    e.update(extras)
    return (code, e)

def _frame_lb(t, drivers, **extras):
    return {"t": t, "drivers": dict(drivers), **extras}


def test_compute_progress():
    assert compute_progress(1, 0.0, TRACK) == 0.0
    assert compute_progress(2, 0.0, TRACK) == TRACK
    assert compute_progress(1, float("nan"), TRACK) == float("-inf")


def test_20_car_race_ordering():
    drivers = [_driver_lb(f"D{i:02d}", lap=1, dist=i * 250.0)
               for i in range(20)]
    board = rank_frame(_frame_lb(10.0, drivers), TRACK)
    codes = [e.code for e in board.entries]
    assert codes[0] == "D19"
    assert all(e.position == idx + 1 for idx, e in enumerate(board.entries))


def test_pit_driver_loses_position():
    drivers = [
        _driver_lb("PIT", lap=1, dist=2000.0, in_pit=True),
        _driver_lb("RUN", lap=1, dist=1500.0),
        _driver_lb("OUT", lap=1, dist=3000.0),
    ]
    board = rank_frame(_frame_lb(10.0, drivers), TRACK)
    pos = {e.code: e.position for e in board.entries}
    assert pos["OUT"] == 1
    assert pos["PIT"] == 3


def test_retired_drops_to_bottom():
    drivers = [
        _driver_lb("RET", lap=1, dist=4000.0, validity="dnf", active=False),
        _driver_lb("A", lap=1, dist=3500.0),
        _driver_lb("B", lap=1, dist=3000.0),
    ]
    board = rank_frame(_frame_lb(10.0, drivers), TRACK)
    pos = {e.code: e.position for e in board.entries}
    assert pos["RET"] == 3


def test_lapped_driver_behind():
    drivers = [
        _driver_lb("LAPPED", lap=4, dist=4800.0),
        _driver_lb("LEAD", lap=5, dist=3000.0),
    ]
    board = rank_frame(_frame_lb(100.0, drivers), TRACK)
    assert board.entries[0].code == "LEAD"


def test_two_drivers_close():
    drivers = [
        _driver_lb("AAA", lap=3, dist=2500.0),
        _driver_lb("ZZZ", lap=3, dist=2500.5),
    ]
    board = rank_frame(_frame_lb(50.0, drivers), TRACK)
    assert board.entries[0].code == "ZZZ"


def test_telemetry_gap_no_phantom():
    drivers_gap = [
        _driver_lb("VER", lap=None, dist=None, validity="gap", active=False),
        _driver_lb("HAM", lap=2, dist=2100.0),
    ]
    board = rank_frame(_frame_lb(50.0, drivers_gap), TRACK)
    pos = {e.code: e.position for e in board.entries}
    assert pos["HAM"] == 1


def test_finish_line_crossing():
    pre = [_driver_lb("VER", lap=1, dist=4999.5)]
    post = [_driver_lb("VER", lap=2, dist=0.5)]
    b1 = rank_frame(_frame_lb(100.0, pre), TRACK)
    b2 = rank_frame(_frame_lb(100.04, post), TRACK)
    delta = b2.entries[0].progress - b1.entries[0].progress
    assert math.isclose(delta, TRACK - 4999.0, abs_tol=1.0)


def test_positions_dense():
    drivers = [_driver_lb(f"D{i}", lap=1, dist=100.0 * i) for i in range(5)]
    board = rank_frame(_frame_lb(0.0, drivers), TRACK)
    assert [e.position for e in board.entries] == [1, 2, 3, 4, 5]


def test_empty_board():
    board = rank_frame(_frame_lb(0.0, {}), TRACK)
    assert board.entries == []


def test_rank_frames_batch():
    frames = [
        _frame_lb(0.0, [_driver_lb("A", dist=0.0), _driver_lb("B", dist=10.0)]),
        _frame_lb(1.0, [_driver_lb("A", dist=100.0), _driver_lb("B", dist=200.0)]),
    ]
    boards = rank_frames(frames, TRACK)
    assert len(boards) == 2
    assert boards[0].entries[0].code == "B"


# ==========================================================================
#  SECTION 9 — REPLAY CLOCK
# ==========================================================================
from src.replay.clock import PLAYBACK_SPEEDS, Direction, EPS, ReplayClock


def _clock(total=10.0, fps=25.0, speed=1.0):
    return ReplayClock(total_seconds=total, fps=fps, initial_speed=speed)


def test_clock_defaults():
    c = _clock()
    assert c.replay_time == 0.0
    assert c.paused is False
    assert c.direction is Direction.FORWARD


def test_clock_validates():
    with pytest.raises(ValueError): ReplayClock(total_seconds=-1)
    with pytest.raises(ValueError): ReplayClock(total_seconds=10, fps=0)


@pytest.mark.parametrize("speed", PLAYBACK_SPEEDS)
def test_all_speeds_accepted(speed):
    assert _clock(speed=speed).playback_speed == speed


def test_tick_forward():
    c = _clock(total=10.0, speed=1.0)
    c.tick(1.0)
    assert c.replay_time == pytest.approx(1.0, abs=EPS)


def test_tick_paused_noop():
    c = _clock(speed=1.0)
    c.pause()
    c.tick(5.0)
    assert c.replay_time == 0.0


def test_end_of_replay():
    c = _clock(total=1.0, speed=1.0)
    c.tick(2.0)
    assert c.at_end and c.wrapped
    assert c.replay_time == 1.0


def test_rewind():
    c = _clock(speed=1.0)
    c.tick(2.0)
    c.set_direction(Direction.REWIND)
    c.tick(0.5)
    assert c.replay_time == pytest.approx(1.5, abs=EPS)


def test_rewind_past_zero():
    c = _clock(speed=1.0)
    c.tick(1.0)
    c.set_direction(Direction.REWIND)
    c.tick(5.0)
    assert c.at_start and c.replay_time == 0.0


def test_speed_change():
    c = _clock(speed=1.0)
    c.tick(1.0)
    c.set_speed(2.0)
    c.tick(1.0)
    assert c.replay_time == pytest.approx(3.0, abs=EPS)


def test_seek():
    c = _clock(total=10.0)
    c.seek(7.5)
    assert c.replay_time == pytest.approx(7.5, abs=EPS)


def test_seek_clamps():
    c = _clock(total=10.0)
    c.seek(-1.0)
    assert c.replay_time == 0.0
    c.seek(999.0)
    assert c.replay_time == 10.0


def test_restart():
    c = _clock(total=10.0, speed=2.0)
    c.tick(3.0)
    c.pause()
    c.restart()
    assert c.replay_time == 0.0 and not c.paused


def test_toggle():
    c = _clock()
    assert c.toggle() is True
    assert c.toggle() is False


# ==========================================================================
#  SECTION 10 — SAFETY CAR
# ==========================================================================
from src.replay.safety_car import (
    SCSource, SCPeriod, active_period_at, attach_sc, classify,
    close_open_periods, extract_sc_periods, simulate_sc_position,
)


def _sc_frame(t, drivers):
    return {"t": t, "drivers": dict(drivers)}

def _sc_d(code, lap=1, dist=0.0, active=True):
    return (code, {"lap": lap, "dist": dist, "active": active})


def test_classify_sc():
    assert classify("4") == "SC"
    assert classify("5") == "VSC"
    assert classify("1") == "OTHER"


def test_extract_single_sc():
    ts = [
        {"status": "1", "start_time": 0.0, "end_time": 10.0},
        {"status": "4", "start_time": 10.0, "end_time": 30.0},
        {"status": "1", "start_time": 30.0, "end_time": 100.0},
    ]
    periods = extract_sc_periods(ts)
    assert len(periods) == 1
    assert periods[0].kind == "SC"


def test_extract_no_sc():
    ts = [{"status": "1", "start_time": 0.0, "end_time": 100.0}]
    assert extract_sc_periods(ts) == []


def test_close_open_periods():
    periods = [SCPeriod(10.0, None, "4", "SC", 0)]
    closed = close_open_periods(periods, default_end=50.0)
    assert closed[0].end_time == 50.0


def test_active_period_at():
    p = SCPeriod(10.0, 30.0, "4", "SC", 0)
    assert active_period_at([p], 9.9) is None
    assert active_period_at([p], 20.0) is p
    assert active_period_at([p], 30.1) is None


def test_simulate_sc_no_drivers():
    assert simulate_sc_position({"drivers": {}}, track_length=5000.0) is None


def test_simulate_sc_picks_leader():
    frame = {"drivers": {
        "A": {"lap": 5, "dist": 100.0, "active": True},
        "B": {"lap": 5, "dist": 3000.0, "active": True},
    }}
    sim = simulate_sc_position(frame, track_length=5000.0, offset_m=150.0)
    assert sim["source"] == "simulated"
    assert sim["leader_code"] == "B"


def test_attach_sc_no_periods():
    frames = [_sc_frame(0.0, dict([_sc_d("A", 1, 100.0)]))]
    out = attach_sc(frames, periods=[], track_length=5000.0)
    assert out[0]["safety_car"]["source"] == "none"


def test_attach_sc_active_period():
    periods = [SCPeriod(5.0, 20.0, "4", "SC", 0)]
    frames = [_sc_frame(0.0, dict([_sc_d("A")])),
              _sc_frame(10.0, dict([_sc_d("A")])),
              _sc_frame(25.0, dict([_sc_d("A")]))]
    out = attach_sc(frames, periods, track_length=5000.0)
    assert out[0]["safety_car"]["source"] == "none"
    assert out[1]["safety_car"]["source"] == "simulated"
    assert out[2]["safety_car"]["source"] == "none"


def test_attach_sc_immutable():
    periods = [SCPeriod(0.0, 100.0, "4", "SC", 0)]
    frame = _sc_frame(10.0, dict([_sc_d("A", 1, 100.0)]))
    out = attach_sc([frame], periods, track_length=5000.0)
    assert "safety_car" not in frame
    assert "safety_car" in out[0]


# ==========================================================================
#  SECTION 11 — STREAMING PROTOCOL & BROKER
# ==========================================================================
from src.streaming.broker import StreamingBroker, Subscriber
from src.streaming.protocol import (
    PROTOCOL_VERSION, MessageType, ProtocolSchemaError,
    ProtocolVersionMismatch, REQUIRED_FIELDS, check_envelope, make_envelope,
)


def test_make_envelope_fields():
    env = make_envelope(MessageType.FRAME_UPDATE, session_id="s1",
                        seq=1, payload={"t": 0.0})
    for f in REQUIRED_FIELDS:
        assert f in env
    assert env["type"] == "FRAME_UPDATE"


def test_make_envelope_rejects_empty_session():
    with pytest.raises(ValueError):
        make_envelope(MessageType.FRAME_UPDATE, session_id="", seq=0, payload={})


def test_check_envelope_wrong_version():
    env = make_envelope(MessageType.HEARTBEAT, session_id="s1", seq=5,
                        payload={}, version=999)
    with pytest.raises(ProtocolVersionMismatch):
        check_envelope(env)


def test_check_envelope_missing_field():
    env = make_envelope(MessageType.HEARTBEAT, session_id="s1", seq=5, payload={})
    del env["session_id"]
    with pytest.raises(ProtocolSchemaError):
        check_envelope(env)


def test_broker_publishes_to_all():
    broker = StreamingBroker(session_id="s1")
    a, b = [], []
    broker.add_subscriber("A", deliver=lambda e: a.append(e))
    broker.add_subscriber("B", deliver=lambda e: b.append(e))
    broker.publish(MessageType.FRAME_UPDATE, {"i": 1})
    broker.dispatch_once()
    broker.dispatch_once()
    assert len(a) == 1 and len(b) == 1


def test_broker_preserves_order():
    broker = StreamingBroker(session_id="s1")
    d = []
    broker.add_subscriber("A", deliver=lambda e: d.append(e))
    for i in range(10):
        broker.publish(MessageType.FRAME_UPDATE, {"i": i})
    while broker.dispatch_once() > 0: pass
    assert [e["payload"]["i"] for e in d] == list(range(10))


def test_broker_backpressure_drops_oldest():
    broker = StreamingBroker(session_id="s1", queue_capacity=4)
    broker.add_subscriber("A", deliver=lambda e: None)
    for i in range(20):
        broker.publish(MessageType.FRAME_UPDATE, {"i": i})
    sub = broker._subscribers["A"]
    seen = []
    while (e := sub.pop()) is not None:
        seen.append(e["payload"]["i"])
    assert seen == [16, 17, 18, 19]


def test_publish_is_nonblocking():
    broker = StreamingBroker(session_id="s1")
    broker.add_subscriber("slow", deliver=lambda e: time_mod.sleep(0.5))
    t0 = time_mod.perf_counter()
    broker.publish(MessageType.FRAME_UPDATE, {"i": 1})
    assert time_mod.perf_counter() - t0 < 0.05


def test_remove_subscriber_stops_delivery():
    broker = StreamingBroker(session_id="s1")
    d = []
    broker.add_subscriber("A", deliver=lambda e: d.append(e))
    broker.publish(MessageType.FRAME_UPDATE, {"i": 1})
    broker.dispatch_once()
    broker.remove_subscriber("A")
    broker.publish(MessageType.FRAME_UPDATE, {"i": 2})
    broker.dispatch_once()
    assert len(d) == 1


def test_subscriber_queue_bounded():
    broker = StreamingBroker(session_id="s1", queue_capacity=8)
    broker.add_subscriber("A", deliver=lambda e: None)
    for _ in range(100):
        broker.publish(MessageType.FRAME_UPDATE, {"i": 1})
    assert len(broker._subscribers["A"].queue) <= 8


# ==========================================================================
#  SECTION 12 — CACHE
# ==========================================================================
from src.data.cache import (
    APP_VERSION, CACHE_SCHEMA_VERSION, CacheCorrupted, CacheKey,
    CacheSchemaMismatch, check_envelope as cache_check_envelope,
    envelope_for, is_cache_compatible, read_cache, write_cache_atomic,
)


@pytest.fixture
def cache_tmp():
    d = tempfile.mkdtemp(prefix="f1_cache_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cache_envelope_keys():
    env = envelope_for({"x": 1}, session_id="abc")
    assert env["__cache__"] is True
    assert env["schema_version"] == CACHE_SCHEMA_VERSION
    assert env["payload"] == {"x": 1}


def test_cache_round_trip(cache_tmp):
    p = os.path.join(cache_tmp, "x.pkl")
    payload = {"frames": [{"t": 0.0}], "meta": [1, 2, 3]}
    write_cache_atomic(p, payload)
    assert read_cache(p) == payload


def test_cache_atomic_on_failure(cache_tmp, monkeypatch):
    p = os.path.join(cache_tmp, "x.pkl")
    write_cache_atomic(p, {"v": 1})
    import src.data.cache as cm
    monkeypatch.setattr(cm.pickle, "dump", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        write_cache_atomic(p, {"v": 2})
    assert read_cache(p) == {"v": 1}


def test_cache_missing(cache_tmp):
    with pytest.raises(FileNotFoundError):
        read_cache(os.path.join(cache_tmp, "nope.pkl"))


def test_cache_corrupted(cache_tmp):
    p = os.path.join(cache_tmp, "x.pkl")
    with open(p, "wb") as f:
        f.write(b"not pickle")
    with pytest.raises(CacheCorrupted):
        read_cache(p)


def test_cache_wrong_schema(cache_tmp):
    p = os.path.join(cache_tmp, "x.pkl")
    env = envelope_for({}, schema_version=999)
    with open(p, "wb") as f:
        pickle.dump(env, f)
    with pytest.raises(CacheSchemaMismatch):
        read_cache(p)


def test_cache_key_filename():
    k = CacheKey(event_name="Monaco Grand Prix", session_type="R",
                  year=2024, round_number=8, suffix="race")
    assert k.to_filename() == "Monaco_Grand_Prix_race_telemetry.pkl"


def test_cache_compatible(cache_tmp):
    p = os.path.join(cache_tmp, "x.pkl")
    write_cache_atomic(p, {"v": 1})
    assert is_cache_compatible(p) is True
    assert is_cache_compatible(os.path.join(cache_tmp, "nope.pkl")) is False


# ==========================================================================
#  SECTION 13 — TYRE MODEL AVAILABILITY
# ==========================================================================
from src.analytics.tyre_model_availability import (
    TyreModelResult, available_result, is_placeholder, not_available, wrap_legacy,
)


def test_not_available_factory():
    r = not_available("missing")
    assert r.available is False
    assert r.actual_delta is None


def test_available_factory():
    r = available_result(baseline_pace=90.0, expected_pace=90.5,
                         actual_delta=-0.5, credible_low=90.2,
                         credible_high=91.0, overdriving=True,
                         tyre_age_laps=10, compound="MEDIUM")
    assert r.available is True
    assert r.actual_delta == -0.5


def test_unavailable_dict_no_placeholders():
    d = not_available("no model").to_public_dict()
    assert d["available"] is False
    assert d["actual_delta"] is None
    assert d["overdriving"] is None


def test_placeholder_detection():
    assert is_placeholder(0.0, False) is True
    assert is_placeholder(0.5, False) is False
    assert is_placeholder(0.0, True) is False


def test_wrap_legacy_placeholder():
    r = wrap_legacy(0.0, False, reason="no fit")
    assert r.available is False


def test_wrap_legacy_real():
    r = wrap_legacy(0.7, True, baseline_pace=89.0, expected_pace=88.3,
                    credible_low=88.0, credible_high=88.6,
                    tyre_age_laps=12, compound="HARD")
    assert r.available is True


# ==========================================================================
#  SECTION 14 — RESOURCE PATHS
# ==========================================================================
from src.lib.resource_paths import (
    _find_project_root, cache_dir, computed_data_dir,
    project_root, resolve, resources_dir,
)


def test_find_project_root(tmp_path):
    (tmp_path / "README.md").touch()
    (tmp_path / "sub").mkdir()
    found = _find_project_root(tmp_path / "sub")
    assert found is not None
    assert found.resolve() == tmp_path.resolve()


def test_project_root_exists():
    root = project_root()
    assert root.is_dir()
    sentinels = ("pyproject.toml", "setup.py", "setup.cfg", "README.md", ".git")
    assert any((root / s).exists() for s in sentinels)


def test_resolve_absolute():
    assert resolve("foo", "bar.txt").is_absolute()


def test_resolve_cwd_independent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = resolve("does_not_exist.txt")
    assert p.is_absolute()
    assert p.parent != tmp_path.resolve()


def test_cache_dir_exists():
    assert cache_dir().is_dir()


def test_resolve_readme():
    cwd = os.getcwd()
    try:
        os.chdir(os.path.dirname(__file__))
        p = resolve("README.md")
        assert "README.md" in str(p)
        assert p.exists()
    finally:
        os.chdir(cwd)


# ==========================================================================
#  SECTION 15 — MODULE IMPORT SMOKE TESTS
# ==========================================================================
MODULES = [
    "src.bayesian_tyre_model",
    "src.cli.race_selection",
    "src.f1_data",
    "src.gui.insights_menu",
    "src.gui.pit_wall_window",
    "src.gui.race_selection",
    "src.insights.tyre_strategy_window",
    "src.interfaces.qualifying",
    "src.interfaces.race_replay",
    "src.lib.season",
    "src.lib.settings",
    "src.lib.time",
    "src.lib.tyres",
    "src.run_session",
    "src.services.stream",
    "src.tyre_degradation_integration",
    "src.ui_components",
]

OPTIONAL = {"arcade", "fastf1", "matplotlib", "numpy", "pandas",
            "pyglet", "PySide6", "questionary", "rich", "prompt_toolkit",
            "PIL", "Pillow"}


@pytest.mark.parametrize("module_name", MODULES)
def test_module_importable(module_name):
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name.split(".")[0] in OPTIONAL:
            pytest.skip(f"missing: {exc.name}")
        raise
    except ImportError as exc:
        msg = str(exc)
        if any(k in msg for k in ("PyQt", "PySide", "matplotlib")):
            pytest.skip(f"optional binding: {exc}")
        raise
