import pytest

from src.lib.sectors import (
    SECTOR_KEYS,
    STATUS_NONE,
    STATUS_PERSONAL_BEST,
    STATUS_SESSION_BEST,
    best_sectors,
    classify_sector_statuses,
    session_best_holders,
    theoretical_best_s,
)


def _entry(lap, s1=None, s2=None, s3=None, **extra):
    entry = {"lap": lap, "sector1_s": s1, "sector2_s": s2, "sector3_s": s3}
    entry.update(extra)
    return entry


class TestBestSectors:
    def test_picks_minimum_per_sector(self):
        entries = [
            _entry(1, 30.0, 40.0, 25.0),
            _entry(2, 29.5, 41.0, 24.8),
            _entry(3, 31.0, 39.2, 26.0),
        ]
        assert best_sectors(entries) == {
            "sector1_s": 29.5,
            "sector2_s": 39.2,
            "sector3_s": 24.8,
        }

    def test_ignores_missing_and_invalid_values(self):
        entries = [
            _entry(1, None, 40.0, 0.0),
            _entry(2, -5.0, 41.0, None),
        ]
        result = best_sectors(entries)
        assert result["sector1_s"] is None
        assert result["sector2_s"] == 40.0
        assert result["sector3_s"] is None

    def test_empty_entries(self):
        assert best_sectors([]) == {key: None for key in SECTOR_KEYS}


class TestTheoreticalBest:
    def test_sums_best_sectors_across_laps(self):
        entries = [
            _entry(1, 30.0, 40.0, 25.0),
            _entry(2, 29.5, 41.0, 24.8),
        ]
        assert theoretical_best_s(entries) == pytest.approx(29.5 + 40.0 + 24.8)

    def test_none_when_a_sector_is_never_set(self):
        entries = [_entry(1, 30.0, 40.0, None)]
        assert theoretical_best_s(entries) is None


class TestClassifySectorStatuses:
    def test_session_best_beats_personal_best(self):
        data = {
            "VER": [_entry(1, 30.0, 40.0, 25.0)],
            "HAM": [_entry(1, 29.0, 41.0, 26.0)],
        }
        statuses = classify_sector_statuses(data)
        # HAM holds the session best in S1, VER in S2 and S3
        assert statuses[("HAM", 1)]["sector1_s"] == STATUS_SESSION_BEST
        assert statuses[("VER", 1)]["sector2_s"] == STATUS_SESSION_BEST
        assert statuses[("VER", 1)]["sector3_s"] == STATUS_SESSION_BEST
        # VER's S1 is his personal best but not the session best
        assert statuses[("VER", 1)]["sector1_s"] == STATUS_PERSONAL_BEST

    def test_slower_lap_is_not_flagged(self):
        data = {
            "VER": [
                _entry(1, 30.0, 40.0, 25.0),
                _entry(2, 31.0, 42.0, 26.0),
            ],
        }
        statuses = classify_sector_statuses(data)
        assert statuses[("VER", 2)] == {key: STATUS_NONE for key in SECTOR_KEYS}
        # The single-driver fastest lap is both personal and session best;
        # session best takes precedence.
        assert statuses[("VER", 1)] == {key: STATUS_SESSION_BEST for key in SECTOR_KEYS}

    def test_tied_session_best_flags_both_drivers(self):
        data = {
            "VER": [_entry(1, 30.0, 40.0, 25.0)],
            "HAM": [_entry(1, 30.0, 41.0, 26.0)],
        }
        statuses = classify_sector_statuses(data)
        assert statuses[("VER", 1)]["sector1_s"] == STATUS_SESSION_BEST
        assert statuses[("HAM", 1)]["sector1_s"] == STATUS_SESSION_BEST

    def test_missing_sector_times_are_none_status(self):
        data = {"VER": [_entry(1, None, 40.0, -1.0)]}
        statuses = classify_sector_statuses(data)
        assert statuses[("VER", 1)]["sector1_s"] == STATUS_NONE
        assert statuses[("VER", 1)]["sector3_s"] == STATUS_NONE
        assert statuses[("VER", 1)]["sector2_s"] == STATUS_SESSION_BEST

    def test_entries_without_lap_number_are_skipped(self):
        data = {"VER": [{"sector1_s": 30.0, "sector2_s": 40.0, "sector3_s": 25.0}]}
        assert classify_sector_statuses(data) == {}


class TestSessionBestHolders:
    def test_returns_time_and_holders(self):
        data = {
            "VER": [_entry(1, 30.0, 40.0, 25.0)],
            "HAM": [_entry(1, 30.0, 39.0, 26.0)],
        }
        holders = session_best_holders(data)
        assert holders["sector1_s"] == (30.0, ["HAM", "VER"])
        assert holders["sector2_s"] == (39.0, ["HAM"])
        assert holders["sector3_s"] == (25.0, ["VER"])

    def test_empty_data(self):
        holders = session_best_holders({})
        assert holders == {key: (None, []) for key in SECTOR_KEYS}
