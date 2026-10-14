"""
Driver telemetry resampling with explicit validity intervals.

The legacy implementation in ``src/f1_data.get_race_telemetry`` used
``numpy.interp`` to resample every driver's telemetry onto a single
global timeline. ``numpy.interp`` clamps to the first/last observed
sample, which silently *invents* driver motion before the driver
appears (DNS) and after the driver disappears (DNF / out of power /
last sample stale).

This module replaces that with an explicit per-driver validity
contract:

* ``valid_start``  : first replay-relative second the driver is
                     considered *active*.
* ``valid_end``    : last replay-relative second the driver is
                     considered *active*. After this, the driver is
                     marked ``"post"`` and excluded from ranking.
* Gaps (NaN/empty windows) inside the active interval are marked
  ``"gap"`` and *not* interpolated.

Channels are split into two classes:

* CONTINUOUS (e.g. x, y, speed, throttle, brake) -> linear interp
  inside the active region, boundary-clamp outside, NaN in gaps.
* DISCRETE   (gear, drs, lap, tyre)             -> step (forward-fill)
  inside the active region, ``None`` outside, last-valid during gaps.

The function is pure-Python + numpy; no FastF1, no Arcade, no PySide6.
This keeps the algorithm unit-testable in a bare Python environment
and is safe to import from anywhere in the project.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Channel classification
# ---------------------------------------------------------------------------
class ChannelKind(str, Enum):
    CONTINUOUS = "continuous"  # linear interpolation
    DISCRETE = "discrete"      # step / forward-fill


# Default mapping from canonical channel name -> kind. Callers may
# override per-call.
DEFAULT_CONTINUOUS = (
    "x", "y", "z",
    "speed", "throttle", "brake",
    "dist", "rel_dist", "tyre_life",
)
DEFAULT_DISCRETE = (
    "gear", "drs", "lap", "tyre", "position",
)


def channel_kind(name: str) -> ChannelKind:
    n = name.lower()
    if n in DEFAULT_CONTINUOUS:
        return ChannelKind.CONTINUOUS
    if n in DEFAULT_DISCRETE:
        return ChannelKind.DISCRETE
    return ChannelKind.CONTINUOUS


# ---------------------------------------------------------------------------
# Validity markers
# ---------------------------------------------------------------------------
class Validity(str, Enum):
    PRE = "pre"           # before valid_start
    ACTIVE = "active"     # inside [valid_start, valid_end]
    GAP = "gap"           # inside the active region but no telemetry
    POST = "post"         # after valid_end
    DNS = "dns"           # no telemetry at all
    DNF = "dnf"           # never reached valid_end (e.g. retired)
    FINISHED = "finished" # reached end of race (caller-declared)


@dataclass
class DriverValidity:
    """Per-driver validity window. All times are *replay-relative* seconds."""
    code: str
    valid_start: float
    valid_end: float
    finished: bool = False
    retired: bool = False


# ---------------------------------------------------------------------------
# Per-channel interpolation helpers
# ---------------------------------------------------------------------------
def _interp_continuous(timeline: np.ndarray,
                       t_obs: np.ndarray,
                       v_obs: np.ndarray) -> np.ndarray:
    """Linear interp on the active region; NaN elsewhere.

    ``t_obs`` and ``v_obs`` are 1-D arrays. If a NaN/empty segment is
    encountered, the interpolation masks it out so the result has
    NaNs in the gap.
    """
    out = np.full_like(timeline, np.nan, dtype=float)
    if t_obs.size == 0 or v_obs.size == 0:
        return out
    finite = np.isfinite(t_obs) & np.isfinite(v_obs)
    if not np.any(finite):
        return out
    t_f = t_obs[finite]
    v_f = v_obs[finite]
    if t_f.size == 1:
        idx = np.searchsorted(timeline, t_f[0])
        if 0 <= idx < len(timeline):
            out[idx] = v_f[0]
        return out
    interp_vals = np.interp(timeline, t_f, v_f)
    inside = (timeline >= t_f[0]) & (timeline <= t_f[-1])
    out[inside] = interp_vals[inside]
    return out


def _step_discrete(timeline: np.ndarray,
                   t_obs: np.ndarray,
                   v_obs: np.ndarray) -> np.ndarray:
    """Forward-fill (step) on the active region; NaN elsewhere."""
    out = np.full(len(timeline), np.nan, dtype=float)
    if t_obs.size == 0 or v_obs.size == 0:
        return out
    finite = np.isfinite(t_obs) & np.isfinite(v_obs)
    t_f = t_obs[finite]
    v_f = v_obs[finite]
    if t_f.size == 0:
        return out
    idxs = np.searchsorted(t_f, timeline, side="right") - 1
    valid = (idxs >= 0) & (timeline <= t_f[-1]) & (timeline >= t_f[0])
    idxs = np.clip(idxs, 0, len(t_f) - 1)
    out[valid] = v_f[idxs[valid]]
    return out


def safe_int(x: Any) -> Optional[int]:
    """Convert ``x`` to int, returning ``None`` for NaN/Inf/None."""
    if x is None:
        return None
    try:
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        v = int(round(f))
    except (TypeError, ValueError, OverflowError):
        return None
    return v


def safe_float(x: Any) -> Optional[float]:
    """Convert ``x`` to float, returning ``None`` for NaN/Inf/None."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@dataclass
