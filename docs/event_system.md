# Event System — Architecture Documentation

## Overview

The F1 Race Replay **Live Event Feed** is a broadcast-intelligence layer that
detects, structures, and displays race events in real time during replay
playback. Events are displayed as colour-coded notification cards that animate
smoothly into view and fade out automatically, giving the replay a
professional broadcast-TV feel.

---

## Pipeline

```
Telemetry Frames
      │
      ▼
Event Detection Engine          (src/services/event_detection.py)
      │
      ▼
events_by_frame dict            dict[frame_index → list[RaceEvent]]
      │
      ▼
Stored in pickle cache           (computed_data/*.pkl)
      │
      ▼
F1RaceReplayWindow.__init__      (src/interfaces/race_replay.py)
      │
      ▼ on_update (per frame)
EventFeedComponent.push_events  (src/ui_components.py)
      │
      ▼ on_draw (per frame)
EventFeedComponent.draw         → Arcade render calls
```

### Key Design Principle

> **Events are detected exactly once**, during the pre-processing pass in
> `get_race_telemetry()`, before the data is cached.  Detection never happens
> inside the render loop.

During replay, `on_update` does nothing more than an O(1) dict lookup:

```python
frame_events = self._events_by_frame.get(current_fi, [])
```

This keeps the render loop at constant cost regardless of session length or
the number of events in the race.

---

## Data Model

```python
@dataclass
class RaceEvent:
    frame_index:      int           # frame where event was detected
    timestamp:        float         # session time in seconds
    event_type:       str           # e.g. "OVERTAKE", "PIT_ENTRY"
    message:          str           # human-readable text shown in the feed
    severity:         str           # "info" | "warning" | "critical" | "purple"
    driver:           str | None    # primary driver abbreviation
    secondary_driver: str | None    # second driver (for two-car events)
    duration:         float         # card lifetime in seconds (default 6.0)
```

---

## Event Types

| Type | Trigger | Severity | Example |
|------|---------|----------|---------|
| `PIT_ENTRY` | `in_pit` flag transition `False → True` | info | `VER enters pit lane` |
| `PIT_EXIT` | `in_pit` flag transition `True → False` | info | `LEC exits pit lane` |
| `DRS_ON` | DRS value crosses ≥ 10 threshold | info | `NOR enables DRS` |
| `DRS_OFF` | DRS value drops below 10 | info | `RUS disables DRS` |
| `SAFETY_CAR` | `track_status` transitions to `"4"` or `"6/7"` | warning | `Safety Car Deployed` |
| `SC_ENDING` | `track_status` leaves `"4"` or `"6/7"` | warning | `Safety Car Returning to Pits` |
| `YELLOW_FLAG` | `track_status` transitions to `"2"` | warning | `Yellow Flag` |
| `FASTEST_LAP` | New all-time session best lap computed | purple | `PIA sets fastest lap (1:29.203)` |
| `OVERTAKE` | Neighbouring drivers swap in track-distance order, held for 1.5 s | info | `VER overtakes NOR for P1` |
| `BATTLE` | Two adjacent cars within 80 m for 2 s | info | `LEC and HAM are battling!` |
| `CRASH` | Speed drop > 80 km/h within 1 s from speed > 100 km/h | critical | `Possible incident detected — SAI` |
| `SPIN` | Heading change > 90° in 0.5 s + speed drop > 40 km/h | warning | `Possible spin — ALO` |

---

## Detector Details

### Phase 1 — Deterministic (stable, high accuracy)

These detectors use data that is reliable and well-structured:

- **Pit entry/exit** — Uses the `in_pit` boolean already embedded per driver
  per frame by `f1_data.py` from official FastF1 pit window data.
- **DRS** — Reads the `drs` integer field. Values ≥ 10 indicate an open DRS
  pod (per FastF1 conventions). A per-driver 2-second cooldown prevents
  noise from oscillating values near the threshold.
- **Track status** — Uses the `track_statuses` list. Simple state-machine
  transition detection; only fires on edge (not while condition persists).
- **Fastest lap** — Detects lap number increments (lap boundary) and measures
  elapsed time to compute lap duration. Guards: 60–200 s validity window.

### Phase 2 — Positional Analytics (medium accuracy)

These detectors reconstruct track position from car coordinates:

