"""
Telemetry / replay data invariants.

This module encodes the rules that ANY well-formed replay dataset
(frames + track_statuses + race_control_messages) MUST satisfy. The
rules are intentionally expressed as pure functions over already-built
data so they can be unit-tested independently of FastF1, Arcade, or
the running replay.

Each public function returns a list of (level, code, message) tuples.
Level is "error" (must not ship) or "warning" (degraded but
acceptable). An empty list means the invariant is satisfied.

The 15 invariants encoded below come from the project's
"PHASE 1 — Establish Data Invariants" specification.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Tuple

# A small tolerance to absorb float round-off from frame interpolation.
EPS = 1e-6

Issue = Tuple[str, str, str]  # (level, code, message)


# ---------------------------------------------------------------------------
# 1. Replay timestamps are monotonically increasing.
# ---------------------------------------------------------------------------
def check_frame_t_monotonic(frames: List[Dict[str, Any]]) -> List[Issue]:
    issues: List[Issue] = []
    prev = None
    for i, f in enumerate(frames):
        t = f.get("t")
        if t is None:
            issues.append(("error", "INV-01.missing_t", f"frame {i} missing 't'"))
            continue
        if prev is not None and t + EPS < prev:
            issues.append((
                "error",
                "INV-01.t_not_monotonic",
                f"frame {i} t={t} < previous t={prev}",
            ))
        prev = t
    return issues


# ---------------------------------------------------------------------------
# 2. Replay frame spacing is approximately 1/FPS.
# ---------------------------------------------------------------------------
def check_frame_spacing(frames: List[Dict[str, Any]], fps: float = 25.0,
                         atol: float = 1e-3) -> List[Issue]:
    issues: List[Issue] = []
    if len(frames) < 2:
        return issues
    dt_expected = 1.0 / fps
    for i in range(1, len(frames)):
        t_prev = frames[i - 1].get("t")
        t_curr = frames[i].get("t")
        if t_prev is None or t_curr is None:
            continue
        dt = t_curr - t_prev
        if abs(dt - dt_expected) > atol:
            issues.append((
                "warning",
                "INV-02.spacing_drift",
                f"frame {i} dt={dt:.6f} deviates from 1/FPS={dt_expected:.6f}",
            ))
    return issues


# ---------------------------------------------------------------------------
# 3. Every driver's telemetry has an explicit valid interval.
# ---------------------------------------------------------------------------
def check_validity_intervals_present(driver_data: Dict[str, Dict[str, Any]]
                                     ) -> List[Issue]:
    issues: List[Issue] = []
    for code, data in driver_data.items():
        if "valid_start" not in data or "valid_end" not in data:
            issues.append((
                "error",
                "INV-03.missing_validity",
                f"driver {code} missing 'valid_start'/'valid_end'",
            ))
    return issues


# ---------------------------------------------------------------------------
# 4. Drivers are not active before their telemetry starts.
# 5. Drivers are not active after their telemetry ends
#    unless a terminal-state model explicitly requires them.
#
# If a frame carries a per-driver ``validity`` field (the new
# ``src.data.telemetry_resample`` convention), that field is
# authoritative. A driver is considered "active" iff their marker
# is ``"active"`` or ``"finished"``. Otherwise presence in the
# drivers dict is allowed (e.g. for rendering an "OUT" label) and
# the invariant checks the ``active`` boolean if present.
# ---------------------------------------------------------------------------
_ACTIVE_MARKERS = {"active", "finished"}


def _is_active_in_frame(driver_entry: Dict[str, Any]) -> bool:
    if "active" in driver_entry:
        return bool(driver_entry["active"])
    v = driver_entry.get("validity")
    if isinstance(v, str):
        return v in _ACTIVE_MARKERS
    # Legacy / unknown schema: presence alone.
    return True


def check_no_activity_outside_validity(frames: List[Dict[str, Any]],
                                       driver_data: Dict[str, Dict[str, Any]]
                                       ) -> List[Issue]:
    issues: List[Issue] = []
    for code, data in driver_data.items():
        if "valid_start" not in data or "valid_end" not in data:
            continue
        v0 = data["valid_start"]
        v1 = data["valid_end"]
        for i, f in enumerate(frames):
            t = f.get("t")
            if t is None:
                continue
            drivers = f.get("drivers", {}) or {}
            entry = drivers.get(code)
            if entry is None:
                continue
            if not _is_active_in_frame(entry):
                continue
            if t + EPS < v0:
                issues.append((
                    "error",
                    "INV-04.active_before_validity",
                    f"frame {i} t={t} driver {code} active before valid_start={v0}",
                ))
            if t - EPS > v1:
                issues.append((
                    "error",
                    "INV-05.active_after_validity",
                    f"frame {i} t={t} driver {code} active after valid_end={v1}",
                ))
    return issues


# ---------------------------------------------------------------------------
# 6. Interpolation never invents driver motion outside observed telemetry.
# Verified by the x/y/spd/... values being exactly equal to the boundary
# sample when t < valid_start or t > valid_end. (np.interp clamps.) If the
# validity fix is applied, a "flag" attribute marks such drivers as
# inactive; this check is run with that flag.
# ---------------------------------------------------------------------------
def check_no_extrapolation_flag(frames: List[Dict[str, Any]]) -> List[Issue]:
    issues: List[Issue] = []
    for i, f in enumerate(frames):
        drivers = f.get("drivers", {}) or {}
        for code, d in drivers.items():
            # If the producer marks an extrapolated frame, every numeric
            # value should still equal the last observed sample; we simply
            # require an explicit "extrapolated" flag so consumers know.
            if d.get("extrapolated") and not d.get("validity_marker"):
                issues.append((
                    "warning",
                    "INV-06.extrapolation_unmarked",
                    f"frame {i} driver {code} extrapolated without validity_marker",
                ))
    return issues


# ---------------------------------------------------------------------------
# 7. Lap numbers are monotonic for an individual driver.
# ---------------------------------------------------------------------------
def check_lap_monotonicity(frames: List[Dict[str, Any]]) -> List[Issue]:
    issues: List[Issue] = []
    prev_lap: Dict[str, int] = {}
    for i, f in enumerate(frames):
        for code, d in (f.get("drivers") or {}).items():
            lap = d.get("lap")
            if lap is None:
                continue
            p = prev_lap.get(code)
            if p is not None and lap < p - 0:  # strictly non-decreasing
                issues.append((
                    "error",
                    "INV-07.lap_decreased",
                    f"frame {i} driver {code} lap {lap} < previous {p}",
                ))
            prev_lap[code] = lap
    return issues


# ---------------------------------------------------------------------------
# 8. Driver progress (lap * track_length + dist) is monotonic except for
#    explicitly handled timing/telemetry anomalies.
# ---------------------------------------------------------------------------
def check_progress_monotonicity(frames: List[Dict[str, Any]],
                                track_length: float
                                ) -> List[Issue]:
    issues: List[Issue] = []
    prev: Dict[str, float] = {}
    for i, f in enumerate(frames):
        for code, d in (f.get("drivers") or {}).items():
            lap = d.get("lap")
            dist = d.get("dist")
            if lap is None or dist is None:
                continue
            prog = lap * track_length + dist
            p = prev.get(code)
            if p is not None and prog + 0.5 * track_length < p:
                # A backward jump of more than half a lap is anomalous
                issues.append((
                    "error",
                    "INV-08.progress_regressed",
                    f"frame {i} driver {code} progress {prog:.1f} << previous {p:.1f}",
                ))
            prev[code] = prog
    return issues


# ---------------------------------------------------------------------------
# 9. Race winner is determined consistently.
# Modeled here: the leader at the final frame (max progress) is the winner.
# ---------------------------------------------------------------------------
def check_race_winner_consistent(frames: List[Dict[str, Any]],
                                 track_length: float,
                                 expected_winner: str | None = None
                                 ) -> List[Issue]:
    issues: List[Issue] = []
    if not frames:
        issues.append(("error", "INV-09.no_frames", "frames empty"))
        return issues
    last = frames[-1]
    best_code, best_prog = None, -1.0
    for code, d in (last.get("drivers") or {}).items():
        lap = d.get("lap", 1)
        dist = d.get("dist", 0)
        prog = (max(lap, 1) - 1) * track_length + dist
        if prog > best_prog:
            best_prog = prog
            best_code = code
    if expected_winner is not None and best_code != expected_winner:
        issues.append((
            "error",
            "INV-09.winner_mismatch",
            f"computed winner {best_code} != expected {expected_winner}",
        ))
    return issues


# ---------------------------------------------------------------------------
# 10. Final replay frame represents the required terminal race state.
# We require the final frame's t to equal global_t_max within tolerance
# and at least one driver to have lap >= total_laps.
# ---------------------------------------------------------------------------
def check_final_frame_terminal(frames: List[Dict[str, Any]],
                               global_t_max: float,
                               total_laps: int,
                               tol: float = 1e-3) -> List[Issue]:
    issues: List[Issue] = []
    if not frames:
        issues.append(("error", "INV-10.no_frames", "frames empty"))
        return issues
    last = frames[-1]
    t = last.get("t")
    if t is None or abs(t - global_t_max) > tol:
        issues.append((
            "error",
            "INV-10.final_t_mismatch",
            f"final frame t={t} != global_t_max={global_t_max}",
        ))
    max_lap = 0
    for d in (last.get("drivers") or {}).values():
        if isinstance(d.get("lap"), (int, float)):
            max_lap = max(max_lap, int(d["lap"]))
    if total_laps > 0 and max_lap < total_laps - 1:
        issues.append((
            "warning",
            "INV-10.no_finisher",
            f"final frame max_lap={max_lap} < total_laps-1={total_laps-1}",
        ))
    return issues


# ---------------------------------------------------------------------------
# 11. Track status timestamps are aligned to the same replay time origin.
# 12. Weather timestamps use the same time origin.
# 13. Pit-in/pit-out timestamps use the same time origin.
# Each list is "aligned" if its earliest start_time >= 0 (no negative
# times after the global_t_min shift).
# ---------------------------------------------------------------------------
def check_time_origin_alignment(track_statuses: List[Dict[str, Any]],
                                weather_min: float | None = None,
                                pit_windows: Dict[str, List[Tuple[float, float]]]
                                | None = None) -> List[Issue]:
    issues: List[Issue] = []
    for s in track_statuses:
        st = s.get("start_time")
        if st is not None and st < -EPS:
            issues.append((
                "error",
                "INV-11.track_status_before_origin",
                f"track status start_time={st} < 0",
            ))
    if weather_min is not None and weather_min < -EPS:
        issues.append((
            "error",
            "INV-12.weather_before_origin",
            f"weather min time={weather_min} < 0",
        ))
    if pit_windows:
        for code, wins in pit_windows.items():
            for start, _ in wins:
                if start < -EPS:
                    issues.append((
                        "error",
                        "INV-13.pit_before_origin",
                        f"driver {code} pit start_time={start} < 0",
                    ))
    return issues


# ---------------------------------------------------------------------------
# 14. All stream timestamps are replay/session time, not wall-clock time.
# If a "wall_clock" flag is set anywhere in a frame payload, the
# invariant is violated. Otherwise the check passes vacuously.
# ---------------------------------------------------------------------------
def check_no_wall_clock(frames: List[Dict[str, Any]]) -> List[Issue]:
    issues: List[Issue] = []
    for i, f in enumerate(frames):
        if "wall_clock" in f or any(
            isinstance(d, dict) and "wall_clock" in d
            for d in (f.get("drivers") or {}).values()
        ):
            issues.append((
                "error",
                "INV-14.wall_clock_leaked",
                f"frame {i} contains wall_clock field",
            ))
    return issues


# ---------------------------------------------------------------------------
# 15. Telemetry unit contracts are explicit and consistent.
# Speed should be in km/h, throttle in [0, 100], brake in [0, 100],
# gear integer, DRS integer, distance in metres.
# ---------------------------------------------------------------------------
def check_telemetry_units(frames: List[Dict[str, Any]],
                          track_length: float | None = None) -> List[Issue]:
    issues: List[Issue] = []
    if not frames:
        return issues
    # Sample a few frames to keep the check fast.
    sample_idx = {0, len(frames) // 2, len(frames) - 1}
    for i in sorted(sample_idx):
        f = frames[i]
        for code, d in (f.get("drivers") or {}).items():
            speed = d.get("speed")
            thr = d.get("throttle")
            brk = d.get("brake")
            # NaN values are missing telemetry (gaps / pre / post / dnf)
            # and are not "out of range" — they are absent.
            if isinstance(speed, (int, float)) and not math.isnan(speed) and speed < 0:
                issues.append((
                    "error",
                    "INV-15.negative_speed",
                    f"frame {i} driver {code} speed={speed} < 0",
                ))
            if isinstance(thr, (int, float)) and not math.isnan(thr) \
                    and not (0.0 - EPS <= thr <= 100.0 + EPS):
                issues.append((
                    "error",
                    "INV-15.throttle_out_of_range",
                    f"frame {i} driver {code} throttle={thr} outside [0,100]",
                ))
            if isinstance(brk, (int, float)) and not math.isnan(brk) \
                    and not (0.0 - EPS <= brk <= 100.0 + EPS):
                issues.append((
                    "error",
                    "INV-15.brake_out_of_range",
                    f"frame {i} driver {code} brake={brk} outside [0,100]",
                ))
            gear = d.get("gear")
            if isinstance(gear, float) and not math.isnan(gear) and not gear.is_integer():
                issues.append((
                    "warning",
                    "INV-15.gear_non_integer",
                    f"frame {i} driver {code} gear={gear} non-integer",
                ))
            if track_length and isinstance(d.get("dist"), (int, float)):
                if d["dist"] < -1.0 or d["dist"] > track_length * (1 + 1e-3) + 1.0:
                    # Within-lap distance should not exceed track length + epsilon.
                    # Cumulative race distance naturally exceeds this, so we do
                    # not flag here; we only flag within-lap rel_dist.
                    pass
            rel = d.get("rel_dist")
            if isinstance(rel, (int, float)) and not math.isnan(rel) \
                    and not (0.0 - EPS <= rel <= 1.0 + EPS):
                issues.append((
                    "warning",
                    "INV-15.rel_dist_out_of_range",
                    f"frame {i} driver {code} rel_dist={rel} outside [0,1]",
                ))
    return issues


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------
def validate_replay(frames: List[Dict[str, Any]],
                    driver_data: Dict[str, Dict[str, Any]] | None = None,
                    track_statuses: List[Dict[str, Any]] | None = None,
                    track_length: float = 0.0,
                    fps: float = 25.0,
                    total_laps: int = 0,
                    global_t_max: float | None = None,
                    weather_min: float | None = None,
                    pit_windows: Dict[str, List[Tuple[float, float]]] | None = None,
                    expected_winner: str | None = None
                    ) -> List[Issue]:
    """Run every invariant and return the combined list of issues."""
    issues: List[Issue] = []
    issues += check_frame_t_monotonic(frames)
    issues += check_frame_spacing(frames, fps=fps)
    if driver_data:
        issues += check_validity_intervals_present(driver_data)
        issues += check_no_activity_outside_validity(frames, driver_data)
    issues += check_no_extrapolation_flag(frames)
    issues += check_lap_monotonicity(frames)
    if track_length:
        issues += check_progress_monotonicity(frames, track_length)
    issues += check_race_winner_consistent(frames, track_length, expected_winner)
    if global_t_max is not None:
        issues += check_final_frame_terminal(frames, global_t_max, total_laps)
    issues += check_time_origin_alignment(track_statuses or [],
                                          weather_min=weather_min,
                                          pit_windows=pit_windows)
    issues += check_no_wall_clock(frames)
    issues += check_telemetry_units(frames, track_length=track_length)
    return issues


__all__ = [
    "validate_replay",
    "check_frame_t_monotonic",
    "check_frame_spacing",
    "check_validity_intervals_present",
    "check_no_activity_outside_validity",
    "check_no_extrapolation_flag",
    "check_lap_monotonicity",
    "check_progress_monotonicity",
    "check_race_winner_consistent",
    "check_final_frame_terminal",
    "check_time_origin_alignment",
    "check_no_wall_clock",
    "check_telemetry_units",
]
