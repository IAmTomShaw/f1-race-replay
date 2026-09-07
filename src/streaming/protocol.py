"""
Telemetry streaming protocol — message contract.

The legacy code in ``src.services.stream`` defines no protocol
envelope: every frame is just ``json.dumps(data) + b"\\n"``. There
is no way to tell:

* a SESSION_INIT message from a FRAME_UPDATE
* a frame from the *current* session from a stale one (no session ID)
* the schema version of the producer from the consumer's expectation
* whether a payload was dropped or out-of-order

This module defines the wire envelope. The actual on-the-wire
serialization remains JSON-with-newline-delimited messages (for
debuggability and inter-language compatibility), but every
message is wrapped in an envelope:

    {
        "type": "FRAME_UPDATE",     // MessageType
        "version": 1,                // PROTOCOL_VERSION
        "session_id": "...",         // unique per replay session
        "seq": 42,                   // monotonic per-type
        "ts": 1234567890.123,        // wall-clock at send
        "payload": { ... }           // type-specific
    }

Message types
-------------
SESSION_INIT        : sent once on connect. Carries session identity,
                      schema version, list of driver codes, total
                      frames, etc. Consumers use this to size their
                      UI before any FRAME_UPDATE arrives.
TRACK_GEOMETRY      : sent once on connect. Static track shape. Never
                      re-sent unless the consumer explicitly requests
                      a re-send (heartbeat ack with seq 0).
ANALYTICS_SNAPSHOT  : low-frequency aggregate stats (e.g. tyre
                      model results, leaderboard). Sent at most every
                      ANALYTICS_INTERVAL_MS.
FRAME_UPDATE        : per-frame telemetry. Sent at replay rate.
CONTROL_STATE       : playback control changes (pause, speed, seek).
SESSION_END         : sent once when the replay terminates cleanly.
ERROR               : producer-side error. Payload is a string.
HEARTBEAT           : keep-alive with last-seen seq. Sent every
                      HEARTBEAT_INTERVAL_MS when no other traffic.

Versioning
----------
Bumping ``PROTOCOL_VERSION`` is a breaking change: any consumer
that does not know the new version must disconnect. The
``check_envelope`` helper raises ``ProtocolVersionMismatch``.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


PROTOCOL_VERSION = 1


class MessageType(str, Enum):
    SESSION_INIT = "SESSION_INIT"
    TRACK_GEOMETRY = "TRACK_GEOMETRY"
    ANALYTICS_SNAPSHOT = "ANALYTICS_SNAPSHOT"
    FRAME_UPDATE = "FRAME_UPDATE"
    CONTROL_STATE = "CONTROL_STATE"
    SESSION_END = "SESSION_END"
    ERROR = "ERROR"
    HEARTBEAT = "HEARTBEAT"


class ProtocolError(Exception):
    """Base for protocol-level errors."""


class ProtocolVersionMismatch(ProtocolError):
    """The producer's protocol version is incompatible."""


class ProtocolSchemaError(ProtocolError):
    """The envelope is missing required fields or has the wrong type."""


REQUIRED_FIELDS = ("type", "version", "session_id", "seq", "ts", "payload")


def make_envelope(message_type: MessageType,
                  *,
                  session_id: str,
                  seq: int,
                  payload: Any,
                  version: int = PROTOCOL_VERSION,
                  ts: Optional[float] = None,
                  ) -> Dict[str, Any]:
    """Build a wire envelope for one message."""
    if not session_id:
        raise ValueError("session_id is required")
    if seq < 0:
        raise ValueError("seq must be non-negative")
    if ts is None:
        import time
        ts = time.time()
    return {
        "type": message_type.value,
        "version": int(version),
        "session_id": session_id,
        "seq": int(seq),
        "ts": float(ts),
        "payload": payload,
    }


def check_envelope(env: Any) -> None:
    """Validate an envelope. Raises ``ProtocolError`` on failure."""
    if not isinstance(env, dict):
        raise ProtocolSchemaError(
            f"envelope must be dict, got {type(env).__name__}")
    for f in REQUIRED_FIELDS:
        if f not in env:
            raise ProtocolSchemaError(f"envelope missing field {f!r}")
    try:
        msg_type = MessageType(env["type"])
    except ValueError as exc:
        raise ProtocolSchemaError(
            f"unknown message type {env['type']!r}") from exc
    if env["version"] != PROTOCOL_VERSION:
        raise ProtocolVersionMismatch(
            f"protocol version {env['version']} != current {PROTOCOL_VERSION}")


__all__ = [
    "PROTOCOL_VERSION",
    "MessageType",
    "ProtocolError",
    "ProtocolVersionMismatch",
    "ProtocolSchemaError",
    "REQUIRED_FIELDS",
    "make_envelope",
    "check_envelope",
]
