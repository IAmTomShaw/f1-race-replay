import socket
import json

# Localhost config
SYNC_IP = "127.0.0.1"
SYNC_PORT = 5005

class TelemetrySender:
    """Used by the Main Race Window to broadcast state."""
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    def send_update(self, frame_index, selected_driver):
        # Pack data into a simple JSON string
        data = {
            "f": frame_index,
            "d": selected_driver
        }
        try:
            msg = json.dumps(data).encode('utf-8')
            self.sock.sendto(msg, (SYNC_IP, SYNC_PORT))
        except:
            pass # Ignore errors if listener isn't open

class TelemetryListener:
    """Used by the Telemetry Window to receive state."""
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Bind allows us to listen
        try:
            self.sock.bind((SYNC_IP, SYNC_PORT))
            self.sock.setblocking(False)
        except OSError:
            print("Telemetry Port busy - is another instance running?")
            
    def get_latest(self):
        """Read the newest packet, discard old ones."""
        latest_data = None
        try:
            # Drain the queue to get the absolute latest packet
            while True:
                data, _ = self.sock.recvfrom(1024)
                latest_data = json.loads(data.decode('utf-8'))
        except BlockingIOError:
            pass # No new data
        except Exception as e:
            print(f"Sync error: {e}")
            
        return latest_data