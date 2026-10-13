import math

import numpy as np
import pandas as pd
import pytest

from src.eval.metrics import (
    exact_match_rate,
    kendall_tau_b,
    mean_abs_error,
    mean_kendall,
    per_lap_kendall,
)


def make_eval(rows):
    """rows: (driver, lap, official_pos, computed_pos, segment, excluded_reason)."""
    return pd.DataFrame(
        rows,
        columns=["driver", "lap", "official_pos", "computed_pos", "segment", "excluded_reason"],
    ).astype({"official_pos": float, "computed_pos": float})


@pytest.fixture
def small_eval():
    return make_eval(
        [
            ("VER", 1, 1, 1, "lap1", None),
            ("HAM", 1, 2, 3, "lap1", None),
            ("LEC", 1, 3, 2, "lap1", None),
            ("NOR", 1, 4, 4, "lap1", None),
            ("SAR", 1, 5, 20, "lap1", "official_pos_nan"),  # excluded: must be ignored
            ("BOT", 1, 6, np.nan, "lap1", None),  # no replay value: ignored
        ]
    )


# ---------- exact match and MAE ----------

def test_exact_match_rate_hand_computed(small_eval):
    # 2 of the 4 scored rows match.
    assert exact_match_rate(small_eval) == pytest.approx(0.5)


def test_mean_abs_error_hand_computed(small_eval):
    # errors 0, 1, 1, 0 -> 0.5
    assert mean_abs_error(small_eval) == pytest.approx(0.5)


def test_metrics_are_nan_without_scored_rows():
    df = make_eval([("VER", 1, 1, 1, "lap1", "no_crossing")])
    assert math.isnan(exact_match_rate(df))
    assert math.isnan(mean_abs_error(df))


# ---------- Kendall tau-b ----------

def test_kendall_identical_order_is_one():
    assert kendall_tau_b([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)


def test_kendall_reversed_order_is_minus_one():
    assert kendall_tau_b([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)


def test_kendall_one_swap_hand_computed():
    # Pairs: (A,B) discordant, (A,C) concordant, (B,C) concordant -> (2 - 1) / 3
    assert kendall_tau_b([1, 2, 3], [2, 1, 3]) == pytest.approx(1 / 3)


def test_kendall_with_ties_hand_computed():
    # y has one tied pair (2, 2). Concordant = 5, discordant = 0.
    # Pairs not tied in x = 6, not tied in y = 5 -> 5 / sqrt(30)
    assert kendall_tau_b([1, 2, 3, 4], [1, 2, 2, 3]) == pytest.approx(5 / math.sqrt(30))


def test_kendall_drops_nan_pairs():
    assert kendall_tau_b([1, 2, np.nan, 3], [1, 2, 9, 3]) == pytest.approx(1.0)


@pytest.mark.parametrize(("x", "y"), [([1], [1]), ([], []), ([1, 1, 1], [1, 2, 3])])
def test_kendall_undefined_is_nan(x, y):
    assert math.isnan(kendall_tau_b(x, y))


def test_kendall_length_mismatch_raises():
    with pytest.raises(ValueError):
        kendall_tau_b([1, 2], [1, 2, 3])


def test_kendall_matches_scipy_when_available():
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(0)
    for _ in range(50):
        n = int(rng.integers(3, 21))
        x = rng.integers(1, 8, size=n)  # small range -> many ties
        y = rng.integers(1, 8, size=n)
        expected = stats.kendalltau(x, y, variant="b").statistic
        result = kendall_tau_b(x, y)
        if np.isnan(expected):
            assert np.isnan(result)
        else:
            assert result == pytest.approx(expected)


# ---------- per-lap Kendall ----------

def test_per_lap_kendall_skips_small_laps():
    df = make_eval(
        [
            ("A", 1, 1, 1, "normal", None), ("B", 1, 2, 2, "normal", None), ("C", 1, 3, 3, "normal", None),
            ("A", 2, 1, 2, "normal", None), ("B", 2, 2, 1, "normal", None), ("C", 2, 3, 3, "normal", None),
            ("A", 3, 1, 1, "normal", None), ("B", 3, 2, 2, "normal", None),  # only 2 drivers
        ]
    )
    taus = per_lap_kendall(df)
    assert taus.to_dict() == pytest.approx({1: 1.0, 2: 1 / 3})
    assert mean_kendall(df) == pytest.approx(2 / 3)


def test_mean_kendall_is_nan_when_no_lap_qualifies(small_eval):
    assert math.isnan(mean_kendall(small_eval, min_drivers=10))
