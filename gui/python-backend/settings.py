from pathlib import Path
import fastf1
import json

# Determine cache directory path, same as the root of the project
def _get_cache_dir() -> Path:
    base_dir = Path(__file__).parent.parent.parent
    return base_dir / ".fastf1-cache"

# Enable caching for fastf1
def enable_cache():
    cache_dir = _get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)

# Cache the schedule JSON for a given year
def schedule_cache(year, schedule_json):
    cache_dir = _get_cache_dir() / str(year)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / "schedule.json", "w", encoding="utf-8") as f:
        json.dump(schedule_json, f, indent=2, default=str)