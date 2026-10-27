import os
import socket
import subprocess
import sys

from src.services.stream import TelemetryStreamServer


# A replay that serves one client, then stops its server and exits.
_PREVIOUS_REPLAY = """
import time
from src.services.stream import TelemetryStreamServer

server = TelemetryStreamServer(port=0)
server.start()
print(server.server_socket.getsockname()[1], flush=True)
while not server.clients:
    time.sleep(0.01)
server.stop()
"""


def test_next_replay_can_start_its_server_after_the_previous_replay_exits():
    # Insight windows keep their old connection open after the replay stops, so the
    # closed connection still holds the port when the next replay starts its server.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    previous = subprocess.Popen(
        [sys.executable, "-c", _PREVIOUS_REPLAY], stdout=subprocess.PIPE, text=True, env=env
    )
    port = int(previous.stdout.readline())
    client = socket.create_connection(("localhost", port))
    try:
        assert previous.wait(timeout=10) == 0
        client.settimeout(5)
        assert client.recv(1) == b""  # the previous replay closed the connection

        server = TelemetryStreamServer(port=port)
        server.start()
        server.stop()
    finally:
        client.close()
        previous.stdout.close()
