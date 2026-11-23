import pandas as pd
import pytest

from src.tyre_degradation_integration import TyreDegradationIntegrator


def _laps():
    """Two drivers, two stints each, lap times creeping up with tyre wear."""
    rows = []
    for driver, base in (("AAA", 78.0), ("BBB", 78.4)):
        for lap in range(1, 31):
            stint = 1 if lap <= 15 else 2
            compound = "MEDIUM" if stint == 1 else "HARD"
            lap_in_stint = lap if stint == 1 else lap - 15
            wear = 0.05 if stint == 1 else 0.02
            rows.append({
                "Driver": driver,
                "LapNumber": float(lap),
                "LapTime": base + wear * lap_in_stint - 0.05 * lap,
                "Compound": compound,
                "Stint": float(stint),
                "PitInTime": 10.0 if lap == 15 else None,
                "PitOutTime": 10.0 if lap == 16 else None,
            })
    laps = pd.DataFrame(rows)
    for column in ("LapTime", "PitInTime", "PitOutTime"):
        laps[column] = pd.to_timedelta(laps[column].astype(float), unit="s")
    return laps


@pytest.fixture
def integrator():
    integ = TyreDegradationIntegrator(laps_df=_laps())
    assert integ.initialize_from_session()
    return integ


def test_outputs_have_the_documented_fields(integrator):
    out = integrator.get_model_outputs("AAA", 10)
    assert out["compound"] == "MEDIUM"
    assert out["laps_on_tyre"] >= 1
    assert 0 <= out["health"] <= 100
    for key in ("wear_s_per_lap", "time_lost_s", "laps_left", "uncertainty_s",
                "next_lap_s", "next_lap_low_s", "next_lap_high_s"):
        assert key in out
    assert out["next_lap_low_s"] < out["next_lap_s"] < out["next_lap_high_s"]


def test_next_lap_builds_on_the_last_clean_lap_of_this_stint(integrator):
    out = integrator.get_model_outputs("AAA", 10)
    laps = _laps()
    last = laps[(laps.Driver == "AAA") & (laps.LapNumber == 9)].LapTime.iloc[0].total_seconds()
    # last lap + one lap of wear - fuel burned: within a few tenths of the last lap
    assert out["next_lap_s"] == pytest.approx(last, abs=0.3)


def test_no_next_lap_until_a_clean_lap_on_new_tyres(integrator):
    # Lap 16 is the out-lap of stint 2: there's no clean lap on these tyres yet.
    out = integrator.get_model_outputs("AAA", 16)
    assert out["compound"] == "HARD"
    assert out["next_lap_s"] is None


def test_outputs_are_cached_per_lap(integrator):
    first = integrator.get_model_outputs("BBB", 12)
    assert integrator.get_model_outputs("BBB", 12) is first


def test_uninitialised_or_unknown_driver_returns_none(integrator):
    assert TyreDegradationIntegrator(laps_df=_laps()).get_model_outputs("AAA", 5) is None
    assert integrator.get_model_outputs("ZZZ", 5) is None
