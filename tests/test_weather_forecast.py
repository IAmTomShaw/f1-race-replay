"""Offline tests for the Open-Meteo weather service (no network access)."""
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from src.services import weather_forecast as wf

LOC = wf.Location("Monza", 45.62, 9.28, "Europe/Rome", "Italy")
UTC = timezone.utc


@pytest.fixture(autouse=True)
def _clean_cache():
    wf.clear_cache()
    yield
    wf.clear_cache()


def _payload(hours=6, start="2026-09-06T10:00", **overrides):
    base = datetime.fromisoformat(start)
    payload = {
        "utc_offset_seconds": 7200,
        "hourly": {
            "time": [(base + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(hours)],
            "temperature_2m": [20 + i for i in range(hours)],
            "relative_humidity_2m": [50] * hours,
            "precipitation_probability": [0, 10, 30, 60, 5, 0][:hours],
            "precipitation": [0, 0, 0.1, 1.2, 0, 0][:hours],
            "weather_code": [0, 1, 3, 63, 2, 0][:hours],
            "cloud_cover": [0] * hours,
            "wind_speed_10m": [10.0] * hours,
            "wind_direction_10m": [90.0] * hours,
            "wind_gusts_10m": [20.0] * hours,
        },
        "current": {"time": "2026-09-06T10:15", "temperature_2m": 21.5, "weather_code": 1,
                    "wind_speed_10m": 8.0, "wind_direction_10m": 180},
    }
    payload.update(overrides)
    return payload


# -- geocoding -------------------------------------------------------------

def test_geocode_prefers_matching_country():
    results = {"results": [
        {"name": "Monza", "latitude": 1.0, "longitude": 2.0, "country": "Other", "country_code": "XX"},
        {"name": "Monza", "latitude": 45.58, "longitude": 9.27, "country": "Italy", "country_code": "IT",
         "timezone": "Europe/Rome"},
    ]}
    with mock.patch.object(wf, "_http_get_json", return_value=results):
        loc = wf.geocode("Monza", "Italy")
    assert (loc.latitude, loc.longitude, loc.country) == (45.58, 9.27, "Italy")


def test_geocode_falls_back_to_first_result():
    results = {"results": [{"name": "A", "latitude": 1, "longitude": 2}]}
    with mock.patch.object(wf, "_http_get_json", return_value=results):
        assert wf.geocode("A", "Nowhere").name == "A"


@pytest.mark.parametrize("payload", [{}, {"results": []}, []])
def test_geocode_not_found(payload):
    with mock.patch.object(wf, "_http_get_json", return_value=payload):
        with pytest.raises(wf.WeatherServiceError):
            wf.geocode("Atlantis")


def test_geocode_empty_name_makes_no_request():
    with mock.patch.object(wf, "_http_get_json") as http:
        with pytest.raises(wf.WeatherServiceError):
            wf.geocode("  ")
    http.assert_not_called()


def test_resolve_location_tries_candidates_in_order_and_skips_blanks():
    calls = []

    def fake(url, params, timeout=0):
        calls.append(params["name"])
        if params["name"] == "Monza":
            return {"results": [{"name": "Monza", "latitude": 1, "longitude": 2}]}
        return {}

    with mock.patch.object(wf, "_http_get_json", side_effect=fake):
        loc = wf.resolve_location(["", "Autodromo", "autodromo", "Monza"], "Italy")
    assert loc.name == "Monza"
    assert calls == ["Autodromo", "Monza"]


def test_resolve_location_raises_when_nothing_resolves():
    with mock.patch.object(wf, "_http_get_json", return_value={}):
        with pytest.raises(wf.WeatherServiceError):
            wf.resolve_location(["x", "y"])
    with pytest.raises(wf.WeatherServiceError):
        wf.resolve_location(["", None])


# -- parsing ----------------------------------------------------------------

def test_parse_forecast_basic():
    fc = wf.parse_forecast(_payload(), LOC, now=100.0)
    assert len(fc.hourly) == 6
    assert fc.hourly[0].time == datetime(2026, 9, 6, 10)
    assert fc.hourly[3].weather_code == 63
    assert fc.utc_offset_seconds == 7200
    assert fc.current.temperature_c == 21.5
    assert fc.fetched_at == 100.0


def test_parse_forecast_tolerates_missing_and_null_columns():
    payload = _payload(hours=3)
    del payload["hourly"]["wind_gusts_10m"]
    payload["hourly"]["temperature_2m"] = [None, "bad", 12]
    payload["hourly"]["precipitation_probability"] = [None]
    fc = wf.parse_forecast(payload, LOC)
    assert [p.temperature_c for p in fc.hourly] == [None, None, 12.0]
    assert all(p.wind_gust_kph is None for p in fc.hourly)
    assert fc.hourly[2].rain_probability_pct is None


def test_parse_forecast_skips_bad_timestamps_and_sorts():
    payload = {"hourly": {"time": ["2026-09-06T11:00", "garbage", "2026-09-06T10:00"],
                          "temperature_2m": [2, 3, 1]}}
    fc = wf.parse_forecast(payload, LOC)
    assert [p.temperature_c for p in fc.hourly] == [1.0, 2.0]


def test_parse_forecast_current_only_is_ok():
    fc = wf.parse_forecast({"current": {"temperature_2m": 5}}, LOC)
    assert fc.hourly == [] and fc.current.temperature_c == 5.0


@pytest.mark.parametrize("payload", [{}, {"hourly": {}}, None, "nope"])
def test_parse_forecast_without_data_raises(payload):
    with pytest.raises(wf.WeatherServiceError):
        wf.parse_forecast(payload, LOC)


# -- fetch / cache -----------------------------------------------------------

def test_fetch_forecast_requests_expected_params_and_caches():
    with mock.patch.object(wf, "_http_get_json", return_value=_payload()) as http:
        first = wf.fetch_forecast(LOC)
        second = wf.fetch_forecast(LOC)
    assert first is second
    assert http.call_count == 1
    url, params = http.call_args[0][:2]
    assert url == wf.FORECAST_URL
    assert params["timezone"] == "auto"
    assert params["wind_speed_unit"] == "kmh"
    assert params["hourly"] == ",".join(wf.HOURLY_FIELDS)
    assert params["forecast_days"] == wf.MAX_FORECAST_DAYS


def test_fetch_forecast_bypass_and_expiry():
    with mock.patch.object(wf, "_http_get_json", return_value=_payload()) as http:
        wf.fetch_forecast(LOC)
        wf.fetch_forecast(LOC, use_cache=False)
        assert http.call_count == 2
        cached = wf._cache[(round(LOC.latitude, 2), round(LOC.longitude, 2))]
        wf._cache[(round(LOC.latitude, 2), round(LOC.longitude, 2))] = wf.Forecast(
            LOC, cached.hourly, cached.current, 0, fetched_at=0.0)
        wf.fetch_forecast(LOC)
        assert http.call_count == 3


def test_fetch_forecast_api_error_and_no_caching_of_failures():
    err = {"error": True, "reason": "Latitude must be in range"}
    with mock.patch.object(wf, "_http_get_json", return_value=err):
        with pytest.raises(wf.WeatherServiceError, match="Latitude"):
            wf.fetch_forecast(LOC)
    assert wf._cache == {}


def test_http_errors_become_service_errors():
    import urllib.error
    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        with pytest.raises(wf.WeatherServiceError):
            wf._http_get_json("https://example.invalid", {})
    with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
        with pytest.raises(wf.WeatherServiceError):
            wf._http_get_json("https://example.invalid", {})


def test_get_forecast_for_event_end_to_end():
    def fake(url, params, timeout=0):
        if url == wf.GEOCODE_URL:
            return {"results": [{"name": "Monza", "latitude": 45.6, "longitude": 9.3, "country": "Italy"}]}
        return _payload()

    with mock.patch.object(wf, "_http_get_json", side_effect=fake):
        fc = wf.get_forecast_for_event(["Monza"], "Italy")
    assert fc.location.name == "Monza" and fc.hourly


# -- time helpers ------------------------------------------------------------

def test_parse_session_start():
    assert wf.parse_session_start("2026-09-06T13:00:00") == datetime(2026, 9, 6, 13, tzinfo=UTC)
    assert wf.parse_session_start("2026-09-06T15:00:00+02:00") == datetime(2026, 9, 6, 13, tzinfo=UTC)
    assert wf.parse_session_start(None) is None
    assert wf.parse_session_start("x") is None


def test_hourly_window_includes_session_hour_when_starting_mid_hour():
    fc = wf.parse_forecast(_payload(hours=6, start="2026-09-06T10:00"), LOC)
    # 12:30 local = 10:30 UTC (offset +2h)
    start = datetime(2026, 9, 6, 10, 30, tzinfo=UTC)
    times = [p.time.hour for p in wf.hourly_window(fc, start, 1, 1)]
    assert times == [11, 12, 13]


def test_session_timing_phases():
    start = datetime(2026, 9, 6, 13, tzinfo=UTC)
    assert wf.session_timing(start, start - timedelta(hours=26)) == ("upcoming", "Session starts in 1d 2h")
    assert wf.session_timing(start, start - timedelta(minutes=45))[1] == "Session starts in 45m"
    phase, text = wf.session_timing(start, start + timedelta(hours=1, minutes=5))
    assert phase == "live" and "1h 05m" in text
    assert wf.session_timing(start, start + timedelta(hours=5))[0] == "finished"


def test_forecast_covers():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    assert wf.forecast_covers(now + timedelta(days=15), now)
    assert not wf.forecast_covers(now + timedelta(days=17), now)
    assert wf.forecast_covers(now - timedelta(days=1), now)
    assert not wf.forecast_covers(now - timedelta(days=3), now)


# -- presentation ------------------------------------------------------------

def test_describe_weather_code_and_compass():
    assert wf.describe_weather_code(63)[0] == "Rain"
    assert wf.describe_weather_code(None)[0] == "Unknown"
    assert wf.describe_weather_code(1234)[0] == "Unknown"
    assert wf.compass_direction(0) == "N"
    assert wf.compass_direction(359) == "N"
    assert wf.compass_direction(90) == "E"
    assert wf.compass_direction(None) == ""


def _pt(prob=None, mm=None, **kw):
    return wf.HourlyForecast(time=datetime(2026, 1, 1), rain_probability_pct=prob, precipitation_mm=mm, **kw)


@pytest.mark.parametrize("points,expected", [
    ([], "Unknown"),
    ([_pt()], "Unknown"),
    ([_pt(0, 0)], "Low"),
    ([_pt(19, 0)], "Low"),
    ([_pt(20, 0)], "Moderate"),
    ([_pt(0, 0.1)], "Moderate"),
    ([_pt(50, 0)], "High"),
    ([_pt(0, 0.5)], "High"),
    ([_pt(None, 2.0)], "High"),
])
def test_rain_risk(points, expected):
    assert wf.rain_risk(points) == expected


def test_summarize():
    fc = wf.parse_forecast(_payload(), LOC)
    s = wf.summarize(fc.hourly)
    assert s["hours"] == 6
    assert (s["temp_min_c"], s["temp_max_c"]) == (20.0, 25.0)
    assert s["max_rain_probability_pct"] == 60.0
    assert s["total_precipitation_mm"] == pytest.approx(1.3)
    assert s["rain_risk"] == "High"
    empty = wf.summarize([])
    assert empty["hours"] == 0 and empty["temp_min_c"] is None and empty["rain_risk"] == "Unknown"
