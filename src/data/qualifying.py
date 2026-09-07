"""
Qualifying telemetry helpers.

The legacy code in ``src.f1_data`` has two places that build
qualifying data:

* ``get_driver_quali_telemetry``     -> one driver, one segment
* ``_process_quali_driver``          -> per-driver worker
* ``get_quali_telemetry``            -> orchestrator

Each one has subtle issues: missing-segment sessions crash, the
final frame's ``t`` is set from the lap's ``LapTime`` (which can
disagree with the resampled t-series), and the unit-canonicalization
problem (brake * 100) is unique to the qualifying path.

This module exposes small, pure-Python helpers that the qualifying
path can call instead of duplicating logic. The helpers do NOT
import FastF1 — they operate on already-loaded FastF1-style data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.data.telemetry_units import (
    CANONICAL_UNITS,
    normalize_frame_entry,
)
from src.lib.time import parse_time_string


# Q1/Q2/Q3 segment labels in chronological order.
SEGMENTS: Tuple[str, ...] = ("Q1", "Q2", "Q3")


@dataclass
class SegmentResult:
    segment: str
    lap_time: Optional[float]
    available: bool
    reason: str = ""

    @property
    def is_valid(self) -> bool:
        return self.available and self.lap_time is not None


def pick_fastest_lap(segment_laps: Any) -> Optional[Any]:
    """Return the fastest lap in a segment, or None.

    ``segment_laps`` is a FastF1 Laps object; ``pick_fastest``
    already returns the row with the lowest ``LapTime``, or
    ``None`` for an empty segment. We do not duplicate that
    logic; we only guard against the empty case.
    """
    if segment_laps is None:
        return None
    if hasattr(segment_laps, "empty") and segment_laps.empty:
        return None
    return segment_laps.pick_fastest()


def segment_lap_time(segment_laps: Any, segment: str) -> SegmentResult:
    """Compute the best lap time for one segment.

    Returns a ``SegmentResult`` with ``available=False`` and a
    human-readable ``reason`` if the segment is missing/empty
    (e.g. wet sessions where Q3 never started)."""
    if segment not in SEGMENTS:
        return SegmentResult(segment, None, False,
                              reason=f"unknown segment: {segment!r}")
    lap = pick_fastest_lap(segment_laps)
    if lap is None:
        return SegmentResult(segment, None, False,
                              reason="no laps in segment")
    raw = lap.get("LapTime")
    if raw is None or (hasattr(raw, "__class__") and raw.__class__.__name__ == "NaTType"):
        return SegmentResult(segment, None, False,
                              reason="fastest lap has no LapTime")
    secs = parse_time_string(str(raw))
    if secs is None:
        return SegmentResult(segment, None, False,
                              reason=f"could not parse LapTime: {raw!r}")
    return SegmentResult(segment, secs, True)


def build_qualifying_frame(t: float, telemetry_row: Dict[str, Any]
                           ) -> Dict[str, Any]:
    """Build a single normalized qualifying frame from one telemetry row.

    The output dict has ``t`` plus a ``telemetry`` sub-dict whose
    values are normalized to canonical units. This is the canonical
    shape for a qualifying frame; consumers should not need to
    re-normalize.
    """
    return {
        "t": float(t),
        "telemetry": normalize_frame_entry(dict(telemetry_row)),
    }


def align_telemetry_arrays(telemetry_rows: Sequence[Dict[str, Any]]
                           ) -> Dict[str, np.ndarray]:
    """Stack a list of per-row telemetry dicts into equal-length arrays.

    All rows must have the same keys; missing values are treated
    as NaN. Returns a dict of column -> np.ndarray (1-D).

    This is the test for the "telemetry arrays all have equal
    length" invariant.
    """
    if not telemetry_rows:
        return {}
    keys: List[str] = []
    for row in telemetry_rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    n = len(telemetry_rows)
    out: Dict[str, np.ndarray] = {}
    for k in keys:
        col = np.full(n, np.nan, dtype=float)
        for i, row in enumerate(telemetry_rows):
            v = row.get(k)
            try:
                col[i] = float(v)
            except (TypeError, ValueError):
                # Keep NaN.
                pass
        out[k] = col
    return out


def set_final_frame_t(frames: List[Dict[str, Any]], lap_time: float) -> None:
    """Set the last frame's ``t`` to the exact lap time.

    Mutates the list in place. Use this to honor the project
    invariant: ``final frame t == LapTime`` of the qualifying lap.
    """
    if not frames:
        return
    frames[-1]["t"] = float(lap_time)


__all__ = [
    "SEGMENTS",
    "SegmentResult",
    "pick_fastest_lap",
    "segment_lap_time",
    "build_qualifying_frame",
    "align_telemetry_arrays",
    "set_final_frame_t",
]
