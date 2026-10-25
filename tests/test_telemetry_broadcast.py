from types import SimpleNamespace

import pytest

race_replay = pytest.importorskip("src.interfaces.race_replay")

LAP_TIMES = {"VER": [{"lap": 1, "time_s": 90.0}]}
STATUS_LAPS = [{"status": "4", "start_lap": 3, "end_lap": 5}]


class FakeStream:
    def __init__(self):
        self.clients = ["viewer"]
        self.sent = []

    def broadcast(self, data):
        self.sent.append(data)


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(race_replay.time, "monotonic", lambda: clock.now)
    return clock


def make_window():
    frame = {"t": 10.0, "lap": 1, "drivers": {"VER": {"x": 0.0, "y": 0.0, "lap": 1}}}
    return SimpleNamespace(
        telemetry_stream=FakeStream(), frames=[frame], frame_index=0.0, n_frames=1, track_statuses=[],
        race_control_messages=[], driver_colors={}, playback_speed=1.0, paused=False, circuit_length_m=5000.0,
        total_laps=57, _ref_total_length=5000.0, _project_to_reference=lambda x, y: 0.0,
        _precomputed_lap_times=LAP_TIMES, _precomputed_status_laps=STATUS_LAPS,
        _lap_data_sent_at=None, _lap_data_client_count=0,
    )


def broadcast(window):
    race_replay.F1RaceReplayWindow._broadcast_telemetry_state(window)
    return window.telemetry_stream.sent[-1]


def has_lap_data(payload):
    return payload.get("lap_times") is LAP_TIMES and payload.get("status_laps") is STATUS_LAPS


def test_first_broadcast_includes_lap_data(clock):
    assert has_lap_data(broadcast(make_window()))


def test_lap_data_is_not_resent_on_every_broadcast(clock):
    window = make_window()
    broadcast(window)

    clock.now += 0.5
    payload = broadcast(window)

    assert "lap_times" not in payload and "status_laps" not in payload
    assert payload["frame"] is window.frames[0]


def test_lap_data_is_sent_when_a_new_client_connects(clock):
    window = make_window()
    broadcast(window)

    window.telemetry_stream.clients.append("lap chart")
    clock.now += 0.5

    assert has_lap_data(broadcast(window))


def test_lap_data_is_resent_periodically(clock):
    window = make_window()
    broadcast(window)

    clock.now += 2.0

    assert has_lap_data(broadcast(window))
