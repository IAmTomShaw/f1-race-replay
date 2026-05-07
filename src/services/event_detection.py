"""
event_detection.py
==================
Race Event Detection Engine for F1 Race Replay.

Architecture
------------
Events are detected in a single pass over all telemetry frames BEFORE replay
begins. The result is an O(1) lookup table keyed by frame index:

    events_by_frame: dict[int, list[RaceEvent]]

This guarantees zero detection work during the render loop.

Detectors (Phase 1 — deterministic):
  - Pit entry / exit (uses official pit window data embedded in frames)
  - DRS enabled / disabled (telemetry DRS field transitions)
  - Safety Car deployed / ending (track_status codes)
  - Yellow flag (track_status codes)
  - Fastest lap (running minimum lap time)

Detectors (Phase 2 — positional analytics):
  - Overtakes (track-distance sort with persistence filter)
  - Battle detection (gap threshold + cooldown)

Detectors (Phase 3 — heuristic analytics):
  - Crash detection (sudden speed collapse)
  - Spin detection (rapid heading change + speed drop)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass
class RaceEvent:
    """
    A single race event that occurred at a specific frame.

    Attributes
    ----------
    frame_index   : Index into the frames list where the event was detected.
    timestamp     : Session time in seconds at detection.
    event_type    : Short category tag used for colour-coding in the UI.
                    One of: PIT_ENTRY, PIT_EXIT, DRS_ON, DRS_OFF, SAFETY_CAR,
                    SC_ENDING, YELLOW_FLAG, FASTEST_LAP, OVERTAKE, BATTLE,
                    CRASH, SPIN.
    message       : Human-readable description shown in the event feed.
    severity      : "info" | "warning" | "critical" | "purple"
                    Maps to UI colour (white / yellow / red / purple).
    driver        : Primary driver abbreviation (e.g. "VER"), or None.
    secondary_driver : Secondary driver for two-car events (e.g. overtakes).
    duration      : How long (seconds of real time) the card stays visible.
    """
    frame_index: int
    timestamp: float
    event_type: str
    message: str
    severity: str = "info"
    driver: Optional[str] = None
    secondary_driver: Optional[str] = None
    duration: float = 6.0
    # World coordinates of the incident (set for CRASH and SPIN events)
    world_x: Optional[float] = None
    world_y: Optional[float] = None
    # Priority for rate limiting (1=critical, 2=high, 3=medium, 4=low)
    # Lower number = higher priority = shown even at fast playback speeds
    priority: int = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _project_track_distance(x: float, y: float, ref_xs, ref_ys, ref_cumdist, tree) -> float:
    """Project a (x, y) world position onto the reference polyline and return
    the cumulative distance along the track (metres)."""
    _, idx = tree.query([x, y])
    idx = int(idx)
    if idx < len(ref_xs) - 1:
        x1, y1 = ref_xs[idx], ref_ys[idx]
        x2, y2 = ref_xs[idx + 1], ref_ys[idx + 1]
        vx, vy = x2 - x1, y2 - y1
        seg_len2 = vx * vx + vy * vy
        if seg_len2 > 0:
            t = ((x - x1) * vx + (y - y1) * vy) / seg_len2
            t = max(0.0, min(1.0, t))
            seg_dist = math.sqrt((x1 + t * vx - x1) ** 2 + (y1 + t * vy - y1) ** 2)
            return float(ref_cumdist[idx] + seg_dist)
    return float(ref_cumdist[idx])


def _total_progress(lap: int, track_dist: float, track_length: float) -> float:
    """Race progress in metres since start (lap-1)*L + track_dist."""
    return float(max(lap, 1) - 1) * track_length + track_dist


def _get_track_status_at(t: float, track_statuses: list) -> str:
    """Return the track status code string at time *t* (seconds)."""
    current = "1"  # green flag default
    for status in track_statuses:
        if status["start_time"] <= t and (status["end_time"] is None or t < status["end_time"]):
            current = str(status.get("status", "1"))
            break
    return current


# ---------------------------------------------------------------------------
# Phase 1 — Deterministic detectors
# ---------------------------------------------------------------------------

def _detect_pit_events(frames, FPS: float, events: defaultdict):
    """Detect pit entry and pit exit from the `in_pit` field embedded in each
    driver's frame data by f1_data.py."""
    prev_in_pit: dict[str, bool] = {}

    for fi, frame in enumerate(frames):
        drivers = frame.get("drivers", {})
        t = frame["t"]
        for code, pos in drivers.items():
            cur_pitting = bool(pos.get("in_pit", False))
            prev = prev_in_pit.get(code, False)

            if not prev and cur_pitting:
                events[fi].append(RaceEvent(
                    frame_index=fi, timestamp=t,
                    event_type="PIT_ENTRY",
                    message=f"{code} enters pit lane",
                    severity="info", driver=code,
                    duration=7.0, priority=3,
                ))
            elif prev and not cur_pitting:
                events[fi].append(RaceEvent(
                    frame_index=fi, timestamp=t,
                    event_type="PIT_EXIT",
                    message=f"{code} exits pit lane",
                    severity="info", driver=code,
                    duration=7.0, priority=3,
                ))

            prev_in_pit[code] = cur_pitting


