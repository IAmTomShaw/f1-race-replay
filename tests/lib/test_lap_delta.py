import numpy as np

from src.lib.lap_delta import compute_time_delta


def _lap(lap_time, n=101, rel_dist=None):
  """A lap driven at constant speed: rel_dist rises linearly while t goes 0 -> lap_time."""
  t = np.linspace(0.0, lap_time, n)
  d = np.linspace(0.0, 1.0, n) if rel_dist is None else rel_dist
  return [{"t": float(ti), "telemetry": {"rel_dist": float(di)}} for ti, di in zip(t, d)]


def test_slower_lap_has_positive_growing_delta():
  rel_dist, delta = compute_time_delta(_lap(91.5), _lap(91.0))

  assert len(delta) == 101
  assert delta[0] == 0.0
  assert np.all(np.diff(delta) >= -1e-9)
  assert abs(delta[-1] - 0.5) < 1e-9  # ends at the lap-time difference
  assert rel_dist[-1] == 1.0


def test_faster_lap_has_negative_delta():
  _, delta = compute_time_delta(_lap(90.0), _lap(91.0))
  assert abs(delta[-1] + 1.0) < 1e-9


def test_same_lap_has_zero_delta():
  _, delta = compute_time_delta(_lap(91.0), _lap(91.0))
  assert np.allclose(delta, 0.0)


def test_laps_with_different_frame_counts_are_matched_by_distance_not_index():
  _, delta = compute_time_delta(_lap(92.0, n=200), _lap(91.0, n=150))
  assert abs(delta[-1] - 1.0) < 1e-9
  assert abs(delta[99] - 0.5025) < 0.01  # roughly half-way, half the gap


def test_backwards_step_in_comparison_distance_does_not_break_interpolation():
  d = np.linspace(0.0, 1.0, 101)
  d[50] = d[49] - 0.001  # resampling noise
  _, delta = compute_time_delta(_lap(91.0), _lap(91.0, rel_dist=d))
  assert not np.isnan(delta).any()
  assert abs(delta[-1]) < 1e-9


def test_missing_samples_stay_aligned_with_primary_frames():
  primary = _lap(91.5)
  primary[10]["telemetry"]["rel_dist"] = None
  rel_dist, delta = compute_time_delta(primary, _lap(91.0))

  assert len(delta) == len(primary)  # same length, so frame_index lines up
  assert np.isnan(delta[10])
  assert not np.isnan(delta[11])


def test_returns_none_without_usable_data():
  assert compute_time_delta([], _lap(91.0)) is None
  assert compute_time_delta(_lap(91.0), []) is None
  assert compute_time_delta(_lap(91.0), [{"t": 0.0, "telemetry": {}}]) is None


def test_final_frame_is_the_finish_line_even_if_rel_dist_stops_short_of_one():
  # Mirrors the cached data: resampled rel_dist ends ~0.998 but the last t is the exact lap time.
  def short_lap(lap_time, end_dist):
    d = np.linspace(0.0, end_dist, 101)
    return _lap(lap_time, rel_dist=d)

  _, delta = compute_time_delta(short_lap(91.427, 0.9977), short_lap(91.373, 0.9982))
  assert abs(delta[-1] - 0.054) < 1e-9