class ResampledDriver:
    """Result of resampling a single driver onto the global timeline."""
    code: str
    timeline: np.ndarray
    channels: Dict[str, np.ndarray] = field(default_factory=dict)
    validity: np.ndarray = field(default_factory=lambda: np.array([], dtype=object))
    valid_start: float = 0.0
    valid_end: float = 0.0
    has_any_telemetry: bool = False

    def is_active(self, frame_idx: int) -> bool:
        if frame_idx < 0 or frame_idx >= len(self.validity):
            return False
        return self.validity[frame_idx] in (Validity.ACTIVE, Validity.FINISHED)


def resample_driver(
    code: str,
    timeline: np.ndarray,
    t_obs: np.ndarray,
    channels: Dict[str, np.ndarray],
    *,
    channel_kinds: Optional[Dict[str, ChannelKind]] = None,
    finished: bool = False,
    retired: bool = False,
) -> ResampledDriver:
    """Resample one driver's telemetry onto ``timeline``."""
    timeline = np.asarray(timeline, dtype=float)
    n = len(timeline)
    validity = np.array([Validity.PRE] * n, dtype=object)

    if t_obs is None or len(t_obs) == 0 or len(channels) == 0:
        validity[:] = Validity.DNS
        return ResampledDriver(
            code=code,
            timeline=timeline,
            channels={k: np.full(n, np.nan) for k in channels},
            validity=validity,
            valid_start=float("inf"),
            valid_end=float("-inf"),
            has_any_telemetry=False,
        )

    t_obs = np.asarray(t_obs, dtype=float)
    valid_start = float(t_obs.min())
    valid_end = float(t_obs.max())
    if not np.isfinite(valid_start) or not np.isfinite(valid_end):
        validity[:] = Validity.DNS
        return ResampledDriver(
            code=code,
            timeline=timeline,
            channels={k: np.full(n, np.nan) for k in channels},
            validity=validity,
            valid_start=valid_start,
            valid_end=valid_end,
            has_any_telemetry=False,
        )

    # Mark validity per-frame.
    pre = timeline < valid_start - 1e-9
    post = timeline > valid_end + 1e-9
    inside = ~pre & ~post
    validity[pre] = Validity.PRE
    if finished:
        validity[post] = Validity.FINISHED
    elif retired:
        validity[post] = Validity.DNF
    else:
        validity[post] = Validity.POST

    if len(timeline) >= 2:
        dt = float(np.min(np.diff(timeline)))
    else:
        dt = 1.0

    if len(t_obs_sorted := np.sort(t_obs)) >= 2:
        obs_diffs = np.diff(t_obs_sorted)
        median_cadence = float(np.median(obs_diffs))
        gap_threshold = max(5.0 * median_cadence, dt)
    else:
        gap_threshold = max(2.0 * dt, 1e-6)
        obs_diffs = np.array([])
        t_obs_sorted = t_obs_sorted if len(t_obs_sorted) else np.array([])

    gap_mask = np.zeros(len(timeline), dtype=bool)
    if len(t_obs_sorted) >= 2 and gap_threshold > 0:
        gap_edges_idx = np.where(obs_diffs > gap_threshold + 1e-9)[0]
        for i in gap_edges_idx:
            lo = float(t_obs_sorted[i])
            hi = float(t_obs_sorted[i + 1])
            gap_mask |= (timeline > lo + 1e-9) & (timeline < hi - 1e-9)
    elif len(t_obs_sorted) == 1:
        d = np.abs(timeline - t_obs_sorted[0])
        gap_mask = d > gap_threshold
    gap_mask &= inside
    validity[gap_mask] = Validity.GAP

    out_channels: Dict[str, np.ndarray] = {}
    for name, arr in channels.items():
        v = np.asarray(arr, dtype=float)
        kind = (channel_kinds or {}).get(name, channel_kind(name))
        if kind is ChannelKind.DISCRETE:
            resampled = _step_discrete(timeline, t_obs, v)
        else:
            resampled = _interp_continuous(timeline, t_obs, v)
            if resampled.size and gap_mask.any():
                resampled = resampled.copy()
                resampled[gap_mask] = np.nan

        # When a driver has finished the race (finished=True), hold their
        # final finite observation across post-finish frames so early
        # finishers stay at their final position/lap/distance while
        # remaining cars finish the race.
        if finished and np.any(post):
            finite_obs = np.isfinite(t_obs) & np.isfinite(v)
            if np.any(finite_obs):
                last_val = float(v[finite_obs][-1])
                resampled = resampled.copy()
                if name.lower() in ("speed", "throttle", "brake"):
                    resampled[post] = 0.0
                else:
                    resampled[post] = last_val

        out_channels[name] = resampled

    still_default = np.array(
        [v == Validity.PRE for v in validity], dtype=bool)
    not_gap = np.array(
        [v != Validity.GAP for v in validity], dtype=bool)
    validity[inside & not_gap & still_default] = Validity.ACTIVE

    return ResampledDriver(
        code=code,
        timeline=timeline,
        channels=out_channels,
        validity=validity,
        valid_start=valid_start,
        valid_end=valid_end,
        has_any_telemetry=True,
    )