def _detect_drs_events(frames, FPS: float, events: defaultdict):
    """Detect DRS enable / disable transitions with a minimum 2-second
    cooldown per driver to prevent rapid toggling noise."""
    COOLDOWN_FRAMES = int(2.0 * FPS)
    DRS_ACTIVE_THRESHOLD = 10  # DRS values >= 10 indicate open pod

    prev_drs: dict[str, int] = {}
    last_event_frame: dict[str, int] = {}

    for fi, frame in enumerate(frames):
        drivers = frame.get("drivers", {})
        t = frame["t"]
        for code, pos in drivers.items():
            cur_drs = int(pos.get("drs", 0))
            prev = prev_drs.get(code, 0)
            last_fi = last_event_frame.get(code, -COOLDOWN_FRAMES - 1)

            if fi - last_fi >= COOLDOWN_FRAMES:
                was_active = prev >= DRS_ACTIVE_THRESHOLD
                is_active = cur_drs >= DRS_ACTIVE_THRESHOLD

                if not was_active and is_active:
                    events[fi].append(RaceEvent(
                        frame_index=fi, timestamp=t,
                        event_type="DRS_ON",
                        message=f"{code} enables DRS",
                        severity="info", driver=code,
                        duration=5.0, priority=4,
                    ))
                    last_event_frame[code] = fi

                elif was_active and not is_active:
                    events[fi].append(RaceEvent(
                        frame_index=fi, timestamp=t,
                        event_type="DRS_OFF",
                        message=f"{code} disables DRS",
                        severity="info", driver=code,
                        duration=5.0, priority=4,
                    ))
                    last_event_frame[code] = fi

            prev_drs[code] = cur_drs


def _detect_track_status_events(frames, track_statuses: list, events: defaultdict):
    """Detect Safety Car deployments, SC endings, and yellow flags from
    track_status codes. Emits events only on transitions."""
    STATUS_SC = "4"
    STATUS_VSC = "6"
    STATUS_VSC2 = "7"
    STATUS_YELLOW = "2"
    STATUS_GREEN = "1"

    prev_status = STATUS_GREEN
    sc_deployed = False
    vsc_deployed = False

    for fi, frame in enumerate(frames):
        t = frame["t"]
        cur = _get_track_status_at(t, track_statuses)

        # --- Safety Car ---
        if prev_status != STATUS_SC and cur == STATUS_SC:
            sc_deployed = True
            events[fi].append(RaceEvent(
                frame_index=fi, timestamp=t,
                event_type="SAFETY_CAR",
                message="Safety Car Deployed",
                severity="warning", duration=8.0, priority=1,
            ))

        elif sc_deployed and prev_status == STATUS_SC and cur != STATUS_SC:
            sc_deployed = False
            events[fi].append(RaceEvent(
                frame_index=fi, timestamp=t,
                event_type="SC_ENDING",
                message="Safety Car Returning to Pits",
                severity="warning", duration=8.0, priority=1,
            ))

        # --- VSC ---
        if prev_status not in (STATUS_VSC, STATUS_VSC2) and cur in (STATUS_VSC, STATUS_VSC2):
            vsc_deployed = True
            events[fi].append(RaceEvent(
                frame_index=fi, timestamp=t,
                event_type="SAFETY_CAR",
                message="Virtual Safety Car Deployed",
                severity="warning", duration=8.0, priority=1,
            ))

        elif vsc_deployed and prev_status in (STATUS_VSC, STATUS_VSC2) and cur not in (STATUS_VSC, STATUS_VSC2):
            vsc_deployed = False
            events[fi].append(RaceEvent(
                frame_index=fi, timestamp=t,
                event_type="SC_ENDING",
                message="Virtual Safety Car Ending",
                severity="warning", duration=8.0, priority=1,
            ))

        # --- Yellow Flag ---
        if prev_status != STATUS_YELLOW and cur == STATUS_YELLOW:
            events[fi].append(RaceEvent(
                frame_index=fi, timestamp=t,
                event_type="YELLOW_FLAG",
                message="Yellow Flag",
                severity="warning", duration=6.0, priority=2,
            ))

        prev_status = cur


