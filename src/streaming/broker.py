"""
In-process message broker for telemetry streaming.

The legacy code did this:

    def broadcast(self, data):
        message = json.dumps(data).encode("utf-8")
        for client in self.clients:
            client.sendall(message + b"\\n")

The producer (the render loop) blocks on every client. A single
slow client stalls the entire replay.

This module decouples the producer from network I/O via a
bounded per-subscriber queue:

* The producer calls ``broker.publish(message_type, payload)``
  and returns immediately.
* A single dispatcher thread pops one envelope off the
  per-subscriber queue and writes it to the socket with a
  bounded ``socket.send()`` loop that respects a slow consumer.

The broker also handles the SESSION_INIT pattern: a *static*
payload (track geometry, session identity) is registered once
and re-sent to every new subscriber automatically.

Backpressure policy
-------------------
If a subscriber's queue is full, the broker drops the OLDEST
queued envelope and logs a warning. The most recent frame
update is the most important one. Dropped frames are reported
back to the producer via the ``dropped`` counter on the broker
and on the subscriber.

This module is pure Python; it does NOT touch sockets. The
sockets themselves are owned by ``transport.py`` (PHASE 6).
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from src.streaming.protocol import (
    MessageType,
    ProtocolError,
    PROTOCOL_VERSION,
    check_envelope,
    make_envelope,
)

logger = logging.getLogger("f1_replay.streaming.broker")


DEFAULT_QUEUE_CAPACITY = 64  # frames; with 25 FPS that's 2.5 s of buffer


class Subscriber:
    """One consumer of the broker.

    A subscriber owns a bounded FIFO queue. The dispatcher
    thread pops envelopes off the queue and hands them to the
    registered ``deliver`` callback.

    The ``deliver`` callback is responsible for any network I/O.
    The broker does not know what a "socket" is.
    """
    def __init__(self, subscriber_id: str, *,
                 deliver: Callable[[Dict[str, Any]], None],
                 queue_capacity: int = DEFAULT_QUEUE_CAPACITY):
        self.subscriber_id = subscriber_id
        self.deliver = deliver
        self.queue: Deque[Dict[str, Any]] = deque()
        self.capacity = max(1, int(queue_capacity))
        self.dropped = 0
        self.delivered = 0
        self._lock = threading.Lock()
        self._closed = False

    def enqueue(self, envelope: Dict[str, Any]) -> None:
        with self._lock:
            if self._closed:
                return
            if len(self.queue) >= self.capacity:
                # Drop the oldest; keep the newest.
                self.queue.popleft()
                self.dropped += 1
            self.queue.append(envelope)

    def pop(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self.queue:
                return None
            return self.queue.popleft()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self.queue.clear()


class StreamingBroker:
    """In-process pub-sub for telemetry messages.

    The broker is thread-safe. The producer can call
    ``publish`` from any thread; the dispatcher will deliver
    envelopes to each subscriber's ``deliver`` callback.
    """
    def __init__(self, *, session_id: str,
                 queue_capacity: int = DEFAULT_QUEUE_CAPACITY,
                 static_payloads: Optional[Dict[MessageType, Any]] = None):
        if not session_id:
            raise ValueError("session_id is required")
        self.session_id = session_id
        self.queue_capacity = queue_capacity
        self._subscribers: Dict[str, Subscriber] = {}
        self._subscribers_lock = threading.Lock()
        self._static_payloads: Dict[MessageType, Any] = dict(
            static_payloads or {})
        # Per-type monotonic sequence number.
        self._seq = {mt: 0 for mt in MessageType}
        self._seq_lock = threading.Lock()
        # Total dropped across all subscribers, by type.
        self.dropped_total = 0
        # Statistics
        self.published_total = 0

    # -- subscriber management --------------------------------------
    def add_subscriber(self, subscriber_id: str, *,
                       deliver: Callable[[Dict[str, Any]], None],
                       send_static: bool = True) -> Subscriber:
        sub = Subscriber(subscriber_id, deliver=deliver,
                          queue_capacity=self.queue_capacity)
        with self._subscribers_lock:
            self._subscribers[subscriber_id] = sub
        if send_static:
            for mt, payload in self._static_payloads.items():
                sub.enqueue(self._build_envelope(mt, payload))
        logger.info("subscriber %r attached (queue_capacity=%d)",
                     subscriber_id, self.queue_capacity)
        return sub

    def remove_subscriber(self, subscriber_id: str) -> None:
        with self._subscribers_lock:
            sub = self._subscribers.pop(subscriber_id, None)
        if sub is not None:
            sub.close()
            logger.info("subscriber %r detached (delivered=%d, dropped=%d)",
                         subscriber_id, sub.delivered, sub.dropped)

    def subscriber_count(self) -> int:
        with self._subscribers_lock:
            return len(self._subscribers)

    # -- static payload management ----------------------------------
    def set_static_payload(self, message_type: MessageType, payload: Any) -> None:
        """Register (or replace) a static payload.

        New subscribers automatically receive the registered
        statics on attach. Existing subscribers do NOT
        re-receive — re-broadcast only happens on a new
        attach.
        """
        self._static_payloads[message_type] = payload

    # -- publishing -------------------------------------------------
    def _next_seq(self, message_type: MessageType) -> int:
        with self._seq_lock:
            self._seq[message_type] += 1
            return self._seq[message_type]

    def _build_envelope(self, message_type: MessageType,
                        payload: Any) -> Dict[str, Any]:
        return make_envelope(
            message_type,
            session_id=self.session_id,
            seq=self._next_seq(message_type),
            payload=payload,
        )

    def publish(self, message_type: MessageType, payload: Any) -> Dict[str, Any]:
        """Publish one message to every subscriber. Non-blocking.

        Returns the envelope that was enqueued, primarily for
        tests and the producer's logging.
        """
        env = self._build_envelope(message_type, payload)
        with self._subscribers_lock:
            subs = list(self._subscribers.values())
        for sub in subs:
            sub.enqueue(env)
        self.published_total += 1
        self.dropped_total += sum(s.dropped for s in subs)
        return env

    # -- dispatcher -------------------------------------------------
    def dispatch_once(self, timeout: float = 0.0) -> int:
        """Pop one envelope per subscriber and deliver it.

        Returns the number of envelopes delivered. Call this
        in a tight loop from a dedicated dispatcher thread.
        """
        delivered = 0
        with self._subscribers_lock:
            subs = list(self._subscribers.values())
        for sub in subs:
            env = sub.pop()
            if env is None:
                continue
            try:
                sub.deliver(env)
                sub.delivered += 1
                delivered += 1
            except Exception as exc:
                logger.warning("deliver to %r raised: %s",
                                sub.subscriber_id, exc)
                sub.close()
        return delivered

    # -- introspection ----------------------------------------------
    def stats(self) -> Dict[str, Any]:
        with self._subscribers_lock:
            subs = list(self._subscribers.values())
        return {
            "session_id": self.session_id,
            "subscriber_count": len(subs),
            "published_total": self.published_total,
            "dropped_total": self.dropped_total,
            "subscribers": [
                {
                    "id": s.subscriber_id,
                    "queued": len(s.queue),
                    "delivered": s.delivered,
                    "dropped": s.dropped,
                }
                for s in subs
            ],
        }


__all__ = [
    "DEFAULT_QUEUE_CAPACITY",
    "Subscriber",
    "StreamingBroker",
]
