"""
Structured logging for F1 Race Replay.

The legacy code uses ``print(...)`` for most diagnostics and
``logging.getLogger("fastf1")`` for one specific case. There is
no per-subsystem logger, no consistent format, and no way for
operators to silence or escalate individual subsystems.

This module provides a single ``configure_logging`` function
that sets up hierarchical loggers with a consistent format.
Subsystems (e.g. ``f1_replay.cache``, ``f1_replay.streaming``)
log into their own logger and inherit level / format from the
root ``f1_replay`` logger.

Usage:
    from src.lib.logging_setup import configure_logging, get_logger
    configure_logging(level="INFO")
    log = get_logger("cache")
    log.info("loaded cache", extra={"session": session_id})

The protocol forbids:
    except Exception:
        pass

Catch specific exceptions and log them. The helper
``log_exception`` wraps an exception with a useful context dict.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional


# Project-level logger namespace. All subsystems log under
# ``f1_replay.*``.
ROOT_LOGGER_NAME = "f1_replay"

# Standard format: timestamp, level, logger, message.
DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"

# Subsystem loggers known to the project. Adding a new subsystem?
# Add an entry here so operators can find it in one place.
SUBSYSTEMS: tuple[str, ...] = (
    "f1_replay.cache",
    "f1_replay.streaming",
    "f1_replay.streaming.broker",
    "f1_replay.streaming.transport",
    "f1_replay.safety_car",
    "f1_replay.process",
    "f1_replay.diagnostics",
)


_configured = False


def configure_logging(*, level: str = "WARNING",
                       fmt: Optional[str] = None,
                       stream=None) -> None:
    """Configure the ``f1_replay`` logger hierarchy.

    Idempotent. Calling twice replaces the existing handler.
    """
    global _configured
    root = logging.getLogger(ROOT_LOGGER_NAME)
    # Remove existing handlers we previously installed.
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(fmt or DEFAULT_FORMAT))
    root.addHandler(handler)
    try:
        root.setLevel(getattr(logging, level.upper()))
    except AttributeError:
        root.setLevel(logging.WARNING)
    # Pre-create the subsystem loggers so they appear in
    # ``logging.Logger.manager.loggerDict`` even before first use.
    for name in SUBSYSTEMS:
        logging.getLogger(name)
    _configured = True


def get_logger(subsystem: Optional[str] = None) -> logging.Logger:
    """Return a logger under ``f1_replay``.

    ``subsystem`` is appended to the root name, e.g.
    ``get_logger("cache")`` returns ``f1_replay.cache``.
    """
    if subsystem:
        return logging.getLogger(f"{ROOT_LOGGER_NAME}.{subsystem}")
    return logging.getLogger(ROOT_LOGGER_NAME)


def log_exception(log: logging.Logger, msg: str, *,
                 exc: BaseException, level: int = logging.ERROR,
                 context: Optional[Dict[str, Any]] = None) -> None:
    """Log an exception with structured context.

    The ``context`` dict is included as ``extra=`` so the
    formatter can include it if desired. We deliberately do NOT
    re-raise; callers handle that.
    """
    extra: Dict[str, Any] = {
        "exc_type": exc.__class__.__name__,
        "exc_message": str(exc),
    }
    if context:
        extra.update(context)
    log.log(level, msg + ": %s", exc, extra=extra)


__all__ = [
    "ROOT_LOGGER_NAME",
    "DEFAULT_FORMAT",
    "SUBSYSTEMS",
    "configure_logging",
    "get_logger",
    "log_exception",
]