def build_frame_payload(
    timeline: np.ndarray,
    drivers: Sequence[ResampledDriver],
    *,
    track_length: Optional[float] = None,
    frame_index_offset: int = 0,
) -> List[Dict[str, Any]]:
    """Build a list of replay frames, one per timeline point."""
    timeline = np.asarray(timeline, dtype=float)
    n = len(timeline)
    out: List[Dict[str, Any]] = []
    for i in range(n):
        frame: Dict[str, Any] = {
            "t": float(timeline[i]),
            "frame_index": int(i + frame_index_offset),
            "drivers": {},
        }
        for d in drivers:
            marker = d.validity[i] if i < len(d.validity) else Validity.DNS
            entry: Dict[str, Any] = {
                "validity": marker.value if isinstance(marker, Validity) else str(marker),
                "active": marker in (Validity.ACTIVE, Validity.FINISHED),
            }
            for name, arr in d.channels.items():
                if i < len(arr):
                    val = arr[i]
                    if isinstance(val, np.generic):
                        val = val.item()
                    entry[name] = val
            frame["drivers"][d.code] = entry
        out.append(frame)
    return out


__all__ = [
    "ChannelKind",
    "DEFAULT_CONTINUOUS",
    "DEFAULT_DISCRETE",
    "Validity",
    "DriverValidity",
    "ResampledDriver",
    "channel_kind",
    "resample_driver",
    "build_frame_payload",
    "safe_int",
    "safe_float",
]
