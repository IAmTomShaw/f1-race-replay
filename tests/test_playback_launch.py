import os
from pathlib import Path
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("fastf1")
from PySide6.QtWidgets import QApplication
import src.gui.race_selection as selection


@pytest.fixture(scope="module")
def application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def playback(tmp_path, monkeypatch, application):
    monkeypatch.setattr(selection.RaceSelectionWindow, "_setup_ui", lambda _: None)
    monkeypatch.setattr(selection.QThread, "start", lambda worker: worker.result.emit(object()))
    monkeypatch.setattr(selection.tempfile, "gettempdir", lambda: str(tmp_path))
    message = Mock()
    monkeypatch.setattr(selection.QMessageBox, "critical", message)
    process = Mock()
    process.poll.return_value = None
    launch = Mock(return_value=process)
    monkeypatch.setattr(selection.subprocess, "Popen", launch)
    window = selection.RaceSelectionWindow()

    def start():
        window._on_session_button_clicked({"year": 2026, "round_number": 16}, "Race")

    yield SimplePlayback(window, start, launch, process, message, tmp_path)
    for timer in window.findChildren(selection.QTimer):
        timer.stop()
    window.close()
    window.deleteLater()


class SimplePlayback:
    def __init__(self, window, start, launch, process, message, directory):
        self.window = window
        self.start = start
        self.launch = launch
        self.process = process
        self.message = message
        self.directory = directory

    @property
    def ready_path(self):
        command = self.launch.call_args.args[0]
        return Path(command[command.index("--ready-file") + 1])

    @property
    def log_path(self):
        return Path(self.launch.call_args.kwargs["stderr"].name)

    def poll(self):
        self.window._ready_timer.timeout.emit()


def test_failed_launch_closes_handle_and_removes_log(playback):
    playback.launch.side_effect = OSError("injected launch failure")
    playback.start()
    assert playback.launch.call_args.kwargs["stderr"].closed
    assert not list(playback.directory.iterdir())
    assert "injected launch failure" in playback.message.call_args.args[2]


def test_running_playback_keeps_log_until_exit(playback):
    playback.start()
    assert playback.launch.call_args.kwargs["stderr"].closed
    playback.ready_path.write_text("ready")
    playback.poll()
    assert not playback.ready_path.exists()
    assert playback.log_path.exists()
    assert playback.window._ready_timer.isActive()
    playback.process.poll.return_value = 0
    playback.poll()
    assert not playback.log_path.exists()
    assert not playback.window._ready_timer.isActive()
    playback.message.assert_not_called()


def test_early_exit_displays_traceback_tail_and_cleans_log(playback):
    playback.start()
    playback.log_path.write_bytes(b"ignored first line\n" * 20 + b"Traceback:\nAttributeError: missing circuit\xff\n")
    playback.process.poll.return_value = 1
    playback.poll()
    text = playback.message.call_args.args[2]
    assert "Playback process exited before signaling readiness" in text
    assert "AttributeError: missing circuit" in text
    assert text.count("ignored first line") == 13
    assert not playback.log_path.exists()
    assert not playback.window._ready_timer.isActive()


def test_windows_locked_log_cleanup_is_retried_without_repeating_error(playback, monkeypatch):
    playback.start()
    playback.log_path.write_text("injected traceback", encoding="utf-8")
    playback.process.poll.return_value = 1
    real_remove = os.remove
    locked = True

    def remove(path):
        if Path(path) == playback.log_path and locked:
            raise PermissionError("Windows child still holds stderr")
        real_remove(path)

    monkeypatch.setattr(selection.os, "remove", remove)
    playback.poll()
    assert playback.log_path.exists()
    assert playback.window._ready_timer.isActive()
    locked = False
    playback.poll()
    assert not playback.log_path.exists()
    assert not playback.window._ready_timer.isActive()
    playback.message.assert_called_once()


def test_immediate_successful_exit_does_not_report_startup_error(playback):
    playback.start()
    playback.ready_path.write_text("ready")
    playback.process.poll.return_value = 0
    playback.poll()
    assert not list(playback.directory.iterdir())
    playback.message.assert_not_called()


def test_error_dialog_pauses_polling_during_its_nested_event_loop(playback):
    playback.start()
    playback.process.poll.return_value = 1

    def show_message(*args):
        assert not playback.window._ready_timer.isActive()

    playback.message.side_effect = show_message
    playback.poll()
    playback.message.assert_called_once()


def test_log_open_failure_reports_error_without_launching(playback, monkeypatch):
    monkeypatch.setattr(selection, "open", Mock(side_effect=PermissionError("cannot open log")), raising=False)
    playback.start()
    playback.launch.assert_not_called()
    assert "cannot open log" in playback.message.call_args.args[2]
    assert not list(playback.directory.iterdir())