def _detect_fastest_lap(frames, FPS: float, events: defaultdict):
    """
    Detect fastest lap improvements using the `lap` (lap number) transition
    as a completion signal. When a driver's lap number increases, we estimate
    their last lap time from the elapsed session time since the previous
    lap-start frame. The driver with the all-time best is marked.
    """
    # Track when each driver last started a new lap
    lap_start_time: dict[str, float] = {}
    prev_lap: dict[str, int] = {}
    best_lap_time: float = float("inf")

    for fi, frame in enumerate(frames):
        t = frame["t"]
        drivers = frame.get("drivers", {})

        for code, pos in drivers.items():
            cur_lap = int(pos.get("lap", 1))
            prev = prev_lap.get(code, cur_lap)

            if cur_lap != prev:
                # Driver completed a lap — compute how long it took
                start_t = lap_start_time.get(code)
                if start_t is not None and cur_lap > prev:
                    lap_time = t - start_t
                    # Sanity-check: a valid F1 lap is between 60 s and 200 s
                    if 60.0 < lap_time < 200.0 and lap_time < best_lap_time:
                        best_lap_time = lap_time
                        mins = int(lap_time // 60)
                        secs = lap_time % 60
                        time_str = f"{mins}:{secs:06.3f}"
                        events[fi].append(RaceEvent(
                            frame_index=fi, timestamp=t,
                            event_type="FASTEST_LAP",
                            message=f"{code} sets fastest lap ({time_str})",
                            severity="purple", driver=code,
                            duration=8.0, priority=2,
                        ))

                lap_start_time[code] = t

            prev_lap[code] = cur_lap
            if code not in lap_start_time:
                lap_start_time[code] = t


# ---------------------------------------------------------------------------
# Phase 2 — Positional analytics (overtakes & battles)
# ---------------------------------------------------------------------------

def _build_track_geometry(frames):
    """
    Extract a lightweight track reference polyline from car positions so that
    event_detection.py has no dependency on example-lap data.  Uses the first
    500 frames of driver positions to approximate a reference.

    Returns (ref_xs, ref_ys, ref_cumdist, tree) or None if unavailable.
    """
    try:
        from scipy.spatial import cKDTree

        # Collect positions from the first 200 frames, deduplicate densely
        xs_all, ys_all = [], []
        for frame in frames[:200]:
            for pos in frame.get("drivers", {}).values():
                xs_all.append(pos.get("x", 0.0))
                ys_all.append(pos.get("y", 0.0))

        if len(xs_all) < 50:
            return None, None, None, None

        # Build a KD-tree over all sampled points then extract the convex hull
        # approximation using angular sorting around centroid — a fast proxy
        # for a circuit reference line.
        cx = np.mean(xs_all)
        cy = np.mean(ys_all)
        angles = np.arctan2(np.array(ys_all) - cy, np.array(xs_all) - cx)
        order = np.argsort(angles)
        ref_xs = np.array(xs_all)[order]
        ref_ys = np.array(ys_all)[order]

        # Densify
        t_old = np.linspace(0, 1, len(ref_xs))
        t_new = np.linspace(0, 1, 2000)
        ref_xs = np.interp(t_new, t_old, ref_xs)
        ref_ys = np.interp(t_new, t_old, ref_ys)

        diffs = np.sqrt(np.diff(ref_xs) ** 2 + np.diff(ref_ys) ** 2)
        ref_cumdist = np.concatenate(([0.0], np.cumsum(diffs)))
        tree = cKDTree(np.column_stack((ref_xs, ref_ys)))

        return ref_xs, ref_ys, ref_cumdist, tree

    except Exception as e:
        print(f"[EventDetection] Could not build track geometry: {e}")
        return None, None, None, None


def _detect_overtakes_and_battles(frames, FPS: float, events: defaultdict,
                                   ref_xs, ref_ys, ref_cumdist, tree):
    """
    Detect overtakes and battles using track-distance projections.

    Algorithm
    ---------
    For each frame:
      1. Project every car onto the reference line → track_distance.
      2. Sort drivers by total_progress (laps * L + track_dist).
      3. Compare order to the previous frame's order.
      4. If two neighbours swapped → candidate overtake.
      5. Confirm the overtake only after the new order is maintained for
         OVERTAKE_HOLD_FRAMES consecutive frames.

    Battle detection:
      If two adjacent cars have a gap below BATTLE_GAP_METRES for at least
      BATTLE_HOLD_FRAMES frames, emit a battle event (with cooldown).
    """
    if tree is None:
        return

    ref_total = float(ref_cumdist[-1]) if len(ref_cumdist) > 0 else 0.0
    if ref_total < 100.0:
        return

    OVERTAKE_HOLD_FRAMES = int(1.5 * FPS)    # 1.5 s of maintained position
    BATTLE_GAP_METRES = 80.0                   # ~1 second gap at 80 m/s
    BATTLE_HOLD_FRAMES = int(2.0 * FPS)       # must persist 2 s
    BATTLE_COOLDOWN_FRAMES = int(15.0 * FPS)  # 15 s between battle cards

    prev_order: list[str] = []

    # Candidate overtakes: dict of (ahead_code, behind_code) -> frame when swap first seen
    candidate_swaps: dict[tuple[str, str], int] = {}
    confirmed_overtakes: set[tuple[str, str]] = set()

    # Battle tracking: dict of (code_a, code_b) -> frames_close counter
    battle_counters: dict[tuple[str, str], int] = {}
    battle_last_event: dict[tuple[str, str], int] = {}

    for fi, frame in enumerate(frames):
        t = frame["t"]
        drivers = frame.get("drivers", {})
        if not drivers:
            continue

        # Step 1 & 2: Compute total progress per driver and sort
        progress: dict[str, float] = {}
        for code, pos in drivers.items():
            x, y = pos.get("x", 0.0), pos.get("y", 0.0)
            lap = int(pos.get("lap", 1))
            td = _project_track_distance(x, y, ref_xs, ref_ys, ref_cumdist, tree)
            progress[code] = _total_progress(lap, td, ref_total)

        # Sort descending (leader first)
        sorted_drivers = sorted(progress.keys(), key=lambda c: progress[c], reverse=True)

        # --- Overtake detection ---
        if prev_order:
            cur_set = set(sorted_drivers)
            prev_set = set(prev_order)
            common = [c for c in sorted_drivers if c in prev_set]
            prev_common = [c for c in prev_order if c in cur_set]

            # Check every neighbouring pair in the current order
            for i in range(len(common) - 1):
                ahead = common[i]
                behind = common[i + 1]

                # Were they swapped in the previous frame?
                if prev_common.index(ahead) > prev_common.index(behind):
                    key = (ahead, behind)
                    if key not in candidate_swaps:
                        candidate_swaps[key] = fi
                else:
                    # Remove stale candidate (order reverted)
                    candidate_swaps.pop((behind, ahead), None)

            # Confirm candidates that have held for OVERTAKE_HOLD_FRAMES
            to_remove = []
            for (ahead, behind), start_fi in candidate_swaps.items():
                if fi - start_fi >= OVERTAKE_HOLD_FRAMES:
                    # Confirm and determine position
                    pos_ahead = sorted_drivers.index(ahead) + 1 if ahead in sorted_drivers else "?"
                    event_key = (ahead, behind)
                    if event_key not in confirmed_overtakes:
                        confirmed_overtakes.add(event_key)
                        events[fi].append(RaceEvent(
                            frame_index=fi, timestamp=t,
                            event_type="OVERTAKE",
                            message=f"{ahead} overtakes {behind} for P{pos_ahead}",
                            severity="info", driver=ahead,
                            secondary_driver=behind,
                            duration=7.0, priority=2,
                        ))
                    to_remove.append(event_key)

            for k in to_remove:
                candidate_swaps.pop(k, None)
                confirmed_overtakes.discard(k)

        # --- Battle detection ---
        for i in range(len(sorted_drivers) - 1):
            a = sorted_drivers[i]
            b = sorted_drivers[i + 1]
            gap_m = abs(progress[a] - progress[b])

            pair = (a, b)
            if gap_m <= BATTLE_GAP_METRES:
                battle_counters[pair] = battle_counters.get(pair, 0) + 1
                if battle_counters[pair] >= BATTLE_HOLD_FRAMES:
                    last_fi = battle_last_event.get(pair, -BATTLE_COOLDOWN_FRAMES - 1)
                    if fi - last_fi >= BATTLE_COOLDOWN_FRAMES:
                        events[fi].append(RaceEvent(
                            frame_index=fi, timestamp=t,
                            event_type="BATTLE",
                            message=f"{a} and {b} are battling!",
                            severity="info", driver=a,
                            secondary_driver=b,
                            duration=6.0, priority=3,
                        ))
                        battle_last_event[pair] = fi
                        battle_counters[pair] = 0  # Reset so we don't spam
            else:
                battle_counters[pair] = 0

        prev_order = sorted_drivers


# ---------------------------------------------------------------------------
# Phase 3 — Heuristic analytics (crash & spin)
# ---------------------------------------------------------------------------

def _detect_crash_and_spin(frames, FPS: float, events: defaultdict):
    """
    Heuristic crash and spin detection.

    Crash heuristic:
      - Speed drops > 80 km/h within 1 second AND car was moving fast (>100 km/h).
      - Cooldown of 20 s per driver.

    Spin heuristic:
      - Rapid heading angle change (>90 degrees in 0.5 s) AND simultaneous
        speed drop of >40 km/h.
      - Cooldown of 15 s per driver.

    These are labelled "Possible" to acknowledge they are approximations.
    """
    CRASH_SPEED_DROP = 80.0       # km/h lost in 1 second
    CRASH_MIN_SPEED = 100.0       # must have been going fast
    CRASH_WINDOW = int(1.0 * FPS)
    CRASH_COOLDOWN = int(20.0 * FPS)

    SPIN_ANGLE_DEG = 90.0         # heading change threshold (degrees)
    SPIN_SPEED_DROP = 40.0        # km/h
    SPIN_WINDOW = int(0.5 * FPS)
    SPIN_COOLDOWN = int(15.0 * FPS)

    prev_speed: dict[str, list[float]] = {}   # rolling window
    prev_heading: dict[str, list[float]] = {}
    prev_x: dict[str, float] = {}
    prev_y: dict[str, float] = {}

    crash_last: dict[str, int] = {}
    spin_last: dict[str, int] = {}

    for fi, frame in enumerate(frames):
        t = frame["t"]
        drivers = frame.get("drivers", {})

        for code, pos in drivers.items():
            cur_speed = float(pos.get("speed", 0.0))
            cur_x = float(pos.get("x", 0.0))
            cur_y = float(pos.get("y", 0.0))

            # Compute movement heading from dx/dy
            px = prev_x.get(code, cur_x)
            py = prev_y.get(code, cur_y)
            dx, dy = cur_x - px, cur_y - py
            if abs(dx) > 0.01 or abs(dy) > 0.01:
                cur_heading = math.degrees(math.atan2(dy, dx))
            else:
                cur_heading = None

            # Maintain rolling windows
            speed_win = prev_speed.get(code, [])
            speed_win.append(cur_speed)
            if len(speed_win) > CRASH_WINDOW:
                speed_win.pop(0)
            prev_speed[code] = speed_win

            heading_win = prev_heading.get(code, [])
            if cur_heading is not None:
                heading_win.append(cur_heading)
                if len(heading_win) > SPIN_WINDOW:
                    heading_win.pop(0)
            prev_heading[code] = heading_win

            # --- Crash detection ---
            last_crash = crash_last.get(code, -CRASH_COOLDOWN - 1)
            if (len(speed_win) >= CRASH_WINDOW and
                    fi - last_crash >= CRASH_COOLDOWN and
                    speed_win[0] >= CRASH_MIN_SPEED and
                    (speed_win[0] - cur_speed) >= CRASH_SPEED_DROP):
                events[fi].append(RaceEvent(
                    frame_index=fi, timestamp=t,
                    event_type="CRASH",
                    message=f"Possible incident detected — {code}",
                    severity="critical", driver=code,
                    duration=8.0, world_x=cur_x, world_y=cur_y,
                    priority=1,
                ))
                crash_last[code] = fi

            # --- Spin detection ---
            last_spin = spin_last.get(code, -SPIN_COOLDOWN - 1)
            if (len(heading_win) >= SPIN_WINDOW and cur_heading is not None and
                    fi - last_spin >= SPIN_COOLDOWN and
                    cur_speed < speed_win[0] - SPIN_SPEED_DROP):
                # Compute total angular change in the window
                angle_changes = []
                for j in range(1, len(heading_win)):
                    diff = abs(heading_win[j] - heading_win[j - 1])
                    diff = min(diff, 360.0 - diff)
                    angle_changes.append(diff)
                total_angle = sum(angle_changes)
                if total_angle >= SPIN_ANGLE_DEG:
                    events[fi].append(RaceEvent(
                        frame_index=fi, timestamp=t,
                        event_type="SPIN",
                        message=f"Possible spin — {code}",
                        severity="warning", driver=code,
                        duration=7.0, world_x=cur_x, world_y=cur_y,
                        priority=2,
                    ))
                    spin_last[code] = fi

            prev_x[code] = cur_x
            prev_y[code] = cur_y


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_race_events(frames: list, track_statuses: list, fps: float = 25.0) -> dict:
    """
    Run all event detectors over *frames* in a single pre-processing pass.

    Parameters
    ----------
    frames        : The fully-built list of frame dicts from f1_data.py.
    track_statuses: The formatted track status list from f1_data.py.
    fps           : Frames per second of the replay (default 25).

    Returns
    -------
    events_by_frame : dict[int, list[RaceEvent]]
        Keyed by frame index. Look up O(1) during replay with:
            frame_events = events_by_frame.get(current_frame_index, [])
    """
    if not frames:
        return {}

    print("[EventDetection] Starting event generation...")
    events: defaultdict[int, list[RaceEvent]] = defaultdict(list)

    # --- Phase 1: Deterministic ---
    print("[EventDetection]   Detecting pit events...")
    _detect_pit_events(frames, fps, events)

    print("[EventDetection]   Detecting DRS events...")
    _detect_drs_events(frames, fps, events)

    print("[EventDetection]   Detecting track status events (SC/VSC/Yellow)...")
    _detect_track_status_events(frames, track_statuses, events)

    print("[EventDetection]   Detecting fastest lap updates...")
    _detect_fastest_lap(frames, fps, events)

    # --- Phase 2: Positional analytics ---
    print("[EventDetection]   Building track geometry for positional analytics...")
    ref_xs, ref_ys, ref_cumdist, tree = _build_track_geometry(frames)

    print("[EventDetection]   Detecting overtakes and battles...")
    _detect_overtakes_and_battles(frames, fps, events, ref_xs, ref_ys, ref_cumdist, tree)

    # --- Phase 3: Heuristics ---
    print("[EventDetection]   Detecting crashes and spins (heuristic)...")
    _detect_crash_and_spin(frames, fps, events)

    total = sum(len(v) for v in events.values())
    print(f"[EventDetection] Done. {total} events detected across {len(events)} frames.")

    return dict(events)
