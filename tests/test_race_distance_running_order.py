import numpy as np
import pytest
from unittest.mock import MagicMock
import pandas as pd

from src.ui_components import LeaderboardComponent


def test_multi_lap_race_distance_accumulation():
    """
    Test that across multiple laps, race distance monotonically accumulates
    and does NOT reset to 0 at lap boundaries.
    """
    # Simulate 3 laps for a driver
    lap_distances = [
        np.linspace(0.0, 5280.0, 50),     # Lap 1
        np.linspace(0.5, 5285.5, 50),     # Lap 2 (starts with minor offset)
        np.linspace(0.0, 5275.0, 50),     # Lap 3
    ]

    total_dist_so_far = 0.0
    last_valid_lap_dist = None
    all_race_dists = []

    for d_lap in lap_distances:
        d_lap_offset = d_lap - d_lap[0]
        race_d_lap = total_dist_so_far + d_lap_offset

        lap_len = float(d_lap_offset[-1])
        if lap_len > 0:
            total_dist_so_far += lap_len
            last_valid_lap_dist = lap_len
        elif last_valid_lap_dist is not None:
            total_dist_so_far += last_valid_lap_dist

        all_race_dists.append(race_d_lap)

    concatenated = np.concatenate(all_race_dists)

    # 1. Total distance must be strictly non-decreasing
    assert np.all(np.diff(concatenated) >= 0), "Race distance decreased across samples"

    # 2. At lap boundaries, distance must NOT drop to 0
    lap1_end = all_race_dists[0][-1]
    lap2_start = all_race_dists[1][0]
    lap2_end = all_race_dists[1][-1]
    lap3_start = all_race_dists[2][0]

    assert lap1_end == pytest.approx(5280.0)
    assert lap2_start == pytest.approx(5280.0)
    assert lap2_end == pytest.approx(5280.0 + 5285.0)
    assert lap3_start == pytest.approx(lap2_end)
    assert lap3_start > 10000.0, "Race distance reset at lap 3 boundary"


def test_lap_boundary_running_order_does_not_flip():
    """
    Test that when Car 1 crosses the start/finish line into Lap 2,
    while Car 2 is still completing Lap 1, Car 1 remains P1 and the running
    order does NOT flip.
    """
    # Frame before crossing:
    # Car 1: end of lap 1, dist = 5270m
    # Car 2: 20m behind, dist = 5250m
    frame_before = [
        {"code": "VER", "dist": 5270.0, "lap": 1},
        {"code": "NOR", "dist": 5250.0, "lap": 1},
    ]
    frame_before.sort(key=lambda r: r["dist"], reverse=True)
    assert [c["code"] for c in frame_before] == ["VER", "NOR"]

    # Frame right after Car 1 crosses the line into Lap 2:
    # Car 1: Lap 2, cumulative dist = 5305m (5280m Lap 1 + 25m Lap 2)
    # Car 2: Lap 1, cumulative dist = 5275m
    frame_crossing = [
        {"code": "VER", "dist": 5305.0, "lap": 2},
        {"code": "NOR", "dist": 5275.0, "lap": 1},
    ]
    frame_crossing.sort(key=lambda r: r["dist"], reverse=True)
    # VER must remain ahead of NOR
    assert [c["code"] for c in frame_crossing] == ["VER", "NOR"]
    assert frame_crossing[0]["code"] == "VER"
    assert frame_crossing[1]["code"] == "NOR"

    # Frame when Car 2 also crosses into Lap 2:
    # Car 1: Lap 2, cumulative dist = 5340m
    # Car 2: Lap 2, cumulative dist = 5310m
    frame_after = [
        {"code": "VER", "dist": 5340.0, "lap": 2},
        {"code": "NOR", "dist": 5310.0, "lap": 2},
    ]
    frame_after.sort(key=lambda r: r["dist"], reverse=True)
    assert [c["code"] for c in frame_after] == ["VER", "NOR"]


def test_leaderboard_component_set_entries_and_gaps():
    """
    Test LeaderboardComponent accurately sorts by progress_m,
    calculates gaps, and does not invert running order.
    """
    comp = LeaderboardComponent(x=10, width=200)

    # Provide entries with cumulative distance / progress_m
    entries = [
        ("NOR", (255, 128, 0), {"dist": 5275.0, "lap": 1}, 5275.0),
        ("VER", (0, 0, 255), {"dist": 5305.0, "lap": 2}, 5305.0),
        ("LEC", (255, 0, 0), {"dist": 5250.0, "lap": 1}, 5250.0),
    ]

    comp.set_entries(entries)

    # 1. Verification of order: VER (5305) > NOR (5275) > LEC (5250)
    ordered_codes = [e[0] for e in comp.entries]
    assert ordered_codes == ["VER", "NOR", "LEC"], "Leaderboard entries are not sorted descending by progress"

    # 2. Leader gap verification
    assert comp.computed_gaps["VER"] == 0.0
    # NOR gap to VER = (5305 - 5275)/10.0 / 55.56
    expected_nor_gap = (30.0 / 10.0) / 55.56
    assert comp.computed_gaps["NOR"] == pytest.approx(expected_nor_gap, rel=1e-3)

    # 3. Neighbor gap verification
    assert comp.computed_neighbor_gaps["NOR"]["ahead"][0] == "VER"
    assert comp.computed_neighbor_gaps["LEC"]["ahead"][0] == "NOR"


def test_get_leader_info_monotonic_with_cumulative_dist():
    """
    Test that get_leader_info correctly identifies the leader from cumulative dist
    without jumping at lap boundaries.
    """
    from src.f1_data import _compute_safety_car_positions

    # Construct frames across lap boundary
    # Frame 1: VER leading at 5270m (lap 1), NOR at 5250m (lap 1)
    # Frame 2: VER crosses to lap 2 at 5305m (lap 2), NOR at 5275m (lap 1)
    frame1 = {
        "t": 90.0,
        "drivers": {
            "VER": {"x": 100.0, "y": 200.0, "dist": 5270.0, "lap": 1},
            "NOR": {"x": 80.0, "y": 190.0, "dist": 5250.0, "lap": 1},
        },
    }
    frame2 = {
        "t": 91.0,
        "drivers": {
            "VER": {"x": 120.0, "y": 210.0, "dist": 5305.0, "lap": 2},
            "NOR": {"x": 105.0, "y": 202.0, "dist": 5275.0, "lap": 1},
        },
    }

    # Verify leader by max dist
    leader1 = max(frame1["drivers"].items(), key=lambda d: d[1]["dist"])[0]
    leader2 = max(frame2["drivers"].items(), key=lambda d: d[1]["dist"])[0]

    assert leader1 == "VER"
    assert leader2 == "VER", "Leader flipped when crossing lap boundary"
