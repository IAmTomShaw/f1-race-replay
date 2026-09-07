"""
Versioned, atomic cache for computed telemetry.

The legacy code in ``src.f1_data`` writes a pickle directly to
the target path:

    with open(cache_file, "wb") as f:
        pickle.dump(payload, f)

Problems:

* No version envelope. Any change to the algorithm silently
  invalidates the cache contents; users must remember
  ``--refresh-data`` after every release.
* Non-atomic: a crash mid-write leaves a half-written file.
  Subsequent reads fail with an opaque traceback.
* No schema documentation. Consumers have to guess what keys
  are present.

This module provides a small wrapper:

* ``CACHE_SCHEMA_VERSION``     : int, bump on any cache-shape change.
* ``APP_VERSION``              : string, included in the envelope.
* ``envelope_for(...)``        : wraps a payload with metadata.
* ``check_envelope(...)``      : raises ``CacheSchemaMismatch`` on incompatibility.
* ``read_cache(path)``         : returns payload, or raises one of:
                                  - ``FileNotFoundError``
                                  - ``CacheSchemaMismatch``
                                  - ``CacheCorrupted``
* ``write_cache_atomic(path, payload, metadata=None)`` : atomic write.

Atomic write uses ``tempfile.NamedTemporaryFile`` in the same
directory, ``f.flush() + os.fsync()``, then ``os.replace(tmp, target)``.
On any failure the temp file is cleaned up.
"""
from __future__ import annotations

import logging
import os
import pickle
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("f1_replay.cache")


# Bump this on any change to the cache shape. Independent of the
# application version so that a bug-fix release that does not touch
# the cache shape does not invalidate every user's cache.
CACHE_SCHEMA_VERSION = 1

# Application version string. Updated by the release process. The
# default "dev" lets developers iterate without bumping the cache
# schema, but production releases should set this to a real version.
APP_VERSION = "dev"


class CacheError(Exception):
    """Base for all cache-related errors."""


class CacheSchemaMismatch(CacheError):
    """The cache file's schema version does not match the current
    code. Caller should recompute and re-write."""


class CacheCorrupted(CacheError):
    """The cache file could not be unpickled. Caller should
    re-compute and re-write."""


def envelope_for(payload: Any, *,
                 session_id: Optional[str] = None,
                 session_type: Optional[str] = None,
                 year: Optional[int] = None,
                 round_number: Optional[int] = None,
                 telemetry_fps: Optional[float] = None,
                 extra: Optional[Dict[str, Any]] = None,
                 app_version: str = APP_VERSION,
                 schema_version: int = CACHE_SCHEMA_VERSION,
                 ) -> Dict[str, Any]:
    """Wrap ``payload`` in a versioned envelope.

    The returned dict is what should be pickled to disk. The
    ``__cache__`` key separates envelope metadata from the actual
    payload (which is stored under ``"payload"``).
    """
    meta = {
        "schema_version": int(schema_version),
        "app_version": str(app_version),
        "session_id": session_id,
        "session_type": session_type,
        "year": year,
        "round_number": round_number,
        "telemetry_fps": telemetry_fps,
    }
    if extra:
        meta["extra"] = dict(extra)
    return {
        "__cache__": True,
        "schema_version": int(schema_version),
        "app_version": str(app_version),
        "metadata": meta,
        "payload": payload,
    }


def check_envelope(env: Any) -> None:
    """Raise ``CacheSchemaMismatch`` if the envelope is incompatible.

    The check is permissive: missing keys are warned about but
    do not raise. Bumping ``CACHE_SCHEMA_VERSION`` is the way to
    force a recompute.
    """
    if not isinstance(env, dict):
        raise CacheSchemaMismatch(
            f"expected dict envelope, got {type(env).__name__}")
    if not env.get("__cache__"):
        raise CacheSchemaMismatch("envelope missing __cache__ flag")
    cached_schema = env.get("schema_version")
    if cached_schema != CACHE_SCHEMA_VERSION:
        raise CacheSchemaMismatch(
            f"cache schema {cached_schema} != current {CACHE_SCHEMA_VERSION}")


def read_cache(path: str) -> Any:
    """Read and validate a cache file.

    Returns the unwrapped payload. Raises:
    * ``FileNotFoundError``  -- no file at ``path``.
    * ``CacheSchemaMismatch`` -- envelope invalid or schema version
      different.
    * ``CacheCorrupted``     -- pickle could not be loaded.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    try:
        with open(path, "rb") as f:
            env = pickle.load(f)
    except (pickle.UnpicklingError, EOFError, ValueError,
            ImportError, AttributeError) as exc:
        raise CacheCorrupted(
            f"cache file at {path!r} is corrupted: {exc}") from exc
    check_envelope(env)
    return env.get("payload")


def write_cache_atomic(path: str, payload: Any, *,
                       metadata: Optional[Dict[str, Any]] = None,
                       schema_version: int = CACHE_SCHEMA_VERSION,
                       app_version: str = APP_VERSION,
                       protocol: int = pickle.HIGHEST_PROTOCOL) -> None:
    """Write ``payload`` to ``path`` atomically.

    The file is first written to a temp file in the same directory,
    fsync'd, then ``os.replace``-d onto the target. If anything goes
    wrong, the temp file is removed and the original file is left
    untouched.
    """
    env = envelope_for(
        payload,
        schema_version=schema_version,
        app_version=app_version,
        **(metadata or {}),
    )
    target_dir = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(target_dir, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".cache.", suffix=".tmp", dir=target_dir,
    )
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            pickle.dump(env, f, protocol=protocol)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError as e:
                # fsync may fail on some filesystems; log and continue.
                logger.debug("fsync failed on %s: %s", tmp_path, e)
        os.replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup of the temp file.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


@dataclass
class CacheKey:
    """Structured identity of a cache entry."""
    event_name: str
    session_type: str
    year: int
    round_number: int
    suffix: str = "race"

    def to_filename(self) -> str:
        safe_event = self.event_name.replace(" ", "_")
        return f"{safe_event}_{self.suffix}_telemetry.pkl"


def is_cache_compatible(path: str) -> bool:
    """Return True iff the cache at ``path`` exists and is compatible.

    Used by callers that want to *check* before trying a full read.
    """
    if not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as f:
            env = pickle.load(f)
    except Exception:
        return False
    try:
        check_envelope(env)
        return True
    except CacheSchemaMismatch:
        return False


__all__ = [
    "APP_VERSION",
    "CACHE_SCHEMA_VERSION",
    "CacheError",
    "CacheSchemaMismatch",
    "CacheCorrupted",
    "envelope_for",
    "check_envelope",
    "read_cache",
    "write_cache_atomic",
    "is_cache_compatible",
    "CacheKey",
]
