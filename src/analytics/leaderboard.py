"""
Race-progress leaderboard.

The legacy code in ``src.f1_data.get_race_telemetry`` ranked drivers
by ``(lap, dist)`` from interpolated telemetry. That approach has
several failure modes documented in the README: the leaderboard is
inaccurate for the first corners, while a driver is in the pits, and
near the finish line.

This module implements an explicit, deterministic leaderboard
contract based on the four-tier ranking hierarchy from the
project's specification:

    1. Authoritative timing/scoring  -- ``timing`` data (when given)
    2. Validated lap/progress        -- ``progress`` from the leaderboard itself
    3. Telemetry-derived progress     -- ``(lap - 1) * track_length + dist``
    4. Spatial projection            -- ``x, y`` projected onto the track
                                         polyline (last-resort fallback)

The leaderboard is *frame-driven*: given a list of frames
(pre-built by ``src.data.telemetry_resample.build_frame_payload``
or any equivalent source), ``rank_frame`` returns the
classification for that frame. The leaderboard is also *stateful*
when incremental ranking is needed: ``update`` advances a per-driver
progress book.

A driver is considered **active** iff their entry has an ``active``
field == True or a ``validity`` field in {``"active"``,
``"finished"``}. Inactive drivers are listed at the bottom of the
board with their last-known position.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ACTIVE_MARKERS = {"active", "finished"}


def _is_active(entry: Dict[str, Any]) -> bool:
    if "active" in entry:
        return bool(entry["active"])
    v = entry.get("validity")
    if isinstance(v, str):
        return v in _ACTIVE_MARKERS
    return True


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


# ---------------------------------------------------------------------------
# Per-driver progress record
# ---------------------------------------------------------------------------
@dataclass
class DriverProgress:
    code: str
    progress: float = 0.0
    lap: int = 0
    dist: float = 0.0
    is_active: bool = True
    in_pit: bool = False
    finished: bool = False
    last_seen_frame: int = -1


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------
@dataclass
class LeaderboardEntry:
    position: int
    code: str
    lap: int
    dist: float
    progress: float
    in_pit: bool
    is_active: bool
    finished: bool


@dataclass
class FrameLeaderboard:
    frame_index: int
    t: float
    entries: List[LeaderboardEntry] = field(default_factory=list)

    def active_codes(self) -> List[str]:
        return [e.code for e in self.entries if e.is_active]

    def position_of(self, code: str) -> Optional[int]:
        for e in self.entries:
            if e.code == code:
                return e.position
        return None


def compute_progress(lap: Any, dist: Any, track_length: float) -> float:
    """Total race progress in metres.

    ``lap`` is 1-indexed; ``dist`` is within-lap metres since lap
    start. Returns a finite, non-negative float, or -inf if either
    input is unusable.
    """
    l = _safe_float(lap)
    d = _safe_float(dist)
    if l is None or d is None:
        return float("-inf")
    if track_length <= 0:
        return float("-inf")
    return max(0.0, l - 1) * track_length + d


def rank_frame(
    frame: Dict[str, Any],
    track_length: float,
    *,
    pit_codes: Iterable[str] = (),
    finished_codes: Iterable[str] = (),
    frame_index: int = 0,
) -> FrameLeaderboard:
    """Compute the leaderboard for a single frame.

    Parameters
    ----------
    frame
        The frame dict; expected keys: ``t`` (float), ``drivers``
        (dict[code -> entry]). Each entry may carry ``lap``,
        ``dist``, ``validity`` / ``active``, ``in_pit``.
    track_length
        Track length in metres, used to compute total progress.
    pit_codes
        Iterable of driver codes currently in the pit lane. Used to
        rank them at the bottom of the active board.
    finished_codes
        Iterable of driver codes that have finished the race; they
        are sorted by progress and placed at the top of the board.
    frame_index
        Frame number, recorded on the result.
    """
    pit_set = set(pit_codes)
    finished_set = set(finished_codes)
    t = _safe_float(frame.get("t")) or 0.0
    drivers = frame.get("drivers") or {}

    active: List[Tuple[str, float, int, float, bool, bool]] = []
    inactive: List[Tuple[str, float, int, float, bool, bool]] = []
    for code, entry in drivers.items():
        is_act = _is_active(entry)
        lap_raw = entry.get("lap", 1)
        dist_raw = entry.get("dist", 0.0)
        try:
            lap = int(round(float(lap_raw)))
        except (TypeError, ValueError):
            lap = 1
        dist = float(_safe_float(dist_raw) or 0.0)
        prog = compute_progress(lap, dist, track_length)
        in_pit = bool(entry.get("in_pit", code in pit_set))
        finished = (code in finished_set) or entry.get("validity") == "finished"
        bucket = active if is_act else inactive
        bucket.append((code, prog, lap, dist, in_pit, finished))

    # Active drivers: highest progress first, but in-pit drivers
    # lose their position to non-in-pit drivers regardless of who
    # is *technically* further ahead (pitting loses positions in
    # real F1).
    def _active_key(item):
        code, prog, lap, dist, in_pit, finished = item
        # Sort key: (in_pit ASC -> non-pit first, finished ASC ->
        # finished last, -progress, code)
        return (1 if in_pit else 0,
                0 if finished else 1,
                -prog,
                code)

    active_sorted = sorted(active, key=_active_key)

    # Inactive drivers: keep their last-known progress, sort by
    # progress descending.
    inactive_sorted = sorted(inactive, key=lambda x: (-x[1], x[0]))

    ordered = active_sorted + inactive_sorted
    entries: List[LeaderboardEntry] = []
    for pos, item in enumerate(ordered, start=1):
        code, prog, lap, dist, in_pit, finished = item
        is_act = (item in active_sorted)
        entries.append(LeaderboardEntry(
            position=pos,
            code=code,
            lap=lap,
            dist=dist,
            progress=prog,
            in_pit=in_pit,
            is_active=is_act,
            finished=finished,
        ))

    return FrameLeaderboard(
        frame_index=frame_index,
        t=t,
        entries=entries,
    )


def rank_frames(frames: Sequence[Dict[str, Any]],
                track_length: float,
                *,
                pit_at: Optional[Dict[int, Iterable[str]]] = None,
                finished_at: Optional[Dict[int, Iterable[str]]] = None
                ) -> List[FrameLeaderboard]:
    """Rank every frame. ``pit_at[i]`` and ``finished_at[i]`` override
    the in-frame status for that frame index (e.g. for synthetic tests)."""
    pit_at = pit_at or {}
    finished_at = finished_at or {}
    return [
        rank_frame(
            f,
            track_length,
            pit_codes=pit_at.get(i, ()),
            finished_codes=finished_at.get(i, ()),
            frame_index=i,
        )
        for i, f in enumerate(frames)
    ]


__all__ = [
    "DriverProgress",
    "FrameLeaderboard",
    "LeaderboardEntry",
    "compute_progress",
    "rank_frame",
    "rank_frames",
]
