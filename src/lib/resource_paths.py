"""
Resource path resolution.

The legacy code resolves caches and computed-data directories
relative to ``os.getcwd()``:

    cache_path = ".fastf1-cache"  # implicitly relative to CWD

This makes the project fragile: running ``python
/absolute/path/to/main.py`` from a different working directory
silently creates the cache in the wrong place. The user is
then confused when ``--refresh-data`` does not see the
existing files.

This module provides the canonical resolution rules:

* Project root is the directory containing the top-level
  ``pyproject.toml`` / ``README.md`` / package directory. We
  discover it by walking up from this file (``__file__``)
  until we find a sentinel file.
* Cache directories are resolved to ``<root>/.fastf1-cache``
  and ``<root>/computed_data`` (or whatever the caller wants
  inside ``<root>``).
* ``resolve_from_project_root`` accepts an override via the
  ``F1_REPLAY_PROJECT_ROOT`` env var; useful for tests and for
  portable installs.
* All resolved paths are absolute, with no symlink resolution
  surprises: ``Path.resolve()`` is used.

The module does NOT read or write any files; it only resolves
paths.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Union


# Files that, if found in a directory, indicate that directory is
# the project root. The first match wins.
_PROJECT_ROOT_SENTINELS: tuple[str, ...] = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "README.md",
    ".git",
)


def _find_project_root(start: Path,
                       sentinels: Iterable[str] = _PROJECT_ROOT_SENTINELS,
                       max_levels: int = 8) -> Optional[Path]:
    """Walk up from ``start`` until a sentinel file is found.

    Returns the directory containing the sentinel, or ``None``
    if none is found within ``max_levels`` levels.
    """
    cur = start.resolve()
    for _ in range(max_levels + 1):
        for s in sentinels:
            if (cur / s).exists():
                return cur
        parent = cur.parent
        if parent == cur:
            return None
        cur = parent
    return None


def project_root() -> Path:
    """Return the project root, or raise if it cannot be located.

    The discovery order is:
    1. ``F1_REPLAY_PROJECT_ROOT`` env var, if set and pointing
       to a directory.
    2. Walk up from this file's directory looking for a sentinel.
    """
    override = os.environ.get("F1_REPLAY_PROJECT_ROOT")
    if override:
        p = Path(override).expanduser().resolve()
        if p.is_dir():
            return p
    here = Path(__file__).resolve()
    # Walk up from this file's parent. The file lives at
    # ``<root>/src/lib/resource_paths.py`` so ``<root>`` is two
    # levels up; the sentinel walk covers this regardless.
    found = _find_project_root(here.parent)
    if found is not None:
        return found
    raise FileNotFoundError(
        "could not locate F1 Race Replay project root; "
        "set F1_REPLAY_PROJECT_ROOT to override."
    )


def resolve(*parts: Union[str, os.PathLike]) -> Path:
    """Resolve a path relative to the project root.

    Each part is joined; the result is absolute. If the first
    part is absolute, it is returned as-is.
    """
    if not parts:
        return project_root()
    first = Path(parts[0])
    if first.is_absolute():
        return first.joinpath(*parts[1:]).resolve()
    return project_root().joinpath(*parts).resolve()


# ---------------------------------------------------------------------------
# Canonical resource locations
# ---------------------------------------------------------------------------
def cache_dir() -> Path:
    """Return the FastF1 cache directory (created if missing)."""
    p = resolve(".fastf1-cache")
    p.mkdir(parents=True, exist_ok=True)
    return p


def computed_data_dir() -> Path:
    """Return the computed-data directory (created if missing)."""
    p = resolve("computed_data")
    p.mkdir(parents=True, exist_ok=True)
    return p


def images_dir() -> Path:
    """Return the images / textures directory."""
    return resolve("images")


def resources_dir() -> Path:
    """Return the resources directory (preview images etc.)."""
    return resolve("resources")


__all__ = [
    "project_root",
    "resolve",
    "cache_dir",
    "computed_data_dir",
    "images_dir",
    "resources_dir",
    "_PROJECT_ROOT_SENTINELS",
    "_find_project_root",
]
