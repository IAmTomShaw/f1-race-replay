# Feature Plan & Issue Tracker

## Upstream Repository

**[IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay)** — 25 open issues, 93 open PRs at time of writing.

---

## Issues We're Solving (3 selected)

### Issue 1 — `[Easy-Medium]` Improve Playback Speed UX Consistency ([#141](https://github.com/IAmTomShaw/f1-race-replay/issues/141))

**Type:** Enhancement  
**Status:** Open, no assignee, no competing PRs  
**Reporter:** anirudhk06

**Problem:** Playback speed controls are tightly coupled inside the window class with scattered conditional branches across `race_replay.py`, `qualifying.py`, and `ui_components.py`. Speed scaling feels unintuitive because multiplicative steps produce non-standard values (1.6x, 3.2x).

**Solution:**
- Extract a `PlaybackController` class that centralizes speed state and step logic
- Use explicit step-based increments (0.5x → 1x → 1.5x → 2x → ... → 4x) for predictable UX
- Decouple input handling (keyboard/mouse) from speed logic
- Preserve existing behavior while reducing conditional branching

**Files to modify:**
- `src/interfaces/race_replay.py` — keyboard input handling + speed state
- `src/interfaces/qualifying.py` — same duplicated logic
- `src/ui_components.py` — mouse click handlers for speed buttons

---

### Issue 2 — `[Medium]` Final Race Position Doesn't Match Official Results ([#34](https://github.com/IAmTomShaw/f1-race-replay/issues/34))

**Type:** Bug (labeled by repo owner)  
**Status:** Open, no assignee, no competing PRs on upstream  
**Reporter:** jaxon3062 — **confirmed by IAmTomShaw (owner)**

**Problem:** The leaderboard at the end of a race replay doesn't match the official FIA classification. Positions are derived purely from telemetry distance (`RelativeDistance` + lap count), which becomes inaccurate near the finish line due to how FastF1 reports the final telemetry samples.

**Solution:**
- Use FastF1's `session.results` (`SessionResults` object) to get the official classification
- On the final frame (or when the leader crosses the finish), override telemetry-derived positions with `SessionResults.Position`
- Avoid `ClassifiedPosition` (which accounts for DQs) — use raw `Position` column instead
- As suggested by contributor xhemals: when a driver crosses the line on the final lap after the leader, snap their position to the official result

**Files to modify:**
- `src/f1_data.py` — frame-building pipeline (lines ~643-652 where positions are sorted by race distance)
- `src/interfaces/race_replay.py` — `_update_leaderboard` method to respect official results at race end

---

### Issue 3 — `[Hard]` Partial First Lap Inaccuracy Fix ([#248](https://github.com/IAmTomShaw/f1-race-replay/issues/248))

**Type:** Bug  
**Status:** Open, no assignee, no PRs  
**Reporter:** HEPNARL (project contributor)

**Problem:** During lap 1, drivers who retire or crash are incorrectly shown in P1 on the leaderboard. This happens because FastF1 creates a synthetic "partial lap" record for drivers who don't complete a timed lap. Their `LapStartTime` is set to session start, and their `Time` is set to when the first driver completes lap 1 — which makes distance-based sorting rank them at the front.

**Example:** Hulkenberg appears in P1 during lap 1 of the 2026 Australian GP despite retiring on the formation/opening lap.

**Solution:**
- Detect drivers with only synthetic partial laps by comparing their `Time` field against the first completed lap time
- Cross-reference: if a driver has exactly one lap and their lap `Time` matches the fastest first-lap completion, they likely retired
- Either remove retired drivers from the leaderboard during lap 1 or pin them at the bottom with a "RET" marker
- Handle edge cases: multiple retirements on lap 1, safety car deployments, red flags

**Files to modify:**
- `src/f1_data.py` — `_process_single_driver` and frame-building pipeline to flag partial-lap drivers
- `src/interfaces/race_replay.py` — leaderboard rendering to display retired drivers correctly

---

## Webapp Transformation Assessment

