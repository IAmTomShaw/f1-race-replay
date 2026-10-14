"""Lap-time extraction, classification, replay-time alignment, and formatting.

Extracted from `src.interfaces.race_replay` and `src.insights.lap_time_chart_window`
so that pure motorsport strategy & timing analytics have zero coupling to OpenGL
(`arcade.Window`) or Qt (`PySide6`/`matplotlib`) GUI toolkits.
"""
from __future__ import annotations

import numpy as np
from src.data.telemetry_resample import safe_int


def format_laptime(seconds, _pos=None) -> str:
    """Format lap time as M:SS.sss. Uses 1 decimal place for Y-axis labels."""
    if (
        seconds is None
        or not isinstance(seconds, (int, float))
        or not np.isfinite(seconds)
        or seconds <= 0
    ):
        return ""
    if _pos is not None:
        total_tenths = int(round(float(seconds) * 10))
        m, rem_tenths = divmod(total_tenths, 600)
        return f"{m}:{rem_tenths / 10.0:04.1f}"
    total_ms = int(round(float(seconds) * 1000))
    m, rem_ms = divmod(total_ms, 60000)
    return f"{m}:{rem_ms / 1000.0:06.3f}"


def format_delta(seconds, _pos=None) -> str:
    """Format delta time, omitting the '+' sign for effectively 0.0."""
    if (
        seconds is None
        or not isinstance(seconds, (int, float))
        or not np.isfinite(seconds)
    ):
        return ""
    if abs(seconds) < 0.0005:
        if _pos is not None:
            return "0.0"
        return "0.000s"
    if _pos is not None:
        return f"{seconds:+.1f}"
    return f"{seconds:+.3f}s"


def moving_average(values, window: int):
    """Compute a simple moving average, returning same-length list with None padding."""
    if len(values) < window:
        return values[:]
    result = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            avg = sum(values[i - window + 1:i + 1]) / window
            result.append(avg)
    return result


def entry_is_pit_entry(entry: dict) -> bool:
    return bool(entry.get("is_pit_entry"))


def entry_is_pit_affected(entry: dict, pit_threshold: float) -> bool:
    explicit = entry.get("is_pit_affected")
    if explicit is not None:
        return bool(explicit)
    legacy = entry.get("is_pit")
    if legacy is not None:
        return bool(legacy)
    t = entry.get("time_s")
    lap = entry.get("lap")
    if t is None or lap is None:
        return False
    return t > pit_threshold and lap > 1


def entry_is_out_lap(entry: dict) -> bool:
    return bool(entry.get("is_out_lap"))


def entry_is_outlier(entry: dict, pit_threshold: float) -> bool:
    explicit = entry.get("is_outlier")
    if explicit is not None:
        return bool(explicit)
    t = entry.get("time_s")
    if t is None:
        return False
    return (
        t > pit_threshold
        and not entry_is_pit_affected(entry, pit_threshold)
        and not entry_is_out_lap(entry)
    )


def is_clean_timed_entry(entry: dict, pit_threshold: float, sc_vsc_laps) -> bool:
    if not entry:
        return False
    t = entry.get("time_s")
    if t is None:
        return False
    return (
        0 < t <= pit_threshold
        and entry.get("lap") not in sc_vsc_laps
        and not entry_is_pit_affected(entry, pit_threshold)
        and not entry_is_out_lap(entry)
        and not entry_is_outlier(entry, pit_threshold)
    )


def entry_has_gap_discontinuity(entry: dict, pit_threshold: float, sc_vsc_laps) -> bool:
    if not entry:
        return False
    lap = entry.get("lap")
    return (
        entry_is_pit_affected(entry, pit_threshold)
        or entry_is_out_lap(entry)
        or entry_is_outlier(entry, pit_threshold)
        or (lap in sc_vsc_laps if lap is not None else False)
    )


def terminal_status_display_text(status) -> str:
    status_text = str(status or "").strip()
    if not status_text or status_text.lower() == "retired":
        return "Retired (DNF)"
    return status_text


