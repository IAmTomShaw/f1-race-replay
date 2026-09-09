"""
Canonical telemetry units and a one-place normalizer.

The legacy code resamples telemetry in two places (race and
qualifying) and disagrees about the unit of ``brake``: the race
path keeps the FastF1 raw value (0 when not braking, 100 when
braking) and the qualifying path multiplies a 0/1 boolean by
100 to "match the throttle scale". A downstream consumer that
re-scales by 100 again will see ``brake == 10000`` (out of
range) and one that does not will see ``throttle=80`` next to
``brake=1`` (out of proportion).

This module fixes the contract. Every channel has a single
canonical unit; every producer and every consumer goes through
``normalize_frame``.

Canonical units
---------------
- ``speed``       : km/h
- ``throttle``    : 0..100 (percent)
- ``brake``       : 0..100 (boolean * 100, same as throttle scale)
- ``gear``        : integer 1..8 (or 0 for neutral / -1 for reverse)
- ``drs``         : integer 0/1/2/3/... (FastF1 returns >= 10 when open)
- ``distance``    : metres
- ``rel_dist``    : 0..1 (fraction of current lap)
- ``lap``         : integer 1..N
- ``tyre_life``   : laps
- ``time``        : seconds

The function ``to_canonical`` accepts a dict of channel -> value
(e.g. a single row from a FastF1 telemetry DataFrame) and returns
a new dict with the same keys but values guaranteed to be in
canonical units. Unknown channels are passed through unchanged
(treated as already-canonical). NaN / None values are passed
through.
"""
from __future__ import annotations

import math
from typing import Any, Dict


# Public constant so docs and tests can refer to it.
CANONICAL_UNITS: Dict[str, str] = {
    "speed": "km/h",
    "throttle": "percent (0..100)",
    "brake": "percent (0..100)",
    "gear": "integer (1..8; 0 = neutral; -1 = reverse)",
    "drs": "integer (>=10 means open)",
    "distance": "metres",
    "rel_dist": "fraction (0..1)",
    "lap": "integer (1..N)",
    "tyre_life": "laps",
    "time": "seconds",
    "x": "metres (track-local)",
    "y": "metres (track-local)",
    "z": "metres (track-local)",
}


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isnan(f) or math.isinf(f)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _coerce_int(v: Any) -> int:
    if v is None:
        return 0
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def to_canonical(channel: str, value: Any) -> Any:
    """Normalize a single channel value to its canonical unit.

    Unknown channels are returned unchanged. Missing values
    (None / NaN / inf) are returned unchanged.
    """
    if _is_missing(value):
        return value
    name = channel.lower()
    if name == "brake":
        # FastF1 returns either a boolean (0/1) or a percent. If the
        # value is in [0, 1] we scale to percent; if it is already
        # in [0, 100] we leave it.
        v = float(value)
        if 0.0 <= v <= 1.0:
            return v * 100.0
        if 1.0 < v <= 100.0:
            return v
        # Anything else is suspect; clamp to 0..100.
        return _clamp(v, 0.0, 100.0)
    if name == "throttle":
        return _clamp(float(value), 0.0, 100.0)
    if name == "speed":
        return float(value)  # already in km/h per FastF1 docs
    if name == "distance":
        return float(value)
    if name == "rel_dist":
        return _clamp(float(value), 0.0, 1.0)
    if name == "lap":
        return _coerce_int(value)
    if name == "tyre_life":
        return _coerce_int(value)
    if name in ("gear", "drs", "x", "y", "z", "time"):
        return value
    return value


def normalize_frame_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict with every channel normalized to its
    canonical unit. The original dict is not modified."""
    return {k: to_canonical(k, v) for k, v in entry.items()}


def normalize_frame(frame: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new frame with each driver entry normalized."""
    drivers = frame.get("drivers") or {}
    new_drivers = {code: normalize_frame_entry(d) for code, d in drivers.items()}
    out = dict(frame)
    out["drivers"] = new_drivers
    return out


__all__ = [
    "CANONICAL_UNITS",
    "to_canonical",
    "normalize_frame_entry",
    "normalize_frame",
]