Several issues ask about turning this into a web/mobile app:
- [#218](https://github.com/IAmTomShaw/f1-race-replay/issues/218) — Tauri + React desktop GUI
- [#104](https://github.com/IAmTomShaw/f1-race-replay/issues/104) — Web/mobile app request
- [#60](https://github.com/IAmTomShaw/f1-race-replay/issues/60) — Electron GUI attempt

### Current State
The app is built on **Python Arcade** (OpenGL game framework), which **cannot be ported to web or mobile**. The repo owner (IAmTomShaw) confirmed this and said he's separately working on a web version.

### Existing Efforts
- **Electron GUI** (#60 / PR #101): Basic proof of concept by xhemals — shows year selection and can spawn the Python process. Stalled.
- **Tauri + React** (#218 / PR #240): Most advanced attempt by Lixander78 & Peppe37. Working PoC with:
  - FastAPI WebSocket bridge (`src/services/bridge.py`) that hooks into the telemetry TCP stream
  - React frontend consuming real-time telemetry
  - Orchestrator script (`run_poc.py`) managing both processes
  - Uses Canvas/PixiJS for 60fps track rendering

### How Hard Would It Be?

| Approach | Difficulty | Why |
|----------|-----------|-----|
| **Full rewrite in JS/TS** | Very Hard | Rewrite all FastF1 data loading, telemetry processing, and rendering. FastF1 is Python-only, so you'd need a Python backend API regardless. |
| **Tauri + FastAPI sidecar** | Hard | The Tauri PoC exists (PR #240) but needs: track rendering in Canvas, full leaderboard, all controls, pit wall insights. The Python backend stays as-is. Biggest effort is rebuilding the entire Arcade UI in React. |
| **Electron wrapper** | Medium-Hard | Same challenge as Tauri but heavier runtime. Electron approach (#60) is more basic/stalled. |
| **Flask/FastAPI + HTMX (lightweight)** | Medium | Serve telemetry over WebSocket, render with simple HTML/JS. Loses real-time smoothness but simplest path. |
| **Django + Plotly Dash** | Medium | Stay in Python ecosystem. Use Plotly Dash for interactive charts. Won't replicate the arcade-style track animation but could do leaderboard + telemetry charts. |

**Bottom line:** A full webapp replacement is a massive undertaking (the Arcade rendering alone is ~2500 lines in `ui_components.py`). The most feasible approach is the Tauri/React hybrid from PR #240, where the Python engine stays intact and a WebSocket bridge feeds data to a modern frontend. But even that PoC is far from feature-complete. **Not recommended for a 3-issue assignment.**

---

## Proposed Feature Additions (From Codebase Analysis)

These are features we identified by scanning the codebase that would add value and are realistic to implement:

### Quick Wins (could pair with an issue)

| Feature | Description | Effort | Relevant Files |
|---------|-------------|--------|----------------|
| **Throttle/Brake overlay in race replay** | This data is already loaded in `f1_data.py` but only displayed in qualifying mode. Add telemetry mini-charts to race replay. | Low-Medium | `race_replay.py`, `ui_components.py` |
| **Gear visualization** | Currently only shown as plain text in the driver info panel. Could be a colored indicator or mini gear-map. | Low | `ui_components.py` (line ~866) |
| **Pit stop duration tracking** | Pit lane positions are computed for safety car logic but pit stop durations aren't extracted or displayed. | Medium | `f1_data.py` (line ~300), `ui_components.py` |

### Medium Effort

| Feature | Description | Effort | Relevant Files |
|---------|-------------|--------|----------------|
| **Overtake detection & counter** | Track position changes between consecutive frames to detect overtakes. One of the 12 insights listed in the menu but entirely unimplemented. | Medium | `f1_data.py`, `insights_menu.py` |
| **Sector times in race mode** | Sector time display already exists in qualifying (`QualifyingLapTimeComponent`) but is absent from race replay. Adapt it. | Medium | `ui_components.py` (lines ~1920-2016) |
| **Tyre strategy visualization** | The Bayesian tyre model (`bayesian_tyre_model.py`, 175 lines) and degradation integration exist but have minimal UI presence. Add stint bars, compound timeline, degradation curves. | Medium | `bayesian_tyre_model.py`, `tyre_degradation_integration.py`, `ui_components.py` |

### Insight Menu Stubs (12 placeholders, 0 implemented)

The file `src/gui/insights_menu.py` defines 12 insight tools that show placeholder dialogs:

1. Speed Monitor
2. Position Tracker
3. Tyre Strategy Analyzer
4. Pit Stop Analysis
5. Gap Analysis
6. Sector Times
7. Lap Evolution
8. Top Speed Tracker
9. Flag Tracker
10. Overtake Counter
11. DRS Usage Tracker
12. Telemetry Stream Viewer (partially attempted)

Each of these is a potential contribution. The `PitWallWindow` template (`src/gui/pit_wall_window_template.py`) also has 6 TODO comments and is essentially empty — designed as a base class for custom insight windows.

### Settings Expansion

`src/lib/settings.py` currently only stores `cache_location` and `computed_data_location`. Missing:
- UI theme preferences
- Default playback speed
- HUD toggle defaults
- Telemetry display preferences (which overlays to show)
- Data refresh behavior

---

## Summary

| Priority | What | Issue/Feature | Difficulty |
|----------|------|--------------|------------|
| 1 | **Playback speed UX refactor** | Issue #141 | Easy-Medium |
| 2 | **Fix final race positions** | Issue #34 | Medium |
| 3 | **First lap inaccuracy** | Issue #248 | Hard |
| Bonus | Throttle/brake in race replay | Feature proposal | Low-Medium |
| Bonus | Overtake detection | Feature proposal | Medium |
| Bonus | Implement insight menu tools | Feature proposal | Medium each |
