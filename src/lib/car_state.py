"""
Helpers for the Car Detail insight.

They turn raw telemetry-stream values into the numbers the panel shows, and
make the source of every number explicit. Each field carries one of three
provenance tags:

  LIVE - recorded timing / telemetry from the session, replayed as it happened
  EST  - calculated from simple, stated assumptions (not measured)
  AI   - output of a fitted model, shown with its uncertainty

A model output is never presented as if it were telemetry.
"""

from typing import Iterable, Optional

LIVE = "LIVE"
EST = "EST"
AI = "AI"

TAG_HELP = {
    LIVE: "Recorded timing and telemetry from the session, replayed as it happened.",
    EST: "Estimated from simple assumptions. Not measured.",
    AI: "Prediction from the Bayesian tyre model, fitted on this session's laps.",
}

COMPOUND_NAMES = {0: "SOFT", 1: "MEDIUM", 2: "HARD", 3: "INTERMEDIATE", 4: "WET"}

# DRS values in FastF1 car data: 8 = eligible (within one second in a zone),
# 10 / 12 / 14 = flap open. Anything else is closed.
DRS_OPEN_VALUES = (10, 12, 14)
DRS_ELIGIBLE_VALUE = 8

# Fuel: cars may start with at most 110 kg (FIA Technical Regulations) and
# finish with a small reserve. Real fuel loads are not published.
FIA_MAX_FUEL_KG = 110.0
FUEL_RESERVE_KG = 1.0


def drs_state(value) -> str:
    """'OPEN', 'ELIGIBLE' or 'OFF' for a FastF1 DRS value."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "OFF"
    if v in DRS_OPEN_VALUES:
        return "OPEN"
    if v == DRS_ELIGIBLE_VALUE:
        return "ELIGIBLE"
    return "OFF"


def compound_name(tyre) -> str:
    """Compound name for the stream's tyre code (e.g. 3.0 -> 'INTERMEDIATE')."""
    try:
        return COMPOUND_NAMES.get(int(round(float(tyre))), "UNKNOWN")
    except (TypeError, ValueError):
        return "UNKNOWN"


def brake_fraction(value) -> float:
    """Brake input as 0..1 (the stream sends 0/1, some sources 0..100)."""
    try:
        v = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if v > 1.0:
        v /= 100.0
    return max(0.0, min(1.0, v))


def estimate_fuel_kg(lap, rel_dist, total_laps,
                     start_kg: float = FIA_MAX_FUEL_KG,
                     reserve_kg: float = FUEL_RESERVE_KG) -> Optional[float]:
    """
    Estimated fuel on board (EST).

    Assumes a full ``start_kg`` load burned evenly so that ``reserve_kg`` is
    left at the flag. Safety-car laps burn less, so this runs slightly low
    in races with long caution periods.
    """
    try:
        lap = int(lap)
        total = int(total_laps)
    except (TypeError, ValueError):
        return None
    if total <= 0 or lap <= 0:
        return None
    try:
        frac = float(rel_dist or 0.0)
    except (TypeError, ValueError):
        frac = 0.0
    frac = min(max(frac, 0.0), 1.0)
    progress = min(max((lap - 1) + frac, 0.0), float(total))
    burn_per_lap = (start_kg - reserve_kg) / total
    return start_kg - burn_per_lap * progress


def average_speed_mps(lap_length_m, lap_time_s) -> Optional[float]:
    try:
        length = float(lap_length_m)
        t = float(lap_time_s)
    except (TypeError, ValueError):
        return None
    if length <= 0 or t <= 0:
        return None
    return length / t


def estimate_gap_s(gap_m, avg_speed_mps) -> Optional[float]:
    """
    Turn a distance gap into seconds (EST) using the lap's average speed.

    Average speed is used instead of the current speed so the gap doesn't jump
    around through slow corners.
    """
    try:
        gap = float(gap_m)
        speed = float(avg_speed_mps)
    except (TypeError, ValueError):
        return None
    if speed <= 0 or gap < 0:
        return None
    return gap / speed


def last_completed_lap(entries: Optional[Iterable[dict]], current_lap) -> Optional[dict]:
    """Most recent lap-time entry before ``current_lap`` that has a valid time."""
    if not entries:
        return None
    try:
        current = int(current_lap)
    except (TypeError, ValueError):
        return None
    best = None
    for entry in entries:
        try:
            lap = int(entry.get("lap"))
            t = float(entry.get("time_s"))
        except (TypeError, ValueError, AttributeError):
            continue
        if lap < current and t > 0 and (best is None or lap > int(best["lap"])):
            best = entry
    return best


def format_lap_time(seconds) -> str:
    """75.123 -> '1:15.123'."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "-"
    if s <= 0:
        return "-"
    minutes = int(s // 60)
    return f"{minutes}:{s - 60 * minutes:06.3f}"


def format_laps_left(laps_left, laps_remaining_in_race) -> str:
    """'≈ 12 laps', or 'Lasts to the finish' when wear isn't the limit."""
    try:
        left = float(laps_left)
    except (TypeError, ValueError):
        return "-"
    try:
        remaining = float(laps_remaining_in_race)
    except (TypeError, ValueError):
        remaining = None
    if remaining is not None and left >= remaining:
        return "Lasts to the finish"
    if left < 1:
        return "Worn now"
    return f"≈ {int(round(left))} laps"
