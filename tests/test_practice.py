"""
Unit tests for Practice Session telemetry extraction and stint analysis.
"""

from unittest.mock import MagicMock
import pytest
import pandas as pd

pytest.importorskip("fastf1")
from src.f1_data import get_practice_telemetry


def test_get_practice_telemetry_structure():
    """Test get_practice_telemetry with mock session object."""
    mock_session = MagicMock()
    mock_session.drivers = ['44', '1']

    # Mock driver laps dataframe
    df_ham = pd.DataFrame({
        'Driver': ['HAM', 'HAM', 'HAM', 'HAM', 'HAM'],
        'LapNumber': [1, 2, 3, 4, 5],
        'LapTime': [pd.Timedelta(seconds=80), pd.Timedelta(seconds=81), pd.Timedelta(seconds=80.5), pd.Timedelta(seconds=82), pd.Timedelta(seconds=81.5)],
        'Compound': ['SOFT', 'SOFT', 'SOFT', 'MEDIUM', 'MEDIUM'],
        'Stint': [1, 1, 1, 2, 2],
        'Sector1Time': [pd.Timedelta(seconds=25)] * 5,
        'Sector2Time': [pd.Timedelta(seconds=30)] * 5,
        'Sector3Time': [pd.Timedelta(seconds=25)] * 5,
    })

    def pick_drivers_side_effect(driver_no):
        mock_laps = MagicMock()
        mock_laps.empty = False
        mock_laps.columns = df_ham.columns
        mock_laps.iloc = [df_ham.iloc[0]]

        mock_fastest = MagicMock()
        mock_fastest.__getitem__ = lambda self, k: df_ham.iloc[0][k]
        mock_fastest.get = lambda k: df_ham.iloc[0][k]
        mock_laps.pick_fastest.return_value = mock_fastest

        # Mock groupby Stint
        group_stint1 = MagicMock()
        group_stint1.columns = df_ham.columns
        group_stint1.iloc = [df_ham.iloc[0]]
        group_stint1.__len__ = lambda self: 3
        quicklaps1 = MagicMock()
        quicklaps1.empty = False
        quicklaps1['LapTime'] = pd.Series([pd.Timedelta(seconds=80), pd.Timedelta(seconds=81)])
        group_stint1.pick_quicklaps.return_value = quicklaps1

        mock_laps.groupby.return_value = [(1, group_stint1)]
        return mock_laps

    mock_session.laps.pick_drivers.side_effect = pick_drivers_side_effect

    res = get_practice_telemetry(mock_session, session_type="FP1")
    assert res is not None
    assert res['session_type'] == "FP1"
    assert 'best_laps' in res
    assert 'driver_stints' in res
    assert 'HAM' in res['best_laps']
    assert res['best_laps']['HAM']['fastest_lap_time'] == 80.0
