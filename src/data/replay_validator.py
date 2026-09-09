"""
Runtime telemetry validator.

This module is the runtime hookup for
``src.lib.telemetry_invariants``. The invariants library
contains pure functions over a frames payload; this
module is the *call policy*:

* Validate at data boundaries, not every render frame.
* Use lightweight sampled checks in hot paths.
* Distinguish **hard** violations (data is unusable) from
  **soft** anomalies (data is imperfect but the replay can
  proceed with a warning).
* Do not block on a missing FastF1 field that is allowed to
  be absent (e.g. weather).

The validator runs ONCE per replay, after
``f1_data.get_race_telemetry`` (or the qualifying variant)
returns, and before the frames are handed to the Arcade
window. The audit is the "data becomes trusted replay state"
boundary called out in PHASE 1.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.lib.telemetry_invariants import (
    Issue,
    check_frame_t_monotonic,
    check_frame_spacing,
    check_no_wall_clock,
)


# When we sample N frames out of a stream that was originally
# recorded at ``fps`` Hz, consecutive *sampled* timestamps are
# further apart than 1/fps. The spacing invariant must accept
# the sampled cadence; the rule of thumb is "within the sample
# step's expected dt". We pass an ``atol`` equal to the maximum
# expected dt for the sampled subset, which is the per-step dt
# the sampler produces.
def _spacing_atol_for_sample(sample_size: int, fps: float) -> float:
    # The sampler returns up to sample_size+1 frames covering
    # the full range. The widest expected gap between consecutive
    # samples is therefore about (1 / fps) * (total / sample_size).
    # We just allow 5 * 1/fps as a comfortable ceiling for the
    # sub-array check.
    return 5.0 / fps


logger = logging.getLogger("f1_replay.replay_validator")


# Codes that represent HARD (unusable) violations. Replay is
# blocked. Every other error / warning is SOFT and only logs.
HARD_CODES: frozenset = frozenset({
    # Frame timestamps must be strictly non-decreasing.
    "INV-01.t_not_monotonic",
    # Cache / replay corruption.
    "INV-14.wall_clock_leaked",
})


@dataclass
class ValidationReport:
    """Result of a sampled validation pass."""
    sample_size: int
    total_frames: int
    issues: List[Issue] = field(default_factory=list)
    hard: List[Issue] = field(default_factory=list)
    soft: List[Issue] = field(default_factory=list)

    @property
    def is_hard_fatal(self) -> bool:
        return bool(self.hard)

    def summary(self) -> str:
        return (f"replay_validator: {len(self.issues)} issue(s) over "
                f"{self.sample_size}/{self.total_frames} sampled frames "
                f"(hard={len(self.hard)}, soft={len(self.soft)})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "total_frames": self.total_frames,
            "is_hard_fatal": self.is_hard_fatal,
            "issues": [
                {"level": lvl, "code": code, "message": msg}
                for (lvl, code, msg) in self.issues
            ],
        }


def _sample_indices(total: int, sample_size: int) -> List[int]:
    """Return a list of up to ``sample_size`` frame indices to
    validate. We pick the first, last, and evenly-spaced interior
    indices so we exercise both edges of the timeline. The
    output is sorted, contains no duplicates, and never exceeds
    ``min(sample_size, total)`` items.
    """
    if total <= 0:
        return []
    if sample_size >= total:
        return list(range(total))
    # End-inclusive endpoints plus evenly-spaced interior.
    step = max(1, (total - 1) // max(1, sample_size - 1))
    idx: List[int] = []
    for i in range(0, total, step):
        idx.append(i)
        if len(idx) >= sample_size - 1:
            break
    # Always include the last frame.
    if idx[-1] != total - 1:
        idx.append(total - 1)
    return idx


def validate_replay_payload(
    frames: Sequence[Dict[str, Any]],
    *,
    sample_size: int = 50,
    fps: float = 25.0,
) -> ValidationReport:
    """Run a sampled invariant pass over a frames payload.

    The checks used here are the cheap / non-O(N) ones that
    only inspect the sampled frames:

    * monotonic timestamps (INV-01)
    * per-frame spacing (INV-02)
    * no wall-clock leak (INV-14)

    The full per-frame checks (validity, leaderboard, units)
    are NOT run here; they are already enforced by the
    resampler + leaderboard + units layer that built the
    payload. Running them again would be a hot-path regression.

    Parameters
    ----------
    frames
        The frames payload produced by ``f1_data.get_race_telemetry``
        or ``f1_data.get_quali_telemetry``.
    sample_size
        Maximum number of frames to inspect. The actual sample
        is ``min(sample_size, len(frames))`` with the first
        and last frame always included.
    fps
        Used by INV-02 to check frame spacing. Pass the
        telemetry FPS (25 by default).
    """
    total = len(frames)
    if total == 0:
        # An empty payload IS a hard failure: the user will see
        # an empty replay with no warning, which is worse than
        # a clear error.
        rep = ValidationReport(sample_size=0, total_frames=0)
        rep.hard.append(
            ("error", "INV-EMPTY",
             "frames payload is empty; cannot start replay"))
        rep.issues.extend(rep.hard)
        return rep

    sample = _sample_indices(total, sample_size)
    sub_frames = [frames[i] for i in sample]

    issues: List[Issue] = []
    # Cheap checks (each is O(sample_size)). Spacing atol is
    # widened because the sampled subset has a coarser cadence
    # than the source fps.
    issues.extend(check_frame_t_monotonic(sub_frames))
    issues.extend(check_frame_spacing(sub_frames, fps=fps,
                                       atol=_spacing_atol_for_sample(
                                           len(sub_frames), fps)))
    issues.extend(check_no_wall_clock(sub_frames))

    rep = ValidationReport(sample_size=len(sub_frames),
                            total_frames=total,
                            issues=issues)
    for lvl, code, msg in issues:
        if code in HARD_CODES or lvl == "error":
            rep.hard.append((lvl, code, msg))
        else:
            rep.soft.append((lvl, code, msg))
    return rep


def run_replay_validation(frames: Sequence[Dict[str, Any]],
                          *, fps: float = 25.0,
                          sample_size: int = 50
                          ) -> ValidationReport:
    """Convenience: validate + log the outcome.

    This is the function the production path calls. It logs
    hard failures at ERROR and soft anomalies at WARNING. The
    returned report is also returned for the caller to act on.
    """
    rep = validate_replay_payload(frames,
                                  sample_size=sample_size,
                                  fps=fps)
    if rep.hard:
        logger.error("%s", rep.summary())
        for lvl, code, msg in rep.hard:
            logger.error("[%s] %s: %s", lvl, code, msg)
    elif rep.soft:
        logger.warning("%s", rep.summary())
        for lvl, code, msg in rep.soft:
            logger.warning("[%s] %s: %s", lvl, code, msg)
    else:
        logger.info("%s", rep.summary())
    return rep


__all__ = [
    "HARD_CODES",
    "ValidationReport",
    "validate_replay_payload",
    "run_replay_validation",
]
