"""Weather forecast service backed by the free Open-Meteo API (no API key).

Used by the Weather insight window to show a pre-race and in-race forecast
for the circuit. This module has no Qt/GUI dependency so it can be tested
offline: every network call goes through ``_http_get_json`` which tests patch.

Open-Meteo docs: https://open-meteo.com/en/docs
Geocoding docs:  https://open-meteo.com/en/docs/geocoding-api
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)
CURRENT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
)

# Open-Meteo serves at most 16 forecast days; we also request a couple of past
# days so a race that finished recently still has data.
MAX_FORECAST_DAYS = 16
PAST_DAYS = 2

REQUEST_TIMEOUT_S = 8.0
CACHE_TTL_S = 10 * 60  # forecasts only change every ~hour; refresh every 10 min
USER_AGENT = "f1-race-replay (weather insight)"


class WeatherServiceError(Exception):
    """Raised for any network, parsing or lookup failure (message is user-facing)."""


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float
    timezone: str = ""
    country: str = ""


@dataclass(frozen=True)
class HourlyForecast:
    time: datetime  # naive, local time at the circuit
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    rain_probability_pct: Optional[float] = None
    precipitation_mm: Optional[float] = None
    weather_code: Optional[int] = None
    cloud_cover_pct: Optional[float] = None
    wind_kph: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    wind_gust_kph: Optional[float] = None


@dataclass(frozen=True)
class CurrentConditions:
    time: Optional[datetime] = None
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    precipitation_mm: Optional[float] = None
    weather_code: Optional[int] = None
    wind_kph: Optional[float] = None
    wind_direction_deg: Optional[float] = None


@dataclass(frozen=True)
class Forecast:
    location: Location
    hourly: list = field(default_factory=list)  # list[HourlyForecast], ascending
    current: Optional[CurrentConditions] = None
    utc_offset_seconds: int = 0
    fetched_at: float = 0.0


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _http_get_json(url: str, params: dict, timeout: float = REQUEST_TIMEOUT_S) -> Any:
    """GET ``url`` with ``params`` and return decoded JSON. Patched in tests."""
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise WeatherServiceError(f"Weather service returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WeatherServiceError(f"Could not reach weather service: {exc}") from exc
    except ValueError as exc:  # json.JSONDecodeError subclasses ValueError
        raise WeatherServiceError("Weather service returned invalid data") from exc


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return (text or "").strip().casefold()


def geocode(name: str, country: str = "") -> Location:
    """Resolve a place name to coordinates. Prefers a result in ``country``."""
    if not _norm(name):
        raise WeatherServiceError("No location name to look up")

    payload = _http_get_json(
        GEOCODE_URL, {"name": name, "count": 10, "language": "en", "format": "json"}
    )
    results = payload.get("results") if isinstance(payload, dict) else None
    if not results:
        raise WeatherServiceError(f"Location not found: {name}")

    chosen = results[0]
    wanted = _norm(country)
    if wanted:
        for candidate in results:
            if wanted in (_norm(candidate.get("country", "")), _norm(candidate.get("country_code", ""))):
                chosen = candidate
                break

    try:
        return Location(
            name=str(chosen.get("name") or name),
            latitude=float(chosen["latitude"]),
            longitude=float(chosen["longitude"]),
            timezone=str(chosen.get("timezone") or ""),
            country=str(chosen.get("country") or ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherServiceError(f"Unusable location result for {name}") from exc


def resolve_location(candidates: Iterable[str], country: str = "") -> Location:
    """Try each candidate name in order (e.g. city, circuit, event) until one geocodes."""
    last_error: Optional[WeatherServiceError] = None
    seen = set()
    for name in candidates:
        key = _norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            return geocode(name, country)
        except WeatherServiceError as exc:
            last_error = exc
    raise last_error or WeatherServiceError("No location name to look up")


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------

_cache: dict = {}


def clear_cache() -> None:
    _cache.clear()


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number  # NaN -> None


def _int(value: Any) -> Optional[int]:
    number = _num(value)
    return None if number is None else int(number)


def _parse_time(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=None)


def parse_forecast(payload: dict, location: Location, now: Optional[float] = None) -> Forecast:
    """Convert an Open-Meteo forecast response into a :class:`Forecast`."""
    if not isinstance(payload, dict):
        raise WeatherServiceError("Weather service returned invalid data")

    hourly_raw = payload.get("hourly") or {}
    times = hourly_raw.get("time") or []

    def column(name: str) -> list:
        values = hourly_raw.get(name)
        return values if isinstance(values, list) else []

    columns = {name: column(name) for name in HOURLY_FIELDS}

    def at(name: str, index: int) -> Any:
        values = columns[name]
        return values[index] if index < len(values) else None

    hourly = []
    for index, raw_time in enumerate(times):
        stamp = _parse_time(raw_time)
        if stamp is None:
            continue
        hourly.append(
            HourlyForecast(
                time=stamp,
                temperature_c=_num(at("temperature_2m", index)),
                humidity_pct=_num(at("relative_humidity_2m", index)),
                rain_probability_pct=_num(at("precipitation_probability", index)),
                precipitation_mm=_num(at("precipitation", index)),
                weather_code=_int(at("weather_code", index)),
                cloud_cover_pct=_num(at("cloud_cover", index)),
                wind_kph=_num(at("wind_speed_10m", index)),
                wind_direction_deg=_num(at("wind_direction_10m", index)),
                wind_gust_kph=_num(at("wind_gusts_10m", index)),
            )
        )
    hourly.sort(key=lambda point: point.time)

    current_raw = payload.get("current")
    current = None
    if isinstance(current_raw, dict) and current_raw:
        current = CurrentConditions(
            time=_parse_time(current_raw.get("time")),
            temperature_c=_num(current_raw.get("temperature_2m")),
            humidity_pct=_num(current_raw.get("relative_humidity_2m")),
            precipitation_mm=_num(current_raw.get("precipitation")),
            weather_code=_int(current_raw.get("weather_code")),
            wind_kph=_num(current_raw.get("wind_speed_10m")),
            wind_direction_deg=_num(current_raw.get("wind_direction_10m")),
        )

    if not hourly and current is None:
        raise WeatherServiceError("Weather service returned no forecast data")

    return Forecast(
        location=location,
        hourly=hourly,
        current=current,
        utc_offset_seconds=_int(payload.get("utc_offset_seconds")) or 0,
        fetched_at=time.time() if now is None else now,
    )


def fetch_forecast(location: Location, use_cache: bool = True) -> Forecast:
    """Fetch (or return a cached) forecast for ``location``."""
    key = (round(location.latitude, 2), round(location.longitude, 2))
    if use_cache:
        cached = _cache.get(key)
        if cached is not None and time.time() - cached.fetched_at < CACHE_TTL_S:
            return cached

    payload = _http_get_json(
        FORECAST_URL,
        {
            "latitude": f"{location.latitude:.4f}",
            "longitude": f"{location.longitude:.4f}",
            "hourly": ",".join(HOURLY_FIELDS),
            "current": ",".join(CURRENT_FIELDS),
            "timezone": "auto",
            "forecast_days": MAX_FORECAST_DAYS,
            "past_days": PAST_DAYS,
            "wind_speed_unit": "kmh",
        },
    )
    if isinstance(payload, dict) and payload.get("error"):
        raise WeatherServiceError(str(payload.get("reason") or "Weather service error"))

    forecast = parse_forecast(payload, location)
    _cache[key] = forecast
    return forecast


def get_forecast_for_event(candidates: Iterable[str], country: str = "") -> Forecast:
    """Geocode the first resolvable name in ``candidates`` and fetch its forecast."""
    return fetch_forecast(resolve_location(candidates, country))


# ---------------------------------------------------------------------------
# Time window helpers
# ---------------------------------------------------------------------------

def parse_session_start(value: Any) -> Optional[datetime]:
    """Parse an ISO string into an aware UTC datetime (naive input is taken as UTC)."""
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_local_naive(start_utc: datetime, utc_offset_seconds: int) -> datetime:
    """Convert an aware UTC datetime to naive circuit-local time."""
    return (start_utc + timedelta(seconds=utc_offset_seconds)).replace(tzinfo=None)


SESSION_DURATION = timedelta(hours=2.5)  # generous: race + red-flag allowance


def _format_delta(delta: timedelta) -> str:
    total_minutes = int(abs(delta.total_seconds()) // 60)
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def session_timing(
    start_utc: datetime,
    now_utc: Optional[datetime] = None,
    duration: timedelta = SESSION_DURATION,
) -> tuple:
    """Describe where "now" sits relative to a session.

    Returns ``(phase, text)`` where phase is ``"upcoming"``, ``"live"`` or
    ``"finished"``.
    """
    now = now_utc or datetime.now(timezone.utc)
    if now < start_utc:
        return ("upcoming", f"Session starts in {_format_delta(start_utc - now)}")
    if now <= start_utc + duration:
        return ("live", f"Session in progress ({_format_delta(now - start_utc)} in)")
    return ("finished", f"Session ended {_format_delta(now - (start_utc + duration))} ago")


def forecast_covers(start_utc: datetime, now_utc: Optional[datetime] = None) -> bool:
    """True if ``start_utc`` lies inside the range Open-Meteo can forecast."""
    now = now_utc or datetime.now(timezone.utc)
    earliest = now - timedelta(days=PAST_DAYS)
    latest = now + timedelta(days=MAX_FORECAST_DAYS)
    return earliest <= start_utc <= latest


def hourly_window(
    forecast: Forecast,
    start_utc: datetime,
    hours_before: float = 2,
    hours_after: float = 3,
) -> list:
    """Hourly points from ``hours_before`` before to ``hours_after`` after the start.

    Forecast points are stamped at the top of each hour, so the lower bound is
    pushed back one extra hour (exclusive) to keep the hour that contains the
    session start even when it begins part-way through (e.g. 14:30 -> 14:00).
    """
    local_start = to_local_naive(start_utc, forecast.utc_offset_seconds)
    low = local_start - timedelta(hours=hours_before + 1)
    high = local_start + timedelta(hours=hours_after)
    return [point for point in forecast.hourly if low < point.time <= high]


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

_WMO = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Freezing fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Drizzle", "🌦️"),
    55: ("Heavy drizzle", "🌧️"),
    56: ("Freezing drizzle", "🌧️"),
    57: ("Heavy freezing drizzle", "🌧️"),
    61: ("Light rain", "🌦️"),
    63: ("Rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"),
    67: ("Heavy freezing rain", "🌧️"),
    71: ("Light snow", "🌨️"),
    73: ("Snow", "🌨️"),
    75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "❄️"),
    80: ("Light showers", "🌦️"),
    81: ("Showers", "🌧️"),
    82: ("Violent showers", "⛈️"),
    85: ("Light snow showers", "🌨️"),
    86: ("Snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with hail", "⛈️"),
    99: ("Severe thunderstorm with hail", "⛈️"),
}


def describe_weather_code(code: Optional[int]) -> tuple:
    """Return ``(description, emoji)`` for a WMO weather code."""
    if code is None:
        return ("Unknown", "")
    return _WMO.get(int(code), ("Unknown", ""))


_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def compass_direction(degrees: Optional[float]) -> str:
    if degrees is None:
        return ""
    return _COMPASS[int((degrees % 360) / 22.5 + 0.5) % 16]


def rain_risk(points: Iterable[HourlyForecast]) -> str:
    """Classify rain risk for a set of hours: ``Low``, ``Moderate``, ``High`` or ``Unknown``."""
    points = list(points)
    probabilities = [p.rain_probability_pct for p in points if p.rain_probability_pct is not None]
    amounts = [p.precipitation_mm for p in points if p.precipitation_mm is not None]
    if not probabilities and not amounts:
        return "Unknown"
    peak_probability = max(probabilities, default=0.0)
    peak_amount = max(amounts, default=0.0)
    if peak_probability >= 50 or peak_amount >= 0.5:
        return "High"
    if peak_probability >= 20 or peak_amount > 0:
        return "Moderate"
    return "Low"


def summarize(points: Iterable[HourlyForecast]) -> dict:
    """Aggregate a set of hours into headline numbers (``None`` when unavailable)."""
    points = list(points)

    def values(attr: str) -> list:
        return [getattr(p, attr) for p in points if getattr(p, attr) is not None]

    temps = values("temperature_c")
    probabilities = values("rain_probability_pct")
    amounts = values("precipitation_mm")
    winds = values("wind_kph")
    gusts = values("wind_gust_kph")
    return {
        "hours": len(points),
        "temp_min_c": min(temps) if temps else None,
        "temp_max_c": max(temps) if temps else None,
        "max_rain_probability_pct": max(probabilities) if probabilities else None,
        "total_precipitation_mm": round(sum(amounts), 2) if amounts else None,
        "max_wind_kph": max(winds) if winds else None,
        "max_gust_kph": max(gusts) if gusts else None,
        "rain_risk": rain_risk(points),
    }
