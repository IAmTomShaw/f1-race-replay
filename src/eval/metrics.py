"""Accuracy metrics for the evaluation table built by ``alignment.build_eval_table``.

Every metric ignores excluded rows. Excluded rows are still counted in
``summarise`` so nothing is hidden.
"""

import numpy as np
import pandas as pd

from src.eval.ground_truth import SEGMENTS

SUMMARY_COLUMNS = ["segment", "n_rows", "n_excluded", "n_scored", "exact_match", "mae", "kendall_tau"]


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


def kendall_tau_b(x, y) -> float:
    """Kendall's tau-b rank correlation, written with numpy (no scipy).

    For every pair of drivers, compare their order in ``x`` and in ``y``:
    same order = concordant, opposite order = discordant.
    tau-b = (concordant - discordant) / sqrt(pairs not tied in x * pairs not tied in y)
    1.0 = identical order, -1.0 = fully reversed, NaN when it is undefined.
    Pairs with a NaN on either side are dropped. O(n^2), fine for 20 drivers.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape:
        raise ValueError("x and y must have the same length")
    keep = ~(np.isnan(x) | np.isnan(y))
    x, y = x[keep], y[keep]
    if len(x) < 2:
        return float("nan")

    i, j = np.triu_indices(len(x), k=1)  # every pair once
    dx = np.sign(x[i] - x[j])
    dy = np.sign(y[i] - y[j])
    denom = np.sqrt(np.count_nonzero(dx) * np.count_nonzero(dy))
    if denom == 0:
        return float("nan")
    return float(np.sum(dx * dy) / denom)


def per_lap_kendall(df: pd.DataFrame, min_drivers: int = 3) -> pd.Series:
    """Kendall tau-b between official and replay order, per lap.

    Laps with fewer than ``min_drivers`` scored drivers are skipped because
    the order of 1 or 2 cars says little.
    """
    s = scored_rows(df)
    taus = {}
    for lap, group in s.groupby("lap"):
        if len(group) >= min_drivers:
            taus[int(lap)] = kendall_tau_b(group["official_pos"], group["computed_pos"])
    return pd.Series(taus, name="kendall_tau", dtype=float)


def mean_kendall(df: pd.DataFrame, min_drivers: int = 3) -> float:
    """Average of ``per_lap_kendall`` over laps where it is defined. NaN if none."""
    taus = per_lap_kendall(df, min_drivers).dropna()
    return float(taus.mean()) if len(taus) else float("nan")


def _summary_row(name: str, part: pd.DataFrame, min_drivers: int) -> dict:
    n_excluded = int(part["excluded_reason"].notna().sum())
    return {
        "segment": name,
        "n_rows": int(len(part)),
        "n_excluded": n_excluded,
        "n_scored": int(len(scored_rows(part))),
        "exact_match": exact_match_rate(part),
        "mae": mean_abs_error(part),
        "kendall_tau": mean_kendall(part, min_drivers),
    }


def summarise(df: pd.DataFrame, min_drivers: int = 3) -> pd.DataFrame:
    """One row for ``overall`` plus one per segment (segments with no rows are kept, with NaN metrics).

    Note: per-segment Kendall tau only uses drivers in that segment on each
    lap, so it is usually NaN for ``pit`` (rarely 3+ cars pit on the same lap).
    """
    rows = [_summary_row("overall", df, min_drivers)]
    for segment in SEGMENTS:
        rows.append(_summary_row(segment, df[df["segment"] == segment], min_drivers))
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def exclusion_counts(df: pd.DataFrame) -> pd.Series:
    """How many rows were excluded, by reason."""
    return df["excluded_reason"].dropna().value_counts().rename("n_rows")
