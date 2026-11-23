from typing import Optional, Tuple

import numpy as np


def compute_time_delta(frames: list, comparison_frames: list) -> Optional[Tuple[np.ndarray, np.ndarray]]:
  """
  Time delta of a lap against a comparison lap, matched by track position.

  For every frame of the primary lap, find the time the comparison lap needed to reach the
  same relative distance and subtract it. Returns (rel_dist, delta), both the same length as
  `frames` (NaN where a frame has no usable sample), or None when either lap has no usable data.

    delta > 0  primary lap is behind (has lost time)
    delta < 0  primary lap is ahead  (has gained time)
  """
  t_primary, d_primary = _time_and_distance(frames)
  t_comp, d_comp = _time_and_distance(comparison_frames)

  valid_comp = ~(np.isnan(t_comp) | np.isnan(d_comp))
  if valid_comp.sum() < 2 or np.isnan(d_primary).all():
    return None
  t_comp, d_comp = t_comp[valid_comp], d_comp[valid_comp]

  # np.interp needs a non-decreasing x axis; resampling noise can make rel_dist step back slightly
  d_comp = np.maximum.accumulate(d_comp)
  comp_time_at_same_point = np.interp(d_primary, d_comp, t_comp)
  return d_primary, t_primary - comp_time_at_same_point


def _time_and_distance(frames: list) -> Tuple[np.ndarray, np.ndarray]:
  t = np.full(len(frames or []), np.nan)
  d = np.full(len(frames or []), np.nan)
  for i, frame in enumerate(frames or []):
    tel = frame.get("telemetry") if isinstance(frame, dict) else None
    if isinstance(tel, dict) and frame.get("t") is not None and tel.get("rel_dist") is not None:
      t[i] = float(frame["t"])
      d[i] = float(tel["rel_dist"])

  # f1_data stamps the final frame with the exact lap time, but the resampled rel_dist stops
  # slightly short of 1.0 (~0.998). That frame is the finish line, so pin it there; otherwise
  # two laps are compared at different points and the final delta no longer equals the lap-time gap.
  valid = np.flatnonzero(~(np.isnan(t) | np.isnan(d)))
  if len(valid):
    d[valid[-1]] = 1.0
  return t, d
