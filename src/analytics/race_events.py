"""Race event extraction for timeline and progress bar visualization.

Pure analytics module with zero coupling to Arcade or Qt GUI classes.
"""
from __future__ import annotations

import math
from typing import List

EVENT_DNF = "dnf"
EVENT_YELLOW_FLAG = "yellow_flag"
EVENT_SAFETY_CAR = "safety_car"
EVENT_RED_FLAG = "red_flag"
EVENT_VSC = "vsc"
EVENT_LEADER_CHANGE = "leader_change"


def extract_race_events(
    frames: List[dict],
    track_statuses: List[dict],
    total_laps: int,
) -> List[dict]:
    """Extract DNF and flag events from telemetry frame and status data."""
    events: List[dict] = []

    if not frames:
        return events

    n_frames = len(frames)

    sample_rate = 25
    sample_indices = list(range(0, n_frames, sample_rate))
    if sample_indices and sample_indices[-1] != n_frames - 1:
        sample_indices.append(n_frames - 1)

    def _driver_is_present(v: dict) -> bool:
        if not isinstance(v, dict):
            return False
        val = v.get("validity")
        if val in ("active", "finished", "gap"):
            return True
        if val in ("dnf", "post", "dns", "pre"):
            return False
        if "active" in v:
            return bool(v["active"])
        return True

    first_active_sample = {}
    last_active_sample = {}
    last_active_lap = {}
    ever_finished = set()
    max_observed_lap = int(total_laps or 0)

    for s_pos, frame_idx in enumerate(sample_indices):
        frame = frames[frame_idx]
        drivers_data = frame.get("drivers", {}) if isinstance(frame, dict) else {}
        for code, v in drivers_data.items():
            if not isinstance(v, dict):
                continue
            lap_val = v.get("lap")
            if isinstance(lap_val, (int, float)) and not math.isnan(lap_val):
                max_observed_lap = max(max_observed_lap, int(lap_val))
            if v.get("validity") == "finished":
                ever_finished.add(code)
            if _driver_is_present(v):
                if code not in first_active_sample:
                    first_active_sample[code] = s_pos
                last_active_sample[code] = s_pos
                if lap_val is not None:
                    last_active_lap[code] = lap_val

    last_sample_pos = len(sample_indices) - 1
    for code, last_pos in last_active_sample.items():
        if last_pos >= last_sample_pos or code in ever_finished:
            continue
        dnf_frame_idx = sample_indices[last_pos + 1]
        lap = last_active_lap.get(code, "?")
        if (
            isinstance(lap, (int, float))
            and max_observed_lap >= 5
            and (
                int(lap) >= max_observed_lap
                or (
                    int(lap) >= max_observed_lap - 1
                    and dnf_frame_idx >= int(n_frames * 0.95)
                )
            )
        ):
            continue

        events.append({
            "type": EVENT_DNF,
            "frame": dnf_frame_idx,
            "label": code,
            "lap": lap,
        })

    for status in track_statuses:
        status_code = str(status.get("status", ""))
        start_time = status.get("start_time", 0)
        end_time = status.get("end_time")

        fps = 25
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps) if end_time else start_frame + 250

        if end_frame <= 0:
            continue

        if n_frames > 0:
            end_frame = min(end_frame, n_frames)

        event_type = None
        if status_code == "2":
            event_type = EVENT_YELLOW_FLAG
        elif status_code == "4":
            event_type = EVENT_SAFETY_CAR
        elif status_code == "5":
            event_type = EVENT_RED_FLAG
        elif status_code in ("6", "7"):
            event_type = EVENT_VSC

        if event_type:
            events.append({
                "type": event_type,
                "frame": start_frame,
                "end_frame": end_frame,
                "label": "",
                "lap": None,
            })

    return events
