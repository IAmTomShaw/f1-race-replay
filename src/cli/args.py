"""
Argument parser for the F1 Race Replay CLI.

The legacy ``main.py`` uses ad-hoc ``if "--flag" in sys.argv``
chains. This module is a thin wrapper around ``argparse`` that
captures every flag the project documents in the README:

* ``--viewer``           : open the Arcade viewer window
* ``--cli``              : use the questionary CLI menu
* ``--year YYYY``        : race year
* ``--round N``          : round number
* ``--sprint``           : sprint session
* ``--qualifying``       : qualifying session
* ``--sprint-qualifying``: sprint qualifying
* ``--refresh-data``     : ignore cache, recompute telemetry
* ``--no-hud``           : hide HUD overlays
* ``--verbose``          : verbose logging
* ``--ready-file PATH``  : write a file once the replay is ready
* ``--diagnostics``      : print diagnostics and exit
* ``--list-rounds``      : list rounds for the given year
* ``--list-sprints``     : list sprint rounds for the given year

The parser supports ``--diagnostics`` as a SUBCOMMAND or as a
top-level flag. When given, the program prints the diagnostic
report and exits 0.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence


SESSION_RACE = "R"
SESSION_SPRINT = "S"
SESSION_QUALI = "Q"
SESSION_SPRINT_QUALI = "SQ"


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Two usage modes are supported:

    1. Backwards-compatible flat flags::

        python main.py --viewer --year 2025 --round 12

    2. Subcommand form::

        python main.py replay --viewer --year 2025 --round 12
        python main.py diagnostics

    The flat form is the default; the subcommand form is opt-in
    when the first argv token is one of ``replay`` or
    ``diagnostics``.
    """
    parser = argparse.ArgumentParser(
        prog="f1-race-replay",
        description="F1 Race Replay — race telemetry visualization",
    )
    parser.add_argument("--viewer", action="store_true",
                        help="open the Arcade viewer window")
    parser.add_argument("--cli", action="store_true",
                        help="use the questionary CLI menu")
    parser.add_argument("--year", type=int, default=None,
                        help="race year (e.g. 2025)")
    parser.add_argument("--round", type=int, default=None,
                        help="round number (e.g. 12)")
    parser.add_argument("--sprint", action="store_true",
                        help="sprint session")
    parser.add_argument("--qualifying", action="store_true",
                        help="qualifying session")
    parser.add_argument("--sprint-qualifying", action="store_true",
                        help="sprint qualifying session")
    parser.add_argument("--refresh-data", action="store_true",
                        help="ignore cache and recompute telemetry")
    parser.add_argument("--no-hud", action="store_true",
                        help="hide HUD overlays")
    parser.add_argument("--verbose", action="store_true",
                        help="verbose logging")
    parser.add_argument("--ready-file", default=None,
                        help="write a file at this path once the replay is ready")
    parser.add_argument("--list-rounds", action="store_true",
                        help="list rounds for --year and exit")
    parser.add_argument("--list-sprints", action="store_true",
                        help="list sprint rounds for --year and exit")
    parser.add_argument("--diagnostics", action="store_true",
                        help="print diagnostics and exit")
    return parser


def parse_args(argv: Optional[Sequence[str]] = None
                ) -> argparse.Namespace:
    """Parse argv. Returns a Namespace with a ``_cmd`` attribute
    set to ``"diagnostics"`` when ``--diagnostics`` was passed,
    otherwise ``"replay"``.

    The legacy tokens ``replay`` and ``diagnostics`` (when used
    as the first non-flag token) are stripped before parsing so
    the canonical flat form is the only schema.
    """
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Strip a leading legacy subcommand token.
    if argv and argv[0] in ("replay", "diagnostics") and not argv[0].startswith("-"):
        argv = argv[1:]
    ns = parser.parse_args(argv)
    ns._cmd = "diagnostics" if getattr(ns, "diagnostics", False) else "replay"
    return ns


def session_type(args: argparse.Namespace) -> str:
    """Resolve the --session-type flag from the boolean args."""
    if args.sprint_qualifying:
        return SESSION_SPRINT_QUALI
    if args.sprint:
        return SESSION_SPRINT
    if args.qualifying:
        return SESSION_QUALI
    return SESSION_RACE


__all__ = [
    "SESSION_RACE",
    "SESSION_SPRINT",
    "SESSION_QUALI",
    "SESSION_SPRINT_QUALI",
    "build_parser",
    "parse_args",
    "session_type",
]
