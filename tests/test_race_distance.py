"""Regression tests for issue #331.

FastF1's ``Lap.get_telemetry()`` returns a ``Distance`` channel that restarts at
zero on every lap. ``_process_single_driver`` is meant to turn that into a
cumulative race distance so drivers can be ranked against each other. These
tests drive it with a fake session (no FastF1, network or cache needed).
"""
import unittest

import numpy as np
import pandas as pd

from src.f1_data import _process_single_driver

LAP_LEN = 5000.0  # metres
LAP_TIME = 90.0  # seconds


def _lap_telemetry(lap_index, t_offset=0.0):
    """Telemetry for one lap, edges included (as FastF1 interpolates them)."""
    t = t_offset + lap_index * LAP_TIME + np.linspace(0.0, LAP_TIME, 91)
    n = len(t)
    return pd.DataFrame(
        {
            "SessionTime": pd.to_timedelta(t, unit="s"),
            "X": np.zeros(n),
            "Y": np.zeros(n),
            "Distance": np.linspace(0.0, LAP_LEN, n),  # restarts every lap
            "RelativeDistance": np.linspace(0.0, 1.0, n),
            "Speed": np.full(n, 200.0),
            "nGear": np.full(n, 6),
            "DRS": np.zeros(n),
            "Throttle": np.full(n, 100.0),
            "Brake": np.zeros(n, dtype=bool),
        }
    )


class _FakeLap:
    def __init__(self, number, telemetry=None, error=None):
        self.LapNumber = float(number)  # FastF1 stores lap numbers as floats
        self.Compound = "SOFT"
        self.TyreLife = 1.0
        self._telemetry = telemetry
        self._error = error

    def get_telemetry(self):
        if self._error is not None:
            raise self._error
        return self._telemetry


class _FakeDriverLaps:
    empty = False

    def __init__(self, laps):
        self._laps = laps
        self.LapNumber = pd.Series([lap.LapNumber for lap in laps])

    def iterlaps(self):
        return iter(enumerate(self._laps))


class _FakeSession:
    def __init__(self, laps_by_driver):
        self.laps = self
        self._laps_by_driver = laps_by_driver

    def pick_drivers(self, driver_no):
        return _FakeDriverLaps(self._laps_by_driver[driver_no])


def _race_distance(laps, code="TST"):
    session = _FakeSession({"1": laps})
    result = _process_single_driver(("1", session, code))
    return result["data"]["t"], result["data"]["dist"]


class RaceDistanceTests(unittest.TestCase):
    def test_distance_accumulates_across_laps(self):
        laps = [_FakeLap(n + 1, _lap_telemetry(n)) for n in range(3)]
        t, dist = _race_distance(laps)

        self.assertTrue(np.all(np.diff(dist) >= -1e-6), "distance must never decrease")
        self.assertAlmostEqual(dist[-1], 3 * LAP_LEN, delta=1.0)
        # Just inside lap 2 the driver must already be past one full lap.
        self.assertAlmostEqual(float(np.interp(LAP_TIME + 1.0, t, dist)),
                               LAP_LEN + LAP_LEN / LAP_TIME, delta=1.0)

    def test_leader_stays_ahead_across_lap_boundary(self):
        # A leads B by 3 s, so A crosses the line while B is still on lap 1.
        a_laps = [_FakeLap(n + 1, _lap_telemetry(n)) for n in range(3)]
        b_laps = [_FakeLap(n + 1, _lap_telemetry(n, t_offset=3.0)) for n in range(3)]
        t_a, d_a = _race_distance(a_laps, "AAA")
        t_b, d_b = _race_distance(b_laps, "BBB")

        # Sample the window around A's line crossing (t=90s) and B's (t=93s),
        # and again around the next crossing.
        for lo, hi in ((80.0, 100.0), (170.0, 190.0)):
            for t in np.arange(lo, hi, 0.5):
                a = float(np.interp(t, t_a, d_a))
                b = float(np.interp(t, t_b, d_b))
                self.assertGreater(a, b, f"leader ranked behind at t={t}s ({a:.0f} vs {b:.0f})")

    def test_lap_without_telemetry_does_not_cost_a_lap(self):
        laps = [
            _FakeLap(1, _lap_telemetry(0)),
            _FakeLap(2, error=KeyError("'Date'")),  # FastF1 position-merge failure
            _FakeLap(3, _lap_telemetry(2)),
        ]
        t, dist = _race_distance(laps)

        # Lap 3 begins at t=180s, after two full laps.
        self.assertAlmostEqual(float(np.interp(LAP_TIME * 2 + 1.0, t, dist)),
                               2 * LAP_LEN + LAP_LEN / LAP_TIME, delta=1.0)
        self.assertTrue(np.all(np.isfinite(dist)))

    def test_missing_first_lap_is_anchored_by_lap_number(self):
        laps = [
            _FakeLap(1, telemetry=_lap_telemetry(0).iloc[0:0]),  # empty frame
            _FakeLap(2, _lap_telemetry(1)),
        ]
        t, dist = _race_distance(laps)

        # First sample belongs to lap 2, so one full lap has already been run.
        self.assertAlmostEqual(dist[0], LAP_LEN, delta=1.0)
        self.assertTrue(np.all(np.isfinite(dist)))


if __name__ == "__main__":
    unittest.main()
