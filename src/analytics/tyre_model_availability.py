"""
Tyre model — availability contract.

The legacy Bayesian tyre model in ``src.bayesian_tyre_model`` is
in early development. The project specification (PHASE 11) is
explicit:

    "Replace placeholder outputs such as:
        actual_delta = 0
        overdriving = False
     with one of:
        A. actual implementation
        B. clearly marked 'not available'
     Never present placeholder values as real analytics."

This module provides the *contract* the Bayesian model must
conform to. It does NOT replace the model; it provides the
result-shape that callers (the UI, the insights menu, the
streaming protocol) can rely on. Any code path that returns a
``TyreModelResult`` with ``available=False`` MUST be respected
by callers; they must show "not available" in the UI rather
than rendering the placeholder values.

A regression test asserts that placeholder zero values are never
returned when the model has not been run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TyreModelResult:
    """A single tyre-model output for one (driver, stint, lap).

    The ``available`` field is the contract. When False, every
    numeric field MUST be ``None``; the UI must render "not
    available" and never render the placeholder.
    """
    available: bool
    reason: str = ""  # human-readable explanation when available=False

    # Pace fields
    baseline_pace: Optional[float] = None      # seconds/lap
    expected_pace: Optional[float] = None      # seconds/lap at current tyre age
    actual_delta: Optional[float] = None       # actual - expected, in seconds
    credible_low: Optional[float] = None       # 5% credible interval lower
    credible_high: Optional[float] = None      # 95% credible interval upper

    # Driver feedback
    overdriving: Optional[bool] = None         # pace below credible interval
    tyre_age_laps: Optional[int] = None        # current tyre age in laps
    compound: Optional[str] = None             # e.g. "MEDIUM"

    # Metadata
    notes: Dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> Dict[str, Any]:
        """Return a dict safe for UI / streaming consumption.

        When ``available`` is False, every numeric field is
        replaced with ``None`` and a ``not_available_reason``
        string is included. Callers MUST check the
        ``available`` flag.
        """
        if not self.available:
            return {
                "available": False,
                "not_available_reason": self.reason or "not available",
                "baseline_pace": None,
                "expected_pace": None,
                "actual_delta": None,
                "credible_low": None,
                "credible_high": None,
                "overdriving": None,
                "tyre_age_laps": None,
                "compound": None,
            }
        return {
            "available": True,
            "baseline_pace": self.baseline_pace,
            "expected_pace": self.expected_pace,
            "actual_delta": self.actual_delta,
            "credible_low": self.credible_low,
            "credible_high": self.credible_high,
            "overdriving": self.overdriving,
            "tyre_age_laps": self.tyre_age_laps,
            "compound": self.compound,
        }


def not_available(reason: str) -> TyreModelResult:
    """Convenience: build an unavailable result."""
    return TyreModelResult(available=False, reason=reason)


def available_result(*, baseline_pace: float, expected_pace: float,
                      actual_delta: float, credible_low: float,
                      credible_high: float, overdriving: bool,
                      tyre_age_laps: int, compound: str,
                      notes: Optional[Dict[str, Any]] = None,
                      ) -> TyreModelResult:
    """Convenience: build a fully-populated available result."""
    return TyreModelResult(
        available=True,
        baseline_pace=baseline_pace,
        expected_pace=expected_pace,
        actual_delta=actual_delta,
        credible_low=credible_low,
        credible_high=credible_high,
        overdriving=overdriving,
        tyre_age_laps=tyre_age_laps,
        compound=compound,
        notes=notes or {},
    )


# ---------------------------------------------------------------------------
# Legacy placeholder detection
# ---------------------------------------------------------------------------
# The legacy tyre-degradation-integration layer returns
# ``actual_delta = 0`` and ``overdriving = False`` as placeholders
# when the underlying model has not been run. This helper flags
# those placeholders so the UI layer can replace them with a
# "not available" indicator rather than rendering 0 / False.
#
# Callers that have the legacy model wired in should:
#   1. Compute their result.
#   2. Run ``is_placeholder(...)``.
#   3. If True, wrap the output in ``not_available(reason)``
#      instead of presenting the placeholder.
# ---------------------------------------------------------------------------
PLACEHOLDER_ACTUAL_DELTA = 0.0
PLACEHOLDER_OVERDRIVING = False


def is_placeholder(actual_delta: Any, overdriving: Any) -> bool:
    """Return True iff the values look like the legacy placeholder."""
    try:
        delta_is_zero = (float(actual_delta) == 0.0)
    except (TypeError, ValueError):
        delta_is_zero = False
    overdriving_is_false = (overdriving is False)
    return delta_is_zero and overdriving_is_false


def wrap_legacy(actual_delta: Any, overdriving: Any,
                *args: Any, reason: str = "model not run",
                **kwargs: Any) -> TyreModelResult:
    """Wrap a legacy tyre-model output in a TyreModelResult.

    If the values look like placeholders, return an
    ``available=False`` result. Otherwise, return an
    ``available=True`` result with the values.
    """
    if is_placeholder(actual_delta, overdriving):
        return not_available(reason)
    return available_result(
        actual_delta=float(actual_delta),
        overdriving=bool(overdriving),
        *args, **kwargs,
    )


__all__ = [
    "TyreModelResult",
    "not_available",
    "available_result",
    "is_placeholder",
    "wrap_legacy",
    "PLACEHOLDER_ACTUAL_DELTA",
    "PLACEHOLDER_OVERDRIVING",
]
