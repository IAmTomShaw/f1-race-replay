from datetime import timedelta
from unittest.mock import MagicMock

import pandas as pd

from src import f1_data


def test_deleted_laps_are_ignored(mocker):
    mocker.patch.object(f1_data, "enable_cache")
    mocker.patch.object(f1_data, "get_driver_colors", return_value={})
    session = MagicMock()
    session.laps = pd.DataFrame([
        {"Driver": "VER", "LapTime": timedelta(seconds=95.860), "Deleted": True},
        {"Driver": "VER", "LapTime": timedelta(seconds=96.136), "Deleted": False},
        {"Driver": "LEC", "LapTime": timedelta(seconds=96.052), "Deleted": False},
        {"Driver": "NOR", "LapTime": timedelta(seconds=96.297), "Deleted": None},
    ])

    results = f1_data.get_practice_results(session)

    assert [r["code"] for r in results] == ["LEC", "VER", "NOR"]
    assert results[1]["time"] == 96.136
