"""
Safety Car — real event timing vs simulated visual position.

The legacy code (``src.f1_data._compute_safety_car_positions``)
inlined a *simulated* SC GPS position into the per-frame payload
with the same shape as a real telemetry sample, and never
re-exposed the *real* SC event timing from
``session.track_status``. Consumers had no way to tell
"simulated visual stand-in" from "real GPS telemetry".

This module provides the explicit separation called for in
PHASE 12 of the project specification:

* ``extract_sc_periods(track_statuses)`` returns the *real*
  event timing as a list of ``SCPeriod`` records. Each record
  has a start_time, end_time (auto-derived if missing), and a
  status code from the F1 timing system.

* ``simulate_sc_position(frame, sc_periods, ...)`` returns a
  *simulated* SC payload with an explicit ``"source": "simulated"``
  flag. Consumers MUST check ``source`` before treating SC data
  as real telemetry.

* The combined ``attach_sc`` helper attaches a properly-tagged
  ``safety_car`` field to every frame in a list.

Two design rules are enforced by tests:

* Real SC periods are NEVER modified by the simulator. They are
  exposed as data; the simulator only generates visual position.
* Simulated SC data is NEVER used to derive rankings, lap counts,
  or any other authoritative timing metric.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger("f1_replay.safety_car")


class SCSource(str, Enum):
    SIMULATED = "simulated"
    REAL = "real"
    NONE = "none"


# F1 track status codes that indicate an SC/VSC period. See FastF1 docs.
SC_CODES = {"4"}      # Safety Car
VSC_CODES = {"5", "6", "7"}  # VSC variants (deprecated; included for safety)


@dataclass
class SCPeriod:
    """A real SC/VSC event window derived from track_status data."""
    start_time: float
    end_time: Optional[float]  # None means "still in progress or unknown"
    status: str                # e.g. "4" for SC
    kind: str                  # "SC" or "VSC"
    period_index: int

    @property
    def is_open(self) -> bool:
        return self.end_time is None


def classify(status: str) -> str:
    if status in SC_CODES:
        return "SC"
    if status in VSC_CODES:
        return "VSC"
    return "OTHER"


def extract_sc_periods(track_statuses: Sequence[Dict[str, Any]]
                       ) -> List[SCPeriod]:
    """Convert a list of track_status dicts into SCPeriod records.

    Each input dict must carry ``status``, ``start_time`` (and
    optionally ``end_time``). The output list is sorted by
    ``start_time`` and indexed in chronological order.

    Missing ``end_time`` is left as ``None`` and an
    ``open=True`` flag is set; downstream code that needs a
    closed window should call :func:`close_open_periods`.
    """
    periods: List[SCPeriod] = []
    idx = 0
    for s in track_statuses:
        status = str(s.get("status", ""))
        kind = classify(status)
        if kind == "OTHER":
            continue
        start = s.get("start_time")
        if start is None:
            continue
        end = s.get("end_time")
        periods.append(SCPeriod(
            start_time=float(start),
            end_time=None if end is None else float(end),
            status=status,
            kind=kind,
            period_index=idx,
        ))
        idx += 1
    periods.sort(key=lambda p: p.start_time)
    # Re-index after sort so period_index is the chronological index.
    for i, p in enumerate(periods):
        p.period_index = i
    return periods


def close_open_periods(periods: Sequence[SCPeriod],
                       *,
                       default_end: Optional[float] = None
                       ) -> List[SCPeriod]:
    """Return a new list where any open period has a concrete end.

    The "default" rules:

    * If ``default_end`` is given, every open period is closed at
      that time.
    * Otherwise, an open period is closed at the START of the
      NEXT period (chronological), or left open if there is no
      next period.
    * A warning is logged for every auto-closed period because
      this is a data-quality issue that should be surfaced.
    """
    closed: List[SCPeriod] = []
    for i, p in enumerate(periods):
        if not p.is_open:
            closed.append(SCPeriod(
                start_time=p.start_time, end_time=p.end_time,
                status=p.status, kind=p.kind, period_index=p.period_index,
            ))
            continue
        # Need an end.
        end = default_end
        if end is None and i + 1 < len(periods):
            end = periods[i + 1].start_time
        if end is None:
            # Leave open, but log it.
            logger.warning(
                "SC period %d (status=%s, start=%.3f) has no end_time "
                "and no following period; leaving open.",
                p.period_index, p.status, p.start_time,
            )
            closed.append(SCPeriod(
                start_time=p.start_time, end_time=None,
                status=p.status, kind=p.kind, period_index=p.period_index,
            ))
        else:
            logger.warning(
                "SC period %d (status=%s) missing end_time; "
                "auto-closed at %.3f.", p.period_index, p.status, end,
            )
            closed.append(SCPeriod(
                start_time=p.start_time, end_time=float(end),
                status=p.status, kind=p.kind, period_index=p.period_index,
            ))
    return closed


def active_period_at(periods: Sequence[SCPeriod], t: float
                     ) -> Optional[SCPeriod]:
    """Return the SC period that is active at replay time ``t``, or
    ``None``. An open period (end_time is None) is active for all
    ``t >= start_time``."""
    for p in periods:
        if t < p.start_time - 1e-9:
            continue
        if p.end_time is None:
            return p
        if t <= p.end_time + 1e-9:
            return p
    return None


def simulate_sc_position(frame: Dict[str, Any],
                         *,
                         track_length: float,
                         offset_m: float = 150.0,
                         ) -> Optional[Dict[str, Any]]:
    """Produce a SIMULATED SC position for one frame.

    The function does NOT consult track status; the caller is
    responsible for only calling it when an SC period is active.
    The returned dict always carries ``source = "simulated"``
    and a ``kind = "visual_only"`` marker so consumers cannot
    confuse it with real telemetry.

    Returns ``None`` if the frame has no drivers (e.g. the SC
    can't find a leader to lead).
    """
    drivers = frame.get("drivers") or {}
    if not drivers or track_length <= 0:
        return None
    # Find the leader by the largest total progress.
    best_code, best_prog = None, -1.0
    for code, d in drivers.items():
        if d.get("active") is False:
            continue
        lap = d.get("lap", 1)
        dist = d.get("dist", 0.0)
        try:
            prog = (max(int(lap), 1) - 1) * track_length + float(dist)
        except (TypeError, ValueError):
            continue
        if prog > best_prog:
            best_prog = prog
            best_code = code
    if best_code is None:
        return None
    leader = drivers[best_code]
    # Simulated SC stands a fixed offset ahead of the leader on
    # the within-lap distance scale. The (x, y) is intentionally
    # left None so a renderer must compute it from the track
    # reference polyline (which is the responsibility of the
    # rendering layer, not this module).
    simulated_lap = leader.get("lap", 1)
    simulated_dist = (float(leader.get("dist", 0.0)) + offset_m) % track_length
    return {
        "source": SCSource.SIMULATED.value,
        "kind": "visual_only",
        "phase": "on_track",
        "alpha": 1.0,
        "leader_code": best_code,
        "offset_m": float(offset_m),
        "lap": int(simulated_lap),
        "dist": float(simulated_dist),
        # We deliberately do NOT include x, y here. The renderer
        # must derive those from the track polyline at (lap, dist).
        "x": None,
        "y": None,
    }


def attach_sc(frames: Sequence[Dict[str, Any]],
              periods: Sequence[SCPeriod],
              *,
              track_length: float,
              offset_m: float = 150.0,
              ) -> List[Dict[str, Any]]:
    """Attach a properly-tagged ``safety_car`` field to each frame.

    The frame's existing ``safety_car`` field (if any) is REPLACED
    with one of:

    * A dict with ``source = "simulated"`` when an SC period is
      active and the simulator can find a leader.
    * A dict with ``source = "real"`` when an SC period is active
      but no leader can be found (rare; e.g. very first frame).
    * A dict with ``source = "none"`` when no SC period is active.

    Frames are NOT mutated in place; a new list of shallow-copied
    frames is returned.
    """
    out: List[Dict[str, Any]] = []
    for f in frames:
        new = dict(f)
        t = f.get("t")
        period = None
        if t is not None:
            period = active_period_at(periods, float(t))
        if period is None:
            new["safety_car"] = {"source": SCSource.NONE.value}
        else:
            sim = simulate_sc_position(
                f, track_length=track_length, offset_m=offset_m,
            )
            if sim is None:
                new["safety_car"] = {
                    "source": SCSource.REAL.value,
                    "kind": "no_leader",
                    "phase": "on_track",
                    "alpha": 1.0,
                }
            else:
                new["safety_car"] = sim
        out.append(new)
    return out


__all__ = [
    "SCSource",
    "SC_CODES",
    "VSC_CODES",
    "SCPeriod",
    "classify",
    "extract_sc_periods",
    "close_open_periods",
    "active_period_at",
    "simulate_sc_position",
    "attach_sc",
]
