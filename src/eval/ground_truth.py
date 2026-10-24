"""Official lap-by-lap positions from FastF1, used as the benchmark's ground truth.

FastF1's ``session.laps`` has one row per driver per lap. ``Position`` is the
driver's official position when they crossed the line at the end of that lap.
"""

import pandas as pd

# TrackStatus is a string of status codes seen during the lap, e.g. "1", "124", "671".
SAFETY_CAR_CODES = ("4",)
VSC_CODES = ("6", "7")  # 6 = VSC deployed, 7 = VSC ending

# Highest priority first: a row that fits several segments gets the first match.
SEGMENTS = ("final", "lap1", "pit", "sc_vsc", "normal")

GROUND_TRUTH_COLUMNS = [
    "driver",
    "lap",
    "official_pos",
    "is_pit",
    "is_sc_vsc",
    "is_final",
    "is_lap1",
    "excluded_reason",
]

REQUIRED_LAP_COLUMNS = ["Driver", "LapNumber", "Position", "PitInTime", "PitOutTime", "TrackStatus"]


def _has_any_code(status, codes) -> bool:
    if not isinstance(status, str):
        return False
    return any(code in status for code in codes)


def build_ground_truth(laps: pd.DataFrame) -> pd.DataFrame:
    """Build one row per driver-lap with the official position and segment flags.

    Assumptions:
    - A pit lap is an in-lap (PitInTime set) or an out-lap (PitOutTime set).
    - A driver's final lap is their highest LapNumber with a known Position.
      Retired drivers therefore get their last completed lap as "final".
    - Rows with a missing Position are kept but marked
      ``excluded_reason="official_pos_nan"`` so they are counted, not hidden.
    """
    missing = [c for c in REQUIRED_LAP_COLUMNS if c not in laps.columns]
    if missing:
        raise ValueError(f"laps is missing required columns: {missing}")

    df = laps.loc[laps["LapNumber"].notna() & laps["Driver"].notna(), REQUIRED_LAP_COLUMNS].copy()

    out = pd.DataFrame(
        {
            "driver": df["Driver"].astype(str).to_numpy(),
            "lap": df["LapNumber"].astype(int).to_numpy(),
            "official_pos": pd.to_numeric(df["Position"], errors="coerce").to_numpy(),
            "is_pit": (df["PitInTime"].notna() | df["PitOutTime"].notna()).to_numpy(),
            "is_sc_vsc": df["TrackStatus"]
            .map(lambda s: _has_any_code(s, SAFETY_CAR_CODES + VSC_CODES))
            .astype(bool)
            .to_numpy(),
        }
    )
    out = out.drop_duplicates(subset=["driver", "lap"], keep="first")
    out = out.sort_values(["driver", "lap"]).reset_index(drop=True)

    out["is_lap1"] = out["lap"] == 1

    classified = out[out["official_pos"].notna()]
    final_lap = classified.groupby("driver")["lap"].max()
    out["is_final"] = out["lap"] == out["driver"].map(final_lap)
    out["is_final"] = out["is_final"].fillna(False).astype(bool)

    out["excluded_reason"] = pd.Series([None] * len(out), dtype=object)
    out.loc[out["official_pos"].isna(), "excluded_reason"] = "official_pos_nan"

    return out[GROUND_TRUTH_COLUMNS]


def label_segments(df: pd.DataFrame) -> pd.Series:
    """Give every row exactly one segment label.

    Priority when a lap fits several segments: final > lap1 > pit > sc_vsc > normal.
    Example: a pit stop under the safety car is labelled "pit".
    """
    labels = pd.Series("normal", index=df.index, dtype=object)
    # Apply from lowest to highest priority so the highest one wins.
    labels[df["is_sc_vsc"].astype(bool)] = "sc_vsc"
    labels[df["is_pit"].astype(bool)] = "pit"
    labels[df["is_lap1"].astype(bool)] = "lap1"
    labels[df["is_final"].astype(bool)] = "final"
    return labels.rename("segment")
