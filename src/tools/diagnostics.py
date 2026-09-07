"""
``--diagnostics`` subcommand implementation.

Prints a concise, actionable report covering:

* Python version, OS, executable
* Installed (and missing) project dependencies
* Project root, cache directory, computed-data directory
* Stream / socket configuration
* OpenGL info if ``OpenGL`` / ``glcontext`` is available
* Cache schema version + application version

This is the *output* the user gets from
``python main.py --diagnostics``. It is also the function the
unit tests exercise.
"""
from __future__ import annotations

import os
import platform
import sys
from typing import Dict, List, Optional, Tuple

from src.data.cache import APP_VERSION, CACHE_SCHEMA_VERSION
from src.lib.resource_paths import (
    cache_dir,
    computed_data_dir,
    project_root,
)


# Project dependencies, grouped by required / optional. The
# ``diagnostics`` output uses these labels.
REQUIRED_DEPS: Tuple[str, ...] = (
    "fastf1",
    "arcade",
    "pyglet",
    "PySide6",
    "numpy",
    "pandas",
    "scipy",
    "matplotlib",
)


def _safe_version(name: str) -> Optional[str]:
    try:
        mod = __import__(name)
    except Exception:
        return None
    return getattr(mod, "__version__", None)


def _section(title: str) -> str:
    return f"\n=== {title} ==="


def _kv(label: str, value: object) -> str:
    return f"  {label}: {value}"


def collect_diagnostics() -> str:
    """Return a multi-line diagnostic report."""
    lines: List[str] = []

    lines.append("F1 Race Replay diagnostics")
    lines.append("=" * 40)

    # -- Python / OS -------------------------------------------------
    lines.append(_section("Python / OS"))
    lines.append(_kv("Python", sys.version.split()[0]))
    lines.append(_kv("Executable", sys.executable))
    lines.append(_kv("Platform", platform.platform()))
    lines.append(_kv("CWD", os.getcwd()))
    try:
        lines.append(_kv("Project root", project_root()))
    except FileNotFoundError as e:
        lines.append(_kv("Project root", f"NOT FOUND ({e})"))

    # -- Cache -------------------------------------------------------
    lines.append(_section("Cache"))
    try:
        lines.append(_kv("Cache directory", cache_dir()))
    except Exception as e:
        lines.append(_kv("Cache directory", f"ERROR: {e}"))
    try:
        lines.append(_kv("Computed-data directory", computed_data_dir()))
    except Exception as e:
        lines.append(_kv("Computed-data directory", f"ERROR: {e}"))
    lines.append(_kv("Cache schema version", CACHE_SCHEMA_VERSION))
    lines.append(_kv("Application version", APP_VERSION))

    # -- Dependencies ------------------------------------------------
    lines.append(_section("Dependencies"))
    for name in REQUIRED_DEPS:
        v = _safe_version(name)
        status = v if v is not None else "MISSING"
        lines.append(f"  {name:<14} {status}")

    # -- Stream / sockets -------------------------------------------
    lines.append(_section("Stream / sockets"))
    lines.append(_kv("Stream port (default)", 9999))
    lines.append(_kv("SO_REUSEADDR", "enabled"))
    lines.append(_kv("Broker queue capacity (default)", 64))

    # -- OpenGL ------------------------------------------------------
    lines.append(_section("OpenGL"))
    gl = _safe_version("OpenGL") or _safe_version("glcontext")
    if gl is None:
        lines.append("  PyOpenGL not installed; renderer will use Arcade's built-in GL info")
    else:
        lines.append(_kv("PyOpenGL", gl))

    # -- Recommendations --------------------------------------------
    lines.append(_section("Notes"))
    lines.append("  This report is purely informational; no install or upgrade is performed.")
    lines.append("  To check telemetry invariants: see docs/DIAGNOSIS.md.")
    return "\n".join(lines)


def main() -> int:
    """Entry point for ``python -m src.tools.diagnostics``."""
    print(collect_diagnostics())
    return 0


__all__ = [
    "REQUIRED_DEPS",
    "collect_diagnostics",
    "main",
]
