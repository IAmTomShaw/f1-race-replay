"""Tests that the multiprocessing workers get the FastF1 session once
(via the Pool initializer) rather than inside every task (issue #327)."""
import pickle
from multiprocessing import Pool

import numpy as np
import pandas as pd

from src import f1_data


class _FakeLap:
    LapNumber = 1
    Compound = "SOFT"
    TyreLife = 3

    def get_telemetry(self):
        n = 5
        return pd.DataFrame(
            {
                "SessionTime": pd.to_timedelta(np.arange(n, dtype=float), unit="s"),
                "X": np.arange(n, dtype=float),
                "Y": np.arange(n, dtype=float),
                "Distance": np.arange(n, dtype=float) * 10,
                "RelativeDistance": np.linspace(0, 1, n),
                "Speed": np.full(n, 200.0),
                "nGear": np.full(n, 5),
                "DRS": np.zeros(n),
                "Throttle": np.full(n, 100.0),
                "Brake": np.zeros(n, dtype=bool),
            }
        )


class _FakeLapNumber:
    @staticmethod
    def max():
        return 1


class _FakeLaps:
    LapNumber = _FakeLapNumber()

    def __init__(self, empty=False):
        self.empty = empty

    def pick_drivers(self, driver_no):
        return _FakeLaps(empty=(driver_no == "99"))

    def iterlaps(self):
        yield 0, _FakeLap()


class FakeSession:
    """Picklable stand-in for a loaded FastF1 session."""

    def __init__(self):
        self.laps = _FakeLaps()
        self.payload = np.zeros(10_000)


def test_task_args_do_not_contain_session():
    assert len(pickle.dumps(("44", "HAM"))) < 200


def test_init_worker_session_sets_global(monkeypatch):
    monkeypatch.setattr(f1_data, "_WORKER_SESSION", None)
    session = FakeSession()
    f1_data._init_worker_session(session)
    assert f1_data._WORKER_SESSION is session


def test_process_single_driver_uses_worker_session(monkeypatch):
    monkeypatch.setattr(f1_data, "_WORKER_SESSION", FakeSession())
    result = f1_data._process_single_driver(("44", "HAM"))
    assert result["code"] == "HAM"
    assert result["max_lap"] == 1
    assert len(result["data"]["t"]) == 5


def test_process_single_driver_empty_laps_returns_none(monkeypatch):
    monkeypatch.setattr(f1_data, "_WORKER_SESSION", FakeSession())
    assert f1_data._process_single_driver(("99", "XXX")) is None


def test_pool_with_initializer_end_to_end():
    """Real Pool: session delivered via initargs, tasks carry only ids."""
    session = FakeSession()
    args = [("44", "HAM"), ("1", "VER"), ("99", "XXX")]
    with Pool(
        processes=2,
        initializer=f1_data._init_worker_session,
        initargs=(session,),
    ) as pool:
        results = pool.map(f1_data._process_single_driver, args)

    assert results[0]["code"] == "HAM"
    assert results[1]["code"] == "VER"
    assert results[2] is None
