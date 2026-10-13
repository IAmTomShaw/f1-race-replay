"""Leaderboard accuracy benchmark: replay running order vs official FastF1 positions.

Usage:
    python -m tools.leaderboard_benchmark --year 2025 --round 12 --refresh
    python -m tools.leaderboard_benchmark --year 2025 --round 12 --offset-sensitivity

Writes three files to --out (default computed_data/benchmarks/):
    <event>_eval.csv     one row per driver-lap (official, computed, segment, exclusions)
    <event>_summary.csv  metrics overall and per segment
    <event>_report.md    the summary as a markdown table plus run details
"""

import argparse
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.eval.alignment import build_eval_table, compare_lap_times, driver_codes, sample_computed_positions
from src.eval.ground_truth import build_ground_truth
from src.eval.metrics import exclusion_counts, summarise

DEFAULT_OUT = Path("computed_data") / "benchmarks"
SENSITIVITY_OFFSETS = (0.5, 1.0, 2.0)
# If exact-match changes by more than this between offsets, the result depends
# on an arbitrary choice and the report says so.
FRAGILE_SPREAD = 0.05
LAP_TIME_TOLERANCE_S = 0.5


def non_negative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark replay leaderboard accuracy against official positions.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--round", type=int, required=True, dest="round_number")
    parser.add_argument("--sprint", action="store_true", help="benchmark the sprint instead of the race")
    parser.add_argument("--offset-s", type=non_negative_float, default=1.0,
                        help="seconds after the line crossing at which the replay position is read (default 1.0)")
    parser.add_argument("--refresh", action="store_true",
                        help="recompute replay telemetry instead of loading computed_data/*.pkl")
    parser.add_argument("--offset-sensitivity", action="store_true",
                        help=f"also run offsets {', '.join(str(o) for o in SENSITIVITY_OFFSETS)} s and report the change")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


# ---------- pure evaluation steps (no network, unit-tested) ----------

def evaluate(laps: pd.DataFrame, frames: list, offset_s: float = 1.0):
    """Return (eval_table, summary) for one race."""
    ground_truth = build_ground_truth(laps)
    computed = sample_computed_positions(frames, offset_s=offset_s)
    table = build_eval_table(ground_truth, computed)
    return table, summarise(table)


def offset_sensitivity(laps: pd.DataFrame, frames: list, offsets=SENSITIVITY_OFFSETS) -> pd.DataFrame:
    """Summary metrics for several offsets, one row per (offset, segment)."""
    parts = []
    for offset in offsets:
        _, summary = evaluate(laps, frames, offset_s=offset)
        parts.append(summary.assign(offset_s=offset))
    return pd.concat(parts, ignore_index=True)


def sensitivity_spread(sensitivity: pd.DataFrame) -> pd.DataFrame:
    """Per segment: max minus min of each metric across offsets."""
    grouped = sensitivity.groupby("segment", sort=False)[["exact_match", "mae", "kendall_tau"]]
    return (grouped.max() - grouped.min()).reset_index()


def lap_time_check(frames: list, laps: pd.DataFrame) -> pd.DataFrame:
    """Replay vs official lap times for every driver (see alignment.compare_lap_times)."""
    parts = [compare_lap_times(frames, laps, code).assign(driver=code) for code in driver_codes(frames)]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame(columns=["lap", "replay_lap_time_s", "official_lap_time_s", "diff_s", "driver"])
    return pd.concat(parts, ignore_index=True)


# ---------- report ----------

def _fmt(value, kind: str) -> str:
    if pd.isna(value):
        return "-"
    if kind == "pct":
        return f"{value * 100:.1f}%"
    if kind == "float2":
        return f"{value:.2f}"
    if kind == "float3":
        return f"{value:.3f}"
    return str(value)