- **Track geometry** — A lightweight reference polyline is built from the
  first 200 frames of car positions using angular sorting around the
  centroid. This avoids a dependency on the example lap at detection time.
- **Overtakes** — For each frame, all drivers are sorted by total race
  progress `(lap - 1) × L + track_dist`. If two neighbours swap, a
  candidate swap is recorded. It is only confirmed as an overtake after the
  new order persists for ≥ 1.5 seconds (OVERTAKE_HOLD_FRAMES).
- **Battles** — If two adjacent drivers are within 80 m of each other for
  ≥ 2 seconds, a battle card is emitted. A 15-second cooldown per pair
  prevents repeated cards for the same sustained battle.

### Phase 3 — Heuristic Analytics (approximations)

These are best-effort detections labelled "Possible" in their messages:

- **Crash** — Detects a speed drop > 80 km/h within a 1-second sliding
  window, requiring the car was travelling > 100 km/h before the incident.
  20-second per-driver cooldown.
- **Spin** — Detects a cumulative heading angle change > 90° within 0.5 s,
  combined with a simultaneous speed drop > 40 km/h. 15-second cooldown.

> **Note**: Because these are heuristic, all messages use "Possible" wording
> to clearly communicate approximation to viewers.

---

## UI Component: EventFeedComponent

```python
EventFeedComponent(right_margin=20, bottom_anchor=80)
```

Located in `src/ui_components.py`.

### Lifecycle

```
push_events(race_events)
        │
        ▼
pending_queue          (FIFO, unbounded)
        │
        ▼  (on_update — promotes when slots available)
active_events          (max 5 visible)
        │
        ▼  (on_update — expires when elapsed >= TOTAL_LIFETIME)
removed
```

### Fade Animation

| Phase | Duration | Opacity |
|-------|----------|---------|
| Fade in | 0.35 s | 0 → 255 (smoothstep) |
| Hold | 4.5 s | 255 |
| Fade out | 1.0 s | 255 → 0 (smoothstep) |
| **Total lifetime** | **5.85 s** | — |

Cards use a smoothstep curve (`t² × (3 - 2t)`) for both fade in and fade out
to avoid the linear "snap" feel.

### Card Visual Structure

```
┌──────────────────────────────────────────────────────┐
│▌ [OVERTAKE]   VER overtakes NOR for P1               │
└──────────────────────────────────────────────────────┘
 ↑               ↑
 4px accent      82px coloured badge    rest = message text
 stripe
```

### Colour Mapping

| Severity | Accent colour | Use case |
|----------|--------------|---------|
| `info` | Light blue `(130, 200, 255)` | Pit, DRS, Overtake, Battle |
| `warning` | Amber `(255, 210, 50)` | Safety Car, Yellow Flag, Spin |
| `critical` | Red `(255, 70, 70)` | Crash / Incident |
| `purple` | Purple `(200, 100, 255)` | Fastest Lap |

---

## Adding a New Event Type

1. **Write a detector** function in `event_detection.py` following the pattern:
   ```python
   def _detect_my_event(frames, FPS, events):
       for fi, frame in enumerate(frames):
           if <condition>:
               events[fi].append(RaceEvent(
                   frame_index=fi,
                   timestamp=frame["t"],
                   event_type="MY_EVENT",
                   message="...",
                   severity="info",
               ))
   ```

2. **Register it** in `generate_race_events()`:
   ```python
   _detect_my_event(frames, fps, events)
   ```

3. **Add a badge label** in `EventFeedComponent._TAG_LABELS`:
   ```python
   "MY_EVENT": "MY LABEL",
   ```

4. **Optionally map a severity** if you need a new colour accent — add the
   key to `EventFeedComponent._SEVERITY_ACCENT`.

That is the complete extension path. No changes needed in the render loop,
`f1_data.py`, or `race_replay.py`.

---

## Performance Notes

- **Detection** runs once per session load, before caching. On a 20-driver
  race of ~4000 frames, all three phases complete in under 5 seconds.
- **Replay cost per frame**: one `dict.get()` call (O(1)) + zero detection.
- **Rendering cost**: at most 5 card draws per frame using Arcade primitives
  (rectangles + text). Negligible compared to the track and car rendering.
- The `_build_track_geometry()` helper for positional analytics uses a
  2000-point dense polyline and a scipy `cKDTree` for all distance queries,
  matching the same approach used in `race_replay.py` for leader detection.