def estimate_official_replay_time_offset(official_result, fallback_result):
    diffs = []
    for code, entries in official_result.items():
        fallback_entries = {
            entry.get("lap"): entry
            for entry in fallback_result.get(code, [])
            if isinstance(entry.get("end_time_s"), (int, float))
        }
        for entry in entries:
            if entry.get("time_source") == "frame_backfill":
                continue
            lap = entry.get("lap")
            fb_entry = fallback_entries.get(lap)
            line_time_s = entry.get("line_time_s")
            if fb_entry is None or not isinstance(line_time_s, (int, float)):
                continue
            diff = float(line_time_s) - float(fb_entry["end_time_s"])
            if 0.0 <= diff <= 8 * 3600:
                diffs.append(diff)
    if len(diffs) < 5:
        return None
    diffs.sort()
    return float(diffs[len(diffs) // 2])


def attach_replay_aligned_lap_times(result, replay_time_offset_s, fallback_result=None):
    fallback_by_code = {}
    if fallback_result:
        fallback_by_code = {
            code: {
                entry.get("lap"): entry
                for entry in entries
                if isinstance(entry.get("end_time_s"), (int, float))
            }
            for code, entries in fallback_result.items()
        }

    for code, entries in result.items():
        fallback_entries = fallback_by_code.get(code, {})
        for entry in entries:
            if entry.get("time_source") == "frame_backfill":
                fb_entry = fallback_entries.get(entry.get("lap"))
                if fb_entry is not None and isinstance(fb_entry.get("end_time_s"), (int, float)):
                    replay_end = float(fb_entry["end_time_s"])
                    entry.setdefault("replay_line_time_s", replay_end)
                    entry.setdefault("replay_end_time_s", replay_end)

            if replay_time_offset_s is None:
                continue

            for src_key, dst_key in (
                ("line_time_s", "replay_line_time_s"),
                ("end_time_s", "replay_end_time_s"),
            ):
                if isinstance(entry.get(dst_key), (int, float)):
                    continue
                src_val = entry.get(src_key)
                if not isinstance(src_val, (int, float)):
                    continue
                aligned_val = float(src_val) - replay_time_offset_s
                if aligned_val >= 0:
                    entry[dst_key] = aligned_val


def fill_missing_official_tyre_life(result):
    def _iter_stints(entries):
        current = []
        prev = None
        for entry in entries:
            tyre = entry.get("tyre", -1)
            if tyre == -1:
                if current:
                    yield current
                    current = []
                prev = entry
                continue
            prev_lap = prev.get("lap") if prev else None
            entry_lap = entry.get("lap")
            new_stint = (
                not current
                or prev is None
                or prev_lap is None
                or entry_lap is None
                or entry_lap != prev_lap + 1
                or entry.get("tyre") != prev.get("tyre")
                or entry.get("is_out_lap")
                or prev.get("is_pit_entry")
            )
            if new_stint:
                if current:
                    yield current
                current = [entry]
            else:
                current.append(entry)
            prev = entry
        if current:
            yield current

    for entries in result.values():
        entries.sort(key=lambda item: (item.get("lap") if item.get("lap") is not None else -1))
        for stint in _iter_stints(entries):
            known = [
                (int(entry["lap"]), int(entry["tyre_life"]))
                for entry in stint
                if entry.get("lap") is not None
                and isinstance(entry.get("tyre_life"), (int, float))
                and int(entry.get("tyre_life", 0)) > 0
            ]
            if known:
                anchor_lap, anchor_life = known[0]
                for entry in stint:
                    if (
                        isinstance(entry.get("tyre_life"), (int, float))
                        and entry.get("tyre_life") is not None
                        and int(entry.get("tyre_life", 0)) > 0
                    ):
                        continue
                    if entry.get("tyre_life") is None or entry.get("lap") is None:
                        continue
                    inferred = anchor_life + (int(entry["lap"]) - anchor_lap)
                    if inferred > 0:
                        entry["tyre_life"] = inferred
                continue

            first_entry = stint[0]
            if first_entry.get("is_out_lap") or first_entry.get("lap") == 1:
                for idx, entry in enumerate(stint, start=1):
                    if entry.get("tyre_life") is None:
                        continue
                    if (
                        not isinstance(entry.get("tyre_life"), (int, float))
                        or int(entry.get("tyre_life", 0)) <= 0
                    ):
                        entry["tyre_life"] = idx


def compute_fallback_lap_times_raw(frames, min_lap_time_s=30.0, max_lap_time_s=7200.0):
    lap_start_t = {}
    current_lap = {}
    result = {}

    for frame in frames:
        t = frame.get("t", 0)
        drivers = frame.get("drivers", {})
        for code, drv in drivers.items():
            lap = drv.get("lap")
            if lap is None:
                continue

            prev_lap = current_lap.get(code)
            if prev_lap is None:
                current_lap[code] = lap
                lap_start_t[code] = t
                result.setdefault(code, [])
                continue

            if lap > prev_lap:
                lap_time = t - lap_start_t.get(code, t)
                tyre = safe_int(drv.get("tyre")) or 0
                tyre_life = safe_int(drv.get("tyre_life"))

                if min_lap_time_s < lap_time < max_lap_time_s and prev_lap >= 2:
                    result.setdefault(code, []).append({
                        "lap": prev_lap,
                        "time_s": float(lap_time),
                        "end_time_s": float(t),
                        "tyre": tyre,
                        "tyre_life": tyre_life,
                        "start_time_s": float(lap_start_t.get(code, t)),
                    })

                current_lap[code] = lap
                lap_start_t[code] = t

    return result


def classify_lap_entries(result, official_data=False):
    """Enrich lap entries with derived pit, out-lap, and pace-outlier metadata."""
    for entries in result.values():
        entries.sort(key=lambda e: e["lap"])
        clean_history = []
        gap_clock_s = 0.0

        for i, entry in enumerate(entries):
            next_entry = entries[i + 1] if i + 1 < len(entries) else None
            entry.setdefault("source", "official" if official_data else "derived")
            entry.setdefault("is_pit_entry", bool(entry.get("is_pit", False)))
            entry.setdefault(
                "is_pit_affected",
                bool(entry.get("is_pit_entry", False) or entry.get("is_pit", False)),
            )
            entry.setdefault("is_out_lap", False)
            entry.setdefault("is_outlier", False)
            entry.setdefault(
                "pit_confidence",
                "official"
                if entry.get("is_pit_entry") and entry.get("source") == "official"
                else "none",
            )

            baseline_pool = clean_history[-5:]
            baseline = None
            if baseline_pool:
                baseline = sorted(baseline_pool)[len(baseline_pool) // 2]
                entry["pace_baseline_s"] = round(float(baseline), 3)

            time_s = entry.get("time_s", -1.0)
            if time_s > 0:
                gap_clock_s += float(time_s)
                entry["gap_clock_s"] = gap_clock_s
            else:
                entry["gap_clock_s"] = None
            if (
                entry.get("source") != "official"
                and not entry.get("is_pit_affected")
                and baseline is not None
                and time_s > 0
                and entry["lap"] > 1
            ):
                tyre = entry.get("tyre", -1)
                tyre_life = entry.get("tyre_life", -1)
                next_tyre = next_entry.get("tyre", -1) if next_entry else -1
                next_tyre_life = next_entry.get("tyre_life", -1) if next_entry else -1

                compound_change = (
                    next_entry is not None
                    and tyre != -1
                    and next_tyre != -1
                    and next_tyre != tyre
                )
                age_reset = (
                    next_entry is not None
                    and tyre_life is not None
                    and next_tyre_life is not None
                    and tyre_life >= 0
                    and next_tyre_life >= 0
                    and next_tyre_life <= 2
                    and next_tyre_life + 1 < tyre_life
                )
                severe_delta = (time_s - baseline) >= max(12.0, baseline * 0.12)
                moderate_delta = (time_s - baseline) >= max(7.0, baseline * 0.08)

                if severe_delta and (compound_change or age_reset):
                    entry["is_pit_affected"] = True
                    entry["pit_confidence"] = "high"
                elif moderate_delta and age_reset:
                    entry["is_pit_affected"] = True
                    entry["pit_confidence"] = "medium"
                elif severe_delta:
                    entry["is_outlier"] = True

            if entry.get("is_pit_entry") and next_entry and next_entry["lap"] == entry["lap"] + 1:
                next_entry["is_out_lap"] = True

            entry["is_pit"] = bool(entry.get("is_pit_affected"))

            if (
                time_s > 0
                and not entry.get("is_pit_affected")
                and not entry.get("is_out_lap")
                and not entry.get("is_outlier")
            ):
                clean_history.append(time_s)

    return result


def compute_lap_times(frames, session=None):
    """Scan the full frame array once to build deterministic lap times per driver."""
    fallback_result = compute_fallback_lap_times_raw(frames)
    classified_fallback = classify_lap_entries(
        fallback_result,
        official_data=False,
    )

    if session is not None and hasattr(session, "laps"):
        try:
            import pandas as pd
            import fastf1._api as ffapi
            import fastf1.utils as ffutils
            from src.lib.tyres import get_tyre_compound_int

            result = {}
            for row in session.laps.to_dict("records"):
                code = row.get("Driver")
                lap_num = row.get("LapNumber")
                lap_time_td = row.get("LapTime")
                tyre_str = row.get("Compound")
                tyre_life = row.get("TyreLife")

                if pd.isna(lap_num):
                    continue

                time_s = lap_time_td.total_seconds() if pd.notna(lap_time_td) else -1.0
                lap_end_td = row.get("Time")
                end_time_s = lap_end_td.total_seconds() if pd.notna(lap_end_td) else None
                line_end_td = row.get("Sector3SessionTime")
                line_end_s = line_end_td.total_seconds() if pd.notna(line_end_td) else end_time_s

                tyre_int = -1
                if pd.notna(tyre_str):
                    tyre_int = get_tyre_compound_int(tyre_str)

                t_life = 0
                if pd.notna(tyre_life):
                    t_life = int(tyre_life)

                is_pit_entry = False
                if "PitInTime" in session.laps.columns and pd.notna(row.get("PitInTime")):
                    is_pit_entry = True
                is_out_lap = False
                if "PitOutTime" in session.laps.columns and pd.notna(row.get("PitOutTime")):
                    is_out_lap = True

                result.setdefault(code, []).append({
                    "lap": int(lap_num),
                    "time_s": float(time_s),
                    "end_time_s": float(end_time_s) if end_time_s is not None else None,
                    "line_time_s": float(line_end_s) if line_end_s is not None else None,
                    "tyre": tyre_int,
                    "tyre_life": t_life,
                    "is_pit_entry": is_pit_entry,
                    "is_pit_affected": is_pit_entry,
                    "is_out_lap": is_out_lap,
                    "fastf1_generated": bool(row.get("FastF1Generated", False)),
                    "is_accurate": bool(row.get("IsAccurate", True)),
                })
            if result:
                fallback_by_code = {
                    code: {entry["lap"]: entry for entry in entries}
                    for code, entries in classified_fallback.items()
                }
                for code, entries in result.items():
                    fallback_entries = fallback_by_code.get(code, {})
                    for entry in entries:
                        fb_entry = fallback_entries.get(entry["lap"])
                        if fb_entry is None:
                            continue
                        if entry.get("time_s", -1.0) <= 0 and fb_entry.get("time_s", -1.0) > 0:
                            entry["time_s"] = fb_entry["time_s"]
                            entry["time_source"] = "frame_backfill"
                            entry["source"] = "derived"
                            if entry.get("end_time_s") is None and fb_entry.get("end_time_s") is not None:
                                entry["end_time_s"] = fb_entry["end_time_s"]
                            if entry.get("line_time_s") is None and fb_entry.get("end_time_s") is not None:
                                entry["line_time_s"] = fb_entry["end_time_s"]
                            if fb_entry.get("end_time_s") is not None:
                                replay_end = float(fb_entry["end_time_s"])
                                entry["replay_end_time_s"] = replay_end
                                entry["replay_line_time_s"] = replay_end
                            if fb_entry.get("start_time_s") is not None:
                                entry["start_time_s"] = fb_entry["start_time_s"]
                        if (fb_entry.get("is_pit_affected") or fb_entry.get("is_pit")) and not entry.get("is_pit_affected"):
                            entry["is_pit_affected"] = True
                            if not entry.get("pit_confidence") or entry.get("pit_confidence") == "none":
                                entry["pit_confidence"] = fb_entry.get("pit_confidence", "medium")
                        if fb_entry.get("is_out_lap"):
                            entry["is_out_lap"] = True
                        if fb_entry.get("is_outlier"):
                            entry["is_outlier"] = True
                        if fb_entry.get("pace_baseline_s") is not None and entry.get("pace_baseline_s") is None:
                            entry["pace_baseline_s"] = fb_entry["pace_baseline_s"]

                fill_missing_official_tyre_life(result)
                replay_time_offset_s = estimate_official_replay_time_offset(
                    result,
                    classified_fallback,
                )
                attach_replay_aligned_lap_times(
                    result,
                    replay_time_offset_s,
                    classified_fallback,
                )
                return classify_lap_entries(result, official_data=True)
        except Exception as e:
            print(f"Error parsing official lap times: {e}")

    return classified_fallback


def compute_status_laps(frames, track_statuses):
    """Map track status periods to leader lap numbers."""
    if not track_statuses or not frames:
        return []

    time_to_lap = []
    for i in range(0, len(frames), 25):
        f = frames[i]
        t = f.get("t", 0)
        lap = f.get("lap", 1)
        time_to_lap.append((t, int(lap)))

    def _lap_at_time(target_t):
        best_lap = 1
        for t, lap in time_to_lap:
            if t <= target_t:
                best_lap = lap
            else:
                break
        return best_lap

    result = []
    for status in track_statuses:
        code = str(status.get("status", ""))
        if code not in ("4", "5", "6", "7"):
            continue
        start_t = status.get("start_time", 0)
        end_t = status.get("end_time")
        start_lap = _lap_at_time(start_t)
        end_lap = _lap_at_time(end_t) if end_t else start_lap
        if (
            result
            and result[-1]["status"] == code
            and result[-1]["end_lap"] >= start_lap - 1
        ):
            result[-1]["end_lap"] = max(result[-1]["end_lap"], end_lap)
        else:
            result.append({
                "status": code,
                "start_lap": start_lap,
                "end_lap": end_lap,
            })
    return result


_format_laptime = format_laptime
_format_delta = format_delta
_moving_average = moving_average
_entry_is_pit_entry = entry_is_pit_entry
_entry_is_pit_affected = entry_is_pit_affected
_entry_is_out_lap = entry_is_out_lap
_entry_is_outlier = entry_is_outlier
_is_clean_timed_entry = is_clean_timed_entry
_entry_has_gap_discontinuity = entry_has_gap_discontinuity
_terminal_status_display_text = terminal_status_display_text
_compute_lap_times = compute_lap_times
_estimate_official_replay_time_offset = estimate_official_replay_time_offset
_attach_replay_aligned_lap_times = attach_replay_aligned_lap_times
_fill_missing_official_tyre_life = fill_missing_official_tyre_life
_compute_fallback_lap_times_raw = compute_fallback_lap_times_raw
_classify_lap_entries = classify_lap_entries
_compute_status_laps = compute_status_laps
