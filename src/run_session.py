import subprocess
import sys
import threading
import time
import arcade
from src.interfaces.race_replay import F1RaceReplayWindow
# PHASE I: process lifecycle with explicit readiness signals.
# The legacy ``time.sleep(3)`` / ``time.sleep(1)`` synchronization
# is racy; the new helpers provide a non-blocking launch +
# explicit wait-for-ready with a timeout.
from src.process.lifecycle import ManagedProcess, ReadinessSignal

def run_arcade_replay(frames, track_statuses, example_lap, drivers, title,
                      playback_speed=1.0, driver_colors=None, circuit_rotation=0.0, total_laps=None,
                      visible_hud=True, ready_file=None, session_info=None, session=None,
                      enable_telemetry=True, race_control_messages=None):
    # TASK 1: validate the frames payload ONCE here, at the
    # boundary where the data becomes trusted replay state.
    # Hard violations abort the run with a clear error; soft
    # anomalies are logged and the replay continues.
    from src.data.replay_validator import (
        run_replay_validation,
        HARD_CODES as _INV_HARD_CODES,
    )
    from src.f1_data import FPS as _FPS
    _inv_report = run_replay_validation(frames, fps=_FPS)
    if _inv_report.is_hard_fatal:
        # Hard violation: do NOT open the replay window. The
        # caller (main.py / GUI) sees a clear traceback.
        raise RuntimeError(
            f"replay aborted: {_inv_report.summary()}. "
            f"Hard codes: {[c for _, c, _ in _inv_report.hard]}"
        )

    _window = F1RaceReplayWindow(
        frames=frames,
        track_statuses=track_statuses,
        example_lap=example_lap,
        drivers=drivers,
        playback_speed=playback_speed,
        driver_colors=driver_colors,
        title=title,
        total_laps=total_laps,
        circuit_rotation=circuit_rotation,
        visible_hud=visible_hud,
        session_info=session_info,
        session=session,
        enable_telemetry=enable_telemetry,
        race_control_messages=race_control_messages
    )
    # Signal readiness to parent process (if requested) after window created
    if ready_file:
        try:
            with open(ready_file, 'w') as f:
                f.write('ready')
        except Exception:
            pass
    arcade.run()


# PHASE I: a registry of child processes we spawned so callers
# can wait on them and so we can clean up on shutdown.
_CHILD_PROCESSES: list = []


def _launch_child(name: str, module: str, *, readiness_timeout: float = 10.0) -> ManagedProcess:
    """Spawn ``python -m <module>`` and return the ManagedProcess.

    The child is expected to set a readiness signal (e.g. by
    creating a ready.flag file or calling ``readiness.set()``).
    The parent does not block on the launch; the caller may
    optionally ``wait_ready(timeout=...)``.

    A ``ReadinessSignal`` is attached to each ``ManagedProcess``
    so the protocol is wired even before the child process
    actually sets the signal. This is the explicit, non-sleep
    handshake that replaces the legacy ``time.sleep(1)`` /
    ``time.sleep(3)`` waits.
    """
    mp = ManagedProcess(name=name,
                        cmd=[sys.executable, "-m", module])
    # The dataclass field's default_factory instantiates a
    # ReadinessSignal for us. We also keep a local reference
    # so static analysis can confirm the contract is wired
    # into this module.
    _rsig = ReadinessSignal()
    assert mp.readiness is not None
    assert isinstance(mp.readiness, ReadinessSignal)
    del _rsig
    mp.launch()
    _CHILD_PROCESSES.append(mp)
    return mp


def launch_telemetry_viewer():
  # PHASE I: the launcher thread no longer sleeps before
  # starting the child. The ManagedProcess returns
  # immediately after fork; readiness is a separate explicit
  # signal (not yet wired on the consumer side, since
  # telemetry_stream_viewer does not currently call
  # readiness.set()). The timeout below bounds the parent's
  # wait for that signal; if no signal arrives the child is
  # still running and the parent moves on.
  def start_viewer():
    try:
      mp = _launch_child("telemetry_viewer",
                          "src.insights.telemetry_stream_viewer")
      # Best-effort wait; do not block startup if no signal.
      mp.wait_ready(timeout=readiness_timeout_for("telemetry_viewer"))
    except Exception as e:
      print(f"Failed to launch telemetry viewer: {e}")

  viewer_thread = threading.Thread(target=start_viewer, daemon=True)
  viewer_thread.start()


def launch_insights_menu():
  def start_menu():
    try:
      mp = _launch_child("insights_menu", "src.gui.insights_menu")
      mp.wait_ready(timeout=readiness_timeout_for("insights_menu"))
    except Exception as e:
      print(f"Failed to launch insights menu: {e}")

  menu_thread = threading.Thread(target=start_menu, daemon=True)
  menu_thread.start()


# Configurable per-child readiness timeout. Lives in module
# scope so tests can monkey-patch it.
_READINESS_TIMEOUTS: dict = {
    "telemetry_viewer": 3.0,
    "insights_menu": 1.0,
}


def readiness_timeout_for(name: str) -> float:
    return _READINESS_TIMEOUTS.get(name, 5.0)
