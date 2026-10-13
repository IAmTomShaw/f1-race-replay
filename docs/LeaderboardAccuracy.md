# Leaderboard Accuracy Benchmark

The replay works out the running order itself, from where each car is on track.
This benchmark measures how often that order matches the **official** lap-by-lap
positions from FastF1, overall and in the parts of a race where it tends to go
wrong (lap 1, pit stops, safety cars, the final lap).

It gives changes to the ordering logic an objective number. Run it on `main`, run
it on a branch, and compare.

## Quick start

    python -m tools.leaderboard_benchmark --year 2025 --round 12 --refresh

Add `--offset-sensitivity` to check that the result does not depend on the
sampling offset (see [Method](#method)).

| Flag | Meaning |
|---|---|
| `--year`, `--round` | Which event |
| `--sprint` | Benchmark the sprint instead of the race |
| `--offset-s` | Seconds after the line crossing at which the replay position is read (default `1.0`) |
| `--refresh` | Recompute replay telemetry. **Use it after any code change.** Without it, `get_race_telemetry` reuses `computed_data/*.pkl` and you benchmark old code |
| `--offset-sensitivity` | Also run offsets 0.5, 1.0 and 2.0 s and report how much the result moves |
| `--out` | Output folder (default `computed_data/benchmarks/`, which is git-ignored) |

The first run for a race needs network access to download FastF1 data. Later runs
use the FastF1 cache.

## Output

| File | Contents |
|---|---|
| `<event>_eval.csv` | One row per driver-lap: `driver, lap, official_pos, computed_pos, segment, excluded_reason, error, frame_idx, method` |
| `<event>_summary.csv` | Metrics for `overall` and each segment |
| `<event>_report.md` | The summary table, excluded rows, lap-time sanity check, offset sensitivity, and the git commit / branch / date of the run |

## Method

**Ground truth.** `session.laps["Position"]` is the driver's official position
when they cross the line at the end of lap N.

**Replay value.** In the replay frames, lap N ends at the first frame where the
driver's `lap` reaches N+1 (the *crossing*). The benchmark reads the driver's
`position` from the frame `--offset-s` seconds after the crossing. It reads
slightly *after* the line, not exactly on it, because the replay's lap value is
rounded from interpolated telemetry, so the frames right at the line are the
noisiest.

**Final lap.** After the flag, a finisher's replay data stops and the car is held
at its last point, so there is no crossing into another lap. For a driver's last
lap in the replay, the benchmark uses their position in the **last frame**: the
final order the replay shows when it ends.

**Retired drivers.** Their last classified lap still has a crossing (they started
the next lap and stopped during it), so it is scored like any other lap. The lap
they retired on has no official position and is excluded.

### Segments

Every driver-lap gets exactly one label. If several fit, the first in this list wins.

| Segment | Rule |
|---|---|
| `final` | The driver's last lap with a known official position |
| `lap1` | Lap 1 |
| `pit` | In-lap or out-lap (`PitInTime` or `PitOutTime` is set) |
| `sc_vsc` | `TrackStatus` contains `4` (Safety Car), `6` (VSC) or `7` (VSC ending) |
| `normal` | Everything else |

### Metrics

| Metric | Meaning |
|---|---|
| `exact_match` | Share of driver-laps where the replay position equals the official one |
| `mae` | Mean absolute error: average number of places off |
| `kendall_tau` | Kendall's tau-b between the official and replay order on each lap (1 = same order, -1 = reversed), averaged over laps with at least 3 scored drivers. Implemented with numpy, no scipy |
| `n_rows`, `n_excluded`, `n_scored` | Row counts, so nothing is silently dropped |

Per-segment `kendall_tau` only compares drivers inside that segment on the same
lap, so it is usually `-` for `pit` (3+ cars rarely pit on the same lap).

### Excluded rows

Excluded rows are counted in the report, never hidden.

| Reason | When |
|---|---|
| `official_pos_nan` | FastF1 has no `Position` for that lap (e.g. the lap a driver retired on) |
| `no_crossing` | The replay has no value for that lap (driver missing from frames, or a lap skipped in the telemetry) |

### Sanity checks in the report

- **Lap-time check.** The time between two replay crossings should equal the
  official `LapTime`. If many laps are off by more than 0.5 s, crossings are
  found at the wrong moment and that race's numbers should not be trusted.
- **Offset sensitivity.** With `--offset-sensitivity`, the report warns when the
  overall exact-match changes by more than 5 points between 0.5, 1.0 and 2.0 s.

## How to benchmark a branch or pull request

Use a separate git worktree per branch. Each worktree has its own
`computed_data/`, so cached telemetry from one branch cannot leak into another.

    git fetch upstream pull/<N>/head:pr-<N>
    git worktree add ../frr-pr-<N> pr-<N>
    cd ../frr-pr-<N>
    git checkout <benchmark-branch> -- src/eval tools tests/eval
    python -m tools.leaderboard_benchmark --year 2025 --round 12 --refresh
    cd -
    git worktree remove --force ../frr-pr-<N>

Run the same command on `main` and compare the two `_summary.csv` files. The
report header records the commit (`-dirty` when the benchmark files were copied
in), so you can always tell which code produced which numbers.

## Results

Baseline numbers for `main` will be added here after the first runs on real data.

## Limitations

- The official `Position` is only known at the end of each lap, so the benchmark
  checks the order once per lap, not continuously.
- The offset is a judgement call. Use `--offset-sensitivity` to show it does not
  change the conclusion.
- The final-lap value is the replay's last frame. If the replay does not end in
  the classified order (e.g. finishers held at the line with the same distance),
  that shows up as `final` errors, which is the intended signal.
- The benchmark scores `frame["position"]` from `get_race_telemetry`. The
  on-screen leaderboard in `src/interfaces/race_replay.py` re-sorts drivers with
  its own track projection. A change to that UI ordering is not measured unless
  it is passed in as `position_fn` to `sample_computed_positions`.
- Penalties applied after the race are not in lap-by-lap positions, so they are
  not part of the comparison.

## Tests

The unit tests run offline on synthetic laps and frames:

    python -m pytest tests/eval
