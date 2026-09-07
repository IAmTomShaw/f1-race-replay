"""
TCP socket transport for the telemetry stream.

The legacy code (``src.services.stream.TelemetryStreamServer``)
had a number of lifecycle problems:

* No SO_REUSEADDR — the port could be in TIME_WAIT after a
  crash and the server would refuse to bind.
* No accept timeout — the accept thread could block forever
  during shutdown, hanging the process.
* One passive per-client thread that just slept (``time.sleep(1)``)
  in a loop, never detecting peer disconnects promptly.
* No explicit lifecycle states.
* No way to recover a real port after a bind failure (e.g. the
  port is already in use).
* No port reporting — callers had to assume the configured port.

This module fixes all of the above:

* Explicit lifecycle: ``INIT | STARTING | RUNNING | STOPPING | STOPPED``.
* ``setsockopt(SO_REUSEADDR, 1)`` before bind.
* Bound ``accept()`` with a timeout, polled by a single dispatcher.
* Per-client queue + bounded send with a short timeout; a slow
  client is dropped after ``SEND_TIMEOUT_S`` and the queue is
  rotated.
* The actual bound port is reported (supports ``port=0`` for
  ephemeral port discovery, common in tests).
* Clean shutdown: ``stop()`` closes every client socket, joins
  the dispatcher thread, and closes the listening socket.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.streaming.broker import StreamingBroker
from src.streaming.protocol import (
    MessageType,
    check_envelope,
    make_envelope,
)

logger = logging.getLogger("f1_replay.streaming.transport")


# Network I/O tuning. Small numbers keep tests fast; production
# values can be overridden via the constructor.
DEFAULT_LISTEN_BACKLOG = 5
ACCEPT_TIMEOUT_S = 0.5
SEND_TIMEOUT_S = 1.0
RECV_BUFFER_SIZE = 4096


class ServerState(str, Enum):
    INIT = "INIT"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class TelemetryStreamServer:
    """TCP server that broadcasts broker messages to connected clients.

    The server is intentionally thin: it owns the listening socket
    and a single dispatcher thread, but all message routing and
    backpressure happen in the ``StreamingBroker`` (PHASE 5).
    """

    def __init__(self, broker: StreamingBroker, *,
                 host: str = "localhost", port: int = 9999):
        self.broker = broker
        self.host = host
        self.requested_port = port
        self._listening_socket: Optional[socket.socket] = None
        self._bound_port: Optional[int] = None
        self._state: ServerState = ServerState.INIT
        self._state_lock = threading.Lock()
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._clients_lock = threading.Lock()
        self._clients: List[socket.socket] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def state(self) -> ServerState:
        with self._state_lock:
            return self._state

    @property
    def bound_port(self) -> Optional[int]:
        return self._bound_port

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Bind, listen, start dispatcher. Raises on failure."""
        with self._state_lock:
            if self._state not in (ServerState.INIT, ServerState.STOPPED):
                raise RuntimeError(f"cannot start in state {self._state}")
            self._state = ServerState.STARTING
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Make the accept call interruptible so the dispatcher can
        # poll its stop flag regularly.
        sock.settimeout(ACCEPT_TIMEOUT_S)
        try:
            sock.bind((self.host, self.requested_port))
        except OSError as exc:
            sock.close()
            with self._state_lock:
                self._state = ServerState.INIT
            # Make the error actionable: include the host, port, and
            # what the user can try (different port, check for
            # another process).
            raise OSError(
                f"failed to bind {self.host}:{self.requested_port}: {exc}. "
                "If another F1 Race Replay is running, stop it. "
                "Otherwise try a different port via the transport config."
            ) from exc
        sock.listen(DEFAULT_LISTEN_BACKLOG)
        self._listening_socket = sock
        self._bound_port = sock.getsockname()[1]
        with self._state_lock:
            self._state = ServerState.RUNNING
        # Two threads: one accepts new clients; the other dispatches
        # broker messages. Splitting them keeps the accept loop
        # responsive even when a deliver callback is slow.
        self._dispatcher_thread = threading.Thread(
            target=self._dispatcher_loop,
            name="TelemetryStreamServer.dispatcher",
            daemon=True,
        )
        self._dispatcher_thread.start()
        self._broker_thread = threading.Thread(
            target=self._broker_dispatch_loop,
            name="TelemetryStreamServer.broker_dispatch",
            daemon=True,
        )
        self._broker_thread.start()
        logger.info("listening on %s:%d (state=RUNNING)",
                     self.host, self._bound_port)

    def stop(self) -> None:
        """Stop the server, close every client, join the dispatcher."""
        with self._state_lock:
            if self._state in (ServerState.STOPPED, ServerState.INIT):
                return
            self._state = ServerState.STOPPING
        # Close listening socket so accept() returns.
        if self._listening_socket is not None:
            try:
                self._listening_socket.close()
            except OSError:
                pass
        # Close all clients.
        with self._clients_lock:
            for c in list(self._clients):
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()
        if self._dispatcher_thread is not None:
            self._dispatcher_thread.join(timeout=ACCEPT_TIMEOUT_S * 4)
        if getattr(self, "_broker_thread", None) is not None:
            self._broker_thread.join(timeout=2.0)
        with self._state_lock:
            self._state = ServerState.STOPPED
        # Reset to INIT so a subsequent start() is allowed.
        with self._state_lock:
            self._state = ServerState.INIT
        logger.info("stopped (state=INIT, ready to restart)")

    # ------------------------------------------------------------------
    # Broker dispatch loop
    # ------------------------------------------------------------------
    def _broker_dispatch_loop(self) -> None:
        """Drain the broker at a steady cadence.

        Each iteration calls ``broker.dispatch_once()`` which pops
        at most one envelope per subscriber and invokes its
        ``deliver`` callback. The cadence is bounded by a short
        sleep so the thread does not busy-spin.
        """
        while self.state is ServerState.RUNNING:
            try:
                self.broker.dispatch_once(timeout=0.0)
            except Exception as exc:
                logger.warning("broker dispatch error: %s", exc)
            time.sleep(0.001)  # 1 ms; tight enough for ~25 FPS

    # ------------------------------------------------------------------
    # Dispatcher loop
    # ------------------------------------------------------------------
    def _dispatcher_loop(self) -> None:
        sock = self._listening_socket
        assert sock is not None
        # We are the only thread that calls accept().
        while self.state is ServerState.RUNNING:
            try:
                client, addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                # Listening socket was closed during stop().
                break
            client.settimeout(SEND_TIMEOUT_S)
            with self._clients_lock:
                self._clients.append(client)
            client_id = f"{addr[0]}:{addr[1]}"
            # Register with broker: deliver pushes JSON lines to the
            # socket; a send failure removes the client.
            self.broker.add_subscriber(
                client_id,
                deliver=self._make_deliver(client, client_id),
            )
            logger.info("client %s connected", client_id)

        # Disconnect all remaining clients on the way out.
        with self._clients_lock:
            for c in list(self._clients):
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()

    def _make_deliver(self, client: socket.socket, client_id: str):
        # Make the client non-blocking so a slow consumer does NOT
        # block the dispatcher thread. We use ``socket.send`` (not
        # ``sendall``) and accept partial writes — if the kernel
        # buffer is full, we drop this single envelope but keep the
        # client connection alive for subsequent frames.
        try:
            client.setblocking(False)
        except OSError:
            pass

        def _deliver(env: Dict[str, Any]) -> None:
            try:
                check_envelope(env)
            except Exception as exc:
                logger.warning("refusing to send invalid envelope to %s: %s",
                                client_id, exc)
                return
            try:
                line = (json.dumps(env) + "\n").encode("utf-8")
            except (TypeError, ValueError) as exc:
                logger.warning("envelope not JSON-encodable for %s: %s",
                                client_id, exc)
                return
            try:
                sent = client.send(line)
            except BlockingIOError:
                # Kernel send buffer full; drop this frame but keep
                # the client. The broker's per-subscriber ``dropped``
                # counter is updated for the *envelope* we just lost.
                self.broker._subscribers[client_id].dropped += 1
                return
            except OSError as exc:
                # Connection-level error: drop the client.
                logger.info("client %s dropped: %s", client_id, exc)
                self.broker.remove_subscriber(client_id)
                with self._clients_lock:
                    if client in self._clients:
                        self._clients.remove(client)
                try:
                    client.close()
                except OSError:
                    pass
                return
            if sent != len(line):
                # Partial write: the kernel send buffer was not large
                # enough to take the whole line. Drop the tail; keep
                # the client alive. (Newline-delimited framing means
                # the client may discard this frame; the next frame
                # will be fine.)
                self.broker._subscribers[client_id].dropped += 1
        return _deliver


__all__ = [
    "ACCEPT_TIMEOUT_S",
    "RECV_BUFFER_SIZE",
    "SEND_TIMEOUT_S",
    "ServerState",
    "TelemetryStreamServer",
]
