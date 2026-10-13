import sys

import numpy as np
import pandas as pd
import pytest

from tools import leaderboard_benchmark as bench

SPEEDS = {"VER": 1.2, "HAM": 1.1, "LEC": 1.0}  # metres per second, so VER leads all race


def fake_race(n_laps=3, lap_len=10.0, dt=0.5):
    """Frames shaped like get_race_telemetry output, plus matching official laps."""
    total = n_laps * lap_len
    t_end = total / min(SPEEDS.values()) + 2
    frames = []
    for i in range(int(t_end / dt) + 1):
        t = i * dt
        cars = {}
        for code, speed in SPEEDS.items():
            dist = min(speed * t, total)  # cars stop at the flag, like np.interp clamping
            cars[code] = {"lap": min(int(dist // lap_len) + 1, n_laps), "dist": dist}
        order = sorted(cars, key=lambda c: (cars[c]["lap"], cars[c]["dist"]), reverse=True)
        for pos, code in enumerate(order, start=1):
            cars[code]["position"] = pos
        frames.append({"t": t, "lap": cars[order[0]]["lap"], "drivers": cars})

    rows = []
    for pos, (code, speed) in enumerate(SPEEDS.items(), start=1):
        for lap in range(1, n_laps + 1):
            rows.append((code, float(lap), float(pos), lap_len / speed))
    laps = pd.DataFrame(rows, columns=["Driver", "LapNumber", "Position", "LapTime_s"])
    laps["LapTime"] = pd.to_timedelta(laps.pop("LapTime_s"), unit="s")
    laps["PitInTime"] = pd.to_timedelta([np.nan] * len(laps), unit="s")
    laps["PitOutTime"] = pd.to_timedelta([np.nan] * len(laps), unit="s")
    laps["TrackStatus"] = "1"
    return laps, frames


def fake_loader(year, round_number, sprint, refresh):
    laps, frames = fake_race()
    return "2025 Season Round 12: Test Grand Prix - Race", laps, frames, "fake"


# ---------- arguments ----------

def test_parse_args_defaults():
    args = bench.parse_args(["--year", "2025", "--round", "12"])
    assert (args.year, args.round_number) == (2025, 12)
    assert args.offset_s == 1.0
    assert not args.sprint and not args.refresh and not args.offset_sensitivity
    assert args.out == bench.DEFAULT_OUT


def test_parse_args_rejects_negative_offset():
    with pytest.raises(SystemExit):
        bench.parse_args(["--year", "2025", "--round", "12", "--offset-s", "-1"])


# ---------- evaluation ----------

def test_evaluate_perfect_replay_scores_100_percent():
    laps, frames = fake_race()
    table, summary = bench.evaluate(laps, frames)
    overall = summary.set_index("segment").loc["overall"]
    assert len(table) == 9
    assert overall["n_excluded"] == 0
    assert overall["exact_match"] == pytest.approx(1.0)
    assert overall["mae"] == pytest.approx(0.0)
    assert overall["kendall_tau"] == pytest.approx(1.0)


def test_offset_sensitivity_has_one_block_per_offset():
    laps, frames = fake_race()
    sens = bench.offset_sensitivity(laps, frames, offsets=(0.5, 1.0, 2.0))
    assert sorted(sens["offset_s"].unique()) == [0.5, 1.0, 2.0]
    assert len(sens) == 3 * 6  # overall + 5 segments
    spread = bench.sensitivity_spread(sens).set_index("segment")
    assert spread.loc["overall", "exact_match"] == pytest.approx(0.0)


def test_lap_time_check_compares_every_driver():
    laps, frames = fake_race()
    check = bench.lap_time_check(frames, laps)
    assert set(check["driver"]) == set(SPEEDS)
    # Crossings are found on a 0.5 s frame grid, so lap times agree to within one frame.
    assert check["diff_s"].abs().max() <= 0.5 + 1e-9


# ---------- report ----------

def test_markdown_table_formats_values():
    df = pd.DataFrame({"segment": ["overall"], "exact_match": [0.8766], "mae": [np.nan]})
    text = bench.markdown_table(df, {"exact_match": "pct", "mae": "float2"})
    assert text.splitlines() == [
        "| segment | exact_match | mae |",
        "|---|---|---|",
        "| overall | 87.7% | - |",
    ]


def _sensitivity(overall_values):
    rows = []
    for offset, value in zip((0.5, 1.0, 2.0), overall_values):
        rows.append({"segment": "overall", "exact_match": value, "mae": 0.0, "kendall_tau": 1.0, "offset_s": offset})
    return pd.DataFrame(rows)


def test_report_flags_fragile_offsets():
    laps, frames = fake_race()
    table, summary = bench.evaluate(laps, frames)
    report = bench.format_report("X", {"Git commit": "abc1234"}, summary, pd.Series(dtype=int),
                                 sensitivity=_sensitivity([0.70, 0.80, 0.90]))
    assert "**Git commit:** abc1234" in report
    assert "Warning: fragile" in report


def test_report_says_stable_when_offsets_agree():
    laps, frames = fake_race()
    _, summary = bench.evaluate(laps, frames)
    report = bench.format_report("X", {}, summary, pd.Series(dtype=int),
                                 sensitivity=_sensitivity([0.80, 0.81, 0.82]))
    assert "Stable" in report
    assert "fragile" not in report


def test_report_lists_exclusions_and_lap_check():
    laps, frames = fake_race()
    _, summary = bench.evaluate(laps, frames)
    exclusions = pd.Series({"no_crossing": 3})
    check = bench.lap_time_check(frames, laps)
    report = bench.format_report("X", {}, summary, exclusions, lap_check=check)
    assert "`no_crossing`: 3" in report
    assert "Lap-time sanity check" in report


def test_safe_slug_removes_characters_windows_rejects():
    assert bench.safe_slug("2025 Season Round 12: British Grand Prix - Race") == (
        "2025_Season_Round_12_British_Grand_Prix_-_Race"
    )


def test_git_commit_without_git_is_unknown(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("git not installed")

    monkeypatch.setattr(bench.subprocess, "run", broken)
    assert bench.git_commit() == "unknown"


# ---------- end to end (fake loader, no network) ----------

def test_main_writes_three_files(tmp_path, capsys):
    code = bench.main(
        ["--year", "2025", "--round", "12", "--out", str(tmp_path), "--offset-sensitivity"],
        loader=fake_loader,
    )
    assert code == 0
    slug = "2025_Season_Round_12_Test_Grand_Prix_-_Race"
    for suffix in ("_eval.csv", "_summary.csv", "_report.md"):
        assert (tmp_path / f"{slug}{suffix}").exists()

    summary = pd.read_csv(tmp_path / f"{slug}_summary.csv")
    assert summary.loc[summary["segment"] == "overall", "exact_match"].iloc[0] == pytest.approx(1.0)
    report = (tmp_path / f"{slug}_report.md").read_text(encoding="utf-8")
    assert "Offset sensitivity" in report
    assert "wrote" in capsys.readouterr().out


def test_load_race_refresh_forces_recompute(monkeypatch):
    f1_data = pytest.importorskip("src.f1_data")
    laps, frames = fake_race()
    seen = {}

    class FakeSession:
        def __init__(self):
            self.laps = laps

        def __repr__(self):
            return "2025 Season Round 12: Test Grand Prix - Race"

    def fake_telemetry(session, session_type="R"):
        seen["refresh"] = "--refresh-data" in sys.argv
        seen["session_type"] = session_type
        return {"frames": frames}

    monkeypatch.setattr(sys, "argv", ["leaderboard_benchmark"])
    monkeypatch.setattr(f1_data, "enable_cache", lambda: None)
    monkeypatch.setattr(f1_data, "load_session", lambda year, rnd, session_type="R": FakeSession())
    monkeypatch.setattr(f1_data, "get_race_telemetry", fake_telemetry)

    name, got_laps, got_frames, source = bench.load_race(2025, 12, sprint=True, refresh=True)
    assert seen == {"refresh": True, "session_type": "S"}
    assert name == "2025_Season_Round_12:_Test_Grand_Prix_-_Race"
    assert got_frames is frames
    assert "recomputed" in source


def test_load_race_raises_when_session_fails(monkeypatch):
    f1_data = pytest.importorskip("src.f1_data")
    monkeypatch.setattr(f1_data, "enable_cache", lambda: None)
    monkeypatch.setattr(f1_data, "load_session", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="Could not load"):
        bench.load_race(2025, 99, sprint=False, refresh=False)
