from types import SimpleNamespace

from src.interfaces.qualifying import QualifyingReplay


def _seg(tag):
    return {"frames": [{"t": 0.0, "telemetry": {"tag": tag}}], "sector_times": {"s1": 1.0}}


def _viewer(loaded_code="LEC", loaded_segment="Q3"):
    # VER pole (Q1-Q3), LEC and HAM reach Q3, NOR is out in Q1.
    data = {
        "results": [{"code": c} for c in ("VER", "LEC", "HAM", "NOR")],
        "telemetry": {
            "VER": {"Q1": _seg("VER-Q1"), "Q2": _seg("VER-Q2"), "Q3": _seg("VER-Q3")},
            "LEC": {"Q1": _seg("LEC-Q1"), "Q2": _seg("LEC-Q2"), "Q3": _seg("LEC-Q3")},
            "HAM": {"Q1": _seg("HAM-Q1"), "Q2": _seg("HAM-Q2"), "Q3": _seg("HAM-Q3")},
            "NOR": {"Q1": _seg("NOR-Q1"), "Q2": {"frames": []}, "Q3": {"frames": []}},
        },
    }
    return SimpleNamespace(
        data=data,
        show_comparison_telemetry=True,
        comparison_driver_code=None,
        loaded_driver_code=loaded_code,
        loaded_driver_segment=loaded_segment,
        _resolve_comparison=lambda: None,  # replaced below
    )


def _bind(v):
    v._resolve_comparison = lambda: QualifyingReplay._resolve_comparison(v)
    return v


def test_default_is_pole_q3():
    v = _bind(_viewer())
    code, segment, frames, sectors = v._resolve_comparison()
    assert (code, segment) == ("VER", "Q3")
    assert frames[0]["telemetry"]["tag"] == "VER-Q3"
    assert sectors == {"s1": 1.0}


def test_default_hidden_when_loaded_lap_is_pole_q3():
    v = _bind(_viewer(loaded_code="VER", loaded_segment="Q3"))
    assert v._resolve_comparison() is None


def test_toggle_off_hides_comparison():
    v = _bind(_viewer())
    v.show_comparison_telemetry = False
    assert v._resolve_comparison() is None


def test_tab_moves_to_next_driver_and_skips_loaded_lap():
    v = _bind(_viewer(loaded_code="LEC", loaded_segment="Q3"))
    QualifyingReplay._cycle_comparison_driver(v, 1)
    assert v.comparison_driver_code == "LEC"  # VER -> LEC; same driver but only Q3 equals loaded, fallback Q2
    code, segment, *_ = v._resolve_comparison()
    assert (code, segment) == ("LEC", "Q2")


def test_cycle_uses_loaded_segment_and_falls_back_for_early_exit():
    v = _bind(_viewer(loaded_code="HAM", loaded_segment="Q3"))
    v.comparison_driver_code = "HAM"
    QualifyingReplay._cycle_comparison_driver(v, 1)
    assert v.comparison_driver_code == "NOR"
    code, segment, *_ = v._resolve_comparison()
    assert (code, segment) == ("NOR", "Q1")  # no Q3/Q2 lap, falls back to Q1


def test_shift_tab_goes_backwards_and_wraps():
    v = _bind(_viewer(loaded_code="HAM", loaded_segment="Q3"))
    QualifyingReplay._cycle_comparison_driver(v, -1)  # from pole backwards wraps to the last driver
    assert v.comparison_driver_code == "NOR"
    QualifyingReplay._cycle_comparison_driver(v, -1)
    assert v.comparison_driver_code == "HAM"


def test_cycle_reenables_comparison():
    v = _bind(_viewer())
    v.show_comparison_telemetry = False
    QualifyingReplay._cycle_comparison_driver(v, 1)
    assert v.show_comparison_telemetry is True


def _delta_viewer():
    return SimpleNamespace(loaded_driver_code="LEC", loaded_driver_segment="Q3", _delta_cache=None)


def _linear_lap(lap_time, n=51):
    return [{"t": lap_time * i / (n - 1), "telemetry": {"rel_dist": i / (n - 1)}} for i in range(n)]


