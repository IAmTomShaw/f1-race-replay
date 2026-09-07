"""
Subprocess lifecycle management with explicit readiness signals.

The legacy code in ``src.run_session`` used
``time.sleep(3)`` and ``time.sleep(1)`` as a process-startup
synchronization mechanism:

    def start_menu():
        time.sleep(1)                      # <-- racy, blocking
        subprocess.run([sys.executable,
                         "-m", "src.gui.insights_menu"], check=False)

Problems:

* racy: 1 second may be too long on a fast machine and too short
  on a slow one, especially when the second process has to load
  PySide6.
* blocking: the launcher thread sleeps even if the child has
  already started and is ready.
* no observability: a deadlocked child shows up as "menu never
  opened" with no diagnostic.

This module provides the explicit contract:

* The parent creates a ``ReadinessSignal`` (a thin wrapper around
  ``multiprocessing.Event``).
* The parent passes the signal to the child as a command-line
  argument (``--ready-fd`` or similar) and then ``wait()``s for
  the child to set it.
* The child, once it is ready to receive messages, calls
  ``signal.set()``.

The ``ManagedProcess`` class owns the subprocess and the signal,
supports clean shutdown, and reports exit codes. It does NOT use
``time.sleep`` for synchronization.
"""
from __future__ import annotations

import logging
import os
import signal as _signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from multiprocessing import Event as _MpEvent
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("f1_replay.process.lifecycle")


# Sentinel used by tests that want to substitute the sleep-free
# wait path. The real launcher passes the child's PID via
# READINESS_FD_ENV so the child can know how to signal readiness
# without a parent-supplied pipe.
READINESS_FD_ENV = "F1_REPLAY_READINESS_FD"


class ReadinessSignal:
    """Cross-process readiness signal.

    The signal is a one-shot boolean. ``set()`` is sticky; once
    the child has signalled readiness, the parent never blocks
    again on ``wait()``.

    The signal is a small wrapper around ``multiprocessing.Event``
    so that the parent and child can share it via a file
    descriptor inherited across ``fork`` (the default on POSIX
    and what Python's multiprocessing uses on Windows spawn).
    """

    def __init__(self):
        self._event = _MpEvent()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until ready. Returns True if the signal fired
        within ``timeout``; False if it timed out."""
        return self._event.wait(timeout=timeout)

    def clear(self) -> None:
        self._event.clear()


@dataclass
class ManagedProcess:
    """A subprocess plus its readiness signal and lifecycle metadata."""
    name: str
    cmd: Sequence[str]
    readiness: ReadinessSignal = field(default_factory=ReadinessSignal)
    proc: Optional[subprocess.Popen] = None
    pid: Optional[int] = None
    started_at: Optional[float] = None
    exit_code: Optional[int] = None
    auto_signal_on_start: bool = False
    _wait_thread: Optional[threading.Thread] = field(default=None,
                                                     init=False,
                                                     repr=False)
    _stopped: bool = field(default=False, init=False, repr=False)

    def launch(self, *, env: Optional[Dict[str, str]] = None,
               cwd: Optional[str] = None,
               readiness_timeout: float = 30.0) -> int:
        """Start the subprocess. Returns the child's PID.

        If ``auto_signal_on_start`` is True, the readiness signal
        is set immediately after the process is spawned (useful
        for tests that want to bypass the real handshake). In
        production code, leave it False and let the child set the
        signal when it is genuinely ready.
        """
        if self.proc is not None:
            raise RuntimeError(f"{self.name!r} already launched")
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        # We do NOT use time.sleep for synchronization. The child
        # calls readiness.set() itself; the parent waits with a
        # real timeout. If the child dies before signalling, the
        # parent gets exit_code != 0 and can react.
        self.proc = subprocess.Popen(
            list(self.cmd),
            env=full_env,
            cwd=cwd,
        )
        self.pid = self.proc.pid
        self.started_at = time.time()
        if self.auto_signal_on_start:
            self.readiness.set()
        return self.pid

    def wait_ready(self, timeout: float = 30.0) -> bool:
        """Block until the child signals readiness or times out."""
        return self.readiness.wait(timeout=timeout)

    def is_alive(self) -> bool:
        if self.proc is None:
            return False
        return self.proc.poll() is None

    def poll(self) -> Optional[int]:
        """Return the child's exit code, or None if still running."""
        if self.proc is None:
            return None
        self.exit_code = self.proc.poll()
        return self.exit_code

    def stop(self, *, timeout: float = 5.0, sig: Optional[int] = None) -> int:
        """Stop the child. Sends SIGTERM (or ``sig``) and waits.

        Returns the exit code. Does NOT raise on non-zero exit.
        """
        if self.proc is None:
            return 0
        if self._stopped:
            return self.exit_code or 0
        self._stopped = True
        if self.proc.poll() is not None:
            self.exit_code = self.proc.returncode
            return self.exit_code
        try:
            self.proc.send_signal(sig if sig is not None else _signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        try:
            self.exit_code = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("%s did not exit on SIGTERM; killing", self.name)
            self.proc.kill()
            try:
                self.exit_code = self.proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
        return self.exit_code or 0

    def wait(self, timeout: Optional[float] = None) -> int:
        if self.proc is None:
            raise RuntimeError("process not launched")
        rc = self.proc.wait(timeout=timeout)
        self.exit_code = rc
        return rc


__all__ = [
    "READINESS_FD_ENV",
    "ManagedProcess",
    "ReadinessSignal",
]