def markdown_table(df: pd.DataFrame, formats=None) -> str:
    """Small markdown table writer (pandas.to_markdown needs tabulate, which is not a dependency)."""
    formats = formats or {}
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    divider = "|" + "|".join("---" for _ in df.columns) + "|"
    lines = [header, divider]
    for _, row in df.iterrows():
        cells = [_fmt(row[c], formats.get(c, "str")) for c in df.columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


SUMMARY_FORMATS = {"exact_match": "pct", "mae": "float2", "kendall_tau": "float3"}


def format_report(event_name: str, run_info: dict, summary: pd.DataFrame, exclusions: pd.Series,
                  lap_check: pd.DataFrame = None, sensitivity: pd.DataFrame = None) -> str:
    lines = [f"# Leaderboard accuracy: {event_name}", ""]
    lines += [f"- **{key}:** {value}" for key, value in run_info.items()]
    lines += ["", "## Summary", "", markdown_table(summary, SUMMARY_FORMATS), ""]
    lines += [
        "`exact_match` = share of driver-laps where the replay position equals the official one. "
        "`mae` = average places off. `kendall_tau` = order agreement per lap (1 = identical), averaged over laps.",
        "",
    ]

    lines += ["## Excluded rows", ""]
    if exclusions.empty:
        lines += ["None.", ""]
    else:
        lines += [f"- `{reason}`: {count}" for reason, count in exclusions.items()] + [""]

    if lap_check is not None:
        lines += ["## Lap-time sanity check", ""]
        if lap_check.empty:
            lines += ["No laps to compare.", ""]
        else:
            abs_diff = lap_check["diff_s"].abs()
            share_off = float((abs_diff > LAP_TIME_TOLERANCE_S).mean())
            lines += [
                f"Time between replay crossings vs official `LapTime` over {len(lap_check)} laps: "
                f"median |diff| = {abs_diff.median():.3f} s, "
                f"{share_off * 100:.1f}% of laps off by more than {LAP_TIME_TOLERANCE_S} s.",
                "",
            ]

    if sensitivity is not None:
        spread = sensitivity_spread(sensitivity)
        overall = spread.loc[spread["segment"] == "overall", "exact_match"]
        overall_spread = float(overall.iloc[0]) if len(overall) else float("nan")
        offsets = ", ".join(f"{o:g}" for o in sorted(sensitivity["offset_s"].unique()))
        lines += ["## Offset sensitivity", "", f"Offsets tested: {offsets} s.", ""]
        segment_order = list(dict.fromkeys(sensitivity["segment"]))
        wide = sensitivity.pivot(index="segment", columns="offset_s", values="exact_match").reindex(segment_order)
        wide.columns = [f"exact_match @ {c:g}s" for c in wide.columns]
        wide = wide.reset_index()
        lines += [markdown_table(wide, {c: "pct" for c in wide.columns if c != "segment"}), ""]
        if pd.notna(overall_spread) and overall_spread > FRAGILE_SPREAD:
            lines += [
                f"**Warning: fragile.** Overall exact-match moves by {overall_spread * 100:.1f} points "
                f"between offsets (threshold {FRAGILE_SPREAD * 100:.0f}). Results depend on the offset choice.",
                "",
            ]
        else:
            lines += [f"Stable: overall exact-match moves by {_fmt(overall_spread, 'pct')} between offsets.", ""]

    return "\n".join(lines)


def safe_slug(name: str) -> str:
    """File-name-safe version of an event name (FastF1 names contain ':' which Windows rejects)."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return re.sub(r"_+", "_", slug) or "event"


def write_outputs(out_dir: Path, slug: str, table: pd.DataFrame, summary: pd.DataFrame, report: str) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "eval": out_dir / f"{slug}_eval.csv",
        "summary": out_dir / f"{slug}_summary.csv",
        "report": out_dir / f"{slug}_report.md",
    }
    table.to_csv(paths["eval"], index=False)
    summary.to_csv(paths["summary"], index=False)
    paths["report"].write_text(report, encoding="utf-8")
    return paths


def _git(*args) -> str:
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def git_commit() -> str:
    """Short hash of HEAD, with ``-dirty`` when tracked files have uncommitted changes."""
    commit = _git("rev-parse", "--short", "HEAD") or "unknown"
    if _git("status", "--porcelain", "--untracked-files=no"):
        commit += "-dirty"
    return commit


# ---------- loading real data (needs network or the FastF1 cache) ----------

def load_race(year: int, round_number: int, sprint: bool, refresh: bool):
    """Return (event_name, laps, frames, telemetry_source)."""
    from src.f1_data import enable_cache, get_race_telemetry, load_session

    session_type = "S" if sprint else "R"
    enable_cache()
    session = load_session(year, round_number, session_type)
    if session is None:
        raise RuntimeError(f"Could not load {year} round {round_number} ({session_type})")

    event_name = str(session).replace(" ", "_")
    suffix = "sprint" if sprint else "race"
    cache_file = Path("computed_data") / f"{event_name}_{suffix}_telemetry.pkl"
    if refresh:
        # get_race_telemetry only skips its pickle cache when this flag is on the command line.
        if "--refresh-data" not in sys.argv:
            sys.argv.append("--refresh-data")
        source = "recomputed (--refresh)"
    elif cache_file.exists():
        source = f"loaded from {cache_file} (may be stale; use --refresh after code changes)"
    else:
        source = "computed (no cache file yet)"

    telemetry = get_race_telemetry(session, session_type=session_type)
    return event_name, session.laps, telemetry["frames"], source


def main(argv=None, loader=load_race) -> int:
    args = parse_args(argv)
    event_name, laps, frames, source = loader(args.year, args.round_number, args.sprint, args.refresh)

    table, summary = evaluate(laps, frames, offset_s=args.offset_s)
    lap_check = lap_time_check(frames, laps)
    sensitivity = offset_sensitivity(laps, frames) if args.offset_sensitivity else None

    run_info = {
        "Session": f"{args.year} round {args.round_number} ({'sprint' if args.sprint else 'race'})",
        "Git commit": git_commit(),
        "Branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "Run at (UTC)": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "Offset": f"{args.offset_s:g} s after the line crossing",
        "Position source": "frame['position'] from get_race_telemetry",
        "Telemetry": source,
        "Frames": len(frames),
        "Python / pandas": f"{platform.python_version()} / {pd.__version__}",
    }
    report = format_report(event_name, run_info, summary, exclusion_counts(table), lap_check, sensitivity)
    paths = write_outputs(args.out, safe_slug(event_name), table, summary, report)

    print(markdown_table(summary, SUMMARY_FORMATS))
    for path in paths.values():
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    # The guard is required: get_race_telemetry uses multiprocessing.
    raise SystemExit(main())
