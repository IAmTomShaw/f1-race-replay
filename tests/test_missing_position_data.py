"""Laps where FastF1 has car data but no (or partial) position data (#303)."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src import f1_data


class _CarData(pd.DataFrame):
    """Stands in for fastf1 Telemetry; Distance/RelativeDistance are precomputed."""

    @property
    def _constructor(self):
        return _CarData

    def add_distance(self):
        return self

    def add_relative_distance(self):
        return self

    def slice_by_lap(self, lap, interpolate_edges=False):
        return self


def _pos(times_s):
    return pd.DataFrame({"SessionTime": pd.to_timedelta(times_s, unit="s")})


def _car(start_s, end_s, n=11):
    rel = np.linspace(0.0, 1.0, n)
    return _CarData({
        "SessionTime": pd.to_timedelta(np.linspace(start_s, end_s, n), unit="s"),
        "Distance": rel * 1000.0,
        "RelativeDistance": rel,
        "Speed": np.full(n, 200.0),
        "nGear": np.full(n, 7),
        "DRS": np.zeros(n),
        "Throttle": np.full(n, 100.0),
        "Brake": np.zeros(n, dtype=bool),
    })


def _lap(number, start_s, end_s, pos_times):
    return SimpleNamespace(
        LapNumber=float(number),
        LapStartTime=pd.Timedelta(start_s, unit="s"),
        Time=pd.Timedelta(end_s, unit="s"),
        Compound="SOFT",
        TyreLife=float(number),
        get_pos_data=lambda **kwargs: _pos(pos_times),
        get_car_data=lambda **kwargs: _car(start_s, end_s),
    )


# Reference lap: a 1000 m square track, X/Y as a function of RelativeDistance.
REFERENCE = pd.DataFrame({
    "RelativeDistance": [0.0, 0.25, 0.5, 0.75, 1.0],
    "X": [0.0, 250.0, 250.0, 0.0, 0.0],
    "Y": [0.0, 0.0, 250.0, 250.0, 0.0],
})


class TestHasPositionData:
    def test_full_coverage(self):
        assert f1_data._has_position_data(_lap(1, 100, 180, np.arange(100.2, 180, 0.25)))

    def test_empty_position_data(self):
        assert not f1_data._has_position_data(_lap(6, 100, 180, []))

    def test_feed_resumes_late_in_lap(self):
        # 2026 Monaco lap 44: position data only for the last few seconds of the lap
        assert not f1_data._has_position_data(_lap(44, 100, 180, np.arange(175.5, 180, 0.25)))

    def test_dropout_mid_lap(self):
        times = np.concatenate((np.arange(100, 130, 0.25), np.arange(150, 180, 0.25)))
        assert not f1_data._has_position_data(_lap(3, 100, 180, times))

    def test_unknown_lap_times_check_only_internal_gaps(self):
        lap = _lap(1, 100, 180, np.arange(120, 140, 0.25))
        lap.LapStartTime = pd.NaT
        lap.Time = pd.NaT
        assert f1_data._has_position_data(lap)


class TestTelemetryWithoutPosition:
    def test_places_car_on_reference_by_relative_distance(self):
        tel = f1_data._telemetry_without_position(_lap(6, 100, 180, []), REFERENCE)
        rd = tel["RelativeDistance"].to_numpy()
        np.testing.assert_allclose(tel["X"], np.interp(rd, REFERENCE["RelativeDistance"], REFERENCE["X"]))
        np.testing.assert_allclose(tel["Y"], np.interp(rd, REFERENCE["RelativeDistance"], REFERENCE["Y"]))
        # car channels are kept
        assert (tel["Speed"] == 200.0).all()

    def test_ignores_nan_in_reference(self):
        ref = REFERENCE.copy()
        ref.loc[2, "X"] = np.nan
        tel = f1_data._telemetry_without_position(_lap(6, 100, 180, []), ref)
        assert np.isfinite(tel["X"]).all()

    def test_no_car_data_returns_none(self):
        lap = _lap(6, 100, 180, [])
        lap.get_car_data = lambda **kwargs: _CarData()
        assert f1_data._telemetry_without_position(lap, REFERENCE) is None


class _Laps:
    def __init__(self, laps):
        self._laps = laps
        self.empty = not laps
        self.LapNumber = pd.Series([lap.LapNumber for lap in laps])

    def iterlaps(self):
        return enumerate(self._laps)


def _session(laps):
    return SimpleNamespace(laps=SimpleNamespace(pick_drivers=lambda driver_no: _Laps(laps)))


class TestProcessSingleDriver:
    def test_lap_without_position_data_is_kept(self, mocker):
        # lap 1 has position data, laps 2-3 do not (the feed stopped)
        laps = [
            _lap(1, 100, 180, np.arange(100.1, 180, 0.25)),
            _lap(2, 180, 260, []),
            _lap(3, 260, 340, []),
        ]
        laps[0].get_telemetry = lambda: _car(100, 180).assign(X=1.0, Y=2.0)
        reference = mocker.patch.object(f1_data, "_reference_lap_telemetry", return_value=REFERENCE)

        result = f1_data._process_single_driver(("12", _session(laps), "ANT"))

        assert set(np.unique(result["data"]["lap"])) == {1.0, 2.0, 3.0}
        assert result["t_max"] == pytest.approx(340.0)
        reference.assert_called_once()  # loaded once, only when first needed

    def test_no_reference_lap_skips_laps_without_position_data(self, mocker):
        laps = [_lap(1, 100, 180, np.arange(100.1, 180, 0.25)), _lap(2, 180, 260, [])]
        laps[0].get_telemetry = lambda: _car(100, 180).assign(X=1.0, Y=2.0)
        mocker.patch.object(f1_data, "_reference_lap_telemetry", return_value=None)

        result = f1_data._process_single_driver(("12", _session(laps), "ANT"))

        assert set(np.unique(result["data"]["lap"])) == {1.0}

    def test_reference_not_loaded_when_all_laps_have_position_data(self, mocker):
        laps = [_lap(1, 100, 180, np.arange(100.1, 180, 0.25))]
        laps[0].get_telemetry = lambda: _car(100, 180).assign(X=1.0, Y=2.0)
        reference = mocker.patch.object(f1_data, "_reference_lap_telemetry")

        f1_data._process_single_driver(("12", _session(laps), "ANT"))

        reference.assert_not_called()
