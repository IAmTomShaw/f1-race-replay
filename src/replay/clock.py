"""
Canonical replay clock.

The legacy code mixed a per-frame ``frame_index`` (a float that
accumulated ``dt * FPS``) with a per-frame ``t`` field stored on
each frame dict. The float accumulator drifts; the per-frame t
field excludes the final sample because of ``np.arange``'s open
endpoint; and the two can disagree.

This module defines a single source of truth for replay time and
derives every other quantity from it.

State
-----
- ``replay_time`` (float, seconds): always in
  ``[0, total_seconds]`` unless the clock is "free" (i.e. the user
  rewound to a state before the start; rare).
- ``playback_speed`` (float, multiplier of wall time): one of
  ``PLAYBACK_SPEEDS`` below, or any positive finite float.
- ``paused`` (bool): when True, ``tick(dt)`` is a no-op.
- ``direction`` (+1 / -1): forward or rewind. Independent of speed
  so that a 1x rewind can be combined with, e.g., 4x speed.

Operations
----------
- ``tick(wall_dt)``        : advance replay time by ``wall_dt * speed * direction``.
- ``pause()`` / ``resume()``
- ``toggle()``             : flip paused.
- ``set_speed(s)``         : set playback_speed (clamped to POSITIVE).
- ``seek(t)``              : set replay_time directly.
- ``seek_frame(i)``        : set replay_time to ``i * dt``.
- ``restart()``            : replay_time = 0, paused = False.
- ``frame_index`` (property): ``round(replay_time / dt)``.
- ``current_t``   (property): ``replay_time``.
- ``at_end``      (property): ``replay_time >= total_seconds - EPS``.
- ``at_start``    (property): ``replay_time <= EPS``.

All public operations are deterministic and free of wall-clock
side effects. The caller advances time by the wall delta they
actually observed; the clock does not call ``time.sleep`` or
``time.perf_counter`` itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Allowed playback speeds. Mirrors PLAYBACK_SPEEDS in
# src/interfaces/race_replay.py and the README.
# ---------------------------------------------------------------------------
PLAYBACK_SPEEDS: tuple[float, ...] = (
    0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0,
    64.0, 128.0, 256.0,
)

# Small tolerance for end-of-replay and similar comparisons.
EPS = 1e-6


class Direction(Enum):
    FORWARD = 1
    REWIND = -1


@dataclass
class ReplayClock:
    """Stateful replay clock.

    Parameters
    ----------
    total_seconds
        Total replay length in seconds. The clock will not advance
        past this value when going forward, nor below 0 when
        rewinding.
    fps
        Frames per second; ``dt = 1 / fps``. The clock derives the
        current frame index from ``replay_time / dt``.
    initial_speed
        Initial playback speed (defaults to 1.0).
    """
    total_seconds: float
    fps: float = 25.0
    initial_speed: float = 1.0
    _replay_time: float = field(default=0.0, init=False)
    _speed: float = field(default=1.0, init=False)
    _paused: bool = field(default=False, init=False)
    _direction: Direction = field(default=Direction.FORWARD, init=False)
    _wrapped: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.total_seconds < 0:
            raise ValueError("total_seconds must be non-negative")
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        self._speed = self._normalize_speed(self.initial_speed)
        self._replay_time = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def dt(self) -> float:
        return 1.0 / self.fps

    @property
    def replay_time(self) -> float:
        return self._replay_time

    @property
    def current_t(self) -> float:
        return self._replay_time

    @property
    def playback_speed(self) -> float:
        return self._speed

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def direction(self) -> Direction:
        return self._direction

    @property
    def frame_index(self) -> int:
        if self._replay_time <= 0:
            return 0
        idx = int(round(self._replay_time / self.dt))
        # Clamp to last valid frame index; the consumer can detect
        # "at end" via ``at_end``.
        max_idx = max(0, int(round(self.total_seconds / self.dt)) - 1)
        return min(idx, max_idx)

    @property
    def at_end(self) -> bool:
        return self._replay_time >= self.total_seconds - EPS

    @property
    def at_start(self) -> bool:
        return self._replay_time <= EPS

    @property
    def wrapped(self) -> bool:
        """True iff the clock was advanced past the end of the replay
        while in FORWARD mode. Used to auto-stop or auto-pause the
        render loop."""
        return self._wrapped

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------
    def _normalize_speed(self, s: float) -> float:
        if not math.isfinite(s):
            raise ValueError(f"playback speed must be finite, got {s!r}")
        if s <= 0:
            raise ValueError(f"playback speed must be positive, got {s!r}")
        return float(s)

    def set_speed(self, speed: float) -> None:
        self._speed = self._normalize_speed(speed)

    def cycle_speed(self, step: int = 1) -> float:
        """Cycle to the next/previous speed in PLAYBACK_SPEEDS."""
        # If current speed is not in the list, snap to the nearest.
        if self._speed not in PLAYBACK_SPEEDS:
            # Pick the closest.
            nearest = min(PLAYBACK_SPEEDS,
                           key=lambda s: abs(math.log2(s) - math.log2(self._speed)))
            self._speed = nearest
            return self._speed
        i = PLAYBACK_SPEEDS.index(self._speed)
        new_i = (i + step) % len(PLAYBACK_SPEEDS)
        self._speed = PLAYBACK_SPEEDS[new_i]
        return self._speed

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def toggle(self) -> bool:
        self._paused = not self._paused
        return self._paused

    def set_direction(self, direction: Direction) -> None:
        self._direction = direction

    def toggle_direction(self) -> Direction:
        self._direction = (Direction.REWIND
                           if self._direction is Direction.FORWARD
                           else Direction.FORWARD)
        return self._direction

    def seek(self, t: float) -> None:
        if not math.isfinite(t):
            raise ValueError(f"seek target must be finite, got {t!r}")
        self._replay_time = max(0.0, min(float(t), self.total_seconds))
        self._wrapped = False

    def seek_frame(self, frame_index: int) -> None:
        if frame_index < 0:
            frame_index = 0
        self.seek(frame_index * self.dt)

    def restart(self) -> None:
        self._replay_time = 0.0
        self._paused = False
        self._direction = Direction.FORWARD
        self._wrapped = False

    def tick(self, wall_dt: float) -> float:
        """Advance (or rewind) the clock by ``wall_dt`` seconds of
        wall time. Returns the new ``replay_time``.

        If the clock is paused, ``tick`` is a no-op that returns the
        current ``replay_time``. If the forward clock runs past the
        end, the clock is pinned to ``total_seconds`` and ``wrapped``
        is set to True so the caller can auto-pause.
        """
        if not math.isfinite(wall_dt) or wall_dt < 0:
            raise ValueError(f"wall_dt must be a non-negative finite number, got {wall_dt!r}")
        if self._paused:
            return self._replay_time
        delta = wall_dt * self._speed * self._direction.value
        new = self._replay_time + delta
        if self._direction is Direction.FORWARD and new >= self.total_seconds - EPS:
            self._replay_time = self.total_seconds
            self._wrapped = True
        elif self._direction is Direction.REWIND and new <= EPS:
            self._replay_time = 0.0
        else:
            self._replay_time = new
        return self._replay_time


__all__ = [
    "PLAYBACK_SPEEDS",
    "Direction",
    "ReplayClock",
    "EPS",
]