def test_time_delta_is_cached_per_lap_pair_and_axis_limit_is_stable():
    v = _delta_viewer()
    slow, fast = _linear_lap(91.8), _linear_lap(91.0)

    first = QualifyingReplay._get_time_delta(v, slow, fast, "VER", "Q3")
    again = QualifyingReplay._get_time_delta(v, slow, fast, "VER", "Q3")
    assert first[1] is again[1]  # same cached array, not recomputed

    rel_dist, delta, limit = first
    assert abs(delta[-1] - 0.8) < 1e-9
    assert limit == 0.8  # rounded up to the next 0.1 s

    # a different comparison driver invalidates the cache
    other = QualifyingReplay._get_time_delta(v, slow, _linear_lap(91.6), "HAM", "Q3")
    assert other[1] is not first[1]
    assert abs(other[1][-1] - 0.2) < 1e-9


def test_time_delta_axis_has_a_minimum_range_for_very_close_laps():
    v = _delta_viewer()
    _, _, limit = QualifyingReplay._get_time_delta(v, _linear_lap(91.05), _linear_lap(91.0), "VER", "Q3")
    assert limit == 0.2


def test_time_delta_is_none_when_comparison_has_no_data():
    v = _delta_viewer()
    assert QualifyingReplay._get_time_delta(v, _linear_lap(91.0), [], "VER", "Q3") is None


# --- rewinding once the replay has finished -------------------------------------------------

from unittest.mock import MagicMock

import numpy as np
import arcade


def _replay_at_end(n=101):
    times = np.linspace(0.0, 100.0, n)
    v = SimpleNamespace(
        chart_active=True, loaded_telemetry={"frames": []}, n_frames=n, frame_index=n - 1,
        _times=times, play_time=100.0, play_start_t=0.0, paused=True, playback_speed=1.0,
        is_rewinding=False, is_forwarding=False, was_paused_before_hold=True,
        race_controls_comp=MagicMock(), qualifying_lap_time_comp=MagicMock(),
        controls_popup_comp=MagicMock(), toggle_drs_zones=True,
    )
    v.is_lap_complete = lambda: QualifyingReplay.is_lap_complete(v)
    return v


def test_left_arrow_starts_rewinding_after_the_replay_has_finished():
    v = _replay_at_end()
    QualifyingReplay.on_key_press(v, arcade.key.LEFT, 0)
    assert v.is_rewinding is True


def test_other_playback_keys_stay_disabled_after_the_replay_has_finished():
    v = _replay_at_end()
    QualifyingReplay.on_key_press(v, arcade.key.RIGHT, 0)
    QualifyingReplay.on_key_press(v, arcade.key.SPACE, 0)
    assert v.is_forwarding is False
    assert v.paused is True


def test_rewind_button_click_still_works_after_the_replay_has_finished():
    v = _replay_at_end()
    v.controls_popup_comp.on_mouse_press.return_value = False
    v.legend_comp = MagicMock(); v.legend_comp.on_mouse_press.return_value = False
    v.leaderboard = MagicMock()
    v.selected_driver = None
    controls = v.race_controls_comp
    controls._point_in_rect.return_value = True
    QualifyingReplay.on_mouse_press(v, 10, 10, arcade.MOUSE_BUTTON_LEFT, 0)
    controls.on_mouse_press.assert_called_once()


def test_other_buttons_stay_inactive_after_the_replay_has_finished():
    v = _replay_at_end()
    v.controls_popup_comp.on_mouse_press.return_value = False
    v.legend_comp = MagicMock(); v.legend_comp.on_mouse_press.return_value = False
    v.leaderboard = MagicMock()
    v.selected_driver = None
    v.race_controls_comp._point_in_rect.return_value = False
    QualifyingReplay.on_mouse_press(v, 10, 10, arcade.MOUSE_BUTTON_LEFT, 0)
    v.race_controls_comp.on_mouse_press.assert_not_called()


def test_play_time_cannot_run_past_the_end_so_rewind_responds_immediately():
    v = _replay_at_end()
    v.is_forwarding = True       # user held "forward" for a while at the end
    for _ in range(100):
        QualifyingReplay.on_update(v, 0.1)
    assert v.play_time <= 100.0  # clamped, not 100 + 30s of overshoot

    v.is_forwarding = False
    v.is_rewinding = True        # one short rewind step must move the frame back
    QualifyingReplay.on_update(v, 0.5)
    assert v.frame_index < v.n_frames - 1
