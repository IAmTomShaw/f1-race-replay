"""Accuracy metrics for the evaluation table built by ``alignment.build_eval_table``.

Every metric ignores excluded rows. Excluded rows are still counted in
``summarise`` so nothing is hidden.
"""

import numpy as np
import pandas as pd

from src.eval.ground_truth import SEGMENTS



def scored_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows that can be scored: not excluded and with both positions known."""
    ok = df["excluded_reason"].isna() & df["official_pos"].notna() & df["computed_pos"].notna()
    return df[ok]


def exact_match_rate(df: pd.DataFrame) -> float:
    """Share of scored rows where the replay position equals the official one. NaN if none."""
    s = scored_rows(df)
    if s.empty:
        return float("nan")
    return float((s["computed_pos"] == s["official_pos"]).mean())


def mean_abs_error(df: pd.DataFrame) -> float:
    """Average number of places the replay is off by. NaN if there are no scored rows."""
    s = scored_rows(df)
    if s.empty:
        return float("nan")
    return float((s["computed_pos"] - s["official_pos"]).abs().mean())
