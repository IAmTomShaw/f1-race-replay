"""Tests for main CLI argument handling."""

import argparse

import pytest

from main import _build_parser, _resolve_session_type, _run_from_args


def test_resolve_session_type_default_race() -> None:
    """No flags defaults to race session."""
    parser = _build_parser()
    args = parser.parse_args([])
    assert _resolve_session_type(args) == "R"


def test_resolve_session_type_qualifying() -> None:
    """Qualifying flag maps to Q session."""
    parser = _build_parser()
    args = parser.parse_args(["--qualifying"])
    assert _resolve_session_type(args) == "Q"


def test_resolve_session_type_sprint() -> None:
    """Sprint flag maps to S session."""
    parser = _build_parser()
    args = parser.parse_args(["--sprint"])
    assert _resolve_session_type(args) == "S"


def test_resolve_session_type_sprint_qualifying_priority() -> None:
    """Sprint qualifying mode wins when both sprint and qualifying are set."""
    parser = _build_parser()
    args = parser.parse_args(["--sprint", "--qualifying"])
    assert _resolve_session_type(args) == "SQ"


def test_resolve_session_type_practice() -> None:
    """Practice selector maps to FP session codes."""
    parser = _build_parser()
    args = parser.parse_args(["--practice", "2"])
    assert _resolve_session_type(args) == "FP2"


def test_run_from_args_rejects_non_positive_speed() -> None:
    """Playback speed validation should fail before runtime imports."""
    args = argparse.Namespace(
        cli=False,
        viewer=False,
        year=None,
        round_number=None,
        list_rounds=False,
        list_sprints=False,
        qualifying=False,
        sprint=False,
        sprint_qualifying=False,
        practice=None,
        fp1=False,
        fp2=False,
        fp3=False,
        no_hud=False,
        ready_file=None,
        playback_speed=0.0,
        refresh_data=False,
        verbose=False,
    )

    with pytest.raises(ValueError, match="--playback-speed must be greater than 0"):
        _run_from_args(args)


def test_run_from_args_rejects_practice_combo_flags() -> None:
    """Practice mode cannot be combined with sprint/qualifying flags."""
    args = argparse.Namespace(
        cli=False,
        viewer=False,
        year=None,
        round_number=None,
        list_rounds=False,
        list_sprints=False,
        qualifying=True,
        sprint=False,
        sprint_qualifying=False,
        practice=1,
        fp1=False,
        fp2=False,
        fp3=False,
        no_hud=False,
        ready_file=None,
        playback_speed=1.0,
        refresh_data=False,
        verbose=False,
    )

    with pytest.raises(ValueError, match="--practice cannot be combined"):
        _run_from_args(args)
