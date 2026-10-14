"""Season schedule lookup and persistent two-tier (memory + disk) schedule caching.

Extracted from `src.f1_data` for high cohesion and single-responsibility modularity.
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date
from multiprocessing.dummy import Pool as ThreadPool

try:
    import fastf1
except ImportError:
    fastf1 = None
import pandas as pd

from src.lib.settings import get_settings

_SCHEDULE_MEM_CACHE: dict[int, list[dict]] = {}


def enable_fastf1_cache() -> None:
    """Enable the local FastF1 disk cache configured in SettingsManager."""
    settings = get_settings()
    cache_path = settings.cache_location
    if not os.path.exists(cache_path):
        os.makedirs(cache_path)
    fastf1.Cache.enable_cache(cache_path)


def _schedule_cache_file() -> str:
    settings = get_settings()
    return os.path.join(settings.computed_data_location, "schedule_cache_v1.pkl")


def _load_disk_schedule_cache() -> dict:
    path = _schedule_cache_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_disk_schedule_cache(cache_dict: dict) -> None:
    path = _schedule_cache_file()
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(cache_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def get_race_weekends_by_year(year):
    """Return a list of race weekends for a given year (with memory + disk cache)."""
    yr = int(year)
    use_cache = "--refresh-data" not in sys.argv
    if use_cache and yr in _SCHEDULE_MEM_CACHE:
        return [dict(w) for w in _SCHEDULE_MEM_CACHE[yr]]

    if use_cache and yr < date.today().year:
        disk_cache = _load_disk_schedule_cache()
        if yr in disk_cache and isinstance(disk_cache[yr], list) and disk_cache[yr]:
            _SCHEDULE_MEM_CACHE[yr] = disk_cache[yr]
            return [dict(w) for w in disk_cache[yr]]

    enable_fastf1_cache()
    schedule = fastf1.get_event_schedule(yr)
    if schedule is None or not hasattr(schedule, "iterrows"):
        return []
    weekends = []
    for _, event in schedule.iterrows():
        if event.is_testing():
            continue

        session_dates = {}
        for i in range(1, 6):
            session_name = event.get(f"Session{i}")
            session_date = event.get(f"Session{i}Date")
            if session_name and pd.notna(session_date):
                session_dates[str(session_name)] = session_date.isoformat()

        ev_date = event["EventDate"]
        d_obj = ev_date.date() if hasattr(ev_date, "date") else ev_date
        weekends.append({
            "round_number": event["RoundNumber"],
            "event_name": event["EventName"],
            "date": str(d_obj),
            "year": int(getattr(d_obj, "year", yr)),
            "country": event["Country"],
            "type": event["EventFormat"],
            "session_dates": session_dates,
        })
    if weekends:
        _SCHEDULE_MEM_CACHE[yr] = weekends
        if yr < date.today().year:
            disk_cache = _load_disk_schedule_cache()
            disk_cache[yr] = weekends
            _save_disk_schedule_cache(disk_cache)
    return [dict(w) for w in weekends]


def get_race_weekends_by_place(place):
    """Return a list of past race weekends matching a given event name."""
    enable_fastf1_cache()
    place = place.lower().strip()
    current_year = date.today().year
    years = list(range(2018, current_year + 1))

    def _fetch_year(yr):
        try:
            return get_race_weekends_by_year(yr)
        except Exception:
            return []

    with ThreadPool(processes=min(8, max(1, len(years)))) as pool:
        all_year_weekends = pool.map(_fetch_year, years)

    weekends = []
    for yr, yr_weekends in zip(years, all_year_weekends):
        for w in yr_weekends:
            event_name = str(w.get("event_name", "")).strip().lower()
            if place == event_name:
                entry = dict(w)
                entry.setdefault("year", yr)
                weekends.append(entry)
    return weekends


def get_all_unique_race_names(start_year: int = 2018, end_year=None):
    """Return a sorted list of all unique race event names across [start_year, end_year]."""
    enable_fastf1_cache()
    if end_year is None:
        end_year = date.today().year
    years = list(range(int(start_year), int(end_year) + 1))

    def _fetch_year_names(yr):
        try:
            return [
                str(w.get("event_name", "")).strip()
                for w in get_race_weekends_by_year(yr)
                if w.get("event_name")
            ]
        except Exception:
            return []

    with ThreadPool(processes=min(8, max(1, len(years)))) as pool:
        nested = pool.map(_fetch_year_names, years)

    race_names = {name for sublist in nested for name in sublist if name}
    return sorted(race_names)


def list_rounds(year):
    """Print all rounds for a given year."""
    enable_fastf1_cache()
    print(f"F1 Schedule {year}")
    schedule = fastf1.get_event_schedule(year)
    for _, event in schedule.iterrows():
        print(f"{event['RoundNumber']}: {event['EventName']}")


def list_sprints(year):
    """Print all sprint rounds for a given year."""
    enable_fastf1_cache()
    print(f"F1 Sprint Races {year}")
    schedule = fastf1.get_event_schedule(year)
    sprints = schedule[
        schedule["EventFormat"].astype(str).str.lower().str.contains("sprint", na=False)
    ]
    if sprints.empty:
        print(f"No sprint races found for {year}.")
    else:
        for _, event in sprints.iterrows():
            print(f"{event['RoundNumber']}: {event['EventName']}")
