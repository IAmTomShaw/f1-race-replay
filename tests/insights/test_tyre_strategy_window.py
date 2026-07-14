from src.insights.tyre_strategy_window import is_new_session, next_session_tracking_state


def test_no_reset_with_no_existing_stints():
    # Nothing loaded yet - lap 1 of a first session is not a "drop".
    assert is_new_session(has_existing_stints=False, current_lap=1, max_seen_lap=1) is False


def test_no_reset_during_normal_progression():
    assert is_new_session(has_existing_stints=True, current_lap=15, max_seen_lap=14) is False


def test_no_reset_on_one_lap_of_jitter():
    # A live feed can report a lap number one behind the running max
    # near a lap boundary; that alone must not wipe real stint data.
    assert is_new_session(has_existing_stints=True, current_lap=13, max_seen_lap=14) is False


def test_resets_when_qualifying_session_carries_into_race():
    # The #293 scenario: qualifying state (max_seen_lap in the high
    # teens/twenties) is loaded from computed_data/tyre_state.json, then
    # the race's first telemetry frame reports lap 1.
    assert is_new_session(has_existing_stints=True, current_lap=1, max_seen_lap=18) is True


def test_no_reset_when_stints_dict_is_empty_even_if_lap_drops():
    # An empty stints dict means there is nothing stale to protect
    # against carrying over, regardless of the lap numbers.
    assert is_new_session(has_existing_stints=False, current_lap=1, max_seen_lap=20) is False


def test_boundary_is_exclusive_at_default_tolerance():
    # A drop of exactly the tolerance (1 lap) is still jitter, not a
    # new session; a drop of tolerance + 1 is.
    assert is_new_session(has_existing_stints=True, current_lap=13, max_seen_lap=14, tolerance=1) is False
    assert is_new_session(has_existing_stints=True, current_lap=12, max_seen_lap=14, tolerance=1) is True


def test_next_session_tracking_state_rebases_max_seen_lap_on_reset():
    should_reset, new_max = next_session_tracking_state(
        has_existing_stints=True, current_lap=1, max_seen_lap=25
    )
    assert should_reset is True
    assert new_max == 1  # not 25 - this is the exact bug this function exists to prevent


def test_next_session_tracking_state_grows_max_seen_lap_without_reset():
    should_reset, new_max = next_session_tracking_state(
        has_existing_stints=True, current_lap=15, max_seen_lap=14
    )
    assert should_reset is False
    assert new_max == 15


def _simulate_session(lap_sequence, initial_max_seen_lap):
    """Drives next_session_tracking_state() the same way
    on_telemetry_data does, frame by frame, without needing a Qt window
    or telemetry client. Returns, for each lap in ``lap_sequence``,
    whether that frame triggered a reset - calling the real function
    (not a re-implementation of its logic) so a regression in the
    actual reset-and-rebase behaviour shows up here too.
    """
    stints = {"VER": ["stale stint"]}
    max_seen_lap = initial_max_seen_lap
    fired = []
    for lap in lap_sequence:
        should_reset, max_seen_lap = next_session_tracking_state(bool(stints), lap, max_seen_lap)
        fired.append(should_reset)
        if should_reset:
            stints = {}
        stints.setdefault("VER", []).append(f"stint at lap {lap}")
    return fired


def test_reset_fires_exactly_once_for_a_new_session_then_stops():
    # Regression test for a bug introduced by an earlier version of this
    # fix: max_seen_lap must be rebased to the new session on reset, or
    # every following frame keeps comparing against the stale (higher)
    # baseline and re-fires the reset every time, never letting the new
    # session's own stints accumulate.
    fired = _simulate_session([1, 2, 3, 4, 5, 10, 20, 30], initial_max_seen_lap=25)
    assert fired == [True, False, False, False, False, False, False, False]


def test_no_reset_at_all_during_normal_same_session_progression():
    fired = _simulate_session([1, 2, 3, 4, 5], initial_max_seen_lap=0)
    assert fired == [False, False, False, False, False]
