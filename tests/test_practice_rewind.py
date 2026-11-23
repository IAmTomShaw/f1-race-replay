from types import SimpleNamespace
from unittest.mock import MagicMock

import arcade
import numpy as np

from src.interfaces.practice import PracticeReplay


def _replay_at_end(n=101):
    times = np.linspace(0.0, 100.0, n)
    v = SimpleNamespace(
        chart_active=True, loaded_telemetry={"VER": {}}, n_frames=n, frame_index=n - 1,
        _times=times, play_time=100.0, play_start_t=0.0, paused=True, playback_speed=1.0,
        is_rewinding=False, is_forwarding=False, was_paused_before_hold=True,
        race_controls_comp=MagicMock(), qualifying_lap_time_comp=MagicMock(),
        controls_popup_comp=MagicMock(), legend_comp=MagicMock(), leaderboard=MagicMock(),
        toggle_drs_zones=True,
    )
    v.controls_popup_comp.on_mouse_press.return_value = False
    v.legend_comp.on_mouse_press.return_value = False
    v.is_lap_complete = lambda: PracticeReplay.is_lap_complete(v)
    return v


def test_left_arrow_starts_rewinding_after_the_replay_has_finished():
    v = _replay_at_end()
    PracticeReplay.on_key_press(v, arcade.key.LEFT, 0)
    assert v.is_rewinding is True


def test_other_playback_keys_stay_disabled_after_the_replay_has_finished():
    v = _replay_at_end()
    PracticeReplay.on_key_press(v, arcade.key.RIGHT, 0)
    PracticeReplay.on_key_press(v, arcade.key.SPACE, 0)
    assert v.is_forwarding is False
    assert v.paused is True


def test_rewind_button_click_still_works_after_the_replay_has_finished():
    v = _replay_at_end()
    v.race_controls_comp._point_in_rect.return_value = True
    PracticeReplay.on_mouse_press(v, 10, 10, arcade.MOUSE_BUTTON_LEFT, 0)
    v.race_controls_comp.on_mouse_press.assert_called_once()


def test_other_buttons_stay_inactive_after_the_replay_has_finished():
    v = _replay_at_end()
    v.race_controls_comp._point_in_rect.return_value = False
    PracticeReplay.on_mouse_press(v, 10, 10, arcade.MOUSE_BUTTON_LEFT, 0)
    v.race_controls_comp.on_mouse_press.assert_not_called()


def test_play_time_cannot_run_past_the_end_so_rewind_responds_immediately():
    v = _replay_at_end()
    v.is_forwarding = True
    for _ in range(100):
        PracticeReplay.on_update(v, 0.1)
    assert v.play_time <= 100.0

    v.is_forwarding = False
    v.is_rewinding = True
    PracticeReplay.on_update(v, 0.5)
    assert v.frame_index < v.n_frames - 1
