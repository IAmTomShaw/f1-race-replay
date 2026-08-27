"""
Helpers for per-lap sector time analysis.

These functions operate on the lap entry dictionaries broadcast by the
replay server (see ``F1RaceReplayWindow._compute_lap_times``), where each
entry may carry ``sector1_s`` / ``sector2_s`` / ``sector3_s`` values in
seconds. Entries without sector data (frame-derived fallback laps, DNF
marker rows) are tolerated everywhere.
"""

SECTOR_KEYS = ("sector1_s", "sector2_s", "sector3_s")

# Classification statuses, mirroring official F1 timing screen colours:
# purple = fastest of the session, green = personal best, no colour otherwise.
STATUS_SESSION_BEST = "session_best"
STATUS_PERSONAL_BEST = "personal_best"
STATUS_NONE = "none"


def _valid_time(value):
    """Return the value as a float if it is a usable sector time, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def best_sectors(entries):
    """
    Return the best time for each sector across a list of lap entries.

    Returns {"sector1_s": float|None, "sector2_s": float|None, "sector3_s": float|None}.
    """
    result = {}
    for key in SECTOR_KEYS:
        times = [t for t in (_valid_time(e.get(key)) for e in entries) if t is not None]
        result[key] = min(times) if times else None
    return result


def theoretical_best_s(entries):
    """
    Sum of a driver's best individual sector times ("ideal lap").

    Returns None unless a valid time exists for all three sectors.
    """
    bests = best_sectors(entries)
    if any(bests[key] is None for key in SECTOR_KEYS):
        return None
    return sum(bests[key] for key in SECTOR_KEYS)


def classify_sector_statuses(entries_by_code):
    """
    Classify every sector time as session best, personal best, or neither.

    Args:
        entries_by_code: {driver_code: [lap entry dict, ...]} — typically the
            subset of lap entries currently visible in the replay, so that the
            colouring reflects the state of the session "so far".

    Returns:
        {(driver_code, lap): {"sector1_s": status, "sector2_s": status,
        "sector3_s": status}} where status is one of STATUS_SESSION_BEST,
        STATUS_PERSONAL_BEST, STATUS_NONE.
    """
    all_entries = [e for entries in entries_by_code.values() for e in entries]
    session_best = best_sectors(all_entries)

    result = {}
    for code, entries in entries_by_code.items():
        personal_best = best_sectors(entries)
        for entry in entries:
            lap = entry.get("lap")
            if lap is None:
                continue
            statuses = {}
            for key in SECTOR_KEYS:
                value = _valid_time(entry.get(key))
                if value is None:
                    statuses[key] = STATUS_NONE
                elif session_best[key] is not None and value <= session_best[key]:
                    statuses[key] = STATUS_SESSION_BEST
                elif personal_best[key] is not None and value <= personal_best[key]:
                    statuses[key] = STATUS_PERSONAL_BEST
                else:
                    statuses[key] = STATUS_NONE
            result[(code, int(lap))] = statuses
    return result


def session_best_holders(entries_by_code):
    """
    Return, for each sector, the best time and the driver(s) who set it.

    Returns {"sector1_s": (time|None, [codes]), ...}. The code list is empty
    when no valid time exists for that sector.
    """
    all_entries = [e for entries in entries_by_code.values() for e in entries]
    session_best = best_sectors(all_entries)

    result = {}
    for key in SECTOR_KEYS:
        best = session_best[key]
        holders = []
        if best is not None:
            for code, entries in entries_by_code.items():
                if any(_valid_time(e.get(key)) == best for e in entries):
                    holders.append(code)
        result[key] = (best, sorted(holders))
    return result
