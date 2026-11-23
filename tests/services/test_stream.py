import time

import pytest

QtCore = pytest.importorskip("PySide6.QtCore")
from src.services import stream

DIRECT = QtCore.Qt.ConnectionType.DirectConnection


class ResetSocket:
    """A connection that was reset: recv() keeps raising, as it does on Windows."""

    def __init__(self, *args, **kwargs):
        self.closed = False

    def settimeout(self, timeout):
        pass

    def connect(self, address):
        pass

    def recv(self, size):
        raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")

    def close(self):
        self.closed = True


def test_client_disconnects_after_connection_reset(monkeypatch):
    sockets = []
    monkeypatch.setattr(stream.socket, "socket", lambda *args: sockets.append(ResetSocket()) or sockets[-1])

    client = stream.TelemetryStreamClient()
    errors, statuses = [], []
    # Direct connections run the slots on the client thread, so no event loop is needed
    client.error_occurred.connect(lambda error: errors.append(error), DIRECT)
    client.connection_status.connect(lambda status: statuses.append(status), DIRECT)

    client.start()
    time.sleep(0.5)
    client.stop()
    assert client.wait(5000)

    assert statuses[:3] == ["Connecting...", "Connected", "Disconnected"]
    assert len(errors) == 1
    assert sockets[0].closed
